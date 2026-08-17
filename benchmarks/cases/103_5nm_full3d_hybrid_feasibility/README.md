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
| T0 | `completed` | inherited audit、material contract、resource budget outcomes；docs-only |
| T1 | `completed` | finite 5 nm profile/input/adapter 接线与 focused contracts；不改变 ordinary defaults |
| T2 A0 | `completed` | 纯 Python preflight record；无 formal PDE |
| T3 | `completed` | [Full3D direct MPI8 authority record](records/task039_t3_full3d_direct_mpi8_v1.json) |
| T4 | `negative_result_recorded` | [Full3D iterative MPI8 negative record](records/task039_t4_full3d_iterative_mpi8_negative_v1.json); 4000-step `DIVERGED_MAX_IT`, not a positive qualification |
| T5 | `completed_negative` | [Hybrid direct M convergence](records/task039_t5_hybrid_direct_m_convergence_v1.json); M_robust_h10 not established; Full3D diagnostic boundary retained |
| T6 | `not_run` / `blocked` | M_robust_h10 not established; no legal M960 direct observable/reference |
| T7 | `not_run` / `blocked` | T4 Full3D iterative negative and T5 M_robust_h10 absent block h7.5 reference; no accuracy-qualified h fit |
| T8 | `not_run` / `blocked` | T7/T4 prerequisite and M_robust_h10 absent; h5/MPI1 not started |
| T9 | `completed` | [0.7 nm component-only record](records/task039_t9_0p7nm_feasibility_v1.json); five component classifications; no full PDE |
| T10 | `completed` | [Final summary](../../../docs/task039_5nm_hybrid_qualification_and_0p7nm_feasibility/outcomes/summary.md)、[test summary](../../../docs/task039_5nm_hybrid_qualification_and_0p7nm_feasibility/outcomes/test_summary.md)、[response](../../../docs/task039_5nm_hybrid_qualification_and_0p7nm_feasibility/response_v1.md)；repository full pytest `cancelled / not_run` |

`config.json`、`schema.json` 是 T0 frozen launch scaffold，不是最终 outcome authority；
`expected.json` 只登记阶段证据索引，最终结论以 compact records 和 outcomes 为准。
这些文件不允许通过 CLI 覆盖 dat 的物理、solver 或 MPI 字段。T3
raw results 仍在 ignored 目录，record 只保存可审查字段和 SHA256。

T4 已有一次正式 Full3D iterative MPI8 运行，但残差在 4000 步上限仍为
`0.1552648200050503`（reported），因此记录为
`5NM_FULL3D_ITERATIVE_NUMERICAL_NEGATIVE_AT_P6H10`，不是 runner 的
`worker_nonzero` 科学分类。官方 R/T/A、场、canonical 和 direct-vs-iterative
比较均为 not_run。这个负结果阻断 T7/T8 的 Full3D iterative Phase B 扩展；T5
Hybrid direct 仍可作为独立容量诊断，不能被标成 Full3D-validated。

## DQ1 fixed-case qualification

DQ1 的 hash-bound compact evidence 已索引如下：
[task039_v3_h5_exact_side_case_qualification_v1.json](records/task039_v3_h5_exact_side_case_qualification_v1.json)。
它只记录 5 nm、1°、phi=0、S、p6/h5、M480、MPI8 的显式 exact-side case
qualification；完整 process-tree、marker、ledger 和 worker raw 仍留在 ignored run root，
没有把 raw artifact 纳入 case scaffold。worker checkpoint 的 pending_parent_resource_gate
与 parent resource authority 的派生合并关系见该 compact record。

## V4-2/V4-3 Full3D h4 boundary

正式 5 nm、1°、phi=0、S、p6/h4、MPI8 Full3D run（Full3D 无 internal Hybrid M，
Hybrid M480 仅为比较目标）在组装完成后进入 MUMPS factor setup，运行满 21600 s
timeout；factorization 未返回、solve/recovery 未开始；完整 process-tree peak 为 `213314.96484375 MiB`，
swap=0，未达到 `224000000000 B` hard stop。该结果分类为
`TASK039_V4_FULL3D_H4_TIMEOUT_DURING_FACTOR_SETUP_BEFORE_SOLVE`，不是数值方法负结果或 OOM。
它不能证明 post-factor lifecycle release 能降低 setup 峰值。
见 [V4 h4 lifecycle outcome](../../../docs/task039_5nm_hybrid_qualification_and_0p7nm_feasibility/outcomes/v4_full3d_h4_lifecycle.md)
和 [compact record](records/task039_v4_full3d_h4_lifecycle_timeout_v1.json)。旧 h4 partial
与 2D Q8 仍保留为历史/不完整诊断。
