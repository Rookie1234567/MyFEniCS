# 项目开发进度：Task000–Task029

## 1. 文档定位

本文档记录项目从初始代码审查到 Task029 当前阶段的完整开发进程，面向：

```text
- 项目开发者；
- 后续 Codex/ChatGPT 任务；
- 新加入的维护者；
- 需要判断当前能力、历史路线和下一步优先级的用户。
```

本文档不是逐次实验的原始日志。详细证据仍位于：

```text
docs/taskXXX_*/task.md
docs/taskXXX_*/outcomes/
docs/taskXXX_*/review_report*.md
```

本文档负责回答：

```text
1. 每个阶段为什么开始；
2. 实现了什么；
3. 哪些结果成功；
4. 哪些路线失败或被替代；
5. 当前主线最终保留了什么；
6. 项目现在能做什么；
7. 尚未完成什么。
```

更新时间：

```text
2026-07-13
current branch = codex/20260713-task29-stage4-direct-memory-forensics
Task028 status = V4 closed and merged to master at 2f9e56d
Task029 status = diagnostic_success; h5/h3 complete; best h3 reduction 15.119%; h2 not run by gate; waiting review
```

## 1.1 2026-07-13 最新更新

Task028 已按普通 merge commit 合入 `master`，并完成 master release check。Task029 从该合并点新建独立分支，完成 direct-memory telemetry、外部 0.25 s sampler、matrix/factor inventory、Case050、h5/h3 baseline、H1–H7、profile 筛选和 h2 安全决策。遥测明确区分 simultaneous worker RSS、各 rank 历史峰值和、MPI 进程树与 cgroup；Task28 canonical records 保持只读。

MPI4 h5/h3 baseline simultaneous RSS 为 2328.145 / 8651.098 MB，主峰都位于 KSPSetUp。release-base 公共生命周期候选在 h3 只下降 5.462%；最佳 default MUMPS MPI2 在 h5/h3 分别下降 28.893% / 15.119%，全部 residual/R/T/A Gate 通过且无 swap，但 h3 低于 20% 工程门槛。因此 Task029 分类为 `diagnostic_success`，不产生合格低内存 direct profile。h2 两类外推中央值为 22.214 / 22.330 GiB、区间 18.882–27.913 GiB，G3/G5/G7/G9 失败，未启动 h2。

---

# 2. 项目总体目标

项目目标是建立可验证、可扩展的二维和三维频域 Maxwell 有限元求解框架，重点面向周期微纳结构和 EUV 光栅散射。

长期物理能力目标：

```text
- 2D/3D Maxwell frequency-domain solve；
- real/complex refractive index；
- Floquet periodic boundary conditions；
- PML、Fresnel interface 和 periodic modal port；
- Nedelec H(curl) elements；
- diffraction orders；
- official R/T/A；
- material volume absorption；
- field output；
- mesh/order/angle/wavelength scans；
- direct and iterative solvers；
- low-memory workstation and future HPC execution；
- eventual geometry/material inversion support。
```

当前长期参考模型：

```text
domain = 50 x 25 x 140 nm
period = 50 x 25 nm
grating = 17 x 25 x 120 nm
substrate thickness = 10 nm
top air above grating = 10 nm
wavelength = 13.5 nm
theta_from_z = 80 deg
phi = 0 deg
polarization = s
material = complex Si index
space = 3D N1curl p=2
side boundaries = double Floquet
z boundaries = periodic modal DtN ports
```

---

# 3. 阶段总览

| 阶段 | Task | 主要目标 | 最终状态 |
|---|---|---|---|
| A. 初始整理与物理口径 | 000–004 | 整理代码、R/T/A、体吸收、能量闭合、MPI/p 回归 | 基础工程链稳定 |
| B. 目标几何与直接法边界 | 005–010 | 真实 3D 资源、official DtN、目标几何 direct、BLR | h=2 direct reference 建立 |
| C. AMS/HX 与低维模态路线 | 011–019 | 低内存 Krylov、real split、AMS/HX、sampled Schur | p1 有信号，p2 主线失败并关闭 |
| D. wave-aware 与 FE-response/Schur | 020–025 | residual-aware modes、FE response、PETSc/MPI Schur、cached-Q | 数学结构成立，h=2 response 质量不足 |
| E. auxiliary-free 与 workstation solver | 026–027 | exact condensation、matrix-free、physical slab two-level PC | h=5/3/2 MPI4 达 production residual |
| F. 阶段收口与可复现版本 | 028 | clean master 整合、文档、benchmark、阶段版本 | V4 完成并合入 master |
| G. direct memory forensics | 029 | simultaneous RSS、factor inventory、生命周期/profile 筛选、h2 Gate | diagnostic_success，等待审查 |

---

# PART I：阶段 A——初始代码整理与物理口径

## 4. Task000：初始代码审查与工作流整理

### 目标

```text
- 阅读项目结构；
- 识别 2D/3D 代码边界；
- 建立 task -> outcomes -> review 的开发流程；
- 记录代码问题和后续优先级。
```

### 主要成果

```text
- 建立任务目录规范；
- 建立代码审查和结果追踪习惯；
- 明确理论笔记、运行结果和任务记录的目录职责；
- 为后续 Stage4 验证提供审计基线。
```

### 当前状态

```text
success_type = documentation/workflow success
code_status = 被后续稳定实现替代
retained_value = 可追溯开发流程
```

---

## 5. Task001：Stage4 validation cleanup

### 目标

清理早期 Stage4 路径中的配置、输出和验证逻辑，减少不同案例之间的隐式差异。

### 主要成果

```text
- 整理 Stage4 case flow；
- 清理输出与验证标签；
- 建立较一致的运行 summary；
- 为后续功率口径修正做准备。
```

### 局限

```text
- 当时的 R/T/A 仍不是最终 official 口径；
- 真实目标几何和 p=2 资源边界尚未建立。
```

### 当前状态

后续 Task003、Task007 和 Task008 已吸收该任务的有效成果。

---

## 6. Task002：R/T/A 输出与 volume absorption

### 目标

```text
- 输出反射率、透射率和吸收率；
- 增加有损材料的体积分吸收；
- 比较不同功率计算方式；
- 检查能量守恒。
```

### 主要实现

```math
P_{abs}
\propto
\int_{\Omega_{loss}}
\operatorname{Im}(\varepsilon_r)|E|^2\,dV.
```

新增或整理：

```text
- port power；
- probe Fourier power；
- sampled net flux；
- A_volume；
- energy closure fields。
```

### 关键发现

初始不同功率口径不一致，不能直接将 probe 或 sampled flux 作为 official R/T。

### 当前状态

```text
infrastructure_success = yes
diagnostic_success = yes
initial_physical_result = superseded by Task003/007
```

---

## 7. Task003：Stage4 power consistency

### 目标

建立统一、可信的功率和能量闭合口径。

### 主要成果

```text
- flat-layer analytic sanity；
- port + A_volume 能量闭合；
- probe 和 sampled flux 降级为 diagnostic；
- 统一能量 closure 字段；
- 修正后续主线的功率验收规则。
```

### 长期保留结论

```text
official power = modal port power
volume absorption = material loss integral
probe-plane Fourier = diagnostic only
sampled net flux = diagnostic only
```

该结论持续沿用到 Task028。

---

## 8. Task004：small-cell p convergence、MPI consistency 与全阶段回归

### 目标

```text
- 小尺寸 flat-layer benchmark；
- p=1/p=2 比较；
- MPI1/4/8 一致性；
- Stage1、2A、2B、2C、4 smoke；
- 防止前几轮修改破坏已有路径。
```

### 主要成果

```text
- p=2 明显优于 p=1；
- official port + A_volume 在小模型上稳定；
- MPI rank 数不改变主线结果；
- Stage1/2A/2B/2C/4 的基本路径可以运行；
- 建立长期 regression baseline。
```

### 边界

```text
- Stage2B PML 和 Stage2C Fresnel 当时只做 smoke，不代表高精度验证；
- small-cell 不是目标 3D EUV 光栅物理 benchmark。
```

### 当前状态

```text
production/infrastructure baseline = retained in master
```

---

# PART II：阶段 B——目标几何、资源边界与直接法

## 9. Task005：真实 3D 光栅内存和直接法资源估算

### 目标

评估真实 3D 光栅中：

```text
- mesh size；
- DoF；
- matrix nnz；
- assembled matrix storage；
- direct LU fill-in；
- MUMPS OOC；
- workstation resource boundary。
```

### 关键发现

```text
- assembled matrix 并非唯一瓶颈；
- MUMPS LU fill-in 和 factor workspace 才是主要峰值；
- 粗网格可以完成，细网格 direct 很快进入内存边界；
- 继续仅依赖 direct 无法支持更细 p=2 3D 模型。
```

### 当前状态

保留为容量规划和失败边界证据，不作为当前推荐 solver。

---

## 10. Task006：缩短计算域与 OOC 资源分析

### 目标

尝试用较短 z 域降低矩阵规模，评估：

```text
- 70 nm reduced-height domain；
- direct/OOC 可达网格；
- 结果对 domain height 的敏感性；
- 资源外推。
```

### 成果

```text
- 明确 reduced-height 能显著减小矩阵；
- 修正真实光栅 top probe 位置；
- 记录 OOC scratch 和失败边界；
- 区分 matrix RSS 上界与进程树真实峰值。
```

### 负结果

```text
- 70 nm 域的 R/T/A 与更高域明显不同；
- 不能把 reduced domain 当作物理等价 benchmark；
- OOC 不能自动解决细网格 direct。
```

### 当前状态

```text
resource diagnostic retained
physical benchmark superseded by Task008
```

---

## 11. Task007：恢复 DtN modal amplitudes 作为 official R/T/A

### 目标

明确 Stage4 periodic modal port 的官方功率来源。

### 最终口径

```text
R_total = outgoing top DtN modal power / incident power
T_total = outgoing bottom DtN modal power / incident power
A_volume = material volume loss / incident power
closure = R + T + A_volume - 1
```

### 关键成果

```text
- auxiliary DtN modal amplitudes 成为 official power source；
- probe Fourier 和 sampled flux 降为 diagnostic；
- 有损基底的 T 与 port reference plane 相关这一边界被记录；
- 后续所有 Task 使用统一口径。
```

### 当前状态

```text
stable production power definition
```

---

## 12. Task008：目标几何 p=2 direct benchmark

### 目标模型

```text
50 x 25 x 140 nm unit cell
17 x 25 x 120 nm grating
13.5 nm
80 deg from z
s polarization
complex Si
p=2 Nedelec
double Floquet + 80 DtN auxiliary modes
```

### 主要成果

建立目标模型 direct reference：

```text
p=2 h=2 nm
R = 0.0013429328462348958
T = 0.5992132294442478
A_volume = 0.3994438377095067
R+T+A = 0.9999999999999893
```

同时记录：

```text
- p=1 和 p=2 direct 可达边界；
- p=2 h=1.5 direct setup 被内存杀死；
- p=2 h=1 assembled matrix/交换空间压力很高；
- h=2 是 workstation best-effort direct reference，不是最终无限细网格极限。
```

### 当前状态

```text
current direct reference = retained
ordinary direct default = retained
```

---

## 13. Task009：黑盒 PETSc 迭代 profile 筛选

### 目标

快速测试：

```text
GMRES / FGMRES / BiCGStab
Jacobi / BJacobi / ASM / ILU / local LU
GAMG / FieldSplit / BoomerAMG diagnostics
```

### 关键结果

```text
- 没有现成黑盒组合达到 production residual；
- GMRES + Jacobi 只能稳定降低残差，不能收敛；
- ASM/ILU/local LU 多数停滞或恶化；
- 未收敛配置禁止输出 official R/T/A。
```

### 关键纠偏

早期记录的：

```text
residual_final / residual_initial
```

不等于：

```text
||Ax-b|| / ||b||
```

从此建立 reported/KSP residual 与 explicit true residual 的严格区分。

### 当前状态

```text
negative-result baseline retained
black-box PC route closed
```

---

## 14. Task010：MUMPS-BLR 与 shifted Maxwell 原型

### 目标

```text
- 测试 MUMPS-BLR compressed factorization；
- 打通 A/P 双矩阵接口；
- 测试 minimal shifted/positive Maxwell P；
- 为 AMS/HX 做工程预检。
```

### 正结果

h=2：

```text
FGMRES + MUMPS-BLR eps=1e-5
iterations = 4
true residual ≈ 2.09e-8
R/T/A 与 direct 一致到约 1e-9
```

### 边界

```text
- BLR 仍属于近似直接因子，不是最终低内存迭代法；
- h=1.5 仍在 setup 阶段被内存杀死；
- minimal shifted/positive Maxwell + ASM/ILU 未收敛。
```

### 当前状态

```text
BLR = explicit fallback/reference
shifted A/P infrastructure = historical foundation
```

---

# PART III：阶段 C——AMS/HX、real split 与低维 sampled-Schur

## 15. Task011：低内存 Krylov、AMS/HX smoke 与 matrix-free feasibility

### 目标

```text
- low-restart Krylov + Jacobi；
- real FE-only hypre AMS/HX；
- complex AMS safety；
- matrix-free FE action。
```

### 结果

```text
Jacobi-Krylov:
- 低内存；
- 不收敛；
- 路线基本关闭。

real FE-only AMS:
- p1/p2 小模型有真实收敛信号；
- p=2 h=5 可到约 1e-6；
- 但内存和完整 Stage4 兼容性未知。

complex AMS:
- 当前 build 下崩溃，不安全。

matrix-free FE action:
- 与 assembled action 误差约 1e-15；
- 证明少存矩阵可行；
- 但不解决 inverse/PC 问题。
```

### 当前状态

```text
matrix-free foundation retained
AMS result = research signal only
```

---

## 16. Task012：Maxwell 预条件器文献调研与路线设计

### 覆盖方向

```text
- H(curl) auxiliary space / Hiptmair-Xu / hypre AMS；
- shifted Maxwell / complex shifted Laplacian；
- overlapping Schwarz / optimized Schwarz；
- sweeping / moving PML；
- DtN-aware block preconditioner；
- Rayleigh/Floquet modal deflation；
- matrix-free high-order Maxwell；
- BLR/H-matrix fallback；
- layered/RCWA-like approximate inverse。
```

### 结果

停止盲目添加 PETSc profile，转为有 Gate 的物理预条件器研究。

### 当前状态

理论和路线文档长期保留，但每条方法的生产状态以后续数值任务为准。

---

## 17. Task013：real-split AMS/HX qualification

### 目标

绕开 complex hypre AMS 崩溃，将复杂 Maxwell FE operator 写成实数块系统：

```math
\begin{bmatrix}
\operatorname{Re}A & -\operatorname{Im}A\\
\operatorname{Im}A & \operatorname{Re}A
\end{bmatrix}.
```

### 成果

```text
- complex-to-real matvec 等价误差约 1e-16；
- real hypre AMS 可安全运行；
- same-H1 auxiliary 显著降低内存；
- FE-only p=2 h=5 达到 true residual <=1e-6。
```

### 局限

```text
- 不含 Floquet MPC 后完整结构；
- 不含 DtN auxiliary unknowns；
- 不含目标 Stage4 R/T/A；
- isolated serial research runner。
```

### 当前状态

```text
B-grade research positive
production code not merged
```

---

## 18. Task014a：reduced Stage4 real-split FE/aux block PC

### 目标

把 Task013 FE-only 正信号接到约化 Stage4：

```text
FE block -> same-H1 AMS
aux block -> identity/exact small block
```

### 成果

```text
- Stage4 complex-to-real equivalence 通过；
- FE/aux block indexing 通过；
- MPC 后 AMS data 可构造；
- MPI ownership 和数据布局明确。
```

### 负结果

```text
FE-AMS + aux identity
1000 steps
true residual ≈ 2.15e-2
```

只比 Jacobi 改善约 1.6 倍，不能进入 p=2/full Stage4。

### 结论

FE-only AMS 正信号不能直接搬到包含 DtN coupling 的完整问题。

---

## 19. Task015：DtN/Floquet boundary-aware diagnostic

### 目标

定位 Task014a 的 residual 停滞来源。

### 关键发现

FE-AMS 之后，剩余 residual 几乎全部集中在：

```text
top port
Rayleigh order (0,0)
y/s polarization
```

进一步证明：

```text
- aux block identity/exact/diag 本身不是瓶颈；
- aux-only modal correction 无效；
- diag(A_FE)^-1 Schur 明显变差；
- 真正问题是 auxiliary mode 与 FE trace/volume 的 coupled slow direction。
```

### 当前状态

诊断成功，驱动 Task016–Task021；diagnostic runner 不进入生产。

---

## 20. Task016：dominant zero-order lifted coarse correction

### 目标

构造：

```text
Z = [-P_FE^-1 C_j ; e_j]
```

并尝试 Galerkin、minimum-residual、additive 和 residual-corrected coarse correction。

### 结果

最好改善约：

```text
1.000045x
```

几乎无效。

### 关键结论

```text
aux residual 集中在某个 mode
!=
solution error 可由相应 right lifted vector 修正
```

可能需要：

```text
- left/test space；
- 更准确 A_FE^-1 C_j；
- 非正规系统的不同投影形式。
```

### 当前状态

right-only lifted coarse 路线关闭。

---

## 21. Task017：Petrov/adjoint coarse 与 true-FE sampled lift

### 目标

```text
- 增加 left/test space W；
- 测试 adjoint-aware projection；
- 用更真实的 FE response 近似 A_FE^-1 C_j。
```

### 结果

Petrov/adjoint 路线仍无效；但 true-FE sampled response 出现第一个明显正信号：

```text
top+bottom zero-order y modes
one-shot residual ≈ 3.69e-3
improvement ≈ 5.82x
```

### 限制

```text
- 依赖 SciPy exported-matrix research path；
- FE response 并非 exact；
- 直接塞进 right PC 后反而变差；
- 尚未形成稳定 solver。
```

### 当前状态

Petrov 路线关闭；true-FE residual correction 进入 Task018。

---

## 22. Task018：adaptive residual-corrected true-FE sampled Schur

### 目标

将 Task017 的 one-shot correction 转为 solver-like process。

### 最佳流程

```text
bounded FE-AMS segment
-> compute true residual
-> solve small min ||r-AZ alpha||
-> update x
-> repeat
```

### p=1 h=5 结果

```text
baseline residual ≈ 2.146e-2
best residual ≈ 1.662e-3
improvement ≈ 12.91x
```

通过 strong research gate，但未达到 \(10^{-6}\)。

### 关键发现

最有效的 FE response 不是最精确的 solve，而是带过滤作用的较松近似。

### 局限

```text
- SciPy single-process response service；
- 不是 MPI production；
- p=2 迁移尚未验证。
```

### 当前状态

p=1 research strong positive；允许进入 Task019 p=2 qualification。

---

## 23. Task019：p=2 h=5 sampled-Schur qualification

### 目标

验证 Task018 是否迁移到 p=2。

### 结果

```text
baseline 120-step residual = 1.6386e-2
required top_bottom_y best = 1.6357e-2
improvement = 1.0018x
best creative low-dimensional variant = 1.0804x
```

### 结论

```text
- p1 filtered sampled response 不迁移 p2；
- 增加少量 mode 无效；
- 低维 sampled-Schur 主线停止；
- 不进入 h=2。
```

### 当前状态

失败代码保留研究分支；文档作为重要负结果长期保留。

---

# PART IV：阶段 D——wave-aware、FE response 与 full Schur

## 24. Task020：branch hygiene 与 wave-aware solver search

### 目标

```text
- 整理失败分支；
- 比较 impedance DDM、sweeping、two-level adaptive coarse、matrix-free；
- 寻找 p=2 下一条主线。
```

### 结果

在 default100 算法沙盒：

```text
Route A row-layer DDM proxy -> 无明显改善
Route B diagonal slab sweep -> 变差
Route C residual-aware adaptive coarse -> 唯一正信号
Route D matrix-free action -> 代数通过但不是 solver
```

p=1 Route C 可到 \(10^{-6}\)，p=2 仅约 0.0525。

### 边界

Task020 使用 default100 沙盒，不是最终目标物理模型。

### 当前状态

路线排序保留；Task021 切回真实目标几何。

---

## 25. Task021：目标几何 DtN auxiliary residual-aware FE response/Schur

### 目标

在真实 p=2 h=5 目标模型上验证：

```text
residual-dominant auxiliary selector
+ FE response
+ coupled Schur correction
```

### 关键结果

```text
Jacobi baseline ≈ 0.2026
SPILU coupled m=1 ≈ 9.87e-7
SPILU block Schur ≈ 2.43e-7
exact FE-block Schur upper bound ≈ 8.16e-12
```

### 物理发现

主导 auxiliary mode 稳定为：

```text
top (0,0) s-polarized mode
```

### 结论

真正有效的是：

```text
FE response quality + FE/aux Schur structure
```

而不是单独 auxiliary correction。

### 局限

```text
serial SciPy SPILU/SPLU research prototype
no MPI production
no h=2
no official iterative R/T/A reconstruction
```

---

## 26. Task022：p=2 h=2 Schur/FE-response preflight

### 目标

验证 h=2 是否能沿 Task021 路线推进。

### 成果

```text
rows = 615188
FE DoF = 615108
aux = 80
nnz ≈ 65.45M
assembly + CSR 可完成
peak preflight RSS ≈ 6.277 GB
main selected mode 与 h5 相同
matrix-free FE action 误差 ≈ 6e-16
```

### 阻塞

```text
serial SciPy SPILU high fill -> 估计约 27.8 GB
very low fill -> setup 超时或质量不足
```

### 结论

h=2 失败不是矩阵、mode selector 或 Schur 结构错误，而是无法低内存近似 \(A_{FE}^{-1}\)。

---

## 27. Task023：PETSc/MPI-safe FE-response PC

### 目标

将 Task021/022 迁移到 PETSc/MPI，并补齐 field/RTA 回填。

### h=5 成果

```text
selected response ASM + local LU residual ≈ 9.33e-7
full 80-aux Schur one apply ≈ 2.49e-10
FieldSplit FE-LU ≈ 3.80e-9
```

official R/T/A 与 direct 差约 \(10^{-12}\)。

### 工程成果

```text
- MPI FE/aux index ownership；
- PETSc subblocks；
- solution reconstruction；
- MPC back-substitution；
- official modal R/T/A；
- FieldSplit/Schur engineering framework。
```

### h=2 负结果

```text
plain ASM/ILU response 质量不足，甚至方向错误；
local LU/MUMPS 进入时间/资源边界。
```

### 当前状态

h=5 工程闭环成功；h=2 仍缺强 FE inverse。

---

## 28. Task024：工程迭代求解器 fast track 与复现基础设施

### 目标

```text
- manual right FGMRES；
- CSR export；
- real split；
- AMS/HX/GMG-lite experiments；
- clean reproduction；
- h=2/h=1.5 low-memory preflight。
```

### 基础设施成果

```text
- manual FGMRES 与 PETSc/SciPy 小矩阵一致；
- complex dot 共轭方向修复；
- MPI1/MPI4 residual history 一致；
- vectorized CSR exporter；
- CSR invariants/hash audit；
- clean container reproduction。
```

### 算法结果

```text
m=1 reduced FE-response
20+20 budget residual = 0.17899
100+100 budget residual = 0.15859
```

没有证明相对严格 baseline 的有意义收益，更不是完整 80-aux solver。

### 当前状态

```text
infrastructure success
algorithm fail
manual FGMRES research-only
CSR/audit concepts retained
```

---

## 29. Task025：full-aux cached Schur 与 multilevel H(curl) 尝试

### 目标

```text
- 完整 80 auxiliary unknown；
- Q ≈ A_FE^-1 C；
- explicit small Schur；
- shifted FE smoother；
- p/coarse/AMS/BDDC 等多层尝试；
- h=2 14 GB 内完整 augmented solve。
```

### h=2 成果

```text
80 response columns
Q nnz ≈ 49.2M
outer iterations = 100
full true residual = 0.118475
peak RSS ≈ 13.006 GB
```

这是完整 full-aux 架构的重要研究突破。

### 根本瓶颈

response columns 满足：

```text
min relative response residual ≈ 0.286
max relative response residual ≈ 0.541
```

小 Schur 已精确求解，主要误差来自 Q 质量。

### 多层路线结论

```text
- 当前 p2->p1 / H1 / BDDC / 2D coarse 原型未捕获主要慢误差；
- 真正 3D nonmatching h-GMG 未实现；
- 不能据此否定所有 AMS/HX 或 h-GMG；
- ILU2 内存收益比太差。
```

### 当前状态

cached-Q 架构被 Task026 exact condensation 替代；诊断和历史证据保留。

---

# PART V：阶段 E——auxiliary-free 与 MPI4 workstation solver

## 30. Task026：auxiliary-free exact static condensation

### 架构变化

从 augmented system：

```math
\begin{bmatrix}F&C\\D&H\end{bmatrix}
\begin{bmatrix}u\\a\end{bmatrix}
=
\begin{bmatrix}b_F\\b_H\end{bmatrix}
```

转为：

```math
(F-CH^{-1}D)u=b_F-CH^{-1}b_H.
```

### 主要成果

```text
- exact condensed operator；
- matrix-free low-rank port action；
- no auxiliary global unknowns in outer solve；
- no Q=A_FE^-1 C cache；
- auxiliary back-substitution；
- explicit condensed reference；
- transpose/Hermitian action；
- h5 field/RTA equivalence；
- h2 MPI1/MPI4 action equivalence；
- 1000 repeated applies stable RSS。
```

### h=5 迭代结果

problem-informed z-slab two-level prototype：

```text
iterations = 795
full residual ≈ 9.999e-10
peak RSS ≈ 1.829 GB
R/T/A closure ≈ 1e-12
```

### 关键代码修复

petsc4py complex `Vec.dot` 语义被正确处理为：

```python
np.conjugate(left.dot(right))
```

用于：

```text
MGS
Z^H A Z
Z^H r
```

该修复将 200-step residual 从约 0.259 降到约 0.00105。

### h=2 初始状态

plain matrix-free ILU2 residual 约 0.166；早期 two-level 仍未达到 production。

### 当前状态

exact condensation 成为 Task28 长期稳定模块。

---

## 31. Task027：mesh-robust physical-slab two-level solver

### 原始目标

用 operator-adaptive spectral coarse 构造 mesh-independent Schwarz PC。

### spectral 路线结果

```text
full-slab energy spectral -> fail
interface harmonic -> fail
shifted near-null -> fail
PCHPDDM energy GenEO -> fail
HPDDM recycling -> false residual risk
```

因此 spectral 假设没有成功。

### 实际成功结构

```text
exact matrix-free condensed operator
+ fixed 75D no-RHS Floquet z-hat coarse
+ 16 complete physical z-slabs
+ deterministic owner-computes assignment
+ shifted local ILU1
+ two fixed shifted-F GMRES smoothing steps
+ right FGMRES restart=100
+ explicit true-residual checkpoints
```

### 最终 MPI4 结果

| h (nm) | iterations | true residual | peak total RSS |
|---:|---:|---:|---:|
| 5 | 1201 | `9.839e-7` | 约 1.96 GB |
| 3 | 993 | `9.933e-7` | 约 5.07 GB |
| 2 | 1804 | `9.997e-7` | 约 12.96 GB |

三网格比值：

```math
1804/993 = 1.8167 < 2.
```

### 物理结果

```text
h5: R=0.0890216, T=0.4425883, A=0.4683901
h3: R=0.0046130, T=0.5836534, A=0.4117336
h2: R=0.00134294, T=0.59921324, A=0.39944383
```

### 准确定位

```text
production candidate = yes
tested-range mesh robustness = yes
strict asymptotic mesh independence = not proven
parameter robustness = not proven
physical mesh convergence = not completed
ordinary default = unchanged
```

### 当前状态

Task027 的 fixed coarse + complete physical slab + sm2 成为 Task28 选择性整合目标。

---

# PART VI：阶段 F——Task028 阶段收口

## 32. Task028：stage consolidation、master integration 与 benchmark

### 目标

暂停新求解器扩展，完成：

```text
- Task000-Task027 审计；
- selective merge manifest；
- clean master 上抽取稳定代码；
- 重建 README 和用户文档；
- 建立独立 benchmarks/；
- 重新运行 direct/iterative benchmark；
- 给出最终 master candidate。
```

### 当前已完成

```text
- 从 master@0465b5f 建立整合分支；
- 没有整分支 merge Task027；
- 新增 condensed_dtn.py；
- 新增 physical_slab_two_level.py；
- 新增 stage4_runtime.py；
- 新增 workstation benchmark runner；
- 新增 total MPI RSS telemetry；
- 新增 condensation 与 physical slab tests；
- 选择性归档 Task021-Task027 58 份核心文档；
- 新增 benchmarks/ 目录；
- h5/h3/h2 iterative clean rerun；
- h5/h3 direct rerun；
- 80 unit tests passed，10 skipped；
- focused MPI4 tests passed。
```

### Task028 clean rerun

```text
h5: 1201 iterations, full residual 9.839e-7
h3: 993 iterations, full residual 9.933e-7
h2: 1804 iterations, full residual 9.997e-7, peak 13.080 GB
```

### V1 审查发现

```text
core solver integration = pass
numerical reproduction = pass
ordinary default = pass
history audit = pass
```

但：

```text
benchmark output boundary = fail
benchmark scripts = fail
automatic gate checker = missing
environment reproducibility = fail
documentation completeness = insufficient
sm2 test coverage = insufficient
master merge = blocked pending response_v1
```

### 当前状态

```text
Task028 core consolidation = accepted
Task028 productization = changes required
```

详细要求见：

```text
docs/task028_stage_consolidation_master_integration_benchmarks/review_report_v1.md
```

### Response V1

2026-07-12 在同一分支完成六个 P0 修正：

```text
benchmark output boundary = pass
benchmark scripts = pass
automatic gate checker = 58/58 pass
environment = pass_with_qualification
documentation = pass
sm2 production tests = pass
full suite = 91 passed, 10 skipped
focused MPI4 = each rank 14 passed
h5 clean rerun = 1201 iterations, full 9.839e-7, 1.991 GB
```

环境仍有一项诚实限定：complex MPC 基础镜像固定了本机 digest，但没有公开 pull source，因此不能宣称任意 clean machine 可直接在线重建。当前状态为：

```text
Task028 productization = pass_with_environment_qualification
master merge = pending review v2 and user approval
```

逐项证据见：

```text
docs/task028_stage_consolidation_master_integration_benchmarks/response_v1.md
```

### Review V2 与 Response V2

V2 认为核心求解器和数值结果仍通过，但要求把项目从“开发者能追踪”升级为“新用户能运行、每项能力有理论/代码/benchmark 对照”。同一分支已完成：

```text
- main.py 改为 15 个安全命名 preset，默认 10x10x10 nm Stage1 p1/h5；
- 2D CLI 支持 complex index；3D direct 显式区分 default/OOC/BLR；
- 建立 Quick Start 15 篇、Code Walkthrough 15 篇、Theory 9 篇规范文档；
- 建立 13 个编号 feature benchmark case，每个使用 22 字段契约；
- historical h3/h2 record 拆分 actual source 与 canonical rerun provenance；
- checker 新增 ID、qualified、KSP、coarse condition、physical model 与 artifact provenance Gate；
- 新增 documentation/main preset/lossy port tests；
- 修复 Docker 根挂载时 main.py 导入；
- 修复 2D lossy DtN 把 complex beta 误判为 evanescent、以及在错误参考平面计算 T 的问题。
```

复材料实算确认：TM `R+T+A_volume-1=3.33e-15`，TE 为 `-5.50e-16`；probe 结果仍只作 diagnostic。最新验证：

```text
full suite = 105 passed, 10 skipped（最终重跑前的预期计数，以 outcomes/test_summary 为准）
focused MPI4 = each rank 14 passed
benchmark checker = 87/87 pass
h2 heavy solve = not rerun; numerical records unchanged
```

当前状态：

```text
Task028 V2 implementation = complete
environment = qualified_local_image
master merge = blocked only pending final review and user approval
```

逐项证据见 `response_v2.md` 与本任务 `outcomes/`。

### Review V3 与 Response V3

V3 保持 Task026/027 核心 solver 和既有 3D records 通过，但要求把“目录存在”提升为可执行、可复核、技术准确的交付。同一分支完成：

```text
- Case002 在同一网格完成 explicit/auxiliary 两次完整 solve；
- Case003 冻结 TM/TE complex absorption lightweight records；
- checker 扩展到 143/143，含 lossy、lossless、case files 与 SHA references；
- main.py 增至 17 个 preset，demo/target 物理身份分离；
- Case021 target preset 直接复用 target_stage4_config；
- Case031 增加 PyCharm Docker/WSL External Tool MPI4 workflow；
- 15 篇核心 Quick Start 全部扩展为 16 节教程；
- 11 篇核心 Walkthrough 全部达到源码/shape/ownership/公式/Gate 深度；
- 修正 SparseCoarseVector 字段、smoother-first 顺序、显式 inverse 和 H=I 限制；
- 13 个 Benchmark 全部建立 case-contained contract 并扩展 README；
- Theory 增加统一符号表、module::function anchors 和 2D/3D power constants。
```

最新验证：

```text
full suite = 115 passed, 10 skipped
focused MPI4 = each rank 14 passed
documentation contract = 11 passed
benchmark checker = 143/143 pass
h2 direct/iterative = not rerun; existing 3D records unchanged
```

逐项证据见 `response_v3.md`。当前状态为 ready for final review；master 仍未合并。

---

# 33. 当前项目能力

## 33.1 2D 当前能力概览

当前代码具备或历史上已实现：

```text
- TM vector Maxwell；
- TE scalar Maxwell；
- Floquet periodic constraint；
- manual / MPC backends with restrictions；
- scattered-field + PML；
- Robin port；
- Fourier-DtN port；
- explicit/auxiliary DtN variants；
- real/complex refractive index；
- diffraction order postprocessing；
- R/T and absorption-related outputs；
- field/mesh export；
- parameterized geometry and mesh controls。
```

需要 Task028 文档复核的边界：

```text
- exact supported command for each combination；
- 2D DtN manual-only restriction；
- MPI support restrictions；
- which R/T source is official in each formulation；
- current iterative solver status；
- angle/wavelength scan maintenance status。
```

正式能力矩阵以更新后的 `docs/capability_matrix.md` 为准。

---

## 33.2 3D 当前能力概览

```text
- Stage1 airbox；
- Stage2A double Floquet airbox；
- Stage2B PML airbox smoke；
- Stage2C Fresnel interface smoke/reference path；
- Stage4 flat-layer and block grating；
- p=1/p=2 Nedelec；
- complex material；
- double Floquet MPC；
- auxiliary DtN modal port；
- explicit/static condensed DtN；
- matrix-free condensed DtN；
- direct MUMPS；
- MUMPS OOC；
- MUMPS-BLR fallback；
- official modal R/T/A；
- volume absorption；
- field/mesh export；
- residual/memory telemetry；
- MPI4 complete physical-slab iterative candidate。
```

当前正式目标 solver 状态：

```text
ordinary default = direct
workstation iterative = explicit opt-in
h=5/3/2 = qualified reference set
h=1.5 = not completed
new angle/wavelength/material/geometry = not qualified
```

---

# 34. 当前主要里程碑

| Milestone | 状态 | 关键 Task |
|---|---|---|
| official modal R/T/A and A_volume | 完成 | 002–007 |
| small-cell p/MPI regression | 完成 | 004 |
| target 3D direct h=2 reference | 完成 | 008 |
| black-box iterative exclusion | 完成 | 009–011 |
| AMS/HX real-split qualification | 研究完成，生产失败 | 012–014a |
| DtN slow-mode diagnostic | 完成 | 015–017 |
| p1 sampled-Schur strong signal | 完成但不迁移 | 018–019 |
| target p2 FE-response/Schur mechanism | 完成 | 021–023 |
| h2 full-aux cached-Schur research solve | 完成但不生产 | 025 |
| exact auxiliary-free condensation | 完成 | 026 |
| MPI4 h2 <1e-6 under 14 GB | 完成 | 027 |
| clean master candidate integration | V4 三项加固完成，已获合并许可 | 028 |

---

# 35. 已关闭或暂停的路线

以下路线当前不应重新盲扫：

```text
- ordinary Jacobi/BJacobi/ASM/ILU profile tuning；
- complex AMS direct attachment；
- minimal FE-AMS + aux identity；
- aux-only modal correction；
- diag FE Schur；
- right-only lifted coarse；
- broad Petrov/adjoint W scan；
- low-dimensional top_bottom_y sampled-Schur as p2 mainline；
- cached-Q full-aux architecture as final solver；
- energy spectral/GenEO threshold scan；
- HPDDM cross-solve recycling without explicit true residual；
- unconditional h2 direct on 14 GB environment。
```

这些路线的文档仍有价值，但不进入普通 API。

---

# 36. 当前未完成问题

## 36.1 Task028 收口问题

```text
- Response V4 已关闭 tracked-source-clean、真实 image digest 和最终提交验证，并以 2f9e56d 合入 master；
- complex MPC base image尚无公开pull source，环境保持qualified；
- `SmallDenseInverse`显式逆、内部下划线依赖和异常路径统一清理为非阻断技术债。
```

## 36.2 Task029 当前问题

```text
- h5/h3 baseline、归因和最多两个 h3 候选均已完成；
- 最佳 h3 只下降 15.119%，未达到 engineering_success；
- h2 预测区间 18.882–27.913 GiB，G3/G5/G7/G9 失败并明确 not-run；
- Task029 outcomes 已完成，当前只等待 ChatGPT review 和用户后续合并许可。
```

## 36.3 数值和物理问题

```text
- h=1.5 production solve；
- physical R/T/A mesh convergence；
- local/adaptive mesh refinement；
- angle/wavelength/material robustness；
- near-Rayleigh conditions；
- parameter reuse/warm start；
- lower iteration count and higher throughput；
- slab-internal parallelism / true multilevel H(curl) method。
```

这些扩展在 Task028 期间暂停。

---

# 37. 当前推荐开发顺序

Task28 合并与 Task29 执行已完成。当前强制顺序：

```text
1. 等待 ChatGPT 创建 Task029 `review_report_v1.md`；
2. 在同一分支只处理可执行审查意见；
3. 审查通过且用户明确许可后再合并建议保留的基础设施；
4. 不提升 MPI2/OOC/BLR/SuperLU/ordering 为低内存 profile；
5. 不在当前工作站运行 h2 direct；
6. 后续优先物理收敛资格化或真正 multilevel H(curl) 研究。
```

Task028 完成后，如重新开启研究，推荐顺序：

```text
A. h=2 physical mesh convergence / local refinement；
B. fixed profile small angle/wavelength/material qualification；
C. warm start and cache reuse for scans；
D. iteration/time reduction；
E. h=1.5 preflight；
F. slab-internal parallel or true H(curl) multilevel solver。
```

---

# 38. 文档维护规则

每个后续阶段完成后，应同步更新：

```text
docs/development_progress.md
docs/capability_matrix.md
notes/reference/current_version_boundaries.md
benchmarks/benchmark_summary.csv
对应 task outcomes/review
```

更新原则：

```text
- 后续证据覆盖早期结论；
- 成功和负结果分开；
- 研究正信号不包装为 production；
- 未收敛不输出 official R/T/A；
- reported residual 必须与 explicit true residual 区分；
- ordinary default 变化必须显式审查；
- benchmark 必须记录 commit 和环境。
```

---

# 39. 当前一句话状态

> 项目已经从基础 2D/3D Maxwell、Floquet 和 DtN 验证，发展到可在约 14 GB 工作站上用 MPI4 对目标 p=2、h=2 三维 EUV 光栅取得全增广真残差小于 \(10^{-6}\) 的限定迭代解；Task028 已合入 master，Task029 已完成 h5/h3 direct-memory forensics 并确认 MUMPS KSPSetUp/factorization 是主瓶颈。最佳 h3 direct 候选只下降 15.119%，因此按 `diagnostic_success` 收口，h2 因 18.882–27.913 GiB 预测与硬 Gate 未通过而未运行。
