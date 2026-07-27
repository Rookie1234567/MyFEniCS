# Case097：保持 exact sequence 的局部 h/p 自适应

## 当前身份

```text
case_id = 097_goal_oriented_exact_sequence_hp_adaptivity
task = Task035d
geometry = Task034 fixed rectangular block grating
ordinary_default_changed = false
```

Case097 是 Task035d 的统一证据入口。当前已建立 Phase A
reference-cell 与小网格 authority，并完成 Phase B–E 的真实 local-p、
2:1 balanced local-h、H(curl) hanging/Floquet、compiled cell tensor、
PETSc ownership、静态凝聚、MPI1/2/8 identity 和正式 MPI8 direct PDE。
最终分类为 `PARTIAL_WITH_CONTROLLED_NEGATIVES`：结构、残差和资源能力通过，
但没有候选达到冻结的 `12/12 powers + 12/12 complex amplitudes`，所以
Full3D hp production candidate 和 Hybrid Phase F 均未产生。

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

### T30 正式 MPI8 结果：controlled negative

首条正式 PDE 绑定：

```text
solver source SHA = c3768cf4723c2ae949c82d1ce8b18a56f5ab0f7b
checker source SHA = 5f960f912809b162e363259b0896af25ef3b0018
raw watchdog SHA256 =
  081ec26770741dddb9039831d38d475a01df051b7062ff5b4d0e1fef2e02ebd9
compact checker SHA256 =
  ac0266578fe38dd9934cfcfb840d817f8c4fbc617694a068462f7d505392acc1
```

权威记录：

```text
records/t30_h10_mpi8_controlled_negative_v1.json
```

结构、残差和资源 Gate 通过，但同精度 Gate 明确失败：

| metric | T30 measured | p6 static baseline | result |
|---|---:|---:|---|
| active FE DoF | 87,600 | 173,802 | mandatory DoF pass |
| direct rows | 28,990 | 51,272 | `-43.46%` |
| matrix NNZ | 15,253,176 | 41,989,040 | `-63.67%` |
| factor NNZ | 63,564,300 | 212,343,992 | `-70.07%` |
| process-tree peak | 10.0929 GiB | 14.7218 GiB | `-31.44%`, 20% mandatory pass |
| PSS / USS peak | 9.0901 / 8.9268 GiB | not same-campaign baseline | measured |
| true residual | `1.410e-11` | `<=1e-9` Gate | pass |
| energy closure | `-5.638e-13` | `<=1e-9` Gate | pass |
| significant power / amplitude | `0/12` / `0/12` | `12/12` / `12/12` | fail |
| normalized R/T/Aclosure L2 | `21.214` | `sqrt(3)` | fail |
| volume / interface field rel-L2 | `9.337%` / `9.884%` | `2.220%` / `2.447%` | fail |

T30 的资源压缩是真实正信号，但物理误差不是边缘失败：12 个冻结通道全部
失败，R00、R、T、Aclosure、Avolume 和两个 field selections 均超出
same-code p5→p6 band。因此更激进的 T25/T15 不会在没有新恢复逻辑时盲目
启动。下一 p-only 点必须把失败通道与 field/interface sensitivity 显式用于
p6 trace/cell 恢复，并仍保持 `active FE DoF <= 90,000`。

### Physics-guard 恢复 authority

T30 的原始 MPI8 VTU 用冻结 probe 重新按物理区域分解。该分解是
`diagnostic_only`，不是 actual channel DWR 或 adjoint derivative，也不提供
精度信用：

| region | T30 rel-L2 / global-p5→p6 band |
|---|---:|
| left/right grating sidewall | `17.07–18.10` |
| substrate volume | `9.84` |
| left/right air volume | `4.10–4.16` |
| grating volume | `3.87` |
| z=0 interface | `2.45–2.65` |
| top air | `1.25` |
| grating top interface | `0.386` |

诊断同时重算 T30 的 12 通道失败宽度：power 为
`1.42–845.26×` tolerance，complex amplitude 为
`8.38–298.83×` tolerance。由此只构造一个保守恢复点
`sidewall_z0_guard_v1`：

1. cycle 1 在 grating 核心 `x=16.5..33.5 nm`、下部
   `z=0..20 nm` 保留 p6，其余降到 p5；
2. cycle 2 只把两条远离结构的外侧均匀空气带降到 p4；
3. 每个 p6 与 p4 区域之间保留 p5 corridor，最大相邻跳阶严格为 1；
4. substrate、top port、全部 material interface 与 grating 主体至少为 p5。

冻结结构 authority：

| metric | sidewall-z0 guard |
|---|---:|
| p4/p5/p6 cells | `72/168/12` |
| active FE DoF | `89,870` |
| edge/face/cell-interior DoF | `4,902 / 31,472 / 53,496` |
| trace before periodic reduction | `36,374` |
| periodic independent trace | `30,984` |
| direct rows with DtN80 | `31,064` |

证据：

```text
records/t30_regional_probe_error_localization_v1.json
  sha256 = baaca8a90a98d459e392468778528edc43217d1c6fa19969592044522d498f3f
records/sidewall_z0_guard_h10_cell_degree_plan_v1.json
  sha256 = 31922411775580b2f44b474897dbf877d96b7887f74d22e02b3f0e410c205bc2
records/physics_guard_plan_authority_mpi1_v1.json
records/physics_guard_plan_authority_mpi2_v1.json
records/physics_guard_plan_authority_mpi8_v1.json
  MPI8 sha256 =
    ccf40707125425540bd60a8118fed4fd74f9138968624255eb1e4fa25c8e911d
```

MPI1/2/8 已重现相同 plan content SHA
`8172bcc9ca2e2fcbc23a8ca15524f80b7658ccf0c19d24da4dcff1ed32fee062`。
该 authority 随后启动了唯一 fresh MPI8 direct recovery PDE；正式结果见下节。

复现：

```bash
cd /home/Projects/MyFEniCS
source scripts/activate_myfenics_wsl.sh

python benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/generate_physics_guard_recovery.py \
  --mode diagnostic

python benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/generate_physics_guard_recovery.py \
  --mode generate

mpiexec -n 2 python \
  benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/generate_physics_guard_recovery.py \
  --mode generate

mpiexec -n 8 python \
  benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/generate_physics_guard_recovery.py \
  --mode generate

python benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/generate_physics_guard_recovery.py \
  --mode check
```

### Physics-guard 正式 MPI8 结果：controlled negative

`sidewall_z0_guard_v1` 在 clean source
`a6f2d8a3b88efda581aa0e36f5ebcd9d6776e0cf` 上完成 MPI8 direct
PDE。solver identity、full explicit true residual、exact-sequence recovery
和资源 Gate 全部通过，但独立 checker 判定物理精度失败：

```text
watchdog sha256 =
  13a017d70892a7877fa8abd1e61846ed8db37804a253a07e26b9c27fb67a60c0
compact checker sha256 =
  c850259c31d8e6554aa3956167fa6ae319c0b2ad335f32ff5cf19371eeebd96f
record =
  records/sidewall_z0_guard_h10_mpi8_controlled_negative_v1.json
```

| metric | measured | p6 reference / Gate | result |
|---|---:|---:|---|
| active FE DoF | 89,870 | `<=90,000` | pass |
| direct rows | 31,064 | p6 static 51,272 | `-39.41%` |
| matrix NNZ | 16,490,572 | 41,989,040 | `-60.73%` |
| factor NNZ | 76,721,484 | 212,343,992 | `-63.87%` |
| process-tree peak | 8.38265 GiB | 14.72176 GiB | `-43.06%`, preferred pass |
| simultaneous worker PSS / USS | 7.38039 / 7.21696 GiB | diagnostic | measured |
| full explicit true residual | `7.5595e-12` | `<=1e-9` | pass |
| significant powers | 1/12 | 12/12 | fail |
| significant complex amplitudes | 0/12 | 12/12 | fail |
| R00 / R / T / Aclosure normalized errors | 3.796 / 3.799 / 8.571 / 9.393 | each `<=1` | fail |
| Avolume absolute error | 0.00174412 | 0.000185676 | fail |
| volume field rel-L2 | 3.7330% | 2.2205% | fail |
| interface field rel-L2 | 4.0155% | 2.4467% | fail |
| zero swap | true | mandatory | pass |

12 个冻结显著通道的独立误差/限值如下；`top(-1,0)` 是唯一 power pass，
但其复振幅仍失败：

| side/order | power error / tolerance | amplitude error / tolerance |
|---|---:|---:|
| bottom -7 | `7.25323e-7 / 2.15869e-9` | `1.23293e-3 / 1.21657e-5` |
| bottom -5 | `7.92214e-9 / 3.89127e-10` | `9.95785e-6 / 1.28065e-6` |
| bottom -4 | `4.38440e-9 / 5.25100e-10` | `2.07690e-5 / 2.54166e-6` |
| bottom -2 | `4.61647e-8 / 4.65105e-9` | `2.99641e-5 / 4.58081e-6` |
| bottom -1 | `1.84990e-6 / 1.11441e-7` | `2.06358e-4 / 1.27290e-5` |
| bottom 0 | `1.86466e-3 / 2.17577e-4` | `5.08728e-2 / 6.77963e-3` |
| top -7 | `2.28277e-7 / 1.24944e-9` | `6.72145e-4 / 7.99504e-7` |
| top -5 | `8.23809e-9 / 1.19430e-9` | `7.92162e-6 / 1.11321e-6` |
| top -4 | `1.58210e-8 / 1.08649e-9` | `1.60124e-5 / 1.88152e-6` |
| top -2 | `3.03981e-9 / 1.24228e-9` | `2.03888e-5 / 3.18649e-6` |
| top -1 | `4.78904e-8 / 5.11184e-8` pass | `8.61368e-5 / 7.41338e-6` |
| top 0 | `1.21288e-4 / 3.19529e-5` | `2.83493e-3 / 8.33027e-4` |

与 T30 的 `0/12 + 0/12` 相比，这不是足以继续 p-only 扫描的精度正信号。
按照同一 lane 连续两个数值负信号后的停止规则，T25/T15 和第三个 p-only
恢复 PDE 均不启动；p-only lane 关闭并切换到真正 local-h 能力。

## True local-h Attempt 1：component authority pass

clean source `b12b1887ca3acb534f36186c93e9e5efb10cf2ad` 新增了真实
dyadic 8-way cell split、face/edge/vertex strong 2:1 closure、material-interface
保护、x/y 周期镜像细化，以及拓扑上 broken、几何上 Q1 affine 的 DOLFINx
hexa carrier。DOLFINx 0.10 不支持原生 hexa refine，且不会把一个 coarse face
与四个 fine faces 识别为共享 facet；因此所有粗细邻接均由物理 geometry-key
catalog 管理，不依赖 `shared_facet` ghost 或 partition-dependent entity ID。

最小 2-cell fixture 中，只细化左 cell：

| metric | authority |
|---|---:|
| leaves | 9（而全局坐标平面 control 为 12） |
| canonical vertices / topological facets | 31 / 42 |
| DOLFINx topological exterior | 30 |
| true physical exterior | 25 |
| catalogued hanging artificial exterior | 5 = 1 coarse + 4 fine |
| unexplained exterior | 0 |
| physical boundary area | 10.0，exact |

p4/p5/p6 的 canonical coarse-to-four-fine H(curl) restriction 分别为
`144x40`、`220x60`、`312x84`，均 full column rank，并与配对 H1
restriction 保持 gradient commuting。进一步覆盖：

- 6 个 hexa local face chart；
- 8 个 quadrilateral D4 orientation；
- 4 quadrants × 8 coarse D4 × 8 fine D4 = 256 种组合/degree；
- local static condensation 后施加 hanging constraint 与 one-shot
  constrained Schur 等价；
- fine patch 的全部 144/220/312 rows 是 dependent slave；`104/160/228`
  只是 fine 坐标数相对 coarse 的 excess，不能冒充实际 slave row 数。

实际 3×3×1 x/y-periodic corner fixture 使用非平凡
`phase_x=exp(0.2i)`、`phase_y=exp(-0.3i)`：

| metric | p4 measured |
|---|---:|
| leaves / hanging patches | 37 / 8 |
| physical edges / faces | 260 / 170 |
| raw trace rows | 5,120 |
| hanging primary / secondary blocks | 8 / 4 |
| periodic primary / secondary blocks | 64 / 8 |
| independent trace rows | 3,384 |
| maximum flattened chain depth | 2 |
| maximum hanging/Floquet compatibility residual | `1.4621e-15` |
| physical authority SHA256 | `19e032d3b15828dda119a0eef7e5c25b575ea94a0324e30df79b7e35c096afa8` |

MPI1/2/8 独立运行重现相同 physical identity：

```text
records/local_h_attempt1_mpi1_v1.json
  sha256 = e652641ff8f7677f235abfe4d3c968032ee41adcc8737dc9c32e782aacba5e63
records/local_h_attempt1_mpi2_v1.json
  sha256 = 4682639ca2ff985408231a950bde9686da5edec2504312a864a3b2dce9675c8e
records/local_h_attempt1_mpi8_v1.json
  sha256 = 62d3d8f1d61f5055bc2e09f385dc3735c581b24db5b4c4b0cadb21b29ce188d1
records/local_h_attempt1_mpi_identity_v1.json
  sha256 = d341ad69dd52df6bbedcec8a522084cd75ae99fd9fd7d751bab7bfb73655fe44
```

复现入口：

```bash
python benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/generate_local_h_attempt1_authority.py \
  --source-sha b12b1887ca3acb534f36186c93e9e5efb10cf2ad \
  --output /tmp/local_h_attempt1_mpi1.json

mpiexec -n 2 python benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/generate_local_h_attempt1_authority.py \
  --source-sha b12b1887ca3acb534f36186c93e9e5efb10cf2ad \
  --output /tmp/local_h_attempt1_mpi2.json

mpiexec -n 8 python benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/generate_local_h_attempt1_authority.py \
  --source-sha b12b1887ca3acb534f36186c93e9e5efb10cf2ad \
  --output /tmp/local_h_attempt1_mpi8.json
```

本 authority 的边界是明确的：

```text
compiled_cell_tensor_binding_complete = false
mpi_constraint_row_ownership_qualified = false
mpi_ghost_expansion_qualified = false
heavy_pde_started = false
pde_accuracy_credit = false
```

因此它是 Attempt 1 的结构正信号，不是 local-h PDE success。下一步为
Attempt 2：把 physical-key flattened graph 绑定到每个实际 cell 的 oriented
trace、compiled FFCx tensor、`C_K^H S_K C_K`、RHS/recovery 和 PETSc row
ownership；全部 component Gate 通过后才允许启动最少的 MPI8 local-h PDE。

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

## Task035d MPI8 正式 p-only Gate

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
`p6/h10/S/MPI8/default/no-swap` 及显式 `--task035d-candidate-id` 对应的
冻结 plan 与 MPI8 plan authority。T30 仍是历史正式负证据；
`sidewall_z0_guard_v1` 是唯一获准的下一恢复点。
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

唯一恢复点把 plan、authority 和 checker candidate identity 同时切换：

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
  --task035d-case097-gate \
  --task035d-candidate-id sidewall_z0_guard_v1 \
  --stage4-variable-p-cell-degree-plan \
    benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/records/sidewall_z0_guard_h10_cell_degree_plan_v1.json \
  --stage4-variable-p-cell-degree-plan-sha256 \
    31922411775580b2f44b474897dbf877d96b7887f74d22e02b3f0e410c205bc2 \
  --task035d-plan-authority \
    benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/records/physics_guard_plan_authority_mpi8_v1.json \
  --task035d-plan-authority-sha256 \
    ccf40707125425540bd60a8118fed4fd74f9138968624255eb1e4fa25c8e911d \
  --verified-clean-sha "${clean_sha}" \
  --warning-gib 48 \
  --terminate-gib 96 \
  --timeout-seconds 21600 \
  --artifact-root benchmarks/artifacts/task035d/case097 \
  --record \
    benchmarks/artifacts/task035d/case097/sidewall_z0_guard_h10_mpi8_watchdog.json

watchdog_sha="$(sha256sum \
  benchmarks/artifacts/task035d/case097/sidewall_z0_guard_h10_mpi8_watchdog.json \
  | cut -d' ' -f1)"

python -m benchmarks.task035d_case097_checker \
  --candidate-id sidewall_z0_guard_v1 \
  --watchdog \
    benchmarks/artifacts/task035d/case097/sidewall_z0_guard_h10_mpi8_watchdog.json \
  --watchdog-sha256 "${watchdog_sha}" \
  --output \
    benchmarks/artifacts/task035d/case097/sidewall_z0_guard_h10_mpi8_check.json
```

## Attempt 2：真实 local-h production binding

Attempt 2 把 Attempt 1 的物理 geometry-key graph 绑定到实际单元的 oriented
trace、compiled FFCx p4/p5/p6 tensor、`C_K^H S_K C_K`、RHS、recovery、
Floquet/hanging 消元和 PETSc owner-routed rows。MPI1/2/8 component
authority 共同证明：

- coarse/fine H(curl) trace restriction 与配套 H1 gradient commuting；
- periodic、material、2:1 closure 以及 hanging/Floquet flattening；
- inactive p6 mode、hanging slave 和 periodic slave 均不获得 global row；
- local Schur、recovery 和完整 active-space true residual 使用同一算子；
- MPI 分区不改变 physical mesh、degree plan、constraint graph 或矩阵 action。

期间保留了两类真实失败证据：

- MPI2 production integration 首次暴露 owner-routing 不完整，保存为
  `local_h_production_mpi2_v3_integration_controlled_failure.json`；
- field checker 首次无法唯一定位局部 h 边界点，保存为
  `h15_top_air_local_h_field_probe_evidence_failure_v1.json`。

修复只扩展了 owner-routed cache 和明确的 VTK cell-position fallback；
没有降低 residual、field 或 12-channel Gate。正式 component authority 为：

```text
records/local_h_attempt2_mpi_identity_v3.json
records/local_h_production_mpi_identity_v3_owner_gate_fix2.json
records/h15_top_air_local_h_plan_v1.json
```

## Phase C–E 正式 MPI8 结果

所有表中 peak 是 simultaneous process-tree authority；PSS/USS 来自同一
MPI8 timeline 中逐 rank `smaps_rollup`。基线为 p6/h10 Full3D static：
`173,802` FE DoF、`51,272` rows、`41,989,040` matrix NNZ、
`212,343,992` factor NNZ、`14.721756 GiB`。

| candidate | local-h / p plan | FE DoF / rows | matrix / factor NNZ | residual | peak GiB | powers / amplitudes | status |
|---|---:|---:|---:|---:|---:|---:|---|
| h15 top-air local-h | 134 leaves；p5 trace / p6 interior | `82,925 / 18,470` | `10,186,108 / 30,865,200` | `5.740e-12` | `7.50068` | `6/12 / 6/12` | controlled negative |
| symmetric local-h + remote p5 interior | 148 leaves；p5/p6 interior `32/116` | `84,240 / 20,060` | `11,176,430 / 32,658,700` | `2.124e-11` | `7.50883` | `4/12 / 4/12` | controlled negative |
| top-air local-h + remote p5 interior bridge | 134 leaves；p5/p6 interior `32/102` | `76,205 / 18,470` | `10,186,108 / 30,865,200` | `3.433e-12` | `7.29866` | `4/12 / 4/12` | controlled negative |
| ten-face selective p6 trace | 134 leaves；p6 interior + 10 p6 faces | `83,125 / 18,670` | `10,406,108 / 32,683,000` | `1.287e-11` | `8.06898` | `5/12 / 6/12` | controlled negative |
| left-grating single-root local-h | 162 leaves；p5/p6 interior `48/114` | `88,915 / 21,650` | `12,382,332 / 37,250,750` | `3.267e-11` | `8.06120` | `4/12 / 6/12` | controlled negative |

Task035d `task.md` §3.2 要求的 global p6/p5 h10、Task035 DWR、
Task035b fixed h15/h14/h13 与本任务 p-only/h-only/combined best 统一
控制表见
`docs/task035d_goal_oriented_exact_sequence_hp_adaptivity/outcomes/summary.md`
§4.1。缺失的历史 channel/peak 字段保持 `not recorded`，没有反推。

所有 local-h 候选的 trace 仍为全局 p5，除十面 selective 候选外没有 p6
face。第一个 h15 top-air
候选在 checker 修复后重新资格化：原 watchdog 的结构失败是 checker 对
authority hash 语义的 false negative，数值 kernel 不需要重跑；物理结论仍为
`6/12 + 6/12` controlled negative。

### h/p factorial 判别

对同一 top-air local-h 网格，三点实际比较为：

| action | DoF / rows | peak | powers / amplitudes | 结论 |
|---|---:|---:|---:|---|
| h-only，细子单元保持 p6 interior | `82,925 / 18,470` | `7.50068 GiB` | `6/12 / 6/12` | 相对最强物理信号 |
| symmetric h + remote p5 interior | `84,240 / 20,060` | `7.50883 GiB` | `4/12 / 4/12` | p-down 使弱通道退化 |
| top-air h + remote p5 interior bridge | `76,205 / 18,470` | `7.29866 GiB` | `4/12 / 4/12` | 最小 DoF/peak，但没有同精度 |

因此 remote p5-interior lane 的资源收益是真实的，但不能获得 combined-hp
精度信用。`hp_factorial_bridge_attribution_v1.json` 将该 lane 关闭为
controlled negative。

## Selective p6 trace 与 actual channel DWR

十个 grating-top face 的 p6 trace mode 在 assembly 前进入真实 active space；
不是完整 p6 trace 矩阵后置零。coarse/enriched 两端点生成 12 个 unit-channel
adjoint 和 36 个实目标（12 power + 24 amplitude component）：

```text
independent checker goals = 36/36 pass
power goals = 12/12 pass
amplitude-component goals = 24/24 pass
selected faces = 10
physical endpoint = 5/12 powers + 6/12 amplitudes
production_qualified = false
```

首次 embedded checker 把 authority semantic hash 与 transfer-content hash
混比，产生受控 checker false negative；独立 checker 修复后从原始报告重算
36/36，不重跑 PDE。DWR closure 只证明这十个 face 的 actual cross-trace
响应计算正确，不能把失败的物理端点写成成功，也不能把未运行的其他
face/orbit/edge mode 判为无效。

权威证据：

```text
records/selective_face_selection_compact_v1.json
raw DWR SHA256 =
  bd19254aff1096b864d30b70d1e44d93802b4721e19c861ad8064939d1776bf1
raw endpoint checker SHA256 =
  258439c0c7a8dffb91d87c9fc5dca3fe749ff65fce1de7675695ed06fe64b875
```

冻结十面子集的 measured 结果为 `5/12 + 6/12`；32 个线性子集预测中，
上限也只有 `6/12 + 7/12`。所以只关闭该 frozen subset lane；整个 top-port
selective-p6-trace 能力保留为 `incomplete_not_run_no_authorized_candidate`。

## Bounded single-root local-h discriminator

`bounded_single_seed_top_air_hp_selection_v2.json` 只比较一个 requested root
seed 加 mandatory periodic/material closure。它使用 compact DWR 作为位置
oracle，并按 added DoF/rows 归一化，但明确没有 actual local-h DWR surplus，
也不给 goal-oriented selection credit。

left-grating action 的 oracle score 强于 outer-periodic：

| action | score / 1000 added DoF | score / 1000 added rows | actual local-h DWR | PDE |
|---|---:|---:|---|---|
| left-grating top | `55.28` | `162.54` | unavailable | run |
| outer-periodic | `35.29` | `101.01` | unavailable | not run by lane stop |

正式 left-grating candidate 固定：

```text
root / leaf cells = 120 / 162
hanging patches = 14
p5 / p6 interiors = 48 / 114
raw / conforming active FE DoF = 91,805 / 88,915
raw / independent trace rows = 28,985 / 21,570
hanging / periodic slave rows = 2,890 / 4,525
DtN-appended solve rows = 21,650
selected p6 faces = 0
```

结构、exact-sequence、MPI、residual 和资源 Gate 全部通过。相对 p6/h10
static：

| metric | candidate | reduction | Gate |
|---|---:|---:|---|
| rows | `21,650` | `57.7742%` | pass |
| matrix NNZ | `12,382,332` | `70.5106%` | pass |
| factor NNZ | `37,250,750` | `82.4574%` | pass |
| peak | `8.061199 GiB` | `45.2430%` | preferred pass |
| PSS / USS | `6.926574 / 6.777557 GiB` | measured | diagnostic |
| swap | `0` | n/a | pass |

物理 observables 也通过：

```text
R00 = 0.000755218940190701
R = 0.000764349909194991
T = 0.602685528512531
Aclosure = 0.396550121578274
Avolume = 0.396550121578974
normalized R/T/Aclosure L2 = 0.117446
```

但 volume maximum-point error 为 `0.04688675 > 0.04102079`，且显著通道
只有 `4/12 powers + 6/12 amplitudes`。逐通道未放宽 Gate：

| side/order | power error / tolerance | amplitude error / tolerance |
|---|---:|---:|
| bottom -7 | `5.617175e-9 / 2.158694e-9` fail | `2.550563e-6 / 1.216565e-5` pass |
| bottom -5 | `6.906912e-9 / 3.891273e-10` fail | `4.459072e-6 / 1.280646e-6` fail |
| bottom -4 | `1.204267e-8 / 5.251003e-10` fail | `1.418775e-5 / 2.541658e-6` fail |
| bottom -2 | `1.284216e-8 / 4.651045e-9` fail | `7.478303e-6 / 4.580806e-6` fail |
| bottom -1 | `1.638713e-8 / 1.114414e-7` pass | `4.142307e-6 / 1.272899e-5` pass |
| bottom 0 | `1.609820e-5 / 2.175766e-4` pass | `5.003714e-4 / 6.779629e-3` pass |
| top -7 | `2.836735e-9 / 1.249444e-9` fail | `1.978697e-6 / 7.995039e-7` fail |
| top -5 | `2.914386e-9 / 1.194302e-9` fail | `2.376892e-6 / 1.113206e-6` fail |
| top -4 | `5.355565e-9 / 1.086492e-9` fail | `1.087300e-5 / 1.881525e-6` fail |
| top -2 | `4.439407e-9 / 1.242282e-9` fail | `1.125110e-6 / 3.186491e-6` pass |
| top -1 | `1.114167e-8 / 5.111835e-8` pass | `3.256777e-6 / 7.413384e-6` pass |
| top 0 | `1.457720e-6 / 3.195287e-5` pass | `4.510204e-5 / 8.330267e-4` pass |

权威记录：

```text
records/h15_left_grating_top_closure_p5fine_mpi8_candidate_check_v1.json
  sha256 = 1b9dd3cdb931f5fe69da5a0a567ff278a47416f7082d47cef2e0b5e4109e2492
records/h15_left_grating_top_closure_p5fine_mpi8_controlled_negative_compact_v1.json
  sha256 = d6e03061465b29ce4e958bfd6ac7972f245130fdf66de197541caed09e8e4225
```

正式运行耗时 `297.114 s`；base matrix assembly `256.515 s`，MUMPS
setup/solve `13.524/0.041 s`。这些阶段计时存在嵌套，不能相加为 total。

## Lane closure 与未运行项

`bounded_single_root_top_air_lane_closure_v1.json` 绑定两个正式精度负信号：

1. h15 top-air local-h：`6/12 + 6/12`；
2. left-grating single-root：`4/12 + 6/12`，并失败 volume max-point Gate。

两点共享 h15 balanced dyadic-hexa、global p5 trace 和单 root + mandatory
closure 范围；interior 是两个显式审计的 variant：top-air control 的细子
单元保持 p6，left-grating discriminator 的新细子单元使用 p5。lane closure
不把第一个候选误写成 p5-fine。

按 Task035d “同一 lane 连续两个数值负信号后关闭”的规则：

| item | final status | 说明 |
|---|---|---|
| bounded single-root top-air local-h | closed after two formal negatives | 不继续盲扫 |
| outer-periodic | `not_run_by_lane_stop` | 较弱 oracle；不是 PDE failure |
| multi-seed combinations | `not_evaluated_by_stop_rule` | 单 seed lane 已关闭 |
| frozen ten-face selective p6 subset | `closed_controlled_negative` | measured 5/12 + 6/12 |
| whole top-port selective p6 trace | `incomplete_not_run_no_authorized_candidate` | 未运行 modes 不能被十面子集证伪 |
| Hybrid Phase F | `not_run_full3d_hp_gate_failed` | Hybrid 不给失败 Full3D 候选精度信用 |

重新开启的最低条件是：先在新定义的 candidate space 上生成 actual
per-channel local-h 或 trace-orbit DWR，再授权唯一判别点。当前 compact
location oracle 不足以支持更多重型 PDE。

## Final left-grating provenance-safe 复现

正式 authority 绑定 numerical source
`333cb7e437906c78c95c94788abb76e2f263bc80`。以下模板会先拒绝其他 HEAD，
并把 watchdog、field 和 checker 输出写到新建的 `/tmp` 目录；它不会覆盖
tracked full/compact checker 或原始 hash-bound artifact。watchdog 自行启动
MPI8，外层不要再套 `mpiexec`：

```bash
cd /home/Projects/MyFEniCS
source scripts/activate_myfenics_wsl.sh

record_source_sha=333cb7e437906c78c95c94788abb76e2f263bc80
current_sha="$(git rev-parse HEAD)"
if [[ "${current_sha}" != "${record_source_sha}" ]]; then
  echo "Refusing exact reproduction: use a clean source checkout at ${record_source_sha}"
  exit 2
fi
clean_sha="${current_sha}"
repro_root="$(mktemp -d /tmp/myfenics-task035d-left-grating.XXXXXX)"
watchdog_path="${repro_root}/watchdog.json"
checker_path="${repro_root}/candidate_check.json"

python -m benchmarks.run_task033_full3d_watchdog \
  --degree 6 \
  --h-nm 15 \
  --polarization-kind s \
  --run-kind full-solve \
  --mpi-size 8 \
  --profile default \
  --stage4-full3d-assembly-backend assembly_time_variable_p_condensed \
  --task035d-case097-gate \
  --task035d-candidate-id h15_left_grating_top_closure_p5fine_v1 \
  --stage4-local-h-refinement-plan \
    benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/records/h15_left_grating_top_closure_p5fine_plan_v1.json \
  --stage4-local-h-refinement-plan-sha256 \
    08e33b5441460029bb3c88d18a63b884782cfc1aef734371f48324116885b393 \
  --task035d-plan-authority \
    benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/records/left_grating_top_closure_p5fine_mpi_identity_v1.json \
  --task035d-plan-authority-sha256 \
    ab6d4ab768feafd7309455bc99776fb383a7f2b6523cc16649158f66de358bd8 \
  --verified-clean-sha "${clean_sha}" \
  --warning-gib 48 \
  --terminate-gib 96 \
  --timeout-seconds 21600 \
  --artifact-root "${repro_root}/artifacts" \
  --record "${watchdog_path}"

watchdog_sha="$(sha256sum "${watchdog_path}" | cut -d' ' -f1)"

python -m benchmarks.task035d_case097_checker \
  --candidate-id h15_left_grating_top_closure_p5fine_v1 \
  --watchdog "${watchdog_path}" \
  --watchdog-sha256 "${watchdog_sha}" \
  --output "${checker_path}"

echo "Reproduction outputs: ${repro_root}"
```

## Final test receipt

```text
Task035d focused serial = 215 passed, 13 skipped
Task035d MPI2 components = 80 passed, 10 skipped
Task035d MPI8 representative = 16 passed, 4 skipped per rank
full repository = 837 passed, 41 skipped
Case097 compact authority = pass
registry / Ruff / compileall / JSON / diff-check = pass
```

全库回归发现并修复一个不属于 Task035d Full3D PDE 的 Hybrid API 组合遗漏：
`hybrid_local_dtn.py` 向 collective significant-entry helper 补传
`comm=comm`。Task032/033/035b Hybrid targeted tests 和全库均通过。
Task035d 正式 Full3D numerical blob 未改变，所以不重跑 heavy PDE。
