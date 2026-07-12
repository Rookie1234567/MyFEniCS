# REVIEW REPORT：Task025 parameter-robust multilevel H(curl) preconditioner

## 1. 审查状态

```text
review_status = partial_pass_research
full_auxiliary_architecture = pass
h5_strong_gate = pass
h2_memory_gate = pass
h2_strong_gate = fail
h2_production_gate = fail
parameter_robustness_gate = not_run
production_default_change = no
```

Task025 没有发现足以推翻主要数值结论的明显错误。现有 outcomes、残差历史、资源记录和实现说明相互一致，可以接受以下核心事实：

```text
1. 完整 80-auxiliary cached Schur 架构已经实际跑通；
2. h=5 达到 strong residual，并完成 official R/T/A；
3. h=2 在 14 GB 配额内完成完整 augmented solve，真残差为 0.118475；
4. h=2 尚未达到 strong 或 production-level；
5. 当前主要误差来自 FE response columns Q_j 的质量，而不是 80 x 80 Schur 求解本身。
```

因此，Task025 应定性为：

```text
完整 augmented / full-aux Schur 架构取得实质突破，
但参数鲁棒、多层 H(curl)、production-level 求解器目标未完成。
```

---

## 2. 物理模型与求解对象审查

本轮继续使用目标模型：

```text
domain = 50 x 25 x 140 nm
period = 50 x 25 nm
grating = 17 x 25 x 120 nm
substrate / top air = 10 / 10 nm
theta_from_z = 80 deg
phi = 0 deg
polarization = s
reference wavelength = 13.5 nm
boundary = double Floquet x/y + 80-mode auxiliary DtN
```

没有退回 default100 算法沙盒。

本轮最终求解的是完整 augmented system：

```math
\begin{bmatrix}
A_{FE} & C \\
D & A_{aux}
\end{bmatrix}
\begin{bmatrix}
x_{FE} \\
x_{aux}
\end{bmatrix}
=
\begin{bmatrix}
b_{FE} \\
b_{aux}
\end{bmatrix}.
```

与 Task024 的 m=1 reduced approximation 不同，Task025 已经处理全部 80 个 auxiliary unknown，并构造：

```math
Q \approx A_{FE}^{-1}C,
\qquad
\widetilde S = A_{aux} - DQ.
```

这是 Task025 最重要的结构性进展。

---

## 3. 最终有效求解器结构

本轮唯一获得完整 full-aux 正结果的结构为：

```text
PETSc FGMRES
+ original augmented operator
+ shifted FE preconditioning operator
  A_FE - i beta |diag(A_FE)|
+ distributed ASM(restrict) / local ILU(1)
+ cached 80 FE-response columns Q
+ explicit 80 x 80 Schur
+ Schur LU
```

一次 PC apply 的主要步骤为：

```text
1. 近似 FE solve；
2. 计算 D*u；
3. 解 80 x 80 Schur；
4. 应用 Q*a 完成 FE/aux correction。
```

该设计比反复嵌套 FieldSplit FE solves 更适合当前问题，因为 auxiliary 维度固定为 80，而 FE solve 昂贵。

审查判断：

```text
cached full-aux Schur architecture = mathematically and computationally justified
```

---

## 4. h=5 结果审查

Task025 cached-Schur h=5：

```text
true residual = 5.338896e-6
outer iterations = 200
peak RSS = about 1.894 GB
```

official R/T/A：

```text
R = 0.0890283523
T = 0.4425611881
A_volume = 0.4683744816
R+T+A_volume = 0.9999640219
closure error = -3.5978e-5
```

直接法参考：

```text
R = 0.089021602936
T = 0.442588278657
A_volume = 0.468390118406
```

审查判断：

```text
h5 strong gate = pass
h5 production-like gate = fail
```

原因：

```text
residual 仍高于 1e-6；
R/T/A 和 closure 仍有约 1e-5 量级误差。
```

因此 h=5 结果可以作为 strong research validation，但不能替代 Task023 中更高精度的 LU-based reference。

---

## 5. h=2 结果审查

最终 h=2 cached-Schur 结果：

```text
FE rows = 615108
Q columns = 80
Q nnz = 49208640
outer iterations = 100
true residual = 0.1184750954
peak RSS = 13.005966 GB
```

资源阶段：

```text
assembly = 114.8 s
Q setup = 393.7 s
Schur assembly/factor = 0.097 s
outer solve = 503.2 s
```

与历史结果比较：

| 方法 | 完整真残差 | 说明 |
|---|---:|---|
| Task023 plain FieldSplit ASM/ILU | `0.989561` | fail |
| Task024 m=1 reduced response | `0.158592` | 非完整 80-aux solve |
| Task025 full 80-aux cached Schur | `0.118475` | 当前最好完整 full-aux result |

审查判断：

```text
h2 memory gate = pass
h2 full-aux architecture gate = pass
h2 minimum signal = pass only as research progress
h2 strong gate = fail
h2 production gate = fail
```

虽然相对 Task023 plain FieldSplit 改善明显，但相对 Task024 最好残差仅约 1.34x，且预算与内存均更高。因此不能把 `0.118475` 称为工程可用或 production solver。

---

## 6. FE response column 质量审查

h=2 的 80 个 response columns 满足：

```math
A_{FE}Q_j \approx C_j,
```

但记录的相对残差范围为：

```text
minimum about 0.286
maximum about 0.541
```

这是当前完整 residual 平台的最主要来源。

Schur 本身只有 80 x 80，已经被精确 LU；因此当前瓶颈不是小 Schur，而是：

```text
Q 近似的 A_FE^{-1} C 精度不足。
```

审查判断：

```text
response_quality = insufficient_for_production
```

下一阶段的核心目标应明确为：

```text
在 14 GB 内把 max_j ||A_FE Q_j - C_j|| / ||C_j||
从约 0.54 降到 < 0.1，最好 < 0.03。
```

---

## 7. 吸收移位与 ASM/ILU 审查

本轮引入：

```math
A_{FE}^{shift} = A_{FE} - i\beta |\operatorname{diag}(A_{FE})|.
```

h=2 局部结果：

| local PC | beta | 50-step FE residual | RSS |
|---|---:|---:|---:|
| ASM/ILU0 | 1.0 | `0.26411` | 7.03 GB |
| ASM/ILU1 | 1.0 | `0.24076` | 8.56 GB |
| ASM/ILU2 | 0.5 | `0.23094` | 12.57 GB |

ILU2 相对 ILU1 仅改善约 4%，但几乎耗尽可用内存，无法再安全容纳 Q cache 与 outer Krylov 数据。

审查判断：

```text
ASM/ILU1 + absorption shift = reasonable current engineering compromise
ILU2 = reject under 14 GB cap
```

但 beta 在 h=5/h=2 分别使用 0.3/1.0，说明当前 shift 尚非参数鲁棒规则，而是网格相关调参。

---

## 8. patch smoother 审查

Task025 任务书要求 edge-star、vertex-star 或 element-star H(curl) patch。

实际实现为：

```text
MPI rank-owned overlapping ASM
+ local ILU0/1/2
```

这不是 topology-aware edge/vertex patch。

原因是当前裸 AIJ/export 路径没有保留：

```text
DMPlex topology
edge/vertex entity adjacency
Nedelec entity dof maps
orientation data
MPC reduced-to-full mapping
```

所以 PETSc PCPATCH 或自定义 H(curl) patch 无法从矩阵本身恢复。

审查判断：

```text
Stage B topology-aware H(curl) patch = not completed
```

这不是小问题，而是说明最初设想的物理型 fine smoother 尚未真正测试。

后续应在 DOLFINx mesh/FunctionSpace/DMPlex 生命周期仍存在时构造 patch，而不是只在导出的 AIJ 上开发。

---

## 9. 多层和 coarse space 审查

本轮测试：

```text
1. H(curl) -> H1 gradient auxiliary correction；
2. same-mesh p2 -> p1 Nedelec interpolation；
3. p1 rediscretized / Galerkin coarse operator；
4. y-invariant x-z Q1 -> 3D H(curl) coarse space；
5. ordinary / adaptive BDDC。
```

这些 transfer 或 partition-of-unity 检查通过，但没有捕获真实 selected/physical RHS 的主要慢误差。

尤其：

```text
general 3D H(curl) nonmatching h hierarchy = not implemented
```

因此本轮不能声称已经验证或否定完整 COMSOL-style h-GMG。

审查判断：

```text
p-transfer prototypes = valid negative evidence
true 3D h-GMG = not completed
COMSOL-style multilevel conclusion = still open
```

---

## 10. p1 AMS/HX 审查

p1 h=2 FE-only 结果：

```text
20 steps residual = 0.523
50 steps residual = 0.414
peak RSS = 2.154 GB
```

接入 p2->p1 两层结构后，selected response cancellation 约为：

```text
0.674
```

说明当前 p1 AMS/HX coarse correction 未形成有效的低频修正。

但此结果只能否定当前组合：

```text
same-mesh p2->p1 + current p1 operator + current AMS setup
```

不能推广为所有 low-order refined、shifted AMS 或真正 h-coarsened AMS 路线均失败。

---

## 11. Q cache 与内存审查

h=2 内存主要构成为：

```text
assembled augmented/runtime about 7.37 GB
shifted ASM/ILU1 state about 8.56 GB cumulative stage
Q cache increment about 1.18 GB
outer Krylov/temporaries about 3.27 GB
peak about 13.006 GB
```

当前只剩约 1 GB 安全余量。

因此下一步若想提高 FE inner PC 强度，必须先释放内存。

建议优先探索：

```text
randomized SVD / rank-revealing QR compression of Q
按 DQ 和 full residual contribution 选择 response subspace
FGMRES restart / Krylov memory guard
按列 residual 自适应 refinement
```

注意：不能只按 `||Q_j||` 选择列，应按其对 Schur 和完整 residual 的影响选择。

---

## 12. 多 RHS 与参数复用审查

当前 80 列 Q 逐列计算，h=2 Q setup 约 394 s。

所有列共享同一个 A_FE，因此下一阶段应考虑：

```text
block Krylov / block FGMRES
recycled Krylov across response columns
shared search space
residual-driven selective refinement
```

参数扫描时，应复用上一角度/波长的 Q：

```text
Q_old 作为 Q_new 的初值；
只更新 residual 超阈值的列；
mesh/MPI partition/mode list 改变时强制 cache invalidation。
```

当前只实现进程内 Q/S 复用，没有实现磁盘 cache 或跨参数低秩更新。

---

## 13. 参数鲁棒性审查

角度/波长资格矩阵被 reference h=2 gate 阻塞：

```text
75 deg = not run
85 deg = not run
13.0 nm = not run
14.0 nm = not run
```

因此目前没有证据证明当前 PC 对：

```text
mesh refinement
angle variation
wavelength variation
material dispersion
```

具有鲁棒性。

而 beta 随 h 改变，也进一步说明当前规则尚未参数化。

审查判断：

```text
parameter_robustness = not demonstrated
```

---

## 14. Krylov recycling 审查

当前 PETSc build 没有可用的 GCRO-DR/HPDDM。LGMRES 在现有实验中没有给出明显收益。

本轮最有效的复用对象是：

```text
Q response cache
80 x 80 Schur factor
```

而不是单纯复用外层 Krylov 向量。

这与当前问题结构一致，但未来在角度/波长连续扫描中仍值得重新测试真正 GCRO-DR 或 recycled block Krylov。

---

## 15. Gate 决策

| Gate | 状态 |
|---|---|
| 完整 80-aux augmented architecture | pass |
| h=5 strong | pass |
| h=5 production-like | fail |
| h=2 memory < 14 GB | pass |
| h=2 minimum research signal | pass |
| h=2 strong <= 1e-2 | fail |
| h=2 production <= 1e-6 | fail |
| h=2 official R/T/A | blocked |
| topology-aware H(curl) patch | not completed |
| true 3D h-GMG | not completed |
| angle/wavelength robustness | not run |
| production default | no |

---

## 16. Merge recommendation

建议选择性合并：

```text
Task025 docs and lightweight outcomes
opt-in Task025 research runner
shifted FE sub-operator support
complex p-transfer fixes
p1 AMS degree fixes
small Schur / response diagnostics utilities
```

暂不合并为普通 solver API 或 production 默认：

```text
cached-Schur profile
h=2 tuned beta/ILU parameters
adaptive BDDC
custom 2D coarse prototypes
unconverged h=2 R/T/A path
```

大型 Q/matrix/mesh/results 继续保持 Git 忽略。

---

## 17. 下一任务建议

下一任务不应继续：

```text
增加 ILU fill
增加 outer iterations
继续普通 p1 coarse 扫描
继续 adaptive BDDC
直接开始 angle/wavelength sweep
```

应只解决一个核心问题：

```text
在 14 GB 内把 h=2 response-column maximum residual
从约 0.541 降到 < 0.1。
```

推荐顺序：

```text
1. 压缩 Q 和限制 outer Krylov 内存，释放 1–3 GB；
2. 使用 block/recycled Krylov 同时或共享子空间地改进 80 个 response columns；
3. 在 DOLFINx topology 生命周期内实现 edge/vertex H(curl) patch；
4. 实现 low-order-refined 或真正 h-coarsened H(curl) hierarchy；
5. Q 质量达到 gate 后重新运行完整 cached Schur；
6. h=2 residual <= 1e-6 后再开放参数鲁棒性矩阵。
```

---

## 18. 最终审查结论

Task025 没有发现足以否定结果的重大错误。它实现了目前最有价值的完整 augmented 求解架构：吸收移位 FE 预处理、全部 80 个 FE-response columns、显式小 Schur 与 Schur LU，并在 14 GB 内把 h=2 完整真残差推进到 `0.118475`。这是相对于 Task023 plain FieldSplit 的明确突破。

但 Task025 的原始最终目标仍未完成：h=2 未达到 strong/production-level，没有 official R/T/A，没有完成 topology-aware H(curl) patch、真正 3D h-GMG，也没有验证角度和波长鲁棒性。当前瓶颈已经被精确定位为 response columns Q 的精度和相应内存预算。

最终定性：

```text
Task025 = full-aux cached-Schur research breakthrough
        + production/parameter-robustness objective not achieved
```
