# V17 R9_P8 轻量来源

本目录保留可审阅的精简记录和索引。完整 mesh、字段、1114 行资源流及主控原始大 observation 仍留在 ignored artifact root；这里不复制 1.76 MB 的 F observation，也不复制完整资源流。

| 文件 | 用途 |
|---|---|
| `S_space_joined_terminal.json`、`S_space_plan_audit_excerpt.json` | S joined 原字节，以及 FE、degree、carrier、约束、资源与 plan/audit 引用实值 |
| `S_runtime_trace_excerpt.json` | 从 S root observation 精简出的 runtime/ABI、资源摘要、进程身份、退出后 PID 核验、affinity events 和 trace 出口；绑定原 observation hash，不含 resource rows |
| `F_partial_terminal_excerpt.json`、`F_resource_summary.json` | F 已到阶段、退出缺口、未保存的独立 runtime 身份和资源 Gate 边界 |
| `F_trace_nonstack_and_setter_stack.jsonl` | 八份 trace 的全部非栈原行，并保留三个 setter 后的原始调用栈；每行注明原文件和行号 |
| `F_resource_first_last_raw.jsonl` | 原始资源 JSONL 的首行和末行；其余行仍在 ignored root |
| `F_launch_lifecycle_excerpt.txt` | 原 launch 的 EXIT trap/写入顺序，以及 watchdog 已有的 TERM/INT 与 finally 清理代码片段 |
| `T_root_qualification.json`、`T_root_qualification_draft.json`、`T_qualification_lineage.json` | 保留原资格和草稿，并说明核验者与单节点 raw observation 字段的补齐 |
| `v17_root_preflight_identity.json`、`v17_S_join_static_failure.json` | 主控静态身份核验，以及一次被局部纠正的 S joined 静态断言错误 |
| `offline_root_read_F_final.py`、`offline_root_join_S.py` | 从 `/tmp` 原样归档的只读 stdlib 后处理脚本快照；本轮不在此重跑 |
| `source_index.json` | 原件路径/hash、精简副本 hash 与 trace 行数索引 |

机器结果为 [`../v17_r9_p8_scientific_results_v1.json`](../v17_r9_p8_scientific_results_v1.json)。S 的真实独立 FE 为 110,722；F 的 124,530 是 carrier 行数，不能称作独立 FE。F 没有 official primary，C 未运行；外层 143、launcher 文件 0 与 watchdog 终态缺失的原因均保持 `UNKNOWN`。

索引中的 `original_sources` 和 `archived_exact_copies.archived` 使用仓库根目录相对路径；`compact_outputs` 中的文件路径使用本索引所在目录为基准。一次只读索引检查最初把 compact basename 按仓库根目录解析，报告17个路径缺失；改为按此目录解析后均已找到，实际没有证据文件缺失，也没有因此启动动态动作。
