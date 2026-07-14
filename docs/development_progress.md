# 项目开发进度：Task000–Task031

## 1. 文档定位

本文档记录项目从初始代码审查到 Task031 当前阶段的完整开发进程，面向：

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
2026-07-14
current branch = codex/20260714-task31-compact-pc-memory-optimization
Task028 status = V4 closed and merged to master at 2f9e56d
Task029 status = diagnostic_success; review V2 closed; merged to master at bfb6586e
Task030 status = final review V3 passed and merged to master at 545165b
Task031 status = strong_memory_success_slow_but_memory_efficient; Review V1 hardening complete in response_v1; pending final review
```

## 1.1 2026-07-14 最新更新

Task031 Review V1 接受正式 h5/h3/h2 的数值正确性与 absolute memory strong Gate，不要求重跑正式计算；合并前加固集中在 master 同步、端口文档、matrix-free/performance 术语、内存口径和选择性合并边界。分支已真实 merge 当前 `master`，保留 [`project_service_requirements_and_forward_model_roadmap.md`](project_service_requirements_and_forward_model_roadmap.md) 与 [`project_service_requirements_phase1_scope.md`](project_service_requirements_phase1_scope.md)：后续统一规划范围为 `13.5 nm + fixed Si + 1–10° grazing + S/P`，但 Task031 只资格化 theta=80°（10° grazing）、S polarization 的 frozen 单点。

新增 [`iterative_solver_ports.md`](iterative_solver_ports.md)，统一列出 Task27 canonical、Task30 compact、Task31 memory-first 的命令和身份；FGMRES 是当前 adaptive PC 的合法/已资格化 outer port，普通 GMRES 被线性认证阻塞，TFQMR/BCGS 只有未资格化接口，fixed Richardson 与 selective boundary Jacobi 是 research-only numeric negative。Task31 的精确术语是 assembled-F-free public MPC form-action path，不是缓存优化的低层 element-kernel matrix-free；一次性 `release_f()` 不是变慢主因，每次 form action 的装配与通信才是主要成本。

Task030 Review V3 已通过并按用户许可合入 master（merge `545165b`）。Task031 从该 clean merge point 创建独立分支，目标是在 frozen p2/80-mode/exact-condensed target 上继续压缩内存，同时把 explicit true residual 收敛置于所有性能目标之前。

Task031 新增外部 simultaneous RSS/cgroup/swap/stage sampler、public DOLFINx-MPC form action、condensed fine-action lifecycle、PC linearity/determinism certification、exact factor fingerprints 与对象 ledger。研究漏斗否定了 restart50、ordinary GMRES、fixed Richardson、20 slabs、boundary Jacobi 与 factor dedup；保留的组合是 FGMRES90 + Task030 physical-slab/wave coarse + 16 slabs overlap0.125 + assembled-F-free public form action + compact lifecycle。

clean SHA `45a0fc6e...` 的 full h5/h3/h2 分别在 1157/1994/1977 步达到 full residual `9.960e-7 / 9.974e-7 / 9.998e-7`。外部 simultaneous worker peak 为 1.619598/3.474346/7.897675 GiB，h2 legacy internal peak 为 8.176441 GiB。相对 Task030 历史 9.374729 GiB 的辅助观察降幅约 15.8% / 12.8%，因 sampler 不完全同口径，保守结论为从约 9.4 GiB 压到约 8.0–8.2 GiB。h2 达到 strong memory success 且无 swap；代价是 solve 11982.581 s，约为 Task030 的 5.01x，因此分类为 `strong_memory_success_slow_but_memory_efficient`，ordinary default 仍不改变。

Task029 已按用户许可合并；Task030 从 `bfb6586e` clean master 创建独立分支。Task030 建立了 active/master-aware nonmatching H(curl) transfer 与 exact condensed Galerkin 基础设施，但五个正式 p/h 候选 100 步残差均比 Task027 基线差 146–264 倍，证明当前 792D p1 coarse 不是目标慢误差的有效表示。

真正正反馈来自 Task27-derived physical-slab + 75D wave-coarse 架构，并加入 symmetric pre/post sm2、ILU0、subdomain-local shift、factor-only storage 和 FGMRES restart90。Review V2 后，h5/h3 在 final implementation commit `5b81359daee0874793c44b019d9c914b334db483` 上 clean 复跑，分别用 855/962 步收敛，峰值 1.687653/3.792912 GB；h3 同时通过 3.8 GB 绝对线和相对 Task027 canonical 降低 25.37% 的相对线，iteration ratio 为 1.125。h2 不重跑，保留为 1873 步、full true residual `9.972e-7`、含 R/T/A 峰值 9.374729 GB（-28.33%）的 reviewed historical dirty-worktree reference。因此分类为 `workstation_memory_success_with_qualifications`；ordinary default 未改变。

Review V1 接受数值结果并要求修正 benchmark/provenance。三份正式 records 已从原 artifacts 恢复 source commit、tracked-dirty qualification、完整命令/时间/镜像/host 和 artifact SHA-256；Case060 已接入 203 项真实数值 Gate，三份记录也进入 manifest，使 normal checker 可重复生成完全相同的 summary。当前 ILU1/ILU0 reported factor nnz 相同，不能宣称 factor-nnz compression；factor-only 只在 PETSc 3.24.0 complex build 验证，跨版本需回归。

Task028 已按普通 merge commit 合入 `master`，并完成 master release check。Task029 从该合并点新建独立分支，完成 direct-memory telemetry、外部 0.25 s sampler、matrix/factor inventory、Case050、h5/h3 baseline、H1–H7、profile 筛选和 h2 安全决策。遥测明确区分 simultaneous worker RSS、各 rank 历史峰值和、MPI 进程树与 cgroup；Task28 canonical records 保持只读。

MPI4 h5/h3 baseline simultaneous RSS 为 2328.145 / 8651.098 MB，主峰都位于 KSPSetUp。release-base 公共生命周期候选在 h3 只下降 5.462%；最佳 default MUMPS MPI2 在 h5/h3 分别下降 28.893% / 15.119%，全部 residual/R/T/A Gate 通过且无 swap，但 h3 低于 20% 工程门槛。因此 Task029 分类为 `diagnostic_success`，不产生合格低内存 direct profile。h2 两类外推中央值为 22.214 / 22.330 GiB、区间 18.882–27.913 GiB，G3/G5/G7/G9 失败，未启动 h2。

Review V1 后补充的构建/链接与固定四核审计确认，当前 PETSc/MUMPS 链接可控的 OpenBLAS pthread，但 MPI1×4 在 KSPSetUp 的 CPU 核均值/峰值仅 0.999/1.054，Stage4 相对 MPI1×1 只有 1.054× speedup。最终身份为 `threaded_direct_capability=unavailable_in_current_image`，因此 threaded h3 按 T4 `not_run`；ordinary default 仍不改变。

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

# 36. Task029：Stage4 direct memory forensics

## 36.1 最终状态

```text
Task = Task029 — Stage4 direct memory forensics
branch = codex/20260713-task29-stage4-direct-memory-forensics
base = master@2f9e56d2edddb801780504f681b2ff295d993e02
classification = diagnostic_success
engineering_success = no
threaded_direct_capability = unavailable_in_current_image
h2 = not_run
h3_threaded_direct = not_run
review = V2 technical review pass
master = user-approved; merge pending execution
ordinary default changed = no
```

Task029 的成功是“诊断、基础设施和安全决策成功”，不是“获得了新低内存 direct solver”。这一分类贯穿代码、Benchmark、能力矩阵和合并边界。

## 36.2 为什么启动

Task028 已把目标 p2/h5、h3、h2 的 direct reference 与 MPI4 workstation iterative 路径收口，但 direct h3/h2 的因子内存仍是工作站边界：h3 direct 已约 8 GiB，历史 h2 direct 约 20.5 GiB，超过当前约 14 GiB 环境。此前只有最终/历史 RSS，没有足够证据回答内存是在 DtN 增广、MUMPS factorization、KSPSolve 还是后处理中增长，也无法判断对象释放、rank 数、OOC/BLR 或 ordering 是否值得提升。

如果不先完成分阶段剖析，后续容易把统计口径变化误写成优化，把单网格正信号包装成 profile，或在没有安全余量时直接运行 h2。本任务不解决物理网格收敛、新迭代预条件器、adaptive mesh 或跨机器 COMSOL 性能可比性。

## 36.3 冻结问题与 baseline

冻结模型为 50 × 25 × 140 nm 周期单元、17 × 25 × 120 nm complex-Si block、13.5 nm、theta=80°、phi=0、s 偏振、p2 Nédélec、double Floquet + auxiliary Fourier-DtN。模式策略始终为 `auto_propagating`，top/bottom 各 40 个模式、`n_aux=80`。允许改变的是 direct 生命周期、MPI rank/thread 组合、明确 opt-in profile/package/ordering 与遥测；禁止改变物理、模式、official R/T/A、full solve 和 ordinary default。

基线是 default MUMPS、MPI4、每 rank 1 thread。数值资格要求 full explicit true residual、Task28 R/T/A 绝对差和能量闭合均 `<=1e-8`。内存主口径是外部同一时刻所有 worker rank RSS 的和；cgroup current、swap 和各 rank 历史峰值和分别记录，不混写。

| 指标 | h5 MPI4 baseline | h3 MPI4 baseline |
|---|---:|---:|
| FE / auxiliary / augmented rows | 44,698 / 80 / 44,778 | 198,438 / 80 / 198,518 |
| true residual | `5.225e-12` | `1.382e-11` |
| max Task28 R/T/A abs delta | `0` | `1.865e-14` |
| simultaneous worker RSS | 2328.145 MiB | 8651.098 MiB |
| cgroup current peak | 1729.035 MiB | 8353.727 MiB |
| KSPSetUp / KSPSolve | 1.838 / 0.0467 s | 31.200 / 1.603 s |
| augmented / factor nnz | 4,896,156 / 33,862,428 | 21,317,860 / 266,127,836 |
| swap in / out | 0 / 0 | 0 / 0 |

## 36.4 采用的方法

| 方法 | 解决的问题 | 保护措施 |
|---|---|---|
| 0.25 s external sampler | 把 simultaneous RSS/cgroup/swap 峰值映射到 solver stage | 原始 timeline 留在 ignored artifacts，轻量 CSV 入库 |
| matrix/factor inventory | 区分 base/augmented 存储与 LU fill | PETSc 原始 0 memory/fill 不冒充有效 allocator 测量 |
| progress checkpoints | 标记 `before/during/after KSPSetUp`、solve、RTA、field output | 每个 full run 保留 residual/R/T/A |
| H1–H7 单因素假设表 | 按收益、风险和 stop rule 筛选优化 | h5 先筛，最多两个候选进 h3 |
| clean-source candidate runner | 绑定 commit、image digest、command、profile | tracked-source-dirty 直接拒绝 |
| h2 两路径外推 + G1–G10 | 在高内存运行前给出范围与硬 stop | Gate 未全 true 时 runner 保持锁定 |
| 构建/链接与 `/proc` 审计 | 区分 NumPy BLAS、MUMPS 实际 BLAS 和真实 CPU 使用 | 固定 `OMP=1`、CPU `0-3`，只控制 OpenBLAS pthread |

低风险实现包括幂等 `DirectSolveFailure.cleanup()`、OOC scratch/I/O/cleanup telemetry、显式 MPI distributed factor package 选择正确性，以及默认 `false` 的 `direct_release_base_after_augmentation`。这些基础设施与性能 profile 资格分开审查。

## 36.5 主要实验与实施步骤

实际运行顺序为：h5/h3 MPI4 baseline；h5 MPI1/2/4 rank 诊断；H1 release-base h5→h3；H5/H6 的 MPI2、SuperLU_DIST、OOC、BLR、ordering h5 筛选；唯一正式 MPI2 候选 h5→h3；h2 外推与 Gate；最后按 review 进行 PETSc/MUMPS/BLAS 静态审计和固定四核 h5 MPI4×1、MPI2×2、MPI1×4、MPI1×1。

没有运行 h2 direct；没有在 h5 线程 Gate 失败后运行 threaded h3；没有重建 image 或在 Task029 实现 multilevel solver。建议模板中的 MPI1×2 是可选补点，但 MPI1×4 已同时触发 T0/T1/T3 stop，继续补点不会改变能力身份。

## 36.6 关键结果

### KSPSetUp / MUMPS factorization 是主峰

h3 从 `before_ksp_setup` 到 `during_ksp_setup_peak`，worker RSS/cgroup 分别增加约 6472.43 / 6474.57 MiB。KSPSolve 结束只比 factorized checkpoint 多约 6.98 MiB worker RSS；official RTA 增量不足 1 MiB；field output 形成约 129.06 MiB 的较低尾部平台。base/augmented 共存约增加 729 MiB worker RSS，只占总峰值约 8%–9%。

h3 factor/augmented nnz 比为 12.484；统一 nnz-storage estimator 约 6093/489 MiB。前者是结构计数，后者是估算，不是 MUMPS allocator 实测。

### H1–H7 与候选结果

下表中“相对变化”为同 h 的 `baseline - candidate` 再除以 baseline：正数表示内存减少，负数表示恶化。

| 路线 | h5 worker RSS 变化 | h3 worker RSS 变化 | 数值 | 最终处置 |
|---|---:|---:|---|---|
| H1 release-base MPI4 | +4.767% | +5.462% | pass | 合并显式低风险生命周期控制；非 profile |
| H2 preallocation rewrite | not_run | not_run | `mallocs=0`,`nz_unneeded=0` | 无 allocator 正证据，拒绝 speculative rewrite |
| H3 cleanup/temporaries | 非主峰收益 | full flow 保持 | pass | 合并幂等 failure cleanup |
| H4 direct A_aug assembly | not_implemented | not_implemented | 无 public safe API | 不使用 private framework hack |
| H5 MUMPS MPI2 | +28.893% | +15.119% | pass | 最佳诊断点；h3 未达 20%，拒绝 profile |
| H5 SuperLU_DIST | -14.462% | not_run | pass | 内存和时间负向 |
| H6 MUMPS OOC | +13.744% | not_run | pass | 559,715,776 bytes scratch、1.539×时间；仅 fallback |
| H6 BLR 1e-5 | -3.427% | not_run | fail | residual `4.704e-3`，拒绝 |
| H6 ordering ICNTL(7)=3 | -4.093% | not_run | pass | factor nnz/峰值增加，拒绝 |
| H7 early factor release | 只影响尾部 | not_run | 风险较高 | 不是全局峰值修复，本任务不实现 |

### 少 rank + 多线程最终结论

静态审计确认 PETSc 3.24.0 / MUMPS 5.8.1 通过 `-llapack -lblas` 动态链接 system OpenBLAS 0.3.26 pthread；OpenBLAS API 能读取并修改线程数。NumPy 使用独立 scipy-openblas 0.3.29，只作 Python 侧交叉检查，不代表 MUMPS。活动 PETSc/MUMPS 未显示 OpenMP 构建，正式线程运行固定 `OMP_NUM_THREADS=1`，避免 OpenMP 嵌套；但两个 OpenBLAS runtime 可能形成多个线程池，runnable-thread oversubscription 不能完全排除，CPU affinity 只负责把实际执行封顶在 `0-3`。

| 固定 CPU 0-3 | worker RSS | KSPSetUp | Stage4 | KSPSetUp CPU 核均值/峰值 |
|---|---:|---:|---:|---:|
| MPI4×1 | 2351.707 MiB | 2.385 s | 18.311 s | 3.906 / 4.061 |
| MPI2×2 | 1677.062 MiB | 1.953 s | 20.687 s | 3.272 / 4.025 |
| MPI1×4 | 1399.648 MiB | 23.841 s | 48.273 s | 0.999 / 1.054 |
| MPI1×1 | 1401.988 MiB | 25.578 s | 50.891 s | 0.999 / 1.060 |

MPI1×4 的 worker thread 数从 3 增至 12，但 KSPSetUp 仍约 1 核，Stage4 相对 MPI1×1 只有 1.054× speedup。T2 内存比通过（RSS/cgroup 均远低于 1.20×），但 T0 runtime、T1 与 T3 失败；最终身份是 `threaded_direct_capability=unavailable_in_current_image`，T4 要求 threaded h3=`not_run`。

## 36.7 结果解释

主导机制是 LU fill，而不是 auxiliary DoF 或后处理。提前释放 base 对象只能回收次要共存量；减少 rank 能减少进程重复和总 RSS，却削弱分布式 factorization 并行。OOC 把部分 RAM 压力转成 scratch/I/O；BLR 则引入当前阈值不可接受的近似误差。

线程审计进一步说明：有可控 pthread 和更高进程 thread count，不代表 MUMPS factorization 会多核执行。MPI1×4 的实际 CPU 证据与 MPI1×1 相同，因而不能用静态 BLAS 能力或 NumPy matmul 证明 threaded direct 可用。

## 36.8 h2 预测与 G1–G10

DoF 幂律与 factor-nnz/fill 两条路径给出 h2 中央预测 22.214 / 22.330 GiB，敏感性范围 18.882–27.913 GiB。这里属于外推，不是实测 h2。

| Gate | 状态 | 含义 |
|---|---|---|
| G1/G2 | true | h5/h3 MPI2 数值通过 |
| G3 | false | h3 只降 15.119%，没有双网格 20% |
| G4 | true | h3 无 swap |
| G5 | false | 预测上界高于 13.5 GiB |
| G6 | true | 13.5 GiB 安全上限未放宽 |
| G7 | false | 当前可用内存低于预测下界 |
| G8 | true | 只有一个最终诊断候选 |
| G9 | false | 早期 Gate 已失败，未实现/启用 h2 watchdog |
| G10 | true | Task28 h2 record 未覆盖 |

因此 `h2 = not_run`，不是 pass、fail-run 或 skipped-without-reason。

若未来确有 direct h2 需求，资源规划应使用至少 48 GB、优先 64 GB 的机器，并先实现 watchdog/clean-abort；这不构成当前工作站运行许可。

## 36.9 成功路线、失败路线与负结果

成功并建议保留的是 telemetry、matrix/factor inventory、clean provenance、异常 cleanup、factor package 选择正确性、OOC 证据、显式 release-base 控制、Case050 与 h2 guard。它们改善可观测性、正确性或安全性。

失败或只作诊断的是 MPI2、OOC、BLR、SuperLU_DIST、ordering 和当前镜像 threaded direct；都不得提升为 ordinary/recommended profile。COMSOL GMG 只提供“未来可研究完整多层层次”的定性线索，不是本任务 runtime、R/T/A 或每 DoF benchmark。

## 36.10 最终决策与合并边界

| 对象 | 决定 | 原因 |
|---|---|---|
| telemetry / Case050 / h2 guard | V2 通过，允许合并 | 可复用且有合同测试 |
| failure cleanup / package selection fix | V2 通过，允许合并 | 正确性与异常安全 |
| release-base option | 建议合并，保持默认 false | 低风险，收益不足 profile 资格 |
| MPI2/OOC/BLR/SuperLU/ordering | 不提升 | 内存、时间或数值 Gate 失败 |
| threaded direct | 不创建 profile | 当前 image KSPSetUp 仍单核 |
| ordinary default | 不改变 | 无候选同时通过工程 Gate |
| h2 / threaded h3 | 不运行 | 分别被 G/T Gate 阻止 |
| master | 用户已许可，待执行合并 | V2 技术审查通过；Task030 启动请求提供明确许可 |

## 36.11 局限

factor storage 是 nnz estimator；部分 PETSc/MUMPS raw memory/fill 字段不可用。CPU 核数由 0.25 s `/proc` 累计 CPU 时间差分，不是硬件计数器。线程结论只适用于当前 image、目标矩阵与固定四核条件。完整 field/mesh/timeline 保存在本地 ignored artifacts，不进入 Git。物理 residual/closure 通过也不等于 h3/h2 R/T/A 已完成网格收敛。

## 36.12 下一步及原因

由于对象生命周期、ordering 和当前 BLAS 线程都不是主峰解法，停止继续 direct 微调。下一阶段应优先做 h3/h2 物理网格收敛或 graded/adaptive mesh qualification；若继续降低 solver memory，则研究真正 multilevel H(curl)、low-order-refined multigrid 或带受控 coarse direct solve 的并行 physical Schwarz。只有更换为明确支持 threaded factorization 的构建时，才重新执行固定四核 h5 能力审计。

## 36.13 证据入口

- [Task029 outcomes summary](task029_stage4_direct_memory_forensics/outcomes/summary.md)
- [线程能力审计](task029_stage4_direct_memory_forensics/outcomes/threaded_direct_capability_audit.md)
- [h2 launch decision](task029_stage4_direct_memory_forensics/outcomes/h2_launch_decision.md)
- [Task029 review V1](task029_stage4_direct_memory_forensics/review_report_v1.md)
- [Task029 response V1](task029_stage4_direct_memory_forensics/response_v1.md)
- [Task029 review V2](task029_stage4_direct_memory_forensics/review_report_v2.md)
- [Task029 response V2](task029_stage4_direct_memory_forensics/response_v2.md)
- [Benchmark Case050](../benchmarks/cases/050_stage4_direct_memory_forensics/README.md)
- [Task 回顾标准](task_retrospective_standard.md)
- [direct runner](../benchmarks/run_direct_memory_forensics.py)
- [direct profile walkthrough](../notes/reference/code_walkthrough/30_direct_solver_profiles.md)

---

# 37. 当前未完成问题

## 37.1 Task028 收口问题

```text
- Response V4 已关闭 tracked-source-clean、真实 image digest 和最终提交验证，并以 2f9e56d 合入 master；
- complex MPC base image尚无公开pull source，环境保持qualified；
- `SmallDenseInverse`显式逆、内部下划线依赖和异常路径统一清理为非阻断技术债。
```

## 37.2 Task029 当前问题

```text
- h5/h3 baseline、归因和最多两个 h3 候选均已完成；
- 最佳 h3 只下降 15.119%，未达到 engineering_success；
- h2 预测区间 18.882–27.913 GiB，G3/G5/G7/G9 失败并明确 not-run；
- review V1 更正、V2 技术验收与 response_v2 状态同步均完成，用户已许可合并；
- 当前 image 的 threaded direct 不可用，threaded h3 按 T4 未运行。
```

## 37.3 数值和物理问题

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

# 38. 当前推荐开发顺序

Task28 合并与 Task29 执行已完成。当前强制顺序：

```text
1. Task029 `response_v1.md`、全部 P0 更正和 V2 技术验收已完成；
2. 提交 `response_v2.md` 并完成轻量 release checks；
3. 按用户许可合并 Task029 后，从更新的 clean master 新建 Task030 分支；
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

# 39. 文档维护规则

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

# 40. 当前一句话状态

> 项目已经从基础 2D/3D Maxwell、Floquet 和 DtN 验证，发展到可在约 14 GB 工作站上用 MPI4 对目标 p=2、h=2 三维 EUV 光栅取得全增广真残差小于 \(10^{-6}\) 的限定迭代解；Task028 已合入 master，Task029 以 `diagnostic_success` 收口并确认 MUMPS KSPSetUp/factorization 是 direct 内存主瓶颈。最佳 h3 候选只下降 15.119%，当前 image 的 MPI1×4 KSPSetUp 仍约 1 核，故 engineering_success=no、threaded direct unavailable、threaded h3 与 h2 均按 Gate 未运行。

---

# 41. Task030：3D H(curl) 多层与低内存迭代研究

## 41.1 任务身份与为什么启动

```text
Task = Task030
branch = codex/20260713-task30-multilevel-hcurl-low-memory-iterative
base master = bfb6586e030efd5208ebd796c39fdc31301e1d6e
physical model = Task27/28 frozen p2 Stage4 target
ordinary default changed = no
current classification = workstation_memory_success_with_qualifications
```

Task029 已证明 direct 的内存主峰在 MUMPS analysis/factorization；MPI2、OOC、BLR、ordering 与线程都没有得到可提升的 h3 工程收益。Task027 虽能在约 14 GB 内完成 h2，但 16 个大 slab ILU1、shifted-F 副本和 FGMRES basis 仍让 h2 达到 13.08 GB。因此 Task030 转向 H(curl) 层级、低 fill smoother、对象生命周期和 Krylov memory，而不继续微调 direct。

COMSOL 报告只提供定性依据：真正多层 Maxwell PC 可能明显低于 direct；它不是当前 FEniCS R/T/A reference，也不能用于跨机器时间排名。

## 41.2 冻结基线与数值合同

物理保持 50×25×140 nm cell、17×25×120 nm Si grating、13.5 nm、theta=80°、phi=0、s polarization、p2 Nédélec、双 Floquet、80 个 auto-propagating modal unknowns、exact matrix-free `F-C H^-1D`、full true residual 和 official modal R/T/A。

Task027 baseline 为 h5/h3/h2 的 1201/993/1804 步和 1.991/5.08/13.080 GB。Case031 h5 100-step residual `2.5737371765314062e-3` 由 SHA-256 pinned record 读取，候选不得手写或覆盖基线。

## 41.3 层级与 transfer 基础设施

实现 `ActiveDofMap`，将 MPC slaves 从 coarse columns 中移除，再逐 active column 用 DOLFINx nonmatching interpolation 构造 p1→p2 H(curl) transfer；每列执行 MPC backsubstitution/homogenize，restriction 为 Hermitian transpose。transfer 支持 MPI CSR cache，fresh/cache action 可复核。

MPI4 目标规模：fine h5/p2 full/active/slave 为 44,698/40,800/3,898；coarse h10/p1 为 1,067/792/275；P 有 145,998 nnz、无零列、adjoint error `1.586e-15`、fresh/cache error `6.410e-15`。精确 coarse operator 使用 `P^H(F-CD)P`，保留全部 80 modes；serial/MPI2 action tests 通过。

这部分达到 infrastructure success，但没有直接得到 solver success。

## 41.4 多 lane 漏斗与负结果

| lane | h5 100-step true residual | 相对基线 | 结论 |
|---|---:|---:|---|
| Jacobi + p/h coarse | 0.680155 | 264.27× | negative |
| z-layer patch + p/h coarse | 0.374864 | 145.65× | negative |
| vertical column + p/h coarse | 0.513599 | 199.55× | negative |
| cell patch + p/h coarse | 0.512730 | 199.22× | negative |
| 16-slab ILU0 + p/h coarse | 0.561064 | 218.00× | negative |

相同 slab smoother 不加 p/h coarse 的 20-step residual 为 0.381817，加 coarse 后反而为 0.685751。说明 transfer/Galerkin 正确，但 792D p1 coarse 没有覆盖当前 Maxwell 近核、梯度和 grazing-wave 慢方向。当前不能声称 pure h-GMG、mixed p/h 或 AMS/HX 成功。

全 80 mode Woodbury 只提供很小改善且增加内存；225D x-harmonic coarse、更多 z hats、去 overlap pre-only、单次廉价 post 和 restart80 都未过 Gate。失败实现没有进入 ordinary default。

## 41.5 正反馈如何继续深化

Task027 ILU1 overlap PC 增加真正 post smooth 后，h5 100-step residual 变为 `1.273503e-3`，达到 strong-positive。此后逐步验证：

1. ILU0 仍为 `1.865566e-3`，说明对称组合后 fill1 不是必要条件；
2. local diagonal shift 不保留完整 shifted-F，residual 不变；
3. factor-only 逐块 setup 后销毁 source submatrix/KSP，只保留因子，action serial/MPI2/MPI4 等价；
4. restart90 仍通过 weak-positive，restart80 失败，因此停止继续缩小。

最终候选固定为 75D wave coarse、16 slabs overlap0.25、ILU0、sm2 symmetric pre/post、local shift、factor-only、right FGMRES(90)。这不是“真正多重网格成功”，而是现有有效 coarse 与更低内存 smoother/lifecycle 的工程改进。

这里的 ILU0 结论只表示“该冻结目标在对称组合下不需要配置 ILU1 才能收敛”。Task27 ILU1 与 Task30 ILU0 的 `global_slab_factor_nnz` 完全相同，当前统计口径不能证明 stored fill 下降。可归因的内存改进是 local shift、factor-only 释放 source submatrix/KSP/PC wrapper 以及 restart90；factor nnz 保持 `measurement_unresolved`。

## 41.6 h5/h3/h2 正式结果

| h | DoF | iterations | full true residual | peak incl RTA | R/T/A | direct max delta |
|---:|---:|---:|---:|---:|---|---:|
| 5 | 44,698 | 855 | 9.924905e-7 | 1.687653 GB | 0.0890216035 / 0.4425882732 / 0.4683901222 | 5.438e-9 |
| 3 | 198,438 | 962 | 9.903890e-7 | 3.792912 GB | 0.00461303218 / 0.58365335775 / 0.41173361173 | 7.719e-10 |
| 2 | 615,108 | 1873 | 9.972228e-7 | 9.374729 GB | 0.00134293442 / 0.59921323601 / 0.39944383222 | 6.561e-9 |

h3 较 Task027 canonical 5.082275 GB 下降 25.37%，h3/h5 iteration ratio 为 1.1251。其 3.792912 GB 同时通过 3.8 GB 绝对线和“相对下降至少 25%”分支。reported/condensed/full residual、80 modes、R/T/A 与 closure 全通过；h5/h3 均为 clean final-HEAD rerun。

## 41.7 h2 预测、实测与当前边界

h5/h3 的 DoF–RSS 仿射/幂律两个独立模型预测 h2 中央值为 9.5298/7.0337 GB；较保守仿射值的 15% engineering upper 为 10.9593 GB，满足 G5/G6。唯一候选 attempt1 的实测峰值为 9.342113 GB，较 Task027 降低 28.58%；1800 步 solve time 2220.43 s，也略低于 Task027 2345.26 s。

attempt1 真残差为 `1.461130e-6`，所以未输出 official R/T/A。随后只对同一 PC/restart 将 max_it 延到 2100；共同 monitor 点残差逐位一致，并在 1873 步收敛。最终 full residual `9.972228e-7`、含 R/T/A 峰值 9.374729 GB、closure `2.639e-9`、direct 最大差 `6.561e-9`。Review V2 明确不重跑 h2，因此这些值的身份是 `reviewed_historical_dirty_worktree_reference`，不是 clean final-HEAD evidence；h2/h3 iteration ratio 为 1.947，且 1873 步仍高于 1200 偏好。

## 41.8 合并边界

建议 final review 接受的内容：nonmatching H(curl) transfer/cache、condensed Galerkin 研究基础设施、local shift、factor-only storage、symmetric pre/post opt-in、Case060、tests 和完整文档。不得提升 p/h solver profiles、Woodbury、x-harmonic、AMS/HX、restart80 或 heavy artifacts。validated infrastructure API 已与失败 candidates 隔离；Task027 canonical 和 ordinary default 均保持不变。master 仍等待 Response V2 后的 final review 与用户明确许可。

## 41.9 局限与下一步因果关系

h2 已收敛，但当前 evidence 只覆盖单个角度/波长/材料/分区，且 1873 步仍高于 1200 目标。下一步优先参数鲁棒性、fallback 和 restart/内存监控；若目标是进一步降低迭代数，应研究 Maxwell commuting projection、梯度/近核 auxiliary space 和材料/端口感知的真正多层 hierarchy，而不是继续扩大当前失败 p1 coarse。

证据入口：

- [Task030 outcomes](task030_multilevel_hcurl_low_memory_iterative_solver/outcomes/summary.md)
- [Case060](../benchmarks/cases/060_multilevel_hcurl_iterative_solver/README.md)
- [candidate funnel](task030_multilevel_hcurl_low_memory_iterative_solver/outcomes/candidate_funnel.csv)
- [transfer validation](task030_multilevel_hcurl_low_memory_iterative_solver/outcomes/transfer_validation.md)
- [h2 decision](task030_multilevel_hcurl_low_memory_iterative_solver/outcomes/h2_launch_decision.md)

## 41.10 Review V1 更正与证据边界

Review V1 的五项 P0 已在同一分支回应：正式 h5/h3/h2 lightweight records 补齐实际运行 provenance；Case060 checker 从文件存在性升级为 provenance、solver identity、80 modes、三残差、R/T/A、closure、direct delta、内存和分类的 203 项 Gate；manifest 加入三份 experimental entries，normal checker 连续生成保持一致；项目级命名统一为 `compact physical-slab low-memory experimental profile`；理论、walkthrough、capability、benchmark 和边界文档同步说明 p/h multigrid solver 失败。Review V2 又把 h5/h3 更新为 clean final-HEAD rerun，并把 h2 固定为 historical dirty-worktree reference。

最终成功求解器身份固定为 `task27_derived_physical_slab_wave_coarse`。H(curl) transfer/Galerkin 是 validated research infrastructure，不是 successful GMG。factor-only 在 PETSc 3.24.0 complex build 通过生命周期测试；跨版本兼容仍需回归。Task27 ILU1 与 Task30 ILU0 的 reported slab-factor nnz 相同，因而不把内存下降解释为已证明的 factor-nnz compression。

## 41.11 Review V2：clean evidence 与 selective-merge 边界

R1 在 final implementation commit `5b81359daee0874793c44b019d9c914b334db483` 上重跑 h5/h3。两次 record 均写 `git_dirty=false`、`tracked_source_dirty=false`、`tracked_source_verification=host_git_clean_attestation`，且 verified clean SHA 与容器 HEAD 完全一致。h5 heavy JSON SHA-256 为 `2be05820cf69db67ba72b257c44624c08e15f7f7ceeae6e479eed2a9e68523f3`；h3 为 `48c9bb51b89a99b7ba1653f8c95f8450e7917f987274c1aef631464484275232`。h2 按审查要求不重跑，保留 `reviewed_historical_dirty_worktree_reference` 身份，并显式链接 clean h5/h3 的 solver/physics 等价性。

R2 把 `hcurl_multilevel.py` 的 validated infrastructure API 限定为 active DoF、nonmatching transfer/cache/validation 和 condensed Galerkin。Damped Jacobi、Galerkin multilevel PC、Modal Woodbury 等 solver-negative candidates 只由 research runner/tests 直接导入，普通 `src.solvers` 不导出。最终工程求解器仍是 Task27-derived compact physical-slab profile，不是 p/h GMG。

因此 Task030 最终状态为 `workstation_memory_success_with_qualifications`。ordinary default 不变；当前分支只可提交 Response V2 并等待 final review，不能直接合并 master 或启动 Task31。Task31 必须在用户批准 selective merge 后，从 clean master 新建独立分支。

---

# 42. Task030 后的当前推荐顺序

```text
1. 提交并推送 Task030 Response V2；
2. 等待 ChatGPT final review，ordinary default 不变；
3. 用户明确批准后，按 selective merge 边界合入 master；
4. 在合并后的 clean master 新建 Task31 独立分支；
5. Task31 优先压缩 Krylov、F/condensed 重复对象、slab factors 与生命周期。
```

# 43. 当前一句话状态（Task030）

> Task030 已获得 `workstation_memory_success_with_qualifications`：Task27-derived compact physical-slab profile 的 clean final-HEAD h5/h3 分别为 855/962 步、1.687653/3.792912 GB，h2 保留为 1873 步、9.374729 GB 的 reviewed historical dirty-worktree reference；80 modes 与 official R/T/A 通过，H(curl) transfer/Galerkin validated infrastructure 正确，但 792D p1 coarse 的 p/h multigrid solver 明确失败。ordinary default 未改变，master 等待 final review 与用户选择性合并许可。

---

# 44. Task031：compact physical-slab 内存优先结构优化

## 44.1 最终状态

```text
Task = Task031
branch = codex/20260714-task31-compact-pc-memory-optimization
base = Task030 merged master 545165b3d29396dcc3a8d5b029089175eafa3c4a
clean implementation SHA = 45a0fc6e19535cb8f14fbfb186f099019612fec2
classification = strong_memory_success_slow_but_memory_efficient
ordinary_default_changed = false
review_status = Review V1 response_v1 hardening complete; pending final review
master_decision = pending review and explicit user approval
```

## 44.2 为什么启动

Task030 已把 h2 从 Task027 的 13.08 GiB 压到 9.374729 GiB并真实收敛，但对内存受限工作站仍接近 10 GiB。Task030 也证明当前 p/h coarse 不是有效慢误差空间，因此 Task031 不再扩大失败层级，而是围绕已经能收敛的 physical-slab + 75D wave coarse，逐项审计 Krylov basis、assembled fine `F`、slab factor、对象重叠和 PC 合法性。

如果不做这一步，工程风险有两个：一是用 per-rank historical peak sum 或 current RSS 下降误判真实峰值；二是为了省 Krylov 存储把非线性 PC 错配给普通 GMRES，得到不受支持的算法。Task031 不解决任意材料/角度鲁棒、真正 mesh-independent multigrid或多 RHS 吞吐。

## 44.3 冻结问题与 baseline

物理仍为 50×25×140 nm cell、17×25×120 nm complex-Si block、13.5 nm、theta80/phi0/s、p2 Nédélec、double Floquet、80 个 auxiliary DtN modes、exact `F-C H^-1D` 与 official volume-absorption R/T/A，MPI4。ordinary config、模式数、物理、RTA 定义与 full residual 都禁止改变。

Task030 baseline：h5/h3/h2 为 855/962/1873 步，full residual 都 `<=1e-6`，peak 1.687653/3.792912/9.374729 GiB。Task031 h3 continuation 需要 `<=3.50 GiB` 或降幅 `>=8%`；h2 解锁还要求 h3 full pass 且降幅 `>=8%`、两套中心预测 `<=8.8 GiB`、保守上界 `<=10 GiB`、无 swap、clean source 和 watchdog。

## 44.4 采用的方法

### 外部同时内存权威

`run_task031_memory_forensics.py` 每 0.25 s 同时采样 live MPI ranks 的 RSS sum、MPI process tree、cgroup current/peak、线程/CPU 和 WSL swap，并从 runner 的 stage JSONL 标注峰值阶段。它不把各 rank 在不同时刻的历史最大值相加。h2 额外强制 `--unlock-h2`、9.5 GiB warning 与 11 GiB controlled termination。

### Assembled-F-free public MPC form action

`mpc_form_action.py` 把 active vector 写入 MPC Function，backsubstitute 后通过 public `dolfinx_mpc.assemble_vector(ufl.action(...))` 计算 action，并显式恢复 MPC slave unit rows。最初遗漏 unit rows 时误差约 0.0263；修复后 h5/h3/h2 action error 都 `<1e-15`。`CondensedDtnOperator` 接受 external fine action，并通过 `require_f/release_f` 只让 assembled `F` 存活到 coarse/slab setup 完成；solve ledger 中没有 `F`。该路径只是 solve 阶段 assembled-F-free，不是缓存优化的低层 element-kernel matrix-free；每次 apply 仍发生 Function/MPC/form assembly 与通信。

### Slab、lifecycle 与合法性

overlap0.125 缩小 factor；compact lifecycle 在 RTA 前释放 KSP/PC/factors/work vectors；exact SHA-256 fingerprints 只允许完全相同 factor 共享。PC certificate 用随机向量检查 linearity/determinism：Task030 adaptive local GMRES PC 的线性误差为 `2.374308e-2`，因此普通 GMRES fail closed，必须保留 flexible Krylov。固定 Richardson 虽达到 `3.611e-15`，却失去收敛能力。

## 44.5 实验漏斗与负结果

| lane | 关键观测 | 决定 |
|---|---|---|
| FGMRES50 | worker RSS -1.89%，residual/time 更差 | `<3%` 停止 |
| ordinary GMRES | PC linearity `2.374308e-2` | 算法不合法，fail closed |
| fixed Richardson | linear，但 200 步 residual 0.7703 | numeric negative |
| 16 slab overlap0.125 | factor nnz -19.59%，residual 略差 | weak positive，进入组合 |
| 20 slab overlap0.125 | factor/RSS/residual 均差于16 slab | 停止 |
| boundary Jacobi1 | stored factor -9.95%，residual 恶化约13.7x | 停止 |
| exact factor dedup | 16/16 fingerprints unique | 无可共享 factor，停止 |
| assembled-F-free public form action | action 等价，200步 RSS约 -2–3%，时间3.18x | 内存优先保留 |

h3 第一次在 max_it1600 时 full residual 为 `5.490e-6`，严格判负；任务书允许 h5/h3 上限 5000 且不以高迭代数自动判失败。同一配置提高安全上限后在 1994 步通过，残差历史与第一次共同点逐位一致，证明是延长同一过程而非参数漂移。

## 44.6 h5/h3/h2 正式结果

| h | DoF | iterations | full residual | simultaneous worker peak | cgroup peak | solve/total s |
|---:|---:|---:|---:|---:|---:|---:|
| 5 | 44,698 | 1,157 | `9.959903e-7` | 1.619598 GiB | 1.056248 GiB | 350.851 / 374.342 |
| 3 | 198,438 | 1,994 | `9.973853e-7` | 3.474346 GiB | 2.899216 GiB | 2311.581 / 2370.351 |
| 2 | 615,108 | 1,977 | `9.998454e-7` | 7.897675 GiB | 7.424026 GiB | 11982.581 / 12173.086 |

三份 run 都来自 clean SHA `45a0fc6e...`、同一 image digest 与 MPI4。h3 external simultaneous peak 3.474346 GiB，通过 3.50 GiB 绝对线；相对 Task030 历史口径的观察降幅 8.399% 只作辅助。h2 external simultaneous / legacy internal peak 为 7.897675 / 8.176441 GiB，相对 Task030 历史值的辅助对照约降 15.8% / 12.8%；保守工程结论约 8.0–8.2 GiB。h2 通过 strong `<=8.0 GiB` external Gate，但未达到 stretch `<=7.0 GiB`。峰值在 `outer_krylov_solve`；coarse operator ready 7.867531 GiB，solver release/RTA 约 6.50 GiB。swap in/out=0，watchdog 未触发。

## 44.7 h2 预测与条件解锁

h5/h3 DoF–RSS 仿射外推给出 8.501130 GiB；Task030 h2 按 h3 实测比例迁移给出 8.587349 GiB。以 h5 最弱的 4.032% 收益应用到 Task030 h2 后再加 5% 余量，保守上界为 9.446530 GiB。三者全部过 Gate，才解锁唯一 h2 candidate。实测 7.897675 GiB 低于两套中心预测和上界；没有运行第二个 h2，因为首个已经 `<8.0 GiB`，也没有机制不同且预测 `<=7.5 GiB` 的候选。

## 44.8 数值正确性与 R/T/A

h5/h3/h2 的 reported、condensed true 和 full augmented true residual 一致。official R/T/A 为：

```text
h5 = 0.089021602568 / 0.442588275323 / 0.468390124569
h3 = 0.004613031629 / 0.583653357934 / 0.411733610310
h2 = 0.001342934186 / 0.599213235569 / 0.399443835926
```

energy closure 分别为 `2.460e-9 / -1.270e-10 / 5.682e-9`；对 direct 最大 delta 为 `6.162e-9 / 1.104e-9 / 6.125e-9`，都远低于 `1e-6`。这排除了仅 reported residual 收敛或 public form-action wrapper 改变物理解的可能。

## 44.9 结果解释

Task031 的收益不是来自单一“神奇 PC”。solve 阶段不常驻 assembled `F`、slab factor 规模与 solver/RTA 对象重叠是三个正交来源；restart50 的 payload 模型下降没有转化为足够的 full-process peak。相对 Task030 历史口径的 h5/h3/h2 百分比只能作为趋势证据，不能包装成严格同 sampler 的精确 A/B。

代价同样清晰：public form action 每次需要 MPC field 写入/backsub/assembly，h2 约 13,960 次 form apply，使 solve 达 11982.581 s，是 Task030 的约 5.01x。迭代数只增加约 5.55%，每步平均成本约增加 4.74x；一次性 `release_f()` 不是主要耗时。因此最终分类必须同时包含 strong memory success 和 slow-but-memory-efficient，不能只报道 7.898 GiB。

## 44.10 最终决策与合并边界

建议 review 后选择性合并 external sampler/watchdog、public MPC form action、safe condensed lifecycle、PC certificate、object ledger、测试、Case070 与文档。最终 candidate 只作为显式 opt-in memory-first profile；ordinary default 不变。

不得提升 fixed Richardson、boundary Jacobi、restart50、20-slab 或 approximate factor sharing。16 个 factor 没有 exact duplicate，因此不存在 dedup implementation。不能把 release 后 current RSS 下降冒充 peak success，也不能把冻结 target 的验证写成任意参数数学保证。

## 44.11 局限与下一步因果关系

当前证据只覆盖一个物理/RHS、MPI4 partition 与当前 image；运行方差、其他机器、参数扫描、多 RHS 和跨 PETSc 版本未验证。Task030 与 Task031 的 memory sampler 口径并非完全一致，故所有轻量 record 同时保留 external simultaneous、cgroup 与 legacy internal 值。

下一步若追求平衡，应优化 public form action 的缓存/批量路径，或设计固定线性且有足够平滑能力的 polynomial/Chebyshev local action；不应继续压 restart 或近似共享 factor，因为已有负证据。新路线必须从 h5 action equivalence、PC legality、true residual 与 simultaneous peak 联合 Gate 开始，再进入 h3/h2。

## 44.12 证据入口

- [Task031 task](task031_compact_physical_slab_memory_optimization/task.md)
- [Task031 outcomes](task031_compact_physical_slab_memory_optimization/outcomes/summary.md)
- [迭代求解器端口与合法性](iterative_solver_ports.md)
- [Case070](../benchmarks/cases/070_compact_physical_slab_memory_optimization/README.md)
- [h2 prediction](task031_compact_physical_slab_memory_optimization/outcomes/h2_memory_prediction.md)
- [negative results](task031_compact_physical_slab_memory_optimization/outcomes/negative_results.md)
- [matrix-free validation](task031_compact_physical_slab_memory_optimization/outcomes/matrix_free_validation.md)
- [iterative theory](../notes/theory/iterative_solver_and_preconditioner.md)
- [workstation runtime walkthrough](../notes/reference/code_walkthrough/33_workstation_fgmres_runtime.md)

---

# 45. Task031 后的当前推荐顺序

```text
1. 完成 Task031 分支 full tests、Case070 checker 与 clean-tree 审计；
2. 推送分支，等待 ChatGPT Task031 review；
3. 按 review 修正，不静默改变 ordinary default；
4. 用户明确批准后才选择性合并 master；
5. 后续若继续，优先降低 public form-action apply 时间，而不是重复已失败的 restart/dedup 路线。
```

# 46. 当前一句话状态（Task031）

> Task031 在 clean MPI4 frozen target 上以 assembled-F-free public MPC form action、16 slabs overlap0.125 与 compact lifecycle 实现 h5/h3/h2 全部 true-residual + official-RTA 通过；h2 1977 步，external simultaneous / legacy internal 为 7.897675 / 8.176441 GiB，保守工程范围约 8.0–8.2 GiB，达到 `strong_memory_success_slow_but_memory_efficient`，但 solve 约 5.01x，ordinary default 未改变；Review V1 数值/内存通过，文档加固见 response_v1。
