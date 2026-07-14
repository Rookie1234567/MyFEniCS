# Task031：compact physical-slab PC 内存优先结构性优化

## 0. 任务身份与启动顺序

```text
task_id = Task031
name_en = Memory-First Structural Optimization of the Compact Physical-Slab PC
status = planned
primary_objective = minimum peak memory subject to verified convergence
ordinary_default_change = forbidden_without final review
suggested_branch = codex/20260714-task31-compact-pc-memory-optimization
```

本任务书先进入 Task030 审查分支，**不得在 Task030 分支执行**。必须依次完成：

```text
Task030 response_v2
→ ChatGPT final review
→ 用户明确同意合并
→ Task030 selective merge master
→ master lightweight release checks
→ Codex 从 clean master 创建 Task031 分支
```

---

# 1. 背景与统一基线

Task027 首次得到可信工作站迭代解：

```text
exact condensed A = F - C H^-1 D
+ 16 complete physical z-slabs
+ overlap0.25
+ shifted local ILU1
+ fixed two-step smoothing
+ fixed 75D Floquet z-hat wave coarse
+ right FGMRES restart100
```

Task030 证明当前 792D p1 p/h coarse、patch+p/h 和 all-mode Woodbury 都没有形成求解正反馈。最终成功机制仍是 Task027-derived physical-slab + 75D wave coarse，但经过：

```text
ILU1 -> ILU0
pre-only -> symmetric pre/coarse/post
global shifted-F copy -> subdomain-local shift
retain submatrix/KSP/factor -> factor-only storage
FGMRES restart100 -> restart90
```

Task030 compact baseline：

| h (nm) | iterations | full true residual | peak incl. R/T/A |
|---:|---:|---:|---:|
| 5 | 855 | `9.924905e-7` | 1.696136 GB |
| 3 | 962 | `9.903890e-7` | 3.807503 GB |
| 2 | 1873 | `9.972228e-7` | 9.374729 GB |

h2：

```text
solve/total = 2393.689 / 2577.796 s
R/T/A = 0.001342934415 / 0.599213236006 / 0.399443832218
energy closure = 2.639e-9
max R/T/A delta vs direct = 6.561e-9
same 80 propagating modes
no swap
```

当前 h2 仍同时保留约 65.12M nnz 的全局 `F`、约 95.62M 记录 nnz 的 slab factors，以及约 0.886 GB 的 restart90 Krylov 向量。继续优化的潜力主要在存储与生命周期，而不是继续修改 75D coarse。

---

# 2. 目标与成功标准

## 2.1 优先级

```text
P1 peak simultaneous total RSS / cgroup peak
P2 explicit true residual + official R/T/A correctness
P3 convergence reliability
P4 iterations and solve time
```

只要最终收敛，较高迭代数不会自动判失败；但迭代数、setup/solve/total time 必须完整记录。

## 2.2 内存目标

相对 Task030 h2 `9.374729 GB`：

```text
memory_positive:          peak < 9.0 GB
engineering_success:      peak <= 8.5 GB
strong_memory_success:    peak <= 8.0 GB
stretch_memory_success:   peak <= 7.0 GB
```

h3 代理 Gate：

```text
minimum continuation: peak <=3.50 GB or >=8% reduction
strong signal:        peak <=3.25 GB or >=15% reduction
```

## 2.3 数值 Gate

所有 qualified full solve：

```text
reported residual <=1e-6
condensed true residual <=1e-6
full augmented true residual <=1e-6
same 80 modes
official R/T/A + A_volume available
energy closure within existing Stage4 Gate
R/T/A delta vs direct <=1e-6
```

不设置 1200/800 步硬门槛。运行安全上限建议：h5/h3 `max_it<=5000`，h2 `max_it<=6000`。

---

# 3. 冻结问题与非目标

所有候选保持：

```text
50 x 25 x 140 nm cell
17 x 25 x 120 nm block
lambda=13.5 nm
theta=80 deg, phi=0 deg, s polarization
complex Si
fine p2 Nedelec
matched hexa target mesh
double Floquet
auto_propagating
80 auxiliary modes before condensation
exact condensed outer operator
official modal R/T + volume absorption
MPI4 target
```

本任务不做：新的 p/h coarse、Woodbury 扫参、GenEO/HPDDM、AMS/HX 重启、自适应网格、角度/材料鲁棒性、减少 modes、修改 R/T/A、direct 微调或 ordinary default 变更。

开始前必须读取 Task026/027/029/030 的 outcomes、Task030 review/response V1/V2、`development_progress.md`、solver guide 和相关 walkthrough，并在 run log 记录 Task030 merge SHA、Task031 base SHA、branch、image digest 和 clean-source 状态。

---

# 4. 统一对象与阶段内存审计

先扩展 Task029/030 telemetry，至少设置：

```text
process_start
stage4_assembly_complete
condensed_blocks_extracted
augmented_matrix_destroyed
coarse_operator_complete
slab_factorization_complete
source_submatrices_destroyed
outer_ksp_setup_complete
during_outer_solve_peak
outer_solve_complete
true_residual_complete
outer_ksp_destroyed
pc/factors destroyed
assembled_F destroyed
before/during/after official RTA
final_cleanup
```

每个阶段记录 simultaneous rank RSS、process-tree RSS、cgroup current/peak、swap、host available memory。

建立对象账本：`F/C/D/H`、condensed work vectors、75D basis/coarse、slab source matrices/factors、scatter/index/weights、Krylov basis、monitor vector/history、field/RTA。记录 nnz/估算 bytes/创建与销毁阶段。

最终必须区分：solve historical peak、RTA second peak、current RSS 下降与真实 solve-peak 下降。

---

# 5. Lane A：固定线性 PC 与低存储 Krylov

先验证：

```text
M(alpha*x+beta*y) ~= alpha*M(x)+beta*M(y)
repeated M(x) deterministic
MPI1/2/4 action identity
inner smoothing uses zero guess + fixed iteration count
```

建议 Gate：linearity `<=1e-11`，determinism `<=1e-13`。失败则保留 FGMRES，不继续普通 GMRES/短递推路线。

通过后筛选：

```text
FGMRES restart90 baseline
GMRES restart90 / 70 / 50
FGMRES restart70 / 50
TFQMR with legal right-PC semantics
最多再选 GCR 或 BiCGStab(l) 之一
```

每个候选定期计算 explicit true residual。restart 更小或短递推导致迭代增加不自动失败；重点记录 Krylov 向量估算、实际 peak、iterations、solve time。

---

# 6. Lane B：真正 matrix-free 的 fine-level F

当前 condensed MatShell 内部仍调用 `blocks.F.mult`，因此 assembled `F` 与 slab factors 同时常驻。

目标：

```text
assemble F temporarily
→ build/certify 75D coarse
→ build all slab factors
→ build element/form-level matrix-free F action
→ certify equivalence
→ destroy assembled F
→ solve (F_mf - C H^-1 D)x=b
```

必须处理 p2 Nedelec orientation、MPC/Floquet reduced mapping、ghost update、complex coefficients、MPI ownership 和材料/边界项。优先复用历史 matrix-free FE action，不得用 private API 或 probe/pinv hack。

Correctness：随机向量、plane-wave-like 向量、coarse basis、MPI1/2/4；`F` action 和 condensed action相对误差 `<=1e-11`。必须证明 wrapper 不再间接引用 assembled F，且 solve peak 中 F 已销毁。

记录 removed F bytes、matrix-free cache、mean F/operator apply time、iterations、solve time 和 peak RSS。允许时间增加，只要收敛且内存显著下降。

---

# 7. Lane C：求解后提前释放与 batch 生命周期

完成 solve、三类真残差和 auxiliary recovery 后，在 official RTA 前安全释放不再需要的：

```text
outer KSP/Krylov basis
monitor buffers
Python PC wrappers
coarse/smoother work objects and factors
operator work vectors
F/C/D/H after full residual and recovery
```

保留 FE/augmented solution、mesh/material/config、MPC/Floquet reconstruction 和 port modes。

记录 solve peak、solve 后 current RSS、KSP destroy 后、PC/factor destroy 后、RTA 前后和最终 cleanup。该 lane主要服务批量计算；若 high-water peak不变，必须标为 lifecycle success，不能包装成 solve-memory success。

---

# 8. Lane D：slab 因子精确去重

假设部分 z 区域的局部矩阵在规范化局部编号后完全一致。对每个 slab 建立 shape、CSR pattern、normalized column offsets、values、material/region/overlap identity 的 fingerprint。

只有 exact hash match 或 action error `<=1e-13` 才允许共享 factor。第一版禁止近似复用。

评估 per-owner-rank dedup 和保持负载均衡的 owner assignment；不得集中到 rank0。记录 slab 数、unique factor classes、factor nnz before/after、peak、communication、PC apply time。没有精确重复则作为可靠负结果停止。

---

# 9. Lane E：保持 symmetric pre/post 的 slab/overlap 优化

固定 75D coarse、symmetric pre/coarse/post、ILU0（或当前最佳局部 action）、local shift、factor-only 和同一外层 Krylov，最多筛选 8 个 h5 候选：

```text
16 slabs overlap 0.25 baseline
16 slabs overlap 0.1875 / 0.125
12 slabs overlap 0.25 / 0.1875
20 slabs overlap 0.1875 / 0.125
1 个 material/layer-aligned nonuniform candidate
```

非均匀候选可在 substrate interface、grating top、ports 附近使用较大 overlap，在均匀内部使用较小 overlap。必须覆盖全部 reduced DoF，并记录 multiplicity、factor rows/nnz、owner balance、PC apply、true residual 和 peak。迭代增加不自动失败。

---

# 10. Lane F：选择性局部因子

最多测试：

```text
ILU0 on interface/port slabs + fixed polynomial/Jacobi on bulk
ILU0 on high-risk slabs + fixed-step local GMRES on remaining slabs
exact-dedup factors + polynomial fallback for unmatched bulk
```

局部 action 必须固定线性、零初值、固定步数。分类只能依据材料/界面/port identity、baseline early residual distribution 或矩阵诊断，不能使用最终解；规则在 h5 冻结后原样用于 h3/h2。

若 h5 true residual长期不下降、PC apply >3x 且内存下降 <15%，立即停止。

---

# 11. 候选漏斗

## Stage A：代数 smoke

线性、action equivalence、MPI collective safety、one/repeated PC apply、对象 destruction。

## Stage B：h5

每个候选做 20-step smoke + 200-step explicit true residual screen。

```text
memory_positive:
  peak <=0.90 x Task030 h5 and downward true-residual trend

strong_memory_positive:
  peak <=0.80 x baseline and no stagnation
```

若有实际内存下降、残差持续下降且无数值不一致，可做 full h5，不因早期比 baseline 慢自动淘汰。

## Stage C：h3

最多 4 个机制不同的 full-h5 候选进入 h3。Continuation：full residual pass、same 80 modes、RTA pass、peak `<=3.50 GB` 或降幅 `>=8%`、无 swap。强信号：`<=3.25 GB` 或降幅 `>=15%`。

允许组合已分别通过且机制正交的优化，例如低存储 GMRES + matrix-free F + factor dedup + optimized overlap。必须保留单项证据，解释组合收益来源。

---

# 12. h2 条件解锁

默认 `RUN_H2=false`。最多运行一个最佳综合候选，加一个机制显著不同且预测更低的可选候选；若第一个已 `<=8.0 GB`，第二个只有预测 `<=7.5 GB` 才允许运行。

Gate：

```text
h5/h3 full numeric pass
h3 memory reduction >=8% vs Task030
两个独立 h2 中央预测 <=8.8 GB
保守上界 <=10.0 GB
same 80 modes / exact condensation
no h3 swap
clean-source provenance
watchdog enabled
ordinary default unchanged
```

Watchdog 建议：9.5 GB warning，11.0 GB controlled termination。

成功分类：

```text
h2_memory_positive:         converged and <9.0 GB
engineering_memory_success: converged and <=8.5 GB
strong_memory_success:      converged and <=8.0 GB
stretch_memory_success:     converged and <=7.0 GB
```

另标记 `balanced_performance`（solve time `<=1.5x` Task030）或 `slow_but_memory_efficient`。时间标签不改变内存分类。

---

# 13. 时间与迭代统计

每个 full run 输出 setup、coarse setup、slab extraction/factor、KSP setup、solve、RTA、cleanup、total time；operator/PC apply count与均值；iterations、restart/方法、true residual history。

必须说明每一 GB 内存收益付出了多少迭代/时间，及其适用机器。Task030 h2 对照：1873 步，solve/total 2393.689/2577.796 s。

---

# 14. 代码、Benchmark 与文档

建议新增独立模块，例如：

```text
src/solvers/matrix_free_fe_action.py
src/solvers/factor_deduplication.py
src/studies/run_task031_memory_optimization.py
```

新行为必须 explicit opt-in；failed candidates 不进入普通 API；ordinary profile 不变。

建立：

```text
benchmarks/cases/070_compact_physical_slab_memory_optimization/
docs/task031_compact_physical_slab_memory_optimization/outcomes/
```

Case070 至少包含 baseline h5/h3/h2、object lifecycle、PC linearity、candidate screen、best h5/h3/h2（若运行）和 memory component records。Outcomes 至少包含 summary、run/test logs、environment、memory breakdown、Krylov comparison、matrix-free validation、factor dedup、overlap/selective-solver funnels、h2 prediction/decision、negative results、merge recommendation、next decision。

所有正式 best records 必须来自 tracked-source-clean commit，记录真实 command、UTC、branch/SHA、image digest、host ID、artifact SHA-256。dirty runs 只能是 research diagnostic。

最终必须按 `task_retrospective_standard.md` 更新 `development_progress.md`、docs index、capability matrix、solver guide、benchmark、theory/walkthrough 和 documentation contracts。

---

# 15. 测试与停止规则

测试 PC linearity/determinism、GMRES/FGMRES true residual、matrix-free F/condensed action、factor fingerprint/refcount、no double destroy、batch lifecycle、MPI1/2/4、重复 apply 内存稳定，并运行 Task026/027/029/030 回归、full unit、docs contracts、benchmark checker、JSON/CSV、diff/clean-tree。

停止某 lane：修复两次仍不正确；false convergence；内存下降 <3% 且成本明显恶化；peak 增加 >10% 无收益；需要 private API；factor sharing 非精确；matrix-free仍引用 F；改变物理/modes/RTA；只降低 current RSS却声称 solve-peak success；h5 有效但 h3 完全不迁移。

---

# 16. 合并原则与最终问题

可以考虑合并：qualified low-storage Krylov、true matrix-free F、safe early cleanup、exact factor dedup、generalized slab definition、qualified selective local solver、Case070/docs/tests，以及最终 explicit Task031 profile。

不得自动合并：unqualified Krylov、approximate factor sharing、failed slab/local profiles、dirty canonical records、heavy artifacts、private hacks、ordinary default 变更或 Task030 failed p/h/Woodbury paths。

Task031 最终必须回答：

```text
1. 固定 PC 能否用 GMRES/短递推方法降低 Krylov memory？
2. assembled F 能否在 setup 后真正释放？
3. slab factors 是否存在可精确去重的类别？
4. symmetric pre/post 下能否减小 overlap？
5. 能否只因子化关键 slabs？
6. h2 能否从 9.374729 GB 降到 8.5/8.0/7.0 GB？
7. 每项内存收益的迭代与时间代价是多少？
8. 哪些可进 master，哪些只留 research？
9. 最终 profile 是否可冻结并进入参数鲁棒性验证？
```
