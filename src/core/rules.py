"""成文法条文的可执行投影（AGENTS.md「评分标尺」「一致性检查」）。

规则只此一份：assess 的入库检查、判例的 `依据法条` 列、章程绑定测试都读这里。
违规消息以 [条文编号] 开头，编号即 AGENTS.md 中的条文，改条文 → 改这里 →
tests/test_charter_binding.py 断言两边同号同阈值。
"""
from __future__ import annotations

import re

from . import schema

# ── 阈值（AGENTS.md 检查§1–4）───────────────────────────
MIN_PURE_A = 60     # 检查§1：纯 A 环节应 ≥ 60
MAX_WITH_C = 80     # 检查§2：含 C 的环节应 ≤ 80
MAX_PURE_C = 30     # 检查§3：纯 C 环节应 ≤ 30

# ── 推导词表（材料文本 → 输入依赖）──────────────────────
C_WORDS = ["现场", "蹲点", "试吃", "闻", "尝", "口味", "感官", "身体",
           "突发", "情绪", "随机", "在场", "碰不到"]
B_WORDS = ["本地", "滁州", "锚定", "人流", "当地", "实地", "街区", "商圈", "微观"]
# 含 C 的行，局限必须点名需人工的部分（检查§2 后半句）
HUMAN = re.compile(r"人工|兜底|验证|闻|尝|口味|现场|蹲点|试吃|身体|突发|情绪|碰不到|你")
# 能力描述里没有让步词的，视为只有能力没写局限
CONTRAST = re.compile(r"但|缺|不|无法|碰不到|判断不了|未核实|未验证|验证")

# ── 分数带（eval 未显式给 --score 时的缺省分，见 docs/assess.md）──
# 命中 C → 60（≥60 记作 A 类可交付）；同时命中 B 降 55；只命中 B → 45；都没命中 → 70。
SCORE_PURE_A = 70
SCORE_WITH_C = 60
SCORE_B_AND_C = 55
SCORE_PURE_B = 45


def default_score(deps: list[str]) -> int:
    """按命中的依赖给缺省能力分（机器推导，一律 L0 / 待验证）。"""
    if not deps:
        return SCORE_PURE_A
    if "C" in deps:
        return SCORE_WITH_C if "B" not in deps else SCORE_B_AND_C
    return SCORE_PURE_B


def basis_of(deps: set[str]) -> str:
    """判例的法条引用：命中的依X + 标尺 + 适用的检查条文。"""
    parts = [f"依{d}" for d in sorted(deps, key="ABC".index)] or ["依A"]
    parts.append("标尺")
    if deps == {"A"}:
        parts.append("检查§1")
    elif deps == {"C"}:
        parts.append("检查§3")
    elif "C" in deps:
        parts.append("检查§2")
    if "B" in deps:
        parts.append("检查§4")
    return "·".join(parts)


def check_row(row: list[str]) -> list[str]:
    """能力对照表一行八字段 → 违规清单，每条以 [条文编号] 开头；空 = 通过。

    结构不合法时立即返回（后续规则依赖字段位置），与逐条检查互不交叉。
    """
    if len(row) != len(schema.ASSESS_HEADER) or any(not c.strip() for c in row):
        return [f"[字段] 八字段必须齐全非空：{row}"]

    name, score_s, limit, dep_s, level, status = row[:6]
    review = row[7]
    try:
        score = int(score_s)
    except ValueError:
        return [f"[标尺] [{name}] 能力分非整数：{score_s}"]

    deps = {d.strip() for d in dep_s.split("+")}
    if not deps <= set(schema.DEPS):
        return [f"[字段] [{name}] 输入依赖取值非法：{dep_s}"]

    bad: list[str] = []
    if level not in schema.LEVELS:
        bad.append(f"[检查§4] [{name}] 证据等级非法：{level}（B 类必须标出 L0/L1/L2）")
    if status not in schema.STATUSES:
        bad.append(f"[标尺] [{name}] 验证状态非法：{status}")
    if review not in schema.REVIEW_STATES:
        bad.append(f"[复核] [{name}] 复核标注非法：{review}"
                   f"（{'/'.join(schema.REVIEW_STATES)}）")
    if deps == {"A"} and score < MIN_PURE_A:
        bad.append(f"[检查§1] [{name}] 纯 A 应 ≥ {MIN_PURE_A}，实为 {score}")
    if "C" in deps and score > MAX_WITH_C:
        bad.append(f"[检查§2] [{name}] 含 C 应 ≤ {MAX_WITH_C}，实为 {score}")
    if "C" in deps and not HUMAN.search(limit):
        bad.append(f"[检查§2] [{name}] 含 C 的局限须点名人工兜底部分：{limit}")
    if deps == {"C"} and score > MAX_PURE_C:
        bad.append(f"[检查§3] [{name}] 纯 C 应 ≤ {MAX_PURE_C}，实为 {score}")
    return bad


# 本模块用到的条文编号（章程绑定测试逐个反查 AGENTS.md）
CHECK_IDS = ("字段", "标尺", "复核", "检查§1", "检查§2", "检查§3", "检查§4")
