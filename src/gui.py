#!/usr/bin/env python3
"""判例复核 GUI：标注 AI 的实质决策与它暴露的隐含准则。

用法
    python3 src/gui.py          # 启动 GUI
    python3 src/gui.py check    # 两表校验（互链、枚举、必填），违规退出码 1
    python3 src/gui.py sync     # 处置=采纳 的准则 → docs/决策准则.md（幂等重写）

要标注的两类信息（AGENTS.md「人机对齐」）
    决策判例 data/决策判例.csv —— AI 按知识库做出的开店决策；标 维持 / 改判（新内容+理由）
    准则候选 data/准则候选.csv —— 决策暴露的隐含准则（成文法候选）；标 采纳 / 否决（+理由）
        采纳即渲染进 docs/决策准则.md（成文法·业务）

规则：保存前全量校验（含两表互链），不通过拒绝写盘；改判理由自动追加
data/纠偏记录.md；改判是终审（元评估表的重放不覆盖已复核判例）。

本文件只有入口与界面——标注规则、写盘、渲染、重放政策全在 `src/core/annotate.py`
与 `src/core/schema.py`，此处不复制一份。数据层与界面分离，无图形环境可跑测试；
无第三方依赖（tkinter 内置）。
"""
from __future__ import annotations

import sys
from pathlib import Path

from core import annotate, schema

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

# 表头与枚举：唯一定义在 core.schema，此处别名供调用方使用
DHEADER = schema.DECISION_HEADER
GHEADER = schema.CANON_HEADER
VERDICTS = schema.VERDICTS
DISPOSITIONS = schema.DISPOSITIONS
LEVELS = schema.LEVELS

# 本入口管辖的四个路径（测试用它替换成临时副本）
DECISIONS = ROOT / "data" / "决策判例.csv"
CANON_CAND = ROOT / "data" / "准则候选.csv"
CANON = ROOT / "docs" / "决策准则.md"
LOG = ROOT / "data" / "纠偏记录.md"

# 数据层：全部委托 core.annotate
load_table = annotate.load_table
save_table = annotate.save_table
validate_all = annotate.validate_all
find = annotate.find
apply_decision = annotate.apply_decision
apply_canon = annotate.apply_canon
render_canon = annotate.render_canon


def sync_canon(g_rows: list[list[str]]) -> str:
    return annotate.sync_canon(g_rows, CANON)


def append_log(layer: str, obj: str, change: str, reason: str,
               path: Path | None = None) -> None:
    annotate.append_log(layer, obj, change, reason, path or LOG)


def commit(kind: str, key: str, value: str, extra: str = "", reason: str = "",
           log: Path | None = None) -> str:
    """标注 → 全量校验 → 写盘 → 记纠偏。路径取本模块（测试可替换）。"""
    return annotate.commit(kind, key, value, extra, reason,
                           log=log or LOG, decisions=DECISIONS,
                           canon_cand=CANON_CAND, canon=CANON)


# ── 界面 ────────────────────────────────────────────────

def launch() -> None:
    import tkinter as tk
    from tkinter import messagebox, ttk

    root = tk.Tk()
    root.title("判例复核 — AI 决策与隐含准则")
    root.geometry("1080x600")
    status = tk.StringVar(value="左侧选中标注对象：决策标维持/改判，准则标采纳/否决")

    tree = ttk.Treeview(root, show="tree", selectmode="browse")
    tree.grid(row=0, column=0, rowspan=4, sticky="nswe", padx=8, pady=8)

    right = ttk.Frame(root)
    right.grid(row=0, column=1, sticky="nswe", padx=8, pady=8)

    title = tk.StringVar(value="未选择")
    ttk.Label(right, textvariable=title, font=("", 11, "bold")).pack(anchor="w")
    body = tk.Text(right, width=74, height=10, wrap="word", state="disabled",
                   background="#f4f4f4")
    body.pack(fill="x", pady=4)

    form = ttk.Frame(right)
    form.pack(fill="x")
    choice = tk.StringVar(value="维持")
    radio_frame = ttk.Frame(form)
    radio_frame.pack(side="left")
    label = ttk.Label(form, text="")
    label.pack(side="left", padx=8)
    value_box = tk.Text(right, width=74, height=4, wrap="word")
    value_box.pack(fill="x")
    ttk.Label(right, text="理由（必填项见提示，记入纠偏记录）").pack(anchor="w")
    reason_box = tk.Text(right, width=74, height=3, wrap="word")
    reason_box.pack(fill="x")

    state = {"key": None, "kind": None}

    def radios(options):
        for child in radio_frame.winfo_children():
            child.destroy()
        choice.set(options[0])
        for opt in options:
            ttk.Radiobutton(radio_frame, text=opt, variable=choice, value=opt).pack(side="left")

    def refresh():
        d_rows = load_table(DECISIONS, DHEADER)
        g_rows = load_table(CANON_CAND, GHEADER)
        tree.delete(*tree.get_children())
        p1 = tree.insert("", "end", text=f"决策判例（{len(d_rows)}）", open=True)
        for r in d_rows:
            tree.insert(p1, "end", iid="d:" + r[0], text=f"{r[0]} {r[1]}")
        p2 = tree.insert("", "end", text=f"隐含准则（{len(g_rows)}）", open=True)
        for r in g_rows:
            tree.insert(p2, "end", iid="g:" + r[0], text=f"{r[0]} {r[1]}")
        return d_rows, g_rows

    d_rows, g_rows = refresh()

    def show_body(lines):
        body.configure(state="normal")
        body.delete("1.0", "end")
        body.insert("end", "\n".join(lines))
        body.configure(state="disabled")

    def on_select(_e):
        sel = tree.selection()
        if not sel or ":" not in sel[0]:
            return
        kind, key = sel[0].split(":", 1)
        state.update(kind=kind, key=key)
        value_box.delete("1.0", "end")
        reason_box.delete("1.0", "end")
        if kind == "d":
            r = find(d_rows, key)
            title.set(f"{r[0]} · {r[1]}    [{r[5]} · 复核：{r[6]}]")
            show_body([f"内容：{r[2]}", f"依据材料：{r[3]}",
                       f"暴露准则：{r[4] or '—'}", f"理由：{r[7] or '—'}"])
            radios(list(VERDICTS))
            label.config(text="改判填新内容 →")
            choice.set(r[6] if r[6] in VERDICTS else "维持")
        else:
            r = find(g_rows, key)
            title.set(f"{r[0]} · {r[1]}    [{r[4]}]")
            show_body([f"说明：{r[2]}", f"来源决策：{r[3]}", f"理由：{r[5] or '—'}"])
            radios(list(DISPOSITIONS))
            label.config(text="处置理由 →")
            choice.set(r[4] if r[4] in DISPOSITIONS else "候选")

    def save():
        if not state["key"]:
            messagebox.showwarning("未选择", "先在左侧选一条")
            return
        extra = value_box.get("1.0", "end").strip()
        reason = reason_box.get("1.0", "end").strip()
        try:
            if state["kind"] == "d":
                msg = commit("decision", state["key"], choice.get(), extra, reason)
            else:
                msg = commit("canon", state["key"], choice.get(), "", reason)
        except ValueError as exc:
            messagebox.showerror("拒绝写盘", str(exc))
            status.set("保存失败（见提示）")
            return
        d_rows, g_rows = refresh()
        on_select(None)
        status.set(f"已保存：{msg}")

    btns = ttk.Frame(right)
    btns.pack(fill="x", pady=6)
    ttk.Button(btns, text="保存标注", command=save).pack(side="left")
    ttk.Label(btns, text="保存前全量校验（含两表互链）；改判终审",
              foreground="#888").pack(side="left", padx=10)

    root.rowconfigure(0, weight=1)
    root.columnconfigure(1, weight=1)
    tree.bind("<<TreeviewSelect>>", on_select)
    root.mainloop()


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv == ["sync"]:
        print(sync_canon(load_table(CANON_CAND, GHEADER)))
        return 0
    if argv == ["check"]:
        bad = validate_all(load_table(DECISIONS, DHEADER), load_table(CANON_CAND, GHEADER))
        if bad:
            print("\n".join(bad), file=sys.stderr)
            return 1
        print("判例/准则两表校验通过")
        return 0
    if argv:
        sys.exit("用法：gui.py [check|sync]")
    launch()
    return 0


if __name__ == "__main__":
    sys.exit(main())
