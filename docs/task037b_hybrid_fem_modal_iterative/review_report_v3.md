# Task037b Review Report V3：双侧 fixed R5 block-PC 的决定性验证

## 0. 审阅身份与授权边界

```text
review                         = Task037b Review Report V3
reviewed_branch                = codex/20260807-task37b-hybrid-iterative-development
reviewed_response              = docs/task037b_hybrid_fem_modal_iterative/response_v3.md
reviewed_numerical_source      = 5b94060eae3a2ce02dd87e8a8c2075b635711346
ordinary_default               = unchanged
merge_to_master                = not_authorized
new_general_PC_family          = forbidden
LOR_HX_reopen                  = forbidden
bounded_double_screen          = authorized
full_Hybrid_solve              = not_authorized
physics_postprocess            = not_authorized
```

本报告保留 Review V2 的全部历史事实，不改写旧 Gate，也不把 V2-T 的严格负结果重新标成
旧合同下的通过：

```text
V2-B = BOTTOM_APPROXIMATE_SIDE_PASS
V2-T = TOP_APPROXIMATE_SIDE_NEGATIVE
```

但是，V2-T 在第 20 步的 Hybrid true residual 为 `0.3518371324843258`，只比旧阈值
`0.35` 高 `0.0018371324843258`，且 0--20 步持续下降，没有平台、反弹、NaN 或代数异常。
因此 V2 只能证明：

```text
top fixed approximate side did not pass the old strict i20 Gate
```

不能据此证明：

```text
top fixed approximate action has no useful block-level capacity
```

V3 只批准一个真正目标候选：

```text
bottom fixed approximate action
+
top fixed approximate action
+
zero bottom/top direct factors
+
exact monolithic Hybrid outer operator
```

本轮不批准重新开发 local inverse，不批准修改现有 R5 action，也不批准任何新的预条件器
家族。

---

# 1. V2 结果的正式复核

## 1.1 Bottom approximate 是明确正信号

V2-B 使用：

```text
bottom = fixed whole-endcap ILU(0) + 40-mode DtN Woodbury action
top    = exact direct inverse
```

Hybrid global true residual 为：

| iteration | true residual |
|---:|---:|
| 0 | 1.0000000000000000 |
| 5 | 0.6345084421766384 |
| 10 | 0.5049818650746013 |
| 15 | 0.3587981754673419 |
| 20 | 0.2679778432478732 |

最后五步：

```text
0.3344126612
0.3215306247
0.2969113369
0.2843769347
0.2679778432
```

该结果不是 standalone local solve 的 `1e-8` 资格化，而是证明同一个弱 local action 放入
一致的 Hybrid block-LDU 后，外层 FGMRES 能够持续修正其误差。

## 1.2 Top approximate 是 near-pass，不是平台负结果

V2-T 使用：

```text
bottom = exact direct inverse
top    = fixed whole-endcap ILU(0) + 40-mode DtN Woodbury action
```

Hybrid global true residual 为：

| iteration | true residual |
|---:|---:|
| 0 | 1.0000000000000000 |
| 5 | 0.7267537746446435 |
| 10 | 0.6122558424161341 |
| 15 | 0.4506777048234873 |
| 20 | 0.3518371324843258 |

最后五步：

```text
0.4282518461
0.4057858208
0.3849912763
0.3675127908
0.3518371325
```

它严格未通过旧合同的 `r20 < 0.35`，Codex 按 Review V2 停止是正确的。但残差曲线没有显示
失败机制，只显示 top 入射侧比 bottom 侧收缩较慢。

## 1.3 Modal block 已被一致处理

V2-B 与 V2-T 的 modal true residual 从第 1 步起均保持在约 `1e-13--1e-14`。这说明：

- 使用 fixed approximate endcap actions 构造的 240×240 modal Schur 与 online block-PC
  action 一致；
- 当前有限步残差主要来自 approximate endcap blocks；
- 不应再调整 M120、内部传播模型或 modal unknown 数量。

## 1.4 V2 的资源不是双侧 iterative 资源

V2-B/T 各自同时保留：

```text
one approximate ILU factor
+
one exact direct factor
```

所以 `7.973 GiB` 和 `8.532 GiB` 不能预测真正双侧 approximate candidate。V3 是第一次要求：

```text
bottom direct factor = 0
top direct factor    = 0
```

只有本轮的资源结果才可用于判断双侧低内存结构。

---

# 2. 已冻结且不得重新开启的路线

Codex 开始 V3 前必须继续继承 Task37-extra 的权威负结果：

```text
LOR transfer/algebra             = pass only
one-slab LOR-HX retained payload = about 2.913 GiB
LOR-HX 1V contraction            = about 1e6--1e8 amplification
LOR-HX 2V contraction            = about 1e15--1e16 amplification
Task37-extra G2                  = G2_FAIL
Task37-extra G3                  = prohibited
```

同时继续冻结：

- LOR、AMS/HX、real-split AMS；
- p6→p4→p2、p6→p2、p/h multigrid；
- full-space ILU；
- 新 modal coarse、sampled-Schur family；
- strong trace、exact trace、joint-Cauchy compression；
- 新 Schwarz family、overlap/shift/ILU-level sweep；
- M160/M240、角度扫描、偏振扫描和 0.7 nm PDE。

V3 的目的是完成当前 fixed R5 block-PC family 的最后一个关键缺失实验，而不是寻找新算法。

---

# 3. 冻结的双侧候选

## 3.1 Exact outer Hybrid operator

外层始终求解同一个 exact monolithic Hybrid block system：

```math
\mathcal K
=
\begin{bmatrix}
A_b & 0   & T_b\\
0   & A_t & T_t\\
P_b & P_t & G
\end{bmatrix}.
```

其中：

- `A_b/A_t` 是包含 formal Matrix-free external DtN 的 exact static-condensed endcap action；
- `T_b/T_t` 是 internal modal traction 到 endcap 的作用；
- `P_b/P_t` 是 endcap trace 到 modal matching equation 的作用；
- `G` 是冻结 M120 正反向传播块。

禁止以 approximate operator 替换外层 `mathcal K`。

## 3.2 每侧 fixed approximate inverse

每侧只使用一次固定的 whole-endcap ILU(0) + exact 40-mode DtN Woodbury action：

```math
\widetilde A_s^{-1}r
=
B_s^{-1}r
+
W_s K_s^{-1}D_sB_s^{-1}r,
\qquad s\in\{b,t\},
```

其中：

```math
W_s=B_s^{-1}C_s,
```

```math
K_s=H_s-D_sW_s.
```

这里 `B_s^{-1}` 是冻结的 whole-endcap shifted ILU(0) smoother apply。每个 callback 必须：

```text
exactly one base ILU apply
exactly one D action
exactly one 40x40 K solve
exactly one Wq correction
```

禁止在 block PC 内调用：

```text
HybridLocalDtnWoodburyLocalInverse.solve(...)
```

禁止创建 nested local FGMRES/KSP、adaptive tolerance、fallback 或多次 stationary correction。

## 3.3 一致的 approximate modal Schur

必须使用与 online PC 完全相同的两个 fixed actions，一次性构造：

```math
\widetilde S_m
=
G
-
P_b\widetilde A_b^{-1}T_b
-
P_t\widetilde A_t^{-1}T_t.
```

要求：

```text
shape                        = 240 x 240
dtype                        = complex128
rank                         = 240
normal equations             = false
finite                       = true
condition number             <= 1e6
matrix repeat error          <= 1e-12
LU repeat solve error        <= 1e-12
```

不得使用 direct endcap inverse构造 `widetilde S_m` 后在 online 阶段换成 approximate action；
setup 与 online 必须是同一个 action identity。

---

# 4. V3-A：实现与生命周期 Gate

在正式 MPI8 PDE 前，必须通过 focused serial 与 MPI1/2/4 tests。

## 4.1 Operator 与 callback

两侧分别检查：

```text
fixed wrapper vs one direct Woodbury.apply identity <= 1e-12
linearity relative error                            <= 1e-12
determinism relative error                          <= 1e-14
repeat action hash                                  = identical
K rank                                              = 40
K condition                                         <= 1e6
arrays finite                                       = true
nested KSP created                                  = false
local direct factor owned                           = 0
```

## 4.2 Factor inventory

在正式 outer solve ready 时必须满足：

```text
bottom direct factor count  = 0
top direct factor count     = 0
bottom ILU factor count     = 1
top ILU factor count        = 1
global direct factor count  = 0
global Hybrid A materialized= false
global bottom/top F         = false / false
explicit external C/D       = 0 / 0
```

若任一 direct factor 在 outer solve 阶段仍存活，分类为 implementation/lifecycle failure，禁止
把该运行当成双侧低内存候选。

## 4.3 Apply-count 合同

必须记录：

- modal Schur setup期间 bottom/top fixed-action apply count；
- outer PC每一步 bottom/top apply增量；
- outer结束后的总 apply count；
- release后的对象状态。

在线 action count必须符合 block-LDU固定合同，不得出现隐藏 nested solves 或依据 residual 改变
apply次数。若实现仍保持 V2 的 two-local-apply-per-outer-PC语义，应记录并验证每侧 online
增量为 `2 × outer PC apply count`。

---

# 5. V3-B：唯一一次 MPI8 双侧运行

## 5.1 冻结配置

```text
case                         = p6/h10, modal p6/h10
wavelength                   = 13.5 nm
polarization                 = S
incident grazing             = 10 deg
interfaces                   = 10 / 110 nm
requested modes              = M120
candidate modal unknowns     = 240
external modes per endcap    = 40
MPI                          = 8
outer                        = right FGMRES
restart                      = 90
rtol                         = 1e-6
atol                         = 0
max_it                       = 200
initial guess                = zero
bottom inverse               = fixed approximate action
top inverse                  = fixed approximate action
```

不得修改任何数值参数，不得先运行一个调参小算例。

## 5.2 只 setup 一次

禁止将 20、60、100、200 步拆成四次独立启动。action/coupling 和 240×240 modal Schur setup
远比外层迭代昂贵，因此必须在一次正式运行中完成 progressive checkpoints。

## 5.3 必须保存的迭代点

完整 scalar residual history应逐步保存；以下 checkpoint还必须重算 block true residual：

```text
0, 1, 2, 5, 10, 20,
30, 40, 60, 80, 90,
100, 120, 150, 160, 180, 200
```

每个 checkpoint记录：

```text
reported residual
global Hybrid true residual
bottom block true residual
top block true residual
modal block true residual
bottom/top fixed-action apply counters
outer PC apply count
```

第 90 步附近必须审计第一次 restart后是否出现持续反弹；第 180 步附近同理。

---

# 6. Progressive Gate 与提前停止规则

旧 V2 的 `r20 < 0.35` 历史 Gate不修改，但 V3 不再用单个脆弱数值作为最终裁决。V3 同时检查
残差水平和真实下降趋势。

## 6.1 任意阶段的硬停止

出现任一项立即停止：

```text
NaN / Inf
PETSc breakdown reason unrelated to fixed max_it checkpoint
true residual > 1.25 for 5 consecutive iterations
five consecutive sampled increases with no subsequent recovery
callback identity / determinism / factor inventory regression
hidden direct fallback or nested local KSP
swap > 0
watchdog termination threshold reached
```

## 6.2 20-step admission Gate

继续到 60 步必须同时满足：

```text
r20 < 0.65
r20 / r10 < 0.85
geometric contraction q(10:20) < 0.98
all bottom/top/modal residuals finite
```

其中：

```math
q(a:b)
=
\exp\left(
\frac{\log r_b-\log r_a}{b-a}
\right).
```

该 Gate只排除明显无效或早期平台，不要求双侧在 20 步复制某个单侧阈值。

## 6.3 60-step admission Gate

继续到 100 步必须同时满足：

```text
r60 < 0.30
r60 < r40
q(40:60) < 0.99
last 20 iterations net decrease
```

## 6.4 100-step admission Gate

继续到 200 步必须同时满足：

```text
r100 <= 0.12
r100 < r60
last 40 iterations net decrease
no sustained post-restart rebound
```

不得因为 `r100` 略高而自动延长；未通过即在同一正式记录中停止并分类。

## 6.5 200-step主 Gate

正式 200-step pass要求：

```text
r200 <= 0.05
r200 < r160
last 40 iterations net decrease
q(160:200) < 0.997
reported and true residual agree within audit tolerance
predicted total iterations to 1e-6 <= 3000
```

预测只能使用 120--200 步的 true-residual log-linear least-squares slope，并显式报告拟合区间、
斜率、`q_fit` 和预测式。若拟合斜率非负，预测为无穷并判 fail。

---

# 7. 最终分类矩阵

## 7.1 完整通过

若 200-step主 Gate全部通过：

```text
DOUBLE_APPROXIMATE_200_STEP_PASS_AWAITING_FULL_REVIEW
```

随后立即停止。本轮不得自动运行 full solve、场恢复、R/T/A 或 12+12。

## 7.2 慢收缩正信号

若：

```text
0.05 < r200 <= 0.12
last 40 iterations net decrease
q(160:200) < 0.995
all algebra/lifecycle/resource records valid
```

则分类：

```text
DOUBLE_APPROXIMATE_SLOW_CONTRACTION_AWAITING_REVIEW
```

这不是 full pass，也不是 automatic negative。不得自动延长到 500/3000 步。

## 7.3 数值负结果

出现以下任一项：

```text
20/60/100 admission Gate失败
r200 > 0.12
late q >= 0.995 with residual plateau
sustained rebound or divergence
```

则分类：

```text
FIXED_ILU0_WOODBURY_BLOCK_PC_FAMILY_NEGATIVE
```

此时 Task37b 当前低内存 block-PC路线应收口，不得重新开启 LOR/HX、p2/p4 或参数扫描。

## 7.4 实现失败

若 operator/callback/factor/lifecycle Gate失败：

```text
DOUBLE_APPROXIMATE_IMPLEMENTATION_GATE_FAILED
```

只能修复同一实现错误，不得改变算法和阈值；修复是否允许重跑需等待新 review，除非失败明确发生在
worker/PDE启动前且完全没有数值迭代。

---

# 8. 数值与资源必须分开分类

V3 是第一次测量 zero-direct-factor 双侧结构。必须报告：

```text
process-tree RSS peak
worker RSS/PSS/USS simultaneous sums
bottom/top ILU factor NNZ and rows
bottom/top factor CSR payload estimate
bottom/top W distributed bytes
bottom/top K and LU replicated bytes
240x240 modal Schur bytes
FGMRES basis/vector estimate
action/coupling cache
field-recovery objects = not built
```

阶段事件至少包括：

```text
action_coupling_build_started/ready
bottom_approx_setup_started/ready
top_approx_setup_started/ready
modal_schur_build_started/ready
outer_iter_20
outer_iter_60
outer_iter_100
outer_iter_200
release_started/finished
```

资源分类：

| 分类 | MPI8 process-tree peak |
|---|---:|
| numerical result | 不由内存阈值否定 |
| resource-positive | `<= 6.0 GiB` |
| engineering-positive | `<= 5.0 GiB` |
| stretch vs direct-Hybrid 50% | `<= 3.77 GiB` |

如果数值通过但峰值为 6.5 GiB，应写：

```text
numerical pass / MPI8 resource negative
```

不得把正确性和资源资格混写。

---

# 9. 本轮禁止 official physics

无论 200-step结果如何，本轮均禁止：

```text
Hybrid field recovery
R/T/A or A_volume
external diffraction-order postprocess
12/12 significant powers
12/12 complex amplitudes
Full3D physical comparison
restart sweep
MPI4/MPI1 full
```

原因是 V3 只做容量裁决。只有下一版 review 才能授权 full numerical qualification。

---

# 10. 测试与证据要求

## 10.1 Focused tests

至少新增或扩展：

- double fixed-action block-LDU setup；
- bottom/top zero-direct-factor inventory；
- same-action modal Schur identity；
- no nested KSP/no fallback；
- progressive checkpoint Gate；
- early-stop classification；
- numerical/resource classification分离；
- object release后 borrowed exact actions仍可用。

运行 serial，并对 action/packing/modal-Schur核心合同运行 MPI2 和 MPI4。

## 10.2 Formal run count

只允许一次正式 MPI8 double run。不得因数值结果不理想修改参数重跑。

若首次因 source/evidence wiring 在 worker/PDE启动前受控失败：

- 保留首次记录；
- 只允许窄 wiring修复；
- 同一数值配置重新运行一次；
- 在 response中明确区分 infrastructure preflight与唯一 numerical run。

## 10.3 交付文件

新增：

```text
docs/task037b_hybrid_fem_modal_iterative/response_v4.md
benchmarks/cases/101_hybrid_iterative_block_solver/records/task037b_v3_double_block_pc_screen_v1.json
```

更新：

```text
outcomes/double_iterative_funnel.md
outcomes/resource_ledger.md
outcomes/test_summary.md
outcomes/changed_files.md
outcomes/summary.md
docs/development_progress.md
```

compact record必须绑定 raw summary、solver record、memory stages、timeline、stdout和 source SHA。

---

# 11. Codex 直接执行指令

```text
请读取并严格执行：

docs/task037b_hybrid_fem_modal_iterative/review_report_v3.md

保留 Review V2、response_v3 和 TOP_APPROXIMATE_SIDE_NEGATIVE 历史分类，不得改写旧
Gate。本轮只实现并运行一个双侧 fixed approximate block-PC candidate：bottom/top 均使用
一次 whole-endcap ILU(0) + 40-mode DtN Woodbury fixed action；不得调用 local
inverse.solve，不得创建 nested local FGMRES/KSP，outer ready 时 direct factor必须为0/0。

使用同一 fixed actions 一次构造一致的240x240 approximate modal Schur。先完成 focused
serial/MPI identity、linearity、determinism、factor inventory、apply-count和lifecycle Gate。

正式数值只启动一次 MPI8：right FGMRES restart90、max_it200、rtol1e-6、zero initial。
只 setup一次，在同一运行中执行20/60/100/200 progressive Gate，并保存报告规定的全部
checkpoint global/bottom/top/modal true residual与apply counters。任何 Gate失败立即停止，
不得修改参数或重跑。

数值与资源分开分类。即使200-step通过，也不得运行full solve、场、R/T/A、12+12、
restart sweep或MPI1/4。完成compact record、outcomes和response_v4.md后停止等待审阅。

禁止重新开启LOR/AMS/HX、p2/p4、p-multigrid、full-space ILU、new modal coarse、
new Schwarz family、shift/overlap/ILU-level sweep、M/角度/偏振扫描或0.7 nm PDE。
ordinary defaults保持不变，不得merge master。
```

---

# 12. 最终主审判断

```text
V2 bottom fixed action          = clear block-level positive
V2 top fixed action             = old-Gate near-pass with sustained contraction
standalone R5 local solver      = negative, unchanged
Task37-extra LOR/HX             = G2_FAIL, remains closed
double zero-direct-factor case  = scientifically unresolved before V3
V3 authorized work              = one decisive MPI8 double screen only
```

V3 将第一次直接回答：

> Hybrid 分解能否让两个低成本、低精度的 endcap inverse 同时工作，并形成一个具有持续
> 收缩能力、且不保留 bottom/top direct factors 的全局 block preconditioner。
