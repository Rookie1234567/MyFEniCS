# V18 P8 来源索引

这里保存 V18 P8 链的少量可读证据副本和索引。`T_root_qualification.json`、S/F joined terminal、C root closeout 与 C saved-array recomputation 均从 ignored 原件逐字节复制；5 份 T1/T2/T3/C_RECOVERY2/C_RECOVERY3 JUnit XML 也逐字节复制，并在 `source_index.json` 记录原件路径、SHA256、每项通过/失败/跳过数及用例名。索引同时列出原件仓库相对路径、旧/当前源码身份、九次运行终态和费用。C 的 host observation、PDE 数组、mesh、NPZ、逐行资源与完整 trace 保留在 ignored artifact 树，Git 中仅保留轻量摘录。

3 个 `.py.txt` 是本轮实际使用的只读审计脚本字节快照，用于审阅数组核算、primary/root 核验及 C closeout 归并。它们不是新入口或测试；脚本写入硬编码的工作站路径并采用 exclusive 创建，勿盲目重放。只读重算读取保存数组，不运行 PDE、重新采样或重新应用算子；40.116043168120086 秒以及另两项独立只读核对时间单列，不混入九个 workflow whole。source index 和证据副本只帮助定位数据，不授予数值 gate。

所有索引路径以及 `copied_compact_outputs[*].path` 和项目内 `source_path` 均以仓库根目录为基准；它们不相对于本目录。只有明确标为 `absolute_source_path` 的三项脚本来源指向 `/tmp`。原件与副本的 SHA256 在索引中逐一绑定。V17 F 的 whole 仍为 `NOT_MEASURED`，不可补零。
