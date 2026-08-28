# Task040 Review Report V7：尺度无关的 Schur identity 裁决、误差分层与主线自动续推

## 0. 审阅身份与正式裁决

```text
review                                      = Task040 Review Report V7
reviewed_branch                             = codex/20260822-task40-hybrid-side-factor-pc
reviewed_branch_head_before_review          = 3bdf4439cd0b82f746dd6b5faf97b986730127c6
reviewed_response                           = response_v7.md
reviewed_primary_outcome                    = outcomes/full_interface_schur_identity.md
review_status                               = CONTINUE_WITH_SCALE_NORMALIZED_IDENTITY_ADJUDICATION
V6_2_record_under_V6_absolute_gate          = valid_negative_preserved
V6_2_project_level_algebra_conclusion       = unresolved
Task040_closed                              = false
full_interface_family_retired               = false
old_776_route_C_retired                     = true
factor_only_full_side_rescue                = permanently_closed
next_required_stage                         = V7_SCALE_NORMALIZED_IDENTITY_AND_ERROR_LOCALIZATION
conditional_V6_3_continuation               = authorized_without_new_review
conditional_moving_PML_continuation         = authorized_without_new_review
conditional_adaptive_Schwarz_continuation   = authorized_without_new_review
full_target_0p7nm_PDE                       = forbidden_in_Task040
same_branch_continuation                    = required
new_execution_branch                        = forbidden
master_or_Task039_write                     = forbidden
ordinary_default_change                     = forbidden
merge_approval                              = NO
response_required                           = response_v8.md
```

本 Review 接受并保留 V6-2 的原始事实：在 Review V6 规定的**绝对范数阈值**下，
`gate_pass=false`。不得删除、覆盖或把原记录改写成 pass。

但 V6-2 的当前证据还不足以证明完整接口 Schur 代数错误。原因是四个失败指标均为有量纲的
绝对二范数，正式记录没有同时保存 source/output/operator-action 的尺度，因而无法区分：

```text
A. 正确的大尺度线性算子上的浮点舍入、MUMPS backsolve 和 MPI reduction 误差；
B. group solve 精度不足；
C. canonical scatter / reverse-add 的累加顺序误差；
D. group partition 没有形成真正 block-diagonal interior；
E. Schur sign、row mapping 或遗漏耦合等真实代数错误。
```

因此，本 Review 不放宽阈值、不修改物理，也不直接重跑相同 formal；而是把 identity Gate
改造成**尺度无关的 relative/backward-error Gate**，同时在一次 factor setup 内分层定位误差。

若尺度无关 identity 通过，Codex 必须立即回到 V6-3 full-spectrum Floquet-DtN 主线，不等待
新审阅。若完整接口实现经过一次明确修复仍为真实代数失败，Task040 也不整体关闭，而是跳过
依赖该接口实现的路线，直接进入不依赖完整接口 Schur 的 adaptive impedance Schwarz 主线。

---

## 1. V6-2 已建立的正结果与未解决项

### 1.1 已建立的工程与资源事实

V6-2 已完成：

```text
Gamma_L rows                       = 7560
Gamma_U rows                       = 7560
joint interface rows               = 15120
canonical key coverage             = exact
owner-local mapping                = pass
per-rank full-interface replica    = false
FE-sized numeric allgather         = false
zero map                           = 0
restriction/prolongation roundtrip = 0
group factor lifecycle             = 3 -> 0
full-side exact factor             = 0
global direct factor               = 0
process-tree RSS peak              = 27,801,870,336 B ≈ 25.89 GiB
wall                                = 339.7141449260016 s
swap                                = 0
```

这些结果继续有效。它们说明完整 15120-row distributed MatPython/MatShell 外壳、canonical
owner mapping、三组 factor mechanism oracle 和生命周期已经建立。

### 1.2 V6 绝对 Gate 的观测

| 检查 | V6 固定绝对阈值 | V6-2 观测 | V6 分类 |
|---|---:|---:|---|
| Gamma action | `<=1e-10` | `3.783538480529195e-10` | fail |
| full-interior residual | `<=1e-10` | `1.2298155651030158e-9` | fail |
| linearity | `<=1e-11` | `6.766170711131541e-9` | fail |
| repeat | `<=1e-11` | `1.4161645932820494e-9` | fail |
| zero map | `<=1e-13` | `0` | pass |
| roundtrip | `<=1e-11` | `0` | pass |

上述表必须继续保留。V7 不通过删除 absolute fields 或改变旧 checker 来取得通过。

### 1.3 尚未运行

因为 identity stop 发生在 exact runner 前：

```text
exact interface FGMRES              = not_run
five-source full bare-F residual     = not_run
exact output packets                 = not_run
full-spectrum Floquet-DtN sweep      = not_run
moving-PML sweep                     = not_run
adaptive impedance Schwarz           = not_run
factor-free local service            = not_run
bottom/top/full Hybrid               = not_run
h3 scaling                           = not_run
0.7 nm measured capacity             = not_run
```

因此不得写成“全部新路线失败”。

---

## 2. 为什么必须使用尺度无关 identity

当前 repeat 和 linearity runner 直接计算绝对范数：

```text
||Sx(first)-Sx(repeat)||
||S(x+alpha*y)-Sx-alpha*Sy||
```

Gamma action 和 interior residual 也使用绝对范数。正式 15120 维 deterministic vectors 不是
单位范数，Schur output 的量级也没有进入 Gate。一个线性 operator、source 或单位系统整体乘以
常数时，绝对误差会相应变化，但代数正确性不应改变。

V7 因此要求同时保存：

```text
absolute error
source norm
每个中间量与output norm
relative/backward error
```

旧 absolute Gate 继续作为 diagnostic；新的正式 identity 决策只由无量纲 relative/backward
error 加结构 Gate 决定。

这不是把 `1e-11` 放宽为 `1e-8`。相反，它要求证明误差相对于实际 operator action 仍在原来
规定的 `1e-10/1e-11` 精度范围内。

---

# 3. V7-1：新增 scale-normalized identity 指标

## 3.1 通用安全分母

对所有非零 probe 使用：

```math
\tau_{safe}=10^{-300}.
```

`zero-map` 继续独立使用绝对 Gate，不使用相对分母。

## 3.2 Repeat relative error

设两次相同输入的结果为 `y1` 和 `y2`：

```math
\eta_{repeat}
=
\frac{
\lVert y_1-y_2\rVert_2
}{
\max\left(
\lVert y_1\rVert_2+
\lVert y_2\rVert_2,
\tau_{safe}
\right)
}.
```

记录：

```text
source_norm
y1_norm
y2_norm
absolute_difference
relative_difference
```

正式 Gate：

```text
eta_repeat <= 1e-11
```

## 3.3 Linearity relative error

固定沿用当前 `alpha = 0.37 - 0.21j`，不得换更容易通过的系数：

```math
\eta_{linear}
=
\frac{
\left\lVert
S(x+\alpha y)-Sx-\alpha Sy
\right\rVert_2
}{
\max\left(
\lVert S(x+\alpha y)\rVert_2+
\lVert Sx\rVert_2+
|\alpha|\lVert Sy\rVert_2,
\tau_{safe}
\right)
}.
```

记录所有三个输入/输出范数、absolute discrepancy 和 relative discrepancy。

正式 Gate：

```text
eta_linear <= 1e-11
```

## 3.4 Schur action vs independent full elimination

对每个 deterministic source `x_Gamma`，记：

```text
y_schur = S_Gamma x_Gamma
y_full  = R_Gamma F E(x_Gamma)
```

其中 `E(x_Gamma)` 是由三个 group interior solve 恢复出的完整 active state。定义：

```math
\eta_{Gamma}
=
\frac{
\lVert y_{schur}-y_{full}\rVert_2
}{
\max\left(
\lVert y_{schur}\rVert_2+
\lVert y_{full}\rVert_2,
\tau_{safe}
\right)
}.
```

正式 Gate：

```text
max eta_Gamma over three vectors <= 1e-10
```

## 3.5 每个 group 的 interior backward error

对 homogeneous elimination probe：

```math
r_{I,j}
=
A_{I_jI_j}x_{I,j}
+
A_{I_j\Gamma}x_{\Gamma,j}.
```

定义：

```math
\eta_{I,j}
=
\frac{
\lVert r_{I,j}\rVert_2
}{
\max\left(
\lVert A_{I_jI_j}x_{I,j}\rVert_2+
\lVert A_{I_j\Gamma}x_{\Gamma,j}\rVert_2,
\tau_{safe}
\right)
}.
```

不要求保留全部 `A_II`。在 homogeneous probe 中可由：

```math
A_{I_jI_j}x_{I,j}
=
r_{I,j}-A_{I_j\Gamma}x_{\Gamma,j}
```

重建分母所需向量。

必须按：

```text
group0
group1
group2
```

分别记录，不能只给一个合并 interior norm。

正式 Gate：

```text
max eta_I,j over all groups and three vectors <= 1e-10
```

## 3.6 Group solve repeat error

对同一个 `A_IGamma*x_Gamma`，每个 group 连续调用两次 factor solve，记录：

```math
\eta_{solve-repeat,j}
=
\frac{
\lVert x_{I,j}^{(1)}-x_{I,j}^{(2)}\rVert_2
}{
\max\left(
\lVert x_{I,j}^{(1)}\rVert_2+
\lVert x_{I,j}^{(2)}\rVert_2,
\tau_{safe}
\right)
}.
```

正式诊断线：

```text
eta_solve_repeat,j <= 1e-11
```

若此项失败，优先分类为 group factor solve precision/repeat blocker，不得先修改 scatter。

---

# 4. V7-2：三层误差定位

V7 formal 必须把同一 source 的误差拆成以下三层。

## 4.1 Layer A：group factor solve

每个 group 记录：

```text
rhs norm
solution norm
repeat solution relative difference
interior backward error
factor solve count
factor identity
MUMPS/PETSc readback fields available in current build
```

不得只记录合并的 three-group residual。

## 4.2 Layer B：group-local Schur contribution

对每个 group 分别构造：

```text
group1 principal A_GammaGamma contribution
group0 interior correction
group1 interior correction
group2 interior correction
```

在进入 canonical reverse scatter 前，分别测试：

```text
repeat relative error
linearity relative error
output norm
finite
```

如果 group-local output 已经不稳定，则问题不在 global canonical scatter。

## 4.3 Layer C：canonical scatter 与累加

新增一个 reference-only 的 fixed-order decomposed action：

```text
1. 每个 group contribution先进入独立 canonical Vec；
2. 每个 scatter只写一个零初始化目标；
3. 最终在owner-local canonical Vec上按固定顺序做AXPY：
   middle_boundary
   - middle_correction
   - lower_correction
   - upper_correction
```

它不得使用 FE-sized allgather 或 full-interface per-rank replica。

比较：

```text
D0 = 当前in-place reverse-add action
D1 = 独立contribution + fixed-order local AXPY action
```

记录：

```math
\eta_{D0,D1}
=
\frac{
\lVert D0(x)-D1(x)\rVert_2
}{
\max(\lVert D0(x)\rVert_2+\lVert D1(x)\rVert_2,\tau_{safe})
}.
```

如果 D1 通过而 D0 不通过，正式分类：

```text
V7_CANONICAL_ACCUMULATION_ORDER_BLOCKER
```

此时允许用 D1 替代 D0 作为后续 full-interface mechanism action。D1 只增加少量 15120-row
scratch vectors，不改变渐近复杂度，不允许因此增加 full replica 或 dense matrix。

如果 D0/D1 都通过，保留实现更简单、内存更低的一项；必须记录选择原因。

---

# 5. V7-3：尺度不变性测试

## 5.1 Tiny regression

现有 7×7 complex Schur tiny oracle 增加固定二进制缩放：

```text
s = 2^-10, 1, 2^10
```

对同一个 matrix/source family 检查：

```text
absolute error可以随尺度变化
relative error保持在对应Gate内
三种尺度的classification一致
```

不得通过把 matrix 归一化后只测归一化版本。

## 5.2 Formal scale triplet

在同一次 MPI8 factor setup 内，对一个 deterministic source 和 linearity pair 运行：

```text
s = 2^-10, 1, 2^10
```

只增加 action/solve 调用，不重新建立 factors。

要求：

```text
all metrics finite
所有尺度的relative Gate均通过，才可判定identity pass
不得只选择最容易通过的尺度
```

记录 relative error 的最大值、最小值与 spread。spread 只用于诊断，不单独替代主 Gate。

---

# 6. V7-4：唯一一次 group-solve refinement 条件分支

只有出现以下任一情况才触发：

```text
max eta_I,j > 1e-10
or max eta_solve-repeat,j > 1e-11
```

不触发时不得实现或运行 refinement 菜单。

## 6.1 固定 refinement

只允许**一次** residual-correction：

```math
x^{(0)}=A_{II}^{-1}b,
```

```math
r^{(0)}=b-A_{II}x^{(0)},
```

```math
\delta=A_{II}^{-1}r^{(0)},
```

```math
x^{(1)}=x^{(0)}+\delta.
```

禁止：

```text
2/3/5次 refinement 扫描
改变 MUMPS ordering
改变 pivot tolerance
BLR/drop 参数扫描
重新建立 full-side factor
```

实现优先级：

```text
1. 当前 PETSc/MUMPS 路径若可证明并readback固定 one-step refinement，则使用原生路径；
2. 否则只在mechanism oracle中保留或按group逐一重建A_II action，完成一次外部residual correction；
3. 不同时常驻三个额外A_II副本，只允许bounded diagnostic transient。
```

refinement 前后必须记录每 group backward error 和内存 transient。

## 6.2 决策

```text
refinement使所有relative identity Gate通过
    -> V7_GROUP_SOLVE_REFINEMENT_IDENTITY_PASS
    -> 同一新family继续V6-3

refinement改善>=100x但仍略高于Gate
    -> 保存结果并检查唯一明确implementation issue；不得再增加次数

refinement改善<10x
    -> group solve不是主因，回到partition/scatter诊断
```

refinement 只属于 h4 exact mechanism oracle。最终 V6-7 factor-free candidate 仍必须删除所有
full-cross-section factors。

---

# 7. V7-5：group partition closure 审计

只有 D0/D1 relative identity 均失败，而 group solve backward/repeat 均通过时执行。

完整接口 Schur 公式要求移除 Gamma 后，三个 interior block 在真实 bare `F` 图上互不耦合。
必须从 current explicit bare `F` 直接审计：

```text
I0-I1 off-block nnz / norm
I0-I2 off-block nnz / norm
I1-I2 off-block nnz / norm
I0-Gamma_U forbidden coupling
I2-Gamma_L forbidden coupling
unassigned active rows
overlapping interior rows
Gamma/interior overlap
```

对每个 block 记录：

```text
local/global nnz
Frobenius norm或可复核等价norm
relative norm vs relevant row-block norm
row/key sample，最多bounded数量
```

正式 closure Gate：

```text
所有禁止 interior-interior coupling 的relative norm <=1e-13
所有active rows恰好属于一个interior或Gamma role
```

## 7.1 明确 closure 缺口时的唯一修复

若发现真实非零跨组 coupling：

```text
1. 不得只放宽identity阈值；
2. 只允许一次graph-separator closure修复；
3. 优先把遗漏的、位于人工截面上的高阶trace row纳入Gamma；
4. 新Gamma必须仍有canonical physical identity和owner coverage；
5. 不得把大块3D interior静默提升为full interface；
6. joint rows增长超过原15120的25%时停止该修复路线。
```

修复后只重跑 focused identity，不直接运行五源。

若 closure rows 无法获得正确 canonical tangential identity，或接口增长超过 25%，分类：

```text
V7_THREE_GROUP_SEPARATOR_NOT_EXACT_FOR_CURRENT_CONDENSED_F
```

此时 full-interface/Fourier sweep family 关闭，但 Task040 不整体关闭，直接转 V7-8 adaptive
impedance Schwarz。

---

# 8. V7-6：一次 MPI8 formal 与自动判定

## 8.1 测试顺序

正式运行前只做：

```text
scaled tiny serial
scaled tiny MPI2
D0/D1 contribution focused test
one group backward-error focused test
Ruff touched modules
compileall touched modules
```

不运行 full repository pytest，不重复无关 MPI4。

## 8.2 Formal 固定范围

```text
case                    = same 5 nm p6/h4 bottom bare F
MPI / threads           = 8 / 1
physical/QEP/DtN        = unchanged; C/D/H=0; QEP=0
full-side factor        = 0
three group factors     = mechanism oracle only
source vectors          = existing three deterministic vectors
scale triplet           = 2^-10, 1, 2^10
D0/D1                   = both evaluated in same setup
conditional refinement  = at most one step
```

资源：

```text
identity adjudication preferred peak <=35 GiB
identity hard stop                 =45 GiB
swap                               =0
identity-only wall target          <=1800 s
identity hard wall                 =3600 s
```

若 identity pass 后同一进程进入 V6-3 continuation，则总 wall 与 watchdog继续使用 Review V6
既有 `21600 s` 预算；不得因 continuation 把 identity-only 结果写成超时。

## 8.3 分类

### D0 直接通过

```text
V7_SCALE_NORMALIZED_IDENTITY_PASS_D0
```

保留 D0，立即进入 V6-3。

### D1 通过、D0 失败

```text
V7_SCALE_NORMALIZED_IDENTITY_PASS_FIXED_ORDER_D1
```

采用 D1，立即进入 V6-3。

### 一次 refinement 后通过

```text
V7_SCALE_NORMALIZED_IDENTITY_PASS_ONE_REFINEMENT
```

mechanism oracle采用固定 one-refinement solve，立即进入 V6-3；最终 factor-free路线仍按
V6-7重新资格化。

### partition closure 修复后通过

```text
V7_SCALE_NORMALIZED_IDENTITY_PASS_SEPARATOR_CLOSURE
```

先检查新接口增长与 spectral canonical identity，再进入 V6-3。

### relative Gate 仍失败

必须根据实际证据分类为以下之一：

```text
V7_GROUP_SOLVE_PRECISION_BLOCKER
V7_CANONICAL_ACCUMULATION_ORDER_BLOCKER
V7_GROUP_PARTITION_CLOSURE_BLOCKER
V7_TRUE_FULL_INTERFACE_SCHUR_ALGEBRA_FAIL
```

禁止只写笼统的 `identity_fail`。

---

# 9. V7-7：identity 通过后立即推进 full-spectrum 主线

identity 通过后不等待新 Review，按 Review V6 的 V6-3 继续；V7 增加以下实现约束和经济筛选。

## 9.1 不得直接 FFT raw active coefficients

V6-2 当前 action 的 `value_basis` 是：

```text
current_raw_active_coefficients
```

V6-3 spectral transform 必须先应用每个 trace entity 的 canonical block transform，得到有明确
物理意义的：

```text
periodic cell/orbit index
entity type
local high-order trace channel
tangential component
orientation/sign
Floquet phase identity
```

然后才能按同一 channel class 在 x/y 做 FFT 或 streamed DFT。

禁止：

```text
对raw PETSc row顺序直接FFT
丢弃无法组成tensor orbit的trace channel
把canonical key排序误当空间FFT顺序
Floquet phase施加两次
```

## 9.2 Transform identity

先在 actual 15120-row trace 上验证：

```text
canonical block transform roundtrip <=1e-10
FFT/DFT forward-inverse roundtrip    <=1e-10
mass-weighted Parseval               <=1e-10
Floquet phase once                   = pass
all trace channels accounted         = pass
propagating + evanescent inventory   = complete
```

serial/MPI2 helper通过后，formal只需当前 MPI8 同进程检查，不再单独跑 MPI4 heavy。

## 9.3 两源经济 screen

先运行：

```text
external_dtn_coupling
fixed_random_repeat_0
```

checkpoint：

```text
one apply
8 / 16 / 32 / 64
```

继续到五源的 screen 条件：

```text
both finite
and (
    both r32 <=0.7
    or both 16->32下降 >=0.15 decade
    or both r64 <=0.5
)
```

若到 r64：

```text
both >0.8
and 32->64下降<0.10 decade
```

则直接分类：

```text
FULL_SPECTRUM_SWEEP_NO_SIGNAL
```

并进入 moving-PML，不扫描 symbol、cutoff、sweep count 或 impedance 常数。

两源有正信号后，运行 Review V6 固定五源 Gate并自动推进 V6-7 factor-free local service。

---

# 10. V7-8：full-interface 真失败时仍推进主线

如果经过 D0/D1、条件 one-refinement 和唯一 separator closure 后，完整接口 Schur 仍为真实
代数失败，不能继续依赖该 action 的 full-spectrum sweep。

但 Task040 不因此整体关闭。

## 10.1 partition正确但canonical action实现失败

允许直接实现一次 moving-PML **full-state PC**：

```text
exact outer bare F unchanged
local extended groups + PML collar
full active residual restriction
forward/backward full-state correction
no explicit S_Gamma solve dependency
```

仍使用 Review V6 固定 PML 配置，不扫描。

## 10.2 partition本身不成立或PML也依赖同一错误separator

直接进入 adaptive impedance Schwarz：

```text
outer FGMRES on exact bare F
3D overlapping brick subdomains
impedance local boundary
fixed mild absorption shift
partition-of-unity weighting
adaptive Maxwell-harmonic local coarse
```

该路线不要求三个 z-group interiors 构成 exact block-diagonal partition，因此是 arbitrary-3D
方向的独立主线。

## 10.3 停止边界

只有以下条件才停止等待下一轮审阅：

```text
scale-normalized identity显示真实代数失败，
且moving-PML full-state pilot无信号，
且adaptive impedance Schwarz h4 pilot也无信号；

或正信号路线无法删除full-cross-section factors；

或出现物理/资源/ABI不可解释失败。
```

不得因为 full-interface family 单独失败就写“0.7 nm 无解”。

---

# 11. 与 0.7 nm 的绑定

V7 的 identity 修正本身不降低 DoF，但它决定是否可以继续使用分布式完整接口波传播层。
任何通过路线仍必须最终满足：

```text
full-side exact factor              = 0
full-cross-section factor           = 0
global direct factor                = 0
global dense coarse factor          = 0
volume action                       = matrix-free path available
physical DtN                        = FFT/streaming; explicit W=0
max local factor rows               <=1024
full basis replication              = false
FE-sized numeric allgather          = false
Krylov restart/live vectors         = bounded
swap                                =0
```

D1 fixed-order action可以作为机制实现，因为它只增加 bounded interface scratch vectors；不能
把它升级为显式 dense interface storage。

one-refinement 和三个 group factors只属于 h4 oracle。0.7 nm-oriented classification必须在
V6-7 删除这些对象后重新判定。

`response_v8.md` 无论成功或失败都必须更新：

```text
误差来源分类
relative identity数据
主线实际推进位置
0.7 nm blocker被消除或仍存在的部分
下一步是Hybrid-specific还是arbitrary-3D Full3D transferable
```

---

# 12. 最小测试政策

| 变更 | 最小测试 |
|---|---|
| relative metric helper | serial scaled tiny |
| group contribution / D1 | serial + MPI2 |
| group solve backward audit | serial + MPI2 |
| separator graph audit | tiny deterministic + metadata test |
| canonical trace transform | serial + MPI2 |
| formal前 | touched Ruff、compileall、focused suite |
| closeout | one consolidated focused suite + doc contract |

默认不运行：

```text
full repository pytest
每commit MPI4
无关Task39 tests
无关benchmark checker全集
重复formal identity而没有具体修复
```

implementation bug可自行最小修复并继续：

```text
norm denominator/schema
owner-local vector extraction
VecScatter mode/order
scratch lifecycle
per-group residual accounting
canonical transform orientation
watchdog/checker fields
```

要求保留失败 root、一个直接 regression、新 SHA 重跑受影响阶段。

---

# 13. Heavy-run 与重跑纪律

本 Review 预授权：

```text
one MPI8 scale-normalized identity formal
one same-setup conditional V6-3 continuation
one corrected formal rerun only if the first run identifies a concrete implementation bug
one moving-PML fallback sequence if required
one adaptive Schwarz pilot if required
```

以下不算新算法 attempt：

```text
同一formal内D0/D1比较
同一formal内scale triplet
条件one-step refinement
```

禁止：

```text
无证据重复相同formal
多次refinement扫描
MUMPS参数扫描
重开full-side factor rescue
继续旧Route C
```

---

# 14. Evidence 与 response_v8

至少新增或更新：

```text
outcomes/v7_scale_normalized_identity.md
outcomes/v7_group_solve_scatter_diagnosis.md
outcomes/v7_separator_closure_audit.md            # only if executed
outcomes/full_spectrum_floquet_sweep.md            # if reached
outcomes/moving_pml_sweep.md                       # if reached
outcomes/adaptive_spectral_schwarz.md              # if reached
outcomes/route_signal_ledger.md
outcomes/memory_residual_time_pareto.md
outcomes/test_summary.md
outcomes/summary.md
response_v8.md
```

`v7_scale_normalized_identity.md` 必须表格列出每个 vector、scale、variant、group 的：

```text
absolute error
relative error
source/output norms
Gate
classification
```

checker必须从 raw norms 重算 relative metrics，不能只读取 runner 给出的 `gate_pass`。

---

# 15. Commit 计划

建议提交顺序：

```text
feat(task040): add scale-normalized Schur identity metrics
feat(task040): add fixed-order full-interface contribution action
bench(task040): add group-solve and separator diagnostics
fix(task040): apply one evidence-driven identity repair          # conditional
feat(task040): continue full-spectrum or independent fallback    # conditional
bench(task040): qualify selected mainline route
 docs(task040): close review v7 and response v8
```

没有发生的 conditional commit应省略。不得把全部数值核心、heavy evidence和文档混成一个提交。

---

# 16. Merge 与最终裁决

```text
merge approval = NO
```

本 Review 只授权 Task040 当前执行分支持续研究。V6-2 当前绝对 Gate negative继续有效，不能
作为 production result合入。

最终裁决：

```text
Task040 closed                                      = no
V6-2 absolute-threshold record preserved           = yes
full-interface algebra definitively failed          = not yet established
scale-normalized adjudication                       = required once
fixed-order accumulation repair                     = authorized in same setup
one group-solve refinement                          = conditional, once
separator closure repair                            = conditional, once
identity pass -> full-spectrum continuation         = automatic
full-interface true fail -> independent fallback    = automatic
0.7 nm target PDE in Task040                        = no
0.7 nm architecture relevance                       = mandatory
master merge                                       = not approved
```
