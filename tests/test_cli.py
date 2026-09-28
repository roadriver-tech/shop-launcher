"""cli.py 门面的回归：子命令转发、全量门禁、未知命令退出码。无图形环境可跑。"""
from __future__ import annotations

import contextlib
import io
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import cli  # noqa: E402
from core import assess  # noqa: E402


def run(*argv: str) -> tuple[int, str]:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        code = cli.main(list(argv))
    return code, buf.getvalue()


class TestDispatch(unittest.TestCase):
    def test_usage_without_args(self):
        code, out = run()
        self.assertEqual(code, 2)
        self.assertIn("check", out)

    def test_unknown_command_exits_2(self):
        code, out = run("nope")
        self.assertEqual(code, 2)
        self.assertIn("未知命令", out)

    def test_subcommand_is_forwarded(self):
        code, out = run("assess", "check", str(assess.TABLE))
        self.assertEqual(code, 0)
        self.assertIn("一致性检查通过", out)

    def test_deviation_check_forwarded(self):
        code, _ = run("deviation", "--check")
        self.assertEqual(code, 0)

    def test_sync_forwarded(self):
        """sync 转给 GUI 模块，渲染目标可替换（不碰仓库里的成文法）。"""
        import tempfile

        import gui

        saved = gui.CANON
        gui.CANON = Path(tempfile.mkdtemp()) / "决策准则.md"
        try:
            code, out = run("sync")
        finally:
            gui.CANON = saved
        self.assertEqual(code, 0)
        self.assertIn("已同步", out)


class TestFullGate(unittest.TestCase):
    """check：三张表任一违规即退出码 1，全过才 0。"""

    def test_all_tables_pass(self):
        code, out = run("check")
        self.assertEqual(code, 0)
        self.assertIn("全量门禁通过", out)

    def test_missing_gate_reported(self):
        import gui
        from core import deviation

        saved = (deviation.MAP, gui.DECISIONS)
        try:
            deviation.MAP = Path("/tmp/不存在的偏差地图.csv")
            gui.DECISIONS = Path("/tmp/不存在的决策判例.csv")
            code, out = run("check")
        finally:
            deviation.MAP, gui.DECISIONS = saved
        self.assertEqual(code, 1)
        self.assertIn("门禁未过", out)


if __name__ == "__main__":
    unittest.main()
