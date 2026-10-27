"""Real protocol/lifecycle tests for the Rust headless task service."""
from pathlib import Path
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT), str(ROOT / "电力工具箱")]
from toolbox_platform import hidden_process_options, process_is_alive

SERVICE = Path(os.environ.get("TOOLBOX_SERVICE_BINARY", str(ROOT / "电力工具箱/bin" / ("toolbox-service.exe" if os.name == "nt" else "toolbox-service"))))


@unittest.skipUnless(SERVICE.is_file(), "build native/price-xlsx first (Rust task service)")
class RustServiceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="rust-service-中文 ")
        self.workspace = Path(self.directory.name)
        self.script = self.workspace / "上网电量抓取/export_online_energy.py"
        self.script.parent.mkdir()
        self.script.write_text('print("中文任务日志",flush=True)\n', encoding="utf-8")
        self.process = subprocess.Popen([str(SERVICE), "--workspace", str(self.workspace),
            "--code-root", str(ROOT), "--python", sys.executable], stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8",
            env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"},
            **hidden_process_options())
        self.sequence = 0
        self.assertEqual(json.loads(self.process.stdout.readline())["event"]["kind"], "service-ready")

    def tearDown(self):
        if hasattr(self, "process"):
            if self.process.poll() is None:
                try:
                    self.call("shutdown", {"cancel": True})
                except Exception:
                    self.process.stdin.close()
                try:
                    self.process.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=5)
            for stream in (self.process.stdin, self.process.stdout, self.process.stderr):
                if not stream.closed:
                    stream.close()
        self.directory.cleanup()

    def call(self, method, params=None):
        self.sequence += 1
        self.process.stdin.write(json.dumps(dict(id=self.sequence, method=method, params=params or {}), ensure_ascii=False) + "\n")
        self.process.stdin.flush()
        while line := self.process.stdout.readline():
            row = json.loads(line)
            if row.get("id") == self.sequence:
                if "error" in row:
                    raise ValueError(row["error"])
                return row["result"]
        self.fail("Rust service exited without a reply")

    def start(self, **changes):
        params = dict(tool_id="online-energy", action="run", request_id="request-1", values={"run_date": "2026-10-27"})
        params.update(changes)
        return self.call("start", params)

    def finish(self, task_id):
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            task = next(task for task in self.call("tasks") if task["id"] == task_id)
            if task["state"] not in {"created", "running", "cancelling"}:
                return task
            time.sleep(.02)
        self.fail("Task did not finish")

    def test_protocol_and_streamed_worker_results_are_native(self):
        self.assertEqual(self.call("ping")["engine"], "rust")
        self.assertEqual(len(self.call("catalog")), 15)
        task_id = self.start()
        self.assertEqual(self.start(), task_id)
        task = self.finish(task_id)
        self.assertEqual(task["state"], "succeeded", task)
        self.assertTrue(task["result"])
        events = self.call("events", {"after": 0})
        self.assertTrue(any("中文任务日志" in row["message"] for row in events["events"]))
        self.assertEqual(self.call("events", {"after": events["cursor"]})["events"], [])
        with self.assertRaisesRegex(ValueError, "不同参数"):
            self.start(values={"run_date": "2026-10-28"})

    def test_real_cancellation_owns_worker_business_and_descendant(self):
        self.script.write_text('import os,subprocess,sys,time\nchild=subprocess.Popen([sys.executable,"-c","import time;time.sleep(60)"],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)\nprint(f"owned:{os.getpid()}:{os.getppid()}:{child.pid}",flush=True)\ntime.sleep(60)\n', encoding="utf-8")
        task_id = self.start()
        ready = None
        deadline = time.monotonic() + 15
        while ready is None and time.monotonic() < deadline:
            ready = next((row["message"].strip() for row in self.call("events")["events"] if row["message"].startswith("owned:")), None)
            time.sleep(.02)
        self.assertIsNotNone(ready)
        pids = [int(value) for value in ready.split(":")[1:]]
        self.assertTrue(self.call("cancel", {"task_id": task_id}))
        self.assertEqual(self.finish(task_id)["state"], "cancelled")
        self.assertTrue(all(not process_is_alive(pid) for pid in pids), pids)

    def test_failure_preserves_exit_code_and_redacts_sensitive_logs(self):
        self.script.write_text('print("password=do-not-leak",flush=True)\nraise RuntimeError("first-business-failure")\n', encoding="utf-8")
        task_id = self.start()
        task = self.finish(task_id)
        self.assertEqual(task["state"], "failed")
        self.assertIn("退出码 1", task["error"])
        self.assertIn("\nRuntimeError: first-business-failure\n", task["error"])
        self.assertIn("first-business-failure", task["error"])
        events = self.call("events")
        self.assertNotIn("do-not-leak", json.dumps(events, ensure_ascii=False))
        from toolbox.tasks.errors import RemoteTaskError
        streamed = "".join(row["message"] for row in events["events"] if row["kind"] == "log")
        self.assertNotIn("Traceback", RemoteTaskError(task["error"], streamed).log_details)

    def test_uninterruptible_write_refuses_cancellation_and_shutdown(self):
        target = self.workspace / "市场表更新/update_market_table.py"
        target.parent.mkdir()
        target.write_text('import time\ntime.sleep(1)\n', encoding="utf-8")
        workbook = self.workspace / "市场.xlsx"
        workbook.touch()
        task_id = self.start(tool_id="market-table", values={"run_date": "2026-10-27", "workbook": str(workbook)})
        self.assertFalse(self.call("cancel", {"task_id": task_id}))
        with self.assertRaisesRegex(ValueError, "不可安全中断"):
            self.call("shutdown", {"cancel": True})
        self.finish(task_id)

    def test_bounded_journal_and_invalid_cursor(self):
        self.script.write_text('for n in range(2200):print(f"line-{n}")\n', encoding="utf-8")
        self.finish(self.start())
        batch = self.call("events", {"after": 0})
        self.assertTrue(batch["truncated"])
        self.assertLessEqual(len(batch["events"]), 2000)
        self.assertGreater(batch["cursor"], 2200)
        with self.assertRaisesRegex(ValueError, "游标"):
            self.call("events", {"after": -1})

    def test_fast_parent_exit_reaps_independent_stdio_descendant(self):
        self.script.write_text('import subprocess,sys\nchild=subprocess.Popen([sys.executable,"-c","import time;time.sleep(60)"],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)\nprint(f"descendant:{child.pid}",flush=True)\n', encoding="utf-8")
        task_id = self.start()
        self.assertEqual(self.finish(task_id)["state"], "succeeded")
        line = next(row["message"] for row in self.call("events")["events"] if row["message"].startswith("descendant:"))
        self.assertFalse(process_is_alive(int(line.strip().split(":")[1])))

    def test_host_disconnect_waits_for_noninterruptible_write(self):
        marker = self.workspace / "completed.txt"
        target = self.workspace / "市场表更新/update_market_table.py"
        target.parent.mkdir()
        target.write_text(f'import time\nfrom pathlib import Path\ntime.sleep(.5)\nPath({str(marker)!r}).write_text("complete")\n', encoding="utf-8")
        workbook = self.workspace / "市场.xlsx"
        workbook.touch()
        self.start(tool_id="market-table", values={"run_date": "2026-10-27", "workbook": str(workbook)})
        self.process.stdin.close()
        self.process.wait(timeout=10)
        self.assertEqual(self.process.returncode, 0)
        self.assertEqual(marker.read_text(), "complete")

    def test_invalid_json_is_redacted_and_transport_recovers(self):
        self.process.stdin.write('password=do-not-echo\n')
        self.process.stdin.flush()
        reply = json.loads(self.process.stdout.readline())
        self.assertIsNone(reply["id"])
        self.assertNotIn("do-not-echo", reply["error"])
        self.assertEqual(self.call("ping")["protocol"], 3)

    def test_maintenance_reservation_rejects_start_before_engine_launch(self):
        self.assertTrue(self.call("prepare_update"))
        with self.assertRaisesRegex(ValueError, "正在更新"):
            self.start()
        self.assertEqual(self.call("tasks"), [])
        self.assertTrue(self.call("abort_update"))
        self.assertEqual(self.finish(self.start())["state"], "succeeded")

    def test_invalid_cursor_types_are_not_treated_as_missing(self):
        for value in (None, True, 1.0, "0"):
            with self.subTest(cursor=value), self.assertRaisesRegex(ValueError, "游标"):
                self.call("events", {"after": value})
