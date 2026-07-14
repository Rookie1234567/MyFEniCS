# Task032：Hybrid FEM–Modal Direct Baseline for a z-Invariant Middle Region

## 0. 任务身份

```text
task = Task032
name = Hybrid FEM–Modal Direct Baseline for a z-Invariant Middle Region
status = planned / execute only after Task031 clean master merge
execution_branch = codex/20260714-task32-hybrid-fem-modal-direct-baseline
old_local_project = C:\Users\admin\Desktop\Code\fenics_vector_maxwell_floquet_demo_v2_parallel
new_local_project = C:\Users\admin\Desktop\Code\fenics_v3_hybrid_FEM_modal
remote_repository = Rookie1234567/MyFEniCS
reference_wavelength = 13.5 nm
material = current validated Si optical constant
incidence_primary = 10 deg grazing from surface, phi=0, S polarization
solver_scope = direct only
memory_priority = correctness first, memory-aware implementation from day one
ordinary_default_changed = false
```

本任务开启新的 Hybrid FEM–Modal 开发阶段。过去完整 3D FEM、DtN、凝聚和迭代求解器研究告一段落，旧本地目录保留为只读历史基线；Task032 必须在新的本地目录中开发，但继续使用同一个远程库 `MyFEniCS`，以保留历史、benchmark、文档和审查链。

Task032 的根本目标是验证：对于当前规则结构中满足

$$
\varepsilon(x,y,z)=\varepsilon(x,y),
\qquad z\in[10,110]\ \mathrm{nm}
$$

的中间区域，是否可以完全移除该区域的三维体网格，改用二维截面本征模沿 z 方向传播，同时保持与完整 3D FEM 一致的复场、逐衍射级 R/T、总体 R/T/A 和能量闭合。

本任务不是迭代求解器任务。第一版必须以直接法建立可信 reference；h/p 自适应属于 Task033，针对最终 hybrid-adaptive 系统的迭代法属于 Task034，波长缩短和材料色散属于 Task035。

---

# 1. 开始前必须读取的文件

Codex 开始 Task032 前必须读取：

```text
docs/repository_work_principles.md
docs/task_retrospective_standard.md
docs/project_service_requirements_and_forward_model_roadmap.md
docs/project_service_requirements_phase1_scope.md
docs/iterative_solver_ports.md

docs/task031_compact_physical_slab_memory_optimization/task.md
docs/task031_compact_physical_slab_memory_optimization/outcomes/summary.md
docs/task031_compact_physical_slab_memory_optimization/review_report_v1.md
docs/task031_compact_physical_slab_memory_optimization/response_v1.md
docs/task031_compact_physical_slab_memory_optimization/review_report_v2.md

notes/theory/hybrid_fem_modal_domain_decomposition.md
notes/theory/dtn_modal_ports_and_condensation.md
notes/theory/maxwell_strong_weak_and_fem.md
notes/theory/iterative_solver_and_preconditioner.md
```

Task032 的结果必须维护：

```text
docs/task032_hybrid_fem_modal_direct_baseline/outcomes/summary.md
docs/development_progress.md
benchmarks/cases/080_hybrid_fem_modal_direct_baseline/
```

---

# 2. P0：Task031 合并和新本地目录迁移

## 2.1 不得直接在当前 Task031 分支开发

Task032 只有在 Task031 按 Review V2 合入 `master` 后才允许执行。必须记录 Task031 最终 merge SHA，并确认远程 `master` 同时包含：

- Task031 通用基础设施、Case070、文档和审查链；
- `project_service_requirements_and_forward_model_roadmap.md`；
- `project_service_requirements_phase1_scope.md`；
- `iterative_solver_ports.md`；
- 本 Task032 任务书和 Hybrid 理论笔记。

若 Task031 尚未合并，不得开始写 Task032 solver code。

## 2.2 旧本地目录只读冻结

旧目录：

```text
C:\Users\admin\Desktop\Code\fenics_vector_maxwell_floquet_demo_v2_parallel
```

迁移开始前记录：

```powershell
cd C:\Users\admin\Desktop\Code\fenics_vector_maxwell_floquet_demo_v2_parallel
git status --short
git branch --show-current
git rev-parse HEAD
git remote -v
```

将输出写入：

```text
docs/task032_hybrid_fem_modal_direct_baseline/outcomes/local_migration_record.md
```

旧目录从此只用于：

- 查看历史实现；
- 运行旧 benchmark 作为 reference；
- 对照文件或结果。

不得在旧目录继续 Task032 开发、提交或切换 Task032 分支。

## 2.3 新目录建立原则

新目录必须为：

```text
C:\Users\admin\Desktop\Code\fenics_v3_hybrid_FEM_modal
```

用户的目标是保留旧项目副本，同时重新建立与远程 `MyFEniCS` 的链接。为避免复制旧 `.git`、脏状态、绝对路径、缓存和重型结果，推荐执行方式是：

1. 保留旧目录不动；
2. 从 `MyFEniCS` 最新 `origin/master` clean clone 到新目录；
3. 仅在确有必要时，从旧目录复制远程库中不存在的本地辅助文件；
4. 不复制旧 `.git`、虚拟环境、缓存、结果和 benchmark heavy artifacts；
5. 复制任何额外文件后必须检查 tracked diff，不得把未知本地差异直接提交。

推荐 PowerShell 流程：

```powershell
cd C:\Users\admin\Desktop\Code

# 从旧目录读取真实 remote URL，不在任务书中假定认证方式
$remote = git -C .\fenics_vector_maxwell_floquet_demo_v2_parallel remote get-url origin

# 目标目录不得预先包含未知文件
if (Test-Path .\fenics_v3_hybrid_FEM_modal) {
    throw "Target directory already exists; inspect it instead of overwriting."
}

git clone $remote .\fenics_v3_hybrid_FEM_modal
cd .\fenics_v3_hybrid_FEM_modal
git fetch origin --prune
git checkout master
git reset --hard origin/master
git status --short
git remote -v
```

如果用户坚持文件系统复制而不是 clean clone，Codex 也不得复制旧 `.git`。必须排除：

```text
.git
.venv / venv
__pycache__
.pytest_cache
.mypy_cache
.ruff_cache
results
benchmarks/artifacts
large logs / matrices / fields / caches
Docker temporary files
```

然后在新目录独立 `git init + remote add + fetch + checkout origin/master`，并在覆盖任何文件前生成差异报告。出现 tracked 差异时必须先分类，不得直接 `git reset --hard` 丢弃用户文件，也不得直接全部提交。

## 2.4 新目录 Git 验收

新目录必须满足：

```text
folder = C:\Users\admin\Desktop\Code\fenics_v3_hybrid_FEM_modal
origin = MyFEniCS remote
HEAD = latest clean origin/master after Task031 merge
git status --short = empty, except explicitly documented user-local untracked assets
old folder remains unchanged
```

随后由 Codex 在新目录创建执行分支：

```powershell
git checkout -b codex/20260714-task32-hybrid-fem-modal-direct-baseline
```

ChatGPT 不创建 Task032 执行分支；分支由 Codex 在新本地目录创建并 push。

## 2.5 迁移后旧功能 smoke

在开始新方法前，至少运行：

- Python import / compile smoke；
- 现有最小 3D Stage4 smoke；
- 一个现有 direct benchmark；
- 一个现有 condensation/action contract；
- `git diff --check`。

目标不是重新运行 h2，而是证明新目录、Docker mount、相对路径、artifact 路径和远程 Git 连接没有损坏。

迁移 Gate 未通过时不得进入 Hybrid solver 开发。

---

# 3. 冻结物理模型与服务边界

## 3.1 当前固定输入

Task032 第一阶段统一使用：

```text
wavelength = 13.5 nm
material = current validated Si optical constant
geometry = current regular periodic grating
periodic directions = x and y
propagation / domain split direction = z
primary grazing angle = 10 deg from surface
primary normal-angle representation = theta=80 deg
primary azimuth = phi=0 deg
primary polarization = S
finite element = p2 Nedelec for 3D reference and local 3D regions
MPI = 4 ranks for target comparison unless a smaller unit test explicitly says otherwise
```

当前 Si 折射率继续使用项目已验证数值：

$$
n_{\mathrm{Si}}
=
0.999002304859
+i\,0.00182649365.
$$

Task032 不扫描材料不确定性，不修改材料体系，不处理 0.7 nm。

## 3.2 域划分

冻结中间规则区：

```text
middle modal region: z = 10–110 nm
```

内部接口：

$$
\Gamma_b: z=10\ \mathrm{nm},
\qquad
\Gamma_t: z=110\ \mathrm{nm}.
$$

局部三维区：

```text
bottom local 3D region = lower external boundary to z=10 nm
top local 3D region = z=110 nm to upper external boundary
```

接口必须放在严格满足 `epsilon(x,y,z)=epsilon(x,y)` 的区域内。第一版接口网格必须匹配：

```text
2D cross-section mesh
= bottom 3D interface face mesh
= top 3D interface face mesh
```

并保持相同阶次、节点/实体映射和 orientation convention。Task032 不引入 mortar 或非匹配接口。

## 3.3 外部端口保持不变

顶部和底部外部半空间继续使用当前已经验证的：

```text
double Floquet
+ auxiliary Fourier-DtN ports
+ exact condensation
+ official modal R/T
```

内部中间区域使用的是截面 FEM eigenmodes。必须在代码和文档中明确：

```text
external Fourier diffraction modes
!=
internal cross-section FEM eigenmodes
```

当前外部 80 个 modal unknowns 不能直接当作中间区域模式数。

## 3.4 暂不考虑

Task032 不允许加入：

- 新迭代求解器；
- h/p 自适应；
- 不规则曲面；
- 非匹配接口或 mortar；
- 0.7 nm 或其他波长；
- 材料色散扫描和材料不确定性；
- 实验绝对强度、gain、背景、噪声和不确定性；
- 反演优化器、伴随、MCMC 或代理模型；
- 大规模参数扫描；
- 全域 RCWA 替代路线。

---

# 4. Task032 的核心数学和软件目标

## 4.1 二维横截面模态

中间区满足：

$$
\varepsilon(x,y,z)=\varepsilon(x,y).
$$

采用：

$$
\mathbf E(x,y,z)
=
\mathbf e(x,y)e^{i\beta z}.
$$

离散后形成关于传播常数的二次本征问题：

$$
\left(
\beta^2 K_2
+
\beta K_1
+
K_0
\right)\mathbf q=0.
$$

第一版截面离散应优先采用：

```text
transverse field E_t -> 2D Nedelec H(curl)
longitudinal field E_z -> 2D Lagrange H1
```

不得简单把三个分量都放入普通 2D vector Lagrange 空间。

必须支持：

- 双 Bloch/Floquet 横向条件；
- 复数、有损、非 Hermitian 本征问题；
- 传播模、反向模和衰减模；
- 左/右模或等价双正交测试数据；
- 模式残差、归一化和分类。

优先探测 SLEPc PEP 支持；若当前环境不支持，允许经过文档化的线性化后使用 EPS。不得在未审计条件数和伪模态前自行实现不稳定 dense eigen solve。

## 4.2 稳定传播

中间长度：

$$
L_m=100\ \mathrm{nm}.
$$

模式传播：

$$
P_m=e^{i\beta_m L_m}.
$$

必须使用稳定的 scattering/two-port 表示，不得构造包含指数增长衰减模的全 transfer matrix。禁止显式形成：

$$
e^{+|\operatorname{Im}\beta_m|L_m}
$$

导致的病态传播块。

建议 unknown convention：

```text
bottom interface: incoming a_b+ / outgoing a_b-
top interface: incoming a_t- / outgoing a_t+
```

并仅保留物理衰减方向的传播因子。

## 4.3 接口条件

在两个内部接口上满足：

$$
\mathbf n\times
\left(
\mathbf E_{\mathrm{FEM}}-
\mathbf E_{\mathrm{modal}}
\right)=0,
$$

$$
\mathbf n\times
\left(
\mathbf H_{\mathrm{FEM}}-
\mathbf H_{\mathrm{modal}}
\right)=0.
$$

接口投影不能默认使用普通 Euclidean 正交。对于有损非 Hermitian 模式，应构造左/右模或稳定的功率/反应双正交关系，例如：

$$
a_m
=
\langle
\widetilde{\mathbf e}_m,
\mathbf E_t^{\mathrm{FEM}}
\rangle_{\Gamma}.
$$

必须记录投影矩阵的 shape、稀疏/稠密身份、condition estimate 和 projection reconstruction residual。

## 4.4 增广直接系统

第一版可信实现：

$$
\begin{bmatrix}
A_b & 0 & C_b\\
0 & A_t & C_t\\
D_b & D_t & H_m
\end{bmatrix}
\begin{bmatrix}
u_b\\
u_t\\
a
\end{bmatrix}
=
\begin{bmatrix}
f_b\\
f_t\\
g
\end{bmatrix}.
$$

先使用 direct MUMPS 求解增广系统，证明 algebra 和物理正确。不得为了节省内存在增广系统尚未验证前直接跳到复杂 matrix-free 或迭代实现。

## 4.5 Modal-Schur 直接系统

增广直接法通过后，实现：

$$
S_m
=
H_m
-
D_bA_b^{-1}C_b
-
D_tA_t^{-1}C_t.
$$

右端：

$$
r_m
=
g
-
D_bA_b^{-1}f_b
-
D_tA_t^{-1}f_t.
$$

求解：

$$
S_ma=r_m,
$$

再回代：

$$
u_b=A_b^{-1}(f_b-C_ba),
$$

$$
u_t=A_t^{-1}(f_t-C_ta).
$$

此实现必须支持多 RHS 稀疏 direct solve，不得逐列重新创建 solver context。模式 Schur 可以是 dense，但只允许 dense 规模与模式数相关；不得构造 `N_interface x N_interface` 的全稠密矩阵。

---

# 5. 内存优先的软件设计约束

Task032 正确性优先，但代码必须从第一天避免明显不可扩展结构。以下为 P0 约束。

## 5.1 禁止全局复制

不得：

- 将完整 3D FE vectors/matrices allgather 到 rank 0；
- 在每个 rank 完整复制所有二维 eigenvectors；
- 在每个 rank 复制大型 projection matrices；
- 以 Python list 保存每个模式的完整全局数组副本；
- 同时常驻 full-3D reference 和 hybrid target 大矩阵。

本征模和接口数据优先保持 PETSc distributed objects。仅允许小型标量 metadata 和经过阈值证明的小型 modal dense blocks 在 rank 0 或各 rank 复制。

## 5.2 对象生命周期

每个阶段必须有 object ledger：

```text
mesh / spaces
2D eigen matrices
right eigenvectors
left eigenvectors
projection blocks
bottom local matrix/factor
top local matrix/factor
modal propagation block
modal Schur
augmented matrix/factor
recovery vectors
RTA objects
```

不再需要的对象必须显式释放，且有 no-double-destroy 测试。

不得为了后处理默认保存完整中间体场。中间场只在用户请求的少量 z 截面重构；完整 3D volume reconstruction 作为 heavy opt-in artifact。

## 5.3 不同时常驻两套直接因子

第一版可先实现 `fast_direct`：同时保留 `A_b` 和 `A_t` factors。

随后至少实现或评估 `memory_minimal_direct`：

```text
factor bottom -> build contribution -> release
factor top    -> build contribution -> release
solve modal Schur
refactor locally only if field recovery requires it
```

是否采用重复因子化由实测 memory/time 决定。不得未经比较便宣称 sequential factorization 更优。

## 5.4 投影和 Schur 存储

必须在 h5 记录：

- interface DoF 数；
- 模式数 M；
- projection matrix bytes；
- modal Schur bytes；
- local factor nnz/bytes；
- eigenvector bytes；
- peak stage。

若某实现导致存储复杂度近似：

$$
O(N_{\Gamma}^2),
$$

必须停止并重构。目标应接近：

$$
O(N_{\Gamma}M)+O(M^2).
$$

## 5.5 复数精度

核心求解保持 PETSc complex128。不得为了内存目标静默改成 complex64。任何低精度研究只能作为后续独立 Task，且必须与 complex128 reference 比较。

## 5.6 内存遥测

复用 Task031 external simultaneous sampler 思路，记录：

```text
simultaneous live-rank RSS
container cgroup current/peak
swap in/out
stage
process tree
object payload model
```

新增阶段至少包括：

```text
cross_section_eigen_assembly
cross_section_eigen_solve
mode_classification
bottom_local_factor
bottom_schur_contribution
top_local_factor
top_schur_contribution
modal_schur_solve
field_recovery
middle_plane_reconstruction
official_rta
```

不得把不同 rank 不同时刻的 historical peaks 相加作为唯一 peak。

## 5.7 h2 解锁条件

h2 Hybrid direct 默认锁定。只有满足以下条件才能运行：

1. h5 全链路数值通过；
2. h3 全链路数值通过；
3. mode truncation 已收敛；
4. hybrid 与 full-3D reference 的 R/T/A、接口场和中间截面场通过；
5. 两套独立内存预测中心值均 `<=4.0 GiB`；
6. 保守上界 `<=5.0 GiB`；
7. 无 swap；
8. clean tracked source；
9. 设置 warning 和 controlled termination。

建议 h2 warning：

```text
warning = 4.5 GiB
controlled termination = 6.0 GiB
```

若早期实测表明该阈值不合理，可在 outcomes 中解释后调整，但不得静默取消。

---

# 6. 分阶段实施计划

## Phase 0：新目录、Git、环境和旧能力迁移

交付：

```text
local_migration_record.md
environment_capability.md
old_vs_new_smoke.md
```

检查：

- 新路径正确；
- remote 正确；
- clean master 正确；
- Task032 branch 正确；
- Docker mount 和 artifact path 不再写死旧文件夹名；
- SLEPc/PEP/EPS 可用性；
- 旧 direct/condensation smoke 通过。

任何源代码中若硬编码：

```text
fenics_vector_maxwell_floquet_demo_v2_parallel
C:\Users\admin\Desktop\Code
```

必须改为相对路径或显式配置，并有测试防止回归。

## Phase 1：冻结 full-3D reference

不重新发明 reference。复用当前完整 3D direct 路径，在 h5/h3 生成：

- full-3D field reference；
- interface tangential traces at z=10/110；
- selected middle planes，例如 z=30/60/90；
- complex diffraction amplitudes；
- per-order R/T；
- total R/T/A；
- energy closure；
- command/SHA/image/material identity。

h2 reference 可使用已有可信 direct/iterative物理结果作为 R/T/A 参考，但 Hybrid h2 正式对比是否需要完整 direct field，应由 h3 结果和资源决定，不得强制重跑 20 GB direct。

## Phase 2：二维截面 eigenproblem MVP

先做可解析/可独立验证的小问题：

1. homogeneous periodic air cross-section；
2. homogeneous lossy cross-section；
3. 当前 `epsilon(x,y)` 截面。

必须验证：

- eigen residual；
- analytic/plane-wave beta on homogeneous case；
- Bloch phase；
- orientation；
- forward/backward pairing；
- distributed eigenvector ownership；
- mode normalization。

不得直接只在最终复杂截面上观察“看起来合理”的 beta。

## Phase 3：模式分类、归一化和追踪

传播方向优先依据 z 向平均 Poynting flux：

$$
P_z
=
\frac12
\operatorname{Re}
\int_{\Gamma}
\left(
\mathbf E\times\mathbf H^*
\right)\cdot\mathbf e_z\,d\Gamma.
$$

纯衰减模依据物理衰减方向和分支选择分类。

必须处理：

- near-zero flux；
- cutoff；
- complex beta；
- near-degenerate groups；
- left/right overlap；
- mode pair identity。

第一版 mode tracking 至少支持相邻角度或模式数变化时的 overlap matching，但 Task032 不要求完整参数扫描鲁棒性。

## Phase 4：稳定 two-sided propagation

单独测试中间 100 nm modal propagation：

- 无界面反射时的单模传播；
- 正反向传播；
- 衰减模无指数爆炸；
- reciprocity/passivity diagnostic；
- propagation composition test：`L1+L2` 与连续两段一致。

不得在 local FEM coupling 尚未加入前跳过该模块测试。

## Phase 5：匹配接口 trace coupling

在匹配网格上实现：

- 3D Nedelec tangential trace extraction；
- 2D mode reconstruction to interface trace；
- left/right projection；
- orientation signs；
- top/bottom normal convention；
- projection/reconstruction residual。

必须有单接口 round-trip test：

```text
mode coefficients -> trace -> projected coefficients
```

并对 near-degenerate mode block 使用子空间误差，而不是强制逐向量唯一相等。

## Phase 6：Hybrid augmented direct

建立完整增广系统并使用 MUMPS direct。

先 h5 单点：

```text
13.5 nm
10 deg grazing
phi=0
S polarization
```

通过后再做 h3。

必须验证：

- matrix block shapes；
- assembled residual；
- interface continuity；
- R/T/A；
- energy closure；
- middle selected-plane reconstruction；
- mode count convergence。

## Phase 7：Modal-Schur direct

在 augmented direct 通过后实现 modal Schur direct。

必须比较：

```text
augmented hybrid direct
vs
modal-Schur direct
```

比较：

- solution；
- modal coefficients；
- interface traces；
- R/T/A；
- memory；
- setup/solve/recovery time。

Schur 路径若数值正确但内存不降，仍要保留负结果并解释峰值来源。

## Phase 8：模式截断 funnel

建议初始模式数：

```text
M = 20 -> 40 -> 80 -> 120 -> 160 -> adaptive continuation
```

但不得假定 160 足够，也不得强制每次重新求所有低阶模式而不使用 warm start/cache。

至少检查：

$$
|R_{\mathrm{total}}^{(M_2)}-R_{\mathrm{total}}^{(M_1)}|,
$$

$$
|T_{\mathrm{total}}^{(M_2)}-T_{\mathrm{total}}^{(M_1)}|,
$$

$$
|A^{(M_2)}-A^{(M_1)}|,
$$

以及可靠衍射级的相对变化。

建议 Gate：

```text
mandatory total R/T/A delta <= 1e-5
strong total R/T/A delta <= 1e-6
significant per-order relative delta <= 1e-4
interface projection residual <= 1e-8 preferred
```

若 weak diffraction order 接近零，使用 absolute+relative 混合容差。

## Phase 9：full-3D vs Hybrid 验证

### 主单点

```text
h5/h3
13.5 nm
10 deg grazing
phi=0
S
```

比较：

- complex `r_mn/t_mn`；
- `R_mn/T_mn`；
- total R/T/A；
- energy closure；
- interface tangential fields；
- selected middle-plane field；
- full algebra residual；
- mode truncation error。

### 参数化 smoke

h5：

```text
alpha = 1,2,3,4,5,6,7,8,9,10 deg
polarization = S and P
```

h3：

```text
alpha = 1,3,5,7,10 deg
polarization = S and P
```

h2：

```text
10 deg, S only mandatory
10 deg, P optional if resources allow
```

Task032 的角度/偏振 smoke 目标是证明参数入口、模式重算、分类和输出正确，不宣称整个 1–10° 范围已经形成 production qualification。

## Phase 10：内存和时间结论

当前 benchmark 工程目标：

```text
acceptable peak <= 5 GiB
target peak <= 3 GiB
preferred peak <= 2 GiB
```

这些是 h2 Hybrid direct 的探索目标，不是预先保证。

最终必须分别报告：

- full-3D reference peak；
- 2D eigen solve peak；
- augmented hybrid peak；
- modal-Schur peak；
- fast vs memory-minimal direct；
- stage peak；
- factor/eigen/projection/modal storage；
- total time；
- memory reduction来源。

禁止只报告最终 current RSS 或理论对象 bytes。

---

# 7. 建议代码结构

Task032 应建立清晰的新模块，不把新逻辑堆入旧 workstation runner：

```text
src/modes/
├── __init__.py
├── cross_section_spaces.py
├── quadratic_beta_eigenproblem.py
├── mode_classification.py
├── mode_normalization.py
├── mode_tracking.py
└── mode_storage.py

src/coupling/
├── __init__.py
├── modal_trace_projection.py
├── internal_modal_two_port.py
└── hybrid_interface_blocks.py

src/solvers/
├── hybrid_fem_modal_augmented_direct.py
└── hybrid_fem_modal_schur_direct.py

src/runners/
└── run_hybrid_fem_modal.py

benchmarks/cases/
└── 080_hybrid_fem_modal_direct_baseline/

docs/task032_hybrid_fem_modal_direct_baseline/
├── task.md
└── outcomes/

notes/theory/
└── hybrid_fem_modal_domain_decomposition.md
```

若实际实现需要不同文件划分，可以调整，但必须保持：

```text
eigenmodes
coupling
solvers
runner
benchmark
```

边界清晰。

---

# 8. API 和数据合同

## 8.1 模态对象

建议定义明确数据类，至少包含：

```text
beta
right eigenvector
left/test eigenvector or biorthogonal representation
forward/backward/evanescent classification
power flux
normalization factor
eigen residual
Bloch wavevector
mode identity
ownership/distribution metadata
```

不得用无结构 dict 在多个模块间传递大量模式数据。

## 8.2 Hybrid solve 输出

每个正式 run 至少输出：

```text
physical parameters
split interfaces
mesh/order/DoF
mode count and classification
beta spectrum summary
projection residual
modal truncation evidence
augmented or Schur identity
reported/direct residual
interface continuity error
complex r_mn/t_mn
R_mn/T_mn
R_total/T_total/A_volume
energy closure
selected middle-plane reconstruction error
memory stages
timing stages
commit/command/image/material identity
```

## 8.3 Heavy artifacts

以下保留在 ignored artifact 目录，不提交 Git：

- eigenvector fields；
- full matrices；
- LU factors；
- full 3D fields；
- all z-plane reconstructions；
- raw memory timeline；
- large mode caches。

Git 只提交 lightweight summaries、hashes、small CSV/JSON 和可复现命令。

---

# 9. 测试要求

至少新增：

## 9.1 单元测试

- QEP block shape and dtype；
- homogeneous analytic beta；
- Bloch phase；
- forward/backward classification；
- evanescent branch；
- left/right normalization；
- propagation composition；
- no exponential-growth branch；
- trace orientation；
- mode-trace round trip；
- augmented vs Schur algebra；
- require/release/no-double-destroy；
- distributed ownership without rank-0 full gather。

## 9.2 MPI 测试

至少 MPI1、MPI2、MPI4：

- cross-section assembly；
- eigenvector distribution；
- trace projection；
- hybrid block assembly；
- direct solve smoke；
- selected field reconstruction。

## 9.3 数值 benchmark

Case080 必须有：

```text
config.json
expected/gates.json
run.sh
README.md
records/
checker integration
```

正式 R/T/A 只能来自通过 full residual、interface continuity 和 mode-truncation Gate 的场。

---

# 10. 停止规则和失败分类

必须停止并记录 negative result，如果出现：

- QEP 伪模态无法通过 residual/filter；
- 模式方向/branch 在 cutoff 附近不稳定；
- transfer representation 指数爆炸；
- projection condition 极差且随 M 恶化；
- hybrid 与 full 3D 在模式增加后不收敛；
- dense interface storage 变成 `O(N_interface^2)`；
- rank 0 聚集成为内存瓶颈；
- h3 预测已表明 h2 超过 5 GiB 保守上界；
- 为了通过结果而修改物理模型、衍射级、材料或端口定义。

失败不得隐藏。应区分：

```text
physics formulation failure
eigenproblem failure
mode classification failure
interface projection failure
modal truncation insufficient
direct factor memory failure
implementation/performance failure
```

---

# 11. 成功标准

## 11.1 最低成功

- 新本地目录和 Git 迁移正确；
- old project 不被修改；
- 2D cross-section eigenproblem 有独立验证；
- stable two-sided propagation 通过；
- matching-interface coupling 通过；
- h5 augmented hybrid direct 与 full 3D 一致；
- 模态截断可观测收敛；
- 文档、测试和 Case080 完整。

分类：

```text
hybrid_formulation_prototype_success
```

## 11.2 工程成功

进一步满足：

- h3 augmented and Schur direct 通过；
- h5/h3 R/T/A、接口场和中间截面场一致；
- modal-Schur 相对 augmented 有明确内存收益；
- 1–10° + S/P h5 smoke 通过；
- 内存阶段和对象生命周期可信。

分类：

```text
hybrid_direct_engineering_success
```

## 11.3 强成功

进一步满足：

- h2 解锁并通过；
- h2 peak `<=3 GiB`；
- preferred 为 `<=2 GiB`；
- 无 swap；
- R/T/A 与 reference 误差达到 strong Gate；
- mode count、内存和时间均可解释；
- 为 Task033 提供固定接口 trace 和可自适应局部 3D 区域。

分类：

```text
hybrid_direct_strong_memory_success
```

若 h2 为 3–5 GiB 但数值正确，分类为：

```text
hybrid_direct_memory_positive_with_qualifications
```

---

# 12. Task032 完成后的决策

Task032 完成后必须回答：

1. 中间 100 nm 是否可以被截面模态可靠替代？
2. 需要多少传播模和衰减模？
3. 内部接口放在 z=10/110 是否合适？
4. augmented 与 modal-Schur 哪个是可信 reference？
5. h2 实测峰值是多少？
6. 内存主要来自 eigenvectors、local factors、projection 还是 Schur？
7. 角度和 S/P 改变时，哪些对象可以复用？
8. Task033 的接口网格是否应固定，只对 local 3D interior 做 h/p 自适应？
9. Task034 应针对什么最终块系统设计迭代法？
10. 该路线是否值得继续缩短到 0.7 nm？

只有 Task032 证明 Hybrid 方法正确且内存有结构性下降后，才允许进入 Task033。

---

# 13. Codex 最终回应格式

Codex 完成后创建：

```text
docs/task032_hybrid_fem_modal_direct_baseline/response_v1.md
```

并在 `outcomes/summary.md` 中使用以下结构：

```text
1. local migration and branch identity
2. frozen physical model
3. theory-to-code mapping
4. eigenproblem implementation and validation
5. mode classification/normalization
6. stable propagation
7. interface projection
8. augmented direct result
9. modal-Schur result
10. truncation convergence
11. full-3D comparison
12. angle/polarization smoke
13. memory and timing
14. negative results
15. changed files
16. merge recommendation
17. next Task033 decision
```

不得用一句“已完成”代替结构化证据。