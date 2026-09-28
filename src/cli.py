#!/usr/bin/env python3
"""统一命令行入口：一个 CLI，覆盖四个模块 + 全量门禁。

    python3 src/cli.py assess --seed "docs/AI 辅助开店.md" --out data/能力对照表.csv
    python3 src/cli.py ledger report --mode shop --ticket 32:45 --traffic 15:20 \\
                                         --staff 1200 --utility 800 --food-rate 0.35
    python3 src/cli.py deviation --check
    python3 src/cli.py check               # 三张表全量门禁，任一违规退出码 1
    python3 src/cli.py sync                # 采纳准则 → docs/决策准则.md

领域逻辑在 `src/core/`（assess / deviation / ledger / annotate / rules），本文件只解析
参数与打印结果；GUI 是另一个入口 `src/gui.py`。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import gui
from core import assess, deviation, ledger, tables

USAGE = """用法：python3 src/cli.py <命令> [参数...]

  assess    能力对照表：--seed / --out / eval / check
  ledger    算账：all / per-head / pot / stall / shop / report / gaps / selftest
  deviation 偏差地图：--check
  check     全部门禁：能力对照表 + 偏差地图 + 判例/准则两表
  sync      采纳准则渲染进 docs/决策准则.md

GUI 不经本门面：python3 src/gui.py [check|sync]
"""


# ── 参数解析（领域函数只收值，不认 argparse）────────────

def parse_mix(text: str) -> tuple[float, float, float]:
    """解析 `素:荤:招牌` 比例。"""
    parts = text.split(":")
    if len(parts) != 3:
        raise argparse.ArgumentTypeError("mix 须为 素:荤:招牌 三段，如 60:30:10")
    try:
        vals = tuple(float(p) for p in parts)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"mix 含非数字：{text}") from exc
    if any(v < 0 for v in vals) or sum(vals) <= 0:
        raise argparse.ArgumentTypeError("mix 须为非负且总和 > 0")
    return vals  # type: ignore[return-value]


def parse_range(text: str | None) -> tuple[float, float] | None:
    """解析 `32:45` 区间。"""
    if not text:
        return None
    parts = text.split(":")
    if len(parts) != 2:
        raise SystemExit(f"区间须为 低:高 两段：{text}")
    lo, hi = float(parts[0]), float(parts[1])
    if lo > hi:
        raise SystemExit(f"区间下界大于上界：{text}")
    return lo, hi


def assess_cmd(argv: list[str]) -> int:
    """能力对照表：--seed 重放 / eval 单行 / check 一致性检查。"""
    if argv and argv[0] == "check":
        p = argparse.ArgumentParser(prog="cli assess check")
        p.add_argument("csv", type=Path, help="要检查的对照表 CSV")
        a = p.parse_args(argv[1:])
        return assess.check(a.csv)

    if argv and argv[0] == "eval":
        p = argparse.ArgumentParser(prog="cli assess eval")
        p.add_argument("name", help="决策环节，如 证照合规")
        p.add_argument("--material", required=True, help="材料/局限描述")
        p.add_argument("--score", type=int, help="能力分，缺省按依赖带推导")
        p.add_argument("--dep", help="输入依赖，显式给出时必须配 --score")
        a = p.parse_args(argv[1:])
        print(assess.to_csv([assess.derive(a.name, a.material, a.score, a.dep)]), end="")
        return 0

    p = argparse.ArgumentParser(prog="cli assess")
    p.add_argument("--seed", type=Path, help="从对照表原文推导")
    p.add_argument("--out", type=Path, help="写出 CSV，缺省打印到 stdout")
    a = p.parse_args(argv)
    if not a.seed:
        p.error("需要 --seed、eval 或 check")
    merged = assess.preserve_reviewed(assess.parse_seed(a.seed), assess.TABLE)
    preserved = [r for r in merged if r[7] in assess.REPLAY_KEEP]
    if a.out:
        tables.write_rows(a.out, assess.HEADER, merged)
        note = f"，保留已复核判例 {len(preserved)} 行" if preserved else ""
        print(f"{a.out}：{len(merged)} 行{note}")
    else:
        print(assess.to_csv(merged), end="")
    return 0


def deviation_cmd(argv: list[str]) -> int:
    """偏差地图：汇总可信度；--check 只校验 schema 与偏差率算术。"""
    p = argparse.ArgumentParser(prog="cli deviation")
    p.add_argument("--check", action="store_true", help="只校验 schema")
    a = p.parse_args(argv)

    rows = deviation.load(deviation.MAP)
    bad = deviation.validate(rows)
    if bad:
        print("\n".join(bad), file=sys.stderr)
        return 1
    if a.check:
        print(f"schema 校验通过：{len(rows)} 行")
        return 0

    if not rows:
        print("缺数据：data/偏差地图.csv 尚无实测行。")
        print("等探店 4 数据与丰全巷摆摊记录回填（TODO.md 3.3）后再汇总。")
        return 2

    print(f"── 偏差地图 {len(rows)} 行（证据等级 L2）──")
    for r in rows:
        print(f"  [{r['环节']}] {r['品类']}/{r['城市']}  "
              f"预测 {r['预测值']} → 实测 {r['实测值']}  偏差 {r['偏差率'] or '—'}")
    print("\n── 品类/城市可信度（平均 |偏差|，越低越可信）──")
    for cat, city, n, avg in deviation.credibility(rows):
        print(f"  {cat}/{city}  {n} 个环节  平均偏差 {avg:.1f}%")
    return 0


def ledger_cmd(argv: list[str]) -> int:
    """算账：人均 / 底料 / 三阶段达标线 / 盈亏平衡 / 三层报表。缺 L1 退出码 2。"""
    p = argparse.ArgumentParser(prog="cli ledger", description="串串店算账工具")
    sub = p.add_subparsers(dest="cmd")

    def add_mix(sp):
        sp.add_argument("--mix", type=parse_mix, default=ledger.DEFAULT_MIX,
                        metavar="素:荤:招牌", help="签型比例 [L0]，默认 60:30:10")

    def add_shop_args(sp):
        sp.add_argument("--rev", type=float, default=ledger.LOCK["rev_floor"],
                        help="月营业额 [锁]，默认达标线")
        sp.add_argument("--rent", type=float, default=ledger.LOCK["rent_cap"],
                        help="月租 [锁]，默认上限")
        sp.add_argument("--staff", type=float, default=None, help="人工月成本 [L1]")
        sp.add_argument("--utility", type=float, default=None, help="水电杂费月成本 [L1]")
        sp.add_argument("--other-fixed", type=float, default=None, help="其他固定成本 [L1]")
        sp.add_argument("--food-rate", type=float, default=None,
                        help="食材成本率 [L1]，占营业额")

    sp_all = sub.add_parser("all", help="全部测算")
    add_mix(sp_all)
    add_shop_args(sp_all)
    add_mix(sub.add_parser("per-head", help="人均拆解"))
    sub.add_parser("pot", help="底料摊薄")
    sp = sub.add_parser("stall", help="摆摊阶段")
    add_mix(sp)
    sp.add_argument("--daily", type=int, default=None, help="实测日均签数 [L1]")

    sp = sub.add_parser("shop", help="档口店阶段")
    add_mix(sp)
    add_shop_args(sp)

    sub.add_parser("gaps", help="列出待回填项")
    sub.add_parser("selftest", help="自检")
    sp = sub.add_parser("report", help="三层报表（结论→账目→细算）")
    sp.add_argument("--mode", choices=["stall", "shop"], default="shop")
    add_mix(sp)
    sp.add_argument("--daily", type=int, default=None, help="摆摊实测日均签数 [L1]")
    sp.add_argument("--ticket", help="客单价区间，如 32:45 [L1]")
    sp.add_argument("--traffic", help="日客流区间，如 15:20 [L1]")
    add_shop_args(sp)

    args = p.parse_args(argv)
    cmd = args.cmd or "all"
    mix = getattr(args, "mix", ledger.DEFAULT_MIX)

    if cmd == "selftest":
        return ledger.selftest()

    missing: list[str] = []
    if cmd in ("all", "per-head"):
        ledger.print_head(mix)
    if cmd == "pot" or cmd == "all":
        ledger.print_pot()
    if cmd in ("all", "stall"):
        ledger.print_stall(mix, getattr(args, "daily", None))
    if cmd in ("all", "shop"):
        missing = ledger.print_shop(
            mix,
            getattr(args, "rev", ledger.LOCK["rev_floor"]),
            getattr(args, "rent", ledger.LOCK["rent_cap"]),
            getattr(args, "staff", None),
            getattr(args, "utility", None),
            getattr(args, "other_fixed", None),
            getattr(args, "food_rate", None),
        )
    if cmd == "gaps" or cmd == "all":
        ledger.print_gaps(mix)

    if cmd == "report":
        params = {
            "mix": mix,
            "daily": getattr(args, "daily", None),
            "ticket": parse_range(getattr(args, "ticket", None)),
            "traffic": parse_range(getattr(args, "traffic", None)),
            "rent": getattr(args, "rent", None),
            "staff": getattr(args, "staff", None),
            "utility_other": getattr(args, "utility", None),
            "other_fixed": getattr(args, "other_fixed", None),
            "food_rate": getattr(args, "food_rate", None),
        }
        return ledger.print_report(args.mode, params)

    return 2 if missing else 0


COMMANDS = {
    "assess": assess_cmd,
    "ledger": ledger_cmd,
    "deviation": deviation_cmd,
}


def full_check() -> int:
    """三张表逐个过门禁：任一违规或校验中途退出，都算门禁未过（退出码 1）。"""
    results = []
    for name, fn in (("能力对照表", lambda: assess.check(assess.TABLE)),
                     ("偏差地图", lambda: deviation_cmd(["--check"])),
                     ("判例/准则两表", lambda: gui.main(["check"]))):
        try:
            results.append((name, fn()))
        except SystemExit as exc:  # 表不存在、表头不符等中途退出
            print(f"{name}：{exc.code}", file=sys.stderr)
            results.append((name, 1))
    bad = [name for name, code in results if code]
    if bad:
        print(f"门禁未过：{'、'.join(bad)}", file=sys.stderr)
        return 1
    print("全量门禁通过：能力对照表 / 偏差地图 / 判例准则两表")
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        print(USAGE, end="")
        return 2
    cmd, rest = argv[0], argv[1:]
    if cmd == "check":
        return full_check()
    if cmd == "sync":
        return gui.main(["sync"])
    run = COMMANDS.get(cmd)
    if run is None:
        print(f"未知命令：{cmd}\n\n{USAGE}", end="", file=sys.stderr)
        return 2
    return run(rest)


if __name__ == "__main__":
    sys.exit(main())
