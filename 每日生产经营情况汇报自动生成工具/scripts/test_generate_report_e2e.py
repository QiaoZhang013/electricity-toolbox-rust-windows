"""Exercise the Word generator with real synthetic Excel inputs and offline APIs."""
from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from docx import Document
from openpyxl import load_workbook

import generate_red_marked_report as report
from test_daily_clearing_fill import _build_workbook
from test_unit_status import BASE_ROWS


def make_sources(directory: Path) -> list[Path]:
    sources = []
    for day in (5, 6, 4):  # D-1, D, D-2, in GUI order.
        path = directory / f"出清情况（分公司2026.11.{day}）.xlsx"
        _build_workbook(path)
        book = load_workbook(path)
        basic = book.create_sheet("基础信息")
        basic["A2"] = datetime(2026, 11, day)
        basic["AA64"], basic["AC64"] = 124, 76
        for row_index, row in enumerate(BASE_ROWS, 5):
            for column, value in enumerate(row, 1):
                basic.cell(row_index, column, value)
        ahead = book.create_sheet("快报（日前）")
        for row, energy, price in ((7, 100, 400), (8, 20, 410), (13, 30, 420), (19, 40, 430)):
            ahead.cell(row, 6, energy)
            ahead.cell(row, 7, price)
        for row, label, energy, price in ((25, "汕头海风", 5, 300), (26, "鮀莲光伏", 3, 310), (27, "归湖光伏", 2, 320)):
            ahead.cell(row, 1, label)
            ahead.cell(row, 7, energy)
            ahead.cell(row, 8, price)
        ahead["A39"] = "日前简析：\n2汕头厂：合成汕头策略。\n3.海门厂：合成海门策略。\n4、东莞厂：合成东莞策略。"
        book["快报"]["J7"] = 635  # 605 thermal + 30 Qingyuan; plus 100 wind.
        for cell, value in (("K32", 100), ("K33", 0), ("K34", 0)):
            book["快报"][cell] = value
        book.save(path)
        book.close()
        sources.append(path)
    return sources


def website_payload():
    metric = dict(selected=1000, compare=1000, difference=0)
    summary = dict(selected=dict(max=1000, min=500, avg=700), maxDiff=0, minDiff=0, avgDiff=0)
    prices = [dict(dataType=kind, selectedDailyAvgPrice=-20.5, difference=-1.5) for kind in ("PRE", "RT")]
    return dict(
        loadCompare=dict(subjects=[dict(loadType=code, comparison={key: metric for key in ("最大值(MW)", "最小值(MW)", "平均值(MW)")}) for code in ("1", "6", "2", "3")]),
        priceBoard=dict(rows=prices),
        marketAnalysisData=dict(loadInfo=dict(byType={code: dict(actual=summary, dayAhead=summary) for code in ("1", "6", "2", "3")}), priceBoard=dict(rows=prices)),
        rollingForecast=dict(rows=[dict(forecastDate=(datetime(2026, 11, 7) + timedelta(days=i)).strftime("%Y-%m-%d"), dailyTotal=24000, hours=[1000] * 24) for i in range(5)]),
    )


def generate_offline(directory: Path, *, blank_online=False, missing_online=False):
    sources = make_sources(directory)
    if blank_online:
        book = load_workbook(sources[0])
        for row in book["快报"].iter_rows(min_col=10, max_col=11):
            for cell in row:
                cell.value = 0
        book.save(sources[0])
        book.close()
    if missing_online:
        book = load_workbook(sources[0])
        book["快报"]["J8"] = None
        book.save(sources[0])
        book.close()
    before = [hashlib.sha256(path.read_bytes()).hexdigest() for path in sources]
    with patch("fetch_daily_data.run_daily_data", return_value=website_payload()), patch.object(report, "replace_weather_prefix"):
        document, audit = report.generate(
            "2026-11-06", report.LOCAL_TEMPLATE_PATH, directory / "output",
            online_workbook=sources[0], day_ahead_workbook=sources[1], daily_clearing_workbook=sources[2],
            prefer_previous_template=False,
        )
    assert [hashlib.sha256(path.read_bytes()).hexdigest() for path in sources] == before
    return document, json.loads(audit.read_text(encoding="utf-8"))


class GenerateReportEndToEndTests(unittest.TestCase):
    def test_excel_to_word_and_audit_readback(self):
        with tempfile.TemporaryDirectory() as directory:
            path, audit = generate_offline(Path(directory))
            saved = Document(path)
            text = "\n".join(p.text for p in saved.paragraphs)
            self.assertIn("11月5日分公司上网电量735万千瓦时", text)
            self.assertIn("清远30万千瓦时", text)
            self.assertIn("11月6日分公司日前出清电量130万千瓦时", text)
            self.assertIn("清远（计划）20万千瓦时", text)
            self.assertIn("汕头厂：合成汕头策略。", text)
            self.assertIn("一套机组备用，二套机组调峰", text)
            self.assertNotIn("粤东区域", text)
            self.assertEqual(audit["workbookDateWarnings"], [])
            self.assertEqual(audit["dailyClearingRows"], 11)
            self.assertEqual(audit["startupStatusParagraphs"], 8)
            self.assertIsNone(audit["onlineEnergyError"])
            self.assertIsNone(audit["unitStatusError"])
            self.assertTrue(audit["spotDeviationFilled"])
            self.assertEqual(audit["plantStrategiesMissing"], [])
            company = next(row for row in saved.tables[0].rows if row.cells[0].text.replace(" ", "") == "分公司火电")
            self.assertEqual(company.cells[19].text, "61")
            self.assertEqual(company.cells[21].text, "360")
            self.assertEqual(saved.tables[1].cell(2, 1).text, "100")
            self.assertEqual(len(audit["tablePageBreaks"]), 2)

    def test_unreleased_online_preserves_template_numbers_and_audits_reason(self):
        with tempfile.TemporaryDirectory() as directory:
            path, audit = generate_offline(Path(directory), blank_online=True)
            text = "\n".join(p.text for p in Document(path).paragraphs)
            self.assertIn("11月5日分公司上网电量", text)
            self.assertIn("尚未出数", audit["onlineEnergyError"])
            self.assertEqual(audit["dailyClearingRows"], 11)

    def test_missing_energy_is_audited_and_never_allocated_to_qingyuan(self):
        with tempfile.TemporaryDirectory() as directory:
            path, audit = generate_offline(Path(directory), missing_online=True)
            saved = Document(path)
            paragraph = next(p for p in saved.paragraphs if p.text.startswith("11月5日分公司上网电量"))
            self.assertIn("J8", audit["onlineEnergyError"])
            self.assertNotIn("清远235万千瓦时", paragraph.text)
            self.assertTrue(any(str(run.font.color.rgb) == "FF0000" for run in paragraph.runs))


if __name__ == "__main__":
    unittest.main()
