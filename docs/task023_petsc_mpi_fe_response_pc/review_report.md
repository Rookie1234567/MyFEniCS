# REVIEW REPORT 20260710：Task023 PETSc/MPI-safe FE-response PC

## 1. 审查结论

Task023 审查通过，但结论必须分为两个层次。

### 已经完成的工程突破

```text
目标模型 p=2 h=5 已经完成 PETSc/MPI-safe FE-response / Schur 求解闭环：
true residual 达到 production-like；
reduced/augmented solution 能回填到 H(curl) Function；
official dtn_port_modal_amplitudes + A_volume R/T/A 与 direct reference 一致到约 1e-12。
```

因此，h=5 已经不再只是 research proof-of-concept。它可以进入下一任务的 opt-in engineering solver 固化阶段。

### 尚未解决的核心问题

```text
目标模型 p=2 h=2 仍没有 minimum useful iterative result。
plain ASM/ILU FE response 已被数据否定；
ASM/local LU 和 LU/MUMPS 在当前资源下进入时间边界；
低内存、足够准确地近似 A_FE^{-1} 仍是唯一核心瓶颈。
```

因此，Task023 不能宣称 h=2 production solver 完成，也不能把任何新 profile 设为默认求解器。

---

## 2. Physical model 审查

本轮继续使用 task008 目标模型：

```text
domain = 50 x 25 x 140 nm
period = 50 x 25 nm
grating = 17 x 25 x 120 nm
substrate / top air = 10 nm / 10 nm
theta_from_z = 80 deg
phi = 0 deg
polarization = s, E along y
material n = 0.999002304859 + 0.00182649365j
boundary = double Floquet x/y + auxiliary DtN port
```

没有退回 default100 算法沙盒。

---

## 3. h=5 PETSc/MPI engineering closure

Task023 在 h=5 上得到：

| profile | true residual | peak RSS | 判断 |
|---|---:|---:|---|
| PETSc selected-mode FE response，ASM + local LU | `9.326e-7` | `1.557 GB` | production-like |
| PETSc full 80-aux Schur one apply，ASM + local LU | `2.493e-10` | `1.701 GB` | production-like |
| PETSc FieldSplit/Schur + FE LU | `3.797e-9` | `1.351 GB` | production-like |

这证明 Task021 的成功不是 SciPy 特有现象。FE-response + auxiliary Schur 的数学结构能够迁移到 PETSc/MPI 框架。

### Official R/T/A

| source | residual | R | T | A_volume | closure |
|---|---:|---:|---:|---:|---:|
| direct reference | `2.764e-11` | `0.089021602936` | `0.442588278657` | `0.468390118406` | `0.999999999999` |
| best PETSc FE-response | `2.493e-10` | `0.089021602936` | `0.442588278658` | `0.468390118407` | `1.000000000001` |
| FieldSplit FE-LU | `3.797e-9` | `0.089021602935` | `0.442588278668` | `0.468390118400` | `1.000000000003` |

审查判断：

```text
h=5 的线性 residual、field reconstruction、MPC backsubstitution、DtN modal power 和 volume absorption 已经闭环。
```

这部分应在 Task024 中固化为一个明确的 opt-in engineering profile，并建立回归测试。

---

## 4. FE response 质量审查

Task023 给出了一个非常重要的工程结论：

```text
FE response 不能只“有一个近似”，还必须足够准确且方向正确。
```

### ASM + local ILU

h=5 selected response：

```text
baseline residual = 0.230585
final residual = 0.281765
```

full auxiliary Schur one apply：

```text
residual ≈ 1.0
```

h=2 FieldSplit/Schur：

```text
residual = 0.989561
```

h=2 selected response：

```text
inner relative residual = 1.12672
one-shot residual = 1.54045
```

结论：

```text
plain ASM/ILU 不只是收敛慢，而是给出的 q_j ≈ -A_FE^{-1} C_j 质量不足，甚至会产生错误修正方向。
```

因此 plain ASM/ILU 不应继续作为 Task024 主线。

### ASM + local LU / FE LU

h=5 上 local LU/FE LU 能给出 production-like response，但 h=2 上：

```text
FieldSplit ASM + local LU > 7200 s
selected response ASM + local LU > 3600 s
LU/MUMPS fallback > 7200 s
```

结论：

```text
LU 质量足够，但 h=2 资源成本开始接近直接法，不能作为最终低内存方案。
```

---

## 5. FieldSplit/Schur 审查

Task023 使用 PETSc `PCFieldSplit + Schur`，分块为：

```text
split 0 = FE block，索引 [0, n_FE)
split 1 = 80 个 DtN auxiliary unknowns
```

FieldSplit 的作用是可靠组织：

```text
A_FE, C, D, A_aux
```

之间的分块耦合，并在 MPI 下处理 ownership 和索引。它不是 `A_FE^{-1}` 的具体实现，FE inner solver 仍需要单独选择。

审查判断：

```text
FieldSplit/Schur 框架应保留并作为后续工程架构，不再回到手写 full Python PCShell 主路径。
```

Task023 已修复 FieldSplit IS / MPI ownership 问题，h=2 的失败不再归因于 ownership。

---

## 6. AMS/HX 路线审查

Task023 尝试在 complex FE block 上直接挂 hypre AMS，但 setup 失败，原因是缺少 AMS 所需的：

```text
coordinate vectors
edge constant vectors
discrete gradient / interpolation data
```

这不是 AMS/HX 数值失败，而是接口与辅助空间数据没有正确建立。

历史上 Task013 的 real-split same-H1 AMS/HX 在 FE-only p=2 h=5 上已有正信号：

```text
约 310 steps 达到 1e-6
RSS 约 1.323 GB
```

而现在 AMS/HX 的职责更窄：

```text
不再独自预条件完整 FE + DtN coupled system；
只用于计算 selected RHS 的 filtered FE response：
q_j ≈ -A_FE^{-1} C_j。
```

审查判断：

```text
real-split same-H1 AMS/HX FE-response service 是 Task024 第一突破主线。
complex AMS 直接挂载路径暂停。
```

---

## 7. COMSOL GMG 参考的工程意义

用户提供的 COMSOL 迭代求解器扫描显示：

```text
direct MUMPS: peak ≈ 22.989 GB, time ≈ 282 s
TFQMR + right GMG: peak ≈ 9.01 GB, time ≈ 800 s
GMRES + right GMG restart 100: peak ≈ 11.699 GB, time ≈ 417 s
```

成功的 GMG 不是单一 ILU，而是：

```text
5-level geometric multigrid
V-cycle
pre-smoothing: SOR + Vanka
post-smoothing: SOR + SOR Vector
coarse solve: MUMPS direct
```

单独 SOR、Vanka、Jacobi、ILU、AMS、SAI 大多失败，但放入多层框架后可成功。

审查判断：

```text
COMSOL 结果证明“多层 FE inverse 近似 + 局部平滑 + 小粗层直接解”值得作为 Task024 第二工程路线。
```

但自研 GMG 的 H(curl) 跨层转移和 patch smoother 工作量较大。为尽快得到可用结果，Task024 只先做 gated GMG-lite FE-response prototype，不允许一开始就无限扩展完整 GMG 框架。

---

## 8. Matrix-free 审查

Task023 的结论保持不变：

```text
h=5 显式 AIJ 足够便宜；
h=2 显式 AIJ 仍能承受，真正瓶颈是 inner PC；
h=1.5 预计显式 matrix/FieldSplit setup 超过当前 14 GB 配额，届时 matrix-free 将成为必要支撑。
```

matrix-free 只提供 `A_FE x`，不直接提供 `A_FE^{-1} r`。

审查判断：

```text
matrix-free 继续作为 MatShell / fine-level action 基础设施；
不作为 Task024 独立 solver 主线；
只有和 AMS/HX、GMG 或其他强 inner PC 结合才有价值。
```

---

## 9. Task023 Gate

| gate | decision |
|---|---|
| h=5 residual | pass，`2.493e-10` |
| h=5 official R/T/A | pass，与 direct 差异约 `1e-12` |
| h=2 minimum useful | fail，最好 `0.9896` |
| h=1.5 | not run |
| production default | no |

最终判断：

```text
h=5 已具备 opt-in engineering candidate；
h=2 低内存 production gate 未通过。
```

---

## 10. Merge recommendation

建议：

```text
merge_docs: yes, after review
merge_research_runner: optional
merge_h5_opt_in_profile: only after Task024 regression hardening
production_default_change: no
```

不建议合并为默认的内容：

```text
plain ASM/ILU profile
complex AMS direct attachment
h=2 local LU/MUMPS timeout profiles
matrix-free-only profile
```

---

## 11. 下一步：Task024

Task024 必须以“尽快实现一个可用、可推进的工程迭代求解法”为目标，采用明确决策漏斗：

```text
Track A：立即固化 h=5 PETSc FieldSplit/Schur 工程求解器；
Track B：集中实现 real-split same-H1 AMS/HX FE-response service，突破 h=2；
Track C：若 AMS/HX 在早期 gate 失败，立即启动 COMSOL-inspired GMG-lite FE-response；
Fallback：保留 selected-response LU/MUMPS/BLR cache 作为 reference，不包装成低内存最终方案。
```

不再进行无边界的 profile 全扫。

---

## 12. 最终审查结论

Task023 完成了 h=5 PETSc/MPI FE-response + Schur + official R/T/A 的完整工程闭环，这是重要成功；同时也用数据否定了 plain ASM/ILU 作为 h=2 FE response 的主线。当前唯一核心问题是低内存、足够准确地近似 `A_FE^{-1}`。Task024 应先把 h=5 成果固化为可用 opt-in solver，然后以 real-split same-H1 AMS/HX FE-response 为第一突破路线，以 COMSOL-inspired GMG-lite FE-response 为 gated 第二路线，尽快让 h=2 达到 minimum useful 并推进到 strong gate。
