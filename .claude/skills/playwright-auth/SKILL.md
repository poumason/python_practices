---
name: playwright-auth
description: Reuse a saved login for the local web app (http://localhost:5173) when driving it with the Playwright MCP browser. On the first run the user logs in manually in the browser window and the session (cookies + localStorage) is saved to .auth/localhost-5173.json; later runs load that file so nobody has to type the account and password again. Use this skill whenever you are about to open, test, click through, screenshot, or debug localhost:5173 (or any page of it) with mcp__playwright__* tools, whenever the page redirects to /login, or when the user says things like "log in once and remember it", "save the auth/session/cookies", "reuse my login", "auth state", or "storageState".
---

# Playwright MCP: log in once, reuse the session

The app at `http://localhost:5173` requires an account and password. The user doesn't want to give credentials to Claude or type them every time. Instead:

1. **First time:** open the login page in the Playwright browser window. The user logs in there by hand, and Claude saves the browser state to a file.
2. **After that:** load the file into the browser before navigating, and the app sees an already-logged-in user.

Defaults (change them if the user names another app or path):

| Setting | Value |
|---|---|
| Base URL | `http://localhost:5173` |
| Auth file | `<project root>/.auth/localhost-5173.json`, using an **absolute** path |

The path must be absolute because `browser_run_code_unsafe` runs inside the MCP server process. That process's working directory is not the project, and the code can't import `fs`, so Playwright's own `path` options are the only way to read or write files.

## Workflow

### Step 1: Try the saved session

Check whether the auth file exists (`ls`). If it exists, load it and see whether you're still logged in:

```js
async (page) => {
  const AUTH = '/ABS/PATH/.auth/localhost-5173.json';
  await page.context().setStorageState(AUTH);
  await page.goto('http://localhost:5173/');
  await page.waitForLoadState('networkidle').catch(() => {});
  const onLogin = /\/(login|signin|sign-in|auth)\b/i.test(new URL(page.url()).pathname)
    || await page.locator('input[type=password]').count() > 0;
  return { url: page.url(), loggedIn: !onLogin };
}
```

- `loggedIn: true` means you're done. Continue with the user's actual task, and navigate anywhere in the app with `browser_navigate`.
- `loggedIn: false` means the session expired or was revoked. Go to Step 2.
- No file means this is the first time. Go to Step 2.

`setStorageState` replaces the context's cookies and localStorage, so call it before navigating, not after.

### Step 2: Manual login, then save

Open the login page with `browser_navigate` to `http://localhost:5173/login`, or to `/` and let the app redirect. Then tell the user, in their language, something like:

> The Playwright browser window is showing the login page. Please enter your account and password there and log in. I'll save the session automatically when it finishes.

Never ask the user to type their password into the chat, and never fill in the login form yourself. The point of this skill is that credentials stay in the browser.

Then wait for the login to finish and save it in one call:

```js
async (page) => {
  const AUTH = '/ABS/PATH/.auth/localhost-5173.json';
  await page.waitForURL(u => !/\/(login|signin|sign-in|auth)\b/i.test(u.pathname), { timeout: 180_000 });
  await page.waitForLoadState('networkidle').catch(() => {});
  await page.context().storageState({ path: AUTH, indexedDB: true });
  return { saved: AUTH, url: page.url() };
}
```

If this call times out (the user was slow, or the MCP tool has a shorter timeout), don't treat it as a failure. Ask the user to say "done" after logging in, check with `browser_snapshot` that the page is past the login screen, and then run just the `storageState({ path: AUTH, indexedDB: true })` part.

Create the `.auth/` directory first (`mkdir -p`). Make sure `.auth/` is listed in `.gitignore`, and add it if it isn't. The file contains live session tokens and must not be committed.

### Step 3: Verify once

Right after the first save, run the Step 1 snippet again. This confirms the saved file really restores the login. Report the result to the user in one line, e.g. "Login saved to `.auth/localhost-5173.json`; next time no login needed."

If it does **not** restore (you're bounced back to /login), the app probably keeps its token in **sessionStorage**, which `storageState` doesn't capture. Handle it like this:

- While logged in, read the keys with `page.evaluate(() => Object.keys(sessionStorage))`. Show the user only the key names, never the values.
- Save the sessionStorage contents with `storageState`, or as a second file via `page.evaluate` plus `browser_run_code_unsafe` `filename`. Whichever way you save it, restore it on future runs with `page.context().addInitScript(...)` before navigating.

Explain to the user what you found before building this.

## Handling the file safely

- Don't `cat` or Read the auth JSON into the conversation. It holds cookies and tokens, and putting them in the transcript would spread them. Check that it exists and has a recent mtime (`ls -l`). That's enough.
- To "log out" or force a fresh login, delete the file and do Step 2 again.

## Alternative: load the file at MCP startup

If the user would rather have every Playwright MCP session start logged in automatically, the server can be launched with the file. Change the MCP args (in `~/.claude.json` or `.mcp.json`) to:

```
"args": ["@playwright/mcp@latest", "--browser=msedge", "--isolated", "--storage-state=/ABS/PATH/.auth/localhost-5173.json"]
```

`--storage-state` only takes effect together with `--isolated`. Claude Code needs a restart afterwards. Suggest this only if the user asks. The in-session approach above needs no config change and recovers from expired sessions by itself.
