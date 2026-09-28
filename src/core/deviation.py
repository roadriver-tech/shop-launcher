"""偏差地图领域：预测值 vs 实测值 → 偏差率与（品类, 城市）可信度。

用法不在这里，在唯一 CLI（`src/cli.py deviation`）：
    python3 src/cli.py deviation            # 汇总 data/偏差地图.csv，按品类/城市标可信度
    python3 src/cli.py deviation --check    # 只校验 schema 与偏差率算术

schema（data/偏差地图.csv，见 AGENTS.md 产出 ②）
    环节, 品类, 城市, 预测值, 实测值, 偏差率, 证据等级, 来源日期
    偏差率 = (实测 − 预测) / 预测；预测值为 0 时留空（不算，不编）。

无实测数据时明确报缺数据，不输出空结论。实测行入库即证据等级 L2。
"""
from __future__ import annotations

from pathlib import Path

from . import schema, tables

ROOT = Path(__file__).resolve().parent.parent.parent
MAP = ROOT / "data" / "偏差地图.csv"
HEADER = schema.DEVIATION_HEADER


def load(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = tables.read_rows(path, HEADER, empty_ok=True)
    return [dict(zip(HEADER, r)) for r in rows]


def dev_pct(pred: str, actual: str) -> str:
    """偏差率，两位小数百分比；预测值无法作分母时留空。"""
    try:
        p, a = float(pred), float(actual)
    except ValueError:
        return ""
    if p == 0:
        return ""
    return f"{(a - p) / p * 100:+.1f}%"


def validate(rows: list[dict]) -> list[str]:
    """违规消息以 [条文编号] 开头，反查 AGENTS.md / docs/deviation.md。"""
    bad = []
    for i, r in enumerate(rows, start=2):
        if any(not r[k].strip() for k in HEADER if k != "偏差率"):
            bad.append(f"行 {i} [字段]：字段缺失 {r}")
            continue
        if r["证据等级"] != "L2":
            bad.append(f"行 {i} [{r['环节']}] [证据等级]：实测行证据等级须为 L2，"
                       f"实为 {r['证据等级']}")
        want = dev_pct(r["预测值"], r["实测值"])
        if r["偏差率"] and want and r["偏差率"] != want:
            bad.append(f"行 {i} [{r['环节']}] [偏差率]：{r['偏差率']} 与算术 {want} 不符")
    return bad


def credibility(rows: list[dict]) -> list[tuple[str, str, int, float]]:
    """按 (品类, 城市) 聚合：行数与平均 |偏差率|，给环节可信度参考。"""
    groups: dict[tuple[str, str], list[float]] = {}
    for r in rows:
        try:
            v = abs(float(r["偏差率"].rstrip("%")))
        except (ValueError, AttributeError):
            continue
        groups.setdefault((r["品类"], r["城市"]), []).append(v)
    out = []
    for (cat, city), vals in sorted(groups.items()):
        out.append((cat, city, len(vals), sum(vals) / len(vals)))
    return out
