# CODEX TASK 20260713：3D Stage4 直接法内存剖析与公共装配层优化

## 0. 任务名称

```text
Task029: Stage4 direct-solver memory forensics,
shared assembly/lifecycle optimization,
and conditional h=2 validation
```

中文定位：

```text
Task029：3D Stage4 直接法内存剖析、公共装配与对象生命周期优化，
以及满足严格内存 Gate 后的条件式 h=2 验证。
```

本任务首先回答：

```text
当前 3D Stage4 direct solve 的峰值内存究竟消耗在哪个阶段、哪个 PETSc/MUMPS 对象、
哪些开销属于 LU 因子本身，哪些属于项目代码的矩阵副本、预分配、MPI/对象生命周期开销？
```

随后只对有证据支持的方向进行优化，并验证优化是否降低内存、是否改变计算结果。

本任务不是新的物理功能任务，不研究自适应网格，不修改 Task27 迭代预条件器，也不以直接法解决上千万自由度为最终目标。直接法在本项目中的长期定位仍是：

```text
reference solver + 中等规模验证 + 局部/coarse 求解 + 迭代法交叉检查。
```

---

# 1. 启动前置条件与分支规则

## 1.1 Task028 必须先收口

Codex 不得立即在当前 Task028 分支开始 Task029 代码开发。

必须先完成：

```text
review_report_v4.md
-> response_v4.md
-> ChatGPT 最终复审
-> 用户明确许可
-> Task028 integration branch 合并 master
-> master 轻量 release check
```

Task028 的三项轻量修改仅限：

```text
M1 tracked_source_dirty Gate；
M2 Case002/003 runner 强制真实 IMAGE_DIGEST；
M3 final-head lightweight validation。
```

不得借 `response_v4.md` 开始 direct memory 优化。

## 1.2 Task029 执行分支

ChatGPT 不创建执行分支。

Task028 合并后，Codex 必须从更新后的干净 `master` 创建独立分支，推荐：

```text
codex/20260713-task29-stage4-direct-memory-forensics
```

开始前记录：

```text
master_base_sha
Task028 merge commit / PR
branch_name
git status
container image + digest
host memory/swap/cgroup limit
```

若 Task028 尚未进入 master，则 Task029 不得开始。

## 1.3 不覆盖 Task028 基准

以下 Task028 canonical records 是只读基线，不得覆盖：

```text
benchmarks/records/direct_p2_h5_mpi4.json
benchmarks/records/direct_p2_h3_mpi4.json
benchmarks/records/direct_p2_h2_reviewed_reference.json
benchmarks/records/workstation_p2_h5_mpi4.json
benchmarks/records/workstation_p2_h3_mpi4.json
benchmarks/records/workstation_p2_h2_mpi4.json
```

Task029 的所有新记录必须使用新目录和新 benchmark ID。

---

# 2. 背景与当前问题

当前冻结 target 的直接法参考大致为：

| h (nm) | FE DoF | direct 总峰值 RSS | 状态 |
|---:|---:|---:|---|
| 5 | 44,698 | 约 2.293 GB | Task28 canonical direct |
| 3 | 198,438 | 约 8.182 GB | Task28 canonical direct |
| 2 | 615,108 | 约 18–20.533 GB，依统计口径/环境 | 历史 reviewed reference；16 GB 个人机可能 swap |

当前迭代法 h=2 约为 13.08 GB，说明 direct 的 LU fill 是主要压力，但仍不能排除项目代码存在以下额外开销：

```text
- FE base matrix 与 augmented DtN matrix 同时存在；
- `_copy_base_matrix_to_augmented` 逐行复制且未精确预分配；
- unconstrained / constrained / augmented / diagnostic matrix 重复保留；
- KSP factorization 期间仍保留已不再需要的 base objects；
- 多 MPI rank 的矩阵结构、分析 metadata、通信 buffer 或临时对象；
- MUMPS ordering、in-core/OOC、BLR 和 memory relaxation 未经过系统对比；
- 当前“总峰值 RSS”可能是各 rank 历史峰值之和，并非同一时刻的真实总内存；
- postprocess / field reconstruction / RTA 的峰值与 factorization 峰值未严格分开。
```

本任务必须用数据判断，而不是先假定原因。

---

# 3. 冻结物理与离散问题

Task029 不得修改目标物理模型。

使用 Task028 的唯一配置工厂：

```text
src/common/config_3d.py::target_stage4_config
```

冻结配置：

```text
geometry_kind = rectangular_block_grating
period_x = 50 nm
period_y = 25 nm
air_height = 130 nm
substrate_thickness = 10 nm
block = 17 x 25 x 120 nm
wavelength = 13.5 nm
incident_theta = 80 deg
incident_phi = 0 deg
polarization = s
material = complex Si
nedelec_degree = 2
boundary = double Floquet + auxiliary Fourier-DtN
order policy = auto_propagating
ordinary solver = PETSc preonly + LU + available reviewed direct package
MPI baseline = 4 ranks
```

只允许改变：

```text
- h = 5 / 3 / 条件式 2 nm；
- direct solver profile；
- ordering / MUMPS factorization options；
- 内存遥测；
- 矩阵预分配；
- 对象生命周期；
- 数学等价的装配实现。
```

不得改变：

```text
geometry / material / incidence / p / Floquet / DtN modal set / official RTA definition。
```

---

# 4. Task029 核心目标

## 4.1 诊断目标

建立 direct 路径的可审计内存账本：

```text
1. 各阶段当前 RSS、阶段峰值和全任务峰值；
2. MPI 同时总 RSS，而不是只报告各 rank 历史峰值之和；
3. matrix rows/nnz/allocated/used/unneeded/mallocs/memory；
4. factor fill ratio、factor memory、analysis/factor/solve 时间；
5. base matrix、augmented matrix、factor、vectors 和 postprocess 的内存占比；
6. swap/cgroup memory 变化；
7. 不同 MPI rank/solver/ordering/profile 的总内存差异。
```

## 4.2 工程优化目标

优先寻找对 direct 和未来 iterative 都有价值的公共优化：

```text
- 精确或更合理的 AIJ 预分配；
- 降低 matrix assembly realloc/malloc；
- base -> augmented 完成后尽早释放 base matrix/vector/forms；
- 避免无必要的 unconstrained/diagnostic matrix；
- 避免不需要的 Mat/Vec copy；
- 明确 KSP/factor/postprocess 生命周期；
- 选择更合适的 direct solver / ordering / MUMPS memory profile；
- 对 OOC/BLR 的内存、时间和数值误差做真实定量。
```

## 4.3 数值保护目标

任何内存优化都必须证明：

```text
- full explicit true residual 不退化；
- official R/T/A 不改变；
- energy closure 不退化；
- direct solution 与 Task028 reference 一致；
- Floquet/DtN 模态集合与 auxiliary amplitude 一致；
- ordinary default 不被静默改变。
```

---

# PART I：先建立可靠内存遥测

## 5. Stage A：内存统计口径

必须区分以下指标：

```text
rank_current_rss_mb
rank_peak_rss_mb
sum_current_rss_all_ranks_mb
max_simultaneous_total_rss_mb
sum_rank_historical_peaks_mb_upper_bound
container_cgroup_current_mb
container_cgroup_peak_mb
container_swap_current_mb
host_swap_in/out delta
PETSc reported allocated memory（若当前 petsc4py API 可用）
```

特别注意：

```text
sum(rank_i historical max RSS)
```

不是同一时刻的真实 MPI 总峰值。两者必须使用不同字段名，不得混写。

## 5.1 阶段 checkpoint

至少记录：

```text
process_start
after_config
after_mesh
after_function_space
after_materials_and_forms
after_base_matrix_assembly
after_floquet_mpc_finalize
after_dtn_mode_enumeration
after_augmented_matrix_allocation
after_base_matrix_copy
after_dtn_coupling_insert
after_augmented_matrix_finalize
before_ksp_create
before_ksp_setup
during_ksp_setup_peak
after_ksp_setup_factorized
before_ksp_solve
during_ksp_solve_peak
after_ksp_solve
after_true_residual
after_fe_field_reconstruction
after_official_rta
after_field_output
after_ksp_destroy
after_matrix_destroy
final_cleanup
```

如果 PETSc/MUMPS 实际上把分析和 numeric factorization 都放在 `KSPSetUp`，必须如实记录，不得虚构更细阶段。

## 5.2 外部/并行采样器

仅在 Python checkpoint 读取 RSS 可能漏掉 C/Fortran factorization 内部峰值。

应实现低开销采样器，推荐：

```text
poll interval = 0.25–1.0 s
stage marker = rank0 写入当前 stage
monitor = 独立进程或容器/cgroup 采样
output = timestamped CSV/JSONL
```

至少捕获：

```text
wall_time
stage
per-rank RSS（可获取时）
simultaneous total RSS
container memory.current
container memory.peak
swap current
```

采样器不得改变求解数值；必须可显式开关。

## 5.3 PETSc matrix inventory

对每个长期存在的 Mat 使用 PETSc matrix info，记录：

```text
name
type
local/global rows and columns
nnz_used
nnz_allocated
nnz_unneeded
mallocs
matrix_memory_bytes
block_size
ownership range
```

对象至少包括：

```text
base constrained FE matrix
augmented DtN matrix
factor matrix（若 backend 可报告）
任何 unconstrained/diagnostic matrix
```

对 factored matrix 尽可能记录：

```text
fill_ratio_given
fill_ratio_needed
factor_mallocs
factor_memory
```

若当前 backend/API 无法提供某字段，写 `null/not_available`，不得猜测。

## 5.4 MUMPS telemetry

自动探测当前 PETSc/MUMPS 支持的：

```text
INFO/INFOG/RINFO/RINFOG
analysis memory estimates
factor memory estimates
actual ordering
actual solver package
OOC state
BLR state
```

只读取当前构建真实支持的字段。不得把未确认的 ICNTL/CNTL 含义硬编码成结论。

---

# PART II：基线重跑与内存归因

## 6. Stage B：只测量、不优化

第一轮提交只允许增加遥测，不改变 direct 数值路径和 profile。

### 6.1 h=5 baseline

运行：

```text
h=5
p=2
MPI4
Task28 default direct profile
telemetry=on
```

验证与 Task28 h5 reference 一致后，才能继续。

### 6.2 h=3 baseline

运行：

```text
h=3
p=2
MPI4
Task28 default direct profile
telemetry=on
```

h=3 必须在不依赖 swap 的环境中完成；若内存环境不足，先停止并记录，不允许开始 h=2。

### 6.3 可选 rank-count 诊断

只在 h=5 上比较：

```text
MPI1
MPI2
MPI4
```

要求固定或记录总 CPU 线程数，防止把线程数差异误认为 rank 内存差异。

h=3 只对 Stage B 选出的 1–2 个最有意义 rank 配置运行，不做无边界组合爆炸。

### 6.4 基线输出

必须给出：

```text
峰值发生在哪个阶段；
KSPSetUp 增量；
KSPSolve 增量；
RTA/field output 增量；
A_base 与 A_aug 同时存在时的增量；
矩阵原始 storage 与 factorization storage 的比例；
MPI rank 数变化对总 RSS 的影响；
是否发生 swap；
Task28 与新测量口径的差异解释。
```

在完成 Stage B 报告前，禁止直接开始大规模重构。

---

# PART III：候选优化调查

## 7. Stage C：建立 optimization hypothesis table

输出：

```text
docs/task029_stage4_direct_memory_forensics/outcomes/optimization_hypotheses.csv
```

字段至少包括：

```text
hypothesis_id
suspected_object_or_stage
baseline_memory_gb
root_cause_evidence
proposed_change
mathematical_effect
expected_memory_gain
risk
required_test
h5_status
h3_status
merge_recommendation
```

必须至少调查以下假设。

## 7.1 H1：base matrix 与 augmented matrix 双份存在

当前 `dtn_port_3d::_copy_base_matrix_to_augmented` 会：

```text
create new A_aug
row-by-row copy A_base
随后插入 C/D/H
```

调查：

```text
- A_base 和 A_aug 同时存在多久；
- A_aug finalize 后 A_base 是否仍被任何路径需要；
- b_base 是否可以更早销毁；
- forms/temporary vectors 是否仍被 Python 引用；
- 提前销毁后 full residual/RTA 是否仍可由 A_aug 完成。
```

第一优先级优化：

```text
完成 copy 和必要诊断后，立即释放不再需要的 base Mat/Vec/临时对象。
```

不得在确认对象所有权前盲目 destroy。

## 7.2 H2：A_aug 缺少精确预分配

当前 A_aug 创建后允许新非零动态分配。

调查：

```text
nz_allocated
nz_used
nz_unneeded
malloc count
assembly time
```

根据：

```text
A_base 每行 nnz + C/D/H coupling pattern
```

构建可靠的 local diagonal/off-diagonal row-wise preallocation。

目标：

```text
- 显著降低 malloc/reallocation；
- 降低 unused allocation；
- 不改变 matrix entries；
- 不依赖固定 DoF 编号或固定 mode 数。
```

## 7.3 H3：无必要的矩阵/向量/诊断副本

检查：

```text
unconstrained matrix
MPC constrained base matrix
augmented matrix
matrix stats copy
diagnostic assemble-only matrix
solution Vec duplicate
residual Vec
field reconstruction Vec
surface mode vectors
```

对每个对象写明：

```text
owner
creation site
last use
destroy site
peak coexistence interval
```

建立：

```text
direct_object_lifecycle.md
```

只删除明确无用的对象；不得为了省内存删除 true residual 和 official RTA 所需证据。

## 7.4 H4：direct augmented assembly

只有 H1–H3 收益不足时，才研究不先形成完整 base Mat 的 direct augmented assembly。

候选方向：

```text
- 预创建 augmented Mat；
- FE block直接装入 augmented FE rows/cols；
- 再插入 modal C/D/H；
- 避免 A_base -> A_aug 的完整复制共存峰值。
```

该方向属于中风险架构优化，必须具备：

```text
matrix action equality
entry/sample comparison
RHS equality
full solution equality
RTA equality
MPI tests
exception-safe lifecycle
```

若 DOLFINx/dolfinx_mpc API 不允许安全完成，记录 `not_feasible_without_framework_change`，不要使用脆弱私有 hack 强行实现。

## 7.5 H5：solver package 与 MPI rank

自动列出 PETSc 构建中可用的 direct packages，例如：

```text
MUMPS
SuperLU_DIST
MKL_PARDISO / MKL_CPARDISO（若存在）
PaStiX（若存在）
```

不得为了本任务重建复杂生产镜像或引入未经审查的新依赖。

已存在即可在 h=5 做受控比较；不存在则写清楚。

比较：

```text
total RSS
factor memory
fill ratio
time
true residual
R/T/A
MPI/thread model
```

## 7.6 H6：MUMPS ordering 与 memory profile

对当前构建实际支持的 ordering/profile 做小规模筛选。

至少保留：

```text
baseline in-core MUMPS
mumps_ooc
mumps_blr
```

可调查：

```text
ordering candidates
parallel analysis settings
memory relaxation
OOC
BLR tolerance
```

规则：

```text
- 一次只改变一个主要因素；
- 先 h=5；
- 只有正信号才进 h=3；
- 所有 profile 保存真实 PETSc/MUMPS options；
- OOC 必须报告 scratch bytes 和 I/O 时间；
- BLR 必须报告真残差和 R/T/A 差异；
- solver 返回 success 不等于数值通过。
```

## 7.7 H7：postprocess 峰值

区分：

```text
factorization peak
solve peak
field reconstruction peak
official RTA peak
field output peak
```

若 RTA/输出导致显著第二峰值，可优化：

```text
- 在不再需要 factor 后先 destroy KSP/factor；
- 再进行 field reconstruction / RTA；
- 或先保存必要 solution Vec，再释放 factor。
```

但必须确认 RTA 不再调用 KSP/factor 对象。

---

# PART IV：实施顺序

## 8. Stage D：低风险公共优化

优先实施：

```text
D1. checkpoint + sampler + matrix inventory；
D2. 提前释放已完成最后使用的 base Mat/Vec/temporary forms；
D3. 精确/合理预分配 A_aug；
D4. 关闭默认不需要的 diagnostic matrix copy；
D5. 异常路径和正常路径统一 destroy；
D6. factor 与 RTA/output 生命周期分离（仅在证据允许时）。
```

每项必须单独记录前后内存和数值结果，不允许把多个修改混在一起后无法归因。

## 9. Stage E：solver/profile 筛选

### 9.1 h=5 screening

每个候选先运行 h=5。

淘汰条件：

```text
- full true residual 不合格；
- R/T/A 超出容差；
- 峰值内存不降且时间显著增加；
- 发生不受控 swap/OOC；
- backend 不可复现；
- 依赖未固定的外部环境。
```

### 9.2 h=3 confirmation

最多选择两个候选进入 h=3：

```text
best in-core candidate
best low-memory candidate（可为 OOC/BLR）
```

h=3 必须完成完整：

```text
assemble -> factor -> solve -> true residual -> field -> official RTA -> cleanup
```

不得只运行 assemble-only 就宣称 direct solve 内存降低。

## 10. Stage F：推荐 profile

最终可以产生：

```text
baseline_task28_direct
optimized_direct_incore_candidate
optimized_direct_low_memory_candidate
```

但 ordinary default 保持 Task28 行为，除非：

```text
- ChatGPT review 通过；
- 用户明确同意；
- 新 profile 在 h5/h3 均满足全部 Gate。
```

Task029 分支中新的 profile 必须显式 opt-in。

---

# PART V：h=2 条件式运行规则

## 11. h=2 默认禁止

Task029 默认：

```text
RUN_H2 = false
```

不得因为历史上存在 h=2 record 就直接重跑。

## 11.1 h=2 解锁 Gate

只有同时满足以下条件，才允许启动一次 h=2 optimized direct run：

```text
G1. h=5 optimized full run 通过全部 residual/RTA Gate；
G2. h=3 optimized full run 通过全部 residual/RTA Gate；
G3. h=5 与 h=3 的 max simultaneous total RSS 均至少下降 20%；
G4. h=3 factorization 阶段未发生 host swap；
G5. 内存增长模型预测 h=2 peak <= safe_h2_rss_limit_gb；
G6. safe_h2_rss_limit_gb 默认 13.5 GB（16 GB 个人机预留 OS/容器余量）；
G7. 当前可用物理内存和 cgroup limit 均满足安全余量；
G8. 只选择一个已通过 h5/h3 的最佳 profile；
G9. run script 有内存 watchdog 和 clean abort；
G10. 不覆盖 Task28 h=2 historical reference。
```

“至少下降 20%”只是最低解锁条件；推荐目标为 h=3 下降 25–30%。

## 11.2 h=2 内存预测

使用 h=5/h=3 的实际：

```text
matrix nnz
factor nnz/fill
factor memory
simultaneous total RSS
DoF
```

建立至少两种外推：

```text
DoF power-law fit
factor-nnz / fill based fit
```

预测区间而不是单点，并说明不确定性。

若上界超过 13.5 GB，则 h=2 不运行。

## 11.3 watchdog

h=2 若解锁，至少监控：

```text
container memory current/peak
host available memory
swap current / swap-in
stage
elapsed time
```

出现以下条件立即安全终止并保存诊断：

```text
memory > configured hard limit
持续 swap-in
cgroup 接近 OOM
factorization 无进展且系统 thrashing
```

不得让个人电脑长期 swap 数小时仅为了得到结果。

## 11.4 h=2 未运行也是合法结论

若 Gate 不满足，输出：

```text
h2_launch_decision = not_run
reason
predicted_peak_range
blocking_stage
recommended_machine_memory
```

不得将“未运行”写成失败；这可以是成功的工程决策。

---

# PART VI：数值与性能 Gate

## 12. 数值 Gate

对 h=5/h=3，优化结果相对 Task28 reference 必须满足：

```text
full true residual <= 1e-8
abs(R_new - R_ref) <= 1e-8
abs(T_new - T_ref) <= 1e-8
abs(A_new - A_ref) <= 1e-8
abs(energy_closure) <= Task28 direct gate
same physical_model
same modal order set
same n_fe / n_aux
same Floquet constraint count
```

若保存完整 FE solution comparison，建议：

```text
relative field coefficient difference <= 1e-8
```

因 ordering/parallel factorization 浮点路径不同，禁止要求 bitwise equality。

## 12.1 OOC/BLR 特别 Gate

OOC：

```text
真残差和 RTA 与 baseline 一致；
报告 scratch peak bytes；
报告 I/O 时间；
成功清理或保留失败诊断；
不得把磁盘占用算成 RAM 节省而不报告代价。
```

BLR：

```text
真残差必须重新计算；
R/T/A 必须对 baseline；
记录 BLR tolerance；
若降低内存但误差不合格，只能标 research/diagnostic。
```

## 13. 内存 Gate

至少报告：

```text
baseline h5/h3 max simultaneous total RSS
optimized h5/h3 max simultaneous total RSS
absolute reduction GB
relative reduction percent
KSPSetUp/factorization reduction
matrix storage reduction
factor fill/memory change
swap delta
runtime ratio
```

成功分类：

```text
diagnostic_success:
  找到可信内存分解和主要瓶颈，即使优化收益有限；

engineering_success:
  h5/h3 数值等价，且 h3 总峰值下降 >=20%；

strong_engineering_success:
  h5/h3 数值等价，且 h3 总峰值下降 >=30%；

h2_workstation_success:
  h2 在 safe limit 内无 swap 完整求解并通过数值 Gate。
```

不得为了达到百分比只改变统计口径。

---

# PART VII：与 COMSOL 的比较边界

## 14. 不做未经控制的直接结论

Task029 可以讨论当前项目与 COMSOL 的内存差异，但不得仅用 DoF 比值断言哪个框架更高效。

必须同时比较或注明缺失：

```text
DoF
matrix nnz / avg nnz per row
element order
mesh topology
complex/real formulation
solver package
ordering
MPI ranks / threads
factor fill
peak memory definition
OOC/swap
RTA/output included or excluded
```

如果用户能够提供 COMSOL solver log / memory report，可建立：

```text
comsol_comparison_notes.md
```

但 COMSOL 数据缺失不得阻塞 Task029。

Task029 的核心仍是项目自身前后对比。

---

# PART VIII：Benchmark 与输出结构

## 15. 新 Benchmark case

建立：

```text
benchmarks/cases/050_stage4_direct_memory_forensics/
```

至少包含：

```text
README.md
config.json
expected.json
run_h5.sh
run_h3.sh
run_h2_guarded.sh
records/
```

默认 candidate/heavy artifact：

```text
benchmarks/artifacts/cases/050/
```

不得提交：

```text
mesh
VTU/XDMF/HDF5/BP
factor/OOC files
full memory trace（若过大）
raw PETSc log
```

可提交轻量：

```text
summary JSON
checkpoint CSV
profile comparison CSV
compressed/downsampled memory timeline
matrix inventory
MUMPS summary
Gate report
```

## 15.1 Task outcomes

建立：

```text
docs/task029_stage4_direct_memory_forensics/outcomes/
```

至少包含：

```text
README.md
summary.md
parameters.json
environment.json
changed_files.md
run_log.txt
test_summary.md
gate_decision.csv
merge_recommendation.md
next_decision.md

baseline_memory_timeline.csv
baseline_matrix_inventory.csv
baseline_factorization_summary.csv
rank_scaling.csv
optimization_hypotheses.csv
optimization_manifest.csv
candidate_comparison.csv
object_lifecycle.md
h2_memory_prediction.md
h2_launch_decision.md
comsol_comparison_notes.md（可选）
```

## 15.2 Record schema

每个 direct profile record 至少包含：

```text
benchmark_id
source commit / branch / tracked dirty
physical_model
resolved_config
h_nm
mpi_size / thread count
solver package
ordering
PETSc options
MUMPS options and supported info fields
n_fe / n_aux
matrix inventory
factor inventory
memory checkpoints
max simultaneous total RSS
sum rank peak upper bound
cgroup peak
swap delta
timings
true residual
official R/T/A
energy closure
Task28 reference delta
status / qualification / limitations
```

---

# PART IX：测试要求

## 16. 单元/轻量测试

必须增加：

```text
memory snapshot schema test
stage marker test
matrix info serialization test
candidate profile parser test
object cleanup/destroy idempotency test
h2 launch gate unit test
h2 blocked path test
memory prediction test
record/checker contract test
```

## 16.1 数值等价测试

小矩阵/小 Stage4 smoke 验证：

```text
baseline augmented assembly vs optimized assembly action
RHS equality
solution equality
residual equality
RTA equality
MPI2/MPI4 lifecycle
exception path cleanup
```

## 16.2 运行级验证

最低要求：

```text
h5 baseline telemetry run
h5 candidate runs
h3 baseline telemetry run
h3 selected candidate full runs
```

h2 不是最低要求。

---

# PART X：禁止事项

## 17. 不得扩大任务范围

Task029 不做：

```text
- 新预条件器；
- Task27 iterative 参数优化；
- adaptive/graded mesh；
- h=1.5；
- 角度/波长/材料扫描；
- 新物理边界；
- 修改 official RTA 定义；
- 自研完整 FEM 框架；
- 整体 merge 历史 research branch；
- 默认运行 h=2；
- 静默修改 ordinary direct default。
```

## 17.1 不允许的优化方式

```text
- 关闭 true residual；
- 不计算 official RTA；
- 只跑 assemble-only 却报告 solve memory；
- 用 swap/OOC 冒充 RAM 降低而不报告时间和磁盘；
- 通过降低物理精度、减少模式或改网格获得“内存优化”；
- 覆盖 Task28 canonical records；
- 用各 rank 历史峰值统计口径变化伪造改进；
- 在未确认 ownership 时 destroy PETSc 对象；
- 使用未固定环境的 solver 结果作为 canonical。
```

---

# PART XI：执行与决策顺序

## 18. 推荐 commit 节奏

建议至少拆分：

```text
Commit A: telemetry only
Commit B: baseline h5/h3 evidence
Commit C: low-risk lifecycle/preallocation changes
Commit D: solver/profile experiments
Commit E: selected h5/h3 candidate qualification
Commit F: optional guarded h2 run or explicit not-run decision
Commit G: benchmark/docs/outcomes finalization
```

不得在一个巨大 commit 中混合遥测、算法修改和结果文件。

## 19. 阶段停止条件

### Stop A：基线不可信

若新遥测改变了数值或无法捕获 factorization 峰值，先修复遥测，禁止继续优化。

### Stop B：公共优化无收益

若 H1–H3 后 h3 内存下降 <10%，记录：

```text
public assembly/lifecycle overhead is not the main bottleneck
```

然后将重点转向 factorization/ordering，而不是继续大规模重写装配。

### Stop C：所有 direct profile 收益不足

若最优 h3 下降 <20%，Task029 仍可作为 `diagnostic_success` 收口，并建议后续将资源投入迭代法/多层方法。

### Stop D：h2 Gate 不通过

不运行 h2，输出预测与建议机器内存。

---

# PART XII：最终验收

## 20. Task029 最低完成标准

必须完成：

```text
1. Task28 已合并 master，Task29 从新 master 建独立分支；
2. h5/h3 baseline direct 内存阶段剖析；
3. simultaneous total RSS 与 sum-rank-peak upper bound 分开；
4. matrix/factor inventory；
5. 主要内存瓶颈定量结论；
6. 至少三类优化假设被验证或否定；
7. 至少一个低风险优化候选完成 h5/h3 全流程；
8. 所有候选对 Task28 residual/RTA reference；
9. h2 有明确 guarded launch / not-run 决策；
10. Benchmark 050、outcomes 和最终 merge recommendation 完整。
```

## 20.1 推荐合并标准

只有满足以下条件，优化代码才建议进入 master：

```text
- h5/h3 数值等价；
- h3 total peak RSS 至少下降 20%，或提供其他明确公共收益；
- 生命周期和异常路径测试通过；
- ordinary default 不改变；
- 新低内存 profile 显式 opt-in；
- 文档说明环境与统计口径；
- ChatGPT review 通过；
- 用户明确许可。
```

如果仅完成诊断，没有稳定内存收益：

```text
合并 telemetry / docs / benchmark infrastructure；
不合并无收益或高风险优化路径。
```

## 21. Codex 最终回应

Codex 完成后提交：

```text
docs/task029_stage4_direct_memory_forensics/outcomes/*
```

等待 ChatGPT 创建：

```text
docs/task029_stage4_direct_memory_forensics/review_report_v1.md
```

不得自行宣称最终通过或直接合并 master。

---

# 22. 最终任务摘要

```text
先测量，不猜测；
先 h5，再 h3；
先公共生命周期/预分配，再 factorization profile；
h2 默认禁止，只有显著降内存且预测 <=13.5 GB 才解锁；
所有优化必须保持 Task28 的 full residual 和 official R/T/A；
直接法优化的长期价值是建立 reference 和清理共享架构，
上千万 DoF 的生产主线仍需要后续低内存迭代/多层方法与分级/自适应网格。
```
