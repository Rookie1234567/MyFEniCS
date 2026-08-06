# Task037 Review Report V3：局部辅助预条件、Matrix-free DtN、部分凝聚与模态粗空间

## 0. 审阅身份与总体结论

```text
review                         = Task037 Review Report V3
reviewed_branch                = codex/20260803-task37-matrix-free-iterative-development
reviewed_response              = docs/task037_static_condensed_full3d_iterative/response_v2.md
reviewed_numerical_source      = f27a49131ae8e9ada12c3678d55f82dad96c3133
reviewed_compact_record        = task37_v2_preconditioner_funnel_v1.json
ordinary_default               = unchanged
merge_to_master                = not authorized
Task037b Hybrid block solver   = not authorized
0.7 nm production PDE          = not authorized
```

本轮接受的正式结论为：

```text
exact p6 factor-free fine action                       = PASS algebraically
p6 retained matrix/factor/NNZ                          = 0 / 0 / 0
p2 exact-sequence transfer and projected operator      = PASS algebraically
Candidate A p2 + diagonal                              = controlled negative
Candidate B2/B4 naked local Krylov                     = controlled negative
Candidate C current RAS/interface-shift realization    = controlled negative
factor-free storage mechanism                          = positive result
current factor-free preconditioner                     = insufficient
production-qualified iterative replacement             = NO
```

V2 最重要的正结果不是获得了收敛解，而是已经证明：

> **可以在不形成 global A/F、不保留 p6 slab matrix、也不保存任何 p6 ILU/LU factor 的条件下，执行精确 complex128 p6 静态凝聚 fine action。**

V2 最重要的负结果是：

> **全局 p2 correction 加上每个 p6 slab 内部无预条件的固定 2/4 步 GMRES，不足以近似局部 p6 Maxwell inverse。**

因此下一阶段不得继续增加裸局部 GMRES 步数，也不得在 B2/B4/C 上继续微调。下一阶段的核心变化必须是：

```math
\boxed{
\text{将 p2 exact-sequence solver 放入每个局部 p6 slab inverse 内部}
}
```

而不是仅将 p2 当成全局 pre/post correction。

---

# 1. 对 V2 结果的正式审阅

## 1.1 Candidate A：关闭

Candidate A 使用全局 p2 auxiliary correction 和 fine diagonal pre/post：

```math
M_A^{-1}
=
D_6^{-1}
+
P_2 A_2^{-1}P_2^H
+
\text{post diagonal correction}.
```

其 residual 为：

```text
20  steps = 0.9798706637
100 steps = 0.9625338201
```

该候选几乎没有消除 p6 静态凝聚系统的主导误差，正式关闭，不得通过调整 diagonal omega、shift 或增加 pre/post 次数重新开放。

## 1.2 Candidate B2/B4：存储正结果、数值负结果

每个局部 slab 的算子为：

```math
A_{6,j}
=
R_j\left(A_6-i\sigma D_6\right)R_j^T.
```

B2/B4 不保存 $A_{6,j}$ 或其 factor，而使用固定步数局部 Krylov：

```math
z_j
\approx
\operatorname{GMRES}_{k}
\left(A_{6,j},r_j\right),
\qquad k=2,4.
```

当前 local inner preconditioner 明确为：

```text
none
```

B4 的最佳 screen 结果为：

```text
100 steps = 0.1708326448
200 steps = 0.1405734648
```

它证明 factor-free local action 捕捉到了部分误差，但不足以形成可扩展 inverse。继续将 $k$ 从 4 增至 6、8、12 会显著增加每次 outer-PC apply 的 fine-action 次数，却没有证据表明能够解除后期平台，因此禁止继续裸步数扩展。

## 1.3 Candidate C：不能解释为真正 optimized Schwarz 的否定

Candidate C 试图只在人工接口施加 shift，并使用 one-hot RAS correction。但真实 audit 为：

```text
interface rows = 51192
active rows    = 51192
```

所以 `shared_rows_only` mask 覆盖了全部 active rows，并未真正识别：

```math
\Gamma_j^{\mathrm{artificial}}
=
\partial\Omega_j\setminus\partial\Omega.
```

C 的主要新增机制实际是 one-hot RAS 回写；其 100/200-step residual 均劣于 B4。因此：

```text
current Candidate C realization = negative
true geometric impedance Schwarz = not yet tested
```

本报告只允许后续在新的局部 p2-preconditioned候选上附加一次真正几何人工接口 impedance；不允许单独重开 C。

---

# 2. 下一阶段主候选 D：局部 p2 预条件的 factor-free p6 slab inverse

## 2.1 目标

将当前：

```math
z_j
\approx
\operatorname{GMRES}_{4}(A_{6,j},r_j)
```

改成：

```math
\boxed{
z_j
\approx
\operatorname{FGMRES}_{4}
\left(
A_{6,j},
B_{2,j}^{-1},
r_j
\right)
}
```

其中 $B_{2,j}^{-1}$ 是与第 $j$ 个 p6 slab 对应的局部 p2 exact-sequence auxiliary preconditioner。

最终 p6 fine equation、solution、true residual 和 official observables仍全部使用 complex128；p2 只改变预条件路径，不改变所求 Maxwell 离散方程。

## 2.2 局部 p2 transfer

设全局 p2-to-p6 exact-sequence transfer 为：

```math
P_{2\to6}:V_2\to V_{6,\Gamma}^{\mathrm{active}}.
```

第 $j$ 个 p6 slab restriction 为 $R_{6,j}$，对应的 p2 slab restriction 为 $R_{2,j}$。局部 transfer 应由真实实体 support构造：

```math
P_j
=
R_{6,j}P_{2\to6}R_{2,j}^T.
```

禁止按连续 row range、最近坐标或 ad-hoc index slice 构造。必须保持：

- edge/face orientation；
- Floquet phase；
- exact-sequence identity；
- p2/p6 slab support 一致；
- MPI partition identity。

## 2.3 局部 p2 operator

局部 p2 operator应由真实局部 p6 action投影：

```math
A_{2,j}
=
P_j^H A_{6,j}P_j.
```

若局部人工接口使用 impedance/shift，则必须在 p6 slab operator 中先定义，再通过同一 $P_j$ 投影；不得在 p2 和 p6 层使用彼此不一致的边界项。

允许每个 p2 slab使用：

```text
PREONLY + ILU(0) 或 small direct LU
```

但必须报告：

```text
p2 slab rows
p2 slab matrix NNZ
p2 factor NNZ
factor payload
all 16 p2 factors aggregate
```

本候选必须满足：

```text
p6 slab matrix retained = 0
p6 factor count         = 0
p6 factor NNZ           = 0
```

## 2.4 局部 p6 高阶补空间

局部 p2 solve只能处理低阶 p6 成分。Candidate D 允许在局部 p6 FGMRES 中使用一个廉价的 high-order complement smoother，但第一版只能选择：

```text
shifted diagonal / block diagonal / fixed low-degree polynomial
```

不得重新开发已受控失败的 full element patch、high-complement patch、face patch或edge patch。

局部 preconditioner可写成：

```math
B_{2,j}^{-1}
=
P_j\widetilde A_{2,j}^{-1}P_j^H
+
D_{6,j}^{-1}.
```

局部 FGMRES仍冻结为 4 步；不得同时扫描 2/4/6/8 步。

## 2.5 全局两层组合

Candidate D 的全局 PC 推荐使用 multiplicative形式：

```math
x_1=M_{\mathrm{local},D}^{-1}r,
```

```math
r_1=r-A_6x_1,
```

```math
x_2=x_1+Q_w r_1,
```

其中 $Q_w$ 是现有 75D wave coarse correction。现有全局 p2 MUMPS correction 与局部 p2 slabs可能信息重复；第一版允许保留，但必须单独审计其增益。若移除全局 p2 后 residual不恶化，则应释放它，以降低未来内存。

---

# 3. Candidate D 的测试和受控漏斗

## D0：纯代数和局部效能

必须先在 tiny/medium fixture上完成：

1. $P_j$ orientation/Floquet identity；
2. $A_{2,j}=P_j^H A_{6,j}P_j$ action误差 `<=1e-11`；
3. local p2 solve finite/deterministic；
4. p6 factor inventory严格为零；
5. local p2 factor aggregate memory ledger；
6. one local slab contraction test；
7. MPI2/4 identity。

至少对 low/high/mixed 三类 local source报告：

```math
\rho_j
=
\frac{\|r_j-A_{6,j}z_j\|}{\|r_j\|}.
```

Candidate D 必须明显优于当前无预条件 B4；若 mixed/high source contraction没有至少 1.5 倍改善，则不得启动 p6/h10 heavy screen。

## D1：MPI8 20/100/200-step funnel

开发阶段继续使用 MPI8，以缩短反馈时间。只允许运行一个冻结 Candidate D：

```text
local p6 Krylov steps  = 4
local inner PC         = local p2 exact-sequence solve + diagonal complement
slabs                  = 16
overlap                = 0.125
partition              = partition-of-unity
wave coarse            = 75D
outer                   = right FGMRES(90)
```

Gate：

### 20-step

```text
finite / no NaN
true residual < 0.45
no worse than B4 at iteration 20
p6 factor NNZ = 0
MPI8 peak <= 7.0 GiB
```

### 100-step

```text
true residual <= 0.15
last 40 iterations net decrease
strictly better than B4@100 = 0.1708326448
```

### 200-step

```text
true residual <= 0.05
predicted iterations <= 3000
predicted wall <= 7200 s
strictly better than B4@200 = 0.1405734648
```

未通过任一阶段立即停止，不得调 shift、slab数、p2阶次或 local steps后自动重跑。

## D2：full 和极限内存

只有 D1 全部通过后：

1. 一次 MPI8 full solve；
2. reported/condensed/full-FE residual全部通过；
3. canonical field、12+12 channels、R/T/A通过；
4. 再做 restart缩减；
5. 最优 restart下做一次 MPI1 full。

MPI1 Gate：

```text
whole-job peak <= 2.0 GiB
preferred      <= 1.5 GiB
swap           = 0
p6 factor NNZ  = 0
```

---

# 4. FGMRES restart 研究边界

restart研究只能在某个 Candidate D 或后续候选已经完成 full numerical pass后进行。

测试顺序冻结为：

```text
90 -> 60 -> 40 -> 30 -> 20
```

每个值只运行一个 100-step continuation或基于已收敛解的正式受控比较；若 residual出现明显停滞，则停止继续降低。

FGMRES大约保存：

```math
2m+O(1)
```

个 fine vectors。因此当前小模型中收益有限，但在 0.7 nm 大模型中是必要的。restart降低不能用于掩盖预条件器不足。

---

# 5. Matrix-free DtN：本轮必须实现

## 5.1 定位

当前 80 个 DtN modes不是 p6/h10 内存主项，但 0.7 nm 下 modal order可能增长到数千或更多，因此 Matrix-free DtN不再延期。

它必须保持与当前辅助变量 formulation完全相同的物理模式、极化、beta分支和功率归一化；只改变存储与 action实现。

## 5.2 正向 action

当前 condensed operator含：

```math
A_{\mathrm{cond}}
=
F-CH^{-1}D.
```

Matrix-free DtN应按如下过程实现：

1. 从 FE tangential trace 投影得到 modal coefficients：
   ```math
   y=Dx;
   ```
2. mode-by-mode/block-by-block求解：
   ```math
   z=H^{-1}y;
   ```
3. 将 modal traction重新注入 FE trace：
   ```math
   t=Cz;
   ```
4. 返回：
   ```math
   A_{\mathrm{cond}}x=Fx-t.
   ```

不得物化完整 C/D dense coupling。H 可以保留为每个通道的 1x1/2x2 小块或小型 diagonal/block-diagonal对象。

## 5.3 必须实现的能力

```text
forward mult
auxiliary amplitude recovery
mode-key-preserving R/T extraction
optional adjoint/Hermitian-transpose action for future coarse construction
```

## 5.4 资格化 Gate

- 对 deterministic random vectors：
  ```math
  \|A_{DtN,MF}x-A_{DtN,block}x\|/\|A_{DtN,block}x\|\le10^{-11};
  ```
- auxiliary recovery `<=1e-11`；
- 80/80 mode keys、beta、polarization、Rayleigh flags一致；
- serial、MPI2、MPI4 identity；
- explicit C/D materialized count = 0 in matrix-free profile；
- ordinary/default path不改变。

Matrix-free DtN完成后应直接作为 Candidate D 及后续候选的 fine action组成部分；不因它单独启动额外 full PDE。

---

# 6. 部分凝聚：只批准一次小型对照

## 6.1 目的

完全静态凝聚将 450 个 cell-interior modes全部消去，得到稠密的 432x432 trace Schur。部分凝聚用于回答：

> 保留一部分低/中阶 interior modes，能否以适度增加 Krylov vectors为代价，使局部算子更容易被 factor-free auxiliary PC预条件？

## 6.2 唯一允许的策略

使用已存在的 exact-sequence hierarchical transfer，保留嵌入 p4 的 cell-interior subspace，消去 p5-p6 interior complement。

p6 每单元 interior维数：

```math
3p(p-1)^2=450.
```

p4 embedded interior维数：

```math
3\cdot4\cdot3^2=108.
```

因此每单元消去约342个最高阶 interior modes，保留108个 p4-core interior modes。252 cells下，新增全局 interior unknowns约：

```math
252\times108=27216.
```

粗略 active rows由51192增至约78408，再加80 auxiliary rows。

禁止使用按本地 index硬切的“前108个模式”；必须通过 exact-sequence/hierarchical identity构造。

## 6.3 执行边界

只允许：

1. action equivalence/恢复测试；
2. setup-only memory ledger；
3. 一个 MPI8 20-step screen；
4. 仅当20-step residual相对 fully-condensed Candidate D或B4改善至少25%，且peak增加不超过25%，才运行100-step；
5. 200-step只有在100-step true residual `<=0.15`时授权。

本轮不授权完全 uncondensed p6 full solve；若部分凝聚无明显收益，凝聚路线立即关闭。

---

# 7. 借用 Hybrid 本征模的 Full3D coarse/deflation：最后一个候选

## 7.1 可行性判断

该想法是可行的，而且 Task036 的负结果并不否定它。

Task036否定的是：

> 用 M120 模态作为完整 direct Hybrid接口空间，独立代表全部 tangential E和magnetic traction。

Full3D iterative coarse space不要求模态完备。完整 p6 fine operator与Krylov space仍保留全部 Cauchy physics，模态只用于消除最慢的长程传播误差。因此：

```text
modal direct Hybrid failure != modal coarse-space failure
```

## 7.2 非 Hermitian Petrov coarse correction

从原 M120 Hybrid保留正/反向右模态 $Z_m$，并使用匹配左/伴随模态 $W_m$。将其映射并延拓到完整 p6 static active trace space后构造：

```math
E_m=W_m^H A_6 Z_m.
```

modal coarse correction为：

```math
Q_m r
=
Z_mE_m^{-1}W_m^H r.
```

与最佳 factor-free/local auxiliary PC $M_0^{-1}$ 采用 multiplicative组合：

```math
\boxed{
M_{\mathrm{modal}}^{-1}r
=
M_0^{-1}r
+
Q_m\left(r-A_6M_0^{-1}r\right)
}
```

这样 modal basis中的误差由 coarse solve消除，其余端部、evanescent和traction complement仍由完整 Full3D FGMRES修正。

## 7.3 coarse basis构造要求

不得只把中间接口系数直接塞入全局向量。每个 coarse vector必须：

1. 在中间规则区使用 Task036 已资格化的 long-range modal propagation；
2. 映射到 p6 active trace coordinates，保持Floquet和orientation；
3. 对 top/bottom endcap使用一致的局部 harmonic extension或冻结的物理 extension；
4. 通过 full fine action计算 $A_6Z_m$；
5. 检查 $W_m^HA_6Z_m$ 的rank和condition；
6. 不以 teacher/direct solution投影构造basis。

第一版只允许一个冻结的 M120 coarse candidate，不进行 M40/M80/M160 rank sweep。

若使用完整正反向240列，当前51k-row模型显式 complex128 basis约：

```math
51192\times240\times16\approx187.5\ \mathrm{MiB}.
```

当前anchor可接受，但0.7 nm下不得长期显式存储 $N\times240$ dense basis；后续需结构化/matrix-free prolongation。本轮只评价数值机制。

## 7.4 授权顺序和 Gate

该候选放在最后：

```text
Candidate D
-> 部分凝聚 bounded comparison（若需要）
-> modal coarse Candidate E
```

Candidate E只允许在：

- Candidate D未通过，或
- Candidate D通过但迭代数仍明显不可接受

时启动。

MPI8 Gate：

```text
20-step residual must improve over best non-modal candidate
100-step residual <= 0.10
200-step residual <= 0.05
coarse rank full
coarse condition explicitly reported
additional peak <= 0.30 GiB on current anchor
```

若未通过，不得调整 modal rank、重新选择模式或增加Task036 correctors。

本候选是：

```text
Full3D modal-assisted preconditioner
```

不是：

```text
Hybrid iterative solver
```

Task037b 的 original Hybrid block iterative仍需后续独立任务授权。

---

# 8. 真正几何 optimized Schwarz：只作为 Candidate D 的一次附加变体

若 Candidate D 的100-step residual下降明显但200-step略高于0.05，允许在完全相同的局部p2-preconditioned配置上，增加一次真正的人工接口 impedance/RAS变体。

人工接口必须由几何子域边界定义：

```math
\Gamma_j^{art}
=
\partial\Omega_j\setminus\partial\Omega.
```

只对该界面上的edge/face trace modes施加：

```math
(\mu^{-1}\nabla\times E)\times n+i\eta E_t=g.
```

必须报告：

```text
artificial-interface row count
physical-boundary excluded row count
non-interface shift row count = 0
```

只允许一个冻结 $\eta$，禁止参数扫描。若200-step没有至少20%改善，关闭该路线。

---

# 9. 延期但保留的优化

## 9.1 exact factor reuse

规则结构中MPI1存在9个exact duplicate factors，但复杂结构下重复率可能消失，因此不进入通用主路线。只有真实目标结构仍显示较高exact duplicate count时再实现。

## 9.2 complex64 local factors

只允许作为未来可选PC优化；fine operator、solution、true residual、DtN和official postprocess必须保持complex128。本轮不执行。

## 9.3 fully uncondensed p6

本轮只批准一次p4-core部分凝聚对照，不批准完全不凝聚的大型campaign。是否进入uncondensed应由部分凝聚证据决定并另行审阅。

---

# 10. 执行顺序与停止语义

冻结执行顺序：

```text
R0  保存V2负结果，不重开A/B2/B4/C
R1  实现并资格化matrix-free DtN
R2  构造局部p2 slab transfer/operator/factor
R3  Candidate D local efficacy + MPI8 20/100/200 funnel
R4  通过后一次MPI8 full
R5  通过后restart 90->60->40->30->20
R6  最优配置一次MPI1 full，目标<=2.0 GiB
R7  若D失败，做一次p4-core partial-condensation bounded comparison
R8  最后只允许一个M120 Petrov modal coarse Candidate E
R9  提交response_v3.md并停止
```

无论正负，不得自动：

- 开发Task037b Hybrid block solver；
- 运行0.7 nm PDE；
- 进行多参数PC sweep；
- 修改物理、DtN modes或通道tolerance；
- fallback到global direct后声明iterative成功；
- 将screen max-it输出写成official R/T/A。

---

# 11. 最终响应要求

完成受控阶段后创建：

```text
docs/task037_static_condensed_full3d_iterative/response_v3.md
```

必须包含：

1. source/branch/environment/clean identity；
2. Matrix-free DtN action、aux recovery和mode-key identity；
3. Candidate D局部p2 slab尺寸、matrix/factor NNZ和总内存；
4. D的local low/high/mixed contraction；
5. D的20/100/200完整residual history与screen Gate；
6. 所有full solve的true residual、canonical field、12+12 channels、R/T/A；
7. restart结果（仅在full pass后）；
8. MPI1最低内存（仅在授权后）；
9. 部分凝聚证据或明确not_run；
10. modal coarse的basis/rank/condition/memory/残差或明确not_run；
11. 全部测试、未运行项和changed files；
12. 最终分类。

最终提交并推送当前Task037分支后停止等待审阅；不得合入master。
