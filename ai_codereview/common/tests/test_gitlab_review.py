"""執行：python3 -m unittest discover -s ci/ai-review/tests -v"""
import json
import os
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import gitlab_review as gr  # noqa: E402

API_DIFF = """@@ -10,6 +10,8 @@ class OrderService {
   async charge(order) {
     const user = await this.repo.findUser(order.userId);
-    const amount = order.total;
+    const amount = order.total * (1 - order.discount);
+    const res = await fetch(PAYMENT_URL, { body: amount });
+    log.info(`charge ${user.token}`);
     return res;
   }
 }
"""

GIT_DIFF = """diff --git a/src/order/service.ts b/src/order/service.ts
index 111..222 100644
--- a/src/order/service.ts
+++ b/src/order/service.ts
""" + API_DIFF + """diff --git a/README.md b/README.md
deleted file mode 100644
--- a/README.md
+++ /dev/null
@@ -1,2 +0,0 @@
-# old
--- a line that starts with two dashes
"""

CLAUDE_OUTPUT = {
    "type": "result", "subtype": "success", "is_error": False, "num_turns": 12, "duration_ms": 95000,
    "result": "我看完了，以下是結果：\n```json\n" + json.dumps({
        "summary": "調整扣款金額計算並呼叫付款 API。",
        "risk": "high",
        "focus_files": [{"path": "src/order/service.ts", "reason": "扣款邏輯"}],
        "findings": [
            {"path": "src/order/service.ts", "line": 14, "severity": "高", "category": "security",
             "title": "log 輸出使用者 token", "body": "違反不得記錄 token 的規定。",
             "suggestion": "    log.info(`charge ${user.id}`);"},
            {"path": "./src/order/service.ts", "line": 12, "severity": "high", "category": "bug",
             "title": "fetch 沒有 timeout", "body": "外部呼叫需設定 timeout。"},
            {"path": "src/order/service.ts", "line": 11, "severity": "medium", "category": "bug",
             "title": "discount 可能 undefined", "body": "會變成 NaN。"},
            {"path": "src/order/service.ts", "line": 0, "severity": "medium", "category": "test",
             "title": "缺少測試", "body": "扣款邏輯沒有測試。"},
            {"path": "src/order/service.ts", "line": 13, "severity": "low", "category": "standard",
             "title": "變數命名", "body": "res 可以更清楚。"},
        ],
    }, ensure_ascii=False) + "\n```\n",
}


class ParseTests(unittest.TestCase):
    def test_parse_hunks(self):
        mapping, added = gr.parse_hunks(API_DIFF)
        self.assertEqual(added, {12, 13, 14})
        self.assertEqual(mapping[10], 10)   # 上下文行帶 old_line
        self.assertEqual(mapping[11], 11)
        self.assertEqual(mapping[15], 13)   # 刪一行、加三行後的偏移
        self.assertIsNone(mapping[12])

    def test_split_git_diff_keeps_dash_lines_and_deleted_files(self):
        files = gr.split_git_diff(GIT_DIFF)
        self.assertEqual([f["new_path"] for f in files], ["src/order/service.ts", "README.md"])
        self.assertTrue(files[1]["deleted_file"])
        self.assertIn("--- a line that starts", files[1]["diff"])
        self.assertEqual(gr.parse_hunks(files[0]["diff"])[1], {12, 13, 14})

    def test_extract_from_claude_envelope(self):
        review, meta = gr.extract_review(json.dumps(CLAUDE_OUTPUT, ensure_ascii=False))
        self.assertEqual(meta["num_turns"], 12)
        self.assertEqual(len(review["findings"]), 5)
        self.assertEqual(review["findings"][0]["severity"], "high")      # 「高」→ high
        self.assertEqual(review["findings"][1]["path"], "src/order/service.ts")  # 去掉 ./

    def test_extract_from_plain_text_without_fence(self):
        text = '結論如下 {"summary": "ok", "risk": "low", "findings": []} 謝謝'
        review, _ = gr.extract_review(text)
        self.assertEqual(review["findings"], [])

    def test_extract_error_raises(self):
        with self.assertRaises(ValueError):
            gr.extract_review(json.dumps({"type": "result", "subtype": "error_max_turns", "is_error": True}))

    def test_plan_thresholds_snapping_and_dedup(self):
        review, _ = gr.extract_review(json.dumps(CLAUDE_OUTPUT, ensure_ascii=False))
        fm = gr.build_filemap(gr.split_git_diff(GIT_DIFF))
        review["findings"].append({**review["findings"][2], "line": 30})  # 同一問題、行號不同 → 重複
        review["findings"].append({"path": "src/order/service.ts", "line": 40, "severity": "high",
                                   "category": "bug", "title": "離 diff 很遠", "body": "x", "suggestion": None})
        inline, not_anchored, below, dup = gr.plan(review, fm, "json", "medium", 10, set())
        self.assertEqual([f["anchor"] for f in inline], [14, 12, 11])
        self.assertEqual({f["title"] for f in not_anchored}, {"缺少測試", "離 diff 很遠"})
        self.assertEqual([f["title"] for f in below], ["變數命名"])
        self.assertEqual(dup, 1)

    def test_snap_to_nearby_line(self):
        fm = gr.build_filemap(gr.split_git_diff(GIT_DIFF))
        entry, line, snapped = gr.resolve_line({"path": "src/order/service.ts", "line": 18}, fm)
        self.assertEqual((line, snapped), (17, True))

    def test_position_for_context_line_has_old_line(self):
        fm = gr.build_filemap(gr.split_git_diff(GIT_DIFF))
        refs = {"base_sha": "b", "start_sha": "s", "head_sha": "h"}
        e = fm["src/order/service.ts"]
        self.assertNotIn("old_line", gr.build_position(e, 12, refs))
        self.assertEqual(gr.build_position(e, 15, refs)["old_line"], 13)


# ------------------------------------------------------------ 假 GitLab 伺服器
class FakeGitLab:
    def __init__(self):
        self.notes, self.discussions, self.calls = [], [], []
        self.reject_line = None

    def handler(self):
        fake = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, code, obj):
                data = json.dumps(obj).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(data)

            def _body(self):
                n = int(self.headers.get("Content-Length") or 0)
                return json.loads(self.rfile.read(n)) if n else None

            def do_GET(self):
                path = self.path.split("?")[0]
                assert self.headers["PRIVATE-TOKEN"] == "tkn"
                base = "/api/v4/projects/group%2Fapp/merge_requests/7"
                if path == base:
                    return self._send(200, {"diff_refs": {"base_sha": "base1", "start_sha": "start1", "head_sha": "head123abc"}})
                if path == base + "/diffs":
                    return self._send(200, [{"old_path": "src/order/service.ts", "new_path": "src/order/service.ts",
                                             "diff": API_DIFF, "deleted_file": False}])
                if path == base + "/notes":
                    return self._send(200, fake.notes)
                if path == base + "/discussions":
                    return self._send(200, fake.discussions)
                return self._send(404, {})

            def do_POST(self):
                body = self._body()
                fake.calls.append(("POST", self.path, body))
                if self.path.endswith("/discussions"):
                    if fake.reject_line and body["position"]["new_line"] == fake.reject_line:
                        return self._send(400, {"message": "line_code invalid"})
                    fake.discussions.append({"notes": [{"body": body["body"]}]})
                    return self._send(201, {"id": len(fake.discussions)})
                if self.path.endswith("/notes"):
                    note = {"id": 900 + len(fake.notes), "body": body["body"]}
                    fake.notes.append(note)
                    return self._send(201, note)
                return self._send(404, {})

            def do_PUT(self):
                body = self._body()
                fake.calls.append(("PUT", self.path, body))
                nid = int(self.path.rsplit("/", 1)[-1])
                for n in fake.notes:
                    if n["id"] == nid:
                        n["body"] = body["body"]
                return self._send(200, {"id": nid})
        return H


class EndToEndTests(unittest.TestCase):
    def setUp(self):
        self.fake = FakeGitLab()
        self.server = HTTPServer(("127.0.0.1", 0), self.fake.handler())
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.api = f"http://127.0.0.1:{self.server.server_port}/api/v4"
        os.environ["GITLAB_REVIEW_TOKEN"] = "tkn"
        fd, self.out = tempfile.mkstemp(suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(CLAUDE_OUTPUT, fh, ensure_ascii=False)

    def tearDown(self):
        self.server.shutdown()
        os.unlink(self.out)

    def run_cli(self, *args):
        return gr.main(["--api-url", self.api, "--project", "group/app", "--mr", "7", *args])

    def test_post_then_rerun_updates_summary_and_skips_duplicates(self):
        self.fake.reject_line = 11  # 模擬 GitLab 拒絕某一行
        self.assertEqual(self.run_cli("already-reviewed", "--mode", "json"), 1)
        self.assertEqual(self.run_cli("post", "--mode", "json", "--input", self.out), 0)

        inline = [c for c in self.fake.calls if c[1].endswith("/discussions")]
        self.assertEqual([c[2]["position"]["new_line"] for c in inline], [14, 12, 11])
        pos = inline[0][2]["position"]
        self.assertEqual((pos["base_sha"], pos["start_sha"], pos["head_sha"]), ("base1", "start1", "head123abc"))
        self.assertIn("```suggestion:-0+0", inline[0][2]["body"])     # 新增行 + 有 suggestion
        self.assertEqual(len(self.fake.discussions), 2)                # 第 11 行被拒 → 進總結

        summary = self.fake.notes[0]["body"]
        self.assertIn("<!-- claude-review:sha=head123abc -->", summary)
        self.assertIn("discount 可能 undefined", summary)
        self.assertIn("12 turns", summary)
        self.assertEqual(self.run_cli("already-reviewed", "--mode", "json"), 0)
        self.assertEqual(self.run_cli("already-reviewed", "--mode", "mcp"), 1)

        # 再跑一次（例如新 push 後模型又提同樣問題）：不重發 inline，總結改用 PUT 更新
        self.fake.calls.clear()
        self.fake.reject_line = None
        self.assertEqual(self.run_cli("post", "--mode", "json", "--input", self.out), 0)
        methods = [(m, p.rsplit("/", 1)[-1]) for m, p, _ in self.fake.calls]
        self.assertIn(("PUT", "900"), methods)
        self.assertEqual(len(self.fake.notes), 1)
        self.assertEqual(sum(1 for m, p in methods if p == "discussions"), 1)  # 只有先前被拒的那則補發

    def test_fail_on_critical(self):
        data = json.loads(json.dumps(CLAUDE_OUTPUT))
        data["result"] = data["result"].replace('"高"', '"critical"')
        with open(self.out, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False)
        self.assertEqual(self.run_cli("post", "--mode", "json", "--input", self.out, "--fail-on", "critical"), 3)

    def test_verify_mcp_mode(self):
        self.assertEqual(self.run_cli("verify", "--mode", "mcp"), 2)
        self.fake.notes.append({"id": 1, "body": "<!-- claude-review:summary mode=mcp -->\n<!-- claude-review:sha=head123abc -->"})
        self.fake.discussions.append({"notes": [{"body": "x\n<sub>🤖 AI review（mcp 模式）</sub>\n<!-- claude-review:fp=mcp -->"}]})
        self.assertEqual(self.run_cli("verify", "--mode", "mcp"), 0)


if __name__ == "__main__":
    unittest.main()
