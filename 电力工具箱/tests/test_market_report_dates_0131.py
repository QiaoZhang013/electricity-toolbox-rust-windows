from __future__ import annotations

import importlib
import io
import queue
import sys
import tempfile
import time
import tkinter as tk
import unittest
from datetime import date, timedelta
from pathlib import Path
from tkinter import ttk
from unittest import mock
from contextlib import redirect_stderr

from openpyxl import Workbook

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "南方分公司电力市场日报"))
from gd_power_report.company_clearing_xlsx import _strategy_lines
from gd_power_report.legacy_concise_report import _split_strategy_profit
from toolbox import workflows
from toolbox.market_report_page import MarketReportPage
from toolbox.runtime import TaskRegistry, ToolPaths

DAY = date(2026, 11, 6)


def write_workbook(path, report_day, *, previous=False):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "分公司" if previous else "新快报"
    sheet["A2" if previous else "A6"] = report_day
    workbook.save(path)
    workbook.close()
    return path


class ReportDateServiceTests(unittest.TestCase):
    def test_service_form_does_not_offer_a_manual_report_date(self):
        from toolbox.service_catalog import desktop_catalog
        form = next(tool for tool in desktop_catalog(ToolPaths(ROOT)) if tool["id"] == "market-report")
        self.assertNotIn("report_date", {field["key"] for field in form["fields"]})

    def test_shared_reader_uses_workbook_date_before_filename(self):
        module = importlib.import_module("toolbox.market_report_dates")
        with tempfile.TemporaryDirectory() as folder:
            path = write_workbook(Path(folder) / "分公司2026.11.10.xlsx", DAY)
            self.assertEqual(module.report_date_from_day_report(path), DAY)

    def test_cli_keeps_explicit_date_and_optional_override_contract(self):
        import run_market_report as runner
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as folder:
            paths = [write_workbook(Path(folder) / f"{index}.xlsx", DAY - timedelta(days=index),
                                    previous=index == 1) for index in range(3)]
            argv = ["run_market_report", DAY.isoformat(), "--day-report", str(paths[0]),
                    "--previous-report", str(paths[1]), "--d2-report", str(paths[2]),
                    "--dongguan-operation", "一套运行", "--realtime-maintenance", "0"]
            with mock.patch.object(sys, "argv", argv), \
                    mock.patch.object(runner.AppConfig, "from_workspace", return_value=object()), \
                    mock.patch.object(runner, "run_pipeline", return_value=SimpleNamespace(
                        preview_pdf_path="phone.pdf", print_pdf_path="print.pdf")) as run, \
                    mock.patch("builtins.print"):
                self.assertEqual(runner.main(), 0)
            self.assertEqual(run.call_args.args[1], DAY)
            self.assertEqual(run.call_args.kwargs["dongguan_operation_override"], "一套运行")
            self.assertEqual(run.call_args.kwargs["realtime_maintenance_capacity"], 0)

    def test_cli_rejects_each_mismatched_workbook_before_config_or_network(self):
        import run_market_report as runner
        for mismatch, label in ((0, "D 日收益表"), (1, "D-1 日收益表"), (2, "D-2 日收益表")):
            with self.subTest(label=label), tempfile.TemporaryDirectory() as folder:
                paths = [write_workbook(Path(folder) / f"{index}.xlsx",
                                        DAY - timedelta(days=index) + timedelta(days=index == mismatch),
                                        previous=index == 1) for index in range(3)]
                argv = ["run_market_report", DAY.isoformat(), "--day-report", str(paths[0]),
                        "--previous-report", str(paths[1]), "--d2-report", str(paths[2])]
                error = io.StringIO()
                with mock.patch.object(sys, "argv", argv), redirect_stderr(error), \
                        mock.patch.object(runner.AppConfig, "from_workspace") as config, \
                        mock.patch.object(runner, "run_pipeline") as run:
                    with self.assertRaises(SystemExit) as caught:
                        runner.main()
                self.assertEqual(caught.exception.code, 2)
                self.assertIn(label, error.getvalue())
                config.assert_not_called()
                run.assert_not_called()

    def test_service_uses_d_workbook_and_accepts_legacy_optional_parameters(self):
        with tempfile.TemporaryDirectory() as folder:
            paths = [write_workbook(Path(folder) / f"{index}.xlsx", DAY - timedelta(days=index),
                                    previous=index == 1) for index in range(3)]
            values = dict(zip(("day_report", "previous_report", "d2_report"), map(str, paths)))
            values.update(report_date="2026-01-01", dongguan_operation="一套运行", realtime_maintenance="0")
            validated = workflows.validate(ToolPaths(ROOT), "market-report", "run", values)
            command = workflows.plan(ToolPaths(ROOT), "market-report", "run", validated)[0][0]
            self.assertEqual(command[2], DAY.isoformat())
            self.assertEqual(command[command.index("--dongguan-operation") + 1], "一套运行")
            self.assertEqual(float(command[command.index("--realtime-maintenance") + 1]), 0)

    def test_strategy_splits_plants_and_keeps_unlabelled_lead(self):
        rows = _strategy_lines(
            "各厂报价策略与收益\n粤东区域：\n500kV线路检修。\n"
            "2汕头厂：汕头报价。各机组日前收益分别为：68万元。\n"
            "（3）海门厂：海门报价。\n4、东莞厂：东莞报价。"
        )
        self.assertEqual([row["plant"] for row in rows], ["", "汕头厂", "海门厂", "东莞厂"])
        self.assertEqual(_split_strategy_profit(rows[0])["paragraphs"], ["500kV线路检修。"])


class ReportDateUiTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.registry = TaskRegistry()
        self.page = MarketReportPage(self.root, ToolPaths(ROOT), self.registry)

    def tearDown(self):
        self.root.update_idletasks()
        if self.page.winfo_exists():
            self.page.destroy()
        self.registry.terminate_all()
        self.root.destroy()

    def wait_until(self, predicate):
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            self.root.update()
            if predicate():
                return
            time.sleep(0.01)
        self.fail("等待报告日期识别超时")

    def test_date_is_readonly_and_replacement_clears_manual_values(self):
        def descendants(widget):
            for child in widget.winfo_children():
                yield child
                yield from descendants(child)

        self.assertEqual(self.page.report_date.get(), "")
        entries = [child for child in descendants(self.page) if isinstance(child, ttk.Entry)
                   and str(child.cget("textvariable")) == str(self.page.report_date)]
        self.assertEqual([str(entry.cget("state")) for entry in entries], ["readonly"])
        with tempfile.TemporaryDirectory() as folder:
            first = write_workbook(Path(folder) / "first.xlsx", DAY)
            second = write_workbook(Path(folder) / "second.xlsx", DAY + timedelta(days=1))
            self.page.day_report.set(str(first))
            self.page.read_report_date(first)
            self.wait_until(lambda: self.page.report_date.get() == DAY.isoformat())
            self.page.save_manual_market({"report_date": DAY.isoformat()})
            self.page.day_report.set(str(second))
            self.page.read_report_date(second)
            self.wait_until(lambda: self.page.report_date.get() == (DAY + timedelta(days=1)).isoformat())
            self.assertEqual(self.page.manual_market.get(), "")

    def test_unreadable_workbook_blocks_report_and_shows_first_error(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "bad.xlsx"
            path.touch()
            for variable in (self.page.day_report, self.page.previous_report, self.page.d2_report):
                variable.set(str(path))
            self.page.read_report_date(path)
            self.wait_until(lambda: "失败" in self.page.date_hint.cget("text"))
            self.assertEqual(self.page.report_date.get(), "")
            with mock.patch("toolbox.market_report_page.messagebox.showerror") as error, \
                    mock.patch.object(self.page, "run_process") as run:
                self.page.start_report()
            run.assert_not_called()
            self.assertIn("识别", error.call_args.args[1])

    def test_stale_async_result_cannot_replace_latest_date(self):
        self.assertTrue(hasattr(self.page, "_poll_report_date"), "必须有异步日期结果处理")
        self.page._date_token = 2
        self.page.report_date.set(DAY.isoformat())
        results = queue.Queue()
        results.put((Path("old.xlsx"), DAY - timedelta(days=1), ""))
        self.page._poll_report_date(results, 1)
        self.assertEqual(self.page.report_date.get(), DAY.isoformat())

    def test_destroy_cancels_pending_date_polls(self):
        self.assertTrue(hasattr(self.page, "_poll_report_date"), "必须有异步日期结果处理")
        results = queue.Queue()
        self.page._poll_report_date(results, self.page._date_token)
        polls = tuple(self.page._date_polls.values())
        self.assertTrue(polls)
        self.page.destroy()
        pending = set(self.root.tk.call("after", "info"))
        self.assertFalse(pending.intersection(polls))
        self.assertEqual(self.page._date_polls, {})
        results.put((Path("late.xlsx"), DAY, ""))
        self.page._poll_report_date(results, self.page._date_token)
        self.assertEqual(self.page._date_polls, {})

    def test_gui_and_remote_service_use_the_same_workbook_date(self):
        with tempfile.TemporaryDirectory() as folder:
            paths = [write_workbook(Path(folder) / f"{index}.xlsx", DAY - timedelta(days=index),
                                    previous=index == 1) for index in range(3)]
            for path, variable in zip(paths, (self.page.day_report, self.page.previous_report, self.page.d2_report)):
                variable.set(str(path))
            command = self.page.build_command()
            self.assertEqual(command[2], DAY.isoformat())
            from toolbox.ui_tasks import RemoteTaskRegistry
            registry = RemoteTaskRegistry(None)
            with mock.patch.object(registry, "execute_remote", return_value={}) as execute:
                registry.prepare_page_worker(self.page, "生成日报", command=command, process=True)(None)
            values = execute.call_args.args[2]
            self.assertNotIn("report_date", values)
            validated = workflows.validate(ToolPaths(ROOT), "market-report", "run", values)
            self.assertEqual(workflows.plan(ToolPaths(ROOT), "market-report", "run", validated)[0][0], command)
