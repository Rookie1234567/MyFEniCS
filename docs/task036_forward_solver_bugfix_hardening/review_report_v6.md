# Task036 Review Report V6：Hybrid-only 物理闭合与 0.7 nm 可扩展路线

## 1. 审阅身份与优先级修正

```text
review = Task036 Review V6
branch = codex/20260730-task36-forward-solver-bugfix-hardening
reviewed_head = 9b1a318514d3c52806d0311bac8ba7fb8729b8f5
ordinary_default = unchanged
master_merge = not_authorized
primary_program = solve_Hybrid_physics_and_scalability
unrelated_research = paused
whole_domain_Full3D_iterative_as_final_0p7_route = not_sufficient
Full3D_iterative_role = Hybrid_endcap_kernel_and_reference
final_response_document = required
```

本审阅补充并覆盖 Review V5 中容易被误读的优先级：

> 当前阶段的唯一主线是解决 Hybrid 已暴露的物理闭合与可扩展性问题。除为 Hybrid
> 提供 same-input Full3D authority、局部 endcap 求解器或预条件器外，不启动独立的
> whole-domain Full3D production 路线，不恢复 h/p controller、代理模型、反演、广域
> 参数扫描或其他数值研究。

对于当前具有较长 `z`-不变中间区的目标结构，0.7 nm 下必须使用 Hybrid 或等价的
维度约简，才能先删除大段三维体积未知量。静态凝聚与迭代法只能继续压缩剩余系统，
不能替代这第一层降维。

因此目标技术栈固定为：

```text
Hybrid / equivalent dimensional reduction
+ minimum certified 3D endcap buffer
+ strong-trace coupling
+ exact-sequence local h/p
+ assembly-time static condensation
+ matrix-free FGMRES
+ distributed streamed modal core
```

当前 Task036 先完成前两项的 13.5 nm 物理闭合；之后再沿同一 Hybrid 主线推进其余项。

---

## 2. 当前已知结论：不得重复研究

以下问题已有实测结论，后续不得重新发明同类候选：

```text
P tangential direct projection bug                         = fixed
reciprocal high-order trace identity                       = fixed
exact variational traction dual                            = fixed
propagation / traction / recovery beta identity            = fixed
near-degenerate connected-component normalization          = fixed/research-qualified
strong trace algebra g = RLa                               = pass
strong trace resource reduction                            = pass
free trace complement as main scattering-error root        = falsified
significant-mode scalar-CG diagonal one-cell propagation   = pass
broad M120 internal cross-mode mixing                       = not supported
M240/M480/M492 direct expansion                             = closed
226-point scan before anchor closure                        = paused
```

当前唯一明确的物理缺口是：

```text
current physical-QEP port space
+ current interface placement
+ actual fixed-channel / energy closure
```

A004-S exact Full3D trace 的 M120 投影残差由端部向中间快速衰减：

| z, nm | exact M120 trace residual |
|---:|---:|
| 10 | `3.514657e-6` |
| 20 | `9.780687e-8` |
| 30 | `2.881134e-9` |
| 40 | `8.852074e-11` |
| 50 | `2.860216e-12` |
| 60 | `7.992046e-13` |
| 70 | `1.629599e-11` |
| 80 | `3.717959e-10` |
| 90 | `8.687626e-9` |
| 100 | `2.089942e-7` |
| 110 | `5.224931e-6` |

这使“接口距离端部散射或 evanescent boundary layer 太近”成为当前第一优先根因。

---

# 3. Hybrid 问题解决总路线

后续不是只做一次接口试验然后转去其他研究，而是按以下有限决策树连续解决 Hybrid：

```text
Stage H0  bounded interface closure
    ↓ pass
Stage H1  S/P anchor closure and p6 59-goal qualification
    ↓ pass
Stage H2  distributed/streamed modal core
    ↓ pass
Stage H3  matrix-free strong-trace Hybrid FGMRES
    ↓ pass
Stage H4  local exact-sequence h/p endcaps
    ↓ pass
Stage H5  wavelength continuation to 0.7 nm
```

若 H0 失败，不转去 unrelated research，而进入一次有证据约束的 port-space redesign：

```text
H0 fail
→ H0R1 full-interface discrete Bloch port basis
→ 若仍不足，H0R2 transfer-eigenmode / optimal port basis
→ 若在资源预算内仍不能闭合，才判定当前 z-invariant Hybrid decomposition 无生产优势
```

每一级必须通过后才进入下一级；不得同时铺开多个架构。

---

## 4. Stage H0：bounded asymptotic-interface closure

### 4.1 H0-preflight

先对两个冻结候选做纯离线与 assemble-only 检查：

```text
H0a interfaces = 30 / 90 nm
H0b interfaces = 40 / 80 nm  # conditional safety-margin candidate
```

必须验证：

1. modal middle 内逐层材料完全满足 `epsilon(x,y,z)=epsilon(x,y)`；
2. 两个接口都是实际 mesh planes；
3. x/y trace grid 与 cross-section 完全匹配；
4. modal length、scalar-CG cell count、traction beta、field recovery、absorption ledger
   全部使用新接口，不能残留 `10/110` 常量；
5. strong-trace standard/static row maps闭合；
6. local z cells、rows、matrix NNZ和无 factor 的资源预估；
7. Full3D authority identity可复用，不无理由重跑 Full3D。

发现真实 interface-dependent bug应直接修复；不得因此搭新 runner framework。

### 4.2 H0a actual：A004-S，30/90 nm

固定：

```text
p/h/Ny       = p5 / h10 / Ny4
polarization = S
grazing/phi  = 0.5° / 45°
M            = 120 per direction
coupling     = strong trace
backend      = assembly-time static condensation
MPI          = 8
interfaces   = 30 / 90 nm
```

接受条件：

```text
96/96 fixed channels                          pass
abs(R + T + A_volume - 1)                    <= 1e-5
max abs(Delta R/T/A_volume vs Full3D)         <= 1e-4
reduced true residual                         <= 1e-9
strong trace identity                         <= 1e-10
Petrov traction                               <= 1e-8
external DtN / noninterface residual          pass
zero swap                                     true
whole-job peak                                <= 0.85 * Full3D peak
```

若全部通过，H0完成，不运行H0b。

### 4.3 H0b actual：A004-S，40/80 nm

只有H0a满足以下条件才运行：

- algebra、strong trace、Petrov、Floquet、DtN、residual全部通过；
- 相比10/110有明确的通道或energy方向性改善；
- 剩余失败与接口安全余量一致；
- assemble-only预估仍保留资源优势。

H0b使用完全相同的正式Gate。

若H0b通过，记录A004-S development buffer为40/80，但不得外推到其他输入。

若H0b仍失败，停止移动接口，不运行更多位置；进入Stage H0R。

---

## 5. Stage H0R：port-space redesign，而不是转去其他研究

### 5.1 H0R进入条件

仅当30/90与条件允许的40/80均未闭合，并且：

```text
strong trace algebra = pass
scalar-CG significant one-cell propagation = pass
same-input Full3D authority = pass
failure remains in port-space representation / channels / energy
```

才进入port-space重构。

### 5.2 H0R1：full-interface discrete Bloch modes

第一选择是复用Task036已有真实one-cell Schur块，直接在完整独立接口trace空间中求离散
Bloch/transfer modes，而不是继续使用连续二维QEP mode family。

目标：

- port modes与同一3D Nedelec、p/h、Floquet和static-condensation离散严格一致；
- 保留strong-trace trial/test结构；
- 不恢复100 nm中间完整3D体网格；
- 不形成长期常驻的full-trace dense square；
- 先按固定M120资源预算选择/截断离散Bloch modes。

进入actual Hybrid前，必须用现有Full3D exact traces证明：

```text
max exact trace projection residual <= 1e-8
one-cell propagation residual       <= 1e-10
port Gram/biorthogonality            pass
```

满足后只运行一个A004-S actual。若通过，再进入H1；若失败，进入H0R2。

### 5.3 H0R2：transfer-eigenmode / optimal port basis

若full-interface Bloch modes在同等资源预算下仍不能稳定覆盖端点可达trace，则构造
transfer-eigenmode/optimal port basis：

- basis目标是近似endcap激励能够传递到接口的可达解空间；
-以transfer singular/eigenvalue tail给出截断证书；
-只保留满足59-goal和trace tolerance所需的最小basis；
-继续使用strong-trace和Petrov flux耦合。

只允许一个固定basis预算和一个A004-S actual，不进行手选face、单cell enrichment或阈值扫描。

### 5.4 H0R停止条件

若H0R2仍不能同时满足：

```text
physical Gate pass
and whole-job peak <= 0.85 * Full3D peak
```

则正式记录：

```text
CURRENT_Z_INVARIANT_HYBRID_DECOMPOSITION_NO_PRODUCTION_ADVANTAGE_AT_13P5NM
```

这时才允许重新选择更高层的“等价维度约简”方法；不能把whole-domain均匀Full3D迭代
冒充0.7 nm最终方案。

---

## 6. Stage H1：13.5 nm物理域闭合

A004-S通过后，顺序固定：

```text
H1a A049-P = 10° / 90° / P
H1b A001-P = 0.5° / 0° / P
H1c p6/h10 nominal + frozen 59-goal inventory
```

对每个S/P点：

1. 使用同一冻结的interface/port-space选择规则，不手工重新挑位置；
2. 先做trace/buffer预检，再运行actual；
3. 必须通过energy、R/T/A、全部fixed channels、residual和资源Gate；
4. 一个点出现新共同根因时暂停后续点，修根因后重跑原点和邻点；
5. 三个p5 anchors与一个p6 59-goal authority全部通过，才称为
   `HYBRID_13P5NM_PHYSICS_CLOSED`。

在H1完成前，不恢复226点扫描。

---

## 7. Stage H2：scalable modal core

物理闭合后，才替换当前不可扩展direct modal实现：

```text
all-mode MUMPS QEP             -> distributed spectrum slicing / continuation
last-rank modal ownership      -> distributed contiguous mode ownership
replicated global M^2          -> local connected blocks + distributed reductions
all-mode dense multi-RHS       -> mode-block streamed operator actions
all modes permanently resident -> bounded block cache / streamed persistence
```

硬合同：

```text
no replicated global M^2
no resident N_local x M dense object
no resident N_xy x M all-mode field block
working memory approximately linear in local M/rank
```

H2只做modal core，不同时开发h/p或新physics。

---

## 8. Stage H3：matrix-free strong-trace Hybrid FGMRES

H3将strong-trace reduced operator改成matrix-free PETSc shell/nest：

1. modal amplitudes block-wise作用 `R_s L_s a`；
2. local endcap operator响应；
3. left Petrov trace投回modal flux；
4.加入external DtN与diagonal/small-block propagation；
5.外层FGMRES。

预条件器：

- local diagonal blocks：static-condensed H(curl)/trace-aware PC；
- modal block：propagation/impedance diagonal与认证近简并小块；
- interface correction：低成本approximate Schur，不形成全量`A^-1 C`。

这里开发的Full3D iterative只作为bottom/top endcap local solver和Hybrid PC组件，不另开
whole-domain 0.7 nm最终主线。

H3必须与H1 direct authority逐通道等价，并明显降低factor memory。

---

## 9. Stage H4：local exact-sequence h/p endcaps

H3成功后，将Task035d/e已验证的组件接入局部3D endcaps：

- active p4/p5/p6 exact-sequence spaces；
- inactive high-order modes不入矩阵；
- local/directional h；
- Floquet/hanging closure；
- assembly-time cell-interior condensation。

不恢复Task035e失败的blind cellwise action predictor。采用：

```text
frozen structured/directional plans
+ residual/port-error ranking
+ actual post-action Hybrid solve
+ 59-goal acceptance
```

目标是压缩剩余endcap 3D未知量，而不是再次从头研究通用h/p controller。

---

## 10. Stage H5：波长continuation

顺序固定：

```text
13.5 -> 5 -> 2 -> 1 -> 0.7 nm
```

每一级重新资格化：

```text
materials
physical mode/port basis size M
interface buffer
local h/p
FGMRES/PC
59-goal inventory
memory and communication
```

0.7 nm不允许固定M120，也不以不可运行的Full3D峰值为分母。目标为：

```text
whole-job peak <= 2 TiB
zero swap
all numerical/goal Gates pass
```

---

## 11. 当前Task036立即执行的范围

本轮只执行Stage H0：

1. 30/90与40/80离线/assemble-only preflight；
2. A004-S 30/90 actual；
3. 满足条件时才运行A004-S 40/80 actual；
4. 更新Hybrid problem tree，明确下一步进入H1还是H0R。

本轮禁止：

- whole-domain Full3D iterative开发；
- h/p开发；
- surrogate/inversion；
- 226点扫描；
- M240/M480/M492；
- new campaign/state machine/evidence framework；
- H0未完成前实现full-interface Bloch或optimal port basis；
- master merge。

---

## 12. 必须交付的Response

结束前必须创建：

```text
docs/task036_forward_solver_bugfix_hardening/response_v6.md
```

Response必须通俗说明：

1. 30/90与40/80的material、mesh、length、rows/NNZ预检；
2.实际运行了哪个A004-S候选；
3. fixed channels、energy、R/T/A、residual和内存；
4.相比10/110是否单调改善；
5.接口假设是否被actual PDE支持；
6.下一状态是H1还是H0R；
7.未运行项及原因；
8.最终HEAD、修改文件、测试、工作树和远程同步状态。

所有提交只推送当前Task036同名远程分支，不得修改master。
