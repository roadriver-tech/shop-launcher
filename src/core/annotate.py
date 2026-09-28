"""标注层：判例复核的领域规则与写盘（人机对齐的可执行部分）。

    决策判例 data/决策判例.csv —— AI 的实质决策；标 维持 / 改判（新内容+理由）
    准则候选 data/准则候选.csv —— 决策暴露的隐含准则；标 采纳 / 否决（+理由）
        采纳即渲染 docs/决策准则.md（成文法·业务）

政策（唯一定义处）
    改判是终审：写盘前全量校验（含两表互链），不通过拒绝写盘；
    `--seed` 重放不覆盖复核为 维持/改判 的行（schema.REPLAY_KEEP）；
    改判/采纳/否决的理由自动追加 data/纠偏记录.md。

GUI（gui.py）与 CLI（cli.py）都只调用本模块，不复制规则。
"""
from __future__ import annotations

import csv
import sys
from datetime import date
from pathlib import Path

from . import schema, tables

ROOT = Path(__file__).resolve().parent.parent.parent
DECISIONS = ROOT / "data" / "决策判例.csv"
CANON_CAND = ROOT / "data" / "准则候选.csv"
CANON = ROOT / "docs" / "决策准则.md"
LOG = ROOT / "data" / "纠偏记录.md"

DHEADER = schema.DECISION_HEADER
GHEADER = schema.CANON_HEADER
VERDICTS = schema.VERDICTS
DISPOSITIONS = schema.DISPOSITIONS
LEVELS = schema.LEVELS
REVIEW_STATES = schema.REVIEW_STATES
REPLAY_KEEP = schema.REPLAY_KEEP


# ── 表读写 ──────────────────────────────────────────────

def load_table(path: Path, header: list[str]) -> list[list[str]]:
    return tables.read_rows(path, header, source=str(path))


def save_table(path: Path, header: list[str], rows: list[list[str]]) -> None:
    tables.write_rows(path, header, rows)


def write_text(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def _refs(text: str, prefix: str) -> set[str]:
    return {t.strip() for t in text.replace("；", ";").split(";") if t.strip().startswith(prefix)}


def validate_all(d_rows: list[list[str]], g_rows: list[list[str]]) -> list[str]:
    """两表全量校验：结构、枚举、必填、互链。返回违规清单（空=通过）。"""
    bad: list[str] = []
    d_ids, g_ids = set(), set()

    for i, r in enumerate(d_rows, start=2):
        if len(r) != len(DHEADER):
            bad.append(f"决策判例.csv:{i} 字段数错误：{r}")
            continue
        did, _name, content, _src, exposed, level, review, reason = r
        if not did or not content.strip():
            bad.append(f"决策判例.csv:{i} ID/内容不得为空")
            continue
        if did in d_ids:
            bad.append(f"决策判例.csv:{i} ID 重复：{did}")
        d_ids.add(did)
        if level not in LEVELS:
            bad.append(f"决策判例.csv:{i} [{did}] 证据等级非法：{level}")
        if review not in REVIEW_STATES:
            bad.append(f"决策判例.csv:{i} [{did}] 复核非法：{review}")
        if review == "改判" and not reason.strip():
            bad.append(f"决策判例.csv:{i} [{did}] 改判必须填理由")

    for i, r in enumerate(g_rows, start=2):
        if len(r) != len(GHEADER):
            bad.append(f"准则候选.csv:{i} 字段数错误：{r}")
            continue
        gid, _rule, _note, src, disp, reason = r
        if not gid or not _rule.strip():
            bad.append(f"准则候选.csv:{i} ID/准则不得为空")
            continue
        if gid in g_ids:
            bad.append(f"准则候选.csv:{i} ID 重复：{gid}")
        g_ids.add(gid)
        if disp not in DISPOSITIONS:
            bad.append(f"准则候选.csv:{i} [{gid}] 处置非法：{disp}")
        if disp == "采纳" and not reason.strip():
            bad.append(f"准则候选.csv:{i} [{gid}] 采纳必须填理由")

    # 互链：决策暴露的准则、准则的来源决策都必须存在
    for i, r in enumerate(d_rows, start=2):
        if len(r) == len(DHEADER):
            missing = _refs(r[4], "G") - g_ids
            if missing:
                bad.append(f"决策判例.csv:{i} [{r[0]}] 暴露准则悬空：{sorted(missing)}")
    for i, r in enumerate(g_rows, start=2):
        if len(r) == len(GHEADER):
            missing = _refs(r[3], "D") - d_ids
            if missing:
                bad.append(f"准则候选.csv:{i} [{r[0]}] 来源决策悬空：{sorted(missing)}")
    return bad


# ── 标注 ────────────────────────────────────────────────

def find(rows: list[list[str]], key: str) -> list[str] | None:
    return next((r for r in rows if r[0] == key), None)


def apply_decision(rows: list[list[str]], did: str, verdict: str,
                   content: str = "", reason: str = "") -> tuple[list, str]:
    """决策复核：维持（值不变）/ 改判（必填新内容与理由）。"""
    if verdict not in VERDICTS:
        raise ValueError(f"复核取值只能是 {'/'.join(VERDICTS)}：{verdict}")
    row = find(rows, did)
    if row is None:
        raise ValueError(f"决策不存在：{did}")
    if verdict == "维持":
        row[6] = "维持"
        return rows, f"{did}：维持（决策内容不变）"
    if not content.strip():
        raise ValueError("改判必须给新内容")
    if not reason.strip():
        raise ValueError("改判必须给理由（记入纠偏记录）")
    row[2] = content.strip()
    row[6] = "改判"
    row[7] = reason.strip()
    return rows, f"{did}：改判"


def apply_canon(rows: list[list[str]], gid: str, disposition: str,
                reason: str = "") -> tuple[list, str]:
    """准则处置：候选（未标）/ 采纳（升格成文法，必填理由）/ 否决（必填理由）。"""
    if disposition not in DISPOSITIONS:
        raise ValueError(f"处置取值只能是 {'/'.join(DISPOSITIONS)}：{disposition}")
    row = find(rows, gid)
    if row is None:
        raise ValueError(f"准则不存在：{gid}")
    if disposition in ("采纳", "否决") and not reason.strip():
        raise ValueError(f"{disposition}必须给理由")
    row[4] = disposition
    row[5] = reason.strip()
    return rows, f"{gid}：{disposition}"


# ── 成文法渲染与写盘 ─────────────────────────────────────

def render_canon(g_rows: list[list[str]]) -> str:
    lines = [
        "# 开店决策准则（成文法·业务）", "",
        "> 由 `data/准则候选.csv` 中处置=采纳的条目自动渲染（`python3 src/gui.py sync`），"
        "幂等重写，勿手改；改准则回准则候选表。", "",
    ]
    adopted = [r for r in g_rows if r[4] == "采纳"]
    if not adopted:
        lines += ["_尚无采纳条目——在 GUI 或 CSV 中把候选标为「采纳」后运行 sync。_", ""]
    else:
        lines += [f"共 {len(adopted)} 条。", ""]
        for r in adopted:
            gid, rule, note, src, _disp, reason = r
            lines += [f"## {gid} {rule}", "", note, "",
                      f"- 来源决策：{src.replace(';', '、')}",
                      f"- 采纳理由：{reason}", ""]
    return "\n".join(lines)


def sync_canon(g_rows: list[list[str]], canon: Path = CANON) -> str:
    """渲染采纳准则到成文法文档（幂等），返回条数说明。"""
    write_text(canon, render_canon(g_rows))
    return f"docs/决策准则.md 已同步（采纳 {sum(1 for r in g_rows if r[4] == '采纳')} 条）"


def append_log(layer: str, obj: str, change: str, reason: str,
               path: Path = LOG) -> None:
    line = f"| {date.today().isoformat()} | {layer} | {obj} | {change} | 个例 | 1 | {reason} |\n"
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    start = next((i for i, ln in enumerate(lines) if ln.startswith("|------")), None)
    if start is None:
        raise ValueError(f"纠偏记录表格结构不符：{path}")
    i = start + 1
    while i < len(lines) and lines[i].startswith("|"):
        i += 1
    lines.insert(i, line)
    write_text(path, "".join(lines))


def commit(kind: str, key: str, value: str, extra: str = "", reason: str = "",
           log: Path | None = None, decisions: Path = DECISIONS,
           canon_cand: Path = CANON_CAND, canon: Path = CANON) -> str:
    """kind='decision' | 'canon'。标注 → 全量校验 → 写盘 → 记纠偏 → 准则变动同步渲染。

    校验不过就不写盘，也不记纠偏。路径都作参数（缺省取本模块），
    GUI 与测试可指向自己的副本；log 运行时解析，保证测试可替换路径。"""
    log = log or LOG
    d_rows, g_rows = load_table(decisions, DHEADER), load_table(canon_cand, GHEADER)

    if kind == "decision":
        d_rows, msg = apply_decision(d_rows, key, value, extra, reason)
        target, header, rows_ = decisions, DHEADER, d_rows
    elif kind == "canon":
        g_rows, msg = apply_canon(g_rows, key, value, reason)
        target, header, rows_ = canon_cand, GHEADER, g_rows
    else:
        raise ValueError(f"kind 只能是 decision|canon：{kind}")

    bad = validate_all(d_rows, g_rows)
    if bad:
        raise ValueError("校验未过，拒绝写盘：\n" + "\n".join(bad))
    save_table(target, header, rows_)

    if kind == "decision":
        if value == "改判":
            append_log("判例", key, "改判决策", reason, log)
        return msg
    if value in ("采纳", "否决"):
        append_log("成文法", key, value, reason, log)
    return msg + "；" + sync_canon(g_rows, canon)


def preserve_reviewed(rows: list[list[str]], table: Path,
                      header: list[str] | None = None) -> list[list[str]]:
    """判例优先：重放保留复核为 维持/改判 的行（schema.REPLAY_KEEP），未复核行重算。"""
    header = header or schema.ASSESS_HEADER
    if not table.exists():
        return rows
    with open(table, encoding="utf-8", newline="") as f:
        existing = [r for r in csv.reader(f) if r]
    if not existing or existing[0] != header or any(len(r) != len(header) for r in existing[1:]):
        return rows  # 旧表头或不完整，无可保留判例
    reviewed = {r[0]: r for r in existing if r[7] in REPLAY_KEEP}
    out, kept = [], set()
    for r in rows:
        if r[0] in reviewed:
            out.append(reviewed[r[0]])
            kept.add(r[0])
        else:
            out.append(r)
    extra = [r for n, r in reviewed.items() if n not in kept]
    if extra:
        print(f"判例保留：{[r[0] for r in extra]} 不在种子源中，不删除", file=sys.stderr)
    return out + extra
