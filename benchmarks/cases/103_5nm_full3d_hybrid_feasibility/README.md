# Task39 5 nm hybrid feasibility case 103

这是 Task39 的 8 个正式 dat 与分阶段 frozen run 的统一 case scaffold。这里的
`one_dat_one_run` 表示每个 dat 每次只触发一个 frozen run，不表示 case 只有一个 dat。
A0 只做
输入解析、动态外部通道清单和容量预估；没有启动 mesh、MPI 或 PDE。完整的
604-channel authority
inventory 只保存在 [T2 A0 record](records/task039_t2_a0_preflight_v1.json)。

## 输入与身份

- 物理输入：`input/official/task039/` 下 8 个 p6/h10 dat；每个 dat 独立声明
  method、M、MPI 和输出身份。
- 共同物理 hash：由 A0 record 的 `method_identity_matrix` 重算，不能由 case
  scaffold 中的重复物理参数代替。
- 继承的 p6/h10 topology 只来自
  [compact carrier](records/inherited_p6h10_topology_v1.json)，标为
  `inherited_measured`，不是 5 nm 正式 PDE 测量。

## 阶段状态

| 阶段 | 状态 | 证据/边界 |
| --- | --- | --- |
| T2 A0 | `completed` | 纯 Python preflight record；无 formal PDE |
| T3 | `completed` | [Full3D direct MPI8 authority record](records/task039_t3_full3d_direct_mpi8_v1.json) |
| T4 | `not_run` / `planned` | Full3D iterative anchor |
| T5 | `not_run` / `planned` | Hybrid direct M selection |
| T6 | `not_run` / `planned` | Hybrid iterative candidate |
| T7 | `not_run` / `planned` | conditional p6/h7.5 reference / Hybrid qualification |
| T8 | `not_run` / `planned` | conditional p6/h5 + MPI1 minimum-memory |
| T9 | `not_run` / `planned` | 0.7 nm component-only feasibility |
| T10 | `not_run` / `planned` | final tests, outcomes and response |

`config.json`、`schema.json` 和 `expected.json` 只描述这个计划与已绑定的 T2/T3
compact evidence；它们不允许通过 CLI 覆盖 dat 的物理、solver 或 MPI 字段。T3
raw results 仍在 ignored 目录，record 只保存可审查字段和 SHA256。
