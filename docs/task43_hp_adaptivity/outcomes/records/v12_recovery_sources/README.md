# V12 有限恢复证据索引

本目录保存本轮准备、两次失败的支持验证和最终静态修正证据；没有 D1、P2R 或正式 PDE 运行结果。[逐文件索引](index.json)绑定轻量原文的 SHA256 和大小。大原件仍位于 ignored `benchmarks/artifacts/task43/v11_science/recovery_v12/`。

| 入口 | 内容与边界 |
|---|---|
| [首次 S1](support/focused_attempt1/root_closeout.json) | 10/24通过，14 fixture失败；含真实main/ABI、资源55行摘录、全部trace事件及独特栈帧计数 |
| [唯一 S1 恢复](support/focused_recovery1/root_closeout.json) | 12/14通过，2断言失败；含真实runtime身份、资源16行摘录和全部trace事件 |
| [恢复合成原件摘录](support/focused_recovery1/root_fixture_excerpts.json) | observer原数组门和P5合成分类；全部是fixture，不能写入科学模型结果表 |
| [最后两断言的静态检查](preparation/final_unrun_static_check.json) | AST、未定义名、diff格式；最终pytest字节未运行 |
| [原历史trace摘录](preparation/historical_trace_excerpts.json) | 只读取既存P1恢复trace和旧P2连续停止栈；不重跑、不作性能归因 |
| [薄launch归档](launch/) | 实际S1两脚本及未运行D1/P2R提案；文件存在不等于已launch或获得继续资格 |

`resource_rows.json`保留逐样本PID/PPID/start_ticks、CPU、RSS、swap与资源门实值；`trace_events.json`保留所有非栈行原文/行号以及全部独特栈帧和次数。完整原始trace逐文件hash在其中，主控解析完整字节后逐项阅读事件、尾段及独特帧；摘录不冒充原始完整trace。退出码、pytest XML和launch manifest均保留原文。空`source_status.txt`表示当次dispatch干净，不代表最终交付与历史测试同字节。

两次support whole合计49.582441974431276秒；S1两槽用尽，V12支持总计2/4，未用D1/P2R因前门未通过而不可启动。所有科学能力状态、正式5/8扩展包络及无合并许可保持。见[Response V12](../../../response_v12.md)与[机器结果](../v12_recovery_and_scientific_results_v1.json)。
