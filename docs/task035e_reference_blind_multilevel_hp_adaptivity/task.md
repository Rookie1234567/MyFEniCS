# Task035e：无参考解、面向反演输出的多层局部 h/p 自适应

## 0. 执行身份与启动条件

```text
task = Task035e
execution_branch = codex/20260728-task35e-reference-blind-multilevel-hp-adaptivity
branch_creation = after Task035d M0-M4 selective merge
branch_base = exact clean post-Task035d master SHA
ordinary_default = unchanged
geometry = Task034 fixed rectangular block grating
wavelength = 13.5 nm
polarization = S
incidence = 10 degree grazing
periodic = x/y double Floquet
external_boundary = sparse auxiliary DtN
primary_solver = assembly-time static condensation + direct MUMPS
formal_MPI = 8 after serial/MPI2 qualification
heavy_PDE_concurrency = one at a time
iterative_solver = out of scope
matrix_free = out of scope
irregular_geometry = out of scope
```

Task035e 只有在：

```text
docs/task035d_goal_oriented_exact_sequence_hp_adaptivity/review_report_v1.md
```

规定的 M0–M4 全部完成、Task035d 已选择性合并 master、工作树干净后才能启动。

本任务在 13.5 nm 上模拟未来 0.7 nm 的核心困难：

> 完整收敛参考解不可获得，自适应程序不能读取一个已知高精度答案来选择网格或阶次，只能依赖自身的残差、伴随、局部 h/p 富集和误差预算。

13.5 nm 的 p6 高阶序列只用于独立验证这种“无参考解”流程是否可信，不得泄漏给自适应控制器。

---

# 1. 研究问题

Task035e 必须回答：

1. 在 adaptive controller 不读取 p6/h10、p6/h7.5、p6/h5 结果的条件下，能否从一个明显较粗的非均匀网格开始，自动生成包含多个 h level 与多个 p level 的 H(curl) 空间？
2. 能否仅根据 current solution、full residual、multi-goal adjoint、local p-shadow、local h-shadow 和误差预算判断何时停止？
3. 冻结候选后，hidden auditor 是否能确认全部正式低阶衍射输出、R/T/A 和场量达到误差要求？
4. 最终内存下降是否来自 active space、rows、matrix NNZ 和 factor NNZ 的真实结构压缩，而不是对象生命周期、不同 MPI 数或遥测口径变化？
5. Full3D blind hp 候选通过后，能否把同一空间接入 static Hybrid M120 并进一步降低内存？

---

# 2. 三层隔离：reference certifier、blind controller、hidden auditor

## 2.1 Reference certifier

独立执行高阶收敛研究：

```text
p6/h10
p6/h7.5
p6/h5
```

它可以读取全部高阶结果，但输出必须写入 sealed hidden-reference package。

## 2.2 Blind adaptive controller

控制器严禁读取：

- p6/h10、p6/h7.5、p6/h5 的 R/T/A；
- 任意逐衍射级 reference value；
- 任意 reference field；
- 任意 candidate-vs-reference cellwise error；
- 由 reference difference 生成的位置标签；
- Task035b/035d 已知成功或失败网格作为直接选择 oracle。

控制器只能读取：

- 当前候选解；
- 当前 full explicit residual；
- 当前 DtN/port 信息；
- 当前目标的 adjoint；
- 当前空间上的 local p-shadow；
- 当前空间上的 local h-shadow；
- 当前 mesh/degree/cost/resource inventory；
- 与当前候选相关的 algebraic、DtN 和后续 Hybrid 截断估计。

## 2.3 Final hidden auditor

只有在：

- 自适应停止条件通过；
- 最终 mesh 与 degree map 冻结；
- source SHA、plan SHA、output SHA 冻结；
- 不再允许根据结果修改候选；

之后，hidden auditor 才能读取 sealed reference package。

hidden audit 失败后，不得根据具体失败通道在同一正式 blind trial 中修网格后重新宣称成功。可以保留失败并在新任务或新算法版本中重新进行一次从头 blind trial。

## 2.4 防止 reference 泄漏

必须建立独立文件与接口：

```text
reference_certifier/
blind_controller/
hidden_auditor/
```

并提供自动测试，证明 blind controller 的输入 manifest 不包含 hidden reference path、hash、数值或派生标签。

---

# 3. Phase A：p6/h10、p6/h7.5、p6/h5 收敛认证

这一步是 evaluator campaign，不是 adaptive controller 的输入。

## A1. 固定身份

三条路径必须保持：

- 同一物理几何；
- 同一材料；
- 同一入射；
- 同一 S 偏振；
- 同一 DtN 物理定义；
- 同一 p6 Nédélec first-family；
- Full3D assembly-time static condensation；
- direct MUMPS；
- MPI8 正式口径；
- zero swap；
- 同一 official postprocessing。

## A2. 重型运行顺序

严格顺序：

```text
p6/h10 现有 authority 校验
→ p6/h7.5 preflight + full solve
→ p6/h5 preflight + full solve
```

一次只运行一个 heavy PDE。

p6/h5 必须尝试，但设置 fail-closed resource Gate：

- 先构造 mesh/DoF/rows/NNZ 预测；
- 再完成 assembly-only memory authority；
- 再决定是否进入 MUMPS factorization；
- 同时保留至少 20% 可用物理内存余量；
- swap 必须为 0；
- 不允许以 OOM kill 作为结果；
- 若当前工作站无法安全运行，记录为 `controlled_resource_stop`，Task035e 不得获得完整 hidden-reference success。

允许用较少 MPI rank 减少进程复制，但正式三点必须采用同一资格化 MPI 口径；不同 rank 的结果只能作为资源诊断。

## A3. 比较的完整输出

不得只比较 R/T/A。至少保存和比较：

```text
R00_s / R00_p / R00_total
R_total
T_total
A_closure
A_volume
full explicit true residual
energy closure
all propagating DtN orders on both ports
co- and cross-polarized order powers
physical-boundary complex amplitudes
selected interface and volume field probes
```

完整传播谱全部保存，不按功率阈值删通道。

## A4. 三层收敛分析

对每个输出 \(J\)：

\[
 d_{10,7.5}=|J_{h10}-J_{h7.5}|,
 \qquad
 d_{7.5,5}=|J_{h7.5}-J_{h5}|.
\]

需要记录：

- 是否单调；
- 是否发生符号振荡；
- fine difference 是否明显小于 coarse difference；
- 三点拟合 \(J(h)=J_*+Ch^q\) 是否稳定；
- 拟合阶次 \(q\) 是否为正且条件数可接受；
- h5 与外推中心的差；
- reference uncertainty。

默认 reference center 为 h5 实测值。只有三点拟合稳定时，才额外记录 extrapolated center；不得用不稳定外推替代 h5。

对每个输出定义：

\[
 u_{ref,J}=\max\left(d_{7.5,5},\ |J_{h5}-J_*|ight)
\]

若外推不稳定，则：

\[
 u_{ref,J}=\max(d_{10,7.5},d_{7.5,5}).
\]

## A5. Reference qualification

只有同时满足以下条件，hidden reference package 才能标记 `qualified`：

- p6/h7.5 与 p6/h5 均完成并通过 residual/energy Gate；
- 正式低阶输出没有无法解释的非收敛振荡；
- reference uncertainty 可量化；
- selected fields 趋于稳定；
- p6/h5 不是资源停止或部分解。

若 h5 不能运行，Task035e 仍可完成 blind infrastructure，但最终分类最多为：

```text
REFERENCE_CERTIFICATION_INCOMPLETE
```

---

# 4. Phase B：冻结反演输出与误差合同

## B1. 不再使用“显著通道”

Task035e 不使用功率阈值选择通道。

当前固定结构沿 y 不变化，正式低阶集合按物理衍射编号冻结为：

```text
N = 8
n = 0
m = 0, -1, -2, -3, -4, -5, -6, -7
```

对 top 与 bottom 两个端口分别保存：

- 每级总功率；
- co-polarized complex amplitude；
- cross-polarized power/amplitude 诊断；
- 是否传播；
- kz / admittance / normalization identity。

如果某一级在某端口为 evanescent，则不把它当作远场功率，但仍保存其身份与近场系数诊断。

## B2. 为什么选择 N=8

当前13.5 nm、固定周期、10°掠入射下，`m=0..-7,n=0` 覆盖当前主要运动学低阶窗口，并包含过去因接近零而未进入“显著通道”的 `m=-3,-6`。

因此该集合：

- 不依赖候选功率；
- 不会因为某级很弱就把它从精度合同中删除；
- 更接近未来反演中固定 detector/order inventory 的做法。

未来换波长时 N 必须按新的传播级和实验观测重新冻结，不得永久沿用8。

## B3. 最终 hidden audit 容差

对每个 reference power \(P_{ref}\)：

\[
 	au_P=\max\left(10^{-9},\ 5	imes10^{-4}|P_{ref}|,\ 2u_{ref,P}ight).
\]

对每个 reference complex amplitude \(a_{ref}\)：

\[
 	au_a=\max\left(10^{-6},\ 10^{-3}|a_{ref}|,\ 2u_{ref,a}ight).
\]

对 `R00_total/Rtotal/Ttotal/Aclosure/Avolume`：

\[
 	au_J=\max\left(10^{-6},\ 2	imes10^{-4}|J_{ref}|,\ 2u_{ref,J}ight).
\]

其他硬 Gate：

```text
full explicit true residual <= 1e-9
|R+T+Avolume-1| <= 1e-9
Aclosure-Avolume <= 1e-9
interface field rel-L2 <= max(1%, 2*reference uncertainty)
volume field rel-L2 <= max(1.5%, 2*reference uncertainty)
```

这些是本任务的工程误差上限。若高阶 reference uncertainty 本身大于目标值，最终容差自动由 `2u_ref` 控制，不得假装 reference 更准确。

## B4. Blind controller 使用的容差

blind controller 看不到 \(P_{ref},a_{ref},u_{ref}\)。它使用当前候选与 shadow enrichment 的尺度：

\[
 \widehat	au_P=\max(10^{-9},5	imes10^{-4}\max(|P_h|,|P_{shadow}|)),
\]

\[
 \widehat	au_a=\max(10^{-6},10^{-3}\max(|a_h|,|a_{shadow}|)).
\]

最终 hidden tolerance 只由 auditor 使用。

---

# 5. Phase C：真正多层、非均匀 local-h 空间

Task035d 已经证明 single-root local-h 能运行，但还没有形成真正多层自适应网格。Task035e 必须突破这一点。

## C1. 两条独立起始路径

至少建立：

### Path A：coarse-root 20 nm family

```text
nominal local h levels = 20 / 10 / 5 nm
```

通过两级 dyadic refinement 得到粗、中、细单元。

### Path B：coarse-root 15 nm family

```text
nominal local h levels = 15 / 7.5 / 3.75 nm
```

作为独立初始网格和最终自洽性检查。

如果 h20 boundary-fitted root 产生非法材料切分、极端 aspect ratio 或 exact-sequence blocker，可受控切换为另一套能产生 `coarse/medium/fine` 三层尺寸的 root family，但必须说明原因，不得退化成全域统一 h10。

## C2. 真正非均匀要求

正式自适应至少必须实际运行：

- 两个 local refinement levels；
- 多个空间上分离的 refinement patches；
- 2:1 balance；
- periodic closure；
- material-interface protection；
- hanging trace；
- MPI ownership。

每一 cycle 必须输出：

- 叶单元尺寸直方图；
- level 0/1/2 数量；
- material-wise cell-size distribution；
- marked roots 与 closure-added roots；
- mesh map/VTK；
- edge/face/cell degree map。

不能再用“整个 z 方向统一加一层”冒充 local-h。

## C3. p 范围

第一版生产空间使用：

```text
p in {4,5,6}
```

允许：

- edge degree；
- face degree；
- cell-interior degree；

分别变化并保持 exact sequence。

p3 只在 p4/p5/p6 blind controller 已稳定、且低敏感区域有两轮连续安全证据后开放。

p7 只可作为 local shadow enrichment 或 reference spot-check，不作为第一版全局生产阶次。

## C4. 初始空间

不得从已知 p6/h10 reference mesh 直接删除少量模式。

建议初始 blind space：

- coarse root mesh；
- material interface 与 port guard 至少 p5 trace；
- 大部分光滑 cell interior 从 p4/p5 开始；
- p6 仅通过 blind p-shadow 自动引入；
- refinement 由 residual/DWR/shadow 决定。

所有初始规则必须由几何、波数和稳定性定义，不得使用 hidden reference error map。

---

# 6. Phase D：无参考解的误差估计与 h/p shadow

## D1. 正式目标集合

对 top/bottom 的 N=8 低阶集合，共16个物理端口级，最低包含：

```text
16 powers
16 amplitude real parts
16 amplitude imaginary parts
R00_total
Rtotal
Ttotal
Aclosure
Avolume
selected interface/volume probes
```

即至少48个 order real-goals，加总量与场目标。

允许通过 unit-channel complex adjoint、SVD/QR 或 block solve 减少重复伴随，但最终必须对全部目标直接重算。

## D2. Local p-shadow

对候选 edge/face/cell orbit 构造一个不改变当前生产解的局部富集动作：

```text
p -> p+1
```

计算：

- enriched local tensor/Schur action；
- signed residual difference；
- 每个目标的 DWR delta；
- added active DoF；
- added rows；
- predicted matrix/factor cost。

p-shadow 不得要求先求完整全局 p6 reference。

## D3. Local h-shadow

对候选 root/patch 构造一层真实 dyadic split：

```text
h -> h/2
```

并计算：

- hanging/Floquet closure 后的实际 action；
- local refined tensor/Schur action；
- signed DWR delta；
- actual added roots/leaves；
- actual added rows；
- factor cost proxy。

Task035d 的 compact face oracle 不能替代 actual local-h shadow。

## D4. 估计器一致性

对每轮实际执行的首个 p-action 与 h-action，必须做 one-step shadow verification：

```text
DWR predicted goal delta
vs
actual candidate goal delta
```

记录：

\[
 I_{eff,J}=rac{\eta_J}{\Delta J_{actual}}.
\]

正式要求：

- 高优先级目标不得出现系统性符号相反；
- 至少90%的正式目标满足 `0.5 <= |I_eff| <= 2.0`；
- 超出范围的目标必须触发保守标记或 estimator repair；
- 不能用绝对值贡献和替代 signed closure。

## D5. h/p 决策

每个动作比较：

```text
predicted normalized goal reduction / added rows
predicted normalized goal reduction / added matrix NNZ
predicted normalized goal reduction / predicted factor NNZ
predicted normalized goal reduction / predicted solver-phase peak
```

决策规则：

```text
p-shadow strong, h-shadow weak
    -> p-up / keep high p

h-shadow strong, p-shadow weak
    -> local h-refine

both strong
    -> compare structural memory cost; allow combined action

both weak and two consecutive cycles low impact
    -> p-down or local coarsening candidate

estimator disagreement / sign conflict
    -> keep current space, fail closed
```

不得再次使用“远离结构，所以降 p”的几何启发式作为正式依据。

---

# 7. Phase E：自动 blind h/p 循环

实现真正的自动流程：

```text
solve current blind space
→ full residual and all goals
→ build p-shadow/h-shadow catalog
→ compute signed multi-goal DWR
→ cost-aware marking
→ periodic/material/2:1 closure
→ build true active space
→ static-condensed solve
→ verify selected shadow actions
→ update estimator and memory model
→ accept/reject cycle
```

## E1. Cycle 数量

最多先运行6个正式 cycle。

每个 cycle 必须保存：

- clean source SHA；
- input/output manifest；
- mesh forest hash；
- degree map hash；
- active FE DoF；
- rows/NNZ/factor；
- mesh size histogram；
- all N-order outputs；
- residual/energy；
- DWR estimate；
- actual shadow verification；
- RSS/PSS/USS/swap；
- phase-exclusive timing；
- accepted/rejected action 与原因。

## E2. Marking

允许使用 multi-goal Dörfler marking，但权重必须来自固定误差合同，不得来自 hidden reference。

目标归一化采用 blind tolerances \(\widehat	au\)。

## E3. Coarsening

初始两轮只允许 refine 或 p-up/keep。

只有某个 entity/patch 在连续两轮中：

- normalized DWR 很小；
- p-shadow/h-shadow 均很小；
- 不参与高优先级目标；

才允许 p-down 或 coarsening。

任何 coarsening 都必须在下一轮实际 PDE 中直接复核。

---

# 8. Phase F：无参考停止条件

blind controller 只有同时满足以下条件才能冻结候选。

## F1. p-shadow 与 h-shadow

对全部正式低阶输出：

```text
max normalized p-shadow delta <= 0.5
max normalized h-shadow delta <= 0.5
```

这里 normalized 使用 blind tolerance。

## F2. 连续两轮稳定

连续两个 accepted cycle 的：

- N-order powers；
- complex amplitudes；
- R/T/A；
- selected fields；

均在 blind tolerance 内稳定。

## F3. 两条初始路径一致

Path A 与 Path B 最终冻结候选的正式输出必须在 blind tolerance 内一致。

它们的最终网格可以不同，但输出不能只在某一个起始网格上稳定。

## F4. DtN 与 algebraic budget

至少比较：

- current DtN order inventory；
- increased DtN inventory；
- direct residual；
- tighter numerical postprocess/integration。

要求：

```text
algebraic contribution <= 10% of blind output budget
DtN truncation contribution <= 10% of blind output budget
postprocess contribution <= 10% of blind output budget
```

## F5. 物理恒等式

```text
full explicit residual <= 1e-9
energy closure <= 1e-9
Avolume >= 0
Floquet residual pass
hanging constraint residual pass
serial/MPI identity pass
```

完成F1–F5后，冻结：

- source；
- mesh；
- p-map；
- output；
- internal error certificate；
- resource authority。

然后才允许 hidden audit。

---

# 9. Phase G：隐藏 reference 最终审计

hidden auditor 读取 Phase A sealed package，按第4章容差检查：

- N=8 top/bottom order powers；
- N=8 complex amplitudes；
- full propagating spectrum；
- R00/R/T/A；
- Avolume/energy；
- fields；
- residual。

## G1. 通过

只有全部正式输出通过，才可声明：

```text
REFERENCE_BLIND_HP_ACCURACY_PASS
```

## G2. 失败

若 hidden audit 失败：

- 保存所有失败输出和值；
- 不允许根据具体失败通道修改同一正式候选；
- 分类为 `BLIND_STOP_FALSE_POSITIVE` 或 `BLIND_ESTIMATOR_INCOMPLETE`；
- 分析 estimator、shadow、initial-path consistency 哪一步没有提前暴露误差；
- 不得放宽容差后改写为成功。

---

# 10. Phase H：接入 static Hybrid M120

只有 Full3D blind candidate 通过 Phase G 后才执行。

## H1. 同一 hp 空间

- 上下 local 3D FEM 使用冻结的 hp mesh/degree map；
- 中间 modal region 使用匹配的横截面离散；
- z 向保持 Task035c 已资格化的 uniform scalar-CG chain；
- local-h 不得破坏当前离散传播模型的适用条件；
- M 首先使用120。

## H2. Hybrid 内部自洽

不需要读取 p6 hidden reference来选择 M。比较：

```text
M120
M160 only if internal M signal requires
```

并检查：

- hp Full3D ↔ hp Hybrid；
- interface E/H；
- all N-order outputs；
- residual；
- middle-plane fields。

## H3. Hybrid Gate

```text
hp Full3D ↔ hp Hybrid:
    all N-order powers pass
    all N-order amplitudes pass
    R/T/A pass
    interface/field pass
```

Hybrid 不能给 Full3D hidden-audit失败的空间补精度信用。

---

# 11. 资源目标：以结构压缩为准

## 11.1 正式基线

```text
p6/h10 Full3D static MPI8 peak = 14.721756 GiB
p6/h10 Hybrid static M120 MPI8 peak = 7.544262 GiB
```

约11.08 GiB是 Hybrid standard M120，不是 Full3D static。

## 11.2 Full3D hp 目标

取消 `<=90,000 DoF` 硬上限。DoF 仍需报告并尽量降低，但成功以误差和实测内存为主。

正式要求：

```text
rows < 51,272
matrix NNZ < 41,989,040
factor NNZ < 212,343,992
solver-phase peak < 14.721756 GiB
mandatory target <= 11.0 GiB
preferred target <= 9.0 GiB
zero swap
```

如果候选精度通过但峰值介于11.0和14.72 GiB之间，分类为 accuracy success / resource incomplete。

## 11.3 Hybrid hp 目标

```text
peak < 7.544262 GiB mandatory
preferred peak <= 6.4 GiB
rows/NNZ/factor all below p6/h10 Hybrid static M120
zero swap
```

## 11.4 结构内存信用

本任务只把以下变化计为 hp 的结构内存收益：

- active DoF；
- independent rows；
- matrix NNZ；
- factor NNZ/fill；
- same-policy solver-phase process-tree RSS/PSS/USS。

以下变化必须单列，不能计入 hp structural gain：

- 提前 `del` / `malloc_trim`；
- 改变输出内容；
- 改变 MPI rank；
- 改变 watchdog 采样；
- 不同生命周期重叠；
- 不同MUMPS/PETSc配置；
- 不同postprocess。

比较必须使用同一 MPI8、同一求解器、同一对象生命周期政策和同一遥测。

---

# 12. Phase-exclusive 时间与内存遥测

Task35e 必须建立互斥 timeline：

```text
mesh/forest/degree-plan
local tensor tabulation
local condensation
hanging/Floquet reduction
PETSc preallocation/insertion
DtN assembly
MUMPS symbolic
MUMPS numeric
backsolve
field recovery
order postprocess
field probes
record serialization
```

不得再出现含义不清的嵌套计时被当作可相加的阶段。

同时记录：

- process-tree RSS；
- simultaneous rank RSS/PSS/USS；
- swap；
- cgroup diagnostic；
- PETSc matrix/factor inventory；
- mesh/constraint/cache retained bytes。

---

# 13. 成功与失败分类

## SUCCESS_REFERENCE_BLIND_HP

必须同时满足：

- p6 h10/h7.5/h5 reference certification pass；
- blind controller 未读取 hidden reference；
- true multilevel local-h；
- true variable-p；
- automatic cycles 完成；
- two-start consistency pass；
- internal blind stop pass；
- hidden audit全部 N-order、R/T/A、fields通过；
- Full3D peak <=11.0 GiB；
- rows/NNZ/factor下降。

## SUCCESS_REFERENCE_BLIND_HP_AND_HYBRID

在上一分类基础上：

- hp Full3D ↔ hp Hybrid pass；
- Hybrid peak <7.544262 GiB；
- preferred <=6.4 GiB。

## BLIND_ACCURACY_SUCCESS_RESOURCE_INCOMPLETE

hidden audit通过，但Full3D结构内存目标未达到。

## MULTILEVEL_H_SUCCESS_P_INCOMPLETE

真正多层local-h和blind stop有正信号，但variable-p/combined hp未闭合。

## BLIND_STOP_FALSE_POSITIVE

blind controller宣布停止，但hidden audit失败。

## REFERENCE_CERTIFICATION_INCOMPLETE

p6/h5因资源或数值原因无法形成合格hidden authority。

## PARTIAL_WITH_CONTROLLED_NEGATIVES

组件、误差归因和负结果清楚，但完整blind hp Gate未通过。

---

# 14. 停止规则

- 一次只运行一个 heavy PDE；
- 同一 candidate lane 连续两个 actual shadow verification 负信号后关闭；
- 连续两个 cycle 的 normalized goal error 不下降时停止该路线；
- exact-sequence、hanging、Floquet、MPI ownership失败立即停止；
- p6/h5超过安全内存Gate时 controlled stop，不得OOM；
- hidden audit后不得针对失败通道调参并继续声称同一次blind成功；
- 不删除负结果；
- 不用 projection forecast 代替 actual PDE；
- 不用 total R/T/A稳定代替逐级与复振幅稳定；
- 不因某级功率很小而从N=8合同删除。

---

# 15. Benchmark、测试与交付

新建：

```text
benchmarks/cases/098_reference_blind_multilevel_hp_adaptivity/
```

至少包含：

- config/schema/expected/test command；
- sealed p6 convergence authority；
- blind-input manifest；
- reference-leak checker；
- multilevel mesh authority；
- p-shadow/h-shadow authority；
- per-cycle records；
- two-start comparison；
- hidden audit；
- resource ledger；
- controlled negatives；
- Hybrid结果（若授权）。

测试至少包括：

- p6 convergence record checker；
- hidden-reference access isolation；
- p4/p5/p6 exact sequence；
- two-level local-h；
- hanging/Floquet/MPI1/2/8；
- p-shadow/h-shadow signed closure；
- estimator effectivity；
- N=8 order inventory；
- all-order postprocess；
- automatic cycle state machine；
- structural memory comparison；
- Task035/035b/035c/035d regression；
- Case095/096/097/098 checker；
- full repository pytest；
- Ruff、compileall、JSON、registry和diff-check。

最终交付：

```text
docs/task035e_reference_blind_multilevel_hp_adaptivity/outcomes/summary.md
docs/task035e_reference_blind_multilevel_hp_adaptivity/outcomes/test_summary.md
docs/task035e_reference_blind_multilevel_hp_adaptivity/response_v1.md
benchmarks/cases/098_reference_blind_multilevel_hp_adaptivity/
docs/development_model_registry.md updated
```

每个新术语必须先用通俗语言解释。每个失败必须列具体输出、实际误差、容差、资源和停止理由。

Task035e 不得自行 merge master；完成后提交并推送执行分支，等待集中 Review。
