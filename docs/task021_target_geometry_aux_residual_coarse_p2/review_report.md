# REVIEW REPORT 20260709：Task021 target-geometry p=2 DtN auxiliary residual-aware coarse correction

## 1. 审查结论

Task021 审查通过，而且是当前低内存迭代求解路线中的重大突破。

本轮已切回 task008 目标物理模型：

```text
domain = 50 x 25 x 140 nm
period = 50 x 25 nm
grating = 17 x 25 x 120 nm
substrate = 10 nm
top air above grating = 10 nm
air_height = 130 nm
theta_from_z = 80 deg, phi = 0 deg
polarization = s, E along y
material n = 0.999002304859 + 0.00182649365j
DtN auxiliary modes = top 40 + bottom 40 = 80
```

核心结论：

```text
target p=2 h=5 reduced Stage4 linear system 已在 research runner 中达到 production-like true residual。
```

但必须强调：

```text
当前结果仍是 serial SciPy / SPILU / SPLU research prototype；
还不是 PETSc/MPI production PC；
还没有完成 p=2 h=2 preflight；
还没有输出 converged iterative official R/T/A validation。
```

---

## 2. p=1 与 p=2 状态

### p=1

目标几何 `p=1 h=5` baseline：

```text
solver = GCROT(m,k) + Jacobi
true residual = 4.520105e-5
gate = strong
```

因此 p=1 在本轮达到 strong，但没有达到 `1e-6` production-like。p=1 可作为低阶 solver prototype 和 sanity check，但不是最终物理精度结论。

### p=2

目标几何 `p=2 h=5` baseline：

```text
solver = GCROT(m,k) + Jacobi
true residual = 2.025767e-1
gate = fail
```

经过 DtN auxiliary residual-aware coarse + FE response / Schur correction 后，最佳结果：

```text
exact FE-block Schur one apply residual = 8.155352e-12
SPILU block Schur PC residual           = 2.430285e-7
SPILU coupled PC m=1 residual           = 9.865457e-7
```

因此 p=2 h=5 已经越过 production-like gate。下一步允许做 p=2 h=2 preflight。

---

## 3. 关键物理发现

目标模型 p=2 h=5 的主导慢模态是：

```text
local aux index = 38
global row = 44736
side = top
Rayleigh order = (0, 0)
polarization = s
propagating = true
aux residual abs = 5.405846e-1
fraction of aux residual norm = 0.999995
fraction of total residual norm = 0.391828
```

这说明 residual selector 是稳定且物理可解释的：当前主要卡在 top-side zero-order s-polarized DtN auxiliary mode。

审查判断：

```text
mode selector 成功；
aux-only correction 失败；
必须把 auxiliary mode 与 FE response 耦合起来。
```

---

## 4. 为什么这是突破

过去几轮已经证明：

```text
fixed top_bottom_y sampled Schur 在 p=2 h=5 不迁移；
aux-only correction 只能略微改善；
diag FE response 太弱。
```

Task021 证明了：

```text
只要选中正确 DtN auxiliary slow mode，并给它配上足够质量的 FE response，p=2 h=5 可以被解到 1e-6 以下。
```

结果对比：

| 方法 | residual | 判断 |
|---|---:|---|
| Jacobi baseline | `2.025767e-1` | fail |
| aux-only one-shot / PC | `1.921949e-1` | fail |
| diag FE response coupled PC | `1.838447e-1` | fail |
| SPILU FE response coupled PC, m=1 | `9.865457e-7` | production-like |
| SPILU FE response coupled PC, m=2 | `9.412760e-7` | production-like |
| SPILU FE response coupled PC, m=4 | `9.134024e-7` | production-like |
| SPILU block Schur PC, full aux | `2.430285e-7` | production-like |
| exact FE-block Schur one apply | `8.155352e-12` | research upper bound |

这说明数学结构是正确的：真正有效的是 block Schur / coupled FE response，而不是单独修 auxiliary unknown。

---

## 5. 算法审查

本轮算法层次如下：

```text
outer Krylov solver: GCROT(m,k)
weak baseline PC: Jacobi
mode selector: residual-dominant DtN auxiliary mode selector
weak response: diagonal FE response
successful response: SPILU FE response
upper-bound response: exact SPLU FE-block solve
successful structure: coupled auxiliary + FE response / FE-block Schur PC
```

重要区分：

```text
SPILU/SPLU 是 FE block response 的实现方式；
Schur complement 是 FE-aux coupling 的数学结构；
GCROT(m,k) 仍是外层 Krylov 迭代器；
突破主要来自预条件器，而不是单纯换外层 Krylov。
```

---

## 6. 工程风险与限制

仍需解决：

```text
1. serial SciPy runner 需要迁移为 PETSc PCShell / MatShell / MPI-safe implementation；
2. SPILU fill nnz 约 4.48e7，h=2 时内存和 fill-in 风险需要 preflight；
3. exact FE-block Schur 是研究上界，不是低内存 production 策略；
4. m>=8 非单调甚至变差，coarse basis 需要过滤、正交化或稳定筛选；
5. 本轮没有输出 converged iterative official R/T/A；下一步必须补。
```

---

## 7. Merge recommendation

建议：

```text
merge_docs: yes, after review
merge_code: no by default
merge_research_runner: optional, opt-in only
production_default_change: no
```

可合并文档：

```text
docs/task021_target_geometry_aux_residual_coarse_p2/outcomes/*
docs/task021_target_geometry_aux_residual_coarse_p2/review_report.md
notes/theory/task021_dtn_auxiliary_schur_fe_response.md
```

代码建议：

```text
src/studies/run_task021_target_aux_coarse.py 可作为 opt-in research runner 审查后保留；
不要接入 ordinary Stage4 default solver；
postprocess.py 的 PyVista lazy import 可单独审查后合并。
```

---

## 8. 下一步 Task022

Task022 应巩固这个突破，而不是重新探索无关路线。

建议主线：

```text
target-geometry p=2 h=2 preflight + PETSc/MPI-safe Schur/FE-response PC design
```

优先级：

```text
1. p=2 h=5 重复性确认：SPILU m=1、SPILU block Schur、exact Schur upper bound。
2. p=2 h=2 resource preflight：先 assemble/preconditioner setup，不直接追 full validation。
3. 选择两个生产化候选：SPILU coupled PC m=1 和 SPILU block Schur PC。
4. 开始设计 PETSc PCShell/MatShell 接口，把 serial SciPy prototype 迁移为可集成的 PC。
5. 在 converged p=2 h=5 解上输出 official R/T/A，与 direct/reference 对照。
```

进入 p=2 h=2 的条件：

```text
p=2 h=5 production-like 已满足；
preflight 不应直接跳 h=1.5 或 h=1；
h=2 先验证 memory、setup、residual trend 和 failure boundary。
```

---

## 9. 最终审查判断

Task021 是目前最重要的突破：它把 p=2 h=5 从 baseline residual `2.025767e-1` 推进到 `1e-6` 以下，证明目标几何上的 DtN auxiliary residual-aware FE-response / Schur 预条件结构是正确方向。下一步不应再回到 fixed sampled-Schur 或普通 profile 微调，而应巩固该成果：做 p=2 h=2 preflight、PETSc/MPI-safe PC 迁移和 official R/T/A 验证。
