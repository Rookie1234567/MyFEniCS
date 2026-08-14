# Task039 Review Report V3：1° 掠射 2D/3D 参考链、Hybrid PC 重设计与内存降峰

## 0. 审阅决定

```text
review                                  = Task039 Review Report V3
reviewed_branch                         = codex/20260812-task39-5nm-hybrid-0p7nm-feasibility
reviewed_head                           = 1060a623255959cbe8f4255d4dbcd812ee5971a7
extension_status                        = AUTHORIZED_WITH_STRICT_SCOPE
master_write_or_merge                   = forbidden
new_branch_or_worktree                  = forbidden
ordinary_default_change                 = forbidden
new_physical_grazing_angle_deg          = 1.0
new_internal_theta_deg                  = 89.0
new_azimuth_deg                         = 0.0
polarization                            = S only
wavelength_nm                           = 5.0
material_n                              = 0.99396854453 + 0.00435380777i
M                                       = 480 fixed
M_above_480                             = forbidden
MPI                                     = 8 only for formal 3D/Hybrid runs
MPI1                                    = forbidden
strict_channel_repair                   = deferred
Full3D_M3a_retuning                     = forbidden
Hybrid_PC_redesign                      = authorized
memory_lifecycle_redesign               = authorized
neural_or_learned_factor                = frozen
full_0p7nm_PDE                          = forbidden
concurrent_heavy_jobs                   = forbidden
```

本 Review 接受并冻结以下判断：

1. 10° 掠射下的 h10、h7.5、h6、h5 结果全部作为 Task39 历史证据保留，但不再作为新一轮 1° 物理模型的 reference；
2. 新一轮物理模型只改变入射角：掠射角从 10° 改为 1°，方位角仍为 0°，S 偏振、5 nm 材料、几何、接口位置和其他物理设置保持不变；
3. 由于结构沿 y 方向完整铺满一个周期、phi=0° 且为 S 偏振，连续问题可以严格约化为二维 TE 问题，因此先建立廉价而高精度的 2D reference，再用相近网格尺寸运行 3D；
4. 旧 V2 的逐衍射通道修复暂缓。本 Review 仍完整导出通道，但不开发新的相位、S/P gauge 或 q-to-amplitude 修复；
5. 后续重点是重设计 Hybrid iterative 的 PC。旧 h5/M480 结果中 modal residual 已约 `4.86e-12`，而 bottom/top residual 约 `0.99/0.96`，说明主要失败来自 FE endcap inverse，而不是 modal solve；
6. 旧 iterative 仅比 Hybrid direct 节约约 4.14% RSS，证明删除全局 direct factor 并未触及主要峰值。本 Review 同时授权 PC 重设计和 QEP/modal/coupling 生命周期降峰；
7. 为尽快获得可解释的正结果，本 Review 使用“2D reference → 3D direct → Hybrid direct integrated physics → exact-side oracle → 生产 PC → 内存降峰”的短漏斗，不再允许盲目增加迭代次数或 M。

本 Review 不撤销以下历史 negative：

```text
TASK039_FULL3D_ITERATIVE_WAVELENGTH_ROBUSTNESS_FAIL_AT_5NM
FULL3D_DIRECT_5NM_REFERENCE_NOT_CONVERGED_AT_P6H5   # 10°历史模型
H5_M480_HYBRID_MODEL_FAIL                           # 10°历史严格通道分类
H5_M480_HYBRID_ITERATIVE_SOLVER_FAIL                # 10°历史PC结果
```

它们必须继续保留，但不得与新的 1° 模型混写为同一结果。

---

# 1. 新物理模型合同

## 1.1 冻结输入

```text
wavelength                       = 5.0 nm
n_grating                        = 0.99396854453 + 0.00435380777i
n_substrate                      = 0.99396854453 + 0.00435380777i
n_air                            = 1 + 0i
period_x / period_y              = 50 / 25 nm
grating width x / y / height     = 17 / 25 / 120 nm
z_min / z_max                    = -10 / 130 nm
Hybrid interfaces                = 10 / 110 nm
grazing angle                    = 1°
internal theta from -z           = 89°
azimuth phi                      = 0°
polarization                     = S
Nedelec / TE degree              = p6
mesh family                      = boundary-fitted
vertical boundary                = DtN port
auto external modes              = required
```

用户输入只写：

```text
grazing_angle_deg = 1.0
azimuth_deg = 0.0
polarization = "s"
```

程序内部必须得到：

```math
\theta = 90^\circ-1^\circ=89^\circ,
```

```math
\widehat{\boldsymbol k}
=
(\sin 89^\circ,0,-\cos 89^\circ).
```

不得把 `theta=1°` 误当作新模型，也不得复用 10° case 的 604-key inventory；所有 1° case 必须由正式枚举器重新生成 external mode keys，并在同一物理模型的 2D/3D/Hybrid 比较中保存精确身份。

## 1.2 2D TE 与 3D S 的严格对应

当前结构满足 y-invariant：

```text
grating_width_y = period_y
materials independent of y
phi = 0°
S polarization gives E parallel to y
```

因此连续 Maxwell 问题可严格约化为二维 TE：

```math
E^{3D}_y(x,z) \leftrightarrow E^{2D}_{TE}(x,z),
```

```math
(H^{3D}_x,H^{3D}_z) \leftrightarrow (H^{2D}_x,H^{2D}_z).
```

Codex 必须先审计 2D 与 3D 的角度、时间因子、磁场符号、端口法向和功率归一化，使解析入射波的：

```text
kx
kz
incident power
specular direction
S/TE field direction
```

一致到 `1e-12` 相对误差以内。该审计未通过时，禁止比较 2D/3D 数值结果。

---

# 2. 快速正结果漏斗

本 Review 的目标不是一次完成所有长期问题，而是尽快建立四个有独立意义的正里程碑：

```text
P1 = 2D_TE_REFERENCE_ESTABLISHED_AT_1DEG
P2 = FULL3D_MATCHES_2D_REFERENCE_AT_AFFORDABLE_MESH
P3 = HYBRID_BLOCK_LDU_EXACT_SIDE_ORACLE_PASS
P4 = HYBRID_PRODUCTION_PC_NUMERICAL_AND_MEMORY_PASS
```

P1、P2、P3、P4 必须分别记录。P3 成功不等于生产 PC 成功；P4 才是最终目标。

执行顺序：

```text
V3-0  inherited audit and 1° physical identity
V3-1  exact 2D/3D reduction audit and 2D input implementation
V3-2  2D TE p6 convergence reference
V3-3  matched 3D Full3D direct h5 and conditional h4.5/h4
V3-4  2D-vs-3D selection of an affordable 3D solver anchor
V3-5  Hybrid direct M480 on the selected 3D mesh; integrated-physics Gate only
V3-6  existing h5 memory timeline attribution and 1° setup telemetry
V3-7  operator identity, side contraction and exact-side-LU oracle
V3-8  bounded production-PC candidate funnel
V3-9  lifecycle/process-separation memory optimization
V3-10 one final Hybrid iterative MPI8 qualification and response_v4.md
```

所有重型作业严格串行。每阶段完成后及时 commit 并 push 到同一 Task39 分支。

---

# 3. V3-0：继承审计与新模型隔离

创建：

```text
docs/task039_5nm_hybrid_qualification_and_0p7nm_feasibility/outcomes/review_v3_inherited_audit.md
```

必须记录：

- current local/remote SHA、upstream、ahead/behind、clean status；
- 10° V2 Full3D h5、Hybrid direct h5 M480、Hybrid iterative negative 的 record/SHA；
- 新 1° model_id、comparison_group、physical SHA；
- 10° 与 1° 结果目录和 compact record 必须完全分开；
- h10 仍仅为历史欠离散压力记录；
- M480 固定，M960 和更大 M 禁止；
- strict per-channel repair 明确 postponed；
- ordinary defaults、master和其他分支不变。

第一项 V3 提交必须为 docs-only。

---

# 4. V3-1/V3-2：2D TE 高精度 reference

## 4.1 2D 输入与执行入口

使用 Task38 的一个 `.dat` 对应一次运行入口，新建独立 2D official inputs。至少包含：

```text
5nm_1deg_2d_te_p6h5_direct_mpi1.dat
5nm_1deg_2d_te_p6h4_direct_mpi1.dat
5nm_1deg_2d_te_p6h3_direct_mpi1.dat
5nm_1deg_2d_te_p6h2_direct_mpi1.dat
5nm_1deg_2d_te_p6h1p5_direct_mpi1.dat   # conditional
```

2D 使用直接法；MPI1足够。若现有 2D 输入 schema 使用不同角度字段，loader 必须从同一个 `grazing_angle_deg=1.0` 生成与 3D 完全相同的 `kx/kz`，不得让用户手工维护两个角度约定。

## 4.2 2D 网格漏斗

正式顺序：

```text
h5 → h4 → h3 → h2 → conditional h1.5
```

只要相邻两对同时通过下述 Gate，即可停止更细网格：

```text
max |delta R,T,A,A_volume|          <= 1e-6
energy closure both                 <= 1e-8
main propagating-order power delta  <= 1e-4
power-weighted all-order delta      <= 1e-5
selected E relative L2              <= 1e-3
selected H relative L2              <= 2e-3
```

若 h3-vs-h2 已通过，则 h1.5不运行。若未通过，运行 h1.5；不得自动进入 h1或更细，完成后等待审阅。

## 4.3 2D 输出

每个 2D case必须保存：

```text
R/T/A/A_volume
all propagating m orders
complex outgoing amplitudes
selected E_y, H_x, H_z on common x-z samples
incident power and normalization
mesh cells / DoFs / matrix NNZ / factor inventory
time and memory
input/resolved/source hashes
```

成功分类：

```text
TASK039_V3_2D_TE_REFERENCE_PASS
```

2D reference只在当前严格 y-invariant、phi0、S偏振案例中有效；不得推广到未来真实二维光栅或非零方位角。

---

# 5. V3-3/V3-4：采用相近网格尺寸运行 3D

## 5.1 3D direct 网格

新 1°模型只运行：

```text
p6/h5    mandatory
p6/h4.5  conditional if h5 does not match 2D reference
p6/h4    conditional only after h4.5 and resource preflight
```

不得运行 h10/h7.5/h6 的新 1° case。h4只有在：

```text
predicted process-tree peak < 190 GiB
integer/index audit pass
MemAvailable >= 210 GiB
swap = 0
disk sufficient
no concurrent heavy job
```

时可启动。若 h4资源不安全，记录 `not_run_by_resource_policy`，不启用OOC/BLR。

## 5.2 2D-vs-3D 比较

3D结果与最终 2D reference比较时，只使用归一化物理量：

```text
R/T/A/A_volume
n=0、S通道的m级功率
all n!=0 或 P通道的总泄漏功率
common x-z plane上的 E_y、H_x、H_z
normal flux
```

Primary Gate：

```text
max |delta R,T,A,A_volume|           <= 1e-4
selected E_y relative L2             <= 5e-3
selected H_x/H_z relative L2         <= 1e-2
main m-order power-weighted delta     <= 1e-3
3D n!=0 and P leakage aggregate       <= 1e-6
energy closure                        <= 1e-5
```

复杂振幅逐级相位继续保存为 diagnostic，但本 Review 不开发 channel repair，也不让其单独否决 P2。

选择逻辑：

```text
if 3D h5 passes:
    selected_3d_mesh = h5
elif h4.5 passes:
    selected_3d_mesh = h4.5
elif h4 is safely run and passes:
    selected_3d_mesh = h4
else:
    selected_3d_mesh = best_available_solver_stress_only
    P2 = fail
```

P2失败不会自动禁止 PC algebra diagnostic，但必须把后续 Hybrid结果标为 solver-stress，而不是物理资格。

---

# 6. V3-5：Hybrid direct M480，通道修复暂缓

在 `selected_3d_mesh` 上运行唯一的：

```text
5 nm / 1° / phi0 / S
Hybrid direct
M480
MPI8
same external keys as corresponding Full3D
same interfaces 10/110 nm
same propagation and exact traction model
```

禁止 M sweep、M960、移动接口或更换 traction/propagation 模型。

本阶段的 Hybrid integrated-physics Gate为：

```text
true residual                         <= 1e-9
projection                            <= 1e-8
exact traction                        <= 1e-8
R/T/A/A_volume delta vs Full3D        <= 1e-4
selected E overall relative L2        <= 5e-3
selected H overall relative L2        <= 1e-2
normal-flux relative delta            <= 1e-4
all-channel power-weighted aggregate  <= 1e-3
external key set                      exact
closure both                          <= 1e-5
```

逐通道 power/amplitude 继续完整导出，但分类为：

```text
channel_resolved_diagnostic_only
```

不得在本 Review 中修复 q-to-amplitude、相位参考面、S/P gauge 或弱通道 Gate。若 integrated-physics Gate通过，分类为：

```text
TASK039_V3_HYBRID_INTEGRATED_PHYSICS_PASS_CHANNEL_DIAGNOSTIC_PENDING
```

这足以作为 iterative solver 的 direct equation reference。

---

# 7. V3-6：先解决内存证据，再做长迭代

## 7.1 离线解析现有 10° h5 Hybrid direct telemetry

V2 h5 Hybrid direct已保存：

```text
memory_stages.jsonl
process_tree_samples.jsonl
memory_object_ledger.json
```

Codex必须先写离线解析器，把18个stage marker与process-tree samples对齐，输出：

```text
stage entry RSS/PSS/USS
stage exit RSS/PSS/USS
stage-local peak RSS/PSS/USS
increment from previous stage
objects created/destroyed
allocator high-water retained after object release
```

不得重跑旧10° case。该解析用于选择1°内存优化方向，不改变旧结果。

## 7.2 新1°运行必须真实持久化telemetry

Full3D、Hybrid direct、oracle和production iterative均必须保存：

```text
process_tree_samples.jsonl
memory_stages.jsonl
memory_object_ledger.json
```

缺一项不得声称阶段内存归因已完成。

## 7.3 允许的内存优化

按实际峰值阶段选择，优先级如下：

### M-A：显式销毁与生命周期缩短

在不改变数学结果的前提下，尽早销毁：

```text
QEP matrices
SLEPc EPS/ST/KSP workspaces
raw candidate eigenvectors
unused full-mode representations
temporary Gram/mapping arrays
streaming P/T assembly buffers
field-recovery前不再需要的modal objects
```

必须使用对象级 `destroy()`/release和focused leak tests，不能只调用 Python `del` 后声称内存已释放。

### M-B：QEP/modal preparation 与 solve 分进程

若对象销毁后 RSS high-water仍不下降，授权实现：

```text
process A: QEP + mode selection + compact modal/coupling packet → exit
process B: fresh process loads packet → FE/PC/outer solve
```

进程退出用于强制释放PETSc/SLEPc和allocator high-water。packet必须带完整SHA、dtype、shape、mode keys、beta、basis/coupling identity和source SHA；不得通过未验证的pickle执行任意代码。

### M-C：P/T流式组装

若峰值位于coupling阶段，允许按列块生成P/T并及时释放full mode objects；最终物理矩阵必须与ordinary path在小fixture上达到 `1e-12` 相对一致。

暂不授权owner-only modal Schur、distributed modal basis或modal matrix-free，除非上述三项实测均无法达到内存目标。

---

# 8. V3-7：先证明 block algebra，再重设计生产 PC

旧 h5 iterative结果中：

```text
modal residual  ≈ 4.86e-12
bottom residual ≈ 0.988
 top residual   ≈ 0.964
```

因此新设计必须把注意力放在 bottom/top side inverse。

## 8.1 Exact operator identity

对至少：

```text
3个确定性随机向量
物理RHS
一个direct-solution-derived residual
```

比较：

```text
assembled/direct Hybrid augmented elimination action
vs
exact monolithic matrix-free Hybrid action
```

并逐块报告：

```text
bottom
top
modal
P/T coupling
RHS
```

Gate：

```math
\frac{\lVert A_{assembled/eliminated}x-A_{matrix-free}x\rVert_2}
{\max(\lVert A_{assembled/eliminated}x\rVert_2,10^{-30})}
\le 10^{-10}.
```

若失败，视为实现bug，先修复，不进入PC候选。

## 8.2 Side contraction survey

对bottom/top分别测量：

```math
\rho_s(r)=\frac{\lVert r-A_sP_sr\rVert_2}{\lVert r\rVert_2}.
```

测试向量至少包含：

```text
physical side RHS
exact direct solution residual
4个固定seed随机向量
early-Krylov residual snapshots
```

对现有：

```text
ILU0 + dynamic DtN Woodbury
```

测试 fixed correction passes：

```text
1, 2, 4, 8
```

只做side microbenchmark，不运行6000步global solve。

## 8.3 Exact-side-LU oracle

构造诊断性：

```text
bottom exact side LU
top exact side LU
same modal Schur/block-LDU
same exact outer operator
outer FGMRES
```

该oracle禁止作为最终低内存结论，但必须回答：

```text
若exact-side oracle快速收敛：block-LDU algebra正确，旧PC弱
若exact-side oracle仍失败：modal Schur或block coupling有bug/不一致
```

Oracle Gate：

```text
outer residual <= 5e-9
bottom/top/modal residual <= 5e-9
iterations <= 100
no global Hybrid direct factor
physics matches Hybrid direct integrated outputs
```

通过分类：

```text
TASK039_V3_HYBRID_BLOCK_LDU_EXACT_SIDE_ORACLE_PASS
```

这是本 Review 最早应获得的PC正结果。

---

# 9. V3-8：有界生产PC候选漏斗

只有 operator identity和exact-side oracle通过后，才进入生产PC。

## 9.1 Candidate A：固定多次残差修正

从 side survey 选择 `2/4/8` 中最小且满足：

```text
median rho <= 0.2
worst rho  <= 0.5
```

的passes。若不存在，不运行global candidate A。

## 9.2 Candidate B：Krylov-accelerated side inverse

使用：

```text
side operator        = exact matrix-free endcap operator
side preconditioner  = current ILU0 + dynamic DtN Woodbury
side solver          = inner FGMRES/GMRES, zero initial guess
inner iteration set  = 8, 16, conditional 32
outer solver         = right FGMRES
```

先只做side microbenchmark；选择满足：

```text
median rho <= 0.1
worst rho  <= 0.3
```

的最小inner iteration。外层FGMRES允许可变/非线性preconditioner，但必须记录nested solver存在、inner iterations和总apply成本。

## 9.3 Candidate C：受控fill side factor

仅当Candidate B在32步仍不满足contraction时，允许一次小范围：

```text
ILU(1) or ILUT/drop-tolerance side factor
+ same DtN Woodbury
```

不得做大范围shift/drop/fill sweep。最多两个受控配置，先比较：

```text
factor NNZ/bytes
side contraction
setup/apply time
```

再决定是否运行一个global candidate。

## 9.4 Candidate选择

只允许一个生产候选进入最终全局长跑。优先级：

```text
A if contraction passes and cheapest
else B if contraction passes
else C if contraction passes
else stop with PC redesign negative
```

不得并行运行多个全局候选，也不得把max_it继续提高来代替PC质量。

---

# 10. V3-9/V3-10：最终 Hybrid iterative 正式资格

## 10.1 正式候选

```text
physical model                 = 5 nm / 1° / phi0 / S
mesh                           = selected_3d_mesh or explicitly labelled solver-stress mesh
M                              = 480
MPI                            = 8
outer                          = right FGMRES
restart                        = 90
hard max_it                    = 4000
initial guess                  = zero
reported/global/bottom/top/modal residual <= 5e-9
exact traction                <= 1e-8
external q identity           <= 1e-10
```

早期停止规则用于避免再次浪费数小时：

```text
iteration 100:  global residual should be < 0.5
iteration 500:  global residual should be < 0.1
iteration 1000: global residual should be < 1e-2
```

若明显长期停滞且side contraction证据已经显示候选失效，可受控提前终止并记录negative；不得自动增加到6000/10000。

## 10.2 数值 Gate

```text
KSP converged reason                 > 0
iterations                           <= 4000
five residuals                       <= 5e-9
projection                           <= 1e-8
exact traction                       <= 1e-8
external q                           <= 1e-10
recovery / canonical / fields        complete
R/T/A/A_volume and closure           finite/pass
iterative vs Hybrid direct integrated outputs pass
```

strict per-channel complex amplitude仍只作diagnostic。

## 10.3 内存 Gate

以同一1°、同一mesh、同一M480的Hybrid direct和Full3D direct为基准：

```text
minimum positive memory result:
    iterative RSS < 0.80 * Hybrid-direct RSS

strong memory result:
    iterative RSS < 0.70 * Hybrid-direct RSS

stretch result:
    iterative RSS < 0.60 * Hybrid-direct RSS
```

同时报告相对Full3D direct的节约。若数值收敛但未达到20%，分类为numerical pass/resource fail；不得将其写成完全成功。

最终正分类要求：

```text
TASK039_V3_HYBRID_PRODUCTION_PC_NUMERICAL_PASS
TASK039_V3_HYBRID_MEMORY_ADVANTAGE_AT_LEAST_20_PERCENT
```

二者同时成立时可写：

```text
TASK039_V3_1DEG_HYBRID_ITERATIVE_POSITIVE
```

---

# 11. Bug处理授权

Codex可自行定位和修复以下实现bug，无需等待额外审阅：

```text
2D/3D角度或符号映射错误
matrix-free/operator identity错误
block scatter/gather/ownership错误
P/T转置或共轭错误
modal Schur action与side inverse不一致
telemetry未落盘或stage/sample时间未对齐
对象destroy/lifecycle错误
输入/launcher/路径/schema错误
deterministic fixture中的shape/order错误
```

每次修复必须：

1. 保留原失败证据；
2. 添加最小复现或focused test；
3. 只修窄范围；
4. 通过serial/MPI focused tests和diff-check；
5. 只重跑受影响候选一次；
6. 及时commit并push。

以下不是bug，不能通过静默调参掩盖：

```text
2D/3D真实离散误差
side PC contraction不足
PC因子内存过大
outer FGMRES不收敛
Hybrid direct integrated physics不一致
资源峰值未达到20%节约
```

---

# 12. 测试与证据

正式PDE前必须完成：

```text
2D/3D angle and plane-wave identity tests
2D TE material/port normalization tests
operator identity tests
side contraction deterministic fixtures
exact-side oracle small fixture
telemetry alignment and object-destroy tests
modal packet serialization hash/shape tests if process separation used
ordinary defaults unchanged tests
```

静态检查：

```text
ruff check
ruff format --check changed files
python -m compileall src benchmarks scripts
git diff --check
benchmarks/check_benchmarks.py --no-write
```

本研究分支不要求每个阶段运行全仓pytest；最终P4通过后再运行一次Task39 focused suite和必要MPI tiny tests。未经后续审阅不得merge master。

---

# 13. 最终交付

至少创建：

```text
docs/task039_5nm_hybrid_qualification_and_0p7nm_feasibility/outcomes/v3_2d_te_reference.md
docs/task039_5nm_hybrid_qualification_and_0p7nm_feasibility/outcomes/v3_2d_3d_identity.md
docs/task039_5nm_hybrid_qualification_and_0p7nm_feasibility/outcomes/v3_hybrid_direct_integrated_validation.md
docs/task039_5nm_hybrid_qualification_and_0p7nm_feasibility/outcomes/v3_side_inverse_oracles.md
docs/task039_5nm_hybrid_qualification_and_0p7nm_feasibility/outcomes/v3_pc_candidate_funnel.md
docs/task039_5nm_hybrid_qualification_and_0p7nm_feasibility/outcomes/v3_memory_lifecycle_and_process_split.md
docs/task039_5nm_hybrid_qualification_and_0p7nm_feasibility/outcomes/v3_final_iterative_result.md
docs/task039_5nm_hybrid_qualification_and_0p7nm_feasibility/response_v4.md
```

最终 response必须明确区分：

```text
2D continuum/reference qualification
3D discretization qualification
Hybrid integrated-physics qualification
strict channel-resolved diagnostic
block-LDU oracle qualification
production PC qualification
memory qualification
```

完成V3-10后停止等待审阅。禁止自行进入P偏振、非零方位角、0.7 nm、M>480、neural factor或master merge。
