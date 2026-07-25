# Task035b Response V5：Review V3 选择性合并与 static Hybrid 回应

## 1. 身份与最终结论

```text
response_status = PARTIAL_WITH_CONTROLLED_NEGATIVES
review = review_report_v3.md
selective_merge_master_sha = 1fb144d3ca50208c22b5f0733e140bfac8d9c47c
execution_branch = codex/20260726-task35b-high-order-local-hp-resource-envelope
numerical_evidence_source = 148729c28c3f9aefec8e5646cc644c5c4e2332da
formal_MPI = 8
ordinary_default = standard_full
ordinary_default_changed = false
H0_static_hybrid = implemented_and_algebraically_qualified
H1_A_p2_h5 = controlled_negative
H1_B_p2_h3 = not_run_by_review_prerequisite
H1_C_high_order = not_run_after_h1a_numerical_gate
H1_D_h13_seed = not_run_after_h1a_numerical_gate
adaptive_hybrid = not_run_after_h1a_numerical_gate
second_master_merge = not_authorized
```

Review V3 的 M0–M4 已完成：项目模型总账完成 Task000–Task035b 连续回填，
公共 assembly backend 端口建立，403 个候选路径逐文件分类，只选择性迁移
154 个路径到干净 master；旧 20260723 stacked branch 没有整体 merge。

新分支随后完成 H0 和 H1-A。静态凝聚本身是合格的：Full3D
standard/static、Hybrid standard/static 以及 static Hybrid M120/M160
全部达到 12/12 powers + 12/12 complex amplitudes 的同路径等价。
但是 static Full3D ↔ static Hybrid 没有通过 Review V3 H3：
Task033 相对 `1e-3` 口径只有 **3/12 + 2/12**，strict absolute audit
只有 **2/12 + 2/12**。M120→M160 几乎不变，排除了 M 数不足。H1-A
因此是 preserved controlled negative，H1-B 的明确前置条件未满足。

这不是凭据、ABI、源码身份或内存安全 blocker，而是 Review V3 指定的
numerical Gate。按用户要求和 Review 停止规则，不能继续用 p2/h3、高阶点
或 h13 adaptive run 掩盖它。

## 2. M0–M4 选择性合并闭环

### 2.1 模型总账

`docs/development_model_registry.md` 现有 3.1–3.37 共 37 个连续 Task
章节，登记 67 个 evidence paths，并保持以下一级方法结构：

```text
COMSOL direct / successful iterative
FEniCS standard-full direct: Full3D / Hybrid
FEniCS standard-full iterative: Full3D / Hybrid
static-condensed direct: Full3D / Hybrid
static-condensed iterative: Full3D / Hybrid
adaptive: Full3D / Hybrid
```

早期没有保存的字段明确写“历史未记录”，当前没有运行的字段写
`not_run`；失败通道、residual 和 resource Gate 写实际值，不用 0
补缺，不从功率反推复振幅。只读 checker 检查章节连续性、统一表头、
evidence path、占位符与状态合同。

### 2.2 单一用户端口

公开配置为：

```python
stage4_full3d_assembly_backend = "standard_full"
# opt-in:
# "assembly_time_static_condensed"
```

`standard_full` 保持普通默认和历史矩阵行为；static backend 只在
complex128、Nédélec、axis-aligned affine hexa、fixed rectangular
target、完整 material tags、Floquet-before-insertion、sparse DtN 和
complete direct solve 合同下资格化。不支持 tetra、mixed/curved/
distorted hexa、irregular geometry 或 production selective trace 时
fail closed，并提示使用 `standard_full`；不会静默降级后伪报 static。

### 2.3 文件级 manifest 与 merge

| item | result |
|---|---:|
| branch/master diff 与 untracked 分类 | 403 paths |
| 最终选择性迁移 | 154 paths |
| production numerical/core | included by dependency group |
| reusable runner/watchdog/checker | only reviewed minimal closure |
| compact evidence/docs | included |
| selective trace research capability | not promoted |
| failed condensed iterative profiles | not promoted；compact negatives retained |
| non-exact-sequence space | not promoted |
| irregular/tetra-static/mixed-mesh capability | not promoted |
| selective merge master | `1fb144d3ca50208c22b5f0733e140bfac8d9c47c` |

精确 allowlist、来源 SHA、目标 SHA、依赖组和排除理由见
`outcomes/selective_merge_manifest_v1.md` 及其 JSON authority。旧分支
closeout 提交为 `a810a13...`；新分支从上述 clean master 创建。

## 3. H0：静态凝聚与 Hybrid 结合

H0 保持 Task032/033 的二维 QEP、双向传播、matching trace 与 M 定义，
只对上下局部三维 FEM 做 exact cell-interior Schur：

```text
local cell matrix
  -> eliminate cell interior
  -> retain periodic-independent exterior/interface trace
  -> retain external DtN auxiliaries and internal modal amplitudes
  -> left/right-condense external/internal coupling and RHS
  -> solve
  -> streaming full-field recovery
  -> full explicit and eliminated-equation residual
```

主要实现：

- `src/solvers/hybrid_local_static_condensation.py`；
- `src/solvers/hybrid_static_field_recovery.py`；
- local DtN、internal-mode coupling、augmented/minimal solver 和正式
  watchdog 接线；
- `src/test/test_179_task035b_hybrid_static_condensation.py`。

实现没有形成完整 p6 trace 后置零，没有消去 modal amplitudes 或接口
tangential trace，也没有分配 full global local-FE matrix 或长期保留
`N_FE × M` dense payload。

## 4. H1-A 四路 p2/h5 对照

| path | rows | matrix NNZ | factor NNZ | peak | residual | R / T / Aclosure |
|---|---:|---:|---:|---:|---:|---|
| Full3D standard | 44,778 | 4,896,156 | 31,053,132 | 2.960 GiB | `9.73e-12` | `0.0890216029363 / 0.442588278657 / 0.468390118407` |
| Full3D static | 30,800 | 3,229,040 | 26,995,728 | 2.763 GiB | `8.21e-12` | `0.0890216029363 / 0.442588278657 / 0.468390118407` |
| Hybrid standard M160 | 14,052 | 1,454,248 pair | 6,390,216 pair | 3.285 GiB | `2.55e-12` | `0.0890210691 / 0.4425867427 / 0.4683921882` |
| Hybrid static M160 | 10,000 | 976,400 pair | 5,986,184 pair | 3.308 GiB | `3.45e-12` | `0.0890210691063 / 0.442586742743 / 0.468392188151` |

每个 local FEM side 的完整空间为 6,826 DoF；静态凝聚后保留 4,800
periodic-independent trace rows 和 40 external auxiliary rows。M160
再增加 320 modal rows，故 total inventory 为 10,000。44,698
Full3D-equivalent DoF 始终保留为离散身份，不能改写成 10,000 DoF。

### 4.1 等价与同离散闭合

| comparison | power | amplitude | result |
|---|---:|---:|---|
| Full3D standard ↔ static | 12/12 | 12/12 | pass |
| Hybrid standard M120 ↔ static M120 | 12/12 | 12/12 | pass |
| Hybrid standard M160 ↔ static M160 | 12/12 | 12/12 | pass |
| static Hybrid M120 ↔ M160 | 12/12 | 12/12 | converged |
| static Full3D ↔ static Hybrid M120 | 3/12 | 2/12 | fail |
| static Full3D ↔ static Hybrid M160 | 3/12 | 2/12 | fail |

strict unchanged-v0 absolute audit 的后两行均为 2/12 + 2/12。watchdog
里的 `formal_pass=true` 只代表 source/resource/numeric shard 合格；
`physical_qualified=false` 没有被改写。

### 4.2 M160 失败通道实际值

| channel | Full3D power | Hybrid power | abs difference / frozen limit | amplitude abs difference / limit |
|---|---:|---:|---:|---:|
| T(-7,0) | `6.576075e-6` | `6.573404e-6` | `2.672e-9 / 2.159e-9` | `1.556e-5 / 1.217e-5` |
| T(-5,0) | `7.173940e-8` | `1.667074e-7` | `9.497e-8 / 3.891e-10` | `8.734e-5 / 1.281e-6` |
| T(-4,0) | `5.351330e-7` | `3.172633e-7` | `2.179e-7 / 5.251e-10` | `1.344e-4 / 2.542e-6` |
| T(-2,0) | `1.008643e-6` | `4.723171e-7` | `5.363e-7 / 4.651e-9` | `2.030e-4 / 4.581e-6` |
| T(-1,0) | `3.839972e-6` | `5.146400e-6` | `1.306e-6 / 1.114e-7` | `1.890e-4 / 1.273e-5` |
| R(-7,0) | `2.241059e-6` | `2.232991e-6` | `8.068e-9 / 1.249e-9` | `4.292e-6 / 7.995e-7` |
| R(-5,0) | `1.270116e-7` | `1.984830e-7` | `7.147e-8 / 1.194e-9` | `4.540e-5 / 1.113e-6` |
| R(-4,0) | `2.208844e-7` | `9.446546e-8` | `1.264e-7 / 1.086e-9` | `6.887e-5 / 1.882e-6` |
| R(-2,0) | `1.920773e-7` | `7.121444e-8` | `1.209e-7 / 1.242e-9` | `1.146e-4 / 3.186e-6` |
| R(-1,0) | `5.779799e-6` | `6.647511e-6` | `8.677e-7 / 5.112e-8` | `1.027e-4 / 7.413e-6` |

`T(-7,0)` power 在相对 `1e-3` 口径通过，但其 amplitude 和 strict
absolute power audit 失败；零级 T/R 在所有口径通过。完整 12 行两侧
complex values 和每项 pass/fail 位于 compact JSON。

## 5. 场、接口、恢复与资源

### 5.1 正确性分层

| metric | static Hybrid M160 | result |
|---|---:|---|
| full explicit true residual | `3.450e-12` | pass |
| bottom/top full-operator residual | `1.782e-12 / 3.868e-12` | pass |
| eliminated-interior max residual | `5.350e-14 / 6.920e-14` | pass |
| interface E relative L2 | `1.664e-7 / 2.476e-7` | pass |
| interface H relative L2 | `7.417e-3 / 6.732e-3` | pass |
| middle-plane E/H relative L2 | `2.880e-4 / 8.792e-4` | pass |
| 12 significant channels | 3/12 / 2/12 | **fail** |

总量、residual 和场范数通过不能覆盖弱衍射级失败。

### 5.2 资源

Full3D static 相对 standard 的 rows/NNZ/factor/peak 分别下降
31.22%/34.05%/13.07%/6.65%，是合格工程正结果。

Hybrid M160 的结果不同：

| metric | standard | static | change |
|---|---:|---:|---:|
| rows | 14,052 | 10,000 | -28.84% |
| matrix NNZ pair | 1,454,248 | 976,400 | -32.86% |
| factor NNZ pair | 6,390,216 | 5,986,184 | -6.32% |
| fill | 4.394 | 6.131 | +39.52% |
| peak | 3.285 GiB | 3.308 GiB | +0.71% |
| total | 96.28 s | 186.36 s | +93.56% |
| internal modal coupling | 11.72 s | 110.62 s | +843.7% |

所以 Hybrid resource signal 是 `mixed_negative`，不能把 rows/NNZ 减少
写成内存或时间成功。当前瓶颈是 static left/right modal correction，
不是 local FEM assembly 或 MUMPS solve。

## 6. Gate A、Gate B 与未运行项

| item | conclusion |
|---|---|
| H1-A static algebraic equivalence | pass |
| H1-A Hybrid same-discretization physics | **fail** |
| A1 Gate A：无新增 Hybrid 误差 | 未建立；p2/h5 已失败 |
| A1 Gate B：绝对参考精度 | not reached |
| H1-B p2/h3 | `not_run_by_review_prerequisite` |
| H1-C p3/h7.5 | `not_run_after_h1a_numerical_gate` |
| H1-D fixed p5-trace/p6-interior h13 | `not_run_after_h1a_numerical_gate` |
| adaptive candidates | 0 |
| 0.7 nm resource model v3 update | not run；没有新 accuracy-qualified Hybrid candidate |

没有启动 irregular geometry、selective trace production、failed condensed
iterative profile、non-exact-sequence space、tetra static condensation 或
mixed mesh。

## 7. Evidence、registry 与测试

compact authority：

- `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/hybrid_static_condensation_h1a_mpi8_v1.json`

详细结果：

- `outcomes/hybrid_static_condensation_h1.md`
- `outcomes/summary.md`
- `docs/development_model_registry.md`

测试与 Gate：

| layer | result |
|---|---|
| selective-merge full repository before master merge | `570 passed, 28 skipped` |
| H0 focused serial/MPI2/MPI8 | pass；包括 MPI8 `test_179` 5 tests/rank |
| H0/H1-A focused serial | `124 passed in 261.92 s` |
| H0 static-condensation MPI8 | each rank `5 passed in 4.61–4.62 s` |
| documentation/Case095/registry | `34 passed in 1.07 s` |
| full repository，first | `581 passed, 28 skipped, 1 failed`；发现 Task034 blob successor classification 缺失 |
| governance targeted after fix | `24 passed in 4.40 s` |
| full repository，final | **`582 passed, 28 skipped in 452.93 s`** |
| JSON parse、changed-Python Ruff、compileall | 892 files / pass / pass |

两次没有进入 PDE 的 fresh-anchor preflight negatives 和所有历史失败
evidence 均保留；没有 reset、rebase、force push、删除 records 或修改
ordinary default。本分支的第二次 master merge 未获授权，提交推送后停在
numerical Gate 等待集中审阅。
