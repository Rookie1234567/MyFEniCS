# Task034 补充任务书：固定结构 p–h 收敛、MPI 资格化与长期 Benchmark

## 0. 权威与执行关系

本文件由 ChatGPT 在 Task034 实施开始前补充，属于 Task034 的正式任务权威，与 [`task.md`](task.md) 同时执行。

如本补充书与原 `task.md` 的阶段顺序或措辞存在冲突，以本补充书为准。Codex 不得删除、覆盖或改写本文件；需要解释或提出偏差时，应在 `response_vN.md` 中回应。

本补充书加入一个新的前置阶段：

```text
fixed-geometry uniform p–h convergence
+ full3D–Hybrid same-degree closure
+ MPI1/MPI8/MPI16 identity and scalability
+ canonical benchmark freeze
```

该阶段必须在原 Task034 的 graded-h / adaptive 阶段之前完成或形成明确的 fail-closed / controlled-resource-negative 结论。

---

# 1. 关于 fixed-p adaptive 的术语修正

固定有限元阶次 `p`，但根据离散场误差指标逐轮局部加密网格，属于真正的：

```text
fixed-p h-adaptivity
```

它不是：

```text
hp-adaptivity
```

也不等于：

```text
一次性手工 graded mesh
```

三者必须区分：

| 路径 | p 是否变化 | 网格是否由场指标逐轮更新 | 正式身份 |
|---|---:|---:|---|
| 手工 graded mesh | 否 | 否 | mesh mechanism / engineering prior |
| fixed-p h-adaptivity | 否 | 是 | genuine h-adaptivity |
| hp-adaptivity | 是 | 是或局部联合决策 | 本任务不实施 arbitrary variable-p H(curl) |

不过，在开发 h-adaptivity 之前，必须先对同一个固定物理结构建立可信的 uniform p–h 收敛参考和 MPI 基线。否则 adaptive 的“误差下降”和“同误差压缩”没有稳定参考。

---

# 2. 插入后的阶段顺序

Task034 的阶段顺序修正为：

```text
Phase A  WSL native environment qualification
-> Phase B  post-merge hardening
-> Phase C  Task033 anchor reproduction
-> Phase D  p3/h3 staged finer reference
-> Phase E  p4/h5 staged workstation study
-> Phase F  fixed-geometry p2/p3/p4 convergence + MPI benchmark freeze
-> Phase G  conforming graded-h + genuine fixed-p h-adaptivity
-> Phase H  resource-model recalibration and 0.7 nm assessment
```

原 `task.md` 的 Phase F adaptive 视为本文件中的 Phase G；原 Phase G resource recalibration 视为本文件中的 Phase H。原有 Gate、禁止项和交付要求继续有效。

---

# 3. Phase F 的固定物理结构

## 3.1 冻结几何与材料

所有 Phase F 正式收敛和 MPI 比较使用同一个冻结模型：

```text
full domain = 50 x 25 x 140 nm
period x/y = 50 / 25 nm
Si grating = 17 x 25 x 120 nm
wavelength = 13.5 nm
Si refractive index = 0.999002304859 + 0.00182649365j
incidence = 10 deg grazing from surface
phi = 0 deg
primary polarization = S
external ports = existing double-Floquet Fourier-DtN
full3D path = complete 3D Nedelec FEM
Hybrid path = bottom/top local 3D FEM + middle generic 2D modal region
```

不得在不同 `p`、不同 `h`、不同 MPI 或 full3D/Hybrid 之间静默改变：

- 物理尺寸；
- 材料；
- 入射角；
- 端口位置和定义；
- incident normalization；
- quadrature policy；
- observable sampling planes；
- significant-order selection rule；
- true-residual 定义；
- official R/T/A 后处理路径。

任何必要变化都必须形成新 benchmark identity，不能混入同一收敛序列。

## 3.2 P 偏振范围

主收敛矩阵使用 S 偏振，以控制重型运行数量。P 偏振必须至少完成：

1. 每个 `p=2,3,4` 最终选定 canonical anchor 在 MPI8 下的 full3D 与 Hybrid；
2. 至少一个代表性同阶 anchor 的 MPI1/MPI8/MPI16 完整 P 偏振 identity matrix；
3. 若 P 与 S 在模式容量、收敛或 MPI 行为上出现不同结论，扩大 P 矩阵并单独分类。

不得用只有 S 偏振的结果声称所有偏振均稳定。

---

# 4. p=1 的边界

用户判断 p1 可能不适合当前 Hybrid 本征模态耦合。Task034 不预设 p1 必然可用，也不允许为了补齐表格强行运行 p1 Hybrid。

Codex 必须先做 capability audit：

```text
p1 full3D legacy support
p1 cross-section QEP space compatibility
p1 matching trace compatibility
p1 Hybrid interface rank/capacity
p1 physical accuracy value
```

正式决定只能是：

```text
p1_full3d_regression_only
p1_hybrid_supported_but_not_accuracy_useful
p1_hybrid_not_qualified_fail_closed
```

Phase F 的 canonical Hybrid convergence 从 `p=2` 开始。p1 只保留 full3D/解析 regression 或经审查的诊断，不阻塞 p2–p4 benchmark。

---

# 5. Phase F1：uniform p–h 收敛矩阵

## 5.1 主矩阵

主矩阵在 **MPI8** 上执行。每个点均尝试 full3D 和 Hybrid；所有重型运行仍遵守 one-heavy-case-at-a-time、assembly/factor/full-solve 分级和工作站资源 Gate。

| degree | uniform h 候选（nm） | full3D | Hybrid | 说明 |
|---:|---|---|---|---|
| p2 | 5, 3, 2 | required staged attempts | required M funnel | 从已验证 p2 路线建立 h 收敛；p2/h2 在新工作站重新资格化 |
| p3 | 10, 7.5, 5, 3 | required staged attempts | required M funnel | h3 沿用 Task034 Phase D 的 staged decision |
| p4 | 10, 7.5, 5 | required staged attempts | required M funnel | 先用较粗 h 建立 p4 closure，再尝试 p4/h5；不运行 p4/h3 |

“required staged attempt”不等于无条件完整求解。每个候选依次经过：

```text
preflight
-> assembly-only
-> factorization-only / KSPSetUp-only
-> full solve
```

Hybrid 依次经过：

```text
QEP/matched-trace prerequisites
-> M80
-> M120
-> M160
-> M240 only if formally required by M120->M160 modal-convergence Gate
```

若某点受资源 Gate 阻止，保存 measured negative，并停止该点后续步骤；不得 OOM 后才记失败。

## 5.2 至少一个 p4 同阶闭合

即使 p4/h5 full3D 因资源失败，Task034 也必须尽力在资源安全的较粗网格上完成至少一个：

```text
p4 full3D
vs
p4 Hybrid selected-M
```

same-degree closure。优先顺序：

```text
p4/h10
-> p4/h7.5
-> p4/h5
```

p4/h5 仍是最终目标点，但 p4/h10 或 p4/h7.5 closure 可证明高阶耦合链在真实固定结构上工作。不得把较粗 p4 closure 冒充 p4/h5 通过。

## 5.3 收敛可观测量

每个 full3D 与 Hybrid 成功点都必须输出同一完整向量：

```text
full explicit true residual
official R_total, T_total, A_balance
A_volume
R+T+A_volume closure
all propagating diffraction-order powers
significant-order complex amplitudes
five fixed planes E relative fields
five fixed planes H relative fields
bottom/top tangential E
bottom/top tangential H
DoF, rows, NNZ, factor inventory
peak memory, job swap, wall time
mode count and QEP diagnostics for Hybrid
```

收敛判断不得只使用 R/T/A，也不得只看某一条中心线。

## 5.4 h 收敛与 p 收敛

必须分别分析：

1. 固定 `p`、减小 `h` 的 h 收敛；
2. 在共同 `h=5 nm` 上比较 p2/p3/p4 的 p 趋势；
3. full3D 与 Hybrid 在相同 `p/h` 下的同阶闭合；
4. 资源成本是否随 p/h 呈现可解释趋势；
5. 是否进入可辨认的 asymptotic regime。

只有同一序列至少有三个成功点，并且误差趋势可辩护时，才允许报告 observed convergence order。若误差非单调、reference 仍不够细或某点 resource-negative，应明确写：

```text
convergence_order_not_established
```

不得通过删除非单调点制造收敛阶。

## 5.5 参考身份

最细成功 full3D 结果只能称为：

```text
best_available_discrete_reference_for_case093
```

除非有独立证据，否则必须继续保留：

```text
grid_convergence_proven = false
continuum_reference = false
```

---

# 6. Phase F2：full3D–Hybrid 同阶闭合

每个 `p/h` 点的 Hybrid 只有在以下条件满足时才可进入收敛表：

- exact requested mode count delivered；
- right/left QEP residual Gate；
- Poynting/passive branch Gate；
- biorthogonality Gate；
- modal propagation 无 growing factor；
- Hybrid full true residual `<=1e-9`；
- interface projection 与 traction equilibrium Gate；
- official R/T/A 合法；
- selected M 通过 funnel；
- 若同阶 full3D 存在，则完整 observable closure 通过。

同阶 closure 必须报告至少：

```text
max abs R/T/A delta
A_volume abs delta
significant-order power max/RMS error
significant-order complex-amplitude max/RMS error
five-plane E max relative L2
five-plane H max relative L2
interface E_t max relative L2
interface H_t max relative L2
```

若 full3D 被 resource Gate 阻止，Hybrid 可以保留 measured engineering result，但该点必须标记：

```text
same_degree_full3d_closure_not_available
```

---

# 7. Phase F3：MPI1 / MPI8 / MPI16 资格化

## 7.1 MPI 集合

用户要求至少比较：

```text
MPI1
MPI8
one larger MPI
```

Task034 将正式集合冻结为：

```text
MPI1 / MPI8 / MPI16
```

要求：

- 禁止 oversubscription；
- MPI16 必须在 Phase A 先通过 microfixture、MUMPS、PEP 和 rank-library identity；
- 若 WSL 可见物理核心少于 16 或 MPI16 环境资格化失败，不能静默替换并声称完成；应记录 `mpi16_not_qualified`，Task034 最终状态至少为 partial；
- 若工作站有不少于 32 个可用物理核心且 NUMA/内存证据允许，可增加 MPI32 exploratory，但它不能替代 MPI16；
- thread counts 默认均为 1，除非另行资格化。

## 7.2 canonical anchor 选择

完成 F1 后，为每个 degree 选择一个最细、同阶 closure 已通过或最接近通过的 anchor：

```text
p2 target anchor = p2/h2；若受控失败则使用最细成功点
p3 target anchor = p3/h3；若受控失败则使用 p3/h5
p4 target anchor = p4/h5；若受控失败则使用最细成功且有 closure 的 p4 点
```

对每个 `p=2,3,4` 的 selected anchor，以下两种方法均必须分别尝试 MPI1/MPI8/MPI16：

```text
full3D
Hybrid selected-M
```

每次都是独立新进程、同一 clean SHA、同一物理配置和相同输出定义。不得在一个 MPI 进程中伪造不同 size。

## 7.3 MPI identity Gate

MPI 比较的第一目标是数值身份与可移植性，不要求 wall-time 单调加速。

必须完全一致或满足预声明容差的项目包括：

- mesh/config hash；
- global DoF、rows、NNZ；
- Floquet slave/master/constraint NNZ；
- number of propagating/significant orders；
- Hybrid requested/selected mode count；
- source/environment identity；
- full true residual 均通过；
- official-result identity 均为 true。

默认数值 Gate：

| 指标 | MPI1/MPI8/MPI16 最大允许差 |
|---|---:|
| R/T/A absolute drift | `1e-8` |
| A_volume absolute drift | `1e-8` |
| significant-order power absolute drift | `1e-8` |
| non-negligible complex-amplitude max relative drift | `1e-7` |
| non-negligible complex-amplitude phase drift | `1e-7 rad` |
| selected-plane E/H relative L2 drift | `1e-6` |
| interface E_t/H_t relative L2 drift | `1e-6` |
| QEP beta relative drift | 沿用或严于 Task033 accepted Gate |
| biorthogonality / tracking | 不得比 Task033 accepted Gate 回归 |

若某个量接近零导致相对误差失真，必须同时报告绝对误差和明确的 significance threshold，不能用除以极小数制造失败或通过。

## 7.4 MPI scalability 记录

每个 MPI size 必须记录：

```text
assembly time
factorization / KSPSetUp time
solve time
QEP time
matched-trace time
field/postprocess time
wall time
per-rank RSS/PSS
process-tree peak
job/cgroup memory authority
swap
communication bytes where available
load imbalance
MUMPS/SLEPc solver identity
```

允许结论包括：

```text
mpi_numerical_identity_pass_no_speedup
mpi8_best_engineering_point
mpi16_memory_positive_time_negative
mpi16_scalability_positive
mpi16_resource_or_solver_negative
mpi1_resource_negative
```

不得把 MPI rank 更多自动解释为并行更好，也不得因 MPI1 内存失败而否定 MPI8/MPI16 的数值正确性。

---

# 8. Phase F4：稳定结果冻结为 Case093 Benchmark

新增长期 benchmark：

```text
benchmarks/cases/093_fixed_geometry_ph_convergence_mpi/
```

Case093 与 Task034 的 Case092 分工：

| Case | 身份 |
|---|---|
| Case092 | Task034 工作站、hardening、p3/h3、p4、自适应和资源研究总记录 |
| Case093 | 固定结构 p2/p3/p4 uniform convergence、full3D–Hybrid closure 与 MPI identity 的长期稳定 benchmark |

Case093 至少包含：

```text
README.md
config.json
schema.json
expected.json
test_command.txt
records/convergence_summary.json
records/mpi_identity_summary.json
records/canonical_benchmark_manifest.json
```

稳定结果只有在以下条件全部满足后才能标记 canonical：

1. clean source before/after；
2. WSL native environment qualified；
3. full explicit true residual passed；
4. official R/T/A identity valid；
5. full3D–Hybrid same-degree closure passed，或明确记录 resource-unavailable；
6. MPI identity Gate passed for要求的 anchor；
7. independent fresh-process rerun 不改变结论；
8. compact evidence 与重型 artifact hash 绑定；
9. checker 从记录重新计算结论，而不是只信 `status` 字段；
10. ordinary default unchanged。

Canonical benchmark 不提交 mesh、field、matrix、factor、完整 timeline 或大日志。重型内容留在：

```text
benchmarks/artifacts/cases/093/
```

Git 只保留轻量 hash-bound records。

若 p4/h5 受资源 Gate 阻止，Case093 可以冻结：

- p4 较粗同阶 closure positive；
- p4/h5 resource negative；
- p4/h5 Hybrid-only measured result；

但不得把 p4/h5 写成完整 canonical positive。

---

# 9. Phase G adaptive 的解锁条件

原 Task034 adaptive 阶段在本补充书中改称 Phase G。只有以下条件满足后才能启动 measured adaptive compression：

```text
p2 uniform convergence sequence has a measured decision
p3 uniform convergence sequence has a measured decision
p4 has at least one same-degree closure or a controlled staged negative
selected discrete reference is frozen
Case093 observable vector and checker are available
MPI8 production-development baseline is selected
```

conforming graded-h mechanism 的代码开发可以与 Phase F 后期轻量并行进行，但不得在 Phase F 完成前把任何压缩结果标记为同误差 adaptive success。

Phase G 中的“真正 adaptive”仍必须满足原 `task.md`：每轮 refinement 由场相关 indicator 驱动，而不是只按几何距离手工划分。

---

# 10. 新增测试要求

除原 Task034 测试外，至少新增：

1. p1 Hybrid capability audit fail-closed contract；
2. p2/p3/p4 fixed-geometry config identity；
3. p–h convergence aggregator 不允许混合物理配置；
4. 少于三个成功 h 点时不得报告 observed order；
5. 非单调点不得被静默删除；
6. full3D–Hybrid observable vector 完整性；
7. MPI1/MPI8/MPI16 mesh/DoF/constraint identity；
8. MPI numerical drift 正向与伪造失败测试；
9. near-zero complex amplitude 的 significance threshold；
10. MPI16 禁止 oversubscription；
11. MPI16 未资格化时不得声称三档 MPI 完成；
12. p4/h5 resource negative 与较粗 p4 closure 不得混写；
13. Case093 canonical status 必须由 checker 重算；
14. heavy artifact 不得进入 Git；
15. benchmark ordinary default unchanged；
16. S/P identity 不得混合；
17. WSL 环境变化必须产生不同 environment ID；
18. fresh-process rerun evidence binding。

最终 formal test matrix 必须显式包含：

```text
MPI1
MPI8
MPI16
```

以及当前仍要求的 MPI2/MPI4 micro/component regression。

---

# 11. 新增交付文件

Task034 必交付列表增加：

```text
docs/task034_workstation_wsl_adaptive_scalability/outcomes/fixed_geometry_ph_convergence.md
docs/task034_workstation_wsl_adaptive_scalability/outcomes/fixed_geometry_ph_convergence.csv
docs/task034_workstation_wsl_adaptive_scalability/outcomes/full3d_hybrid_closure_matrix.md
docs/task034_workstation_wsl_adaptive_scalability/outcomes/mpi_scalability_and_identity.md
docs/task034_workstation_wsl_adaptive_scalability/outcomes/benchmark_freeze_decision.md

benchmarks/cases/093_fixed_geometry_ph_convergence_mpi/README.md
benchmarks/cases/093_fixed_geometry_ph_convergence_mpi/config.json
benchmarks/cases/093_fixed_geometry_ph_convergence_mpi/schema.json
benchmarks/cases/093_fixed_geometry_ph_convergence_mpi/expected.json
benchmarks/cases/093_fixed_geometry_ph_convergence_mpi/test_command.txt
benchmarks/cases/093_fixed_geometry_ph_convergence_mpi/records/convergence_summary.json
benchmarks/cases/093_fixed_geometry_ph_convergence_mpi/records/mpi_identity_summary.json
benchmarks/cases/093_fixed_geometry_ph_convergence_mpi/records/canonical_benchmark_manifest.json
```

`outcomes/summary.md` 必须新增三张主表：

```text
p2/p3/p4 uniform convergence matrix
full3D vs Hybrid same-degree closure matrix
MPI1/MPI8/MPI16 numerical identity and resource matrix
```

每张表标明：

```text
unit
baseline
data identity
source SHA
environment ID
evidence path
positive / negative / not_run reason
```

---

# 12. 修正后的 Task034 最低完成条件

在原 Task034 完成条件基础上，新增：

```text
fixed physical model frozen
p2 uniform full3D/Hybrid convergence received a measured decision
p3 uniform full3D/Hybrid convergence received a measured decision
p4 full3D/Hybrid received at least one same-degree closure or controlled staged negative
MPI1/MPI8/MPI16 received explicit qualification decisions
at least one canonical anchor per qualified degree is frozen
Case093 checker and compact records exist
adaptive result is not claimed before the uniform benchmark reference exists
```

若 MPI16 因硬件或环境无法资格化、p3/h3 或 p4/h5 因资源受控停止，Task034 仍可得到：

```text
PARTIAL_WITH_CONTROLLED_RESOURCE_NEGATIVES
```

但不得标记完整 `PASS`。

---

# 13. Codex 执行与审查要求

Codex 开始 Task034 前必须同时阅读：

```text
docs/task034_workstation_wsl_adaptive_scalability/task.md
docs/task034_workstation_wsl_adaptive_scalability/task_fixed_geometry_convergence_addendum.md
```

Codex 创建分支后，应在首个 `response_v1.md` 或 `outcomes/environment_and_base.md` 明确写出：

```text
task034_addendum_loaded = true
phase_order_uses_fixed_geometry_benchmark_before_adaptive = true
mpi_matrix = [1, 8, 16]
case093_planned = true
```

完成后仍需推送指定 Task034 分支，停止等待 ChatGPT review，不得自行合并 `master`。