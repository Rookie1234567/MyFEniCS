# Task037 Review Report V6：最后候选 E——M120 modal-assisted Full3D 预条件器的决定性验证

## 0. 审阅身份与核心决定

```text
review                         = Task037 Review Report V6
reviewed_branch                = codex/20260803-task37-matrix-free-iterative-development
reviewed_response              = response_v5.md
reviewed_candidate             = Candidate E / M120 modal-assisted Full3D coarse
ordinary_default               = unchanged
merge_to_master                = not authorized
Task037b Hybrid block solver   = not authorized
0.7 nm production PDE          = not authorized
```

当前已经取得的结论为：

```text
M3a p6 slab ILU                     = 唯一 full numerical/physical pass
A / B2 / B4 extension / C / D       = controlled negative
R7 p4-core partial condensation     = component positive / public integration negative
Candidate F p6->p4->p2              = closed on frozen ideal-capacity oracle
Matrix-free p6 fine action          = algebraically qualified
p6 factor-free storage mechanism    = positive
factor-free convergent replacement  = not demonstrated
Candidate E M120 modal coarse       = final not-run candidate
```

V6 只授权最后一个预条件器候选：

> **保留完整 p6/h10 Full3D fine operator 与完整 Krylov 空间，将原 Hybrid 的冻结 M120 正/反向本征模作为全局长程 coarse/deflation 空间，帮助 factor-free B4 消除其长期停滞的传播型误差。**

该候选不是 original Hybrid solver，也不把 Full3D 解限制在模态空间内。Task036 已证明 M120 不能在所有角度独立承担完整 Maxwell joint-Cauchy 接口；但 Full3D coarse correction 只需要捕捉慢收敛方向，其余近场、倏逝与 traction complement 仍由完整 p6 Krylov 空间修正。因此：

```text
modal direct-Hybrid failure != modal coarse-space failure
```

V6 的目标不是“让最后一个候选一定通过”，而是给它一次最有利、可审计且有停止语义的验证。若连理想 action-minimum-residual modal capacity 都不足，则 Candidate E 正式关闭，Task037 的低内存 factor-free PC 研究收口。

---

# 1. Candidate 快速索引

| 名称 | 方法含义 | 当前状态 |
|---|---|---|
| Direct authority | p6/h10 静态凝聚 + 全局 MUMPS | 数值权威 |
| M3a | 16 个重叠 p6 slab ILU(0) + 75D wave coarse + FGMRES | full pass；MPI1 4.60 GiB |
| A | 全局 p2 auxiliary + p6 diagonal | closed |
| B2 | factor-free p6 slab + local GMRES(2) | closed；MPI1 2500 步仍约 0.1563 |
| B4 | factor-free p6 slab + local GMRES(4) | factor-free 数值基线；200 步约 0.1406 |
| C | B4 + 当前 RAS/interface-shift 实现 | closed |
| D | local p6 Krylov 内加入 local p2 auxiliary | closed |
| R7 | 保留 p4-core interior 的部分凝聚 | public complement Gate 未闭合 |
| F | p6→p4→p2 p-multigrid | frozen family closed |
| **E** | **M120 Hybrid 本征模作为 Full3D modal coarse/deflation** | **V6 最后候选** |
| Matrix-free DtN | 不物化完整 C/D 的 DtN action | component pass；formal 80-mode Gate 待完成 |

---

# 2. Candidate E 与原 Hybrid 的区别

## 2.1 原 direct Hybrid

原 Hybrid 将中间规则区的场限制为有限模态展开：

```math
E_{\mathrm{middle}}
=
\sum_{m=1}^{120} a_m^+\,\phi_m^+(x,y)e^{i\beta_m^+ z}
+
\sum_{m=1}^{120} a_m^-\,\phi_m^-(x,y)e^{i\beta_m^- z}.
```

在 direct Hybrid 中，这 240 个模态坐标承担中间区全部信息。Task036 的负结果表明，在部分角度/偏振下，这个空间不能完整代表接口 electric trace 与 magnetic traction。

## 2.2 Candidate E

Candidate E 仍求解完整 Full3D 方程：

```math
A_6 x=b,
```

其中 $A_6$ 是当前 exact complex128、静态凝聚、matrix-free 的 p6 Full3D operator。M120 只生成一个 coarse trial basis：

```math
Z_M
=
[z_1,\ldots,z_{240}]
\in
\mathbb{C}^{51192\times240}.
```

完整 Krylov 空间没有被删除，因此任何不在 $\operatorname{range}(Z_M)$ 中的场分量仍可由 Full3D FGMRES 恢复。

本报告将 action basis 定义为：

```math
Y_M=A_6 Z_M.
```

为了避免非 Hermitian Petrov 选择本身掩盖 modal trial-space 的真实容量，V6 的 primary coarse 使用 action-QR/SVD minimum-residual correction，而不是先依赖某个可能不稳定的左模态公式。

若 $Y_M=QR$ 为秩揭示薄 QR/SVD 分解，则 modal correction 为：

```math
Q_M r
=
Z_M R^{-1}Q^H r.
```

它直接在 $\operatorname{range}(Z_M)$ 中寻找使欧氏 true residual 最小的系数。禁止通过 normal equations 构造。

原 physical-adjoint 左模态仍需完成身份和 biorthogonality 审计，但不是 V6 capacity pass 的唯一 test basis。若最有利的 action-minimum-residual correction 都失败，任何使用同一右模态 trial space 的 Petrov coarse 不会获得更好的二范数容量上界。

---

# 3. 冻结模型与历史正证据

Candidate E 只使用当前 Task037 anchor：

```text
wavelength              = 13.5 nm
incidence               = theta 80° from normal = 10° grazing
phi                     = 0°
polarization            = S
field space             = first-family Nédélec p6
mesh                    = h10 / structured hexa (6,3,14) / 252 cells
full FE DoFs            = 173802
active trace rows       = 51192
DtN auxiliary rows      = 80
fine operator           = exact static-condensed complex128 Full3D
base factor-free PC     = frozen B4 family
```

同一物理点的历史 M120 Hybrid authority 已经证明：

| path | rows | factor NNZ | peak | total | physics |
|---|---:|---:|---:|---:|---|
| Full3D static | 51,272 | 212,343,992 | 14.7218 GiB | 260.74 s | authority pass |
| Hybrid static M120 | 17,168 | 45,293,792 | 7.5443 GiB | 322.78 s | 12/12 power + 12/12 amplitude pass |

M120 在该成功角度下的 interface tangential E/H 与 middle-plane E/H 也通过冻结 Gate。这只说明 M120 对当前 anchor 的长程传播具有物理相关性，不等于提前证明 coarse PC 会成功。

冻结规则：

- 只使用 M120；不得运行 M40/M80/M160/M240 rank sweep；
- 正向 120 + 反向 120，共 240 个 trial columns；
- 不加入 Task036 discrete-Bloch correctors、POD 或 exact-trace correctors；
- 不根据当前 Full3D direct solution、B4 residual 或测试结果重新挑选模态；
- 不修改 beta branch、near-degenerate grouping、mode ordering 或 normalization threshold。

---

# 4. E0：正式 80-mode Matrix-free DtN 前置 Gate

Matrix-free DtN 是未来 0.7 nm 必需基础设施，也应成为 Candidate E 使用的 fine operator 组成部分。当前 synthetic component 已通过，但正式 80-mode p6/h10 identity 尚未完成。

## 4.1 必须完成的 action

对当前 80 个外部 DtN modes，比较显式 block 路径与 matrix-free 路径：

```math
A_{\mathrm{DtN}}x
=
C H^{-1}D x.
```

Matrix-free 路径必须逐通道/小块执行：

```math
y=Dx,
\qquad
z=H^{-1}y,
\qquad
t=Cz,
```

而不物化完整 dense C/D coupling。

## 4.2 Gate

必须在同一 frozen p6/h10 operator 上完成：

- 3 个 deterministic random active-trace vectors；
- physical RHS vector；
- forward action relative error `<=1e-11`；
- auxiliary amplitude recovery relative error `<=1e-11`；
- optional Hermitian-transpose/adjoint action identity `<=1e-11`；
- 80/80 mode keys、beta、polarization、power normalization、Rayleigh flags完全一致；
- serial、MPI2、MPI4 identity；
- matrix-free profile 的 explicit C/D materialized count = 0；
- ordinary default 不变。

若 E0 失败，立即写 `MATRIX_FREE_DTN_FORMAL_80MODE_GATE_FAILED` 并停止。不得以 Candidate E 为理由跳过该 Gate。

E0 只做 component/action 资格化，不单独启动新的 full PDE。

---

# 5. E1：冻结 M120 全局 coarse basis 的构造

## 5.1 模态身份

必须通过现有 Task032/035c/036 mode pipeline重建同一 M120：

- 120 forward right modes；
- 120 backward right modes；
- 匹配 physical-adjoint left modes；
- reciprocal pairing；
- near-degenerate group closure；
- biorthogonality；
- propagation beta 与 traction beta identity。

至少报告：

```text
right/left mode count
beta hashes / extrema
right QEP residual max
left QEP residual max
left-pair relative error max
biorthogonality max identity error
near-degenerate group count and sizes
forward/backward propagation factor hashes
```

不得为了通过 Gate重新求更多 modes或改变 selection tolerance。

## 5.2 右 trial basis $Z_M$

每个 modal column必须是完整 Full3D active-trace vector，而不是只在一个中间接口上填值。

对第 $j$ 个单位 modal amplitude：

1. 中间规则区使用已有 `TwoSidedPropagation` 与 M120 模态场，在所有 p6 trace entity/interpolation points上恢复正向或反向传播场；
2. bottom/top endcap使用同一 Hybrid local operator做 homogeneous harmonic extension；
3. 通过 canonical entity key、Basix orientation 与 Floquet constraint映射到 Full3D 的 51,192 active rows；
4. 不使用 Full3D direct solution、teacher response或 residual snapshot构造列；
5. 每列以 active-trace二范数归一，并以最大幅值 entry 的相位固定为实部非负；
6. missing/duplicate active keys 必须为 0。

局部 harmonic extension可在 E1 research setup 中暂时使用现有 p6 local direct factor，以给予 modal basis最有利的物理延拓；但必须：

- 单独记录 basis-generation peak、factor inventory和wall；
- basis生成后立即释放全部 local factors；
- 后续 capacity/online solve不得保留这些 factors；
- 不能把离线 basis-generation peak隐瞒为 online solver peak；
- 即使在线通过，也不自动获得 0.7 nm production qualification。

## 5.3 Action basis 与存储

计算：

```math
Y_M=A_6 Z_M
```

必须使用 exact complex128 Full3D fine action，包括正式 Matrix-free DtN。

当前显式 distributed basis的原始数值量约为：

```math
51192\times240\times16
\approx187.5\ \mathrm{MiB}
```

每个 $Z_M$ 或 $Y_M$ 各约 187.5 MiB。要求：

- basis按 PETSc ownership分布；
- 禁止在每个 MPI rank完整复制 $Z_M$、$Y_M$ 或 $Q$；
- 240×240 small matrix允许复制；
- 记录 Z/Y/QR workspace、metadata和总 resident bytes；
- p6 retained slab factor count/NNZ继续为 0/0；
- global A/F不物化。

## 5.4 E1 implementation Gate

- 240 columns全部 finite且非零；
- active key missing/extra/duplicate = 0；
- deterministic repeat error `<=1e-12`；
- random coefficient action identity `<=1e-11`；
- effective action rank必须报告；若 rank < 180，分类为 `M120_GLOBAL_ACTION_BASIS_COLLAPSED`并停止；
- retained action condition与singular spectrum完整报告；
- no normal equations；
- ordinary defaults unchanged。

E1 失败时不得通过删除困难模式、降低 rank或改为 M160重跑。

---

# 6. E2：理想 modal capacity oracle

Candidate E 只有在理想 action-minimum-residual 上界显示有明显容量时，才允许进入实际 outer solver。

## 6.1 冻结 B4 residual snapshots

需要 current B4 factor-free Full3D 的 true residual vectors：

```text
iteration 0
iteration 20
iteration 100
iteration 200
```

必须保存：

```math
r_k=b-A_6x_k
```

的 canonical active-trace vector，而不是 PETSc reported scalar residual或preconditioned residual。

若既有 ignored B4 artifacts中没有这些完整 vectors，只允许额外运行一次 MPI8 B4 200-step snapshot carrier；配置必须与冻结 B4完全一致，且只增加 residual-vector export。不得改变任何求解参数或把该运行视为新候选。

## 6.2 必须比较的空间

对每个 $r_k$，计算以下理想 minimum-residual 上界，全部使用 rank-revealing QR/SVD：

### 75D wave coarse only

```math
\rho_{75}(r_k)
=
\min_c
\frac{\lVert r_k-A_6Z_{75}c\rVert_2}{\lVert r_k\rVert_2}.
```

### M120 modal coarse only

```math
\rho_M(r_k)
=
\min_c
\frac{\lVert r_k-Y_Mc\rVert_2}{\lVert r_k\rVert_2}.
```

### 75D + M120 联合 coarse

```math
\rho_{75+M}(r_k)
=
\min_c
\frac{\lVert r_k-A_6[Z_{75},Z_M]c\rVert_2}{\lVert r_k\rVert_2}.
```

### 实际 B4 correction 后的 modal capacity

先应用一次冻结 B4 preconditioner：

```math
z_B=M_{B4}^{-1}r_k,
\qquad
r_B=r_k-A_6z_B.
```

再计算：

```math
\rho_{B+M}(r_k)
=
\min_c
\frac{\lVert r_B-Y_Mc\rVert_2}{\lVert r_k\rVert_2}.
```

同时记录相对当前 B4 remainder 的 contraction：

```math
\widehat\rho_{M|B}(r_k)
=
\frac{\min_c\lVert r_B-Y_Mc\rVert_2}{\lVert r_B\rVert_2}.
```

## 6.3 E2 capacity Gate

重点判断 B4 已经进入平台的 iteration 100 与 200 residual。

两者必须同时满足：

```text
modal-only improvement 1/rho_M              >= 1.5
modal after B4 remainder contraction         rho_hat_M|B <= 0.67
75D+M120 vs 75D incremental improvement      rho_75 / rho_75+M >= 1.20
all LS ranks/conditions/repeat errors         pass
```

如果 iteration 100 或 200 任一 residual未同时满足上述条件，正式记录：

```text
M120_MODAL_COARSE_INSUFFICIENT_ON_FROZEN_LATE_RESIDUALS
```

并关闭 Candidate E，不运行重型 MPI8 candidate。

该关闭具有较强意义：E2直接使用完整 M120 trial space与理想 minimum-residual系数，真实 coarse implementation不会拥有比它更强的同空间二范数容量。

若 E2 通过，只能写：

```text
M120_TRIAL_SPACE_HAS_COARSE_CAPACITY
```

不得提前写 solver success。

---

# 7. E3：唯一实际 Candidate E

只有 E0、E1、E2全部通过，才实现一个冻结的实际 coarse PC。

## 7.1 Base PC

保持 B4 其余结构不变：

```text
fine operator             = exact p6 matrix-free + matrix-free DtN
physical slabs            = 16
overlap                   = 0.125
local correction          = factor-free fixed 4-step local GMRES
global p2 correction      = existing frozen path
75D wave coarse           = retained
outer KSP                 = right FGMRES restart 90
p6 slab matrix/factor     = 0 / 0
```

Candidate E只增加一次 multiplicative modal correction：

```math
x_B=M_{B4}^{-1}r,
```

```math
r_B=r-A_6x_B,
```

```math
M_E^{-1}r
=
x_B+Q_M r_B.
```

禁止改变 B4 local steps、slab数、overlap、shift、global p2或75D coarse后再判断 modal candidate。

## 7.2 Coarse implementation

Primary implementation使用 E1 的 action-QR/SVD basis。禁止 normal equations。

必须报告：

```text
modal input columns = 240
effective retained rank
Z/Y/Q or factorized storage bytes
small coarse solve bytes
coarse apply count and mean wall
modal correction norm
true residual before/after each sampled modal correction
```

physical-adjoint left modes可用于额外 Petrov identity诊断：

```math
E_P=W_M^H A_6Z_M.
```

但不得因为 Petrov condition较差而放弃已经通过的 action-MR realization，也不得增加第二个重型 candidate。V6 的实际候选只有 action-MR coarse这一条。

---

# 8. E4：MPI8 20/100/200-step 漏斗

只运行一个冻结 Candidate E。

## 20-step Gate

```text
finite / no NaN
true residual <= 0.30
strictly better than B4@20 = 0.4261192527
p6 factor count / NNZ = 0 / 0
global A/F = false / false
MPI8 process-tree peak <= 7.25 GiB
```

## 100-step Gate

```text
true residual <= 0.10
last 40 iterations net decrease
strictly better than B4@100 = 0.1708326448
modal coarse apply finite and deterministic
```

## 200-step Gate

```text
true residual <= 0.05
predicted iterations <= 3000
predicted wall <= 7200 s
strictly better than B4@200 = 0.1405734648
```

任一阶段失败立即停止。禁止：

- mode rank sweep；
- 删除“效果差”的 modes；
- M160/M240；
- 改 local steps；
- 改 overlap/slab/shift；
- 改 residual Gate；
- 自动重跑。

---

# 9. E5：full solve、restart 与 MPI1 极限内存

只有 E4三阶段全部通过，才允许：

## 9.1 一次 MPI8 full

必须通过：

```text
reported residual            <= 1e-6
condensed true residual      <= 1e-6
full augmented residual      <= 1e-6
full FE residual             <= 1e-6
canonical active/full field  <= 1e-5 vs direct
12/12 powers                 pass
12/12 complex amplitudes     pass
R/T/A and energy closure     pass
zero swap                    pass
```

## 9.2 Restart 缩减

只有 MPI8 full通过后，按固定顺序测试：

```text
90 -> 60 -> 40 -> 30 -> 20
```

每一级只做一个100-step continuation或等价的受控比较。出现明显停滞立即停止继续降低。

## 9.3 一次 MPI1 full

在最优已资格化 restart下运行一次 MPI1 full：

```text
online process-tree peak <= 2.0 GiB
preferred                <= 1.5 GiB
swap                     = 0
p6 factor NNZ            = 0
all numerical/physical Gates pass
```

必须分开报告：

1. M120 basis-generation peak；
2. basis artifact写盘大小；
3. online solver peak；
4. whole workflow peak；
5. 若basis由离线direct extension产生，不得把online peak冒充0.7 nm whole-job qualification。

Candidate E即使数值和online内存通过，仍只可分类为：

```text
CURRENT_ANCHOR_MODAL_ASSISTED_PC_PASS
```

不得直接写0.7 nm scalable或production-qualified。0.7 nm下显式 $N\times240$ basis与basis-generation策略需要独立重构。

---

# 10. 结果分类

## 10.1 E0/E1 implementation failure

```text
MATRIX_FREE_DTN_FORMAL_80MODE_GATE_FAILED
或
M120_GLOBAL_MODAL_BASIS_IMPLEMENTATION_FAILED
```

不得改阈值重跑。

## 10.2 E2 capacity failure

```text
M120_MODAL_COARSE_INSUFFICIENT_ON_FROZEN_LATE_RESIDUALS
```

Candidate E正式关闭；不运行E3–E5。

## 10.3 E2通过但E4失败

```text
M120_TRIAL_SPACE_HAS_CAPACITY_ACTUAL_COARSE_PC_INSUFFICIENT
```

保留科学正/工程负结果，不开发第二种modal implementation。

## 10.4 E5 full通过

```text
M120_MODAL_ASSISTED_FULL3D_PC_NUMERICAL_PASS
```

资源Gate另外独立写 pass/fail。

## 10.5 所有候选关闭

若 Candidate E关闭，则 Task037最终结论为：

```text
M3a factor-heavy iterative = numerical pass / 4.60 GiB MPI1
factor-free p6 action       = storage pass
factor-free scalable PC     = not demonstrated
Task037 low-memory PC study = closed with controlled negatives
```

随后只允许结项、选择性合并和另立新任务；不得在Task037继续发明Candidate G/H。

---

# 11. 代码与证据边界

建议新增职责单一的research-only模块：

```text
src/solvers/static_modal_coarse_pc.py
src/solvers/static_modal_coarse_basis.py
```

以及分阶段测试/record。具体编号由当前仓库顺序决定，不应覆盖已有test。

所有新入口必须：

- explicit research opt-in；
- ordinary defaults unchanged；
- fail closed；
- deterministic seeds；
- source SHA、command、ABI、MPI、artifact hash完整；
- 不提交重型basis/residual raw arrays，只提交hash-bound compact record；
- 数学公式使用 GitHub fenced `math` block。

每阶段至少运行：

```text
Ruff check
Ruff format --check
compileall
git diff --check
focused serial tests
MPI2/4 identity where required
```

full repository pytest只在最终准备合并时运行；未运行必须写not_run，不得写PASS。

---

# 12. 冻结执行顺序

```text
E0  formal 80-mode Matrix-free DtN component qualification

E1  build and audit frozen M120 global Full3D modal basis Z_M and action Y_M

E2  one B4 residual-snapshot carrier if required
    + ideal 75D / M120 / 75D+M120 / B4+M120 capacity oracle

E3  only if E2 passes: implement one action-MR modal coarse PC

E4  MPI8 20 / 100 / 200 funnel

E5  only if E4 passes:
    one MPI8 full
    restart 90 -> 60 -> 40 -> 30 -> 20
    one MPI1 full

E6  write compact records and response_v6.md, then stop
```

任何 Gate失败立即收口，不得自动进入后续阶段。

不得在本轮启动：

- original Hybrid block iterative；
- Task037b；
- new port compression；
- p3/p5/p-multigrid复活；
- partial/uncondensed新路线；
- 0.7 nm PDE；
- RCWA；
- surrogate/inversion；
- master merge。

完成后只提交证据与 `response_v6.md`，等待下一次审阅。