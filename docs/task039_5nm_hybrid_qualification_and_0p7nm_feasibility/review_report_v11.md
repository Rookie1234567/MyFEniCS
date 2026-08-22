# Task039 Review Report V11：双端 exact-response 消元、固定案例压缩与 response-based side PC

## 0. 审阅决定

```text
review                                  = Task039 Review Report V11
reviewed_branch                         = codex/20260812-task39-5nm-hybrid-0p7nm-feasibility
reviewed_head                           = b4d4759e3cff670c2cc420146a5130fe957ad79b
extension_status                        = AUTHORIZED_WITH_STRICT_SCOPE
master_write_or_merge                   = forbidden
new_branch_or_worktree                  = forbidden
ordinary_default_change                 = forbidden
primary_method_line                     = exact response packet full Hybrid + response-based factor-free side research
physical_case                           = 5 nm / 1° grazing / phi=0° / S
formal_spatial_discretization           = p6/h4
formal_Hybrid_M                         = 480 per direction
formal_MPI                              = 8
matched_Hybrid_direct_reference_GiB     = 93.377006531
current_best_full_iterative_GiB         = 80.025856018
current_best_full_saving_percent        = 14.298113646
bottom_response_producer_peak_GiB       = 50.7548675537
bottom_response_payload_bytes           = 2034244800
minimum_full_workflow_objective         = strictly below 93.377006531 GiB
next_full_workflow_objective            = strictly below 80.025856018 GiB
useful_target_GiB                       = 74.701605225
major_target_GiB                        = 56.026203919
half_memory_target_GiB                  = 46.688503266
J1_inner_FGMRES_family                  = closed at 16-step stagnation
V9_original_SN2_SGS                     = closed
raw_load_vector_Petrov_family           = closed
current_random_holdout_compression      = generalization negative, not global noncompressibility proof
Hybrid_direct_rerun                     = forbidden
V7_exact_side_full_rerun                = forbidden
bottom_full_response_producer_rerun     = forbidden unless packet integrity fails and a new review authorizes it
Full3D_new_heavy_run                    = forbidden
full_0p7nm_PDE                          = forbidden
third_BLR_profile                       = forbidden
generic_ILU_or_budget_scan              = forbidden
FB8_or_more_defect_corrections          = forbidden
heavy_jobs_concurrent                   = forbidden
default_heavy_timeout_seconds           = 21600
conditional_consumer_timeout_seconds    = 28800 total, one time only
response_required                       = response_v12.md
```

本 Review 接受 V10 的主要正负结果：

1. 三个真实 two-layer supernode 的 conventional 与 factor-only solve 均 finite，局部 residual 约为
   `1e-12` 到 `5e-11`。V9 的历史 `Inf/NaN` 未在 V10 取证路径中复现，根因仍为
   `not_established`，不得宣称已发现通用 MUMPS 或 factor-only bug。
2. 修复后的固定 `SN2-J` 比 single-layer `J1` 更强，但最坏 bare-`F` residual 仍为
   `17.0879610640`，不能作为 side inverse。
3. `J1`-preconditioned full-side FGMRES 在16步后的五项 true residual 仍为
   `0.9971` 到 `0.9990`，几乎停滞；继续增加预算没有当前证据支持。
4. bottom exact-response producer 已准确生成960个 modal response 和一个 zero validation column：
   最大 true residual `1.52248376596e-10`、payload `2034244800 B`、峰值
   `50.7548675537 GiB`、factor 生命周期 `1 -> 0`、swap为0。
5. 当前950-column training / 10-column holdout压缩的执行、资源和生命周期通过，但在 rank512
   仍有索引 `0/1/480/481` 四列约 `0.9673` 的投影误差。该结果证明当前 holdout泛化失败，
   **不等价于证明全部960个已知 response无法压缩**。

V11 的第一优先级不是再设计普通 side smoother，而是把已经准确的 response packet用于完整
Hybrid block elimination：bottom producer、top producer和无 factor consumer分属独立进程，任何时刻
最多保留一个 side factor。这样先建立5 nm下更低内存的 exact Hybrid authority，再用正确的
solution-response 数据研究 factor-free coarse correction。

---

## 1. V10 最终审阅

### 1.1 统一结果

| 路径 | 范围 | 数值/物理 | process-tree RSS | 当前角色 |
|---|---|---|---:|---|
| h4 Hybrid direct | 完整 workflow | own Gate pass | `93.377006531 GiB` | matched authority |
| V7 exact-side iterative | 完整 workflow | 1 outer；residual、recovery、R/T/A、E/H、canonical、channels pass | `80.025856018 GiB` | 当前最好完整低内存结果 |
| V10 factor integrity | bottom component | 三组 conventional/factor-only residual pass | `41.0968208313 GiB` | research forensic pass |
| V10 SN2-J | bottom component | finite/repeat/linearity pass；worst `r_F=17.0879610640` | `27.0815505981 GiB` | advancement positive / side-solver fail |
| V10 J1-inner-FGMRES | bottom component | 16步后 worst true residual `0.9989849199` | `22.0071983337 GiB` | numerical stagnation，family closed |
| V10 full bottom response producer | bottom component | 960 modal response residual pass | `50.7548675537 GiB` | exact response authority |
| V10 response compression | bottom component | execution/resource pass；holdout generalization fail | `15.4776763916 GiB` | research compression negative |

V10 没有产生 top、both-side、完整 Hybrid consumer、recovery或新的 R/T/A，因此当前完整 workflow
最好结果仍是：

```text
Hybrid direct               = 93.377006531 GiB
V7 exact-side Hybrid        = 80.025856018 GiB
measured saving             = 14.298113646%
```

正式 saving tier 保持：

| saving | full-workflow upper bound | 当前状态 |
|---:|---:|---|
| 0% | `93.377006531 GiB` | direct reference |
| 5% | `88.708156204 GiB` | reached |
| 20% | `74.701605225 GiB` | not reached |
| 30% | `65.363904572 GiB` | not reached |
| 40% | `56.026203919 GiB` | not reached |
| 50% | `46.688503266 GiB` | not reached |
| 60% | `37.350802612 GiB` | not reached |

### 1.2 J1-inner-FGMRES 的关闭边界

五个 mandatory RHS 在16步后的 true residual 为：

```text
modal+   = 0.9971014671
modal-   = 0.9981152471
external = 0.9979895526
random0  = 0.9989785112
random1  = 0.9989849199
```

V11 禁止：

```text
J1-FGMRES 32/64/128
增加 restart 或普通 tolerance 扫描
把 J1/F1/FB 换名称后原样重跑
```

这不否定所有 Krylov side solver，只关闭当前 single-layer J1 family。

### 1.3 当前 response compression 负结果的正确解释

现有压缩使用950个训练列和10个 holdout列。最大 rank 的 training optimal error 为
`3.8908212468e-12`，说明训练矩阵本身近似低秩；但 holdout `0/1/480/481` 仍约
`0.9673`，其余六个 holdout在最大 rank 已达到约 `1e-10` 到 `1e-12`。

只能使用：

```text
CURRENT_HOLDOUT_GENERALIZATION_FAIL
```

不得扩大为：

```text
FULL_960_RESPONSE_MATRIX_NOT_COMPRESSIBLE
ALL_RESPONSE_BASED_PRECONDITIONING_IMPOSSIBLE
```

V11 必须分开回答：

```text
A. 固定 h4/M480 案例的全部已知960列能压到多少 rank；
B. basis 对未见模态、不同 M、不同波长是否具有泛化能力。
```

A 可以用于当前固定案例的存储压缩；B 才关系到未来 production/generalization。

---

## 2. V11 的核心数学身份

对每个 side `s in {bottom, top}`，以实际代码 block identity 为权威，概念上写成：

```math
A_s u_s + B_s a = f_s,
```

其中：

- `A_s` 是包含 local FE 与 external DtN 的完整 side operator；
- `B_s` 把960维 modal amplitudes映射为 side source；
- `f_s` 是该 side 的实际物理 RHS；
- `a` 是960维 modal unknown；
- `u_s` 是 side condensed unknown。

定义：

```math
X_s=A_s^{-1}B_s,
\qquad
u_s^0=A_s^{-1}f_s.
```

则：

```math
u_s=u_s^0-X_s a.
```

代回 modal equation 后形成 reduced modal Schur。上式的正负号只是统一记号；正式实现不得根据本文
手写符号，而必须从实际 assembled block action、V7 exact-side authority和 sampled column identity
中推导并验证。任何 sign/order/normalization 不一致都必须在离线 algebra audit 停止，不能通过翻转符号
凑结果。

V11 packet consumer只需要当前固定方程中实际出现的：

```text
960 个 modal response columns
每侧实际 physical RHS response
一个独立 zero-map validation
```

它不需要在 consumer 中保存 side factor，也不要求 response basis能够表示任意未知 RHS。

---

## 3. 总执行顺序

```text
V11-0  inherited audit，docs-only
V11-1  既有 bottom packet 的 block/sign/order/algebra 离线资格
V11-2  bottom 全960列 closed-set compression 与 mode-metadata audit
V11-3  top 16-modal pilot + physical RHS + zero validation
V11-4  条件 top full response producer
V11-5  factor-free two-side packet consumer + 条件完整 recovery/physics
V11-6  条件 response-interpolatory bottom side PC
V11-7  条件 structured/generalizable compression audit
V11-8  Pareto、0.7 nm implications、selective merge 与 response_v12.md
```

重型作业严格串行。`V11-1/V11-2` 只读取现有 packet、tracked代码与轻量 authority，不启动新的
PDE/factor。`V11-3` 通过后才允许 `V11-4`；`V11-4` 通过后才允许完整 two-side consumer。

---

## 4. 资源、时间与数值 Gate

### 4.1 Exact response producer

每个 side producer是独立进程：

```text
process-tree peak                    <= 60 GiB
exact side factor at ready           = 1
exact side factor after exit         = 0
global Hybrid direct factor          = 0
producer and any consumer overlap    = false
per-side packet payload              <= 16 GiB
swap                                 = 0
QEP                                  = 0
```

已有 bottom producer authority：

```text
peak    = 50.7548675537 GiB
wall    = 4390.176657 s
payload = 2034244800 B
residual max = 1.52248376596e-10
```

V11 禁止重跑完整 bottom producer。若 V11-1 发现 packet hash、coverage或代数 identity损坏，则停止并
等待新 review；不得自动重算960列。

### 4.2 Factor-free packet consumer

```text
bottom exact factor                  = 0
top exact factor                     = 0
global direct factor                 = 0
QEP                                  = 0
selected-mode packet                 = reuse only
response packet access               = owner-row mmap / streamed batches
consumer absolute hard stop          = 79 GiB
swap                                 = 0
```

`79 GiB` 是防止 consumer超过当前 `80.025856018 GiB`完整最好点的 hard line，不是新的成功阈值。
完整 workflow按所有串行进程的最大峰值分类：

```math
B_{workflow}
=
\max(B_{bottom\ producer},B_{top\ producer},B_{consumer}).
```

不得把三个进程峰值相加，也不得只报告 consumer RSS。

### 4.3 Full Hybrid numerical/physics Gate

沿用 V7 exact-side 与 matched direct 的正式 Gate：

```text
reported/global/bottom/top/modal true residual <= 5e-9
all finite                                  = true
projection bottom/top/combined              <= 1e-8
exact traction bottom/top                   <= 1e-8
R/T/A/A_volume delta vs matched direct      <= 1e-6
energy closure                              <= inherited formal limit
selected E relative L2                      <= 5e-3
selected H relative L2                      <= 1e-2
canonical active/full relative L2           <= 1e-5
power-weighted channel error                <= 1e-4
external keys/order identity                = exact
normal flux / diffraction orders / powers   = inherited Gate pass
swap                                        = 0
```

packet路线目标是同一 Hybrid 方程的 exact elimination，因此新增 algebra Gate：

```text
sampled response equation residual          <= 1e-9
bottom/top modal-Schur contribution error    <= 5e-9
modal amplitude relative difference          <= 5e-9
condensed trace solution relative difference <= 5e-9
```

### 4.4 时间 Gate

每个 heavy producer/consumer默认6小时。只有已经进入 two-side consumer 的 modal solve或
recovery/postprocess，且：

```text
RSS < 79 GiB
swap = 0
linear residual Gate 已通过或持续下降
无 NaN/Inf
预计剩余时间 <= 2 h
```

才允许一次延长到总计8小时。producer setup/factor未完成时不得自动延长。

必须分别报告：

```text
cold serial wall = bottom producer + top producer + consumer
reuse wall       = consumer only（两个 packet 已存在）
```

二者不得混写。

---

## 5. V11-0：继承审计

第一项提交必须是 docs-only：

```text
docs(task039): audit v11 exact response full hybrid baseline
```

创建：

```text
outcomes/review_v11_inherited_audit.md
```

至少记录：

```text
branch / HEAD / upstream / ahead-behind / worktree
review_report_v11.md identity
V7 exact-side full record/hash
V10 bottom response compact record/hash
bottom producer source SHA = dbc5e9bfdf9ad0520881caa168c7a27316d50f10
bottom packet manifest SHA256 = 1f4e8acaf278bde0d0d14a2a096335049ee988cdbc1b406bca4197918ff64a0e
selected-mode packet identity/hash
h4 input / physical_model_sha256 / resolved-config identity
MemAvailable / swap / disk / ABI / MPI / threads
93.377006531 GiB direct baseline
80.025856018 GiB current full iterative baseline
50.7548675537 GiB bottom producer peak
J1-inner-FGMRES closed
V9 SGS、generic ILU/BLR、Full3D、0.7 nm PDE均冻结
```

不得夹带 Python 修改或启动 heavy。

---

## 6. V11-1：bottom packet algebra 资格

### 6.1 目的

在生成 top packet 前，先证明已有 bottom packet不仅每列 residual正确，而且列身份、符号、顺序和
Hybrid block elimination完全一致。

### 6.2 必须验证

```text
960 modal column indices 完整且唯一
每列与实际 B_bottom column 的 mode key / sign branch / normalization exact match
packet owner-row coverage / shape / dtype / hash exact
actual bottom physical RHS norm 与身份
existing zero column 是否可合法复用为 bottom physical response
```

若实际 bottom physical RHS 非零，V11只允许后续单独生成一个 bottom physical-response column；不得重跑
完整960列 producer。该条件生产者仍受60 GiB、6小时、factor `1->0`和swap0约束。

### 6.3 Algebra checks

使用实际 code block，不手写符号：

1. 重新作用 `A_bottom` 到至少冻结的10个 sampled packet columns，检查 source identity与 residual；
2. 以 streamed batch计算 bottom modal-Schur contribution；
3. 与 V7 exact-side modal-Schur authority或同 source sampled reconstruction比较；
4. 使用 V7 authority 的 modal amplitude，重构 bottom condensed trace solution；
5. 与 V7 exact-side bottom trace/selected reconstruction比较。

Gate：

```text
column/source identity                      = exact
sampled equation residual                   <= 1e-9
sampled modal-Schur contribution relative   <= 5e-9
sampled modal-amplitude action relative     <= 5e-9
bottom trace reconstruction relative        <= 5e-9
all packet references released              = true
factor/QEP/PDE                              = 0/0/not_run
```

任一失败：停止 top producer和full consumer，保留诊断，不自动修改 signs/order或重算 bottom packet。

---

## 7. V11-2：固定案例全列压缩与 metadata audit

### 7.1 Closed-set compression

只读取现有 bottom packet的960个非零 modal response columns。不得留出 holdout；本阶段回答当前固定
h4/M480方程本身可压缩到多少 rank。

只运行一次：

```text
owner-row TSQR
-> one small-R SVD / rank-revealing decomposition
-> all-960-column reconstruction audit
```

禁止 normal equations或 Gram-matrix eigensolve。必须报告：

```text
960 singular values
numerical rank
达到 max per-column error <=1e-6 / 1e-8 / 1e-10 的最小 rank
对应 Frobenius error
全部960列 max/median/p95 error
每个 branch/group 的 max error
compressed payload estimate
consumer RSS / wall
```

正式分类分别为：

```text
FIXED_CASE_CLOSED_SET_COMPRESSION_PASS_1E6 / FAIL
FIXED_CASE_CLOSED_SET_COMPRESSION_PASS_1E8 / FAIL
FIXED_CASE_CLOSED_SET_COMPRESSION_PASS_1E10 / FAIL
```

即使 closed-set通过，也不表示对未见 modes或0.7 nm泛化通过；首次完整 Hybrid formal必须使用未压缩
packet，避免把压缩误差和 packet algebra混在一起。

### 7.2 Mode metadata audit

对960列记录：

```text
positive/negative branch
mode index / partner identity
propagating or evanescent classification
attenuation/|beta| bucket
selected group/family identity
是否位于 branch start/end 或 singleton group
```

重点解释旧 holdout `0/1/480/481` 的身份，但不得仅因为它们失败就人工塞回训练集并宣布泛化通过。
metadata 不可取得的字段写 `not_available`。

---

## 8. V11-3：top response pilot

### 8.1 固定 pilot schedule

运行一个 top producer pilot，包含16个 modal indices：

```text
0, 1, 2, 239, 240, 267, 478, 479,
480, 481, 482, 719, 720, 746, 958, 959
```

另外必须包含：

```text
actual top physical RHS response
independent zero-map validation
```

manifest必须将 modal、physical和zero三类列分开命名，不允许把非零 physical RHS误标成 zero validation。

### 8.2 Pilot Gate

```text
all modal/physical responses finite         = true
per-column true residual                    <= 1e-9
zero output norm                            <= 1e-13
projected full wall                         <= 21600 s
projected full payload                      <= 16 GiB
producer peak                               <= 60 GiB
factor lifecycle                            = 1 -> 0
swap                                        = 0
owner-row packet coverage/hash              = exact
```

pilot失败则不运行 full top producer。

---

## 9. V11-4：top full producer

pilot通过后，只允许一次 full top producer。payload至少包含：

```text
960 modal response columns
1 actual top physical RHS response
1 independent zero validation
```

若 top physical RHS数学上为零，manifest仍必须明确记录其 source norm、degenerate身份和与zero validation
是否共享payload；不得静默省略。

Gate沿用 §4.1 和 §8.2。必须生成：

```text
owner-row sharded packet
manifest / hashes / column schedule
每列 residual compact history
factor lifecycle markers
process-tree RSS/swap/wall
```

full producer通过后进程退出，确认 factor为0，再启动 consumer。

---

## 10. V11-5：无 side factor 的双 packet consumer

### 10.1 Consumer 结构

consumer不得重新运行 QEP、不得建立 bottom/top exact factor、不得建立 global augmented direct factor。
它必须：

```text
读取 selected-mode packet
读取 bottom/top response packets
按固定 batch=32 流式形成 bottom/top modal-Schur contributions
加入实际 modal block 与 physical RHS correction
求解 960x960 modal system
用 owner-row local packet流式组合 bottom/top condensed trace solution
释放 response packets
执行既有 recovery / postprocess / checker
```

允许对960x960 modal system使用 dense LU；该对象不是当前5 nm主要内存项。必须报告其 shape、rank、condition、
LU bytes和wall。

### 10.2 Conditional continuation

同一次 formal consumer先完成：

```text
modal solve
bottom/top/global/modal true residual
packet algebra comparison
resource checkpoint
```

只有线性与资源 Gate通过，才继续 recovery/postprocess；否则在该进程受控停止，不另起一遍相同 solve。

### 10.3 Full workflow classification

完整 workflow峰值使用：

```text
max(existing bottom producer peak,
    measured top producer peak,
    measured consumer peak)
```

正式分类：

| 分类 | workflow peak |
|---|---:|
| no improvement | `>=80.025856018 GiB` |
| new full-Hybrid low-memory best | `<80.025856018 GiB` |
| useful 20% saving | `<=74.701605225 GiB` |
| strong 30% saving | `<=65.363904572 GiB` |
| major 40% saving | `<=56.026203919 GiB` |
| half-memory strategic pass | `<=46.688503266 GiB` |

在不优化既有 bottom producer的前提下，该 exact-packet workflow的阶段性峰值下界受
`50.7548675537 GiB`约束；若 top和consumer均不超过它，则相对 direct的派生 saving约为
`45.645%`。这是条件预测，不是预先通过值，也说明当前 exact-factor producer路线即使成功，仍可能略高于
50%战略线。

正式成功措辞必须为：

```text
5NM_FIXED_CASE_EXACT_RESPONSE_PACKET_FULL_HYBRID_PASS
```

不得写成：

```text
0P7NM_PRODUCTION_PASS
FACTOR_FREE_PRODUCER_PASS
ARBITRARY_3D_PASS
```

---

## 11. V11-6：response-interpolatory bottom side PC

该 lane 只有在 V11-1 bottom packet algebra通过后才允许；它可与 top producer顺序执行，但不得并发 heavy。
目标是用真正的 solution response，而不是 raw load vectors构造 factor-free coarse correction。

### 11.1 固定候选

设 source matrix为 `B`、exact response为 `X=A_side^{-1}B`。使用稳定的 owner-row TSQR / small-R
rank-revealing solve构造 source projection，不允许 normal equations。固定候选为：

```text
M_resp r = X c + M_J1 (r - B c)
```

其中 `c` 是 `r` 在 source column space中的稳定最小二乘系数，`M_J1` 只处理补空间。不得修改成多种
random basis、drop tolerance或rank扫描。

若 source matrix rank-deficient，使用一次 rank-revealing截断并报告实际 rank/tolerance；不得通过普通
正则化参数扫描凑结果。

### 11.2 Component Gate

```text
modal source interpolation error             <= 1e-8
A_side * M_resp(B_j) residual                <= 1e-8 for sampled/all modal columns
zero-map                                     <= 1e-13
finite/repeat/linearity                      <= 1e-10
five frozen RHS mandatory residual           <= 1e-2
modal+/modal-/external residual              <= 1e-3
construction peak                            <= 45 GiB
retained peak                                <= 30 GiB
exact/global factor                          = 0/0
swap                                         = 0
```

若固定 action未通过随机补空间，但 modal/external三项通过，分类只能是：

```text
MODAL_SUBSPACE_RESPONSE_CORRECTION_PASS_RANDOM_COMPLEMENT_FAIL
```

不得直接进入完整 Hybrid。只有全部五项通过，才允许一次 bottom full-side FGMRES
`4/8/16/条件32`验证；该 FGMRES使用 `M_resp`，不再运行J1-alone。

---

## 12. V11-7：结构化泛化压缩（条件）

只有 V11-2 closed-set compression至少达到 `1e-8`，且 mode metadata完整到足以定义 strata时才执行。

strata至少按以下字段构造：

```text
positive / negative branch
propagating / evanescent
attenuation bucket
mode group/family
branch edge / singleton status
```

规则：

1. singleton 或 branch-edge modes可以列为 `exact-keep`，但必须由metadata规则自动产生；
2. 每个非单例 stratum必须同时含training和holdout；
3. 不得把某一整个难模态家族全部移入training；
4. 只运行一个 deterministic stratified split；
5. 报告 exact-keep payload、compressed remainder rank和逐stratum holdout error。

分类必须分开：

```text
FIXED_CASE_CLOSED_SET_COMPRESSION_*
STRATIFIED_UNSEEN_MODE_GENERALIZATION_*
```

即使结构化泛化通过，也仍只是固定5 nm/h4/M480 mode family，不能外推到0.7 nm。

---

## 13. 0.7 nm 含义

V11 exact-response workflow即使完整通过，也仍使用每侧一个临时 exact sparse factor producer。因此它的角色是：

```text
5 nm低内存 exact authority
solution-response oracle
response-based coarse-space数据源
packet/consumer架构资格
```

而不是0.7 nm production solver。

0.7 nm前仍需解决：

```text
exact producer factor的可扩展替代
response payload O(N_side M)增长
external channel K 的 matrix-free/iterative处理
modal Schur随M增长
QEP与selected mode扩展
未知模式/不同波长的response泛化
```

V11必须更新2 TB含义，但只能使用：

```text
measured 5 nm packet/factor/RSS
明确公式推导
带假设的predicted envelope
```

不得运行完整0.7 nm PDE，也不得把当前2 GB packet按简单比例直接称为0.7 nm内存上界。

---

## 14. 测试与证据要求

### 14.1 Focused tests

至少覆盖：

```text
bottom packet source/sign/order identity
owner-row packet hash/coverage/release
physical RHS 与 zero validation 分离
top pilot/full manifest contract
streamed modal-Schur contribution
two-side consumer no-factor inventory
conditional continuation before recovery
closed-set TSQR/SVD all-column reconstruction
response-interpolatory source projection
```

新 owner-row与consumer helper需在 serial、MPI2、MPI4 tiny fixtures通过。真实 h4正式运行仍为MPI8。

### 14.2 Static/documentation Gate

```text
Ruff check
Ruff format --check
compileall for changed Python
focused pytest
MPI tiny fixtures
check_benchmarks.py --no-write
compact JSON parse/hash consistency
Markdown relative links
fenced math / table column consistency
git diff --check
```

repository full pytest / CI若未运行，必须写 `not_run`，不得声称zero failures。

### 14.3 必需 outcomes

```text
outcomes/review_v11_inherited_audit.md
outcomes/v11_bottom_packet_algebra.md
outcomes/v11_closed_set_response_compression.md
outcomes/v11_top_response_packet.md
outcomes/v11_two_side_packet_full_result.md
outcomes/v11_response_interpolatory_pc.md
outcomes/v11_structured_response_generalization.md
outcomes/v11_memory_residual_time_pareto.md
outcomes/v11_0p7nm_implications.md
outcomes/summary.md
outcomes/test_summary.md
docs/development_progress.md
response_v12.md
```

未运行的条件文件仍可创建，但必须明确写 `not_run` 与阻断原因。

### 14.4 Compact records

至少为以下正式阶段建立hash-bound compact record：

```text
bottom packet algebra
closed-set compression
top pilot/full producer
two-side factor-free consumer/full formal
response-interpolatory PC（若运行）
structured generalization（若运行）
```

raw matrices、response shards、JSONL、field arrays和factor不得提交Git。

---

## 15. 提交计划

建议按以下职责提交，不要求机械一一对应，但不得把多个heavy结果混入同一实现提交：

```text
docs(task039): audit v11 exact response full hybrid baseline
feat(task039): qualify response packet block algebra
feat(task039): add top response packet producer
feat(task039): add factor-free two-side packet consumer
feat(task039): add fixed-case response compression audit
feat(task039): add response-interpolatory side correction
record(task039): add v11 packet workflow evidence
docs(task039): close v11 exact response and compression results
```

历史 implementation failures和负结果不得删除、覆盖或改写。

---

## 16. Stop conditions

立即停止依赖 lane并完成证据收口，若发生：

```text
bottom packet source/sign/order identity fail
top pilot residual/resource/hash fail
top full producer >60 GiB、swap>0或超时
consumer出现任一side/global direct factor
consumer peak >=79 GiB
linear residual Gate fail
packet algebra与V7 authority不一致
closed-set all-column compression执行失败
response-interpolatory action产生NaN/Inf或source interpolation fail
```

不得通过以下方式绕过：

```text
重跑既有 bottom 960-column producer
静默改变M480、网格、材料或角度
删除困难 modal columns
放宽 residual/physics Gate
把component RSS写成full-workflow saving
把closed-set reconstruction写成unseen-mode generalization
```

---

## 17. response_v12.md 必答问题

1. bottom packet 的960列是否与实际 modal source block在key、sign、order和normalization上 exact match？
2. bottom packet 是否能重构 V7 modal-Schur contribution和bottom trace solution？误差是多少？
3. 全960列 closed-set compression 在 `1e-6/1e-8/1e-10` 下最小 rank分别是多少？
4. 旧 holdout `0/1/480/481` 的 mode metadata身份是什么？
5. top pilot/full producer的residual、RSS、wall、payload和factor生命周期是多少？
6. top physical RHS是否非零，如何保存与验证？
7. 双packet consumer是否完全不含side/global factor和QEP？
8. 完整 five residual、R/T/A、E/H、canonical、channels是否通过？
9. 完整 workflow peak、cold wall和reuse wall分别是多少？
10. 是否刷新80.026 GiB，是否达到20%、30%、40%或50% saving tier？
11. response-interpolatory PC是否准确映射modal source subspace，随机补空间是否通过？
12. fixed-case compression与unseen-mode generalization各自的正式分类是什么？
13. 哪些组件可selective merge，哪些research-only，哪些不得promotion？
14. 这些结果对2 TB下0.7 nm的哪个 blocker有帮助，哪些 blocker仍未解决？
15. top、full、structured compression、response PC和0.7 nm中哪些是pass、fail、not_run？

完成全部已授权且未被stop condition阻断的阶段后，Codex必须更新 `response_v12.md`，提交并推送同一分支，
然后停止等待审阅。未经新 review，不得继续新的solver family、完整0.7 nm PDE或master合并。
