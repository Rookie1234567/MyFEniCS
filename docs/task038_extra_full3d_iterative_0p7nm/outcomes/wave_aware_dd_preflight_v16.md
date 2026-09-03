# W0：wave-aware interface Schur DD 预审

本文件是 Review V16 的 W0 docs/read-only preflight，不是 W1 实现或数值结果。它只冻结一个候选：
`wave_aware_interface_schur_dd_v1`。W0 的作用是先回答“矩阵机制和同时内存能否闭合”；如果不能，后续只能进入 Z0，不写 DD solver。

## 结论

| 项目 | 结论 |
|---|---|
| 进入原因 | Q2 的真实 reference correction 数值 Gate 失败；不是把旧负结果重分类 |
| candidate | `wave_aware_interface_schur_dd_v1` |
| local iterative inverse | Q2 机制已失败，因此固定为 `same_mesh_positive_pMG` fallback；`restart/max_it=20/100`，不得恢复 physical p-coarse |
| W0 classification | `W0_INTERFACE_RANK_CAPACITY_FAIL` |
| `eligible_for_W1` | `false` |
| major unknown | 三条内部接口的实际独立 trace rank/count；四组 R/P map、local physical workset、streamed harmonic workset 的 simultaneous bytes |
| W1–W4 | `not_run`；不实现、不运行、不创建对应 outcome |
| 下一步 | 仅允许 Z0；不重跑 V15 rank32，也不重开 GenEO/BDDC/HX |

失败原因是证据边界而非猜测的资源超限：已有 authority 规定了三个接口和 `rank≤512` 的上限，但没有给出这个固定四分位几何在当前 p1 tangential trace 加 exact gradient-trace 后的实际 key inventory、独立 rank 或 map/workset 字节。因此不能把上限当作已经闭合的 rank/count，也不能把局部对象的门限当作测量值。

## 身份和冻结触发

| 项目 | 值 |
|---|---|
| Review/source commit | V16 / `9f18a6ccdf979f13fcb8eaab2bd57defb55f3c7b` |
| branch | `codex/20260820-task38-extra-full3d-iterative-0p7nm` |
| input file SHA256 | `819fc99caea2dbc8ea22546917fbe3898c822a955d079b4582c4a27e34ebba41` |
| normalized checkpoint input identity | `754dbf810cc38b32804bced03b8d4b8f702d5943671724e7529f47cadefe8b1f` |
| physical model SHA256 | `9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f` |
| ordered mode manifest SHA256 | `dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2` |
| Q2 checkpoint manifest / solution | `7f7d6fd29e6a3d6130de439fa510a19c6830061f59090cfd9f6ee4c51d8eb139` / `00f55e5256e673687942f79d98398d0fd2524d6d956c3b7ef5264615ab2c659b` |

Q2 的永久保留事实为：checkpoint reproduction relative `6.8416957056789795e-09 > 1e-11`，inner 10000 步 true residual `0.7749555148382701 > 1e-6`，`rho_ref=2.7001483995603124 > 0.70`，`rho3=0.774955514838267 > 0.10`；parent peak `1,560,625,152 B`、worker peak `873,783,296 B`、swap `0 B`。这些是 Q2 的 measured evidence，不是 W0 的新测量。

Q2 formal evidence packet 使用实际 artifact 的 root-relative 路径；`checker.json` 是 checker record 的实际文件名，`parent_process.jsonl` 是 process timeline 的实际文件名：

| root-relative path | SHA256 |
|---|---|
| `parent_record.json` | `7957ceeb43b449aa5adf0281d77c69a43fde51ec17fb8d0adc8dee2f94b14cd6` |
| `raw/worker_record.json` | `df541289efe0de98887f342a45125dc77b46cd3127a4a77835cd07767cca0f92` |
| `parent_process.jsonl` | `a31cdf1b673777ec0f5eb3513ce311994959a15c07908a2914882f9eb1dc46c4` |
| `marker_manifest.json` | `451c336a031597735a40ab5d7035210eda517be409b10e5c99c769fbd8b4087a` |
| `checker.json`（checker record） | `12e4fbe4d41a96afbc2bd4d644ae4e2b97756a3d6d2a5eccb0f7743dff48bde4` |

checkpoint manifest/solution SHA 仍为 `7f7d6fd29e6a3d6130de439fa510a19c6830061f59090cfd9f6ee4c51d8eb139` / `00f55e5256e673687942f79d98398d0fd2524d6d956c3b7ef5264615ab2c659b`；old checkpoint source SHA 为 `ee5920b9fa977a39fea7bc09cfbe155303acdb2d`。

证据入口：[`Review V16`](../review_report_v16.md)、[`Q0 preflight`](physical_pcoarse_preflight_v16.md)、[`V15 后候选边界`](next_wave_aware_dd_after_v15.md)、[`V14 response`](../response_v14.md)、[`V15 response`](../response_v15.md)、[`Q2 parent raw`](../../../benchmarks/artifacts/task038_extra_full3d_iterative_0p7nm/q2_checkpoint_reference_v1/9f18a6ccdf979f13fcb8eaab2bd57defb55f3c7b/mpi1/parent_record.json)、[`Q2 worker raw`](../../../benchmarks/artifacts/task038_extra_full3d_iterative_0p7nm/q2_checkpoint_reference_v1/9f18a6ccdf979f13fcb8eaab2bd57defb55f3c7b/mpi1/raw/worker_record.json)、[`Q2 checker`](../../../benchmarks/artifacts/task038_extra_full3d_iterative_0p7nm/q2_checkpoint_reference_v1/9f18a6ccdf979f13fcb8eaab2bd57defb55f3c7b/mpi1/checker.json)。

## 通俗解释和唯一矩阵机制

区域分解把大问题切成数个有一层重叠的小区域；局部求解处理体内变化，接口粗问题负责把跨区域传播波的相位和切向场重新接起来。它的收益是避免保存一个随有限元规模增长的全局粗基；代价是必须明确接口自由度、方向、梯度耦合和 owner 路由，且局部物理逆仍可能昂贵。

固定四个只由几何 z 四分位得到的子域 `Ω_i^q`（`i=0,…,3`），每个子域加一层 h10 cell overlap；三个内部接口为 `Γ_1,Γ_2,Γ_3`。令 `R_i` 是 full-space 到 `Ω_i` 的 restriction，`R_i^H` 是 owner-local prolongation，`D_i` 是重叠区域的 PoU 权重，冻结为

```text
sum_i R_i^H D_i R_i = I
```

现有 exact split-volume plus streaming-DtN 物理 action 记为 `A_phys`。由于 Q2 的 physical p-coarse correction 已真实失败，W0 的 local iterative inverse 只能是已资格化的 `same_mesh_positive_pMG` fallback；local `restart/max_it` 固定为 `20/100`，不得暗中恢复 physical p-coarse。局部矩阵机制唯一写成

```text
A_i = R_i A_phys R_i^H + B_i^T4,
S_Gamma = sum_i H_i^H A_i H_i,
P_Gamma = sum_i R_i^H D_i H_i,
C_Gamma = P_Gamma S_Gamma^{-1} P_Gamma^H.
```

其中 `B_i^T4` 是冻结 T4 一阶 impedance，只放在人工切面上使局部问题可解；它不是全局传播机制，也不是新的 Robin 扫描参数。`A_i` 的体积、complex material mass、真实 Maxwell curl 和 streaming DtN 均保持 physical matrix-free action。`H_i` 是 two-sided physical harmonic extension：对每一侧的接口数据解局部 `A_i` 闭合的物理延拓；`S_Gamma` 的 apply 在 owner 上流式累加，不构造 production global AIJ、dense DtN、physical factor 或 persistent FE-sized `Z/AZ`。

每个 `Γ_j` 的接口变量固定为 p1 tangential H(curl) trace 和其 exact gradient-trace：

```text
T_j u = (T_j^t u, grad_Gamma T_j^0 u),
H_i : trace -> local physical harmonic field,
P_Gamma^H = sum_i H_i^H D_i R_i.
```

production `S_Gamma^{-1}` 只能是 owner-distributed iterative apply/solve；rank `≤512` 的 dense matrix+factor 仅允许作为 diagnostic oracle。此处的 `rank≤512` 是冻结上限，不是实际 rank 证据。

## 与旧路线的矩阵差异

| 路线 | 已有矩阵机制/事实 | 本候选不可混淆的差异 |
|---|---|---|
| T4/T5 two-slab Robin | 两个 slab 的一阶 Robin/transmission action；旧测试只证明边界 action，不形成三接口 global Schur，且 contraction 弱 | 本候选是四个 quartile 子域、三条接口、`C_Gamma=P_Gamma S_Gamma^{-1}P_Gamma^H`；T4 只闭合人工边界 |
| V15 fixed rank32 projection | 固定全局波模 `Z_32` 的 projection/correction；已捕获 `0.002179823642496248`，`rho=0.9989094935766222`，span Gate 关闭 | 本候选由完整 p1 trace、gradient trace 和 local physical harmonic extension 产生接口空间；不使用 `Z_32`，不重跑 global projection，不做 residual fitting |
| 普通 GenEO/BDDC/HX | 依赖正定/辅助能量、通用 coarse constraints 或 HX hierarchy；不是当前不定传播 Maxwell 的接口机制 | `A_i` 保留真实 physical curl/mass/DtN 和 phase；传播与 near-cutoff 身份由显式接口 trace 承担，不是把正定 coarse 换名 |
| 旧 trace-harmonic/local-spectral | [`fullspace_trace_harmonic.py`](../../../src/solvers/fullspace_trace_harmonic.py) 的辅助形式是 coercive `curl-curl + k0^2 abs(epsilon) mass`；distributed 版本有旧 slab-local eigen/rank prefixes | 本候选使用真实 `A_i` 的 two-sided physical harmonic extension；production 不保留 FE-sized Z/AZ 或 local factor，diagnostic dense oracle 也只受 rank cap 约束 |

因此这是一个不同的 restriction/harmonic/Schur 组合，而不是旧 two-slab、rank32、GenEO、BDDC、HX 或 local-spectral 路线换名。

## 接口 rank/count authority

| 量 | 冻结值或公式 | authority 状态 |
|---|---|---|
| internal interfaces | `3` | Review V16 固定 |
| geometry subdomains | `4` z quartiles + one h10-cell overlap | Review V16 固定；未读取/改写网格 |
| independent trace rank | `r_Gamma = rank([T_j^t, grad_Gamma T_j^0]_{j=1}^3)` after MPC/orientation dependencies | **unknown**：没有当前 p1 key inventory、cell/facet count 或 dependency audit |
| accepted total rank | `r_Gamma <= 512` | 只有 hard cap；不是 measured/derived actual count |
| old trace ranks | D1 fixed `16`; distributed prefixes `16,32,48,64` | 旧 auxiliary route，不能替代本候选 rank |
| V15 rank32 | `32` global Floquet modes | 仅 projection error evidence，不是接口 basis |

因此 `major_unknown` 不能为空。没有实际 `r_Gamma`，就不能诚实地计算四组 R/P map 的 bytes、trace metadata 或 harmonic work，也不能证明 metadata/local simultaneous Gate。

## simultaneous live-set 账本

staging 和 solve 是 phase-disjoint，不能把两个阶段的对象逐项相加：

```text
overall_peak = max(cold_staging_envelope, solver_live_set, recovery_phase)
```

所有字节都是 measured、derived 或 predicted 的明确口径；未知项不填零。Q2 parent peak 是完整 cold-staged workflow 的校准，Q2 worker peak 是 solver-stage upper anchor；二者不是 W0 solver 对象的可重复 baseline。

| 阶段/同时存活对象 | 公式/值 | 字节 | 口径 |
|---|---:|---:|---|
| central cold-staging envelope | V14 J5 pass-to-controlled-stop anchor | `1,450,262,528` | measured；不是完整 workflow PASS |
| hard cold-staging envelope | `max(V14 J4 1,557,270,528, Q2 parent 1,560,625,152)` | `1,560,625,152` | measured conservative calibration；不与 solver 相加 |
| Q2 solver-stage anchor | p6+p3/restart20/10k inner worker peak | `873,783,296` | measured upper anchor；不是 W0 retained 精确测量 |
| diagnostic dense oracle matrix+factor | `2 * 512^2 * 16` | `8,388,608` | predicted numeric upper bound；条件满足 `<=32,000,000` |
| four `R_i/R_i^H` maps | `4 * U_RP(r_Gamma, mesh, overlap)` | **unknown** | no authority inventory/bytes；不能假设等于旧 transfer |
| one local physical workset | `U_local` | **unknown** | simultaneous local total must be `<=250,000,000` |
| trace metadata | `U_trace(r_Gamma, keys, orientation, phase)` | **unknown** | must be `<=100,000,000`; rank/count missing |
| streamed harmonic work | `U_harmonic` | **unknown** | recomputable, not persistent; no byte authority |
| owner routing / phase-coupling | `U_owner + U_overlap` | **unknown** | overlap with measured worker anchor not proven |
| outer restart20 reserve | not separately added to Q2 worker anchor | `U_restart` | overlap attribution is unresolved; do not charge a second fixed basis |
| solver allocator/JIT increment | not separated from worker anchor | `U_allocator` | no independent W-only authority; no Q0 reserve is double-counted |
| release-before-recovery reserve | `2 * V6 = 2 * 2,780,832` | `5,561,664` | predicted separate phase after release |
| persistent FE-sized `Z/AZ` | forbidden | `0` retained | fixed architecture constraint, not an allocation claim |
| prior Q0 allocator/JIT reserve | central / hard `64 MiB / 128 MiB` | `0` incremental | prior forecast only; assigned to its own Q0 envelope |

Let

```text
U_active = 4*U_RP + U_local + U_trace + U_harmonic
           + U_owner + U_overlap + U_restart + U_allocator
U_recovery = U_recovery_work + U_recovery_overlap
solver_live_set = 873,783,296 + 8,388,608 + U_active
recovery_phase = 5,561,664 + U_recovery
```

The phase-disjoint auditable formulas are

```text
central = max(1,450,262,528,
              873,783,296 + 8,388,608 + U_active,
              5,561,664 + U_recovery)
        = max(1,450,262,528, 882,171,904 + U_active,
              5,561,664 + U_recovery)

hard-upper = max(1,560,625,152,
                 873,783,296 + 8,388,608 + U_active,
                 5,561,664 + U_recovery)
           = max(1,560,625,152, 882,171,904 + U_active,
                 5,561,664 + U_recovery)
```

在未知项为零的条件算术中，central/hard 分别为 `1,450,262,528 B` / `1,560,625,152 B`，距门限的条件余量为 `299,737,472 B` / `339,374,848 B`；这不是 PASS margin，因为 `U_active`、`U_recovery` 和 phase coupling 均没有 authority bound。独立 Gates 仍要求 `U_trace<=100,000,000 B`、local simultaneous total `<=250,000,000 B`、oracle `<=32,000,000 B`。只有 oracle 的 numeric upper bound 可由固定 cap 条件闭合，metadata/local/overall capacity 均未闭合。

## Gate、未运行项和历史边界

| Gate | 结果 | 说明 |
|---|---|---|
| matrix mechanism | formula-defined | 未做 W1 数值 identity；不冒充通过 |
| actual rank/count | FAIL | `r_Gamma` 与 key inventory 未由现有 authority 给出 |
| central / hard simultaneous capacity | FAIL | 未知 `U` 不能填零或用预测消除 |
| metadata/local/oracle capacity | FAIL / conditional | metadata、local 未闭合；oracle 仅有 cap-based numeric upper bound |
| persistent FE-sized Z/AZ | fixed forbidden | 不创建、不保留 |
| W0 overall | `W0_INTERFACE_RANK_CAPACITY_FAIL` | `eligible_for_W1=false` |

W1 的 R/P/PoU、人工 impedance、local physical action、harmonic residual、MPI owner identity、phase、finite、input unchanged 和 swap/lifecycle 均为 `not_run`。W2 local-only/two-level contraction、W3 short screen、W4 fresh physical、official output 也均为 `not_run`。本回合没有实现代码、没有创建 solver/checker、没有运行测试/PDE/formal；两份文件之外的旧 Q2、V14、V15 raw/compact/negative 均不改动。

本文件对应的 compact facts 在 [`wave_aware_dd_preflight_v16.json`](records/wave_aware_dd_preflight_v16.json)；旧路线边界见 [`next_wave_aware_dd_after_v15.md`](next_wave_aware_dd_after_v15.md)。
