# REVIEW REPORT 20260709：Task022 p=2 h=2 Schur/FE-response PC preflight

## 1. 审查结论

Task022 审查通过。它没有把 p=2 h=2 直接求通，但非常清楚地定位了下一阶段瓶颈。

核心结论：

```text
Task021 的 Schur/FE-response 数学结构在 h=5 稳定复现；
h=2 的主导 DtN auxiliary mode 仍然是 top (0,0) s；
h=2 matrix/CSR 可以完成；
h=2 失败点集中在 serial SciPy SPILU FE block factorization；
matrix-free FE action 已验证正确，可作为 PETSc MatShell 支撑层；
下一步必须转向 PETSc/MPI-safe FE response PC，而不是继续调 SciPy spilu 参数。
```

因此，Task022 的负结果不是路线失败，而是工程实现边界被定位：

```text
真正要解决的问题是低内存、可并行地近似 A_FE^{-1}。
```

---

## 2. h=5 reproducibility 审查

Task022 成功复现 Task021 的 h=5 breakthrough：

| profile | true residual | gate | peak total RSS GB |
|---|---:|---|---:|
| baseline GCROT + Jacobi | `2.109624e-1` | fail | `0.676` |
| SPILU coupled PC m=1 | `9.865457e-7` | production-like | `2.281` |
| SPILU block Schur PC | `2.430285e-7` | production-like | `2.354` |
| exact FE-block Schur PC | `8.183739e-12` | production-like | `4.194` |
| exact FE-block Schur one apply | `8.155352e-12` | production-like | `4.194` |

审查判断：

```text
h=5 breakthrough 不是偶然；
Schur/FE-response 结构成立；
SPILU coupled m=1 和 SPILU block Schur 都是有效 proof-of-concept。
```

---

## 3. h=2 resource preflight 审查

目标模型 p=2 h=2：

```text
rows = 615188
nnz = 65448472
n_FE = 615108
n_aux = 80
estimated AIJ = 1250.68 MB
assembly time = 297.81 s
CSR conversion = 2.36 s
CSR delta RSS = 1.219 GB
peak total RSS = 6.277 GB
```

审查判断：

```text
h=2 matrix assembly 和 CSR conversion 本身可以完成；
问题不是矩阵建不出来；
真正的瓶颈是 FE inverse / factorization。
```

---

## 4. h=2 mode selector 审查

h=2 主导 auxiliary mode：

```text
local aux index = 38
global row = 615146
side = top
Rayleigh order = (0,0)
polarization = s
aux residual abs = 1.781991e-1
aux norm fraction = 0.999792
total fraction = 0.140165
```

审查判断：

```text
h=2 的主导 mode 与 h=5 相同，仍为 top (0,0) s；
mode selector 具有网格鲁棒性；
h=2 失败不是物理模式识别错误。
```

---

## 5. h=2 FE factorization failure 审查

Candidate A / B 均卡在 FE block factorization。

| candidate | FE response | status | 原因 |
|---|---|---|---|
| coupled m=1 | SPILU drop=1e-3 fill=12 | blocked | estimated total RSS `27.79 GB`，超过 12 GB guard |
| block Schur | SPILU drop=1e-3 fill=12 | blocked | 同上 |
| coupled m=1 | SPILU drop=1e-1 fill=1.05 | timed out | 7200 s 无 factor 返回 |
| block Schur | SPILU drop=1e-1 fill=1.05 | timed out | 同上 |

审查判断：

```text
继续调 serial SciPy spilu 参数没有价值；
fill 大会爆内存，fill 小会超时或质量不足；
需要 PETSc/MPI-safe FE inverse strategy。
```

---

## 6. Matrix-free 审查

Task022 验证了 target box p=2 h=10 的 FE weak-form matrix-free action：

```text
relative action error = 6.034580e-16
peak total RSS = 0.207 GB
```

审查判断：

```text
matrix-free FE action 是可信的；
它应作为 PETSc MatShell / memory support layer 进入下一阶段；
但 matrix-free 只提供 A_FE x，不能自动提供 A_FE^{-1} r；
因此它不能直接让 exact Schur 或 SPILU factorization 变便宜。
```

换句话说：

```text
Schur/FE-response 解决“怎么收敛”；
matrix-free 解决“怎么少存矩阵”；
真正缺口是低内存近似 A_FE^{-1}。
```

---

## 7. Official R/T/A 审查

Task022 没有输出 h=5 iterative official R/T/A。

原因：

```text
current SciPy research runner verifies reduced linear residual but does not reconstruct field Function for official dtn_port_modal_amplitudes + A_volume postprocessing。
```

审查判断：

```text
这是下一步 blocking item。
线性 residual 成功后，必须把 reduced vector 回填到 Stage4 field，再调用现有 official R/T/A pipeline。
```

---

## 8. 下一步路线判断

Task022 后，主问题已经明确：

```text
如何低内存、可并行、可工程化地近似 A_FE^{-1}。
```

这不是单一路线能直接保证解决的问题，因此 Task023 应系统尝试多种 FE response inner PC，但必须围绕同一个 Schur/FE-response framework，不再回到普通 profile 微调。

值得进入 Task023 的路线：

```text
1. PETSc PCShell / MatShell framework：必须做，作为工程化载体。
2. Reduced vector reconstruction + h=5 official R/T/A：必须做，闭合物理后处理链路。
3. PETSc ASM/GASM + local ILU/LU：第一批低内存 FE inverse 候选。
4. AMS/HX-smoothed FE response：重点路线，因为它与 H(curl) FE block 物理结构匹配。
5. MUMPS/BLR inner solve：强对照 / fallback，不能包装成低内存最终方案。
6. Matrix-free FE action + inner Krylov：作为 h=2/h<2 memory support and MatShell infrastructure。
7. Hybrid route：AMS/HX smoother + small auxiliary Schur coarse mode，测试二者是否互补。
```

---

## 9. Merge recommendation

建议：

```text
merge_docs: yes, after review
merge_code: no by default
merge_research_runner: optional, opt-in only
production_default_change: no
```

不得合并为 production 默认的内容：

```text
serial SciPy SPILU h=2 path
exact FE-block Schur as low-memory production method
unvalidated PETSc PCShell
unvalidated matrix-free-only solver
```

可以作为文档证据保留：

```text
docs/task022_p2_h2_schur_pc_preflight/outcomes/*
docs/task022_p2_h2_schur_pc_preflight/review_report.md
```

---

## 10. 最终审查判断

Task022 成功巩固了 Task021 的突破，并证明了 h=2 失败的真正原因：不是 Schur/FE-response 数学结构，不是 DtN mode selector，也不是 assembled matrix，而是 serial SciPy SPILU 无法低内存、可控地近似 `A_FE^{-1}`。下一步 Task023 必须进入 PETSc/MPI-safe FE response PC 体系，系统比较 ASM/ILU、AMS/HX-smoothed response、MUMPS/BLR inner solve、matrix-free MatShell + inner Krylov 等路线，并优先完成 h=5 official R/T/A 回填验证。
