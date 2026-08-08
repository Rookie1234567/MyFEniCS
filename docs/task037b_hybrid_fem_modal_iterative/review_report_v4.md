# Task037b Review Report V4：双侧 fixed block-PC 的 MPI8 完整数值与物理资格化

## 0. 审阅身份与授权边界

```text
review                         = Task037b Review Report V4
reviewed_branch                = codex/20260807-task37b-hybrid-iterative-development
reviewed_response              = docs/task037b_hybrid_fem_modal_iterative/response_v4.md
reviewed_screen_source         = c7b6aa3ddaac4dbfb9f86aab8f59801330d63a16
screen_disposition             = DOUBLE_APPROXIMATE_200_STEP_PASS_AWAITING_FULL_REVIEW
ordinary_default               = unchanged
merge_to_master                = not_authorized
MPI8_full_solve                = authorized_once
restart_sweep                  = not_authorized
MPI1_or_MPI4_full              = not_authorized
new_PC_family                  = forbidden
PC_parameter_change            = forbidden
LOR_HX_reopen                  = forbidden
production_qualification       = not_authorized
```

本报告接受 Review V3 的全部实现与数值证据。V3 已第一次证明，在 bottom/top 均不保留
直接因子的情况下，冻结的双侧 fixed block-PC 可以稳定降低完整 Hybrid 真残差：

| iteration | Hybrid true residual |
|---:|---:|
| 20 | `0.47312934919147054` |
| 60 | `0.11272071486850113` |
| 100 | `0.022267181511852894` |
| 200 | `0.0015751888272117643` |

V3 的 120--200 步拟合给出 `q_fit=0.9734079564339503`，预测总迭代约 `469`；更保守的
后期收缩估计仍落在约 `470--510` 步范围。因此现在有充分依据运行一次完全冻结的 MPI8
full solve，回答两个尚未回答的问题：

1. 是否能够真实收敛到 `1e-6`，而不是只在 200 步内表现良好；
2. 收敛后的场、模态振幅、衍射通道和 R/T/A 是否与 direct Hybrid 和 Full3D authority 一致。

本轮不是资源优化轮。V3 的 MPI8 process-tree peak 为 `6.296966552734375 GiB`，按既有
`6.0 GiB` 线属于 resource negative；这不影响数值 full qualification。只有完整数值与物理
Gate 通过后，下一轮才可讨论 restart、MPI1 和生命周期压缩。

---

# 1. 已接受且不得重新争论的结论

## 1.1 Exact Hybrid 代数已通过

以下结论继续作为本轮前提：

- direct Hybrid authority 通过；
- exact monolithic Hybrid block operator 通过；
- bottom/top Matrix-free local endcap action 通过；
- exact block-LDU 在 1 个 outer iteration 内恢复 direct Hybrid；
- external Matrix-free DtN action/recovery 通过；
- exact DtN Woodbury identity 通过；
- fixed R5 callback 的线性、确定性、rank、condition、ownership 和生命周期通过；
- 双侧 approximate modal Schur 为 `240×240`、full rank，并与 online fixed actions 一致。

除非本轮出现明确的 exact identity regression，否则不得把 full solve 的失败重新归因于
Hybrid 公式、DtN 符号或 block layout。

## 1.2 Standalone local solver 失败不再作为阻断条件

R5 不能把每个 local RHS 独立解到 `1e-8`，但 V3 已证明同一个 fixed action 作为 block-PC
能够持续降低完整 Hybrid residual。因此本轮禁止再次调用：

```text
HybridLocalDtnWoodburyLocalInverse.solve(...)
```

也禁止在 block PC 内建立 nested local FGMRES/KSP。每次 local callback 必须仍然只执行一次
固定的 Woodbury action。

## 1.3 已关闭路线继续冻结

以下路线不得因本轮 full solve 的任何结果重新开启：

```text
LOR / AMS / HX
p6 -> p4 -> p2
p6 -> p2 auxiliary
full-space ILU
six-slab ASM sweep
new modal coarse / sampled-Schur family
new Krylov family
shift / overlap / ILU-level / mode-count sweep
```

Task37-extra 的 `G2_FAIL`、LOR-HX 高内存和残差放大结论继续有效。

---

# 2. V4 唯一获批的候选

## 2.1 冻结物理与离散身份

```text
wavelength                     = 13.5 nm
polarization                   = S
incident grazing angle         = 10 deg
bottom/top interface           = 10 / 110 nm
endcap FE degree / mesh        = p6 / h10
modal FE degree / mesh         = p6 / h10
requested modes                = M120
modal unknowns                 = 240
external DtN modes/endcap      = 40
assembly backend               = assembly_time_static_condensed
internal propagation model     = full3d_uniform_cg
internal traction model        = scalar_cg_discrete_derivative
MPI                            = 8
initial guess                  = zero
```

不得修改任一物理参数、网格、阶次、模态数、接口位置、极化或角度。

## 2.2 Exact outer operator

外层始终求解同一个 exact monolithic Hybrid 系统：

```math
\mathcal K
=
\begin{bmatrix}
A_b & 0   & T_b\\
0   & A_t & T_t\\
P_b & P_t & G
\end{bmatrix}.
```

其中 bottom/top 的 external DtN 已在 action 中按隐式 Schur 方式精确施加。不得物化全局
Hybrid AIJ matrix，也不得用近似 operator 替代外层 exact action。

## 2.3 双侧 fixed approximate inverse

bottom 和 top 均继续使用 V3 同一 fixed action：

```math
\widetilde A_s^{-1}r
=
B_s^{-1}r
+
W_s K_s^{-1}D_s B_s^{-1}r,
\qquad s\in\{b,t\},
```

其中：

```math
W_s=B_s^{-1}C_s,
```

```math
K_s=H_s-D_sW_s.
```

冻结要求：

```text
B_s^{-1}                    = whole-endcap shifted ILU(0) one apply
bottom/top subdomains       = 1 / 1
overlap                    = 0 / 0
bottom/top direct factors  = 0 / 0
nested local KSP           = false
fixed action per callback  = exactly one
normal equations           = false
```

## 2.4 Modal Schur

必须用与 online PC 完全相同的两侧 fixed actions 构造一次：

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
shape                       = 240 x 240
dtype                       = complex128
rank                        = 240
condition                   = finite and <= 1e8
matrix repeat error         <= 1e-12
LU repeat solve error       <= 1e-12
setup and online callback   = same fixed action identity
```

不得使用 direct local inverse 构造 Schur 后再在线换成 approximate inverse。

## 2.5 外层 KSP

唯一配置为：

```text
outer KSP       = right FGMRES
restart         = 90
rtol            = 1e-6
atol            = 0
max_it          = 700
initial guess   = zero
```

`max_it=700` 只是为 V3 预测的约 470--510 步提供安全余量，不是参数扫描。不得自动改为
800、1000 或 3000；若 700 步未通过，必须停止等待复审。

---

# 3. 实施前 Gate

## 3.1 Source 与 authority

正式运行前必须：

- 工作树 clean；
- 记录完整 source SHA；
- 验证 H1 direct Hybrid authority hash；
- 验证 pinned Full3D authority hash；
- 验证 V3 compact record 与 raw evidence hash；
- ordinary defaults unchanged；
- candidate 只能通过显式 research profile进入。

不得在正式 candidate 进程中重跑 direct Hybrid 或 Full3D authority，也不得让 direct factors
与双侧 approximate factors 同时驻留。

## 3.2 Focused tests

至少覆盖：

1. bottom/top fixed action identity、linearity、determinism；
2. callback 每次只触发一次 Woodbury apply；
3. modal Schur setup 与 online action identity一致；
4. bottom/top direct factor count在 outer-ready 时为 `0/0`；
5. KSP/PC/factor/W/K/Schur 的释放顺序；
6. 释放 approximate PC 后，borrowed exact action与解向量仍可用于 residual和field recovery；
7. external auxiliary recovery；
8. full-FE static-condensation recovery；
9. residual failure时 official physics fail closed。

运行相关 serial tests，并对关键 action/lifecycle tests执行 MPI2 和 MPI4。随后执行：

```text
ruff check
ruff format --check
python -m compileall
git diff --check
```

本阶段不要求 full repository pytest；若未运行，必须在 response 中明确写 `not_run`。

## 3.3 正式运行次数

完成所有轻量实现和测试后，只允许一次正式 MPI8 full numerical run。

若首次 parent/worker 在进入 PDE 求解前因纯粹 launch、path、schema 或 telemetry wiring 问题
停止，可在保留失败证据后做一次不改变数值算法的窄修复；一旦 outer KSP 已开始数值迭代，
不得为了改变结果自动重跑。

---

# 4. 正式运行阶段与对象生命周期

## 4.1 Phase A：构造 exact actions 与 coupling

记录：

```text
cross-section/QEP and mode classification
bottom/top matrix-free action build
external DtN component build
T/P/G coupling build
active/full row inventory
```

## 4.2 Phase B：构造双侧 fixed PC

记录：

```text
bottom/top whole-endcap factor NNZ and rows
factor payload estimate
bottom/top W distributed bytes
bottom/top K/LU bytes and condition
240x240 modal Schur bytes, rank, condition
all setup apply counts
```

outer-ready 时必须断言：

```text
bottom direct factor = 0
top direct factor    = 0
global direct factor = 0
global A/F           = false/false
explicit external C/D= 0/0
```

## 4.3 Phase C：FGMRES full solve

从零初值运行至：

- KSP 正收敛；或
- `max_it=700`；或
- NaN/Inf、内存安全阈值或不可恢复错误。

至少保存以下 iteration checkpoints：

```text
0, 1, 2, 5, 10, 20, 40, 60, 80, 90,
100, 120, 150, 180, 200, 270, 360, 450,
540, 630, 700, and the actual convergence iteration
```

每个 checkpoint 至少记录：

```text
reported residual
global Hybrid true residual
bottom block true residual
top block true residual
modal block true residual
PC apply count
bottom/top fixed-action apply count
```

若现有实现已安全记录每一步 scalar history，可继续保留；不得为了减少文件大小删除最终
explicit true residual。

## 4.4 Phase D：收敛后 residual 与 solution snapshot

在销毁 PC 以前，必须保存：

- 完整 Hybrid solution；
- bottom/top active trace solution；
- 240 个 modal amplitudes；
- final reported/global/bottom/top/modal residual；
- external auxiliary recovery所需数据；
- canonical export所需最小 identity metadata。

随后先完成 final explicit residual audit，再进入对象释放。

## 4.5 Phase E：先释放 solver/PC，再恢复场

为避免 postprocess 与 solver setup对象同时驻留，推荐并授权以下顺序：

1. 销毁 outer KSP 与 restart basis；
2. 销毁 bottom/top PC contexts；
3. 释放两侧 ILU factors；
4. 释放两侧 Woodbury `W/K/LU`；
5. 释放 approximate modal Schur及其 LU；
6. 保留 exact action、static-condensation recovery cache和已复制的最终解；
7. 再进行 bottom/top field recovery、external auxiliary recovery和postprocess。

这一生命周期调整不改变算法。必须通过测试证明释放后 exact action和recovery仍可用。

## 4.6 Phase F：场恢复与本轮自身 official postprocess

按顺序、尽量串行地完成：

```text
bottom full-FE recovery
top full-FE recovery
external DtN auxiliary amplitudes
interface E/H
middle-plane E/H
external diffraction orders
R/T/A
A_volume by material
energy closure
canonical active/full exports
```

candidate online run不加载大型 direct/Full3D field reference。direct Hybrid和Full3D comparison
在候选进程完成并释放后，由独立只读 checker执行，避免污染 candidate online memory authority。

---

# 5. 数值 Gate

## 5.1 线性求解 Gate

全部必须满足：

```text
KSP converged reason              > 0
iterations                        <= 700
reported relative residual        <= 1e-6
Hybrid global true residual       <= 1e-6
bottom block true residual        <= 1e-6
top block true residual           <= 1e-6
modal block true residual         <= 1e-6
all residuals finite              = true
no direct fallback                = true
```

若 KSP reported residual通过但 explicit global true residual未通过，判为数值失败，不得输出
官方物理量。

## 5.2 External auxiliary recovery Gate

对 recovered external modal amplitudes验证：

```math
q
=
H^{-1}(g-Du).
```

要求：

```text
action/recovery identity          <= 1e-10
mode keys                         exact match
beta/polarization/Rayleigh flags  exact match
all amplitudes finite             = true
```

## 5.3 Full-FE recovery Gate

bottom/top 静态凝聚恢复后要求：

```text
full-FE relative residual         <= 1e-6
interior recovery residual        <= 1e-8 or existing stricter frozen Gate
constraint/Floquet identity       pass
canonical vector completeness     pass
```

若当前项目已有更严格的冻结 recovery Gate，沿用原值，不得放宽为本报告数值。

## 5.4 Fail-closed 规则

以下任一项发生时：

```text
KSP reason <= 0 at 700
reported/global/block residual > 1e-6
NaN/Inf
external recovery failure
full-FE recovery failure
```

则：

```text
official R/T/A              = not_run
official diffraction orders = not_run
12+12 comparison            = not_run
```

不得把 200-step screen结果替代 full solve结论。

---

# 6. 与 direct Hybrid 的资格化比较

只有 §5 全部通过后，才使用 H1 的冻结 direct Hybrid authority做只读比较。

## 6.1 代数解比较

要求：

```text
modal amplitude relative L2          <= 1e-5
bottom canonical active relative L2  <= 1e-5
bottom canonical full relative L2    <= 1e-5
top canonical active relative L2     <= 1e-5
top canonical full relative L2       <= 1e-5
```

同时报告最大绝对差和最大相对差所在的 canonical entity/mode key。

## 6.2 场比较

沿用 H1 和 Task36 已冻结的成功案例 Gate：

```text
bottom/top interface E_t pass
bottom/top interface magnetic traction pass
middle-plane E pass
middle-plane H pass
fresh-mesh L2/curl/H(curl) norms pass
```

不得新定义宽松阈值。

## 6.3 通道与物理量

要求：

```text
12/12 significant powers              = pass
12/12 significant complex amplitudes  = pass
R_total/T_total/A_port                 = pass
A_volume_total and material split     = pass
R + T + A_volume closure              = pass
```

全部使用既有 frozen direct-Hybrid comparator tolerance。

---

# 7. 与 Full3D authority 的边界

本案例的 direct Hybrid 已经是相对 Full3D 的成功 anchor。只有 iterative Hybrid 与 direct
Hybrid通过后，才执行既有 Full3D只读 comparator。

分类必须区分：

```text
iterative Hybrid != direct Hybrid
    -> iterative solver / recovery failure

iterative Hybrid == direct Hybrid
but Hybrid != Full3D frozen authority
    -> Hybrid/reference regression or authority mismatch
       not an iterative-solver failure
```

不得在 Task37b 中修复原 Hybrid 在其他入射角下的模型不完备，也不得启动新的角度扫描。

---

# 8. 资源与时间资格化

## 8.1 权威口径

本轮在线权威峰值必须覆盖：

```text
action/coupling build
PC/modal-Schur setup
full FGMRES solve
final true residual
field recovery
own R/T/A and canonical export
object release
```

使用 simultaneous process-tree RSS作为主权威，同时报告 worker RSS/PSS/USS sum和swap。

独立 direct/Full3D comparator进程的峰值单独报告，不与candidate online peak相加。

## 8.2 分类线

数值与资源分开分类：

| 分类 | process-tree peak |
|---|---:|
| MPI8 resource-positive | `<= 6.0 GiB` |
| MPI8 engineering-positive | `<= 5.0 GiB` |
| historical 50% stretch | `<= 3.77 GiB` |

若完整数值和物理通过但峰值为 6.3--7 GiB，必须写：

```text
numerical and physics pass / MPI8 resource negative
```

不得把资源负结果改写成数值失败。

## 8.3 Watchdog

继续使用保守安全边界：

```text
warning threshold      = 10 GiB
termination threshold  = 14 GiB
timeout                = existing qualified value, at least 1800 s
swap                   = 0 required
```

不得为了通过资源 Gate在正式运行后改变采样口径。

## 8.4 对象账本

必须报告至少：

```text
bottom/top static-condensation caches
bottom/top exact action/DtN state
bottom/top ILU factor NNZ and payload
bottom/top W/K/LU
240x240 modal Schur/LU
FGMRES basis estimate and actual lifecycle
field recovery buffers
canonical/postprocess objects
MPI/PETSc/Python residual overhead
```

若RSS峰值发生在release阶段，仍保留process-tree authority，同时明确区分：

- live-object numeric payload；
- allocator/high-water RSS；
- release后对象inventory。

---

# 9. 决策矩阵

## 9.1 完整通过

若线性、recovery、direct Hybrid、Full3D和物理Gate均通过：

```text
DOUBLE_APPROXIMATE_MPI8_FULL_NUMERICAL_AND_PHYSICS_PASS
```

再按资源结果追加：

```text
MPI8_RESOURCE_PASS
```

或：

```text
MPI8_RESOURCE_NEGATIVE
```

完成后停止，等待下一轮决定restart和MPI1；不得自动继续。

## 9.2 700步仍未达到1e-6，但持续下降

若：

```text
reason = DIVERGED_MAX_IT
r700 > 1e-6
last 90 iterations net decrease
no NaN / no rebound
```

分类为：

```text
DOUBLE_APPROXIMATE_FULL_SLOW_CONTRACTION_AWAITING_REVIEW
```

不得自动把max_it提高到1000或3000。

## 9.3 数值收敛但恢复/物理失败

分别分类：

```text
FULL_LINEAR_SOLVE_PASS_EXTERNAL_RECOVERY_FAIL
FULL_LINEAR_SOLVE_PASS_FULL_FE_RECOVERY_FAIL
FULL_LINEAR_SOLVE_PASS_DIRECT_HYBRID_COMPARATOR_FAIL
FULL_LINEAR_SOLVE_PASS_PHYSICS_GATE_FAIL
```

保存解与证据，停止；不得重新调PC。

## 9.4 数值发散或平台

若出现非有限值、持续增长、明显restart平台或700步远高于Gate，分类：

```text
FIXED_ILU0_WOODBURY_BLOCK_PC_FULL_NEGATIVE
```

此时 Task37b 的当前低内存PC家族可以收口；不得自行发明下一候选。

---

# 10. 明确禁止事项

本轮禁止：

```text
restart 90 -> 60/40/20 sweep
MPI1 / MPI4 full
complex64
ILU1/ILU2
shift tuning
overlap tuning
new slab count
M80/M160/M240 scan
new external mode count
LOR/AMS/HX
p2/p4 hierarchy
new modal coarse
strong-trace/exact-trace修复
new angle/polarization
0.7 nm PDE
master merge
```

也禁止在已开始正式数值运行后，以“预测迭代数不准”为理由修改max_it并自动重跑。

---

# 11. 交付物

新增：

```text
docs/task037b_hybrid_fem_modal_iterative/response_v5.md
docs/task037b_hybrid_fem_modal_iterative/outcomes/full_mpi8_qualification.md
benchmarks/cases/101_hybrid_iterative_block_solver/records/task037b_v4_mpi8_full_qualification_v1.json
```

更新：

```text
outcomes/summary.md
outcomes/resource_ledger.md
outcomes/test_summary.md
outcomes/changed_files.md
docs/development_progress.md
```

compact record必须绑定：

- source SHA；
-完整命令身份；
- raw summary/solver/history/stages/timeline/stdout SHA256；
- direct Hybrid authority hash；
- Full3D authority hash；
- final residual和iteration；
- factor/action/lifecycle inventory；
- field/recovery/channel/comparator Gate；
- online和offline comparator资源口径。

不得覆盖 response_v1--v4、review_report_v1--v3或旧raw evidence。

---

# 12. Codex 最终回报格式

完成后只报告：

```text
formal source SHA
KSP reason / iterations
reported/global/bottom/top/modal residuals
external auxiliary recovery result
full-FE recovery result
modal/canonical difference vs direct Hybrid
interface/middle E/H result
12/12 powers and amplitudes
R/T/A/A_volume/closure
Full3D comparator result
online process-tree RSS and worker RSS/PSS/USS
swap and wall time
resource classification
compact record path and SHA
response_v5 commit SHA
```

随后停止等待下一轮审阅。

---

# 13. 直接执行摘要

```text
读取并严格执行 review_report_v4.md。

只运行一个冻结的MPI8 full candidate：p6/h10、S、10°、M120，bottom/top均为一次
fixed whole-endcap ILU(0)+40-mode DtN Woodbury action，exact monolithic Hybrid outer，
right FGMRES restart90、rtol1e-6、max_it700、zero initial。outer-ready时direct factors必须0/0，
禁止nested local KSP和任何参数变化。

先完成focused serial/MPI/lifecycle测试。正式运行只启动一次；数值未通过时official physics
全部fail closed。数值通过后先完成explicit residual，再释放KSP/PC/factors/W/K/modal-Schur，
然后依次完成field recovery、external auxiliary、R/T/A、A_volume、canonical export。
Direct Hybrid和Full3D比较在独立只读checker中完成，不污染online peak。

完成response_v5、full_mpi8_qualification outcome和compact record后停止。不要自动做restart、
MPI1/MPI4、资源调优、LOR/AMS/HX或任何新候选。
```
