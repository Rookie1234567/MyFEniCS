# V10 静态纠正证据索引

这里只处理已保存文本，不是运行入口。执行权威为[正式V9 review](../../../review_report_v9.md)第9节；回应见[Response V10](../../../response_v10.md)，费用和资格见[纠正记录](../v10_static_evidence_correction_v1.json)。

| 入口 | 内容与范围 |
|---|---|
| [纠正版依赖表](corrected/direct_needed_edge_map_corrected.json) | 唯一当前V10派生表：61边、18 parent、24 resolved对象；不代表新采集或运行映射 |
| [逐字段差异](corrected/direct_needed_edge_field_diff.json)与[原边界摘录](corrected/direct_needed_raw_boundary_excerpts.json) | 三条共12字段；保留原stdout hash与原行号，旧v1不变 |
| [保存的输入摘录](v9_static_input_context.json) | activation/venv实际source行、长短MCA名、参数/override/路径；来自旧raw，不是当前环境检查 |
| [主控独立核算](root_review/root_independent_accounting.json)与[最终逐字段比较](root_review/root_final_static_comparison_attempt3.json) | PACKAGE终止解析、旧15对象NEEDED集合覆盖，再比较最终代理表；含实值与全部对应边 |
| `static_action_records/` | 本轮静态失败/成功输出、退出码、计时及四次代理parser命令；不计作support/sanity/pytest |
| `collector_snapshots/` | 10份原采集脚本的字节副本，只供阅读，**本轮未执行** |
| `parse_direct_needed_stdout.py`、`build_v9_input_context_excerpt.py`、`root_review/*.py` | 本轮仅解析保存文本的stdlib脚本；不是旧v1生成器，也不提供任何运行许可 |

错误行号的attempt2完整输出、输入摘录初稿和错误closeout初稿保留在ignored，并由纠正记录索引；不与当前表并列为权威。具体历史v1生成器、语句与生成时间UNKNOWN，不能从相邻污染推定具体根因或当时launch必然误放行。

固定D3与20项测试只复用正式V9的有限工程接受；本轮新增运行全0，科学状态和合并资格不变。
