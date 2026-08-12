# Task039：5 nm Full3D/Hybrid 资格化、Hybrid iterative 最小内存与 0.7 nm 可行性审计

## 0. 任务身份

```text
task                                   = Task039
task_kind                              = WAVELENGTH_ROBUSTNESS_REFERENCE_QUALIFICATION_AND_CAPACITY_AUDIT
status                                 = READY_FOR_CODEX_EXECUTION
base_master_sha                        = 438caf150439343ee7c4c58ad7e02a3da812a23c
working_branch                         = codex/20260812-task39-5nm-hybrid-0p7nm-feasibility
remote_upstream                        = origin/codex/20260812-task39-5nm-hybrid-0p7nm-feasibility
ordinary_default_change                = forbidden
master_write                           = forbidden
merge_to_master                        = not_authorized_without_final_review
public_input_entry                     = python scripts/run_case.py <one-case.dat>
one_dat_one_run                        = required
primary_wavelength_nm                  = 5.0
primary_grazing_angle_deg              = 10.0
primary_azimuth_deg                    = 0.0
primary_polarization                   = S
primary_geometry                       = current 50 x 25 x 140 nm target grating
primary_discretization                 = p6 / h10 fixed-grid stress anchor
accuracy_grid_candidates_nm            = [10.0, 7.5, 5.0]
full3d_direct_primary_mpi              = 8
full3d_iterative_primary_mpi           = 8
hybrid_direct_primary_mpi              = 8
hybrid_iterative_fast_mpi              = 8
hybrid_iterative_minimum_memory_mpi    = 1
internal_mode_candidates               = [120, 240, 480, 960]
automatic_modes_above_960              = forbidden
full_0p7nm_PDE                         = forbidden
neural_or_learned_factor_work          = forbidden
new_preconditioner_family              = forbidden
P_polarization                         = out_of_scope
azimuth_sweep                          = out_of_scope
Task036_failure_reopening              = out_of_scope
campaign_layer                         = out_of_scope
```

Task039 的主目标不是立刻计算完整 0.7 nm 模型，而是用 5 nm 作为决定性中间波长，分离并测量：

1. Full3D iterative 在更高波数下能否收敛，并能否在同一网格上复现 Full3D direct；
2. Hybrid direct 在 5 nm 下需要多少内部模态，且是否仍然逼近 Full3D；
3. Hybrid iterative 是否能以低内存准确求解已经 M 收敛的 Hybrid 方程；
4. 当网格从 h10 收紧到 h7.5、h5 时，FE、factor、external DtN/Woodbury、内部模态和 Krylov
   分别如何增长；
5. 依据 5 nm 实测结果，当前架构在 0.7 nm、256 GiB 工作站预算下是可继续、需先重构，
   还是明确 no-go。

本任务冻结神经网络 factor 替代路线。不得读取旧 neural branch 后继续训练、移植模型、
创建 learned PC 或以神经网络作为任何正式候选。

---

# 1. 开始执行前的 Git 与继承 Gate

Codex 开始时必须确认：

```text
current branch = codex/20260812-task39-5nm-hybrid-0p7nm-feasibility
upstream       = origin/codex/20260812-task39-5nm-hybrid-0p7nm-feasibility
base ancestor  = 438caf150439343ee7c4c58ad7e02a3da812a23c
local HEAD     = remote HEAD before first local commit
ahead/behind   = 0/0
worktree       = clean
```

必须读取并继承当前 `master` 中实际存在的文件，不得依据旧研究分支猜测：

```text
AGENTS.md
docs/repository_work_principles.md
docs/markdown_rendering_standard.md
docs/task_retrospective_standard.md

docs/task037_static_condensed_full3d_iterative/outcomes/summary.md
docs/task037b_hybrid_fem_modal_iterative/response_v8.md
docs/task037c_hybrid_iterative_robustness/response_v3.md
docs/task037c_hybrid_iterative_robustness/outcomes/summary.md
docs/task037c_hybrid_iterative_robustness/outcomes/mpi1_mpi8_resource_and_time.md

docs/task038_input_driven_configuration/task.md
docs/task038_input_driven_configuration/response_v1.md
docs/task038_input_driven_configuration/outcomes/summary.md
input/README.md
```

还必须审计当前 `master` 中以下实际实现：

```text
scripts/run_case.py
src/io/
src/runners/task038_full3d_direct.py
src/runners/task038_hybrid_direct.py
src/runners/task038_hybrid_iterative.py
Full3D iterative accepted Task037 entry/profile
Hybrid direct accepted entry/profile
Hybrid iterative Task037b/37c accepted entry/profile
external DtN dynamic mode enumerator
memory watchdog and process-tree telemetry
```

Task039 第一项提交必须是 docs-only：

```text
docs(task039): audit inherited 5nm-capable numerical paths
```

该提交创建：

```text
docs/task039_5nm_hybrid_qualification_and_0p7nm_feasibility/outcomes/inherited_master_audit.md
docs/task039_5nm_hybrid_qualification_and_0p7nm_feasibility/outcomes/material_and_case_contract.md
docs/task039_5nm_hybrid_qualification_and_0p7nm_feasibility/outcomes/resource_budget.md
```

不得夹带 Python 修改或启动正式 PDE。

---

# 2. 5 nm 材料合同

用户提供的 5 nm 光学常数为：

```text
Wavelength (nm) = 5.0
Delta           = 0.00603145547
Beta            = 0.00435380777
```

沿用项目当前 X-ray/EUV 复折射率约定：

```math
n = 1-\delta+i\beta.
```

因此：

```math
n_{5\mathrm{nm}}
=
0.99396854453
+
0.00435380777i.
```

由代码派生的相对介电常数应为：

```math
\varepsilon_{r,5\mathrm{nm}}
=
n_{5\mathrm{nm}}^2
=
0.9879545118729887
+
0.00865509594462061i.
```

正式 `.dat` 中只允许输入折射率，不得同时再输入一套独立的介电常数：

```toml
[materials]
n_air = [1.0, 0.0]
n_substrate = [0.99396854453, 0.00435380777]
n_grating = [0.99396854453, 0.00435380777]
```

本任务冻结：

```text
substrate material = same 5 nm material
grating material   = same 5 nm material
n_air              = 1 + 0i
mu_r               = 1 + 0i
```

解析后 `resolved_config.json` 必须同时记录：

```text
input delta/beta provenance
resolved complex n
derived epsilon_r
wavelength
material labels
```

若代码内部时间约定或材料损耗符号与上述正虚部合同不一致，必须在 R0 停止并审计，
不得通过翻转符号来凑能量闭合。

---

# 3. 冻结几何、入射与基本物理

## 3.1 几何

除波长和材料外，第一阶段沿用已验证目标结构：

```text
period x / y                  = 50 / 25 nm
z min / max                   = -10 / 130 nm
interface z                   = 0 nm
air height                    = 130 nm
substrate thickness           = 10 nm
grating width x / y           = 17 / 25 nm
grating height                = 120 nm
Hybrid bottom / top interface = 10 / 110 nm
geometry kind                 = rectangular_block_grating
```

不得在 Task039 内同时改变光栅高度、宽度、周期、接口位置或材料分区。

## 3.2 入射

主案例固定为：

```text
grazing angle = 10 deg
internal theta from downward -z = 80 deg
azimuth = 0 deg
polarization = S
incident amplitude = 1
```

主案例只选 10°、phi=0°，目的是隔离波长变化。不得在本任务自动增加 1°、phi=±5°、
P 偏振或角度扫描。

如 5 nm 主案例全部通过，后续是否增加 1° 压力点由新的 review 决定，不属于本任务自动范围。

## 3.3 边界与背景

```text
x/y boundary              = dual Floquet
vertical boundary         = Fourier-DtN
DtN order policy          = auto_propagating
DtN assembly              = accepted matrix-free / auxiliary path
PML                       = false
scattering background     = layered
```

不得把 13.5 nm 的 40-mode external set 写死到 5 nm。Full3D direct、Full3D iterative、
Hybrid direct 和 Hybrid iterative 在同一物理案例中必须使用完全一致的 external mode keys。

---

# 4. 输入驱动合同

所有正式运行必须通过 Task038 的单一 `.dat` 入口：

```bash
python scripts/run_case.py input/official/task039/<case>.dat
```

禁止通过命令行追加：

```text
--method
--mpi-size
--requested-modes
--wavelength
--material
--mesh-target
--restart
--max-it
```

Task039 必须建立：

```text
input/official/task039/
```

一个 `.dat` 只表示一次明确计算。至少应生成以下输入，具体名称可以保持同一语义：

```text
5nm_g10_phi0_p6h10_full3d_direct_mpi8.dat
5nm_g10_phi0_p6h10_full3d_iterative_mpi8.dat
5nm_g10_phi0_p6h10_hybrid_direct_M120_mpi8.dat
5nm_g10_phi0_p6h10_hybrid_direct_M240_mpi8.dat
5nm_g10_phi0_p6h10_hybrid_direct_M480_mpi8.dat
5nm_g10_phi0_p6h10_hybrid_direct_M960_mpi8.dat          # conditional
5nm_g10_phi0_p6h10_hybrid_iterative_Mrobust_mpi8.dat
5nm_g10_phi0_p6h10_hybrid_iterative_Mrobust_mpi1.dat

5nm_g10_phi0_p6h7p5_full3d_iterative_mpi8.dat           # conditional
5nm_g10_phi0_p6h7p5_hybrid_direct_M*.dat                # conditional
5nm_g10_phi0_p6h7p5_hybrid_iterative_M*.dat             # conditional
5nm_g10_phi0_p6h5_full3d_iterative_mpi8.dat              # conditional
5nm_g10_phi0_p6h5_hybrid_direct_M*.dat                   # conditional
5nm_g10_phi0_p6h5_hybrid_iterative_M*.dat                # conditional
```

`Mrobust` 必须在实际选择后写成数字，不能把字符串 `Mrobust` 作为正式输入值。

每个结果目录必须保留 Task038 provenance：

```text
input_original.dat
resolved_config.json
run_manifest.json
input_sha256.txt
physical_model_sha256.txt
source_sha.txt
run_summary.json
```

三种方法比较前必须验证：

```text
physical_model_sha256 exact match
external mode keys exact match
mesh identity / p-h identity exact match
material identity exact match
```

---

# 5. 任务结构：固定网格鲁棒性与真实网格规模必须分开

Task039 分为两大阶段：

```text
Phase A = p6/h10 fixed-grid wavelength and solver stress test
Phase B = 5 nm p6/h7.5 and p6/h5 accuracy/resource scaling
```

Phase A 的身份是：

```text
algorithmic stress anchor
same approximate FE scale as current p6/h10
not a final 5 nm discretization-accuracy claim
```

因为：

```math
h/\lambda = 10/5 = 2.
```

Phase B 才负责 5 nm 网格收敛与 accuracy-qualified 结论。

不得把 Phase A 的 R/T/A 直接写成最终 5 nm 物理答案。

---

# 6. Phase A：p6/h10 Full3D reference 链

## A0：轻量 preflight

在任何 PDE 前运行：

- `.dat` validate-only 与 dry-run；
- 5 nm 材料和派生 epsilon测试；
- 10° grazing / theta=80° / S 偏振测试；
- dynamic external mode enumeration；
- Full3D direct/iterative/Hybrid 三路 mode-key identity；
- h10 mesh/DoF/active-row estimate；
- 资源 watchdog 配置；
- no-swap 和 source-clean preflight。

A0 必须输出：

```text
exact external spatial-order count
exact external S/P channel count per endcap
Rayleigh / near-cutoff count
estimated Full3D rows / NNZ
estimated active condensed rows
estimated Hybrid endcap rows
estimated Woodbury W and K bytes
```

估计值不能冒充实测值。

## A1：Full3D direct MPI8 authority

运行：

```text
wavelength = 5 nm
p6/h10
Full3D direct
MPI8
assembly-time static condensed
```

Gate：

```text
direct solve success                = true
true relative residual              <= 1e-9
R/T/A/A_volume finite               = true
energy closure absolute value       <= 1e-5
all propagating mode keys unique    = true
selected E/H export                 = true
process-tree telemetry complete     = true
swap                                = 0
```

必须记录：

```text
mesh cells / full DoF / active rows / auxiliary rows
matrix NNZ and factor telemetry
analysis/factor/solve/postprocess wall
process-tree RSS/PSS/USS
all orders and dynamic significant-channel set
selected E/H at z = 10, 30, 60, 90, 110 nm
canonical vectors when capability exists
```

若 A1 因资源或 direct factorization失败：

```text
classification = 5NM_P6H10_FULL3D_DIRECT_AUTHORITY_NOT_ESTABLISHED
```

允许继续 Full3D iterative 和 Hybrid capacity diagnostics，但所有 Hybrid-vs-Full3D
准确性结论必须标为 `authority_incomplete`，不得提升为三路通过。

## A2：Full3D iterative MPI8

使用 Task037 已接受的 Full3D iterative结构，不重新扫描候选：

```text
exact condensed operator
matrix-free DtN
accepted M3a physical slab decomposition
accepted coarse correction
right FGMRES
same p6/h10 mesh
same dynamic external mode keys
MPI8
```

冻结：

```text
ordinary accepted M3a parameters unchanged
rtol = 1e-6
restart = inherited accepted value
max_it = 4000
zero initial guess
```

不得调 slab数、overlap、coarse维数、ILU level、shift或 Krylov family。

Gate：

```text
KSP reason                         > 0
iterations                         <= 4000
reported / condensed / full-FE     <= 1e-6
official R/T/A                     = true
energy closure                     <= 1e-5
swap                               = 0
```

若 A1 authority存在，A2 还必须通过同方程比较：

```text
R/T/A/A_volume absolute delta      <= 1e-6
max significant-power rel delta    <= 1e-4
max significant-amplitude rel delta<= 1e-4
selected E/H relative L2           <= 1e-5
canonical relative L2              <= 1e-5
all mode keys                      exact match
```

若 A2 不收敛：

```text
classification = 5NM_FULL3D_ITERATIVE_NUMERICAL_NEGATIVE_AT_P6H10
```

停止 Phase B 的 Full3D iterative reference 扩展，但仍可运行 Hybrid direct容量诊断，
不得把 Hybrid结果称为 Full3D-validated。

---

# 7. Phase A：Hybrid direct 的 M 收敛

## 7.1 顺序候选

Hybrid direct 只按以下顺序运行：

```text
M120
M240
M480
M960 only if needed
```

不得自动运行 M1280、M1920 或调整 QEP cutoff、near-degenerate tolerance、传播模型或 traction模型。

共同设置：

```text
p6/h10
interfaces 10/110 nm
full3d_uniform_cg propagation
accepted exact traction model
same external mode keys as Full3D
MPI8
true residual <= 1e-9
exact traction <= 1e-8
```

## 7.2 每个 M 必须记录

```text
requested / raw / retained modes
positive / negative propagation counts
propagating / weakly evanescent counts
QEP reduced dimensions
basis bytes
coupling bytes
2M x 2M modal Schur dimensions
modal Schur storage / LU storage / condition
build / factor / solve / recovery wall
R/T/A/A_volume
all diffraction orders
selected interface/middle E/H
process-tree RSS/PSS/USS and swap
```

## 7.3 M 收敛 Gate

相邻候选比较：

```text
R/T/A/A_volume absolute delta       <= 1e-6
max significant-order rel delta     <= 1e-4
selected E/H relative L2            <= 5e-3
interface projection residual       <= 1e-8
mode-key set                         exact match for external channels
```

与 Full3D authority比较：

```text
R/T/A/A_volume absolute delta       <= 1e-5
energy closure absolute value       <= 1e-5
max significant-order rel delta     <= 1e-4
interface E relative L2             <= 5e-3
interface H relative L2             <= 1e-2
middle-plane E/H relative L2        <= 5e-3
```

选择最小 `M_robust_h10`：

```text
if M120 passes M120-vs-M240 and Full3D:
    M_robust_h10 = 120
elif M240 passes M240-vs-M480 and Full3D:
    M_robust_h10 = 240
elif M480 passes M480-vs-M960 and Full3D:
    M_robust_h10 = 480
elif M960 passes Full3D and all own numerical/physics Gates:
    M_robust_h10 = 960 (upper-cap authority)
else:
    M_robust_h10 = not established
```

若 M960 仍不通过 Full3D：

```text
classification = 5NM_HYBRID_MODEL_NOT_ESTABLISHED_BY_M960_AT_P6H10
```

允许运行一次 M960 Hybrid iterative 对 direct 的 solver diagnostic，但不得声称 Hybrid 对 Full3D准确。

---

# 8. Phase A：Hybrid iterative MPI8 与 MPI1

## 8.1 冻结方法

使用 Task037b/37c 已接受结构：

```text
exact monolithic Hybrid matrix-free operator
+ right FGMRES
+ action-consistent block-LDU
+ whole-endcap shifted ILU(0)
+ dynamic Matrix-free DtN Woodbury
+ fixed two-pass side residual correction
+ exact one-cell traction
+ M10-style lifecycle/streaming
```

冻结参数：

```text
M                         = M_robust_h10
restart                   = 90
max_it                    = 6000
rtol for reported/global/
 bottom/top/modal          = 5e-9
exact traction Gate       = 1e-8
initial guess             = zero
ILU level                 = 0
overlap                   = 0
subdomains per endcap     = 1
nested local KSP          = false
bottom/top direct factors = 0/0
```

不得根据 5 nm结果调整 shift、restart、passes、M、DtN mode set或 tolerance。

## 8.2 MPI8 fast lane

先运行 MPI8。Gate：

```text
KSP converged reason                   > 0
iterations                             <= 6000
five true residuals                    <= 5e-9
exact traction bottom/top              <= 1e-8
external q identity                    <= 1e-10
full recovery / own physics            = pass
R/T/A/A_volume finite                  = true
energy closure                         <= 1e-5
no direct fallback                     = true
nested local KSP                       = false
swap                                   = 0
```

与 M_robust_h10 Hybrid direct比较：

```text
R/T/A/A_volume absolute delta          <= 1e-6
significant-order relative delta       <= 1e-4
canonical active/full relative L2      <= 1e-5
selected interface/middle E/H          <= 5e-3
modal magnitude relative L2            <= 1e-6
all external mode keys                 exact match
```

若 Hybrid direct本身没有通过 Full3D，iterative通过上述 direct对比只能分类为：

```text
ITERATIVE_SOLVER_PASS_HYBRID_MODEL_NOT_VALIDATED
```

## 8.3 MPI1 minimum-memory lane

只有 MPI8 Hybrid iterative 通过后才运行 MPI1。必须保持完全相同：

```text
M
restart
max_it
rtol
PC
external mode set
field and order outputs
```

MPI1 与 MPI8 的数值身份 Gate：

```text
R/T/A/A_volume absolute delta          <= 1e-6
significant-order relative delta       <= 1e-4
canonical active/full relative L2      <= 1e-5
selected E/H relative L2               <= 5e-3
all mode keys                          exact match
```

资源分类：

```text
preferred            <= 2.0 GiB
engineering-positive <= 4.0 GiB
hard stop            >= 12.0 GiB or any swap
```

这些资源线只用于分类，不改变数值 pass/fail。

必须回答：

```text
5 nm p6/h10 MPI1 peak RSS
relative to 13.5 nm accepted MPI1 baseline increase
increase decomposed into FE factor / W / K / modal basis / Schur / Krylov / recovery
```

不得只报告总内存而不拆解增长来源。

---

# 9. Phase B：5 nm 网格精度与规模扩展

Phase B 只有在以下条件满足后才能开始：

```text
A2 Full3D iterative p6/h10 numerical pass
M_robust_h10 established or clearly bounded
Hybrid iterative p6/h10 numerical pass
no shared implementation/physics defect
```

## 9.1 网格顺序

严格按：

```text
p6/h7.5
p6/h5
```

不得自动进入 h4、h3 或更细网格。

每个网格先执行：

```text
mesh-only preflight
assembly/action-only preflight
factor/setup estimate
external-mode and modal-capacity estimate
```

达到资源 hard stop估计时不得启动正式 solve。

## 9.2 Full3D reference

每个新网格优先运行：

```text
Full3D iterative MPI8
```

保持与 A2 相同的 M3a参数和 max_it=4000。

Full3D direct的条件运行：

```text
only if symbolic/analysis estimate <= 160 GiB
and predicted process-tree peak <= 180 GiB
and swap is zero
```

Full3D direct h7.5/h5不是必需；若未运行，必须明确标为 `not_run_by_resource_policy`。

Full3D iterative 在没有同网格 direct时的 reference身份必须依靠：

- h10 direct/iterative identity；
- 同一 iterative算法无参数变更；
- full-FE residual与能量闭合；
- h 收敛趋势；
- mode-key和canonical一致性。

## 9.3 每个网格的 M 复核

对 h7.5/h5，先运行：

```text
M = previous-grid M_robust
M = min(2 * previous-grid M_robust, 960)
```

若两者和 Full3D均通过，选择较小值。
若失败，可继续在 `[120,240,480,960]` 余下候选中顺序升级，但不得超过960。

记录：

```text
M_robust_h7p5
M_robust_h5
```

## 9.4 Hybrid iterative

每个网格的 Hybrid direct和 M选择通过后，运行：

```text
Hybrid iterative MPI8
```

MPI1只在 h5最终 accuracy candidate通过 MPI8后运行一次，用于测量：

```text
5 nm accuracy-qualified minimum memory
```

不得为 h7.5和 h5同时进行大范围 MPI扫描。

## 9.5 网格收敛 Gate

最终以 h7.5 vs h5 的 Full3D iterative比较判断 5 nm离散收敛：

```text
R/T/A/A_volume absolute delta          <= 1e-4
max significant-order relative delta   <= 1e-3
selected E/H relative L2               <= 1e-2
energy closure each grid               <= 1e-5
mode-key physical identity             exact match where both are propagating
```

若未通过：

```text
classification = 5NM_DISCRETIZATION_NOT_CONVERGED_BY_P6H5
```

停止，不得自动 h4。等待 review决定是否值得扩大资源投入。

5 nm accuracy-qualified overall必须同时满足：

1. h7.5/h5 Full3D迭代网格收敛；
2. h5 Hybrid direct在 M_robust_h5下通过 Full3D Gate；
3. h5 Hybrid iterative通过 Hybrid direct和 Full3D Gate；
4. full residual、traction、energy、orders和fields全部通过。

---

# 10. 动态衍射级与显著通道合同

5 nm下传播衍射级数量会显著增加。不得继续硬编码：

```text
40 external modes
80 total external channels
12 significant channels
```

每个正式 case必须记录：

```text
all top/bottom mode keys
spatial (m,n) count
S/P channel count
propagating / evanescent / Rayleigh classification
actual significant-channel count
significance threshold and normalization
```

比较必须使用动态 key intersection和 exact key-set Gate。所有低于 floor 的通道仍需保存，
不得只输出显著通道。

同一个物理案例的 Full3D、Hybrid direct和 Hybrid iterative必须使用同一外部通道定义。

---

# 11. 资源预算与 watchdog

## 11.1 工作站预算

物理内存：

```text
256 GiB
```

正式 watchdog默认：

```text
warning threshold = 180 GiB
hard stop         = 220 GiB
swap required     = 0
```

若运行环境/WSL/Docker实际可用内存低于物理内存，hard stop必须设置为：

```text
min(220 GiB, 0.90 * actual available limit)
```

并在记录中给出实际依据。

## 11.2 资源阶段

每个重型 case至少记录：

```text
mesh/function-space
assembly or exact action build
Full3D local factors
Hybrid bottom/top factors
external W
external K and K-LU
internal modal basis
modal coupling
modal Schur and dense LU
Krylov basis
field recovery
postprocessing
release/allocator high-water
```

正式权威使用 simultaneous process-tree RSS；PSS/USS为诊断。不得混用历史 per-rank峰值计算节省比例。

## 11.3 时间

必须分别记录：

```text
mesh/assembly
QEP/basis
factor/PC setup
modal coupling/Schur
linear solve
recovery
postprocess
total wall
```

嵌套或重叠时间不能相加反推 total wall。

---

# 12. 0.7 nm 可行性审计：禁止完整 PDE

Task039 的 0.7 nm阶段只做容量与架构审计，不创建完整 0.7 nm FEM求解。

## 12.1 材料边界

本任务没有获得 0.7 nm 的 delta/beta。不得猜测、插值或沿用 5 nm材料。

因此：

```text
air-side external mode enumeration = allowed and exact
substrate-side material-dependent enumeration = pending 0.7 nm optical constants
full absorption/RTA prediction = forbidden
```

最终报告必须包含：

```text
0P7NM_MATERIAL_INPUT_INCOMPLETE
```

直到用户提供 0.7 nm材料常数。

## 12.2 FE/网格外推

使用 5 nm h10/h7.5/h5 实测拟合：

```math
n_{\Gamma}(h),
```

```math
\mathrm{NNZ}_{\mathrm{factor}}(h),
```

```math
M_{\mathrm{FE\ cache}}(h),
```

```math
T_{\mathrm{apply}}(h).
```

至少报告两个 0.7 nm场景：

### 场景 A：保持 5 nm accuracy-qualified 的 h/λ

```math
h_{0.7,A}
=
h_{5,\mathrm{qualified}}
\frac{0.7}{5.0}.
```

### 场景 B：工程目标 p6/h1 nm

```text
p6 / h1 nm
```

对两种场景估计：

```text
cell count
full DoF
active trace rows
factor NNZ and bytes
matrix-free action/cache bytes
MPI1 and MPI8 process-tree range
```

外推必须给出拟合区间和不确定性，不能只给一个精确到小数点后的伪精确数字。

## 12.3 External DtN/Woodbury

使用当前正式 enumerator在 0.7 nm空气侧计算：

```text
exact propagating spatial (m,n) count
S/P channel count
Rayleigh / near-cutoff count
```

对每个预测 FE规模计算：

```math
W_s\in\mathbb C^{n_\Gamma\times N_{\mathrm{DtN}}},
```

```math
K_s\in\mathbb C^{N_{\mathrm{DtN}}\times N_{\mathrm{DtN}}}.
```

必须报告：

```text
single-side W bytes
two-side W bytes
single-side dense K bytes
K-LU estimated bytes
K factor time estimate
whether current dense K is plausible
```

若任何单一 external component超过预算，应优先分类为：

```text
0P7NM_REQUIRES_EXTERNAL_DTN_WOODBURY_REDESIGN
```

不得用 factor优化掩盖 external瓶颈。

## 12.4 Internal M/modal Schur

使用 13.5 nm已接受 M与 5 nm实测 M_robust，报告至少两种保守增长模型：

```text
M proportional to 1/lambda
M proportional to 1/lambda^2
```

对每种估计计算：

```text
2M modal unknowns
modal basis bytes
coupling bytes
Schur bytes
Schur dense-LU bytes
O(M^3) factor-time range
```

若 current dense modal Schur超过预算：

```text
0P7NM_REQUIRES_INTERNAL_MODAL_SCHUR_REDESIGN
```

## 12.5 收敛性风险

根据 13.5 nm和5 nm实测：

```text
Full3D iterative iterations
Hybrid iterative iterations
late contraction factor
restart behavior
endcap local quality
```

给出 0.7 nm迭代次数范围，但不得声称为已验证数值结果。

## 12.6 最终 0.7 nm分类

可以同时出现多个瓶颈。最终至少选择以下状态之一：

```text
0P7NM_CURRENT_ARCHITECTURE_PLAUSIBLE_UNDER_256GIB
0P7NM_REQUIRES_EXTERNAL_DTN_WOODBURY_REDESIGN
0P7NM_REQUIRES_INTERNAL_MODAL_SCHUR_REDESIGN
0P7NM_FE_FACTOR_OR_CACHE_EXCEEDS_256GIB_BUDGET
0P7NM_CONVERGENCE_RISK_UNRESOLVED
0P7NM_MATERIAL_INPUT_INCOMPLETE
```

只有所有主要组件的保守上界低于 220 GiB、没有 dense算子单点失控、且收敛趋势可接受时，
才可使用 `CURRENT_ARCHITECTURE_PLAUSIBLE`。这仍不等于 0.7 nm物理资格通过。

---

# 13. 失败与停止规则

## 13.1 共享实现故障

若 angle、material、mode-key、MPI ownership、input mapping或 ABI出现共享故障：

```text
stop all heavy jobs
fix narrowly
run focused tests
await review if numerical semantics changed
```

## 13.2 Full3D direct未建立

可继续 capacity诊断，但所有正式三路准确性状态为：

```text
authority_incomplete
```

## 13.3 Full3D iterative不收敛

不得调 PC。停止 Phase B的 Full3D iterative reference扩展。

## 13.4 Hybrid M未由960建立

不得 M>960。允许一次 M960 iterative-vs-direct solver diagnostic，随后停止。

## 13.5 Hybrid iterative不收敛

不得增加 max_it、改 restart、加第三次 residual correction、调 ILU或切换新PC。

## 13.6 h5网格未收敛

不得自动 h4。记录资源和趋势后等待审阅。

## 13.7 资源超限

达到 hard stop或出现swap时立即终止，保存 partial telemetry，不得重启同一 case并静默放宽预算。

---

# 14. 测试要求

正式 PDE前至少完成：

- 5 nm material parse/epsilon测试；
- one-dat/one-run identity测试；
- 10° grazing/S polarization测试；
- dynamic external-mode count >40测试；
- Full3D direct/iterative/Hybrid mode-key identity测试；
- M120/240/480/960 profile和选择逻辑测试；
- large dynamic Woodbury shape/rank/condition测试；
- resource ledger和hard-stop测试；
- 0.7 nm air-side mode enumerator纯组件测试；
- no 0.7 nm PDE launch合同；
- no neural/learned factor path合同；
- ordinary defaults unchanged合同。

轻量 MPI测试：

```text
MPI1
MPI2
MPI4
```

正式 PDE仅使用任务书规定的 MPI8和MPI1。

静态检查：

```text
ruff check
ruff format --check for changed Python
git diff --check
python -m compileall -q src scripts benchmarks
python benchmarks/check_benchmarks.py --no-write
```

任务结束前运行一次无 deselect的：

```bash
python -m pytest -q
```

要求 zero failures。若环境/ABI identity导致失败，必须保留原始失败证据，不得修改测试或阈值掩盖。

---

# 15. Artifact、case与Git边界

建议建立：

```text
benchmarks/cases/103_5nm_full3d_hybrid_feasibility/
benchmarks/artifacts/task039/
```

tracked内容只包括：

```text
README/config/schema/expected/test_command
compact records
small JSON/CSV summaries
outcomes and response
```

不得提交：

```text
raw fields
mesh files
matrix/factor dumps
large modal bases
large W/K arrays
stdout logs
resource timelines
results directories
```

这些放入 ignored artifact路径，并由 compact record绑定路径和 SHA256。

Task039所有提交只进入：

```text
codex/20260812-task39-5nm-hybrid-0p7nm-feasibility
```

必须及时按阶段 commit并推送远程同一分支。未经最终审阅不得 merge master，不得创建额外分支。

---

# 16. 阶段执行顺序

```text
T0 inherited audit and material contract
T1 input/profile/component support and focused tests
T2 5nm p6/h10 preflight and dynamic external-mode authority
T3 Full3D direct p6/h10 MPI8
T4 Full3D iterative p6/h10 MPI8 and identity
T5 Hybrid direct M120 -> M240 -> M480 -> conditional M960
T6 Hybrid iterative p6/h10 MPI8 -> MPI1
T7 conditional p6/h7.5 reference/Hybrid qualification
T8 conditional p6/h5 reference/Hybrid qualification and MPI1 minimum memory
T9 0.7nm component-only feasibility audit
T10 final tests, outcomes and response
```

不得跳过 Full3D reference链直接宣布 Hybrid准确，也不得在 Phase A未通过时盲目启动 h5。

---

# 17. 最终交付文档

必须完成：

```text
docs/task039_5nm_hybrid_qualification_and_0p7nm_feasibility/outcomes/inherited_master_audit.md
docs/task039_5nm_hybrid_qualification_and_0p7nm_feasibility/outcomes/material_and_case_contract.md
docs/task039_5nm_hybrid_qualification_and_0p7nm_feasibility/outcomes/fixed_grid_full3d_reference.md
docs/task039_5nm_hybrid_qualification_and_0p7nm_feasibility/outcomes/hybrid_m_convergence.md
docs/task039_5nm_hybrid_qualification_and_0p7nm_feasibility/outcomes/hybrid_iterative_mpi8_mpi1.md
docs/task039_5nm_hybrid_qualification_and_0p7nm_feasibility/outcomes/grid_convergence.md
docs/task039_5nm_hybrid_qualification_and_0p7nm_feasibility/outcomes/resource_ledger.md
docs/task039_5nm_hybrid_qualification_and_0p7nm_feasibility/outcomes/feasibility_0p7nm.md
docs/task039_5nm_hybrid_qualification_and_0p7nm_feasibility/outcomes/test_summary.md
docs/task039_5nm_hybrid_qualification_and_0p7nm_feasibility/outcomes/summary.md
docs/task039_5nm_hybrid_qualification_and_0p7nm_feasibility/response_v1.md
```

---

# 18. 最终结果表

## 18.1 p6/h10 fixed-grid

| method | MPI | M | external modes/endcap | iterations | residual | R/T/A | RSS GiB | total wall | status |
|---|---:|---:|---:|---:|---:|---|---:|---:|---|

## 18.2 M convergence

| M | QEP retained | Schur size | Full3D R/T/A delta | max order delta | field delta | RSS | selected |
|---:|---:|---:|---:|---:|---:|---:|---|

## 18.3 Grid convergence

| h nm | Full3D iterative | M_robust | Hybrid direct vs Full3D | Hybrid iterative vs direct | RSS MPI8 | RSS MPI1 |
|---:|---|---:|---|---|---:|---:|

## 18.4 内存分解

| h / MPI | FE cache | local factors | W | K/LU | modal basis | Schur | Krylov | recovery | process-tree peak |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|

## 18.5 0.7 nm审计

| component | 5nm measured | 0.7nm scenario A | 0.7nm p6/h1 | 220 GiB status | redesign needed |
|---|---:|---:|---:|---|---|

---

# 19. 最终分类

若 p6/h5 accuracy chain全部通过，可分类为：

```text
TASK039_5NM_FULL3D_HYBRID_ACCURACY_AND_MEMORY_QUALIFIED
```

若只完成 p6/h10固定网格：

```text
TASK039_5NM_FIXED_GRID_SOLVER_CAPACITY_QUALIFIED_ONLY
```

若 Hybrid iterative准确求解 direct Hybrid但 Hybrid偏离 Full3D：

```text
TASK039_ITERATIVE_SOLVER_PASS_HYBRID_MODEL_FAIL_AT_5NM
```

若 Full3D iterative自身失败：

```text
TASK039_FULL3D_ITERATIVE_WAVELENGTH_ROBUSTNESS_FAIL_AT_5NM
```

0.7 nm分类与 5 nm分类并列报告，不得互相替代。

完成 T10 后停止等待审阅；不得自动创建下一任务、合入 master、运行完整0.7 nm、恢复神经网络路线或扩展新的角度/偏振。
