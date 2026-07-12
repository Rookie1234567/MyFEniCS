# 文档审计

## 已重建

| 文件 | 状态 | 主要修正 |
|---|---|---|
| `README.md` | 完成 | 删除过期分支叙述，增加当前能力与边界 |
| `docs/README.md` | 完成 | 按阶段索引 Task000-Task028 |
| `docs/quick_start.md` | 新建 | 区分普通 direct 与显式 workstation |
| `docs/architecture_overview.md` | 新建 | 稳定模块和数据流 |
| `docs/solver_guide.md` | 新建 | profile 参数、残差gate和已排除路线 |
| `docs/result_schema.md` | 新建 | benchmark、RSS与R/T/A字段 |
| `docs/capability_matrix.md` | 新建 | 支持/未支持能力 |
| `docs/benchmark.md` | 新建 | L1-L3与当前结果 |
| `notes/reference/code_walkthrough.md` | 重建 | 对齐Task28模块 |
| `notes/reference/current_version_boundaries.md` | 重建 | 删除Task010时代边界 |
| `notes/README.md` | 重建 | 明确docs/notes职责 |

## 历史归档

Task021-Task027 选择性归档 58 个核心闭环文件。归档包含 task、review、summary、gate、merge、next、response、parameters 和 changed_files；不包含 raw_runs、场文件、矩阵缓存和大批中间诊断 CSV。

## 一致性检查

| 检查 | 结果 |
|---|---|
| Task000-Task027 progress CSV | 28 行，字段完整 |
| Task027 success/negative separation | 通过 |
| ordinary default 描述 | 明确保持 direct |
| h1.5 状态 | 明确未支持 |
| official power source | 统一为 DtN modal amplitudes |
| benchmark/results 边界 | 已说明 |
| 文档语言 | 中文为主 |

## Review V1 扩充

| 文件 | V1要求 | 修正结果 |
|---|---|---|
| `docs/quick_start.md` | 从clean/qualified环境可执行 | 增加PowerShell、Docker、完整命令、资源表、结果与错误处理 |
| `docs/capability_matrix.md` | 逐能力且状态统一 | 覆盖2D/3D全部指定项，使用8种标准枚举 |
| `notes/reference/code_walkthrough.md` | 解释调用链和生命周期 | 覆盖2D、3D、condensation、coarse、slabs、sm2和可信度链 |
| `docs/solver_guide.md` | 覆盖全部稳定direct/iterative路线 | 增加auxiliary、explicit condensed、MUMPS/OOC/BLR与参数域外流程 |
| `current_version_boundaries.md` | 声明能力、限制与资源 | 增加official/diagnostic、环境和benchmark边界 |
| `docs/development_progress.md` | 长期阶段总览 | 保留Task000-028并追加Response V1状态 |

最终本地Markdown链接检查通过。审查方新增的repository work principles、README保护区和对应测试均保留。
