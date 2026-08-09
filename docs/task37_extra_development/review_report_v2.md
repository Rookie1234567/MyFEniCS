# Task037-extra Review Report V2：G2 负结果后的唯一新候选——full-space matrix-free coercive multigrid oracle

## 0. 审阅身份与决定

```text
review                         = Task037-extra Review Report V2
working_branch                 = codex/20260806-task37-iterative-extra-development
create_new_branch              = forbidden
pull_request                   = forbidden
merge_to_master                = permanently_not_planned
ordinary_default_change        = forbidden
review_v1_G2_decision          = accepted_and_not_reopened
G2_LOR_HX                      = closed
G3_additive_LOR_HX             = prohibited
G4_sweep_with_failed_LOR_HX    = prohibited
new_authorized_candidate       = Candidate H
candidate_H_scope              = bounded component/oracle development only
candidate_H_full_PDE           = not_authorized_in_first_execution
```

Review V1 对 G2 的裁决保持不变：当前 slab full-space LOR-HX hierarchy 的实现、测试、
原始证据和负结果分类可信；其 retained payload 与 contraction 均失败，因此不得继续 G3，
也不得通过 shift、cycle 数、smoother 参数或 sweep 扫描来“修出”正结果。

V2 只授权一个与 G2 不同的新候选：

> **在未静态凝聚的完整 p6 Nédélec 空间中，先建立精确 matrix-free action，再对一个强制性、
> 强耗散的 Maxwell 代理问题验证 class-reused element-block smoother 与两层几何多重网格是否
> 具有稳定收缩和近线性存储。**

该候选不是“恢复 full-space 后一定能收敛”的承诺。它只是一个二元判别型 oracle：

```text
若 coercive full-space oracle 不能稳定收缩或不能保持低存储：立即关闭 full-space MG。
若 coercive oracle 通过：才有资格另行审阅是否进入 exact time-harmonic shifted-PC screen。
```

---

## 1. 为什么只允许 oracle，而不直接开发完整求解器

### 1.1 已有负证据

当前分支已经实测：

| 路线 | 正式结果 |
|---|---|
| static-condensed M3a | 352 iterations、4.7673 GiB、full residual/RTA/12+12 pass |
| condensed B2/B4 factor-free | 低存储成立，但出现长期平台；未形成可用 full solve |
| slab full-space p6 ILU | retained payload 是 trace ILU 的 5.3166 倍，局部 correction 更差 |
| slab LOR transfer | topology/Floquet/orientation/adjoint 代数通过 |
| slab LOR-HX hierarchy | retained payload 2.913 GiB，是一块 trace ILU 的 25.636 倍 |
| slab LOR-HX 1V/2V | residual 放大约 `1e6--1e16`；G2_FAIL |

因此，以下推论均被禁止：

- full-space 从拓扑上更稀疏，所以普通 ILU 会更小；
- LOR transfer 正确，所以 LOR-HX 会有效；
- condensed factor-free 失败，只要恢复 full-space 就会自然收敛；
- sweep 能补救一个单 slab 上已经严重不稳定的局部 inverse。

### 1.2 full-space 强 ILU 的内存预测不满足长期目标

根据 slab14 的实测 full/trace factor 比例，若在完整 p6 空间沿用 16-slab 强 ILU，
MPI1 p6/h10 峰值的合理量级约为 `11--15 GiB`，MPI8 很可能重新接近
`28--35 GiB`。这条路线不满足当前 `<2 GiB` 的必要单点目标，也不具备 p6/h1 的
可扩展资格。

### 1.3 `<2 GiB` 是必要条件，不是最终目标

从 h10 到 h1，三维单元数的量级约增加 `10^3`。若未来总内存预算约为 2 TiB，
则 p6/h10 的线性缩放常数必须约低于 2 GiB；考虑 DtN、MPI、recovery 和运行时余量，
更合理的核心目标应接近 `1.2--1.5 GiB`。

但单点内存仍不够。真正的长期 Gate 是：

```math
M(N)=cN^{\alpha},
\qquad \alpha\approx1.
```

候选必须最终证明：

```text
低常数
+ 近线性内存缩放
+ refinement 下稳定的迭代/cycle 数
```

任何只对当前小横截面有效、却包含 dense plane block、随子域规模增长的 factor 或
显式大 hierarchy 的方法，都不能作为 0.7 nm 主线。

---

## 2. 文献给出的准确启示

以下文献只支持“值得做严格 oracle”，不构成当前问题的成功保证。

1. Gopalakrishnan、Pasciak、Demkowicz，*Analysis of a Multigrid Algorithm for Time Harmonic Maxwell Equations*，DOI `10.1137/S003614290139490X`。
   该工作说明不定 Maxwell 多重网格需要特定的 indefinite block smoother 和 cycle，普通 Jacobi V-cycle 并不充分。
2. Chanaud 等，*A Parallel Full Geometric Multigrid Solver for Time Harmonic Maxwell Problems*，DOI `10.1137/130909512`。
   该工作采用几何网格层级、细层 matrix-free、粗层直接求解，并报告大规模并行结果；但其元素阶次、边界和材料与本项目不同。
3. Lai 与 Olson，*Algebraic Multigrid for High-Order Hierarchical H(curl) Finite Elements*，DOI `10.1137/100799095`。
   该工作强调 curl-curl 问题需要与离散梯度近核相容的专用多层结构。
4. Pazner、Kolev、Dohrmann，*Low-Order Preconditioning for the High-Order Finite Element de Rham Complex*，DOI `10.1137/22M1486534`。
   该工作给出高阶 de Rham 空间低阶等价预条件框架；但本分支的显式 slab LOR-HX 已经失败，故该文献不能用于重新开启 G2。

V2 的结论是：文献证明 full-space matrix-free multilevel 方法在其他 Maxwell/de Rham
问题上存在成功先例，但当前 p6、复材料、Floquet、DtN、掠入射问题仍必须从最小 oracle
重新证明，不允许从论文结果推断本项目必然收敛。

---

## 3. Candidate H 与已失败路线的区别

### 3.1 fine space 从一开始就是完整 H(curl) 空间

Candidate H 的 fine unknown 是未静态凝聚的完整 p6 Nédélec 系数：

```math
A_h u_h=b_h.
```

它不执行：

```text
cell interior elimination
-> dense trace Schur
-> trace-space local inverse
```

但“full-space”不等于组装完整稀疏矩阵。fine action 必须是：

```math
y=A_hx
```

的 element-local matrix-free/partial-assembly 实现。

### 3.2 Candidate H 不使用 G2 的 LOR-HX hierarchy

Candidate H 第一阶段禁止：

- scalar H1 + vector H1 双 hierarchy；
- slab-local LOR proxy；
- trace residual 补零后再投回 Schur；
- explicit large LOR/HX hierarchy；
- p6 slab ILU；
- global assembled p6 matrix。

Candidate H 直接在嵌套 full-space Nédélec 层级上作用。第一版 smoother 固定为
**exact-class-reused overlapping element-block smoother**：相同材料、尺寸、orientation、
边界类型的局部 block 只保存一份 factor；block class 数必须被审计，不能假定其为常数。

### 3.3 第一阶段只解 coercive proxy

第一阶段不求原始散射方程。冻结 proxy 为：

```math
B_h
=
K_{\mathrm{curl},h}
+
k_0^2 M_{|\epsilon|,h}.
```

其中质量项使用正的 `|epsilon|` 权重，使该组件测试具有强制性。Floquet 拓扑、Nédélec
orientation、材料分区和完整 full-space DoF 均保留；DtN 与 official R/T/A 不属于第一阶段。

理由是：若候选连 coercive full-space H(curl) 问题都不能稳定收缩，就没有资格进入更困难的
复数、非 Hermitian、不定时谐问题。

---

# 4. 执行阶段 H0--H4

## H0：继承与能力审计

创建：

```text
docs/task37_extra_development/outcomes/h0_fullspace_mg_audit.md
```

必须记录：

- 当前 branch、HEAD、upstream、clean、ahead/behind；
- Review V1 与 consolidated `response_v1.md` 的身份；
- G2_FAIL、G3/G4-old 禁止边界；
- 可复用的 cell kernel、Basix orientation、Floquet、matrix-free DtN 和 full-space assembled authority；
- 当前 full standard / static direct / M3a 内存数据；
- 当前环境中 PETSc PCMG、MatPython、coarse communicator 和 custom prolongation 的 capability；
- 是否能够在不新依赖的前提下实现 element-local p6 action。

H0 不运行新 PDE。

## H1：full-space matrix-free action

### H1.1 小型 fixture

先在 p2/p3 structured-hexa fixture 上实现并验证：

- full-space cell restriction/gather；
- Nédélec orientation；
- curl 与 mass action；
- Floquet periodic mapping；
- material tags；
- MatPython/PETSc Vec 生命周期；
- serial/MPI2 partition identity。

与 assembled full-space action 比较：

```math
\frac{\|A_{\mathrm{assembled}}x-A_{\mathrm{mf}}x\|_2}
{\|A_{\mathrm{assembled}}x\|_2}
\le10^{-11}.
```

### H1.2 p6/h10 action-only

fixture 通过后，允许在 frozen p6/h10 上运行 action-only gate：

```text
3 deterministic vectors
1 physical-RHS-like vector
no KSP solve
no official field
no RTA
```

硬性 inventory：

```text
global full-space A materialized       = false
global condensed Schur materialized    = false
cell dense 882x882 matrices retained    = false
cell Schur matrices retained            = false
slab matrix/factor count                = 0
DtN explicit dense C/D                   = 0 when DtN probe is enabled
```

H1 Gate：

```text
action relative error <= 1e-11
finite and deterministic
MPI1/MPI2 identity pass
retained numeric payload <= 0.50 GiB
process-tree action-only peak <= 1.25 GiB
```

若 H1 失败，Candidate H 立即关闭。

## H2：class-reused element-block smoother oracle

只对 coercive proxy `B_h` 测试，不启动原始时谐 FGMRES。

### H2.1 block 定义

第 `c` 类 cell block：

```math
B_c=R_c B_h R_c^T.
```

只允许：

- pivoted complex LU/ILU on one small block per exact class；
- multiplicity/partition-of-unity weighting；
- fixed two-color or deterministic coloring；
- one pre-smooth + one post-smooth。

禁止：

- 每个 cell 一份独立 factor；
- 16-slab factor；
- 20--90 步 local Krylov；
- 根据结果自动改变 block/shift；
- global assembled matrix。

### H2.2 residual sources

必须测试：

```text
gradient-dominated
curl-dominated
mixed
checkerboard/high-frequency
```

定义：

```math
\rho_{\mathrm{smooth}}
=
\frac{\|r-B_hM_{\mathrm{smooth}}^{-1}r\|_2}{\|r\|_2}.
```

H2 Gate：

```text
all sources finite/deterministic
high-frequency rho <= 0.70
mixed rho <= 0.85
exact class count reported
class count does not grow on repeated/refined fixture
retained block-factor payload <= 0.25 GiB on p6/h10
one smoother apply <= 20 * one matrix-free action wall
```

若 H2 失败，禁止构建两层 multigrid。

## H3：两层 coercive multigrid oracle

只在 H2 通过后进入。

### H3.1 层级顺序

先做小型 nested geometry-conforming fixture，再做真实物理层级：

```text
fine   = uniform refinement of frozen h10 mesh (nominal h5)
coarse = frozen h10 mesh
```

fine mesh 必须由 coarse parent cell精确细化，材料界面和 Floquet entity identity不得重新近似。

### H3.2 transfer

构造 full-space H(curl) prolongation `P` 与 dual restriction：

```math
R=P^H.
```

必须验证：

- constant/affine/curl-compatible fields；
- orientation；
- Floquet phase；
- adjoint identity；
- MPI repartition identity；
- no missing/duplicate canonical entity key。

### H3.3 coarse solve 的证据边界

第一轮 two-grid 只做容量 oracle。允许使用一个**离线 coarse authority**计算少量 coarse
correction，以判断 coarse space 是否具备误差容量；该 authority 的 setup/peak必须单独报告，
不得计入可扩展在线 solver 成功，也不得掩盖 H1/H2 在线存储。

只有 two-grid correction 有正信号后，才允许设计真正低内存的多层 coarse solve。

H3 Gate：

```text
one V-cycle rho <= 0.50 on mixed/high-frequency sources
10 V-cycles reduce residual by >= 1e4
fine-level online retained peak <= 1.50 GiB
fine operator and transfer matrix-free/sparse-local
no growing slab/subdomain factor
h10/h5 cycle-count ratio <= 1.5 on coercive proxy
```

若 H3 失败，Candidate H 正式关闭；不得进入时谐问题。

## H4：时谐 shifted-PC screen——本次不授权执行

H4 只保留为后续审阅接口。只有 H3 完整通过，并由用户/ChatGPT 再次审阅后，才允许：

```math
A_hu=b
```

保持 exact fine equation，用吸收型 multigrid近似逆作为 right PC，并运行 20/100/200-step
true-residual screen。

当前 Codex 执行不得实现或运行 H4，不得输出 official R/T/A。

---

## 5. 第一轮 Codex 执行边界

本次只执行：

```text
H0
H1.1
H1.2（仅当 H1.1 通过）
H2（仅当 H1 全部通过）
```

不得执行：

```text
H3 physical h5/h10 heavy campaign
H4 exact time-harmonic screen
new full solve
new branch
PR
master merge
G2/G3/G4-old reopen
LOR-HX repair/parameter scan
```

第一轮 response 必须回答：

1. exact p6 full-space matrix-free action 是否成立；
2. action-only retained bytes 与 process-tree peak 是否低于 H1 Gate；
3. exact element-block class 数及其随 fixture refinement 的变化；
4. coercive proxy 上四类 residual 的 one-smoother contraction；
5. 是否具备进入 H3 two-grid oracle 的条件。

第一轮输出：

```text
docs/task37_extra_development/outcomes/h0_fullspace_mg_audit.md
docs/task37_extra_development/outcomes/h1_fullspace_matrix_free_action.md
docs/task37_extra_development/outcomes/h2_coercive_block_smoother.md
docs/task37_extra_development/response_v2.md
```

注意：当前 `response_v1.md` 是 G0--G2 的 consolidated authority。后续新实验从
`response_v2.md` 开始，不得再次拆分成每个小阶段一个 response。

---

## 6. 推荐代码边界

新代码优先放在独立模块：

```text
src/solvers/fullspace_matrix_free_hcurl.py
src/solvers/fullspace_element_block_smoother.py
src/solvers/fullspace_hcurl_transfer.py
src/solvers/fullspace_coercive_two_grid.py
```

实际名称可按仓库结构调整，但必须满足：

- 所有入口显式 `task037_extra_candidate_h` opt-in；
- ordinary defaults不变；
- import 时不创建 PETSc/MPI对象；
- MatMult/PC apply 中不分配 FE-sized Python global arrays；
- cell class factor只构造一次；
- destroy幂等；
- no-rank-work时仍遵守collective路径；
- raw artifacts保持gitignored；
- Git只提交小型records、tests和docs；
- 不新增外部依赖。

建议测试文件：

```text
src/test/test_271_task037_extra_fullspace_mf_action.py
src/test/test_272_task037_extra_fullspace_mf_mpi.py
src/test/test_273_task037_extra_element_block_smoother.py
src/test/test_274_task037_extra_fullspace_hcurl_transfer.py
src/test/test_275_task037_extra_coercive_two_grid.py
```

编号若已占用，使用下一个空闲编号并在 H0 中记录映射。

---

## 7. 硬停止规则

### 7.1 代数停止

- matrix-free action error `>1e-11`；
- orientation/Floquet/transfer identity失败；
- reported/true residual或proxy residual不一致；
- nonfinite或重复作用不确定。

### 7.2 数值停止

- H2 high-frequency `rho>0.70`；
- H2 mixed `rho>0.85`；
- H3 one-V-cycle `rho>0.50`；
- 需要增加到 20--90 次 local Krylov/smoothing才能通过；
- 需要结果驱动的无界 shift/block扫描。

### 7.3 资源停止

- H1 action-only peak `>1.25 GiB`；
- H2 block-factor payload `>0.25 GiB`；
- 需要保留global matrix、cell dense matrix、slab factor或显式大auxiliary hierarchy；
- swap持续增长；
- 依赖hot factor磁盘流式读取；
- class count随cell count显著增长。

### 7.4 治理停止

- 需要新分支、PR、master合并或force push；
- 需要修改ordinary default；
- 需要降低p、减少modes、改变物理或放宽true residual；
- 需要安装新依赖或替换生产环境。

触发停止后，写 compact outcome，提交并推送当前 extra 分支，然后等待审阅。

---

## 8. 最终裁决

V2 不批准恢复到 full-space 并直接运行完整时谐求解器，也不宣称 full-space factor-free
会收敛。V2 只批准一个低成本、可停止的验证：

```text
exact full-space matrix-free action
+ coercive Maxwell proxy
+ class-reused element-block smoother
+ conditional two-grid oracle
```

其目的不是获得 R/T/A，而是先回答：

> 在当前 FEniCS/Basix、p6 Nédélec、Floquet 拓扑下，是否存在一个不依赖 growing
> slab factors、存储接近 O(N)、且能稳定处理 coercive full-space H(curl) 误差的基础多层机制？

只有这个问题得到肯定答案，才值得继续讨论真实时谐、0.7 nm 和 p6/h1。无论结果如何，
全部代码和证据只保留在：

```text
codex/20260806-task37-iterative-extra-development
```
