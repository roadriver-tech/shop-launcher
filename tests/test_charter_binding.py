"""章程绑定：代码里的条文编号、阈值、字段、枚举必须与 AGENTS.md 一致。

散文与代码漂移的机器门禁——改章程条文而不同步 `core/rules.py`（或反之）测试即红。
无图形环境可跑：python3 -m unittest discover -s tests
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from core import assess, rules, schema  # noqa: E402

CHARTER = (ROOT / "AGENTS.md").read_text(encoding="utf-8")


def clause(rid: str) -> str:
    for line in CHARTER.splitlines():
        if f"**{rid}**" in line:
            return line
    raise AssertionError(f"AGENTS.md 里没有条文 {rid}")


class TestRuleIdsInCharter(unittest.TestCase):
    def test_every_check_id_is_findable_in_charter(self):
        """条文编号要么是章程里的成文条（检查§n），要么是章节/术语名。"""
        for rid in rules.CHECK_IDS:
            with self.subTest(rid=rid):
                if rid.startswith("检查§"):
                    self.assertIn(f"**{rid}**", CHARTER)
                else:
                    self.assertIn(rid, CHARTER)

    def test_violation_messages_carry_known_ids(self):
        """实际打出的每条违规都带 CHECK_IDS 里的编号，否则人反查不到条文。"""
        probes = [
            ["市场调研", "50", "仅通用知识", "A", "L0", "待验证", "依A·标尺·检查§1", "未复核"],
            ["底料", "90", "落地有点难", "A + C", "L0", "待验证", "依A·依C·标尺·检查§2", "未复核"],
            ["现场运营", "40", "现场盯摊由人工负责", "C", "L0", "待验证", "依C·标尺·检查§3", "未复核"],
            ["定价", "40", "本地锚点未核", "B", "L3", "未知", "依B·标尺·检查§4", "同意"],
            ["定价", "", "", "D", "L0", "待验证", "依B", "未复核"],
            ["定价", "abc", "本地锚点未核", "B", "L0", "待验证", "依B·标尺·检查§4", "未复核"],
        ]
        seen = set()
        for row in probes:
            for msg in rules.check_row(row):
                m = re.match(r"\[([^\]]+)\]", msg)
                self.assertIsNotNone(m, f"违规消息缺条文编号：{msg}")
                seen.add(m.group(1))
        self.assertLessEqual(seen, set(rules.CHECK_IDS))
        self.assertEqual(seen, set(rules.CHECK_IDS))  # 六组探针覆盖全部条文


class TestThresholdsMatchClauses(unittest.TestCase):
    def test_check_thresholds(self):
        for rid, threshold in (("检查§1", f"≥ {rules.MIN_PURE_A}"),
                               ("检查§2", f"≤ {rules.MAX_WITH_C}"),
                               ("检查§3", f"≤ {rules.MAX_PURE_C}")):
            with self.subTest(rid=rid):
                self.assertIn(threshold, clause(rid))

    def test_field_table_matches_header(self):
        for col in schema.ASSESS_HEADER:
            with self.subTest(col=col):
                self.assertIn(f"| {col} |", CHARTER)

    def test_enums_are_charter_values(self):
        for v in schema.REVIEW_STATES + schema.LEVELS + schema.STATUSES:
            with self.subTest(v=v):
                self.assertIn(v, CHARTER)
        for v in ("采纳", "否决"):  # 准则处置的两种终态（候选是缺省态，章程不列）
            with self.subTest(v=v):
                self.assertIn(v, CHARTER)

    def test_annotation_table_columns(self):
        decisions = next(l for l in CHARTER.splitlines() if "（决策/内容" in l)
        for col in schema.DECISION_HEADER[1:]:
            self.assertIn(col, decisions)
        canon = next(l for l in CHARTER.splitlines() if "（准则/说明" in l)
        for col in schema.CANON_HEADER[1:]:
            self.assertIn(col, canon)


class TestPolicyIsExplicit(unittest.TestCase):
    def test_basis_cites_only_known_clauses(self):
        """`依据法条` 列生成的每个编号都必须是已登记的条文。"""
        cases = [{"A"}, {"B"}, {"C"}, {"A", "B"}, {"A", "C"}, {"B", "C"},
                 {"A", "B", "C"}]
        for deps in cases:
            with self.subTest(deps=deps):
                for part in assess.basis_of(deps).split("·"):
                    if part.startswith("依"):
                        continue
                    self.assertIn(part, rules.CHECK_IDS)

    def test_replay_policy_is_charter_terminal_verdict(self):
        """改判终审：重放保留的取值 = 复核取值，且章程写明终审。"""
        self.assertEqual(schema.REPLAY_KEEP, schema.VERDICTS)
        self.assertIn("改判是终审", CHARTER)


if __name__ == "__main__":
    unittest.main()
