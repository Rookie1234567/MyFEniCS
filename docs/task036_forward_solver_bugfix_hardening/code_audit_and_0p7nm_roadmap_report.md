# MyFEniCS 全仓代码审阅与 0.7 nm / 2 TB 路线报告

> 报告性质：用户要求的参考性、只读代码审阅汇总。
> 本文不是新的 `review_report_vN.md`，不改变 Task036 任务书、最新 review、response 或既有 Gate 的权威顺序。
> 审阅日期：2026-07-31。
> 审阅代码快照：`6efcafff318dce684ad35648e4568baebe8f5d20`。
> 审阅期间没有修改代码，没有运行 MPI/PDE/MUMPS 重型算例。

## 1. 执行摘要

当前代码还不能直接、可信地完成“0.7 nm 波长、整机最多 2 TB 内存”的目标。

这不是再调整少量网格或 solver 参数就能解决的问题，而是以下三层前置条件尚未同时满足：

1. 正式结果、provenance 和资源证据仍存在若干 fail-open 缺陷，例如 solver 失败仍可能写 `pass`、缺失体吸收量可能被当成零、旧 watchdog 不能保证杀掉完整 MPI 进程组。
2. 当前 whole-domain Full3D 和 direct Hybrid 数据布局仍包含全局复制、稠密 \(M^2\)、`N×M` 全模态 RHS、direct MUMPS factorization 等结构。已有 projection 显示它们距离 2 TB 不是边缘超限，而是数量级不合适。
3. Task036 最新实算已经表明，简单移动 Hybrid 接口没有解决主要物理误差：30/90 nm 和 40/80 nm 两个点都只有 79/96 固定通道通过，不能把相同思路直接扩到 0.7 nm。

项目已经具备大量可复用基础，包括 H(curl)、Floquet、DtN、static condensation、Hybrid strong trace、full explicit residual、严格 checker 和资源采样。更现实的路线是：

> 先修正式证据和资源安全性 → 冻结 0.7 nm 材料与物理合同 → 验证 2D/2.5D 降维 → 解决 Task036 暴露的接口缺失空间 → 把 modal/Hybrid 改为分布式、流式、矩阵自由架构 → 再做小规模 0.7 nm anchor 和逐级扩容。

2 TB 应视为这条路线完成后的条件性机会，而不是当前代码的直接运行预算。

## 2. 审阅范围、仓库状态和限制

### 2.1 仓库快照

- 分支：`codex/20260730-task36-forward-solver-bugfix-hardening`。
- 最终审阅 HEAD：`6efcafff318dce684ad35648e4568baebe8f5d20`。
- 审阅期间 HEAD 从 `3259bcb...` 前进到当前 SHA；代码未发生变化，只增加了 Task036 的 `response_v5.md`。
- 审阅时工作树已有一处未提交文档修改：
  `docs/task036_forward_solver_bugfix_hardening/outcomes/hybrid_production_readiness_assessment.md`。
- 该处现有差异只是第 194 行的行尾空格；本次审阅没有触碰。

### 2.2 覆盖范围

- 337 个 tracked Python 文件。
- Python 总计 186,719 行。
- 134 个测试文件。
- 对全部 tracked Python 做 AST、结构和危险模式扫描。
- 分区深读：
  - `src/common`、`constraints`、`geometry`、`postprocessing`、`validation`、`studies`；
  - `src/modes`、`coupling`、`solvers`、`adaptivity`；
  - `benchmarks`、`src/runners`、`src/tools`、`src/test`；
  - activation、benchmark shell 和根目录 demo 入口。
- 排除 ignored 的大型 mesh、field、matrix、factor 和原始 artifacts；这些不属于源代码审阅对象。

### 2.3 轻量检查结果

- 337 个 Python 文件：0 个 AST/语法错误。
- `ruff check --no-cache src benchmarks`：通过。
- 选定轻量测试：39 passed。
- 文档合同测试：13 passed、1 failed。
- 唯一失败是 case registry 没有登记已经存在的 Case098 和 Case099：
  [`src/test/test_26_documentation_contract.py`](../../src/test/test_26_documentation_contract.py#L276)。
- 没有运行 full pytest、MPI、PDE、MUMPS 或重型 mesh。

### 2.4 三个轻量行为复现

1. 证实 SLEPc `setFromOptions()` 可以覆盖程序预设，而当前 QEP report 仍写死旧 solver 配置。
2. 证实两个吸收区域均缺失时，通用 Full3D `A_volume` 路径会返回 `status="ok"` 和 `A_volume_total=0.0`。
3. 证实同一秒的两个 `unique_run_dir()` 调用在目录尚未创建时可以返回完全相同的路径。

同时排除了一个最初疑点：petsc4py 复数 `Vec.dot()` 的语义使
[`run_workstation_iterative.py`](../../benchmarks/run_workstation_iterative.py#L425)
中的共轭处理恰好正确，不能把该 Gram–Schmidt 实现列为 bug。

### 2.5 审阅能力边界

静态审阅和轻量测试可以确认控制流、状态语义、资源生命周期、数据布局和若干可复现缺陷，但不能替代：

- 实际 MPI 分区行为；
- 大规模 KSP/PEP/MUMPS 的收敛与内存曲线；
- 0.7 nm 材料数据正确性；
- Full3D/Hybrid 的连续体收敛；
- 与独立电磁软件或实验结果的同物理验证。

因此本文对“确认 bug”和“高风险扩展性判断”分别标注，不把未运行的路线写成已经通过。

## 3. Task036 当前真实状态

最新状态来自 [`response_v5.md`](response_v5.md#L5)：

- I0：30/90 nm 和 40/80 nm assemble-only 均通过。
- I1：30/90 nm 实算为 `physics_fail/resource_pass`。
- I2：40/80 nm 实算为 `physics_fail/resource_fail`。
- 两点都只通过 79/96 固定通道，没有达到 96/96。
- 当前结论为 `ASYMPTOTIC_INTERFACE_HYPOTHESIS_NOT_SUFFICIENT`。
- R0 因物理 Gate 未运行；R1 因 R0 Gate 未运行，见
  [未运行清单](response_v5.md#L257)。

由此得到的直接决策是：

1. 不应重复 30/90、40/80 或继续做同性质的接口位置扫描。
2. 不应直接增大全局 M，希望通过“多放模式”自动解决。
3. 若继续，应由正式 review 决定是否建立 transfer-eigenmode / optimal-port basis，即 `response_v5` 所指向的 R2 方向。
4. 当前 Task036 analyzer 对 residual、R/T/A、`A_volume`、接口误差和资源字段是 fail-closed 的。因此本文发现的通用 `A_volume` 缺陷不能直接反推“Task036 已有正式记录全部失效”；它主要影响底层通用 Full3D API 和其他消费者。

## 4. 缺陷总览

| 优先级 | 问题 | 分类 | 主要影响 |
|---|---|---|---|
| P0 | watchdog 不能保证终止完整 MPI 进程组 | 确认缺陷 | controlled stop 后仍可能残留 ranks/MUMPS |
| P0/P1 | solver 失败仍可写 `pass`、退出 0 | 确认 false-pass | 正式状态与真实数值结果不一致 |
| P1 | Full3D `A_volume` 缺失被当成零或部分和 | 确认缺陷 | 错误 energy closure 和 official 标志 |
| P1 | QEP 实际 solver 配置与 report 不一致 | 已轻量复现 | provenance、性能归因和资格化失真 |
| P1 | existing artifact、输出目录和 source identity 不安全 | 确认缺陷 | 旧/残缺/并发证据被误复用或混写 |
| P1 | DOLFINx interpolation callback 内执行 MPI collective | 高风险确认设计缺陷 | 部分 MPI 分区可永久死锁 |
| P1 | QEP/Hybrid 异常路径缺少事务式清理 | 确认生命周期缺陷 | factor、Mat、Vec、field 峰值重叠 |
| P1 | p5/p6 fixed-target 和材料身份判定过宽 | 确认资格缺陷 | 0.7 nm 可能误用 13.5 nm 资格与材料 |
| P1 | Task036 并行 dispatcher 只租 CPU、不管总内存 | 确认设计缺口 | 多 job 合计可超过 2 TB |
| P1 | local static condensation 不对奇异块 fail closed | 高风险数值缺口 | NaN/Inf Schur block 可进入全局矩阵 |
| P1 | 每 rank 复制全局网格、后处理复制多套全场 | 确认扩展性阻塞 | MPI rank 增加仍放大聚合内存 |
| P1 | 0.7 nm 可继续误用 zero-order DtN | 高风险配置陷阱 | 代数收敛但开放边界物理不完整 |

## 5. 详细缺陷分析

### 5.1 P0：watchdog 不能保证完整终止 MPI 作业

多个旧 watchdog 启动子进程时没有创建独立 session，超限后只对直接 `mpiexec` 父进程调用 `terminate()`：

- [Task031 watchdog](../../benchmarks/run_task031_memory_forensics.py#L221)
- [Task032 watchdog](../../benchmarks/run_task032_memory_forensics.py#L101)
- [Task033 memory watchdog](../../benchmarks/run_task033_memory_watchdog.py#L2937)
- [Task033 Full3D watchdog](../../benchmarks/run_task033_full3d_watchdog.py#L2543)

这意味着记录可能写成 `controlled_stop`，但 MPI ranks、MUMPS 或其他 descendants 仍继续占用内存。

仓库已有可复用的较好实现：
[Case090 watchdog](../../benchmarks/run_task033_case090_watchdog.py#L474)
使用 `start_new_session=True`、`killpg(SIGTERM)`、等待、再 `SIGKILL`。

Task031/032 还会把整个 WSL `/init.scope` 的 `memory.current` 当成本 job 的终止依据。若同一 WSL 中另一个对话或程序占用大量内存，本 job 会被误停。

建议统一为：

- 独立 process group 或 dedicated cgroup；
- TERM → 限时等待 → KILL；
- 最后验证全部 descendants 已消失；
- 只有 dedicated job cgroup 或完整 process-tree simultaneous memory 才能作为终止 authority；
- host/WSL 全局内存只能作为诊断量，不能直接作为单 job pass/fail authority。

### 5.2 P0/P1：solver 失败仍可能写 `pass` 并退出 0

[`run_workstation_iterative.py`](../../benchmarks/run_workstation_iterative.py#L903)
的顶层 `status` 只依赖参数是否符合 qualified profile，而不要求：

- `ksp_reason > 0`；
- full explicit true residual 达标；
- `official_rta` 存在；
- 物理和能量 Gate 通过。

[main 返回值](../../benchmarks/run_workstation_iterative.py#L1139)
还无条件返回 0。

Task031 的 `--screen-only` 路径更明显：
[残差只要下降](../../benchmarks/run_task031_memory_forensics.py#L257)
就会升级为 `numeric_pass`。残差下降只能说明迭代趋势改善，不能说明：

- KSP 收敛；
- full residual 达标；
- official R/T/A 存在；
- 任何物理 Gate 通过。

建议统一状态机：

| 状态 | 含义 |
|---|---|
| `screen_trend_positive` | 仅观察到残差下降 |
| `numeric_not_pass` | 数值 Gate 未通过 |
| `physics_not_pass` | 数值可解，但物理 Gate 未通过 |
| `resource_controlled_stop` | 因资源 Gate 受控停止 |
| `formal_pass` | residual、物理、资源、source identity 全部通过 |

只有 `formal_pass` 才允许 exit 0 和 official observable。

### 5.3 P1：Full3D 体吸收缺失会被静默当成零

在 [`rta_3d.py`](../../src/postprocessing/rta_3d.py#L84)：

- 区域无 cell 时返回 `A_volume=None,status="missing"`；
- 汇总时过滤所有 `None` 后求和；
- 两个区域均缺失便得到 `A_volume_total=0.0`；
- payload 仍硬编码为 `status="ok"`，见
  [汇总逻辑](../../src/postprocessing/rta_3d.py#L166)；
- 这个假零随后进入 energy closure。

而 [`common_3d_case_flow.py`](../../src/solvers/common_3d_case_flow.py#L1604)
中的初始 `official_result` 主要跟随线性求解是否收敛；
[有损材料的 energy Gate](../../src/solvers/common_3d_postprocess.py#L387)
又不会强制 closure。

建议：

1. 根据 geometry/config 明确 required material regions。
2. 任一 required region 缺失、incident power 缺失或结果非有限时，volume payload 必须非 `ok`。
3. `official_result` 必须降级。
4. 禁止 partial sum 冒充 total absorption。
5. 增加“两区域都缺失”“一侧缺失”“incident power 缺失”“NaN absorption”的单元测试。

### 5.4 P1：QEP 实际配置与 report 不一致

[`quadratic_beta_eigenproblem.py`](../../src/modes/quadratic_beta_eigenproblem.py#L336)
先设置 TOAR、SINVERT、PREONLY、LU/MUMPS，随后调用 `pep.setFromOptions()`。全局 PETSc/SLEPc options 可以覆盖这些设置。

但 [结果报告](../../src/modes/quadratic_beta_eigenproblem.py#L409)
始终写：

- `SLEPc.PEP/TOAR`；
- `sinvert_with_MUMPS_LU`。

轻量复现中，将实际配置覆盖为 `linear/shift/gmres/jacobi` 后，运行对象 getter 已显示新值，但当前 report 仍会声称 TOAR/sinvert/MUMPS。

建议：

- `setFromOptions()` 后读取实际 PEP/ST/KSP/PC/factor solver；
- 分别记录 requested 和 actual；
- 若正式路径冻结 TOAR/SINVERT/MUMPS，则在 options 解析后验证并 fail closed；
- 增加 options-override 回归测试。

### 5.5 P1：artifact 和 source identity 可能被误复用或污染

#### Task036 existing directory

[Task036 dispatcher](../../benchmarks/run_task036_robustness_scan.py#L245)
只要目标目录存在就返回 `existing_artifact_not_rerun`，不验证：

- summary schema；
- source SHA；
- input/config identity；
- artifact hash；
- 是否完整结束；
- formal status。

空目录、旧 SHA、崩溃残留或不同输入的旧目录都可能使命令退出 0。

#### 输出目录 TOCTOU 竞态

[`unique_run_dir()`](../../src/common/output_paths.py#L7)
使用秒级时间戳，先检查存在性但不原子占有。两个同名作业在同一秒启动时可选择同一路径，随后共同写 summary、field 和 log。

旧 runner 还可能由各 MPI rank 独立选择路径，形成 rank 间目录分歧。

#### source attestation

[Task031 provenance](../../benchmarks/run_task031_memory_forensics.py#L35)
和 [workstation runner](../../benchmarks/run_workstation_iterative.py#L77)
可以因传入 `verified-clean-sha` 而忽略真实 dirty status，并且缺少 run 后的 HEAD/status 稳定性检查。

建议：

- rank 0 用 `mkdir(exist_ok=False)` 原子认领，再广播已创建路径；
- 目录名加入纳秒/UUID和 source SHA；
- 复用 artifact 前独立验证 schema、SHA、input identity、hash 和最终状态；
- 运行前后核验 HEAD、tracked status、环境和输入 hash；
- source 在运行中发生变化时，正式结果 fail closed。

### 5.6 P1：旧 trace extractor 有 MPI 死锁风险

[`modal_trace_projection.py`](../../src/coupling/modal_trace_projection.py#L254)
在 DOLFINx `interpolate()` callback 中执行 `comm.alltoall()`。

若某 rank 没有目标 trace cell，DOLFINx 可能不调用 callback；其他 rank 进入 collective 后便会永久等待。

仓库的新实现已经正确识别并规避该问题：
[`hybrid_internal_modes.py`](../../src/coupling/hybrid_internal_modes.py#L197)
把 collective 放到插值前预计算，callback 只读取本地缓存。

旧 extractor 仍被若干 Task032/036 研究 runner 调用。建议：

- 迁移到相同的预计算模式；
- callback 内禁止 collective；
- 增加 MPI2/MPI4 测试，其中至少一个 rank 没有 trace cell；
- watchdog 测试应能够区分真实 deadlock 与正常无输出计算。

### 5.7 P1：QEP、Hybrid 异常路径缺少事务式清理

多个 solve 函数只有成功尾部清理，没有覆盖中间失败：

- [QEP 构造和 solve](../../src/modes/quadratic_beta_eigenproblem.py#L227)
- [Hybrid augmented direct](../../src/solvers/hybrid_fem_modal_augmented_direct.py#L563)
- [Hybrid strong trace direct](../../src/solvers/hybrid_strong_trace_direct.py#L1403)
- [Hybrid modal Schur](../../src/solvers/hybrid_fem_modal_schur_direct.py#L572)

典型触发：

- KSP/MUMPS setup 或 solve 失败；
- bottom recovery 成功、top recovery 失败；
- residual audit 或 mode expansion 中途失败；
- reduction 或 full-vector expansion 中途失败。

这会让 factor、Mat、Vec 和部分 recovered field 在 Python GC 前重叠驻留。小模型可能只是泄漏，接近 2 TB 时会直接改变峰值和后续 case 的可运行性。

建议采用 staged ownership：

1. 每创建一个 PETSc/SLEPc 对象就进入 rollback 列表。
2. 完整成功后才把所有权转移到返回 dataclass。
3. setup、solve、bottom recovery、top recovery、residual 分别做 failure-injection 测试。
4. 区分 `release_solver_state()`、`detach_physical_fields()` 和 `release_physical_fields()`，避免 `destroy()` 被误解为释放全部结果内存。

另有几个 full-size Vec 未显式销毁：

- [`common_3d_solve.py`](../../src/solvers/common_3d_solve.py#L599)
- [`dtn_port_3d.py`](../../src/solvers/dtn_port_3d.py#L2290)

### 5.8 P1：高阶 fixed-target 和材料身份判定过宽

[`floquet_3d.py`](../../src/constraints/floquet_3d.py#L98)
仅依据 `stage_case` 和 `geometry_kind` 就把 case 认定为已经资格化的 p5/p6 fixed target。

以下信息没有进入身份判断：

- 波长；
- 材料；
- 周期和结构尺寸；
- 入射角和偏振；
- 网格轴；
- 单元族和 degree；
- 背景与边界模型。

因此仅把波长改为 0.7 nm，也可能误用 13.5 nm 的高阶资格。

与此同时，[`config_3d.py`](../../src/common/config_3d.py#L12)
只提供当前 13.5 nm Si 常数；runner 允许波长和折射率分别覆盖，没有 wavelength/material consistency Gate。

0.7 nm 必须建立 canonical target fingerprint，至少绑定：

- 波长、周期、结构尺寸、角度和偏振；
- 材料复折射率、来源、版本、密度/组成和插值规则；
- 网格、单元族、degree、边界/DtN 模型；
- 完整配置 hash。

### 5.9 P1：Task036 并行 dispatcher 不管理总内存

[`run_task036_robustness_scan.py`](../../benchmarks/run_task036_robustness_scan.py#L318)
的并行机制只租 CPU cores，允许 `max_parallel` 到 5，没有 aggregate RSS/cgroup memory lease。

多个 job 可以各自低于 per-job limit，但合计超过 2 TB。

在全局 coordinator 实现并验证前：

- 正式重型工作保持一次一个 heavy case；
- `max_parallel>1` 只能用于明确轻量阶段；
- per-job limit 不能替代 whole-host/job-group limit；
- 临时目录、JIT cache 和 MUMPS OOC 也应纳入总预算。

### 5.10 P1：local static condensation 不对奇异块 fail closed

[`hcurl_assembly_time_condensation.py`](../../src/solvers/hcurl_assembly_time_condensation.py#L1392)
对局部 \(A_{ii}\) 直接执行 `lu_factor/lu_solve`，没有：

- 捕获 `LinAlgWarning`；
- finite 检查；
- pivot/condition surrogate；
- 局部 factor residual Gate。

SciPy 对奇异矩阵可能只给 warning 并返回含 `inf/nan` 的结果。variable-p 路径虽有 residual，但 NaN 也可能绕过当前聚合逻辑。

0.7 nm、高 p、强材料对比或局部 resonance 下风险会放大。

建议对 LU、recovery 和 Schur block 全部执行：

- finite 检查；
- pivot/condition surrogate；
- 显式 \(A_{ii}X-B\) 相对残差；
- collective fail closed；
- 精确奇异和逐级恶化条件数的 synthetic 单元测试。

## 6. 直接阻塞 0.7 nm / 2 TB 的架构问题

### 6.1 当前 whole-domain direct Full3D 不可行

仓库估算表明，机械均匀细化到约 0.1 nm 时可能产生约 1.75 亿 hex cells 和数十亿 H(curl) DoF；Krylov basis 与 direct factors 会进入数 TiB 到数十 TiB：
[`project_service_requirements_and_forward_model_roadmap.md`](../project_service_requirements_and_forward_model_roadmap.md#L494)。

因此不能把当前 13.5 nm whole-domain Full3D 简单缩小网格后投入 2 TB 机器。

### 6.2 当前 direct Hybrid 数据布局同样不可行

已有 0.7 nm projection 给出的机械估计包括：

- 每方向约 16,029 modes 的 planning floor；
- 59,306 modes/direction 是压力测试说明，不是严格、普适的数学下界；
- 约 9.24 亿 local-system rows；
- 单个 all-mode dense multi-RHS 对象约 1,595.6 TiB；
- 显式对象累计体积约 1,611.3 TiB。

详见：

- [0.7 nm scalability assessment](../task032_hybrid_fem_modal_direct_baseline/outcomes/task032_0p7nm_scalability_assessment.md#L35)
- [显式对象体积估算](../task032_hybrid_fem_modal_direct_baseline/outcomes/task032_0p7nm_scalability_assessment.md#L75)

累计对象体积不等于 simultaneous RSS，但足以证明当前显式布局距离 2 TB 约三个数量级，不能靠 OOC 或单纯增加 MPI ranks 解决。

### 6.3 modal core 仍存在全局稠密和集中所有权

当前路径仍含：

- 稠密 \(M^2\) overlap/Gram/matching；
- `NΓ×M` strong-trace 矩阵；
- all-mode `Nlocal×M` dense RHS；
- modal rows 集中到最后一个 rank；
- near-degenerate grouping 为 \(O(M^2)\)；
- dense Hungarian matching 为 \(O(M^3)\)；
- 全局 row/entity maps 在每个 rank 复制。

QEP 文件本身也说明当前 all-mode MUMPS 路线不适合 0.7 nm：
[`quadratic_beta_eigenproblem.py`](../../src/modes/quadratic_beta_eigenproblem.py#L1)。

### 6.4 网格和后处理仍有每 rank/全场复制

[`mesh_builder_3d.py`](../../src/geometry/mesh_builder_3d.py#L608)
的 hex/tetra 路径在每个 rank 构造全部全局 vertices，只分片 cells。增加 MPI ranks 会增加聚合坐标内存。

[`postprocess_3d.py`](../../src/postprocessing/postprocess_3d.py#L182)
又可能在 factor 仍存活时同时创建：

- code/physical DG 场；
- scattered/background/incident 场；
- E/H 与 curl 重建；
- NumPy 复数数组；
- PyVista grid 和 `grid.copy()`；
- real/imag/abs 展示数组。

在接近 2 TB 的 case 中，后处理可能成为实际同步峰值。

生产模式应：

- 默认不生成全域 DG/PyVista 场；
- 只流式输出端口积分、材料积分、选定界面/切片；
- 在允许的情况下先释放 factor/KSP/大矩阵；
- 将 postprocess 自身纳入独立内存 Gate。

### 6.5 0.7 nm 不能继续使用 zero-order DtN

[`src/main.py`](../../src/main.py#L210)
默认 `stage4_dtn_order_policy="zero_order"`；
[`modes_3d.py`](../../src/common/modes_3d.py#L201)
在该策略下只保留 \((0,0)\)。

当周期约 100 nm、波长 0.7 nm 时，会出现大量传播衍射级。仅保留零级可能得到代数收敛，却对应不完整的开放边界物理。

正式 0.7 nm 必须包含：

- 所有传播级；
- Rayleigh 临界级专项处理；
- 有界 evanescent buffer；
- modal power completeness；
- M/order 收敛证明；
- 完整显著衍射级 observable vector，而非只比较零级反射。

## 7. 建议的 0.7 nm / 2 TB 工作路线

### M0：基础设施硬化

在任何新的重型运行前修复：

1. 完整 MPI 进程组/cgroup 终止。
2. false-pass 和 exit-code 状态机。
3. `A_volume` fail-closed。
4. QEP requested/actual provenance。
5. 原子 artifact 目录与 existing-artifact 验证。
6. before/after source identity。
7. Task036 aggregate-memory Gate。
8. PETSc/SLEPc 异常路径清理。
9. local LU finite/pivot/residual Gate。

这些修复应配套 negative-path 和 failure-injection 测试，而不仅是成功路径测试。

### M1：冻结 0.7 nm 物理合同

建立独立的 0.7 nm canonical case，不允许“13.5 nm preset 只改 lambda”。

材料数据至少绑定：

- \(n+ik\) 或等价原子散射数据来源；
- 波长、密度、组成、温度；
- 插值与吸收边附近的处理规则；
- 数据版本与 hash；
- 时间因子和虚部符号约定；
- 数据不确定度及其对 R/T/A 的传播。

可将以下权威数据入口作为来源或交叉核验：

- [NIST X-Ray Form Factor, Attenuation, and Scattering Tables](https://www.nist.gov/pml/x-ray-form-factor-attenuation-and-scattering-tables)
- [CXRO](https://www.cxro.lbl.gov/)

但仍需明确从原始表到复介电常数的转换、插值和 cache invalidation。

还应明确粗糙度、氧化层、界面扩散是否属于目标物理模型；0.7 nm 下这些细节可能不再是可忽略修正。

### M2：优先验证 2D/2.5D 降维

当前目标几何存在 `grating_width_y == period_y` 的潜在 y 不变性。如果真实结构、入射和材料也满足，应优先建设正式 2D/2.5D 或 Fourier-separated 路线。

但必须由小规模 3D anchor 证明：

- n=0 alias 和 trace identity；
- S/P 解耦或可控耦合；
- `R00_s`、`R00_p`、`R00_total`、显著衍射级、T、A、`A_volume` 一致；
- 不是只凭几何外观宣布对称。

如果降维成立，这是最可能把问题真正压入 2 TB 的一步。

### M3：停止接口位置扫描，解决缺失接口空间

Task036 已证明移动接口不足。下一步优先利用已有 Full3D exact traces 做离线分析：

- 比较 full-interface discrete Bloch basis；
- 比较 thin-buffer transfer-eigenmode / optimal-port basis；
- 检查现有 QEP modes 无法表达的 endpoint missing space；
- 对新增 basis 使用 transfer singular-value tail 或等价误差证书。

如果正式 review 授权 R2，建议采用：

- bottom、core、top 分段 basis；
- extra evanescent modes 只在短 buffer 内存在；
- buffer/core 接口局部 Schur 消元；
- 全局未知量只保留跨越主要中间区的 core basis；
- near-degenerate block 整体保留或整体消元；
- 禁止再次形成 global \(M_{\mathrm{total}}^2\)。

在小模型恢复 96/96 通道前，不进入 0.7 nm 放大。

### M4：重写 modal/QEP 数据布局

目标不应是“求出并保存全部模式”，而应是“只求对可观测量和接口传递有贡献的子空间”。

需要：

- contiguous distributed mode ownership；
- block-wise/streamed mode generation；
- 只保留接口 traces 或压缩表征；
- 去除最后一个 rank 的 modal ownership 瓶颈；
- 不生成 all-mode dense RHS；
- 不复制 global \(M^2\) Gram/matching；
- near-degenerate modes 按 connected block 跟踪；
- 根据传播级、衰减长度和 transfer tail 自适应决定 M。

当前 lossy QEP 属于一般复谱问题，不能直接假设 STOAR interval spectrum slicing 可用。SLEPc 文档对其 Hermitian/hyperbolic 条件有限制：
[SLEPc PEP manual](https://slepc.upv.es/release/documentation/manual/pep.html)。

可研究 target continuation、block eigensolve 或
[PEPCISS contour method](https://slepc.upv.es/release/manualpages/PEP/PEPCISS.html)，
但 PEPCISS 会引入多次线性求解，必须先做小型成本原型。

### M5：建立 matrix-free strong-trace Hybrid

推荐主算子形式：

```text
modal amplitudes
    -> lifted interface trace
    -> local endcap/FEM response
    -> Petrov/traction projection
    -> modal residual
```

不显式构造全局 Schur matrix，而使用 PETSc shell/nested operator：

- [PETSc MatCreateShell](https://petsc.org/release/manualpages/Mat/MatCreateShell/)
- [PETSc KSPFGMRES](https://petsc.org/release/manualpages/KSP/KSPFGMRES/)

建议评估：

- FGMRES；
- block-triangular / approximate-Schur preconditioner；
- 局部 H(curl) auxiliary-space/multilevel preconditioner；
- domain decomposition；
- static-condensed trace 或 matrix-free volume action。

whole-domain Full3D direct 只保留为小 anchor；局部 direct solve 只作为局部块或预条件器组成。

### M6：完成可扩展的 local h/p 自适应

当前 variable-p/local-h 仍包含全局 entity/row allgather，broken-cell trace 也尚未完成 production scalability 和 PDE accuracy 资格化。

需要：

- owner-routed distributed numbering；
- ghost/neighbor exchange，替代全量 allgather；
- 材料/interface 附近的方向性 h/p refinement；
- static condensation 奇异块 fail-closed；
- `A_volume_total` 及主要衍射可观测量的 adjoint/goal derivative；
- 以完整 observable vector 做 DWR，而不是只追一个 R 值。

历史 Task035 表明 adaptive p6 不会自动产生 50% DoF 节省。structured high-order 和 uniform high-order 应继续作为对照。

迭代内存比较只能在 adaptive/Hybrid candidate 先通过 accuracy Gate 后开始。

### M7：分级验证与扩容

建议顺序：

1. 0.7 nm homogeneous、zero-contrast、Fresnel、manufactured tests。
2. 2D TE/TM p/h 收敛。
3. 与 RCWA/FMM 或 COMSOL 的同物理独立参考比较。
4. 小型 3D one-cell Floquet anchor。
5. full 与 static-condensed operator action equivalence。
6. 小型 Hybrid/interface basis anchor。
7. 13.5 → 5 → 2 → 1 → 0.7 nm continuation。
8. 每级重新评估材料、传播级、M、buffer、h/p、内存和全部固定通道。
9. 只有预测峰值明显低于预算，才启动正式目标 case。

每一级至少要求：

- full explicit true residual；
- official-result identity；
- 全部传播级和 modal completeness；
- R/T/A 与 `A_volume` closure；
- passivity/reciprocity 或适用的对称性检查；
- interface trace/traction Gate；
- source/config/material/artifact hash；
- 独立资源 Gate。

## 8. 建议的 2 TB 内存设计预算

下表是研发分配上限，不是已证明可以达到的预测：

| 子系统 | 建议上限 |
|---|---:|
| OS、MPI、allocator、runtime | 150 GiB |
| 分布式 mesh、DoF maps、系数 | 220 GiB |
| Krylov basis 与工作向量 | 220 GiB |
| matrix-free/Schwarz/multilevel PC | 420 GiB |
| modal/QEP/接口压缩数据 | 260 GiB |
| 流式后处理和瞬时对象 | 80 GiB |
| 失败路径、波动和安全储备 | 180 GiB |
| **合计** | **1530 GiB** |

这对应约 1.49 TiB 的设计目标，给 2 TiB 物理上限留下约 25% 余量。

建议资源 Gate：

- preferred whole-job peak：不超过约 1.5 TiB；
- 2 TiB 是硬上限，不能被全部视为 solver 可用内存；
- zero swap；
- 一次一个 heavy case；
- dedicated cgroup 或完整 process-tree simultaneous peak；
- 同时报告 RSS/PSS/USS、shared pages、swap delta 和 OOC scratch；
- assembly、NNZ、preconditioner/factor setup、full solve、postprocess 分阶段放行；
- 任一阶段预测进入硬上限区，执行完整进程组 controlled stop。

当前 readiness 文档建议 active rows 优选不超过约 \(2\times10^8\)，候选区约 \(2\text{–}3.5\times10^8\)，约 2 kB/DoF 为优选、3 kB/DoF 为探索硬线：
[`hybrid_production_readiness_assessment.md`](outcomes/hybrid_production_readiness_assessment.md#L300)。

这些数字只能作为设计目标，最终必须由小规模实测校准。

## 9. 次要但应纳入近期清理的项目

### 9.1 潜在 correctness 与 MPI 问题

- [modal Schur residual](../../src/solvers/hybrid_fem_modal_schur_direct.py#L542)
  漏减通用 `modal_rhs`。当前 correction 为零，所以已有正式路径未触发；未来启用非零 RHS 时会误报 residual。
- [2D power metrics](../../src/postprocessing/power_metrics.py#L591)
  混用 `MPI.COMM_WORLD` 与 mesh communicator，subcommunicator 下可能重复写文件或错误跳过。
- [解析 reference identity](../../src/postprocessing/postprocess_3d.py#L185)
  由 `stage_case` 字符串决定，可能给自定义 grating 生成错误 reference，或漏掉 flat-layer reference。
- [diffraction probe](../../src/postprocessing/diffraction_3d.py#L407)
  在 facet 上选择第一个 cell/第一个 rank，DG curl(H) 诊断可能随分区变化。

### 9.2 资源和数值语义

- [Full3D reference guard](../../src/postprocessing/full3d_reference.py#L26)
  在大坐标数组分配之后才检查 64 MiB guard，极大 sample count 可能先 OOM。
- [boundary locator](../../src/geometry/mesh_builder_3d.py#L47)
  使用默认 `np.isclose` 相对容差，极细网格时可能误标邻近内部 facet。
- 部分旧 memory 字段把“各 rank 历史峰值之和”写成类似 simultaneous peak 的名称；2 TB Gate 只能认同一时刻的 process-tree/cgroup authority。
- 若干 mode/power 路径通过裁零或 `1e-30` floor 隐藏方向、材料符号或 incident power 错误；正式被动材料路径应 fail closed。

### 9.3 runner、checker 和维护性

- `check_benchmarks.py` 默认会写 tracked 汇总文件；审阅和测试默认应只读。
- 根目录 `run_demo*.sh` 仍引用旧目录布局，属于失效入口。
- 两个 runner 会先删除调用者指定或派生的输出文件，缺少 artifact-root 限制和并发锁。
- benchmark runner 内积累了大量数值核心：
  - 最长函数约 2,953 行；
  - 若干 main/solve 超过 2,000 行；
  - 多代 watchdog、状态和 provenance 实现并存。
- 测试中约有 60 处 skip 门控、约 200 处源码文本或 `inspect.getsource()` 断言。这些能守住代码形状，但不能替代实际 MPI/数值行为测试。

## 10. 正面观察

本次审阅不是“代码整体不可用”的结论。值得保留和推广的做法包括：

- Task036 analyzer 对 residual、R/T/A、`A_volume`、接口弱形式、biorthogonality 和资源 authority 采用 fail-closed。
- Task035c compact/strict checker 已有较强的 hash、source、official-result 和 residual 独立核验模式。
- Case090 watchdog 已有正确的 process-group TERM/KILL 流程。
- 新 Hybrid trace 实现已经把 MPI collective 移出 interpolation callback。
- Hybrid sampled strong-traction proxy 明确标为 `diagnostic_only`，没有冒充正式 weak-traction Gate。
- recovered DOLFINx field 与 solver factor 生命周期已在成功路径上部分解耦。
- 高阶 Floquet 公共路径没有重新引入明显的全局稠密 boundary square。
- 现有 Task036 B02–B06、B08 的核心修复总体存在，当前主要缺口转向异常生命周期、接口表达空间和大规模数据布局。

## 11. 推荐优先级和停止规则

如果只按一条最有效的顺序推进：

1. 修 P0/P1 的 evidence、watchdog、artifact、lifecycle 缺陷。
2. 冻结 0.7 nm 材料和完整物理身份。
3. 证明或否定 y-invariant 2D/2.5D 降维。
4. 根据 Task036 V5 转向 transfer/optimal-port basis，不再重复接口移动。
5. 消除 modal \(M^2\)、all-mode RHS、last-rank ownership 和全局 maps。
6. 建立 matrix-free Hybrid 与可扩展 H(curl) 预条件器。
7. 完成 local h/p、adjoint goal 与 distributed recovery。
8. 经小 anchor 和 continuation 梯级后，才尝试受约 1.5 TiB 设计预算约束的正式 0.7 nm case。

建议明确以下停止规则：

- 小模型无法恢复 96/96 通道：停止扩容，继续处理接口 basis。
- 材料、传播级或 `A_volume` identity 不完整：不得生成 official result。
- 预测 simultaneous peak 超过约 1.5 TiB：不得直接进入 full solve。
- 没有完整进程组 termination：不得启动 TB 级 case。
- adaptive/Hybrid candidate 未通过 accuracy Gate：不得开始其 iterative-memory 比较。
- 资源 Gate 停止只能记为 `controlled_stop`，不能写成数值方法失败或通过。

## 12. 总体判断

当前项目已经过了“修一个明显 bug 就能运行”的阶段。下一步需要把正式证据系统、接口物理、modal 表示、分布式数据布局和内存生命周期作为同一个工程问题处理。

否则，即使某次计算在 2 TB 内跑完，也很难证明：

- 使用了正确的 0.7 nm 材料；
- 开放边界包含完整传播衍射空间；
- Hybrid 接口 basis 足以表达真实 Full3D trace；
- full explicit residual 和所有物理 Gate 通过；
- `A_volume` 没有因缺失 region 被伪造成零；
- artifact 没有被旧目录、并发写入或 source drift 污染；
- watchdog 终止后没有残留 MPI/MUMPS 进程。

因此，0.7 nm / 2 TB 的合理定位应是：

> 具备研究价值、存在条件性可行路线，但当前尚无 production solver entry，也不能从现有 direct Full3D 或 direct Hybrid 投影宣称可行。

最值得优先投入的不是继续扩大当前 direct case，而是：

1. 可信 fail-closed 基础设施；
2. 0.7 nm 物理与材料身份；
3. 2D/2.5D 对称性降维；
4. transfer/optimal-port 接口 basis；
5. distributed streamed modal core；
6. matrix-free H(curl)/Hybrid 求解；
7. 严格的分阶段数值和资源资格化。
