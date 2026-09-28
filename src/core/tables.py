"""表读写：表头校验 + 原子写。四张 CSV 各有一份读写，不再各写各的。"""
from __future__ import annotations

import csv
import io
import sys
from pathlib import Path


def read_rows(path: Path, header: list[str], *, empty_ok: bool = False,
              source: str | None = None) -> list[list[str]]:
    """读 CSV 并校验表头，返回数据行。表头不符即退出——不是这份 schema 就不入库。"""
    if not path.exists():
        sys.exit(f"表不存在：{path}")
    with open(path, encoding="utf-8", newline="") as f:
        rows = [r for r in csv.reader(f) if r]
    if not rows:
        if empty_ok:
            return []
        header_ok = False
    else:
        header_ok = rows[0] == header
    if not header_ok:
        where = f"（{source}）" if source else ""
        sys.exit(f"表头不符{where}，应为：{','.join(header)}")
    return rows[1:]


def write_rows(path: Path, header: list[str], rows: list[list[str]]) -> None:
    """先写临时文件再替换，避免中途失败留下半张表。"""
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(header)
        w.writerows(rows)
    tmp.replace(path)


def to_csv(header: list[str], rows: list[list[str]]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(header)
    w.writerows(rows)
    return buf.getvalue()
