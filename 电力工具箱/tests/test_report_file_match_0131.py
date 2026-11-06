from __future__ import annotations

import os
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from toolbox import file_rules
from toolbox.runtime import load_module


class MorningFileMatchTests(unittest.TestCase):
    def test_both_tk_entrypoints_match_the_whole_date(self):
        root = Path(__file__).resolve().parents[2]
        standalone = load_module(
            "morning_gui_date_0131",
            root / "每日生产经营情况汇报自动生成工具/scripts/report_gui.py",
        )
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            downloads = home / "Downloads"
            downloads.mkdir()
            selected = downloads / "出清情况（分公司2026.11.01）.xlsx"
            selected.touch()
            later = downloads / "出清情况（分公司2026.11.10）.xlsx"
            later.touch()
            os.utime(selected, (1000, 1000))
            os.utime(later, (2000, 2000))
            with patch.object(file_rules.Path, "home", return_value=home), patch.object(
                standalone, "DOWNLOADS_DIR", downloads
            ):
                for finder in (file_rules.find_workbook_for_day, standalone.ReportTool.find_workbook_for_day):
                    self.assertEqual(finder(date(2026, 11, 1)), selected)
                    selected.unlink(missing_ok=True)
                    self.assertIsNone(finder(date(2026, 11, 1)))
                    selected.touch()
                    os.utime(selected, (1000, 1000))


if __name__ == "__main__":
    unittest.main()
