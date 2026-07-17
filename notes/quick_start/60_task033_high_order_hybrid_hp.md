# Task33 高阶 Floquet、Hybrid h/p 与自适应研究入口

> 2026-07-17 阶段更新：Case090 p3/p4 高阶路径已完成；QEP MPI1 分片已运行；
> Hybrid/full3D 对比复用 Task032 p2 记录。自适应、buffer 与 1 TiB 阶段已延期。

本页保留为 Task33 的操作与恢复入口。完整原始任务边界见
[`../../docs/task033_high_order_floquet_hybrid_hp_adaptivity/task.md`](../../docs/task033_high_order_floquet_hybrid_hp_adaptivity/task.md)，
代码调用链见
[`../reference/code_walkthrough/52_task033_high_order_floquet_hp.md`](../reference/code_walkthrough/52_task033_high_order_floquet_hp.md)。

## 1. 先确认四条硬边界

| 项目 | 当前合同 |
|---|---|
| ordinary default | 不变；Task33 runner 全部显式 opt-in，不修改 `ACTIVE_PYCHARM_PRESET` |
| 当前可提交证据 | Case090 144 PDE、QEP MPI1 36 shards、阶段 summary 与 Task032 p2 对照 |
| formal evidence | 本阶段不是原任务书的 21-role closure；完整 manifest 仍是 `NOT_RUN` |
| 内存 | host hard budget 为 14 GiB；swap 禁止；预测或现场 Gate 不通过就不启动 |

当前仓库可以声明高阶 Stage1 完成，但不能声称自适应压缩、buffer 最优点或 1 TiB 路线已经完成。
`planning_eligible` 也不等于 `launch_eligible`。

## 2. Windows PowerShell 与 Docker 准备

在仓库根目录启动 PowerShell：

```powershell
$Repo = (Resolve-Path ".").Path
$Image = "myfenics-stage4:task28"
$Artifact = "benchmarks/artifacts/task033"

docker run --rm --memory 14g $Image python -c "from petsc4py import PETSc; print(PETSc.ScalarType)"
```

预期是复杂标量类型。为了缩短后续命令，可以定义只在本 PowerShell 会话中存在的
helper：

```powershell
function Invoke-Task33Docker {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Command)
    docker run --rm --memory 14g -v "${Repo}:/work" -w /work $Image @Command
    if ($LASTEXITCODE -ne 0) {
        throw "Task33 Docker command failed with exit code $LASTEXITCODE"
    }
}
```

Planning 命令不要求 clean tree。正式运行前必须重新取 SHA，并且只检查 tracked
源码；ignored artifact 不会破坏该检查：

```powershell
$CleanSha = (git rev-parse HEAD).Trim().ToLowerInvariant()
$TrackedChanges = @(git status --short --untracked-files=no)
if ($CleanSha.Length -ne 40 -or $TrackedChanges.Count -ne 0) {
    throw "Formal Task33 run requires one committed tracked-source-clean SHA."
}

$ImageDigest = (docker image inspect $Image --format '{{.Id}}').Trim()
```

不要在运行后重新填写一个不同 SHA。正式 shard、watchdog、aggregate 和 manifest
必须全部指向同一个 `$CleanSha`。

## 3. 安全的 planning-only 命令

下面命令会写入 gitignored 的 `benchmarks/artifacts/`。它们不运行 PDE，也不会生成
solver pass。

### 3.1 Case090 oracle 与执行计划

```powershell
Invoke-Task33Docker python -m benchmarks.run_task033_case090_matrix `
    --output "$Artifact/case090/planning/analytic_oracles_and_matrix.json"
```

结果应保持 `status=not_run`，正式 core 未提供时矩阵行只能是
`not_run_by_core_gate` 或 `not_run_by_scope`。详细合同见
[`../../benchmarks/cases/090_high_order_3d_floquet_hcurl/README.md`](../../benchmarks/cases/090_high_order_3d_floquet_hcurl/README.md)。

### 3.2 Case091 20 项资源矩阵

```powershell
Invoke-Task33Docker python -m benchmarks.run_task033_resource_matrix `
    --output-json "$Artifact/case091/planning/resource_matrix.json" `
    --output-csv "$Artifact/case091/planning/resource_matrix.csv"
```

不传运行 attestation 时，clean/no-swap/watchdog/one-large-case 保持 unknown，launch
会 fail closed。默认 planning 采用 Phase-0 的 13.6485 GiB Docker limit；14 GiB 是
host hard budget，不是允许扩大预测门限的理由。

### 3.3 QEP p/h/MPI 计划

```powershell
Invoke-Task33Docker python -m benchmarks.run_task033_qep_matrix `
    --output "$Artifact/case091/planning/qep_matrix_plan.json"
```

当前计划是 p1--p4、h5/h3/h2.5/h2/h1.5、MPI1/2/4 与三种 material kind 的
180 项矩阵，默认 `requested_modes=8`。没有 `--execute` 就不是 QEP measurement。

### 3.4 Graded-h、variable-p 与 1 TiB 计划

```powershell
Invoke-Task33Docker python -m benchmarks.run_task033_adaptive_mesh `
    --reference-h 5 `
    --output-json "$Artifact/case091/planning/graded_h5_plan.json"

Invoke-Task33Docker python -m benchmarks.run_task033_adaptive_mesh `
    --reference-h 3 `
    --output-json "$Artifact/case091/planning/graded_h3_plan.json"

Invoke-Task33Docker python -m benchmarks.run_task033_variable_p_audit `
    --output "$Artifact/case091/planning/variable_p_capability_audit.json"

Invoke-Task33Docker python -m benchmarks.run_task033_one_tib_projection `
    --output "$Artifact/case091/planning/one_tib_projection_NOT_QUALIFIED.json"
```

无 reference/candidate measured evidence 的 graded 记录只能是 plan。variable-p audit
当前必须保留 `not_qualified_fail_closed`；不得自行发明 cellwise variable-p H(curl)
约束。未传 measured compression 的 1 TiB 结果也必须是 `not_qualified`。

## 4. Case090 正式 PDE：只在资源窗口明确时执行

这不是 smoke。每个 MPI shard 固定运行 48 个 PDE 算例；MPI1/2/4 共三个 shard。
正式流程必须使用 Case090 专用外部 watchdog，不能直接运行 worker 后把历史 RSS 当作
simultaneous memory。

```powershell
$Case090 = "$Artifact/case090/formal"

foreach ($Mpi in 1, 2, 4) {
    $MpiDir = "$Case090/mpi$Mpi"
    Invoke-Task33Docker python -m benchmarks.run_task033_case090_watchdog `
        --mpi-size $Mpi `
        --raw-output "$MpiDir/watchdog_raw.jsonl" `
        --summary-output "$MpiDir/watchdog_summary.json" `
        --sample-interval 1 `
        -- mpiexec -n $Mpi python -m benchmarks.run_task033_case090_pde_core shard `
        --work-dir "$MpiDir/work" `
        --output "$MpiDir/shard.json"
}
```

任一 rank、数值 Gate、tracked clean/stable SHA、cgroup/RSS、swap 或 95% container
limit Gate 失败都应立即停止。三个 shard 和三个 memory summary 都成功后才能聚合：

```powershell
Invoke-Task33Docker python -m benchmarks.run_task033_case090_pde_core aggregate `
    "$Case090/mpi1/shard.json" `
    "$Case090/mpi2/shard.json" `
    "$Case090/mpi4/shard.json" `
    --memory-summaries `
    "$Case090/mpi1/watchdog_summary.json" `
    "$Case090/mpi2/watchdog_summary.json" `
    "$Case090/mpi4/watchdog_summary.json" `
    --output "$Case090/case090_core.json" `
    --require-pass

Invoke-Task33Docker python -m benchmarks.run_task033_case090_matrix `
    --core-gate-record "$Case090/case090_core.json" `
    --require-core-gate-pass `
    --output "$Case090/case090_formal_matrix.json"

$CoreSha256 = (Get-FileHash "$Repo/$Case090/case090_core.json" -Algorithm SHA256).Hash.ToLowerInvariant()
```

聚合器会再次核对三份 shard、三份 watchdog、同一 clean SHA、p1--p4 × MPI1/2/4、
sparse/no-gather/no-dense、p1/p2 regression 和物理 Gate。输出文件存在不等于通过；
必须同时检查退出码与 `all_core_gates_passed=true`。

## 5. QEP 与 Hybrid 必须通过通用 watchdog

### 5.1 正式运行前刷新 launch matrix

下面四个 attestation 只能在本次现场条件确实成立后使用。高阶 degree 还必须先完成
相应资格；不要为了让 JSON 变绿而填写这些开关。

```powershell
$ContainerLimitGiB = 13.6485  # 只可替换为本次实测值；若更小，Gate 必须随之缩小
$Resource = "$Artifact/case091/formal/resource_matrix_runtime.json"

# 仅在 clean/no-swap/watchdog/one-large-case 都已由现场确认后执行：
Invoke-Task33Docker python -m benchmarks.run_task033_resource_matrix `
    --container-limit-gib $ContainerLimitGiB `
    --source-clean-verified `
    --no-swap-verified `
    --watchdog-enabled-verified `
    --one-large-case-verified `
    --output-json $Resource `
    --output-csv "$Artifact/case091/formal/resource_matrix_runtime.csv"
```

若要运行 p3，还必须在 Case090、QEP/trace 等前置证据真实通过后重新生成矩阵并加入
`--p3-qualified`。p4 同理，且不能因为 p3 可运行就自动加入 `--p4-qualified`。

### 5.2 一个 QEP measurement shard 模板

```powershell
Invoke-Task33Docker python -m benchmarks.run_task033_memory_watchdog `
    --target qep `
    --case-label qep_air_p3_h5_mpi2 `
    --degree 3 `
    --h-nm 5 `
    --mpi-size 2 `
    --material-kind air `
    --requested-modes 8 `
    --candidate-modes 16 `
    --verified-clean-sha $CleanSha `
    --high-order-core-evidence-file "$Case090/case090_core.json" `
    --container-image $Image `
    --container-digest $ImageDigest `
    --host-environment-id windows-docker-desktop `
    --artifact-root "$Artifact/case091/qep_runs" `
    --summary-output "$Artifact/case091/qep_runs/qep_air_p3_h5_mpi2_summary.json"
```

正式 QEP study 需要按 plan 完成所需唯一 shards 后再聚合；当前仓库只有
`aggregate_qep_shards(...)` 库 API，没有独立 aggregate CLI，也没有已提交的正式
aggregate record。因此执行一个 shard 不能写成 QEP study 完成。

### 5.3 MPI timeout negative

timeout negative 必须来自 clean SHA 上的真实外部 watchdog 超时，不能由 preflight
失败或 memory kill 代替。可在专门的短时诊断窗口把上一个模板的
`--timeout-seconds` 改为小值；预期命令返回非零，并且 summary 同时满足：

```text
status = formal_not_pass
formal_pass = false
terminated_for_timeout = true
terminated_for_memory = false
```

这个负记录是 formal checklist 的必需角色，但不是 solver pass。

### 5.4 p1/p3 Hybrid M 漏斗

这里的 `M` 始终表示**每个传播方向最终保留的模态数**。为完成稳定筛选，watchdog
合同要求 `candidate_modes=2M`。Hybrid 内部振幅总数同样写成 `2M`，但它表示
`M forward + M backward`；这个数值与候选池大小相同，物理语义并不相同。

下面示例是 p1/h5/MPI4 的 M80/M120/M160 漏斗。必须使用同一 p/h/interface、同一
clean SHA 和同一 resource matrix；M120→M160 未收敛时才条件增加 M240。

```powershell
$Hybrid = "$Artifact/case091/hybrid_p1_h5"
foreach ($M in 80, 120, 160) {
    Invoke-Task33Docker python -m benchmarks.run_task033_memory_watchdog `
        --target hybrid `
        --case-label "hybrid_p1_h5_m$M" `
        --degree 1 `
        --h-nm 5 `
        --mpi-size 4 `
        --requested-modes $M `
        --candidate-modes (2 * $M) `
        --solver-path modal-schur-memory-minimal `
        --compare-modal-schur `
        --resource-matrix $Resource `
        --verified-clean-sha $CleanSha `
        --high-order-core-evidence-file "$Case090/case090_core.json" `
        --container-image $Image `
        --container-digest $ImageDigest `
        --host-environment-id windows-docker-desktop `
        --artifact-root "$Hybrid/runs" `
        --summary-output "$Hybrid/m$M.json"
}

Invoke-Task33Docker python -m benchmarks.run_task033_hybrid_funnel `
    "$Hybrid/m80.json" "$Hybrid/m120.json" "$Hybrid/m160.json" `
    --output "$Hybrid/funnel.json" `
    --require-qualified
```

p3 使用相同流程，但只能在含真实 `--p3-qualified` attestation 的 resource matrix 上
运行。单个 M80、普通 smoke、dirty SHA 或缺少显著衍射级/场证据都不能成为 funnel
qualification。

## 6. Graded-h 与四个 interface buffer

### 6.1 Graded h5/h3

planning 见第 3 节。取得同一 clean SHA 的 uniform reference 与 graded candidate
measured evidence 后，才可附着 same-accuracy 资格：

```powershell
Invoke-Task33Docker python -m benchmarks.run_task033_adaptive_mesh `
    --reference-h 5 `
    --reference-evidence "$Artifact/case091/measured/uniform_h5.json" `
    --candidate-evidence "$Artifact/case091/measured/graded_h5.json" `
    --output-json "$Artifact/case091/formal/adaptive_h5.json"

Invoke-Task33Docker python -m benchmarks.run_task033_adaptive_mesh `
    --reference-h 3 `
    --reference-evidence "$Artifact/case091/measured/uniform_h3.json" `
    --candidate-evidence "$Artifact/case091/measured/graded_h3.json" `
    --output-json "$Artifact/case091/formal/adaptive_h3.json"
```

这两个命令只聚合证据；真实 graded Hybrid shard 仍必须由 watchdog 启动，并传入
`--graded-reference-h 5` 或 `--graded-reference-h 3`。缺少 full-field、modal gate、
plan hash 或 same-accuracy Gate 时记录必须保持 not qualified。

### 6.2 Buffer 10/7.5/5/2.5 nm

四个对称候选固定为：

| buffer | bottom interface | top interface |
|---:|---:|---:|
| 10 nm | 10 nm | 110 nm |
| 7.5 nm | 7.5 nm | 112.5 nm |
| 5 nm | 5 nm | 115 nm |
| 2.5 nm | 2.5 nm | 117.5 nm |

它们通过 Hybrid watchdog 的现有参数选择：

```powershell
$Buffer = 7.5
$TopInterface = 120.0 - $Buffer

Invoke-Task33Docker python -m benchmarks.run_task033_memory_watchdog `
    --target hybrid `
    --case-label "buffer_${Buffer}_p2_h3_m80" `
    --degree 2 `
    --h-nm 3 `
    --mpi-size 4 `
    --requested-modes 80 `
    --candidate-modes 160 `
    --bottom-interface-nm $Buffer `
    --top-interface-nm $TopInterface `
    --solver-path modal-schur-memory-minimal `
    --resource-matrix $Resource `
    --verified-clean-sha $CleanSha `
    --artifact-root "$Artifact/case091/buffers" `
    --summary-output "$Artifact/case091/buffers/buffer_${Buffer}_m80.json"
```

每个 buffer 仍需完整 M80/M120/M160 funnel。当前没有独立
`interface_buffer_tradeoff` 生成 CLI，也没有四个正式 funnel record；不能手工挑一个
最快 smoke 后写成最优 buffer。

## 7. Variable-p 与 1 TiB 的正确解释

`run_task033_variable_p_audit` 是能力审计，不是实现入口。当前可接受的正式结论可以是
negative：原生安全 cellwise variable-p 未资格化，Task33 退回 fixed-p equal-accuracy、
p2 h-adaptive 和 hp zoning 设计报告。

只有 measured same-accuracy compression 已存在时，才可更新 1 TiB 分类：

```powershell
$Compression = 2.1  # 示例位置；必须替换为真实 measured record 中的值
$CompressionRecord = "$Artifact/case091/formal/adaptive_h3.json"

Invoke-Task33Docker python -m benchmarks.run_task033_one_tib_projection `
    --measured-compression $Compression `
    --measurement-identity measured `
    --evidence-record $CompressionRecord `
    --output "$Artifact/case091/formal/one_tib_projection.json"
```

不要复制示例数值作为结果。即便得到 `classified`，它也只更新 local FE row resource
zone，不证明 0.7 nm 已可解。

## 8. 统一 Case090/091 checker

checker 是纯读取验收器，只向 stdout 输出报告。

```powershell
Invoke-Task33Docker python -m benchmarks.check_task033
```

当前 planning 模式应返回 0，并验证 committed Case090 oracle/planner/core NOT_RUN、
Case091 resource JSON/CSV、QEP plan、variable-p/1 TiB schema/records 和全部 Task33
schema。报告中的 `evidence_verified` 不是 PDE 或 solver pass。

当前正式检查应 fail closed 并返回 2，因为 committed manifest 仍是 NOT_RUN：

```powershell
docker run --rm --memory 14g -v "${Repo}:/work" -w /work $Image `
    python -m benchmarks.check_task033 --require-formal
$LASTEXITCODE  # 当前预期为 2
```

未来 formal manifest 必须符合
[`../../benchmarks/cases/091_hybrid_hp_adaptivity_feasibility/formal_evidence_manifest_schema.json`](../../benchmarks/cases/091_hybrid_hp_adaptivity_feasibility/formal_evidence_manifest_schema.json)，
然后运行：

```powershell
docker run --rm --memory 14g -v "${Repo}:/work" -w /work $Image `
    python -m benchmarks.check_task033 `
    --formal-manifest "$Artifact/case091/formal/formal_manifest.json"
```

验收器要求 16 个唯一角色、每个文件 SHA256、冻结 JSON schema、角色接受状态、角色
语义和同一 clean source SHA。缺一个文件、用错 SHA、把 timeout negative 写成 pass、
或让 variable-p audit 冒充实现，都会返回 2。不要复制 committed NOT_RUN manifest 后
只改 `status`；这不会通过角色与证据检查。

## 9. PyCharm 友好入口

Planning 与 checker 可建立普通 Python Run Configuration：

| 字段 | 建议值 |
|---|---|
| Run kind | Module name |
| Module | `benchmarks.check_task033` |
| Parameters | planning 留空；正式时填 `--formal-manifest <repo-relative-path>` |
| Working directory | 仓库根目录 |
| Interpreter | 已配置的 complex DOLFINx Docker interpreter |

也可把第 3 节的 module name 和参数分别建立为 planning 配置。正式 Case090、QEP、
Hybrid、graded 或 buffer 运行不要用普通单进程 Run 按钮代替：它们依赖外部
watchdog、真实 `mpiexec`、cgroup 和 swap 采样。请在 PyCharm Terminal 中执行本页
PowerShell，或建立调用同一 Docker 命令的 External Tool。

## 10. 当前缺口与停止条件

| 项目 | 当前状态 | 正确动作 |
|---|---|---|
| Case090 committed record | oracle/planner/core 均为 NOT_RUN | 保留；只有 clean watchdog 三 shard 可替代 |
| QEP formal aggregate | 尚无正式 aggregate；无独立 aggregate CLI | 保存 shards，不能宣称 study 完成 |
| p1/p3 Hybrid funnel | 尚无正式 M80/120/160 records | 逐 shard watchdog，再用 funnel CLI |
| adaptive h5/h3 | planning path 存在，measured compression 未提交 | 缺 same-accuracy evidence 就停止 |
| 四 buffer + tradeoff | 参数入口存在，正式 funnel/tradeoff record 缺失 | 不从 smoke 选最优点 |
| variable-p | fail-closed negative audit | 不自造任意 variable-p 约束系统 |
| 1 TiB | 当前 NOT_QUALIFIED | 只用 measured compression 更新分类 |
| unified formal manifest | committed entries 为空 | `--require-formal` 返回 2 是正确结果 |

任何资源预测超过 Gate、现场可用内存不足、swap 非零、tracked source 变脏、SHA 变化、
watchdog 不可用或前序角色缺失时，都应停止，不得通过放宽 residual/RTA/field Gate 或
手工编辑 record 继续推进。
