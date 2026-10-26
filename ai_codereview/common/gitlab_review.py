#!/usr/bin/env python3
"""GitLab MR 的 AI review 輔助工具（只用 Python 標準庫，CI 映像不需 pip install）。

子指令：
  already-reviewed  此 MR 目前的 head commit 是否已被該模式 review 過（exit 0 = 已 review，可略過）
  prepare           產生 .ai-review/mr.diff 與 changed-files.txt（模式 B 用）
  render-prompt     把 prompt 範本中的 ${VAR} 以環境變數代入後輸出
  mcp-config        輸出 Claude Code 用的 GitLab MCP 設定（模式 A 用，token 不落地到 repo）
  post              解析 Claude 輸出的 JSON findings，發 inline comment + 置頂總結（模式 B）
  verify            確認模式 A 的 agent 有留下總結留言，並統計它發了幾則意見
  preview           離線：拿本機 diff 檔 + Claude 輸出，預覽會怎麼對應到行（不需 GitLab）

必要環境變數（GitLab CI 會自動提供前三個）：
  CI_API_V4_URL, CI_PROJECT_ID, CI_MERGE_REQUEST_IID
  GITLAB_REVIEW_TOKEN   具 api scope 的 Project/Group Access Token（Reporter 以上）
"""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import re
import string
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

MARK = "claude-review"
SEVERITIES = ["low", "medium", "high", "critical"]
SEV_ALIASES = {
    "critical": "critical", "blocker": "critical", "嚴重": "critical", "致命": "critical",
    "high": "high", "major": "high", "高": "high",
    "medium": "medium", "moderate": "medium", "中": "medium",
    "low": "low", "minor": "low", "info": "low", "nit": "low", "低": "low",
}
SEV_LABEL = {"critical": "⛔ 嚴重", "high": "🔴 高", "medium": "🟠 中", "low": "🔵 低"}
RISK_LABEL = {"high": "🔴 高", "medium": "🟠 中", "low": "🟢 低"}
SNAP_DISTANCE = 3  # 模型常差一兩行，允許吸附到最近的 diff 行


# ---------------------------------------------------------------- GitLab API
class GitLab:
    def __init__(self, api_url: str, token: str, project: str, iid: str, dry_run: bool = False):
        if not (api_url and token and project and iid):
            sys.exit("缺少 GitLab 設定：需要 CI_API_V4_URL / GITLAB_REVIEW_TOKEN / CI_PROJECT_ID / CI_MERGE_REQUEST_IID")
        self.base = f"{api_url.rstrip('/')}/projects/{urllib.parse.quote(str(project), safe='')}/merge_requests/{iid}"
        self.token = token
        self.dry_run = dry_run

    def request(self, method: str, path: str = "", params: dict | None = None, data: dict | None = None):
        url = self.base + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        if self.dry_run and method != "GET":
            print(f"[dry-run] {method} {path}\n{json.dumps(data, ensure_ascii=False, indent=2)}\n")
            return {"id": 0}
        body = json.dumps(data).encode() if data is not None else None
        req = urllib.request.Request(url, data=body, method=method)
        req.add_header("PRIVATE-TOKEN", self.token)
        if body is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = resp.read()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:500]
            raise GitLabError(e.code, f"{method} {path} -> HTTP {e.code}: {detail}") from None

    def paged(self, path: str):
        page = 1
        while True:
            items = self.request("GET", path, {"per_page": 100, "page": page}) or []
            yield from items
            if len(items) < 100:
                return
            page += 1

    def mr(self):
        return self.request("GET")

    def diffs(self):
        try:
            return list(self.paged("/diffs"))
        except GitLabError as e:  # GitLab < 15.7 沒有 /diffs
            if e.status != 404:
                raise
            return (self.request("GET", "/changes") or {}).get("changes", [])

    def notes(self):
        return list(self.paged("/notes"))

    def discussions(self):
        return list(self.paged("/discussions"))


class GitLabError(Exception):
    def __init__(self, status: int, msg: str):
        super().__init__(msg)
        self.status = status


def gitlab_from_args(args) -> GitLab:
    return GitLab(
        args.api_url or os.environ.get("CI_API_V4_URL", ""),
        os.environ.get("GITLAB_REVIEW_TOKEN", ""),
        args.project or os.environ.get("CI_PROJECT_ID", ""),
        args.mr or os.environ.get("CI_MERGE_REQUEST_IID", ""),
        dry_run=getattr(args, "dry_run", False),
    )


# ---------------------------------------------------------------- diff 解析
HUNK_RE = re.compile(r"^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@")


def parse_hunks(diff_text: str):
    """回傳 ({new_line: old_line 或 None}, {新增行})。None 代表是新增行（'+'），否則是上下文行。"""
    mapping: dict[int, int | None] = {}
    added: set[int] = set()
    old = new = None
    for raw in diff_text.splitlines():
        if raw.startswith("diff --git "):
            old = new = None
            continue
        m = HUNK_RE.match(raw)
        if m:
            old, new = int(m.group(1)), int(m.group(2))
            continue
        if old is None or raw.startswith("\\"):
            continue
        tag = raw[:1]
        if tag == "+":
            mapping[new] = None
            added.add(new)
            new += 1
        elif tag == "-":
            old += 1
        else:  # ' ' 或空行（有些工具會去掉上下文行的前導空白）
            mapping[new] = old
            old += 1
            new += 1
    return mapping, added


def split_git_diff(text: str) -> list[dict]:
    """把 `git diff` 的整份輸出切成 GitLab /diffs 相同形狀的 list。"""
    files, cur = [], None
    for line in text.splitlines(keepends=True):
        if line.startswith("diff --git "):
            m = re.match(r"diff --git a/(.+?) b/(.+)$", line.rstrip("\n"))
            cur = {"old_path": m.group(1) if m else "", "new_path": m.group(2) if m else "",
                   "diff": "", "deleted_file": False, "new_file": False}
            files.append(cur)
        elif cur is not None:
            if line.startswith("deleted file mode"):
                cur["deleted_file"] = True
            elif line.startswith("new file mode"):
                cur["new_file"] = True
            elif not cur["diff"] and not line.startswith("@@"):
                continue  # hunk 之前的 header（index / --- / +++ / rename ...）
            else:
                cur["diff"] += line
    return files


def build_filemap(diffs: list[dict], local_fallback: tuple[str, str] | None = None) -> dict:
    """path -> {old_path, new_path, deleted, lines, added}。API diff 太大被截斷時，改用本機 git diff 補。"""
    fm = {}
    for d in diffs:
        text = d.get("diff") or ""
        if not text and local_fallback and not d.get("deleted_file"):
            text = _local_diff(local_fallback[0], local_fallback[1], d.get("new_path", ""))
        lines, added = parse_hunks(text)
        entry = {"old_path": d.get("old_path"), "new_path": d.get("new_path"),
                 "deleted": bool(d.get("deleted_file")), "lines": lines, "added": added}
        fm[d.get("new_path")] = entry
        if d.get("old_path") and d.get("old_path") != d.get("new_path"):
            fm.setdefault(d.get("old_path"), entry)
    return fm


def _local_diff(base: str, head: str, path: str) -> str:
    try:
        return subprocess.run(["git", "diff", base, head, "--", path], capture_output=True,
                              text=True, check=True, timeout=60).stdout
    except Exception:
        return ""


def normalize_path(p: str) -> str:
    p = (p or "").strip().strip("`")
    for prefix in ("./", "a/", "b/"):
        if p.startswith(prefix):
            p = p[len(prefix):]
    return p


def resolve_line(finding: dict, filemap: dict):
    """回傳 (entry, line, snapped) 或 (entry|None, None, False)。"""
    entry = filemap.get(normalize_path(finding.get("path", "")))
    try:
        line = int(finding.get("line") or 0)
    except (TypeError, ValueError):
        line = 0
    if not entry or entry["deleted"] or line <= 0 or not entry["lines"]:
        return entry, None, False
    if line in entry["lines"]:
        return entry, line, False
    near = sorted(entry["lines"], key=lambda n: (abs(n - line), n not in entry["added"]))
    if near and abs(near[0] - line) <= SNAP_DISTANCE:
        return entry, near[0], True
    return entry, None, False


def build_position(entry: dict, line: int, refs: dict) -> dict:
    pos = {"position_type": "text", "base_sha": refs["base_sha"], "start_sha": refs["start_sha"],
           "head_sha": refs["head_sha"], "old_path": entry["old_path"], "new_path": entry["new_path"],
           "new_line": line}
    old_line = entry["lines"].get(line)
    if old_line is not None:  # 上下文行需同時給 old_line
        pos["old_line"] = old_line
    return pos


# ---------------------------------------------------------------- 解析 Claude 輸出
def extract_review(text: str) -> tuple[dict, dict]:
    """從 `claude -p --output-format json` 的輸出（或純文字）取出 review JSON。回傳 (review, meta)。"""
    meta: dict = {}
    body = text
    try:
        env = json.loads(text)
    except json.JSONDecodeError:
        env = None
    if isinstance(env, list):  # stream-json / --verbose：取最後一個 result 事件
        results = [e for e in env if isinstance(e, dict) and e.get("type") == "result"]
        env = results[-1] if results else None
    if isinstance(env, dict):
        if "findings" in env:
            return normalize_review(env), meta
        if "result" in env or "subtype" in env:
            meta = {k: env.get(k) for k in ("subtype", "is_error", "num_turns", "duration_ms",
                                            "total_cost_usd", "usage") if k in env}
            body = env.get("result") or ""
    candidates = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", body, re.S)
    for c in reversed(candidates):
        try:
            obj = json.loads(c)
            if isinstance(obj, dict) and "findings" in obj:
                return normalize_review(obj), meta
        except json.JSONDecodeError:
            pass
    dec = json.JSONDecoder()
    for i, ch in enumerate(body):
        if ch == "{":
            try:
                obj, _ = dec.raw_decode(body[i:])
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict) and "findings" in obj:
                return normalize_review(obj), meta
    raise ValueError(f"找不到含 findings 的 JSON（subtype={meta.get('subtype')}）。原始輸出前 300 字：{body[:300]!r}")


def normalize_severity(s) -> str:
    return SEV_ALIASES.get(str(s or "").strip().lower(), "medium")


def normalize_review(obj: dict) -> dict:
    findings = []
    for f in obj.get("findings") or []:
        if not isinstance(f, dict) or not (f.get("title") or f.get("body")):
            continue
        findings.append({
            "path": normalize_path(f.get("path", "")),
            "line": f.get("line"),
            "severity": normalize_severity(f.get("severity")),
            "category": str(f.get("category") or "bug").strip().lower(),
            "title": str(f.get("title") or "").strip() or str(f.get("body"))[:60],
            "body": str(f.get("body") or "").strip(),
            "suggestion": f.get("suggestion") if isinstance(f.get("suggestion"), str) else None,
        })
    findings.sort(key=lambda f: -SEVERITIES.index(f["severity"]))
    risk = str(obj.get("risk") or "").lower()
    return {
        "summary": str(obj.get("summary") or "").strip(),
        "risk": risk if risk in RISK_LABEL else ("high" if any(f["severity"] in ("critical", "high") for f in findings) else "low"),
        "focus_files": [x for x in obj.get("focus_files") or [] if isinstance(x, (dict, str))],
        "findings": findings,
    }


# ---------------------------------------------------------------- 留言內容
def fingerprint(mode: str, f: dict) -> str:
    title = re.sub(r"\W+", "", f["title"].lower())
    return hashlib.sha1(f"{mode}|{f['path']}|{f['category']}|{title}".encode()).hexdigest()[:12]


def inline_body(f: dict, mode: str, fp: str, allow_suggestion: bool) -> str:
    parts = [f"**{SEV_LABEL[f['severity']]}｜{f['title']}**　`{f['category']}`", "", f["body"]]
    sug = f.get("suggestion")
    if allow_suggestion and sug and "```" not in sug:
        parts += ["", "```suggestion:-0+0", sug.rstrip("\n"), "```"]
    parts += ["", f"<sub>🤖 AI review（{mode} 模式）</sub>", f"<!-- {MARK}:fp={fp} -->"]
    return "\n".join(parts)


def esc(s: str) -> str:
    return str(s).replace("|", "\\|").replace("\n", " ")


def summary_body(review: dict, mode: str, head_sha: str, posted: list, not_anchored: list,
                 below_threshold: list, duplicates: int, meta: dict) -> str:
    L = [f"<!-- {MARK}:summary mode={mode} -->", f"<!-- {MARK}:sha={head_sha} -->",
         f"## 🤖 AI Code Review（{mode} 模式）", "",
         f"**風險等級：** {RISK_LABEL.get(review['risk'], review['risk'])}", ""]
    if review["summary"]:
        L += [review["summary"], ""]
    if review["focus_files"]:
        L += ["### 👀 建議人工重點看", ""]
        for x in review["focus_files"]:
            if isinstance(x, dict):
                L.append(f"- `{x.get('path', '')}` — {x.get('reason', '')}")
            else:
                L.append(f"- `{x}`")
        L.append("")
    all_f = posted + not_anchored
    if all_f:
        L += [f"### 發現事項（{len(all_f)}）", "", "| 嚴重度 | 位置 | 問題 |", "|---|---|---|"]
        for f in all_f:
            loc = f"`{f['path']}:{f.get('line') or '-'}`" if f["path"] else "-"
            L.append(f"| {SEV_LABEL[f['severity']]} | {loc} | {esc(f['title'])} |")
        L.append("")
    else:
        L += ["✅ 沒有發現需要回報的問題。", ""]
    if not_anchored:
        L += ["<details><summary>無法掛到 diff 行上的意見（完整內容）</summary>", ""]
        for f in not_anchored:
            L += [f"**{SEV_LABEL[f['severity']]}｜{f['title']}** — `{f['path']}:{f.get('line') or '-'}`", "", f["body"], ""]
        L += ["</details>", ""]
    if below_threshold:
        L += [f"<details><summary>低於門檻、未發行內留言的小建議（{len(below_threshold)}）</summary>", ""]
        for f in below_threshold:
            L.append(f"- `{f['path']}:{f.get('line') or '-'}` {esc(f['title'])} — {esc(f['body'])[:200]}")
        L += ["</details>", ""]
    stats = [f"commit `{head_sha[:8]}`", f"行內 {len(posted)} 則"]
    if duplicates:
        stats.append(f"略過先前已提過的 {duplicates} 則")
    if meta.get("num_turns") is not None:
        stats.append(f"{meta['num_turns']} turns")
    if meta.get("duration_ms"):
        stats.append(f"{meta['duration_ms'] / 1000:.0f}s")
    L.append("<sub>" + " · ".join(stats) + "</sub>")
    return "\n".join(L)


def find_summary(notes: list, mode: str):
    tag = f"<!-- {MARK}:summary mode={mode} -->"
    for n in notes:
        if tag in (n.get("body") or ""):
            return n
    return None


def summary_sha(note) -> str | None:
    m = re.search(rf"<!-- {MARK}:sha=([0-9A-Za-z]+) -->", (note or {}).get("body") or "")
    return m.group(1).lower() if m else None


def existing_fingerprints(discussions: list) -> set:
    fps = set()
    for d in discussions:
        for n in d.get("notes", []):
            fps.update(re.findall(rf"<!-- {MARK}:fp=([0-9a-f]+) -->", n.get("body") or ""))
    return fps


# ---------------------------------------------------------------- 主要流程
def plan(review: dict, filemap: dict, mode: str, min_sev: str, max_inline: int, seen: set):
    """決定每則 finding 要發 inline、放總結、或略過。純函式，方便測試。"""
    inline, not_anchored, below, dup = [], [], [], 0
    threshold = SEVERITIES.index(min_sev)
    for f in review["findings"]:
        fp = fingerprint(mode, f)
        if fp in seen:
            dup += 1
            continue
        seen.add(fp)
        if SEVERITIES.index(f["severity"]) < threshold:
            below.append(f)
            continue
        entry, line, snapped = resolve_line(f, filemap)
        if line is None or len(inline) >= max_inline:
            not_anchored.append(f)
            continue
        inline.append({**f, "fp": fp, "entry": entry, "anchor": line, "snapped": snapped,
                       "added_line": line in entry["added"]})
    return inline, not_anchored, below, dup


def cmd_post(args):
    gl = gitlab_from_args(args)
    with open(args.input, encoding="utf-8") as fh:
        raw = fh.read()
    review, meta = extract_review(raw)
    mr = gl.mr()
    refs = mr["diff_refs"]
    filemap = build_filemap(gl.diffs(), (refs["base_sha"], refs["head_sha"]))
    seen = existing_fingerprints(gl.discussions())
    inline, not_anchored, below, dup = plan(review, filemap, args.mode, args.min_severity, args.max_inline, seen)

    posted = []
    for f in inline:
        body = inline_body(f, args.mode, f["fp"], allow_suggestion=f["added_line"] and not f["snapped"])
        try:
            gl.request("POST", "/discussions", data={"body": body, "position": build_position(f["entry"], f["anchor"], refs)})
            posted.append({**f, "line": f["anchor"]})
        except GitLabError as e:  # 例如行號對不上 GitLab 的 line_code → 改放總結
            print(f"inline 失敗，改列入總結：{f['path']}:{f['anchor']} ({e})", file=sys.stderr)
            not_anchored.append(f)

    body = summary_body(review, args.mode, refs["head_sha"], posted, not_anchored, below, dup, meta)
    existing = find_summary(gl.notes(), args.mode)
    if existing:
        gl.request("PUT", f"/notes/{existing['id']}", data={"body": body})
    else:
        gl.request("POST", "/notes", data={"body": body})
    print(f"完成：行內 {len(posted)}、總結內 {len(not_anchored)}、低於門檻 {len(below)}、重複略過 {dup}")
    if args.fail_on and any(SEVERITIES.index(f["severity"]) >= SEVERITIES.index(args.fail_on) for f in posted + not_anchored):
        print(f"有 {args.fail_on} 以上的問題，依設定讓 job 失敗", file=sys.stderr)
        return 3
    return 0


def cmd_already_reviewed(args):
    gl = gitlab_from_args(args)
    head = gl.mr()["diff_refs"]["head_sha"]
    sha = summary_sha(find_summary(gl.notes(), args.mode))
    if sha == head:
        print(f"{args.mode} 模式已 review 過 {head[:8]}，略過")
        return 0
    return 1


def cmd_verify(args):
    gl = gitlab_from_args(args)
    head = gl.mr()["diff_refs"]["head_sha"]
    note = find_summary(gl.notes(), args.mode)
    ai_notes = sum(1 for d in gl.discussions() for n in d.get("notes", [])
                   if f"{MARK}:fp=" in (n.get("body") or "") and f"（{args.mode} 模式）" in (n.get("body") or ""))
    if not note:
        print(f"⚠️ 找不到 {args.mode} 模式的總結留言，agent 可能中途失敗或沒照指示做", file=sys.stderr)
        return 2
    print(f"總結留言 sha={summary_sha(note)}（head={head[:8]}），行內意見 {ai_notes} 則")
    return 0 if summary_sha(note) == head else 2


def cmd_prepare(args):
    base = os.environ.get("CI_MERGE_REQUEST_DIFF_BASE_SHA") or args.base
    if not base:
        sys.exit("需要 CI_MERGE_REQUEST_DIFF_BASE_SHA 或 --base")
    os.makedirs(args.out, exist_ok=True)
    excludes = [p.strip() for p in os.environ.get("AI_REVIEW_EXCLUDE", "").split(",") if p.strip()]
    numstat = subprocess.run(["git", "diff", "--numstat", base, "HEAD"], capture_output=True, text=True, check=True).stdout
    kept, skipped = [], []
    for row in numstat.splitlines():
        a, d, path = row.split("\t", 2)
        path = path.split(" => ")[-1].rstrip("}")
        (skipped if any(fnmatch.fnmatch(path, g) for g in excludes) else kept).append((a, d, path))
    with open(os.path.join(args.out, "changed-files.txt"), "w", encoding="utf-8") as fh:
        fh.write("# 新增\t刪除\t檔案（已排除自動產生／lock 檔）\n")
        for a, d, p in kept:
            fh.write(f"{a}\t{d}\t{p}\n")
    diff = subprocess.run(["git", "diff", base, "HEAD", "--"] + [p for _, _, p in kept],
                          capture_output=True, text=True, check=True).stdout if kept else ""
    with open(os.path.join(args.out, "mr.diff"), "w", encoding="utf-8") as fh:
        fh.write(diff)
    print(f"變更檔案 {len(kept)} 個（排除 {len(skipped)} 個），diff {diff.count(chr(10))} 行")
    return 0


def cmd_render_prompt(args):
    with open(args.template, encoding="utf-8") as fh:
        print(string.Template(fh.read()).safe_substitute(os.environ))
    return 0


def cmd_mcp_config(args):
    tools = os.environ.get("AI_REVIEW_MCP_TOOLS") or ",".join([
        "get_merge_request", "list_merge_request_changed_files", "get_merge_request_file_diff",
        "mr_discussions", "get_merge_request_notes", "get_issue", "create_draft_note", "list_draft_notes",
        "bulk_publish_draft_notes", "create_note", "update_merge_request_note"])
    cfg = {"mcpServers": {"gitlab": {
        "command": os.environ.get("GITLAB_MCP_COMMAND", "zereight-mcp-gitlab"),
        "args": [],
        "env": {
            "GITLAB_API_URL": os.environ.get("CI_API_V4_URL", ""),
            "GITLAB_PERSONAL_ACCESS_TOKEN": os.environ.get("GITLAB_REVIEW_TOKEN", ""),
            "GITLAB_PERMISSION_MODE": "modify",   # 不給任何刪除類工具
            "GITLAB_TOOLS": tools,                # 白名單：只能讀 MR、留言
            "GITLAB_DISABLE_VERSION_CHECK": "true",
        }}}}
    print(json.dumps(cfg, indent=2))
    return 0


def cmd_preview(args):
    with open(args.input, encoding="utf-8") as fh:
        review, meta = extract_review(fh.read())
    with open(args.diff_file, encoding="utf-8") as fh:
        filemap = build_filemap(split_git_diff(fh.read()))
    inline, not_anchored, below, _ = plan(review, filemap, args.mode, args.min_severity, args.max_inline, set())
    print(f"風險：{review['risk']}　摘要：{review['summary'][:120]}")
    print(f"meta：{meta}")
    for f in inline:
        flag = "（吸附）" if f["snapped"] else ""
        print(f"  [inline] {f['severity']:8} {f['path']}:{f['line']} -> 行 {f['anchor']}{flag}  {f['title']}")
    for f in not_anchored:
        print(f"  [總結]   {f['severity']:8} {f['path']}:{f.get('line')}  {f['title']}")
    for f in below:
        print(f"  [門檻下] {f['severity']:8} {f['path']}:{f.get('line')}  {f['title']}")
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--api-url")
    p.add_argument("--project")
    p.add_argument("--mr")
    sub = p.add_subparsers(dest="cmd", required=True)

    def review_opts(sp):
        sp.add_argument("--mode", default="json")
        sp.add_argument("--min-severity", default=os.environ.get("AI_REVIEW_MIN_SEVERITY", "medium"), choices=SEVERITIES)
        sp.add_argument("--max-inline", type=int, default=int(os.environ.get("AI_REVIEW_MAX_INLINE", "10")))

    sp = sub.add_parser("post"); review_opts(sp)
    sp.add_argument("--input", required=True)
    sp.add_argument("--dry-run", action="store_true")
    sp.add_argument("--fail-on", choices=SEVERITIES, default=os.environ.get("AI_REVIEW_FAIL_ON") or None)
    sp.set_defaults(func=cmd_post)

    sp = sub.add_parser("already-reviewed"); sp.add_argument("--mode", default="json"); sp.set_defaults(func=cmd_already_reviewed)
    sp = sub.add_parser("verify"); sp.add_argument("--mode", default="mcp"); sp.set_defaults(func=cmd_verify)
    sp = sub.add_parser("prepare"); sp.add_argument("--out", default=".ai-review"); sp.add_argument("--base"); sp.set_defaults(func=cmd_prepare)
    sp = sub.add_parser("render-prompt"); sp.add_argument("template"); sp.set_defaults(func=cmd_render_prompt)
    sp = sub.add_parser("mcp-config"); sp.set_defaults(func=cmd_mcp_config)
    sp = sub.add_parser("preview"); review_opts(sp)
    sp.add_argument("--input", required=True); sp.add_argument("--diff-file", required=True)
    sp.set_defaults(func=cmd_preview)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
