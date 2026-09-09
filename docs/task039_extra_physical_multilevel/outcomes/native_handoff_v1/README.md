# 原生 Linux 迁移资料说明

本目录已完成历史输入、80 个有序衍射通道及编译条件的资料整理，供迁移前核对。它不是新的求解结果，也不是包含网格和解场的完整复现包。本次只提取文件与探测版本，未创建网格、装配矩阵或运行 PDE。

在所选历史证据中，CPU 型号、完整 Python、NumPy、DOLFINx、Basix、UFL、dolfinx_mpc、MUMPS 精确包版本和 GCC 次版本均未找到，具体缺失范围见 `historical_environment_scope.json`。当前 `dolfinx_mpc` 版本通过安装分发包 METADATA 的 Name/Version 确认为 `0.10.1`，来源路径已记录；该当前探测不用于倒填历史版本。

|资料|身份与用途|
|---|---|
|`mode_manifest.json`、`mode_identity.json`|历史 E1 原始 80 通道与身份说明；未重建或替换预期哈希|
|`historical_input_original.dat`、`historical_run_manifest.json`、`historical_resolved_config.json`、`historical_setup.json`、`historical_solve_summary.json`|原始输入、配置及求解记录，逐字节保留|
|`historical_recovery_checker.json`、`historical_recovery_summary.json`|同一个已保存解的后处理恢复证据；没有再次求解|
|`historical_stages_excerpt.jsonl`、`stage_index.json`|原始阶段行及原文件行号、哈希；时间差为派生量，不是 CPU 时间或独立内核耗时|
|`historical_compiler_samples.jsonl`、`historical_p4_generated_options.txt`、`p4_kernel_index.json`|原始编译采样、生成选项及 C 文件大小、哈希、函数名索引|
|`historical_source_configuration.json`|从求解源码 SHA 提取的 JIT 和积分配置小段，包含正确的 `fullspace_v17_p3_oracle.py` 和调用模块|
|`historical_environment_scope.json`、`current_environment_probe.json`|区分历史已有记录、历史缺失项和当前只读探测；当前版本不能倒填为历史版本|
|`provenance.json`、`files.sha256.json`|原件路径、提取方法与逐文件大小、SHA256；清单不包含自身|

原始求解源码为 `2bb6770ad00b35881558c576e7296e250656e571`。564 步达到原生真实残差 `9.932289219916376e-7`，但后处理采样面位于结构内部导致原工作进程失败；原 manifest 的 `WORKER_FAILED`、退出码 `4` 均保留。恢复源码 `094204b7281fe867744fe334e8753d2faebaf89b` 使用同一保存解修正采样面。不得把恢复成功改写为原工作进程成功。

通道原件来自 `c4e86cfe1e6ba88ca5d26df82942e82f190e7eda` 的 E1 记录，其字节 SHA256 为 `dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2`，与原求解记录中的通道身份相符。跨工作站比较应核对有序通道、波矢、偏振、功率及投影约定；不能遇到哈希差异便替换预期值。

历史生成 C 为 38,004,393 字节，仅收录索引和选项片段，未复制 C、共享库、矩阵、LU、解场或缓存。原始编译命令包含 `-march=x86-64`，不能假设使用 `-march=native`。当前 dpkg 探测包含 `libmumps-5.6t64`；空版本条目不代表已安装，历史 MUMPS 精确包版本仍未获证实。

资料整理时源码为 `4c5838d2d12e722641c3758f10874a499d12a0b9`。原始绝对路径只是来源索引，不是迁移后的执行路径。提取脚本首次因仓库导入路径缺失中止，修正后完成同一目录，未触发数值工作。本目录不回应或收口 G5。
