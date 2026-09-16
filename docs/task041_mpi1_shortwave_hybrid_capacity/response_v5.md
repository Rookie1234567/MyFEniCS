# Task041 Response V5：V4 同布局响应配对收口

## 0. 当前状态与结论

V4-A0 已安全同步到 `b5d0a39e8f85a2c63d56df28fb8414836e5aef3b`。该 source/head 是 A0
同步时的身份，不是本轮七份待提交文档的最终 HEAD；宿主现场快照采集于
`2026-09-16T02:53:02Z`。宿主现场仍有另一项 Full3D 重型作业，因此本轮在启动前被
`BLOCKED_BY_ACTIVE_HEAVY_JOB` 收口；没有启动
Task041 的测试、MPI、PDE 或 service。V4 的 C1–C3、16 次主响应和 8 对响应比较均为
`not_run`，不能产生本轮 RSS、耗时、等价或提速数据。

这与历史结论分开：R2 原算法和唯一 R2g optimized 两场各完成 8 项（每场 bottom/top
各 4 项），但跨 fresh run
的凝聚编号没有稳定的物理行身份，正式状态仍为 `PAIRING_IDENTITY_UNPROVEN`；S1f 的双侧
构造仍以 `53331742720 B > 53221163008 B` 受控停止。两者都不是本轮 V4 的新数值失败。

| 项目 | V4-A0 实际状态 |
|---|---|
| 新运行 | `scope.new_runs=false`（仅表示本次 V4 文档/启动前阶段；R2 baseline 与唯一 R2g 已在历史阶段运行） |
| C1 轻量路径 | `not_implemented / not_run` |
| C2 MPI8 同布局组件运行 | `not_run` |
| C3 主响应比较 | `0/16` 主响应，`0/8` pairs，`not_run` |
| layout / P / PH / PC / response 等价 | `not_run` |
| 本轮 RSS / speedup | 无数据；不得从旧 R2 数字重标为 V4 测量 |
| 本轮停止原因 | `BLOCKED_BY_ACTIVE_HEAVY_JOB` |

## 1. 启动前现场与账本

当前宿主只读快照显示受保护的 `Maxwell3D-Lab/task39extra_para_workstation_capacity`
仍在运行：public `2949935`（starttime ticks `161587726`，affinity `9`）、MPI launcher
`2949971`（`161587846`，affinity `23`）、worker `2949974`（`161587857`，affinity
`23`），以及 observer `2952397`（`161611593`，affinity `9`）。这些是现场新读到的身份，
不复用此前已退出的旧 PID。完整的 argv、cwd、runroot、RSS 和 swap 快照见
[A0 宿主保护证据](../../results/task041_side_balh_component_audit/v4a0_preparation_20260916_b5d0a39e/active_heavy_protection.json)
（SHA256 `8b3b1ce344bfcb66ad313db6fd714f01fda53375cbb6509432577b39541ff98d`）。

唯一 V2 账本仍为
`../../results/task041_side_balh_component_audit/task041_schur_speed_v2_s1a_3890cdd2/task041_schur_speed_v2_compute_wall_ledger.json`，
当前 `used_compute_wall_seconds=11145.889606652894`，shared 桶剩余
`10454.110393347106 s`，batch 上限 `201600 s`，S2/S4 均为 `0`；账本 SHA256 为
`1473ad466c95a05bf4f4c186864d03f3304f58b904873a9ae6ecca08a7535953`。本次对四次
先前遗漏的静态失败按 `tool_reported_command_duration` 一次追加 `0.180794456 s`；
上一次静态核对已按 `0.099701023 s` 计入，阅读、等待和编辑时间未计入计算成本。
四次失败（其中两次直接发现文档 hash 错误）及其公开 execution id、UTC、exit1 和原始
原因均保存在 compact 的 `documentation_checks` 中；它们不是 PDE/数值失败。

## 2. V4 要验证什么

“同布局”是指两种传递实现使用同一侧的 mesh、MPC、凝聚映射、原始 global action/RHS 和
同一套 p4 factor；这样比较的是传递实现本身，而不是两个 fresh run 中无法对应的 PETSc
编号。每侧只构建一次：先 bottom 的四个固定 RHS，释放并以真实 diagnostics 确认 p4/KSP
为零，再构建 top 的四个 RHS。不能同时保留两侧 adapter/factor，也不能重建 mesh、MPC
或 global operator。

固定顺序为八个 frozen entry 的 ordinal `0..7`；偶数 ordinal 先走 legacy，奇数 ordinal
先走 optimized，再用同一 live layout 下的 owned global vector 比较。每个实现均为零初值，
不复用 KSP guess。总计是 `8 RHS × 2 implementations = 16` 次主响应、8 对；这不是
完整 Schur、outer、recovery、official RTA 或 QEP 运行。

固定身份如下，列号来自原始审计映射，不进行值排序、相位拟合或跨运行行重排：

| ordinal | side | 原始 audit index | formal column |
|---:|---|---:|---:|
| 0 | bottom / positive | 227 | 207 |
| 1 | bottom / positive | 35 | 15 |
| 2 | bottom / negative | 691 | 671 |
| 3 | bottom / negative | 513 | 493 |
| 4 | top / positive | 330 | 310 |
| 5 | top / positive | 32 | 12 |
| 6 | top / negative | 686 | 666 |
| 7 | top / negative | 513 | 493 |

仍须执行原有 action、transfer、duplicate-row、ghost/MPC、P/PH、p4/refinement、BAL_H、
KSP reason/iteration/explicit residual 检查。V4 附加的同布局响应差异只是诊断门：
诊断字段为 `threshold_e_x=1e-8`、`threshold_e_A=1e-8`，实测值均为 `null`；它不替代原始
`1e-11` action/transfer 线性门，也不把近似 KSP response 另立成 `1e-11` 硬门。每个响应仍须 `reason>0` 且 explicit residual
`<=1e-2`，p4 residual `<=1e-10`，BAL_H `<=1e-8`。

任一 ABI、source、manifest、owner layout、identity、数值或资源 Gate 失败都停止并保留
证据，不自动重试。超过严格全树 RSS cap `53221163008 B`、job/global swap 或时间/安全
门时由既有监督路径受控停止；90% warning 只是预警，不能提高 cap。V4 未授权新增热点
优化、QEP、完整双侧 consumer 或 13.5 nm 全场扩展。

## 3. 历史结果的正确用途

以下数字是旧 R2/R2g 的实测历史对照，不是 V4-A0 数据，也不能绕过编号身份门：

| 历史对象 | R2 baseline | 唯一 R2g optimized | 解释 |
|---|---:|---:|---|
| 分侧 8 项 apply | `1680.27495998214 s` | `1258.8479048048612 s` | 分区不同；只可作历史组件耗时差 |
| full service wall | `4015.539370124 s` | `3630.563676387 s` | 不是本轮完整 consumer 结论 |
| full-tree RSS | `51975606272 B` | `51796770816 B` | 历史运行峰；不是 V4 paired non-increase |

旧 R2 的 132300 condensed rows 没有可跨运行验证的几何/拓扑、方向或 MPC active-row key；
位置相减约 `sqrt(2)` 只能记为 `diagnostic_only_unverified_numbering`。同样，R2e tiny-FE
的 P/PH relative `0` 只证明那一小组 action/transfer 等价，不能升级为 5 nm response
等价。R2b 的类别/分项统计可作后续预测的旧输入，但不替代本轮配对。

旧 S1f 的双侧构造曾达到 `53331742720 B`，高于本 cap，fixed8=`0/8`，分类为
`process_tree_rss_limit` 的受控资源停止；旧 H3 的 `RESOURCE_COMPARISON_INCONCLUSIVE`
和父丢失事故继续单列。预算尚余不等于双侧准入已满足。

### 3.1 旧 R2b 构造内存摘录（非 V4 测量）

以下六行来自既有 [R2b analysis v2](../../results/task041_side_balh_component_audit/r2_preparation_20260915_3ee452ac/r2b_analysis_v2.json)
（SHA256 `9bac3eaae74911198b656ae75b6a2959b62b6d7ae2130702c219502a02a5c28a`）与旧 R2
compact。inventory 是 rank-local 暴露 payload 下界；RSS 是约 0.3 s 级的全树采样在
marker 前后的括号，PSS/USS 才是稀疏诊断。各行不是可相加的内存账，也不证明泄漏。

| 阶段 | 已知 inventory / RSS 关联 |
|---|---|
| 公共/借用数据 | p6 mesh、FE/MPC 与 physical inputs 为借用；full-action owned vectors bottom/top 为 action/input `826752/841728 B` 各一份，另有 mode/traction arrays；不是全树 RSS |
| bottom 保留与释放 | `before_release` marker line 51 / memory line 8112：`37383737344 B`；`bottom_after_release` marker line 53 / memory line 8114：`32090693632 B`，按 cap 重算余量 `15837425664/21130469376 B`；是 marker 前后括号，不等同 native 全返还 |
| top 构造临时 | `top p4 factor_ready` marker line 64 前/后 memory line 9881/9882：`51259228160/51315433472 B`；`top transfer_ready` line 66 后、memory line 10150：`51867832320 B`；`top H6 ready` line 72 后、memory line 10306：`51974172672 B`。对应 cap 余量（p4 前/后、transfer、H6）为 `1961934848/1905729536/1353330688/1246990336 B`；不是同刻值 |
| p4 源矩阵与 factor | bottom/top local shape `15520²/15872²`、local nnz `6928418/7130656`；estimated payload `166282032/171135744 B`，`getInfo(LOCAL)` native memory 为 `0`；MUMPS/native factor workspace unknown |
| transfer/H6 | transfer known local payload 含 canonical map `4233600 B`、fine work `1584288/1596000 B`，其余 coarse/dual 分阶段记录；H6 known arrays 含 basis values/curls 各 `10838016 B`、kernel dofs `275184 B` 等，不与 RSS 相加 |
| allocator/native unknown | PETSc/MUMPS/FFCx/backend workspace、full-action/H6 matrix、Vec ghost/native allocation及 destroy 后 allocator retention 均 unknown；旧全树峰 `51975606272 B` 的 cap 余量按实算为 `1245556736 B`，optimized 历史峰 `51796770816 B` 余量为 `1424392192 B` |

旧 S1f 双侧超 cap 为 `110579712 B`，仍是独立负证据。上述分侧括号只能帮助定位近 cap
时段，不能替代新的双侧资格。

## 4. 最小实现边界（待后续准入）

代码审核通过且宿主 heavy 空闲后，才拟在现有路径实现显式 `common_layout_equivalence`
opt-in：

- 主控制流：`benchmarks/task041_exact_side_workflow.py` 的
  `_run_task041_balh_candidate_setup` / `run_task041_consumer`，复用既有 sequential
  side build/probe/release 与 fixed manifest；不复制 runner 或 checker。
- 已有优化路径：`src/solvers/physical_balanced_same_mesh_transfer.py` 中的 legacy
  `_resolve_owner_candidates`、`matrix.conj().T` 路径与 V2
  `_resolve_owner_candidates_batched`、`_apply_conjugate_transpose_vector`；不改变 P/PH
  数学、阈值或通信顺序。
- 必要绑定：仅在现有 `benchmarks/task041_balh_workflow.py`/既有 public 参数链确有缺口
  时传递 comparison mode、manifest 与 profile；不新建 CLI、service、ledger 或
  canonicalization 框架。
- 轻量测试计划：先用现有 `test_346` 的纯/小 fixture 验证双路径交替和输入不变，再用
  必要的 `test_347`/`test_351` 做小 FE/合同接线，最后才是一次 MPI8 同布局组件运行。
  本 A0 未执行上述任何测试。

计划中的一次 MPI8 运行资源固定为 8 ranks、CPU `0–7`、每 rank 一个数学线程、同一专属
process-tree RSS cap `53221163008 B`；C1 预计仅为秒至分钟级。C2/C3 的实际时长当前
不作新预测，受唯一 shared 剩余 `10454.390888826107 s` 和既有 time-stop 约束；旧 R2
wall 只作历史排程参考，不能写成 V4 预计或实测。

## 5. 证据与交付边界

本轮新 compact 为 [common_layout_equivalence_v4.json](outcomes/records/task041_common_layout_equivalence_v4.json)，
计划说明为 [common_layout_equivalence_v4.md](outcomes/common_layout_equivalence_v4.md)。
它只引用必要的 [V4 review](review_report_v4.md)、[旧 S0/S1/S1f/S5a compact](outcomes/records/task041_schur_speed_v2.json)、
[旧 R2/R2g compact](outcomes/records/task041_setup_recovery_v3.json)、唯一账本和 A0 宿主证据；
V4 没有 `run_directory`、`service_unit` 或 public runroot，不生成假路径，也不复制旧大 raw。

后续七份正式文档分别说明：V4 的启动前阻塞、历史 R2/R2g 的边界、C1–C3 的
`not_run`、旧 `PAIRING_IDENTITY_UNPROVEN`、旧双侧资源停止，以及依赖分组。最终状态只有
在同一布局、所有原始 Gate 和 8 对响应同时闭合时才可改写；当前不作任何等价/提速/内存
不增或 production 结论。
