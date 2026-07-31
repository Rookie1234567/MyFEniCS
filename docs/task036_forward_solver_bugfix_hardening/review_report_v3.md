# Task036 Review Report V3：强 trace-subspace Hybrid 重构与优势保持判定

## 1. 审阅身份与最终决策

```text
review = Task036 Review V3
branch = codex/20260730-task36-forward-solver-bugfix-hardening
reviewed_head = 02b3380e8e98ac10bf3dd4fba470da80aa4168bc
ordinary_default = unchanged
master_merge = not_authorized
next_numerical_action = implement_strong_trace_subspace_hybrid_m120
```

Review V2 的五个同输入 Full3D/Hybrid 对照已经重复暴露同一根因：当前 Hybrid 只约束
有限元界面的 M 个模态投影坐标，未消除投影算子看不见的 trace complement。继续扩大
角度/几何扫描或继续提高 M，不会修复这个结构问题。

本审阅批准把当前弱投影式耦合：

```text
D_s g_s = L_s a
```

改为强 approximation-space restriction：

```text
g_s = R_s L_s a
```

其中：

- `g_s`：bottom/top 局部 FEM 在内部接口上的真实 H(curl) 切向 trace；
- `R_s`：由 right waveguide modes 形成的物理 trace prolongation；
- `D_s`：由 left modes 和 trace mass/Gram 构造的 Petrov projection；
- `L_s`：将正向/反向内部模态系数传播到该接口的已有映射；
- `a`：全局内部模态振幅。

这不是给旧矩阵再加一层 penalty，也不是形成稠密 `R_s D_s` projector，而是直接改变
Hybrid 的 trial/test space，使接口 trace 自始至终只能位于保留模态张成的空间内。

审阅结论：

```text
can_preserve_hybrid_advantage = yes, structurally
accuracy_advantage = not_yet_measured
memory_advantage = plausible_but_requires_actual_factorization
recommended_route = proceed
fallback_if_failed = Full3D_static_condensed_iterative
```

---

## 2. 为什么这个改动仍然是 Hybrid，而不是退回 Full3D

Hybrid 的核心优势来自两点：

1. 100 nm 级中间传播区仍由二维横截面模态和解析/离散轴向传播表示，不重新铺设完整
   三维体网格；
2. 上下端部的三维 FEM 只保留局部复杂区域。

强 trace restriction 不会恢复中间区域的三维单元，也不会把所有中间场自由度重新加入
系统。它只改变两个内部接口的连接方式：从“比较 M 个投影系数”改为“直接以 M 个模态
系数参数化完整接口 trace”。

因此，中间体积消除这一最大降维来源仍然完整保留。

当前实测 M120 结果已经给出资源余量：

| point | Full3D peak GiB | current Hybrid M120 peak GiB | reduction |
|---|---:|---:|---:|
| p5 A001-P | 10.092 | 7.212 | 28.5% |
| p5 A004-P | 10.516 | 7.450 | 29.2% |
| p5 A004-S | 10.549 | 7.464 | 29.2% |
| p5 A049-P | 10.228 | 7.131 | 30.3% |
| p6 D001-P | 18.572 | 11.222 | 39.6% |

这些旧 Hybrid 结果数值不合格，但证明“仅保留端部 FEM + M120 中间模态”在当前规模下
确实具有明显内存优势。新 formulation 不应恢复被删去的中间体积，因此有现实余量保持
该优势。

---

## 3. 结构自由度与矩阵规模

### 3.1 当前增广系统

当前每个端部系统保留完整局部未知量，包括内部接口 trace。记：

```text
n_b, n_t = bottom/top local system rows，包含内部接口 trace 和外部 DtN auxiliary
g_b, g_t = bottom/top 内部接口的独立 trace rows
M        = 每个传播方向保留的内部模态数
```

当前增广系统规模为：

```text
N_old = n_b + n_t + 2M
```

它同时保留 `g_b/g_t`，再增加 2M 个内部模态未知量。M 个投影方程只能控制 trace 的
M 个坐标；当 `g_s > M` 时，仍存在 `ker(D_s)` complement。

### 3.2 强 trace-subspace 系统

将局部未知量拆成：

```text
u_s = [v_s, g_s]
```

其中 `v_s` 包含除内部接口 trace 外的所有局部未知量。强制：

```text
g_s = R_s L_s a
```

后，接口 trace 不再是独立未知量，理想规模为：

```text
N_new = (n_b - g_b) + (n_t - g_t) + 2M
```

因此在不增加 Lagrange multiplier 的前提下：

```text
N_new = N_old - g_b - g_t
```

结构行数必然不高于当前 M120 增广系统，而且通常会更低。

### 3.3 不得形成稠密接口平方算子

禁止显式形成：

```text
R_s D_s             # N_gamma x N_gamma
I - R_s D_s
penalty * (I-RD)^H(I-RD)
```

允许的块只有：

```text
A_vg R_s L_s
W_s^H A_gv
W_s^H A_gg R_s L_s
small 2M x 2M propagation/traction block
```

其中 `R_s/W_s` 是 `N_gamma x M` 分布式列，`M=120` 时小型 `M x M` 复矩阵每块仅
约 0.22 MiB。真正需要测量的是稀疏直接分解的 fill，而不是担心小型 modal block 本身。

---

## 4. 数学 formulation：必须是方形 Petrov–Galerkin 限制，不是过约束

### 4.1 trial space

对 bottom/top 两个局部系统，构造 trial transform `T_R`：

- 非内部接口局部 unknown：identity；
- 外部 DtN auxiliary：identity；
- 内部接口 trace：由 `R_s L_s a` 给出；
- 内部 modal amplitudes：保留 2M 个全局 unknown。

### 4.2 test space

不能在替换 trace unknown 后仍保留全部原接口 FE test rows，否则会形成不平衡或重复约束。

构造 left/Petrov test transform `T_L`：

- 非接口 FEM test rows 保留；
- 原 `g_s` 个接口 test rows由 M 个 left modal trace test rows替代；
- left trace 使用当前 `ModalTraceProjection.left_traces` 与 trace mass/Gram 合同；
- lossy、非自伴问题不得把 `T_L` 偷换成 `T_R` 或简单共轭转置。

最终 reduced operator 的概念形式为：

```text
A_reduced = T_L^H A_uncoupled_with_modal_traction T_R
b_reduced = T_L^H b
```

但实现不得先装配巨大 full transform，也不得对当前错误的投影增广矩阵直接做二次投影。
应从 bottom/top local FEM、existing traction columns、right traces、left traces 和 propagation
blocks直接装配所需 reduced blocks。

### 4.3 flux/traction continuity

丢弃的接口 FE rows不能被简单删除。它们必须通过 left modal test space形成 M 个
variational flux-equilibrium rows：

```text
W_s^H * (local interface FE residual + modal traction action) = 0
```

这使：

- electric trace 通过 trial-space restriction 强连续；
- magnetic/traction continuity 通过 left-modal Petrov rows弱式满足；
- 系统保持方形；
- 非自伴 modal biorthogonality仍被正确使用。

---

## 5. 为什么现有代码不是从零开始

当前仓库已经具有关键材料：

1. `ModalTraceProjection`
   - `right_traces = Q_gamma`；
   - `left_traces = W_gamma`；
   - trace mass `B_gamma`；
   - Gram `G = W^H B Q`；
   - `reconstruct()` 与 `project()` round trip；
   - 明确禁止 dense `N_gamma x N_gamma` interface operator。

2. `HybridInternalModeCoupling`
   - bottom/top projection `D_s`；
   - positive/negative traction columns；
   - propagation factors；
   - positive/negative trace map；
   - static-condensation interior corrections。

3. `HybridLocalDtnSystem`
   - standard/static 两种 local FEM system；
   - external sparse auxiliary DtN；
   - static-condensation row maps和field recovery。

4. Task036 已修复
   - P tangential projection；
   - exact traction dual；
   - propagation/traction/reconstruction beta；
   - near-degenerate connected-component normalization；
   - lifecycle和memory authority。

因此下一步是重组已有数值块，而不是新建另一套 mode solver、campaign或telemetry框架。

---

## 6. 实现路线

### Phase A：exact-trace 小型 fixture

先在小型匹配接口 fixture 上完成，不运行正式重型 PDE。

必须证明：

```text
D_s R_s = I_M                         within 1e-10
trace(given a) = R_s a                within 1e-10
complement q with D_s q = 0           cannot enter restricted trial space
Floquet slave/orientation residual    within existing Gate
standard/static restricted algebra    equivalent
no dense interface square             true
```

fixture必须包含：

- S 与 P mode；
- 非零 `E_z` 的 P mode，但只使用 H(curl) tangential trace；
- top/bottom相反法向；
- complex/lossy material；
- MPI1/2，随后一个MPI8 micro-fixture。

### Phase B：接口 row/column map

为每个 `HybridLocalDtnSystem` 构造：

```text
internal_interface_rows
noninterface_rows
trial_right_trace_columns
petrov_left_trace_columns
propagation_to_side
```

要求：

- index dtype使用 `PETSc.IntType`；
- standard与assembly-time static condensation都使用各自实际row identity；
- static路径不得把full FE dof id误当成condensed active row；
- Floquet slave不能重新成为独立row；
- external DtN auxiliary不被误删；
- bottom/top接口row count和trace-space dimension必须写入record。

### Phase C：直接装配 strong-trace reduced system

新增一个清晰的research入口，例如：

```text
build_hybrid_strong_trace_direct_system(...)
solve_hybrid_strong_trace_direct(...)
```

可以放在现有Hybrid solver模块或一个单独、职责明确的solver文件；禁止复制整个runner。

装配要求：

- 从local FEM和现有modal coupling blocks直接生成reduced matrix；
- 不先构造旧的projection-only monolithic matrix再修补；
- 不形成 `R D` dense square；
- M120保持冻结；
- ordinary default不改变；
- existing projection-only path保留为历史对照，不能被静默覆盖。

### Phase D：true residual与field recovery

新 formulation 的 residual必须分成：

```text
noninterface_local_FE_residual
modal_Petrov_flux_residual
strong_trace_identity_residual = ||g - RLa||
external_DtN_residual
```

不得继续用已经被替换的全部接口 FE rows冒充new-system true residual。

field recovery必须直接把 `R_s L_s a` 写回物理接口trace，再恢复局部cell interior；禁止
从projection-only carrier恢复出新的自由complement。

---

## 7. 首轮实际 PDE：只跑三个 anchor

强trace fixture和MPI micro-fixture通过前，不恢复226点扫描。

固定：

```text
p = 5
h = 10 nm
Ny = 4
M = 120
backend = assembly-time static condensation
MPI = 8
```

按顺序运行：

```text
1. A004-S : grazing 0.5°, azimuth 45°, S
2. A049-P : grazing 10°,  azimuth 90°, P
3. A001-P : grazing 0.5°, azimuth 0°,  P
```

全部复用现有same-input Full3D authority，不重跑Full3D，除非hash/input identity无法闭合。

### 7.1 数值Gate

```text
reduced true residual                       <= 1e-9
strong trace identity residual              <= 1e-10
modal Petrov traction residual              <= 1e-8
biorthogonality row norm                    <= 1e-6
direct tangential projection difference     <= 1e-10
abs(R + T + A_volume - 1)                  <= 1e-5
same-p Full3D max(|Delta R/T/A|)            <= 1e-4
fixed-channel amplitude/power contract       pass
zero swap                                    true
```

sampled physical interface jump继续作为diagnostic，但不能替代strong trace coefficient
identity与variational residual。

### 7.2 Hybrid优势Gate

除数值精度外，必须同时报告：

```text
old Hybrid M120 rows / NNZ / factor / peak
new strong-trace rows / NNZ / factor / peak
same-point Full3D rows / NNZ / factor / peak
```

分类：

```text
HYBRID_STRONG_TRACE_ADVANTAGE_PASS
    accuracy pass
    and peak memory <= 0.85 * Full3D peak

HYBRID_STRONG_TRACE_FUNCTIONAL_SMALL_ADVANTAGE
    accuracy pass
    and 0.85 < peak memory / Full3D peak < 1.0

HYBRID_STRONG_TRACE_FUNCTIONAL_NO_ADVANTAGE
    accuracy pass
    but peak memory >= Full3D peak

HYBRID_STRONG_TRACE_TRUNCATION_FAIL
    strong trace algebra pass
    but M120 accuracy fails

HYBRID_STRONG_TRACE_IMPLEMENTATION_FAIL
    trace identity / residual / orientation / energy identity fails
```

`15%` memory reduction是工程资格线，不是数学定理；原M120已有约28%–40%余量，因此该
门槛现实且能防止“数值能算但已失去Hybrid价值”被写成成功。

---

## 8. 是否允许增加M

首轮固定M120，不能在strong-trace实现尚未证明前继续用M掩盖错误。

若：

```text
A004-S和A049-P均通过
A001-P仅有明确的modal truncation error
new M120 peak仍明显低于Full3D
```

则最多允许一个 `M160` 低掠射P检查。M160必须通过资源preflight，并且预计peak仍低于
same-point Full3D；否则不运行。

禁止恢复M240/M480/M492漏斗。历史数据已经表明高M会耗尽Hybrid资源优势。

---

## 9. 如果强 trace restriction仍失败，下一步是什么

### 9.1 第一生产备选：Full3D static-condensed iterative

若strong trace algebra正确但M120/160仍不能满足精度或资源优势，立即停止Hybrid当前
production路线，转入：

```text
Full3D assembly-time static condensation
+ FGMRES
+ H(curl)/trace-aware preconditioner
```

这是对所有S/P和角度最稳妥的主线。

### 9.2 第二研究备选：optimal/transfer port basis

如果物理waveguide eigenmodes在低掠射P下需要过多模式，可另立后续任务，用局部
transfer eigenproblem或snapshot-based optimal port space代替单纯按beta选取的QEP modes。
这类port-reduced static condensation方法的目标正是以更少接口basis逼近局部PDE的
trace range。

该方向不属于本轮实现；只有strong trace证明“耦合结构已正确、瓶颈确实是basis效率”后
才值得启动。

### 9.3 不优先的方法

本轮不采用：

- penalty / Nitsche complement suppression：保留全部interface rows并引入参数；
- full-dimensional mortar multiplier：增加interface unknown，削弱降维；
- explicit dense projector `R D`：产生 `N_gamma^2` 存储；
- 继续增加M到近full rank：已显示可能比Full3D更贵；
- 人工energy correction：不能修复trace空间错误。

### 9.4 可选几何折中

若high-grazing通过而low-grazing P只在高M下失败，可在未来测试缩短modal middle、扩大
上下local FEM区域。该方案可能降低所需M，但会增加3D体积，必须按资源Pareto判断；不能
自动视为Hybrid成功。

---

## 10. 文献定位

本次改动不是无依据的新发明，而是与以下思路一致：

1. Orlandini, Devloo and Hernández-Figueroa, *A Waveguide Port Boundary Condition Based
   on Approximation Space Restriction for Finite Element Analysis*, arXiv:2407.21766。
   其核心是将端口自由度直接关联到waveguide modes，通过限制approximation space减少端口
   DoF，而不是只在完整trace空间上附加modal projection。

2. Smetana and Patera, *Optimal Local Approximation Spaces for Component-Based Static
   Condensation Procedures*, SIAM J. Sci. Comput. 38 (2016), DOI:10.1137/15M1009603。
   该工作说明port/interface approximation space可以与static condensation结合，接口维数
   是决定component reduction效率的关键。

3. Buhr and Smetana, *Randomized Local Model Order Reduction*, SIAM J. Sci. Comput. 40
   (2018), DOI:10.1137/17M1138480。若物理QEP modes不足，transfer-operator port basis是后续
   可考虑的系统化替代。

---

## 11. Codex执行边界

本轮允许修改真正需要修改的数值核心，但禁止把工作转化为新的管理框架。

允许：

- 新增一个职责明确的strong-trace solver模块；
- 扩展现有matched-trace/interface mapping；
- 增加必要的standard/static/MPI测试；
- 修复实现过程中由actual fixture/PDE暴露的真实orientation、row-map或recovery bug。

禁止：

- 新campaign engine、state machine、receipt/hash framework；
- 复制现有Task036 runner形成第二套大型runner；
- 在fixture未通过前启动226点扫描；
- 放宽数值Gate；
- 静默替换ordinary Hybrid默认；
- 自行merge master。

开发原则：

```text
先写最小代数fixture
-> 再实现真实interface row map
-> 再装配一个strong-trace system
-> 再跑三个anchor
-> 根据结果决定恢复扫描或转Full3D iterative
```

---

## 12. 交付要求

更新/新增：

```text
docs/task036_forward_solver_bugfix_hardening/outcomes/
    strong_trace_hybrid_implementation.md
    strong_trace_hybrid_anchor_results.md

benchmarks/cases/<new_case_or_task_local_fixture>/
    compact exact-trace fixture records
```

结果文档必须包含：

- old projection-only与new strong-trace的方程对照；
- exact interface row counts `g_b/g_t`；
- old/new/Full3D rows、NNZ、factor、peak；
- `D R` identity；
- trace identity与Petrov flux residual；
- 三个anchor全部observable；
- S/P分类；
- 是否保持>=15%内存优势；
- 未解决问题与下一路线。

最终提交只推送当前Task036远程同名分支，停止等待下一次Review。
