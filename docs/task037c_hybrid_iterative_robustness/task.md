# Task037c：1° 掠射 S 偏振下 Hybrid 迭代法的方位角鲁棒性、三路一致性与 MPI1 内存下限

## 0. 任务身份

```text
task                              = Task037c
task_kind                         = ROBUSTNESS_AND_SCALABILITY_QUALIFICATION
status                            = READY_AFTER_TASK037B_SELECTIVE_MASTER_INTEGRATION
prepared_on_branch                = codex/20260807-task37b-hybrid-iterative-development
execution_branch                  = codex/20260810-task37c-hybrid-iterative-robustness
execution_base                    = post-Task37b origin/master HEAD
ordinary_default_change           = forbidden
master_write_during_execution     = forbidden
merge_to_master                   = not_authorized_without_final_review
primary_scope                     = accepted Task37b Hybrid iterative solver robustness
wavelength                        = 13.5 nm
polarization                      = S only
grazing_angle                     = 1 deg
polar_angle_from_downward_minus_z = 89 deg
azimuth_set_deg                   = [-5, 0, +5]
formal_PDE_MPI                    = [8, 1]
Full3D_direct_MPI                 = 8
Hybrid_direct_MPI                 = 8
Hybrid_iterative_MPI8             = required
Hybrid_iterative_MPI1             = required after MPI8 qualification
spatial_discretization            = p6 / h10
internal_mode_candidates          = [M120, M160]
automatic_M200                    = forbidden
Task036_failure_cases             = out_of_scope
P_polarization                    = out_of_scope
additional_angle_sweep            = forbidden
new_preconditioner_family         = forbidden
restart_or_ILU_parameter_sweep    = forbidden
0p7nm_PDE                         = out_of_scope
```

Task037c 不再证明 Task37b 方法“能否工作”。Task37b 已经在冻结的 10° 掠射、
方位角 0°、S 偏振、p6/h10、M120、MPI8 案例上完成 tight linear、exact traction、
场恢复、R/T/A、12/12 显著通道、Full3D/direct Hybrid 对比，并把 process-tree RSS
压到 6 GiB 以下。

Task037c 只回答四个问题：

1. 当掠射角进一步减小到 1°，且方位角从 0° 扩展到 -5° 和 +5° 时，
   Task37b 的固定 block-PC 是否仍然收敛；
2. 在每个方位角下，Full3D direct、Hybrid direct 和 Hybrid iterative 是否给出同一物理解；
3. M120 是否已经足够，还是三个方位角需要统一升级到 M160；
4. 同一 Hybrid iterative 在 MPI1 下的数值结果是否保持一致，以及 process-tree 内存是否
   稳定在约 1.5 GiB 的优选区间。

本任务不复用 Task036 的已知失败案例，也不主动寻找失败角度。若本任务新定义的三个案例
中出现 Hybrid 模型偏差，必须就地、如实分类，但不得据此扩展到 Task036 的其他角度、P 偏振
或新的接口方法。

---

# 1. 角度与偏振的冻结定义

## 1.1 角度约定

项目 `SimulationConfig3D` 使用：

- `incident_theta_deg`：相对向下 $-z$ 传播方向的偏转角；
- `incident_phi_deg`：入射波矢在 $x$-$y$ 平面内的方位角。

本任务定义掠射角为相对结构表面的角度 $\gamma$，因此：

```math
\gamma = 1^\circ,
\qquad
\theta = 90^\circ-\gamma = 89^\circ.
```

正式方位角集合冻结为：

```math
\Phi=\{-5^\circ,\ 0^\circ,\ +5^\circ\}.
```

向下传播的单位波矢应满足当前项目约定：

```math
\widehat{\boldsymbol k}
=
\left(
\sin\theta\cos\phi,
\sin\theta\sin\phi,
-\cos\theta
\right).
```

每个正式 record 必须同时保存：

```text
incident_grazing_deg = 1.0
incident_theta_deg   = 89.0
incident_phi_deg     = -5.0 / 0.0 / +5.0
```

不得只保存“1°”而不说明它是 grazing angle，也不得把 `theta=1°` 误当成本任务配置。

## 1.2 S 偏振

S 偏振必须相对于当前入射平面定义，而不是在三个方位角中始终固定成全局 $y$ 向量。
在本任务的角度约定下，理想 S 偏振方向可写为：

```math
\widehat{\boldsymbol e}_s
=
\left(
-\sin\phi,
\cos\phi,
0
\right).
```

正式 preflight 必须验证：

```math
\widehat{\boldsymbol k}\cdot\widehat{\boldsymbol e}_s=0,
\qquad
\lVert\widehat{\boldsymbol e}_s\rVert_2=1.
```

还必须记录实际配置生成的入射波矢、S 偏振向量、Floquet $k_x/k_y$ 和左右/前后周期相位，
并与上述解析定义一致到 `1e-13` 以内。

P 偏振不运行，也不得为了处理非零方位角而退回 `custom` 固定全局偏振。

---

# 2. 冻结几何、材料与离散

除角度外，三个案例共享 Task37b 的成功模型：

```text
stage case                    = stage4_block_grating
geometry                      = fixed rectangular block grating
period x / y                  = 50 / 25 nm
z min / max                   = -10 / 130 nm
grating height                = 120 nm
grating width x / y           = 17 / 25 nm
bottom / top Hybrid interface = 10 / 110 nm
wavelength                    = 13.5 nm
material                      = existing silicon complex index authority
mesh                          = boundary-fitted conforming hexahedron
Nedelec degree                = p6
mesh target                   = h10 nm
assembly backend              = assembly_time_static_condensed
internal propagation          = full3d_uniform_cg
internal traction             = scalar_cg_discrete_derivative
external boundary             = Fourier-DtN
```

不得在不同方位角之间修改网格、材料、接口位置、PML、传播模型、traction model、
静态凝聚策略或求解精度。

三个方位角必须由同一 clean source SHA、同一容器 digest 和同一工作站环境生成。
正式重型作业必须串行排队；禁止同时运行两个 PDE job。

---

# 3. 开始执行前的 Git 与交接 Gate

Task037c 只能在 Task37b 选择性合入完成后开始。Codex 必须确认：

```text
current branch = codex/20260810-task37c-hybrid-iterative-robustness
upstream       = origin/codex/20260810-task37c-hybrid-iterative-robustness
local HEAD     = origin/master HEAD at Task37c branch creation
remote HEAD    = local HEAD
ahead/behind   = 0/0 before first Task37c commit
worktree       = clean
```

必须验证本任务书已经由 Task37b selective integration 进入 `master`，并随新分支继承：

```text
docs/task037c_hybrid_iterative_robustness/task.md
```

若 Task37b selective merge、full pytest、M10 integration anchor 或 `origin/master` 推送尚未完成，
Task37c 不得开始编码或运行 PDE。

Task37c 的第一项提交只能是：

```text
docs(task037c): record inherited master and robustness plan
```

该提交创建最小 outcomes 骨架和 inherited audit，不得夹带 solver 修改。

---

# 4. 开始前必须读取的权威文件

Codex 必须完整读取：

```text
docs/repository_work_principles.md
docs/markdown_rendering_standard.md
docs/task_retrospective_standard.md
docs/iterative_solver_ports.md

docs/task037b_hybrid_fem_modal_iterative/task.md
docs/task037b_hybrid_fem_modal_iterative/review_report_v7.md
docs/task037b_hybrid_fem_modal_iterative/response_v8.md
docs/task037b_hybrid_fem_modal_iterative/outcomes/summary.md
docs/task037b_hybrid_fem_modal_iterative/outcomes/full_mpi8_qualification.md
docs/task037b_hybrid_fem_modal_iterative/outcomes/resource_ledger.md
docs/task037b_hybrid_fem_modal_iterative/outcomes/test_summary.md

docs/task035c_hybrid_channel_memory_closure/outcomes/summary.md
docs/task032_hybrid_fem_modal_direct_baseline/outcomes/summary.md
benchmarks/cases/080_hybrid_fem_modal_direct_baseline/expected/gates.json
```

还必须读取 Task37b 选择性合入后 `master` 中实际存在的最终模块和 runner。
不得假设 Task37b 研究分支的所有历史文件都已进入 `master`，也不得重新复制一套平行实现。

继承审计必须明确记录：

- Task37b selective master commits；
- 最终成功的显式 opt-in runner 路径；
- ordinary direct Hybrid 默认路径仍未改变；
- M10 成功 anchor 的 source、RSS、残差、R/T/A 和 checker hash；
- 哪些 H5/V1/V2/V3 历史研究代码没有进入 master；
- Task37c formal PDE 只允许 MPI8 和 MPI1；MPI2/MPI4 仅可用于轻量测试。

---

# 5. 三种正式求解方法

## 5.1 Full3D direct

每个方位角必须先建立一个 MPI8 Full3D direct authority：

```text
solver                  = direct MUMPS authority
assembly                = assembly_time_static_condensed
p/h                     = p6/h10
MPI                     = 8
true residual           <= 1e-9
reference field export  = required
```

每个 Full3D authority 必须导出：

```text
R/T/A and A_volume
energy closure
external q and complete diffraction-order table
sampled E/H planes at z = [10, 30, 60, 90, 110] nm
sample grid = 40 x 20 unless inherited authority contract requires the same existing grid
canonical active/full vectors when supported by the integrated master path
process-tree RSS/PSS/USS, swap, setup/solve/postprocess wall
```

三个 Full3D direct 作业的正式顺序为：

```text
phi = 0 deg
phi = -5 deg
phi = +5 deg
```

先跑 0° 是为了验证 1° 掠射下的基本执行链；它不是把 0° 当作其他方位角的数值替代。

## 5.2 Hybrid direct

每个方位角都必须运行：

```text
Hybrid direct M120
Hybrid direct M160
```

共同设置：

```text
p6/h10
interfaces 10/110 nm
same external DtN mode keys as the corresponding Full3D authority
same propagation/traction model
MPI8
true residual <= 1e-9
```

不得自动运行 M200，也不得根据单个方位角单独调 modal filter、beta branch、near-degenerate
阈值或 propagation model。

## 5.3 Hybrid iterative

正式 Hybrid iterative 必须复用 Task37b 已合入的成功结构：

```text
exact monolithic Hybrid matrix-free operator
+ right FGMRES
+ action-consistent block-LDU
+ bottom whole-endcap shifted ILU(0) one apply
+ top whole-endcap shifted ILU(0) one apply
+ bottom/top Matrix-free DtN Woodbury
+ approximate modal Schur
+ multimetric true-residual convergence
+ M10 lifecycle / streaming path
```

冻结参数：

```text
restart                         = 90
qualification threshold         = 5e-9 for reported/global/bottom/top/modal
exact traction gate             = 1e-8
initial guess                   = zero
nested local KSP                = false
bottom/top direct factor        = 0/0
ILU level                       = 0
overlap                         = 0/0
ordinary default                = unchanged
```

由于 1° 掠射可能比 Task37b 的 10° anchor 更难，本任务统一使用：

```text
max_it = 1600
```

该上限对三个方位角、MPI8 和 MPI1 完全相同，不得按案例修改。达到 1600 仍未通过时，
必须记录 controlled numerical negative，不得自动增加上限。

---

# 6. External DtN 模态集合与 Woodbury 维度

不得把 Task37b anchor 的“每端 40 个外部模态”硬编码到 Task37c。
每个方位角必须由同一个 `auto_propagating` / 项目正式枚举器生成物理所需的 external mode keys，
并在三种方法之间冻结一致：

```text
Full3D direct mode keys
= Hybrid direct mode keys
= Hybrid iterative mode keys
```

每个 case 必须记录：

```text
mode count per endcap
propagating / near-cutoff / evanescent classification
(m,n,polarization,side) keys
beta branch and Rayleigh flags
Woodbury K shape/rank/condition
W distributed bytes
```

若三个方位角的 mode count 不同，这是物理枚举结果，不属于参数修改；但每个方位角内部三种方法
必须完全一致。

若 accepted Task37b core 仍隐含固定 40-mode 假设，必须先做一个窄的动态维度修复和 focused test；
不得通过裁剪 mode set 来维持 40。

---

# 7. M 收敛与统一 M 的冻结逻辑

## 7.1 每个方位角的 M120/M160 比较

每个方位角先比较 direct Hybrid M120 与 M160。沿用项目已有 final gates：

```text
max absolute R/T/A total delta              <= 1e-6
max significant-order relative delta        <= 1e-4
interface projection residual               <= 1e-8
selected middle-plane E/H relative L2       <= inherited Task032 final limits
mode keys and external order identities     exact match
```

## 7.2 与 Full3D 的比较

对 M120 和 M160 分别比较 Full3D authority。正式 Hybrid-vs-Full3D Gate沿用：

```text
R/T/A and A_volume absolute delta            <= 1e-5
energy closure absolute value                <= 1e-5
max significant-order relative delta         <= 1e-4
sampled interface E relative L2              <= 5e-3
sampled interface H relative L2              <= 1e-2
max selected middle-plane E/H relative L2    <= 5e-3
all compared mode keys                       exact match
```

## 7.3 统一 M 的选择

Task37c 必须为三个方位角选择一个共同的 `M_robust`：

```text
若三个方位角的 M120 均通过 M120-vs-M160 和 Full3D Gate：
    M_robust = 120

否则，若三个方位角的 M160 均通过 Full3D Gate：
    M_robust = 160

否则：
    M_robust = not established
    classification = HYBRID_MODEL_ROBUSTNESS_NOT_ESTABLISHED_BY_M160
```

不得为 -5°、0°、+5° 分别选择不同的正式 M，也不得自动进入 M200。

若某一方位角的 M160 direct Hybrid 仍未通过 Full3D，但其 direct linear/physics自身有效，
允许在该方位角运行一次 M160 Hybrid iterative 作为**solver-vs-direct diagnostic**；该结果只能回答
迭代器是否求解了 direct Hybrid 方程，不能计入三路一致性通过。

---

# 8. 正式执行漏斗

## R0：继承与参数审计

创建：

```text
docs/task037c_hybrid_iterative_robustness/outcomes/inherited_master_audit.md
docs/task037c_hybrid_iterative_robustness/outcomes/angle_and_polarization_contract.md
```

完成：

- branch/upstream/clean/master SHA；
- 角度转换与 S 偏振解析审计；
- phi=-5/0/+5 的 $k_x/k_y$、Floquet phase 和 polarization audit；
- accepted Task37b runner/core inventory；
- dynamic external-mode support audit；
- ordinary defaults unchanged。

R0 失败时不得运行 PDE。

## R1：轻量实现与测试

只允许实现：

- Task37c 专用 robustness runner/watchdog 或对最终 Task37b opt-in runner 的最小参数扩展；
- `incident_phi_deg` 和 1° grazing 的安全传递；
- dynamic external mode identity；
- 三路 comparator；
- M120/M160 selection logic；
- MPI1/MPI8 resource ledger。

禁止实现新 PC、改变 Task37b fixed action、增加 P 偏振或展开通用角度扫描框架。

## R2：MPI8 Full3D direct authorities

按 0°、-5°、+5° 顺序运行三个 Full3D direct。
每个 case 独立 fail-closed；一个 case失败不允许伪造 authority，但可继续另两个独立 case，
前提是失败不是共享代码/环境错误。

## R3：MPI8 Hybrid direct M120/M160

每个 phi 依次运行 M120、M160，并完成：

```text
M120 vs M160
M120 vs Full3D
M160 vs Full3D
```

然后按第 7 节选择统一 `M_robust`。

## R4：MPI8 Hybrid iterative

使用统一 `M_robust` 对三个方位角运行 Hybrid iterative。
正式顺序：

```text
phi = 0 deg
phi = -5 deg
phi = +5 deg
```

不得根据 0° 结果调节 ±5° 的 PC、restart、max_it、shift、overlap或 tolerance。

## R5：三路一致性与 ±5° 镜像诊断

对每个 phi 完成三路比较：

```text
Full3D direct vs Hybrid direct
Full3D direct vs Hybrid iterative
Hybrid direct vs Hybrid iterative
```

固定几何在 $y$ 方向铺满一个周期；若代码级几何/材料审计确认 $y\mapsto-y$ 镜像对称，
则增加 ±5° 诊断：

```text
R/T/A totals under phi -> -phi
power channels under (m,n) -> (m,-n)
```

复振幅只有在明确实现并测试 S 偏振基底的相位/符号映射后才可做镜像比较；不得直接逐项相等。
镜像诊断不能替代各自对 Full3D 的正式比较。

## R6：MPI1 Hybrid iterative

只有对应 phi 的 MPI8 Hybrid iterative 数值和自身物理通过后，才运行 MPI1。
三个方位角均使用同一个 `M_robust` 和完全相同的 solver参数。

MPI1 正式顺序仍为：

```text
phi = 0 deg
phi = -5 deg
phi = +5 deg
```

每个 MPI1 结果必须与对应 MPI8 Hybrid iterative比较，不得只看自身 residual。

## R7：最终汇总

完成：

```text
docs/task037c_hybrid_iterative_robustness/outcomes/summary.md
docs/task037c_hybrid_iterative_robustness/outcomes/test_summary.md
docs/task037c_hybrid_iterative_robustness/outcomes/three_way_comparison.md
docs/task037c_hybrid_iterative_robustness/outcomes/m_convergence.md
docs/task037c_hybrid_iterative_robustness/outcomes/mpi1_mpi8_resource_and_time.md
docs/task037c_hybrid_iterative_robustness/response_v1.md
```

然后停止等待审阅，不得自行 merge master或扩展新角度。

---

# 9. 每种方法的数值 Gate

## 9.1 Full3D direct

```text
KSP/direct solve success              = true
true relative residual                <= 1e-9
official result                       = true
external mode keys finite/unique      = true
R/T/A/A_volume finite                 = true
energy closure                        <= 1e-5
reference field export                = true
swap                                  = 0
```

## 9.2 Hybrid direct

```text
true relative residual                <= 1e-9
bottom/top local residual             <= inherited direct gates
interface E projection                <= 1e-8
exact traction dual                   <= 1e-8
external q identity                   <= 1e-10
field/R/T/A/orders finite             = true
swap                                  = 0
```

## 9.3 Hybrid iterative

```text
KSP converged reason                  > 0
iterations                            <= 1600
reported residual                     <= 5e-9
global true residual                  <= 5e-9
bottom true residual                  <= 5e-9
top true residual                     <= 5e-9
modal true residual                   <= 5e-9
exact traction dual bottom/top        <= 1e-8
external q identity bottom/top        <= 1e-10
recovery / own physics / canonical    = pass
no direct fallback                    = true
bottom/top direct factor              = 0/0
nested local KSP                      = false
swap                                  = 0
```

数值通过与资源通过必须分别分类。

---

# 10. 三路一致性 Gate

## 10.1 Hybrid direct 与 Full3D

沿用第 7.2 节 Gate。

## 10.2 Hybrid iterative 与 Full3D

至少满足：

```text
R/T/A/A_volume absolute delta          <= 1e-5
significant-order relative delta       <= 1e-4
all external mode keys                 exact match
sampled interface E relative L2        <= 5e-3
sampled interface H relative L2        <= 1e-2
middle-plane E/H relative L2           <= 5e-3
energy closure                         <= 1e-5
```

## 10.3 Hybrid iterative 与 Hybrid direct

由于二者求解同一 Hybrid方程，采用更严格 Gate：

```text
R/T/A/A_volume absolute delta          <= 1e-6
external q relative difference         <= 1e-6
significant-order relative delta       <= 1e-4
canonical active/full relative L2      <= 1e-5
selected interface/middle E/H          <= 5e-3
modal magnitude relative L2            <= 1e-6
```

独立 QEP 下 raw modal coefficient逐项比较仍不是 gauge-invariant正式 Gate；必须保留原始诊断值，
但以 gauge-invariant physical E/H、modal magnitude和通道结果作为资格权威。

## 10.4 三路通过定义

一个方位角只有在以下均通过时才记为：

```text
THREE_WAY_FULL3D_HYBRID_DIRECT_ITERATIVE_PASS
```

- Full3D direct authority通过；
- `M_robust` Hybrid direct通过；
- `M_robust` Hybrid iterative通过；
- 三组 pairwise comparison全部通过。

Task37c robustness overall pass要求三个方位角全部三路通过。

---

# 11. MPI8 资源与用时对比

每个 phi 的三种方法必须在独立进程、同一工作站、无并行重型作业条件下记录：

```text
process-tree RSS peak
worker RSS/PSS/USS simultaneous sum
swap
assembly/action build wall
QEP/modal basis wall
factor/PC setup wall
linear solve wall
recovery/postprocess wall
total wall
matrix/factor NNZ or matrix-free inventory
```

正式对比表至少包含：

| phi | Full3D direct RSS/time | Hybrid direct RSS/time | Hybrid iterative RSS/time | iterative iterations |
|---:|---:|---:|---:|---:|

Hybrid iterative MPI8资源分类：

```text
preferred resource pass     = process-tree RSS <= 6.0 GiB
numerical pass/resource fail= allowed and must be reported separately
```

不得为了维持 6 GiB 而修改 restart、M、ILU、field sample或资格阈值。

---

# 12. MPI1 极限内存测量

MPI1 的目标是测量单 rank下 accepted Hybrid iterative 的最小 MPI复制开销，不是重新优化算法。
保持：

```text
same M_robust
same restart90
same 5e-9 multimetric Gate
same M10 lifecycle
same field and authority outputs
same external mode set for that phi
```

每个 phi 的 MPI1 必须与 MPI8比较：

```text
R/T/A/A_volume
external orders and significant channels
canonical active/full vectors
selected interface/middle E/H
iteration count
wall time
```

MPI1 资源分类：

```text
preferred memory floor      = process-tree RSS <= 1.5 GiB
engineering memory target   = process-tree RSS <= 2.0 GiB
hard safety stop            = process-tree RSS >= 6.0 GiB
swap                        = 0
```

若 MPI1 数值通过但峰值高于 1.5或2.0 GiB，必须写成资源未达优选/工程目标，不能写成求解失败。

“约 1.5 GiB 是否一直成立”只有在 -5°、0°、+5° 三个 MPI1 正式作业都完成后才可回答。
不得用单个 phi 外推全部方位角。

---

# 13. 失败分类与停止规则

## 13.1 Full3D authority失败

```text
FULL3D_AUTHORITY_NOT_ESTABLISHED_AT_PHI_X
```

该 phi 的三路资格化停止；不得用 Hybrid direct代替 Full3D authority。

## 13.2 M160仍不满足Full3D

```text
HYBRID_MODEL_ROBUSTNESS_NOT_ESTABLISHED_BY_M160_AT_PHI_X
```

不得自动M200。允许一次 M160 iterative-vs-direct诊断，但不能记为三路通过。

## 13.3 Iterative不收敛或物理不通过

```text
HYBRID_ITERATIVE_ROBUSTNESS_FAIL_AT_PHI_X
```

禁止按方位角调整PC、shift、overlap、restart或max_it。

## 13.4 MPI1数值失败

```text
MPI1_NUMERICAL_IDENTITY_NOT_ESTABLISHED_AT_PHI_X
```

不得用MPI8结果代替。

## 13.5 共享实现/环境故障

若一个 case暴露共享 parser、angle conversion、mode-key或ABI错误，停止后续重型作业，
先做窄修复和focused tests；修复不得改变物理或算法。已启动数值迭代的正式 case不得为改变结果
自动重跑，除非新审阅明确批准。

---

# 14. 测试与静态检查

正式 PDE前至少完成：

- theta/grazing转换测试；
- phi=-5/0/+5波矢与S偏振测试；
- Floquet phase与MPI一致性测试；
- dynamic external-mode key和Woodbury rank测试；
- Full3D/Hybrid direct/iterative三路record schema测试；
- M120/M160 selection测试；
- MPI1/MPI8 comparator测试；
- ordinary defaults unchanged测试；
- fail-closed official output测试。

轻量测试可使用 MPI1/2/4；正式 PDE只允许 MPI8和MPI1。

静态检查：

```text
ruff check
ruff format --check
python -m compileall
git diff --check
```

所有正式结果完成后运行一次无 deselect的 full repository pytest。
若 full pytest未完成或有failure，必须如实记录，不得声称全仓通过，也不得自行合入master。

---

# 15. Artifact与Git边界

建议建立：

```text
benchmarks/cases/102_hybrid_iterative_robustness/
```

只有首个完整三路 case通过后才允许提交 compact records。
重型 raw artifacts、field arrays、timelines和stdout保存在 ignored目录：

```text
benchmarks/artifacts/task037c/
```

tracked compact record必须绑定 raw artifact路径和SHA256，但不得把重型数组提交Git。

所有 Task37c实现、测试、records、outcomes和response只提交到：

```text
codex/20260810-task37c-hybrid-iterative-robustness
```

未经最终审阅，不得merge或push master。

---

# 16. 最终交付表

最终 response必须至少给出以下总表。

## 16.1 MPI8三路一致性

| phi | M120/M160结论 | M_robust | Full3D direct | Hybrid direct | Hybrid iterative | three-way | iterative RSS | iterative time |
|---:|---|---:|---|---|---|---|---:|---:|

## 16.2 三种方法资源与时间

| phi | method | MPI | iterations | total wall | setup wall | solve wall | post wall | process-tree RSS | swap |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|

## 16.3 MPI1内存下限

| phi | MPI8 RSS | MPI1 RSS | MPI1/MPI8 result identity | preferred <=1.5 GiB | engineering <=2.0 GiB | MPI1 wall |
|---:|---:|---:|---|---|---|---:|

## 16.4 最终分类

仅当三个方位角全部满足三路一致性、Hybrid iterative数值/物理通过，且MPI1结果与MPI8一致时，
可以分类为：

```text
TASK037C_S_POL_1DEG_AZIMUTH_ROBUSTNESS_PASS
```

MPI1是否达到1.5/2.0 GiB另行附加资源分类，不改变数值鲁棒性结论。

完成上述文件后停止等待审阅；不得自动扩展 P偏振、更多方位角、其他掠射角、M200、0.7nm或新PC。
