"""能力对照表领域：决策环节 + 材料 → 一行八字段判例，入库前一致性检查。

用法不在这里，在唯一 CLI（`src/cli.py assess`）：
    python3 src/cli.py assess --seed "docs/AI 辅助开店.md" [--out data/能力对照表.csv]
    python3 src/cli.py assess eval 证照合规 --material "常见证照清单能列全，本地执法口径未核实"
    python3 src/cli.py assess check data/能力对照表.csv

推导规则（AGENTS.md 评分标尺的可执行化，词表与分数带本体在 `rules.py`）
    输入依赖：局限文本命中 C 词表（现场、感官…）记 C，命中 B 词表（本地、锚定…）记 B；
              能力分 ≥ 60 视作 AI 可交付的 A 类，低于此只由缺失的输入决定分数；
              两类都没命中 → A（纯抽象推理）。
    分数带（eval 未显式给 --score 时）：纯 A 70 / 含 C 60 / 含 C+B 55 / 纯 B 45。
    证据等级默认 L0、验证状态默认待验证 —— 机器推导一律是待验证假设，不是结论。

与 AGENTS.md 的关系（判例与成文法，见其「人机对齐」节）：
    规则只此一份，在 `src/core/rules.py`——词表、分数带、检查§1–4 都在那里，
    违规消息带条文编号，`tests/test_charter_binding.py` 断言条文与章程同号同阈值。
    改章程条文 → 改 rules.py → 重放，测试不红才算同步完。
    输出是判例：`依据法条` 列引用条文（依A·标尺·检查§2），`复核` 列留给人的标注。
    重放（--seed）不覆盖复核为 维持/改判 的行——改判是终审（`annotate.py`）。
    L1/L2 只由数据到达推进，与人的表态脱钩，不在此臆造。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from . import annotate, rules, schema, tables

ROOT = Path(__file__).resolve().parent.parent.parent
TABLE = ROOT / "data" / "能力对照表.csv"

HEADER = schema.ASSESS_HEADER
LEVELS = schema.LEVELS
STATUSES = schema.STATUSES
REVIEW_STATES = schema.REVIEW_STATES
REPLAY_KEEP = schema.REPLAY_KEEP
C_WORDS = rules.C_WORDS
B_WORDS = rules.B_WORDS
HUMAN = rules.HUMAN
CONTRAST = rules.CONTRAST

basis_of = rules.basis_of
preserve_reviewed = annotate.preserve_reviewed


def derive(name: str, text: str, score: int | None = None, dep: str | None = None) -> list[str]:
    """材料文本 → 一行八字段。分数与依赖可显式给出，缺省按规则推导。"""
    if dep is None:
        deps = []
        if any(w in text for w in C_WORDS):
            deps.append("C")
        if any(w in text for w in B_WORDS):
            deps.append("B")
        if score is None:
            score = rules.default_score(deps)
        # 分数达到可交付线才算 AI 的 A 类能力（与检查§1 的 60 同源）
        if score >= rules.MIN_PURE_A:
            deps.insert(0, "A")
        if not deps:
            deps = ["A"]
        deps.sort(key="ABC".index)
        dep = " + ".join(deps)
    elif score is None:
        raise SystemExit("显式 --dep 时必须同时给 --score（机器不猜分数）")

    if not CONTRAST.search(text):
        text = f"{text}；仅通用知识，未喂本地数据"
    deps = {d.strip() for d in dep.split("+")}
    return [name, str(score), text, dep, "L0", "待验证", basis_of(deps), "未复核"]


def parse_seed(path: Path) -> list[list[str]]:
    """解析对照表原文（制表符分隔：环节 / 星级分 / 局限）。"""
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if "\t★" not in line:
            continue
        name, rating, text = line.split("\t", 2)
        m = re.search(r"(\d+)\s*分", rating)
        if not m:
            continue
        rows.append(derive(name.strip(), text.strip(), score=int(m.group(1))))
    if not rows:
        sys.exit(f"种子表未解析到任何行：{path}")
    return rows


def to_csv(rows: list[list[str]]) -> str:
    return tables.to_csv(HEADER, rows)


def read_csv(path: Path) -> list[list[str]]:
    return tables.read_rows(path, HEADER)


def validate_rows(rows: list[list[str]], label: str = "") -> list[str]:
    """对内存中的行跑一致性检查（规则在 `rules.py`），此处只加行号定位。"""
    bad: list[str] = []
    for i, row in enumerate(rows, start=2):
        where = f"{label}:{i}" if label else f"行 {i}"
        bad += [f"{where} {msg}" for msg in rules.check_row(row)]
    return bad


def check(path: Path) -> int:
    """AGENTS.md 一致性检查：入库前必过，违规退出码 1。"""
    rows = read_csv(path)
    bad = validate_rows(rows, str(path))
    if bad:
        print("\n".join(bad), file=sys.stderr)
        print(f"{len(bad)} 处违规 / {len(rows)} 行", file=sys.stderr)
        return 1
    print(f"一致性检查通过：{len(rows)} 行")
    return 0
