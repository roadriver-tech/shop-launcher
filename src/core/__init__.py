"""核心层：规则与领域逻辑只此一份。

    schema    唯一表头与枚举
    rules     AGENTS.md 条文的可执行投影（词表、分数带、检查§1–4）
    annotate  标注政策与写盘（改判终审、纠偏记录、成文法渲染）
    assess    能力对照表：推导、一致性检查、判例优先重放
    deviation 偏差地图：偏差率算术校验、（品类, 城市）可信度
    tables    CSV 表读写（表头校验、原子写）

约定
    命令行入口 `src/cli.py` 与 GUI `src/gui.py` 只解析参数与画界面，
    规则不在入口处复制第二份。
    每条校验消息以 [条文编号] 开头（如 [检查§2]），可直接反查 AGENTS.md；
    编号与阈值由 tests/test_charter_binding.py 绑定章程，散文改了测试就红。
"""
