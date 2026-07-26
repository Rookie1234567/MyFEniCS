# Case097：保持 exact sequence 的局部 h/p 自适应

## 当前身份

```text
case_id = 097_goal_oriented_exact_sequence_hp_adaptivity
task = Task035d
geometry = Task034 fixed rectangular block grating
ordinary_default_changed = false
```

Case097 是 Task035d 的统一证据入口。当前已建立 Phase A
reference-cell 与小网格 authority；在 A1–A4 完整通过前不运行
`p6/h10` variable-p PDE。

## Phase A 当前能力

- p4/p5/p6 hexahedral N1curl edge、face、cell DoF 目录；
- 通过 `basix.compute_interpolation_operator` 建立低阶到 p6 的真实嵌入，
  不假定数组前缀；
- 逐实体 `edge <= face <= cell` exact-sequence 闭包；
- 配套 Qp 标量空间、离散 gradient、`curl(grad)`、rank/nullity 审计；
- `active --E_K--> p6 local container` 与
  `E_K^H A_K,p6 E_K`；
- active cell-interior static condensation 与 p6 容器 field recovery；
- 单 cell、两共享-face cell、`2×2×2`、serial/MPI2；
- x、y 和双周期实体 orbit、Floquet pullback 与角点闭合；
- inactive p6 模式不获得 global row。

Basix 0.10 的 custom element 对同类实体默认复用第一个实体的
transformation template。因此 heterogeneous edge/face degree 不调用
custom-element `T_apply`；Case097 显式选用每个实体相应 p4/p5/p6
标准元素的 Basix transformation block，并保存审计。

## 证据

```text
records/reference_active_space_authority_v1.json
records/mpi2_fixture_authority_v1.json
records/compact_authority_v1.json
```

前两份记录分别必须由真实 serial 和 MPI2 进程生成。两者都是低成本
reference/topology fixture，不启动 Maxwell PDE。

## 复现

```bash
cd /home/Projects/MyFEniCS
source scripts/activate_myfenics_wsl.sh

python benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/generate_reference_authority.py \
  --mode serial

mpiexec -n 2 python \
  benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/generate_reference_authority.py \
  --mode mpi2

python benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/generate_reference_authority.py \
  --mode manifest

python benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/generate_reference_authority.py \
  --mode check
```

后续 Phase B–F 的 p-only、h-only、combined hp、12 通道和资源记录继续放在
本 Case 中，但不得把尚未运行的条目写成通过。

## Phase B：历史多目标 seed 与真实减行候选

Task035b 的 same-mesh p4/p5 DWR 只提供历史 seed，不提供 Task035d
精度信用。Case097 将其压缩为
`records/legacy_multigoal_seed_v1.json`，并同时保存以下限制：

- 没有12个显著功率和12个复振幅各自的 residual-weighted adjoint；
- 没有独立的 `A_volume` 和 field/interface cellwise adjoint；
- `production_qualified=false`；
- 每个候选都必须重新运行 direct PDE 和完整物理 Gate。

在实际 `p6/h10`、`(6,3,14)`、252-cell 网格上，serial/MPI2/MPI8
共同重现了三个两周期 exact-sequence 计划：

| 候选 | p4/p5/p6 cells | active FE DoF | periodic trace + DtN80 | 定位 |
|---|---:|---:|---:|---|
| T30 | 144/56/52 | 87,600 | 28,990 | 首个正式 p-only seed |
| T25 | 159/51/42 | 82,052 | 27,869 | T30 有正信号后的第二候选 |
| T15 | 178/46/28 | 74,522 | 26,052 | preferred-band，精度风险更高 |

计划构造严格分成两轮：

1. cycle 1 只允许 `p6 -> p5`；
2. cycle 2 保留 p6 core 和 p5 face-ring，其余只允许 `p5 -> p4`；
3. x/y periodic cell component 同步选择；
4. shared edge/face degree 取 incident cell 的合法最小闭包；
5. inactive p6 mode 不生成 active global row。

对应 evidence：

```text
records/t30_h10_cell_degree_plan_v1.json
records/t25_h10_cell_degree_plan_v1.json
records/t15_h10_cell_degree_plan_v1.json
records/legacy_seeded_plan_authority_mpi1_v1.json
records/legacy_seeded_plan_authority_mpi2_v1.json
records/legacy_seeded_plan_authority_mpi8_v1.json
```

这些 authority 只证明 mesh/plan/entity/Floquet identity 和真实 active-row
规模，`heavy_pde_started=false`，不能写成物理通过。

复现：

```bash
cd /home/Projects/MyFEniCS
source scripts/activate_myfenics_wsl.sh

python benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/generate_legacy_seeded_plans.py \
  --mode generate

mpiexec -n 2 python \
  benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/generate_legacy_seeded_plans.py \
  --mode generate

mpiexec -n 8 python \
  benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/generate_legacy_seeded_plans.py \
  --mode generate

python benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/generate_legacy_seeded_plans.py \
  --mode check
```

## Variable-p DtN 一致性 Gate

assembly-time variable-p backend 对每个 port surface functional 先投影到
真实 active space，再执行 trace-only fail-closed Gate。N1curl
cell-interior 基函数的切向边界迹严格为零；FFCx 留下的 roundoff-sized
interior 值只有低于记录阈值才会被统一清零。这样 DtN row、column、
auxiliary block、RHS、recovery 和 residual 使用同一个离散定义。

若 interior 项超过阈值，运行立即失败；不得只修 auxiliary diagonal 后忽略
cross-mode Schur 或 auxiliary RHS。恢复/残差另外保留非 Hermitian
`+T_i a` dense oracle，以防未来引入真正非零 interior coupling 时发生符号
或左右列混用。

## T30 MPI8 正式 p-only Gate

首个正式候选固定为 `T30`：

```text
cells p4/p5/p6 = 144/56/52
actual conforming active FE DoF = 87,600
active trace rows before periodic reduction = 35,208
periodic independent trace rows = 28,910
DtN auxiliary rows = 80
direct solve rows = 28,990
```

`benchmarks.run_task033_full3d_watchdog` 的 Task035d opt-in 入口只接受
`p6/h10/S/MPI8/default/no-swap`、冻结的 T30 plan 与 MPI8 plan authority。
它检查 exact-sequence backend、真实减行、Floquet、mesh/tag/orientation、
trace-only DtN、full recovery、full explicit residual、MUMPS factor inventory
和 solver lifecycle；只授予结构/残差信用。

`benchmarks.task035d_case097_checker` 随后独立读取并哈希校验 raw
watchdog、solver summary、timeline、80-order DtN JSON 和 8 个 VTU shard，
再重算：

- Case095 reference-v1 的 `12/12` significant powers 与 `12/12`
  physical-boundary complex amplitudes；
- R00/R/T/Aclosure normalized vector、Avolume 与 energy closure；
- 冻结 volume/interface probes；
- rows、matrix NNZ、factor NNZ；
- process-tree RSS 权威、每 rank PSS/USS/smaps、cgroup 诊断账本和 zero swap。

当 cgroup 不是当前 job 的专属 cgroup 时，其 current/peak 只作为诊断账本，
不得覆盖 simultaneous process-tree RSS 权威。

正式命令在 runner/checker 提交后从干净 SHA 启动：

```bash
clean_sha="$(git rev-parse HEAD)"

python -m benchmarks.run_task033_full3d_watchdog \
  --degree 6 \
  --h-nm 10 \
  --polarization-kind s \
  --run-kind full-solve \
  --mpi-size 8 \
  --profile default \
  --stage4-full3d-assembly-backend assembly_time_variable_p_condensed \
  --stage4-variable-p-cell-degree-plan \
    benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/records/t30_h10_cell_degree_plan_v1.json \
  --stage4-variable-p-cell-degree-plan-sha256 \
    4f580a06f4c1774316ecbdce950828b3cda143f0807145d9d40de2cd64df5c3a \
  --task035d-case097-gate \
  --task035d-plan-authority \
    benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/records/legacy_seeded_plan_authority_mpi8_v1.json \
  --task035d-plan-authority-sha256 \
    97e8ddaab151cfc985c43c66256c036f3809ee216c47f67710a1f01679de0961 \
  --verified-clean-sha "${clean_sha}" \
  --warning-gib 48 \
  --terminate-gib 96 \
  --timeout-seconds 21600 \
  --artifact-root benchmarks/artifacts/task035d/case097 \
  --record benchmarks/artifacts/task035d/case097/t30_h10_mpi8_watchdog.json

watchdog_sha="$(sha256sum \
  benchmarks/artifacts/task035d/case097/t30_h10_mpi8_watchdog.json \
  | cut -d' ' -f1)"

python -m benchmarks.task035d_case097_checker \
  --watchdog benchmarks/artifacts/task035d/case097/t30_h10_mpi8_watchdog.json \
  --watchdog-sha256 "${watchdog_sha}" \
  --output benchmarks/artifacts/task035d/case097/t30_h10_mpi8_check.json
```
