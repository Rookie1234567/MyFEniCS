# Task038-extra Review Report V12：三路线层次选择、正信号持续强化与失败后的有界下一 PC 候选

## 0. 审阅身份与最终决定

```text
review                                  = Task038-extra Review Report V12
repository                              = Rookie1234567/MyFEniCS
reviewed_branch                         = codex/20260820-task38-extra-full3d-iterative-0p7nm
reviewed_HEAD                           = 19fe517f2325763756464b66bc6bee6608267c3b
base_master_SHA                         = 438caf150439343ee7c4c58ad7e02a3da812a23c
branch_vs_master_at_review              = ahead 137 / behind 0
reviewed_response                       = docs/task038_extra_full3d_iterative_0p7nm/response_v11.md
reviewed_previous_review                = docs/task038_extra_full3d_iterative_0p7nm/review_report_v11.md
working_branch_continues                = yes; same branch only
new_branch_or_worktree                  = forbidden
whole_branch_merge_to_master            = forbidden
V11_S1_global_structure                 = ACCEPTED_PASS
V11_S2_p6_foundation_resource           = ACCEPTED_PASS
V11_S4_small_geometric_edge_MG          = ACCEPTED_PASS_AT_SMALL_ORACLE_SCOPE
V11_S5_resource                         = ACCEPTED_PASS
V11_S5_exact_energy_gate                = ACCEPTED_FAIL_UNDER_OLD_CONTRACT
old_lor_edge_geometric_mg_v1            = CLOSED_UNDER_EXACT_ENERGY_CONTRACT
LOR_foundation                          = REMAINS_POSITIVE
current_primary_blocker                 = p6 interlevel hierarchy qualification
primary_objective                       = final correctness under bounded memory
iteration_count_and_wall_time           = secondary
production_Krylov                       = right-preconditioned GMRES
production_restart                      = 20, fixed
residual_replacement_period             = 20 iterations, fixed
positive_auxiliary_max_it               = 10000, fixed
physical_Maxwell_max_it                 = 20000, fixed
continuous_authorized_batch             = R0 through R12 below, with fixed branches
mandatory_review_stop                   = after R12 or any earlier terminal hard stop
full_0p7nm_PDE                          = forbidden
ordinary_default_change                 = forbidden
master_merge                            = forbidden
response_required                       = response_v12.md
```

本 Review 继续服从唯一长期目标：

> 在单节点约 2 TiB 物理内存内，以自主 FEniCS/DOLFINx、complex128、Nédélec `H(curl)`、双 Floquet 和 Fourier-DtN，最终求解 0.7 nm 周期单胞内任意非可分三维 Maxwell 散射问题。

用户已明确本阶段的优先级：

```text
第一优先级 = 在有界内存内得到最终正确解
第二优先级 = 缩短迭代次数与耗时
```

因此 V12 不再用几十或几百步的性能窗口单独否定一个最终可收敛的方法；但仍为每条候选冻结有限的总迭代上限、资源硬线和唯一分支，防止形成开放式参数搜索。

本轮依次尝试三条主路线：

```text
路线 A：保留非嵌套 6→3→1，但改用层间谱等价资格
路线 B：若 A 不合格，改用节点嵌套的 6→2→1
路线 C：若 A、B 均不合格，正式关闭当前 LOR-edge p-level MG，
        自动转入两个有界的新 PC 候选；出现正信号即继续强化
```

V12 不允许在同一失败点无限生成 `v3/v4/v5`。全部候选、顺序、Gate 和终止条件均在下文预先冻结。

---

# 1. 对 V11 最新结果的审阅

## 1.1 接受的结构与资源正结果

V11 S1 已建立：

| case | independent rows | transfer rank | generalized condition |
|---|---:|---:|---:|
| p2/h50/MPI1 | 768 | 768 | `53.37253952072989` |
| p3/h50/MPI1 | 2538 | 2538 | `14173.652247500142` |

两案的 work、Hermitian、SPD、rank 与 eigen residual Gate 均通过。p3 的 condition 明显高于 p2，是性能警告，但不是秩亏或基础代数失败。

V11 S2 已实测 p6/h10 foundation：

```text
high/low rows             = 173,802 / 173,802
B_L NNZ                   = 5,825,468
cold process-tree peak    = 983,363,584 B
retained external peak    = 983,363,584 B
process-tree/rank swap    = 0 B
headroom to 2 GB          = 1,016,636,416 B
```

V11 S5 在保留 `6→3→1` 三层矩阵、transfer、Chebyshev work 和 `restart=20` reserve 后实测：

```text
cold/retained-window peak = 1,207,476,224 B
swap                      = 0 B
```

因此接受以下架构结论：

> p6/h10 的 matrix-free high-order action、streaming DtN、LOR edge foundation、三层低阶矩阵、局部 transfer 和固定 restart20 工作空间，在当前锚点上具有明显低于 2 GB 的真实 live-set 窗口。

## 1.2 接受的 S4 数值正结果

固定 small oracle 在：

```text
p2/p3
MPI1/MPI2
random / gradient / curl / checkerboard
right GMRES / restart20
```

下达到 16/16 individual PASS 和 8/8 MPI pair PASS。p2 为 60 步；p3 为 1880–2960 步。V12 接受其为：

```text
LOR-edge geometric MG small-case positive signal
```

但不把它外推为 p6 solver、物理 Maxwell 或 0.7 nm production pass。

## 1.3 旧 S5 negative 永久保留

V11 S5 的旧合同要求 rediscretized coarse energy 与 fine-prolongated energy达到机器精度一致：

```text
energy_6_to_3 = 0.04115402900674629 > 1e-9   FAIL
energy_3_to_1 = 2.7851655955739857e-15       PASS
```

旧 `lor_edge_geometric_mg_v1` 在该合同下继续保持关闭，不能删除、覆盖或重新分类。

同时，当前 6→3 transfer 的其他指标为：

```text
edge line-integral relative  = 1.64912117993347e-15
curl-flux relative           = 3.017621245046702e-15
gradient commuting relative  = 1.6885078710167433e-14
local adjoint work relative   = 4.803162573733104e-16
global adjoint work relative  = 1.2865066317766304e-14
linearity relative            = 3.0795110632853766e-16
repeat relative               = 0
```

这些事实不支持 orientation、Floquet phase、MPC owner routing 或伴随实现存在明显错误。Supplemental diagnosis 已发现 p6 与 p3 GLL/LOR nodes 非嵌套；因此 V12 将新 prospective 资格从“单向量 exact energy identity”改为“全局可推广的层间谱等价”。这不会重写旧 negative。

---

# 2. 为什么 non-Galerkin coarse level 应检查谱等价

对 fine level 正定辅助矩阵 `B_f`、coarse level rediscretized矩阵 `B_c` 和 prolongation `P`，Galerkin coarse operator 为：

```math
B_c^{G}=P^H B_f P.
```

只有当实际 coarse operator 就是 `B_c^G` 时，才自动满足：

```math
x^H B_c x=(Px)^H B_f(Px)
```

到舍入误差量级。

当前 p3 coarse operator 是在独立 p3 LOR 网格上 rediscretized 的，而 p6/p3 GLL nodes 并不严格嵌套。因此 V12 的 prospective hard authority 改为：

```math
c\,x^H B_cx
\le
x^H P^H B_fPx
\le
C\,x^H B_cx,
```

其中 `c>0` 且 `C/c` 有界。

旧 deterministic energy relative `0.041154...` 继续报告，但不再单独决定新 v2 的合法性。新 v2 必须通过完整材料 class 的 generalized Hermitian spectrum，而不是靠一个向量或事后放宽到 `5%`。

---

# 3. 全局不变量和禁止项

## 3.1 冻结的 exact fine operator

所有 p6 正式运行继续使用：

```text
full-space p6 Nedelec fine space
matrix-free Maxwell volume action
streaming Fourier-DtN
finalized dual Floquet MPC exactly once
complex128
13.5 nm frozen development physics
```

预条件器变化不得改变 exact `A`、RHS、材料、DtN mode identity、input hash 或 physical model hash。

## 3.2 固定 Krylov 生命周期

```text
right-preconditioned GMRES
restart = 20
zero initial guess for each fresh formal
explicit unpreconditioned true residual is authority
residual replacement every 20 iterations
completed-cycle KSP/Krylov basis destroyed before next cycle
solution-only checkpoint every 500 iterations
no Krylov basis in checkpoint
```

允许通过增加 restart cycles 换取最终正确性，但不得提高 restart。

## 3.3 禁止恢复或扫描

```text
old HX + scalar PCGAMG
additive HX v2
new HX v3/v4
omega scan
shift scan
GAMG option scan
Chebyshev degree scan
pre/post sweep count scan
restart scan
FGMRES/GCROT/LGMRES/BiCGStab campaign
old slab/transmission/trace-harmonic/local-spectral families
high-order global AIJ
FE-sized numeric allgather
global dense transfer
p6 exact edge factor
global direct factor as production requirement
```

## 3.4 当前开发锚点的 p1 direct oracle边界

在 p6/h10 当前锚点中，p1 level 只有约 `1067` rows。V12 允许使用一个 fresh、hash-bound 的 p1 exact sparse factor作为**数值 oracle coarse solve**，前提是：

```text
只用于当前 p6/h10 MPI1/MPI2 qualification
记录 factor bytes、setup peak和lifecycle
不用于 p6 fine level
不写成0.7 nm production coarse solver
在release/recovery前销毁
```

任何借助该 oracle得到的 p6 pass必须标注：

```text
numerical/physics authority pass with coarse-scalability qualification
```

不能称为最终 0.7 nm production architecture pass。

---

# 4. 执行总览与唯一分支顺序

```text
R0  冻结 V11 证据与新 prospective contract
R1  路线 A：6→3 local/global spectral-equivalence audit
R2  条件路线 A p6 hierarchy + positive qualification
R3  路线 B：6→2→1 nested hierarchy audit
R4  条件路线 B p6 hierarchy + positive qualification
R5  路线 C：若 A/B 均失败，关闭 current LOR-edge p-level MG
R6  条件 fallback C1：same-mesh H(curl) p-multigrid
R7  条件 fallback C2：nested LOR-edge h-multigrid
R8  对第一条通过 p6 positive Gate 的 hierarchy运行 physical Maxwell MPI1
R9  条件 bounded Floquet/near-cutoff deflation强化
R10 条件 physical MPI2、release/recovery与official physics
R11 条件 h5 setup-only scaling和0.7 nm/2 TiB容量更新
R12 outcomes、response_v12.md、提交推送并停止
```

顺序是硬合同：

1. 先尝试 A；
2. A 的结构、资源或 p6 positive任一失败时才进入 B；
3. A 或 B 一旦完整通过 p6 positive四类 source，选择该 hierarchy，不再继续比较另一条；
4. A、B 均失败才进入 C；
5. C1 出现合格正信号即继续强化，不再运行 C2；
6. C1 明确失败才运行 C2；
7. C2也失败时终止本轮，不得自行发明第五个候选。

---

# 5. R0：证据冻结和 prospective contract

R0 只做文档、checker contract和轻量单元测试准备，不运行 heavy job。

必须永久保留：

```text
V10 Q0 500-step negative
foundation-E 3020-step PASS
old global SLEPc nonconvergence
HX/PCGAMG closure
V11 S1/S2/S4 PASS
V11 S5 exact-energy FAIL
ba40358 invalid-probe archive
```

必须创建新的 prospective schema；不得修改旧 S5 record/checker中的 threshold或status。

推荐新增：

```text
docs/task038_extra_full3d_iterative_0p7nm/outcomes/interlevel_route_selection_v1.md
docs/task038_extra_full3d_iterative_0p7nm/outcomes/records/interlevel_route_selection_v1.json
```

---

# 6. 路线 A：`lor_edge_geometric_mg_6_3_1_spectral_v2`

## 6.1 它解决什么问题

路线 A 保留 V11 已完成的：

```text
level 6 LOR edge matrix
level 3 rediscretized LOR edge matrix
level 1 rediscretized LOR edge matrix
6→3 line-integral/histopolation transfer
3→1 transfer
fixed Chebyshev smoothers
```

只替换错误的 prospective certification：

```text
旧：要求 non-nested rediscretized energy machine-identity
新：要求材料 class 和全局 probe 上的 uniform spectral equivalence
```

## 6.2 R1 local material-class audit

使用与 p6/h10 物理身份一致的全部正定辅助系数 class，至少包括：

```text
air
formal grating/material class
formal substrate class
任何不同 |epsilon| 或 geometry Jacobian class
```

对每个 class构造 cell-local：

```math
G_{63}=P_{63}^H B_6 P_{63},
```

并求：

```math
G_{63}v=\lambda B_3v.
```

必须使用 deterministic dense Hermitian solver，不得依赖 iterative endpoint luck。每个 coarse cell local dimension为144，允许 audit-only dense objects；这些对象不得进入 p6 retained hierarchy。

每个 class必须保存：

```text
class digest
material/coefficient identity
geometry/Jacobian identity
rank(P63)
sigma_min(P63)
sigma_max(P63)
Hermitian defects of B3 and G63
minimum eigenvalue of B3 and G63
lambda_min
lambda_max
spectral condition
smallest/largest eigen residual
```

### 路线 A prospective hard Gate

```text
rank(P63)                        = 144
Hermitian defects                <= 1e-12
B3 and G63                       = strict SPD
smallest/largest eigen residual  <= 1e-10
lambda_min                       >= 0.10
lambda_max                       <= 10.0
lambda_max/lambda_min            <= 100
finite                           = true
```

这些宽松但有限的 bounds服务于“最终正确性优先”：它们不要求快速收敛，但排除近零 coarse direction和数量级爆炸。

## 6.3 orientation、Floquet 和 global probe

不得对所有 cell 重复 dense eigenproblem。orientation/permutation由局部 signed permutation identity验证；Floquet/MPC由已有 owner-local route验证。

在 p6/h10 MPI1 上至少使用固定：

```text
random
gradient
curl
checkerboard
physical-component-derived coarse probe
R3-long-tail-derived coarse probe
```

共不少于6个 coarse owner probes，记录：

```math
q(x)=\frac{(P_{63}x)^HB_6(P_{63}x)}{x^HB_3x}.
```

每个 `q(x)` 必须处于 `[0.10,10.0]`；adjoint、linearity、repeat、finite、input-unchanged和phase-once继续通过。

## 6.4 路线 A 的决策

若 R1 全部通过：

```text
candidate = lor_edge_geometric_mg_6_3_1_spectral_v2
old S5 negative = preserved
new prospective status = STRUCTURALLY_QUALIFIED
```

随后执行 R2。

若任一 hard Gate失败：

```text
route_A = CLOSED_BY_INTERLEVEL_SPECTRAL_GATE
```

保存最坏 class/eigenvector和数值后立即进入路线 B；不得调整 `[0.10,10]` 或 condition `100`。

---

# 7. R2：路线 A 的 p6 资源与正定最终求解

## 7.1 fresh hierarchy setup

必须在新 source SHA 和新 artifact root 下重建，不复用旧 S5 root。

固定：

```text
levels = 6→3→1
one pre + one post Chebyshev/Jacobi smoother
Chebyshev degree = 3
power steps = 10
one V-cycle per PC apply
p1 exact sparse solve = current-anchor oracle only
restart reserve = 21 basis + 4 auxiliary vectors
```

资源 Gate：

```text
cold process-tree peak  < 2,000,000,000 B
retained-window peak    < 1,800,000,000 B
process-tree/rank swap  = 0 B
no repeated RSS growth
```

## 7.2 p6 positive qualification

顺序运行：

```text
random
then gradient
then curl
then checkerboard
```

每案固定：

```text
right GMRES
restart = 20
max_it = 10000
residual replacement = 20
checkpoint = 500
final explicit true residual <= 1e-8
```

性能里程碑只记录，不作 hard Gate：

```text
20 / 100 / 200 / 500 / 1000 / 2000 / 5000 / 10000
```

若 random失败，立即关闭路线 A并进入 B；无需运行其余三案。若后续任一案失败，也关闭 A并进入 B。

若四案全部通过且完整 live workflow低于2 GB：

```text
route_A = POSITIVE_AUXILIARY_PASS
selected_hierarchy = 6→3→1 spectral-v2
```

随后跳过 B/C，进入 R8。

---

# 8. 路线 B：`lor_edge_geometric_mg_6_2_1_nested_v1`

## 8.1 为什么只测试 6→2→1

p2 的 GLL node set包含端点和中心点；p6 的对称 GLL node set包含同一中心点。因此 `6→2` 具有明确的 nested-node候选，而 `p2→p1` 已有 S4 的强正证据。

V12 只允许这一种替代 degree hierarchy；禁止继续扫描 `6→4`、`6→5` 或任意自选 degree。

## 8.2 R3 local algebra

固定 local shapes：

```text
6→2 edge map = 882 × 54
6→2 node map = 343 × 27
2→1 edge map = 54 × 12
2→1 node map = 27 × 8
```

必须验证：

```text
nested coordinate subset identity
edge line-integral/histopolation
curl commuting
gradient commuting
adjoint work
linearity
repeat
input unchanged
orientation/permutation identity
```

对全部材料 class构造：

```math
G_{62}=P_{62}^H B_6P_{62},
```

并与 rediscretized `B_2`比较。

### 路线 B hard Gate

```text
rank(P62)                        = 54
Hermitian defects                <= 1e-12
B2 and G62                       = strict SPD
line/curl/gradient errors        <= 1e-11
global adjoint                   <= 1e-11
smallest/largest eigen residual  <= 1e-10
lambda_min                       >= 0.50
lambda_max                       <= 2.00
spectral condition               <= 4.00
nested energy relative           <= 1e-9
finite/input/repeat              = pass
```

路线 B 的 Gate比 A 更强，因为其数学依据就是 nested injection；若 nested energy仍不能闭合，应视为实现或离散身份不一致，不能再事后改用宽谱 Gate。

## 8.3 R4 p6 qualification

若 R3通过，构建 fresh：

```text
6→2→1
fixed degree-3 Chebyshev smoother on levels 6 and 2
one pre + one post
one V-cycle
p1 exact oracle coarse solve
restart20 reserve
```

资源与 p6 positive四类 source合同与 R2完全相同。

若四案通过：

```text
route_B = POSITIVE_AUXILIARY_PASS
selected_hierarchy = 6→2→1 nested-v1
```

进入 R8。

若结构、资源或任何 positive source失败：

```text
route_B = CLOSED
```

进入路线 C。

---

# 9. 路线 C：关闭当前 LOR-edge p-level MG，并继续两个有界候选

当且仅当 A、B均失败时，必须正式写入：

```text
lor_edge_geometric_mg_p_level_family
= CLOSED_AFTER_6_3_AND_6_2_QUALIFICATION
```

关闭范围包括：

```text
6→3→1 rediscretized p-level hierarchy
6→2→1 nested p-level hierarchy
继续扫描其他degree组合
```

这不关闭：

```text
matrix-free high-order action
streaming DtN
LOR foundation
memory-first Krylov lifecycle
same-mesh p-multigrid
nested custom h-coarsening
```

关闭后 Codex 不停止，而是按 C1→C2 的固定顺序继续。只要某条出现下文定义的正信号，就沿该路线继续强化。

---

# 10. R6 fallback C1：`same_mesh_hcurl_pmg_v1`

## 10.1 它解决什么问题

该路线不再把 p6 映射到不同 GLL refined meshes，而是在**同一物理 mesh**上的 Nédélec polynomial spaces之间做：

```text
p6 H(curl) → p3 H(curl) → p1 H(curl)
```

Nédélec polynomial spaces在同一 cell上具有嵌套关系，预期能避免 p6/p3 LOR nodes非嵌套造成的 rediscretized mismatch。

## 10.2 固定架构

```text
p6 exact fine action = matrix-free positive/physical action
p3 positive operator = sparse assembled auxiliary matrix
p1 positive operator = sparse assembled auxiliary matrix
transfer              = local Basix N1E interpolation/histopolation
orientation/Floquet   = owner-local canonical routes
smoother              = degree-3 Chebyshev, one pre + one post
coarsest current anchor = p1 exact sparse oracle
Krylov                = right GMRES/restart20
```

禁止构造 high-order p6 global AIJ或global dense transfer。

## 10.3 C1 structural Gate

p3/h50和p6/h10均须验证：

```text
full-column-rank transfer
edge/curl/gradient commuting <=1e-11
adjoint <=1e-11
Hermitian/SPD
nested Galerkin/rediscretized energy <=1e-9
MPI1/MPI2 canonical identity on small case
```

## 10.4 C1 positive-signal定义与连续推进

以下任一单独事实不够：

```text
code builds
one apply finite
residual briefly下降
```

C1 的最低正信号必须同时满足：

```text
structural Gate pass
small p3/h50 MPI1 random最终true residual <=1e-8 within10000
small-case peak <500,000,000 B
swap=0
```

一旦取得该正信号，继续运行：

```text
p3 MPI1/MPI2四类source
p6/h10 setup resource
p6 positive random→gradient→curl→checkerboard
```

p6合同与 R2相同。p6四案通过后进入 R8。

若 C1 structural Gate、small random或p6 random任一失败：

```text
same_mesh_hcurl_pmg_v1 = CLOSED
```

进入 C2；不得生成 same-mesh `v2` 或扫描 p4/p2中间层。

---

# 11. R7 fallback C2：`nested_lor_edge_hmg_v1`

## 11.1 它与失败的 p-level LOR hierarchy不同

C2 保留 p6 LOR fine grid，但不再创建标准 p3 GLL coarse grid。它从 p6 fine GLL nodes中选择固定子集：

```text
fine indices   = [0,1,2,3,4,5,6]
mid indices    = [0,2,4,6]
coarse indices = [0,6]
```

形成：

```text
6-subinterval fine grid
→ 3-subinterval custom nested grid
→ 1-subinterval coarse grid
```

中间层不是 Basix p3 LOR，必须命名为 `h3star` 或等价无歧义名称，禁止伪装成标准 p3。

## 11.2 固定架构与 Gate

```text
lowest-order Nedelec on every nested subgrid
edge aggregation prolongation
rediscretized positive operator on custom nested meshes
exact orientation/Floquet owner routes
fixed Chebyshev smoother
one V-cycle
p1 exact current-anchor oracle
```

必须通过：

```text
node subset exact identity
edge/curl/gradient commuting <=1e-11
adjoint <=1e-11
nested energy relative <=1e-9
rank full
Hermitian/SPD
all materials classes
```

资源与 p6 positive合同仍与 R2相同。

## 11.3 C2正信号与终止

C2 取得 structural pass且 p6 positive random在10000步内达到 `1e-8` 后，继续其余三类 source；四案通过后进入 R8。

若 C2任一 hard Gate失败：

```text
nested_lor_edge_hmg_v1 = CLOSED
no qualified multilevel PC in V12
```

此时停止 numerical implementation，创建：

```text
docs/task038_extra_full3d_iterative_0p7nm/outcomes/next_pc_architecture_after_v12.md
```

文档必须比较但不得实现：

```text
energy-minimizing BDDC/FETI-DP for H(curl)
GenEO/adaptive domain-decomposition coarse spaces
matrix-free p-h multigrid with distributed algebraic coarse correction
```

并明确每条路线消除的 blocker、预计内存、全局 coarse边界和最小验证案例。完成 response_v12 后停止等待新审阅；不得自行开始第五个 PC family。

---

# 12. R8：选中 hierarchy 的 p6 physical Maxwell MPI1

只有某一 hierarchy 完成 p6 positive四类 source PASS后，才允许运行 physical Maxwell。

## 12.1 固定物理与 solver

```text
13.5 nm
p6/h10
MPI1
exact matrix-free Maxwell volume
streaming Fourier-DtN
selected positive auxiliary hierarchy
right GMRES
restart=20
max_it=20000
residual replacement every20
checkpoint every500
```

## 12.2 成功 Gate

```text
final explicit true residual <=1e-6
finite=true
input/operator/physical hashes closed
complete process-tree peak <2,000,000,000 B
process-tree/rank swap=0
no KSP/basis accumulation across cycles
```

迭代次数与 wall time只报告，不决定成功。

若在20000步内通过，立即执行：

```text
save minimum recovery packet
destroy outer KSP/Krylov objects
destroy p1 oracle factor
confirm RSS release
recover E/H
compute official R/T/A
compute A_volume
compute 12+12 diffraction channels
compare selected E/H and full observable vector against direct authority
```

任何 official physics必须来自通过 true residual Gate 的场。

## 12.3 physical 仅慢收敛时的正信号

若 hierarchy已通过 p6 positive，但 physical在20000步未通过，且满足：

```text
residual finite
last5000 steps降低至少1个数量级
no memory growth
no algebra/provenance defect
```

则分类为：

```text
POSITIVE_AUXILIARY__PHYSICAL_GLOBAL_WAVE_BLOCKER
```

并进入 R9；不得直接关闭该 hierarchy。

若 residual非有限、增长、最近5000步几乎无下降，或资源越线，则保存 negative并停止该路线；若尚有未尝试的 A/B/C候选，回到固定分支顺序，否则进入R12。

---

# 13. R9：唯一 bounded Floquet/near-cutoff deflation强化

R9 只在 R8 得到“positive auxiliary但physical global-wave blocker”时授权。

## 13.1 它解决什么问题

edge hierarchy主要处理正定局部/多尺度误差；真实 Maxwell 的剩余长尾可能来自传播与near-cutoff全局波动。R9只增加一个物理可解释的低秩 correction：

```text
propagating Floquet components
+ near-cutoff Floquet components
```

## 13.2 固定设计

```text
basis source       = existing qualified component authority
rank               = actual propagating + near-cutoff inventory
hard rank cap      = 32
orthogonalization  = deterministic
AZ                 = exact matrix-free physical action
coarse matrix      = Z^H A Z, dense complex128
apply count        = one coarse correction per outer PC apply or one fixed deflation form
```

禁止：

```text
rank scan
residual-derived vectors
random coarse vectors
regional/local spectral modes
large Z/AZ replication beyond rank cap
```

若 actual inventory超过32，必须先选择按 `|beta|` 距cutoff最近的固定32个，并记录未选 inventory；不得自行提高cap。

## 13.3 资源与数值 Gate

```text
complete setup/workflow peak <2,000,000,000 B
swap=0
rank<=32
coarse solve residual <=1e-12
```

随后只重跑一次 R8 physical合同，仍为 `restart20/max_it20000`。

若通过，进入official recovery和R10。若仍失败，保留 hierarchy正定PASS与physical negative，进入R12；不得增加第二个coarse family。

---

# 14. R10：条件 MPI2 与物理一致性

MPI1 physical和official physics全部通过后，条件运行同一 selected hierarchy 的 MPI2 formal。

允许 MPI2 的预条件器内部中间量随partition变化，但必须满足：

```text
exact A/b identity
final explicit true residual <=1e-6
complete process-tree peak <2,000,000,000 B
swap=0
final action consistency within residual-derived bound
official E/H、R/T/A、A_volume、channels与MPI1一致
```

若 MPI2资源超过2GB，不否定 MPI1数值pass，但分类为：

```text
MPI1_NUMERICAL_PHYSICS_PASS__MPI2_RESOURCE_FAIL
```

本轮不得通过提高2GB线绕过。

---

# 15. R11：条件 h5 setup-only 与 0.7 nm / 2 TiB 更新

只有 p6/h10 physical MPI1 pass后才执行。

## 15.1 p6/h5

先基于 h10实测对象 ledger预测 h5 cold setup。只有：

```text
central predicted peak <10 GB
hard upper <12 GB
MemAvailable充分
swap=0
一次只运行一个heavy job
```

才允许运行 h5 setup-only和最多10次PC apply；不运行完整 h5 physical solve。

必须得到：

```text
h10→h5 rows/NNZ/object bytes/RSS scaling
hierarchy level scaling
transfer scaling
MPI duplication
```

## 15.2 0.7 nm / 2 TiB capacity audit

使用最新 measured p6/h10、条件 h5结果和实际 selected hierarchy，更新：

```text
FE rows
matrix-free action
DtN inventory
all multilevel matrices/transfers
restart20 vectors
bounded Floquet correction if used
MPI replication
coarsest scalable-solver reserve
recovery reserve
process-tree lifecycle overlap
```

给出：

```text
optimistic
central
conservative
```

三种情景，明确 measured/derived/predicted。仍禁止运行完整0.7 nm PDE。

---

# 16. 资源与停止条件

所有 p6/h10 formal：

```text
warning threshold = 1,800,000,000 B
hard stop         = 2,000,000,000 B
swap              = 0 B
one heavy job     = true
threads per rank  = 1
```

必须由外部 process-tree watchdog覆盖：

```text
cold setup
retained dwell
PC applies
long solve cycles
release transition
recovery
postprocess
```

以下任一触发立即保存真实证据并按固定分支转移或终止：

```text
nonfinite
true residual cap failure
rank/SPD/spectral Gate failure
RSS hard stop
swap>0
input/operator identity mismatch
phase/orientation failure
checkpoint mismatch
orphan process
unapproved global object
```

数值通过但完整 recovery后超过2GB只能标记：

```text
NUMERICAL_PHYSICS_PASS__RESOURCE_FAIL
```

---

# 17. 实现与测试要求

任何新数值核心必须进入：

```text
src/solvers/
```

benchmark runner只能负责参数化 orchestration、watchdog和evidence。禁止继续复制单case巨型脚本。

至少需要：

```text
local transfer/rank/spectrum unit tests
orientation/permutation tests
Floquet/MPC phase-once tests
adjoint/work tests
MPI1/MPI2 canonical tests
resource ledger tests
checkpoint/resume tests
independent checker tests
```

每次 formal前必须运行最小focused tests；最终 source修改后重跑相关测试、compileall、AST/duplicate-key和文档rendering检查。Ruff不可用时只可记录 unavailable，不得声称通过。

---

# 18. 证据文件与 response 要求

Codex必须按实际经过的路线创建/更新：

```text
docs/task038_extra_full3d_iterative_0p7nm/outcomes/interlevel_route_selection_v1.md
docs/task038_extra_full3d_iterative_0p7nm/outcomes/p6_positive_selected_hierarchy_v1.md
docs/task038_extra_full3d_iterative_0p7nm/outcomes/p6_physical_selected_hierarchy_v1.md
docs/task038_extra_full3d_iterative_0p7nm/outcomes/p6_mpi2_selected_hierarchy_v1.md
docs/task038_extra_full3d_iterative_0p7nm/outcomes/feasibility_0p7nm_2tib_v4.md
docs/task038_extra_full3d_iterative_0p7nm/response_v12.md
```

未运行文件必须明确写 `not_run_by_gate`，不得留空模板暗示已执行。

`response_v12.md`必须回答：

1. 路线 A 的各材料 class spectrum是什么，是否通过；
2. 是否进入路线 B，6→2 nested identity与spectrum/energy结果是什么；
3. 若进入路线 C，关闭范围是什么，C1/C2分别取得了哪些正/负信号；
4. 最终 selected hierarchy是什么；
5. p6 positive四类 source的完整 true-residual histories；
6. p6 physical是否通过、是否使用bounded Floquet correction；
7. complete workflow峰值、swap、release与recovery事实；
8. official E/H、R/T/A、A_volume和12+12 channels；
9. 当前最粗层是否仍使用development direct oracle；
10. 对0.7 nm / 2 TiB主目标还剩哪些明确 blocker。

---

# 19. 最终授权边界

V12授权 Codex在同一分支按 R0→R12 条件连续执行，不需要每个子阶段等待审阅。

V12 不授权：

```text
完整0.7 nm PDE
ordinary default改变
master merge/rebase
无限候选或参数扫描
删除任何旧negative
把p1 direct oracle写成production coarse solver
```

正常停止点：

```text
完成 selected hierarchy 的允许链并写 response_v12.md
```

提前停止点：

```text
C2也无正信号
或任何终端资源/ABI/provenance hard stop
或positive hierarchy经唯一wave correction后physical仍失败
```

本轮核心原则是：

> 先用谱与真实最终残差选择层次；只要出现可审计正信号，就沿该路线继续推进到 p6 正定、真实 Maxwell、official physics和资源闭环。只有有限候选全部失败后才停止，而不是在一个不适用的单向量 energy Gate上反复循环。
