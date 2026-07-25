# Task035b Response V4：Review V3 选择性合并闭环

## 1. 交付身份与总决定

```text
response_status = REVIEW_V3_SELECTIVE_MERGE_COMPLETE
archive_branch = codex/20260723-task35b-high-order-local-hp-resource-envelope
archive_pre_response_head = 417eb4211ab662790236bd0c81ac1c110343985a
master_base = 5002636852ffb67b4711443da70eb536c303e34e
selective_integration_branch = codex/20260726-task35b-selective-integration
selective_integration_commit = 06c3e95eda2a0239ac23ecd4df5e7e7687c5bb25
master_merge_commit = 1fb144d3ca50208c22b5f0733e140bfac8d9c47c
merge_method = no_ff_merge_of_file_level_selective_integration
whole_research_branch_merge = false
master_pushed = true
master_worktree_after_merge = clean
ordinary_default = standard_full
static_condensation_public_backend = assembly_time_static_condensed
static_condensation_backend_default = false
Task035_status = accepted_research_infrastructure
Task035b_accuracy_status = partial_with_controlled_negatives
best_h13_significant_gate = 10_of_12_power_and_10_of_12_amplitude
user_hard_blocker = false
```

Review V3 的 M0–M4 已闭环。旧的 265-commit research branch 没有整体
merge；选择性集成从干净 `master@5002636...` 开始，只迁移 allowlist
依赖组和经清洗的 extracted successors，形成单独集成提交，再以 `--no-ff`
合入 master。merge commit 的 tree SHA 与已测试的 integration commit
完全相同：

```text
tree_sha = 2012b173d0ab4b21eaf6875eb354add78dbcf307
```

因此 merge commit 没有引入额外文件或数值变化。

## 2. M0：项目级模型总账

`docs/development_model_registry.md` 已按 Review V3 固定一级分类回填：

- COMSOL direct / successful iterative；
- FEniCS original-full direct / iterative，分别登记 Full3D 与 Hybrid；
- static-condensed direct / iterative，分别登记 Full3D 与 Hybrid；
- Full3D / Hybrid adaptivity。

第 3 章连续覆盖 Task000–Task035b 共 37 个 Task section。每个 Task
使用统一的研究问题说明和模型表，明确数据身份、物理、离散、算法、规模、
R/T/A、逐级衍射、资源与状态。历史缺失字段写成“历史未记录”或
`not_run`，没有填 0 或从 power 反推 complex amplitude。

负结果保留实际失败对象和数值，包括：

- Task035 受控负结果与 one-local-h research stop；
- Task035b h13 的 `T(-4,0)`、`R(-4,0)`、`r(-4,0)`、`r(-5,0)`；
- 三条 condensed iterative terminal ratio：
  `0.8616624409`、`0.9996606194`、`0.9962645476`；
- selective trace 正式 PDE candidate 数为 0；
- irregular geometry 为 `out_of_scope_by_user/not_run/not_a_completion_gate`。

只读校验结果：

```text
task_section_count = 37
task_sequence = Task000 ... Task035, Task035b
evidence_paths_checked = 67
registry_errors = 0
```

Case094 checker 验证 6 条 compact authority，Case095 checker 验证
19 条 compact authority。Task035b candidate ledger 共 68 行：

```text
tracked_compact_authority = 18
tracked_project_document = 5
source_branch_archive_not_merged = 45
```

后 45 条只保留 archive path/hash/source SHA，不读取或复制旧分支 raw
record。

## 3. M1：统一 assembly backend 用户端口

公开端口为：

```python
stage4_full3d_assembly_backend = "standard_full"
# opt-in:
stage4_full3d_assembly_backend = "assembly_time_static_condensed"
```

实现合同：

1. `standard_full` 保持 ordinary default；
2. `assembly_time_static_condensed` 必须显式选择；
3. 旧三布尔组合只允许 `000`、`100`、`111`，部分组合 fail closed；
4. legacy `111` 与公开端口走同一 qualification；
5. requested、actual、selection source、qualification 与 audit 都进入
   log/progress/success/failure summary；
6. original-full 与 static-condensed 共用物理配置、official
   postprocess 与 provenance；
7. unsupported scope 明确报错并提示改用 `standard_full`，不静默降级。

当前 static-condensed 资格范围严格限定为：

```text
complex128 H(curl) Nedelec
first-order axis-aligned affine hexahedron
every owned cell has an explicit material tag
Task034 fixed rectangular block grating
assembly-time cell-interior elimination
Floquet slave elimination before global insertion
sparse auxiliary DtN
full field recovery and full explicit true residual
direct MUMPS solve
```

production API 还允许全局一致、exact-sequence 审计通过的
`fixed p5-trace + p6-interior` element。`p4-trace/p6-interior` 等
non-exact 空间由 API 和回归测试明确拒绝。

## 4. M2/M3：文件级 manifest 与实际迁移

`selective_merge_manifest_v1.csv/md` 从
`master@5002636...` 与旧 research branch 实际 403-path diff 生成。

| manifest group | path count |
|---|---:|
| `production_core` | 36 |
| `research_api_opt_in` | 21 |
| `reusable_benchmark` | 14 |
| `compact_evidence` | 28 |
| `project_docs` | 51 |
| `do_not_merge` | 253 |
| **total** | **403** |

最终 integration commit 包含 154 个文件。它不是把全部非
`do_not_merge` 文件机械复制，而是按真实 import/test 依赖迁移并对交叉文件
做最小 extracted successor：

| integration area | files |
|---|---:|
| root governance | 2 |
| Case094/095 compact contracts and records | 33 |
| reusable benchmark/checker tools | 5 |
| project docs | 8 |
| Task035/035b task/review/response/outcomes | 42 |
| quick-start | 1 |
| qualified activation | 1 |
| production/research `src` | 39 |
| tests | 23 |
| **total** | **154** |

Case094 只保留 6 条 authority；Case095 只保留 19 条 authority、compact
aggregate 和 68-candidate ledger。raw field、matrix、factor、timeline、
大型重复 JSON 与 ignored artifacts 没有进入 master。

为完成 full Ruff，另对 5 个 master 基线文件做了无数值行为变化的机械
lint closure：删除 unused imports/variables、去掉一个多余 f-string 前缀，
并把两个局部 lambda 改成等价条件选择。这些改动由 full pytest 和
Task032/033 Hybrid 回归覆盖。

## 5. 明确排除的能力

以下内容没有作为 public/production 能力进入 master：

- `selective_p6_trace_*` 与其 actual-channel DWR 原型；
- `physical_channel_dwr_trace_selection.py`；
- `missing_p6_trace_sensitivity.py`；
- `formal_h14_live_capture_bridge.py`；
- `hcurl_regionwise_p.py` 和 regionwise/inverse trace-interior 空间；
- 三条失败的 condensed iterative profiles 与 physical-slab/harmonic PC；
- non-exact-sequence p 分配；
- irregular geometry；
- tetra static condensation；
- mixed-cell static condensation。

master 只保留 selective-trace capability boundary 和 iterative
controlled-negative compact evidence，用户不能从普通 solver profile
选择这些失败能力。

Task035 的 periodic tetra、真实 discrete adjoint/DWR、uniform controls
和 same-origin h/p helpers 以 `research-grade explicit opt-in` 身份进入，
没有提升为 production automatic hp，也没有改变 ordinary default。

## 6. 数值与资源锚点

### 6.1 提交后 ordinary-full / static-condensed anchor

精确 integration commit `06c3e95...` 上重新执行 serial、MPI2、MPI8：

| backend | FE DoF | rows | NNZ | true residual | Rtotal | Ttotal |
|---|---:|---:|---:|---:|---:|---:|
| standard full, serial reference | 802 | 882 | 90,180 | `5.52e-14` | `0.9997827084780738` | `0.000108701774427765` |
| static condensed, serial | 802 | 560 | 48,412 | `1.63e-13` | `0.9997827084780743` | `0.000108701774427764` |

MPI2 static NNZ 为 48,412；MPI8 因分布式结构为 48,716。三种 MPI 数均
通过同一 R/T 与 residual 断言，static audit 证明：

```text
full_global_matrix_allocated = false
full_trace_matrix_allocated = false
exact_preallocation_mallocs = 0
full field recovered = true
eliminated interior residual measured = true
```

MPI2 fixed p5-trace/p6-interior 小型 PDE 也通过：

```text
FE DoF = 15,385
active augmented rows = 3,620
matrix NNZ = 1,871,846
full explicit residual = 3.01e-12
peak authority = 1.404 GiB sum-rank historical upper bound
```

该点再次显示 setup 瓶颈：base assembly `321.7 s`，MUMPS setup
`1.93 s`，backsolve `0.013 s`。它是资格锚点，不改变 h13 的
10/12 + 10/12 accuracy 结论。

### 6.2 h13 身份保持

Review V3 接受的 seed 身份未被改写：

```text
fixed p5 trace + p6 cell interior directional-z h13
Full3D-equivalent DoF = 89,740
active rows = 20,120
significant powers = 10/12
significant complex amplitudes = 10/12
status = under-resolved Hybrid engineering seed
```

它可以用于下一分支 Gate A 的同离散 Hybrid engineering closure，但未通过
Gate B，不能称最终 same-error 或 adaptive accuracy success。

## 7. 最终测试

| Gate | result |
|---|---|
| qualified ABI | `.venv/bin/python`; `complex128`; PETSc `int32`; activation marker `1` |
| public backend contract | 21 passed |
| fixed p5/p6 element/cache | 13 passed, 2 skipped |
| Task035/035b focused integration | 67 passed, 6 skipped；3 个选择性闭包问题修正后 9 passed, 4 skipped |
| Task032/033 Hybrid regression | 219 passed, 8 skipped；唯一 non-exact stale test 改为拒绝后 7 passed |
| MPI2 high-order Floquet + Task035 DWR | each rank 27 passed |
| MPI8 high-order Floquet + Task035 DWR | each rank 27 passed |
| post-commit serial/MPI2/MPI8 full/static PDE | all selected tests passed on every rank |
| Task034/Case093 targeted | 95 tests collected；两项 integration contract 修正并在 final full suite 通过 |
| Case094 checker | 6/6 hash/status authority pass |
| Case095 checker | 19/19 hash/status authority pass |
| registry checker | 37 Task sections；67 evidence paths；0 errors |
| full repository pytest | **570 passed, 28 skipped in 449.50 s** |
| full Ruff | pass |
| compileall | `src` and `benchmarks` pass |
| JSON parse | 11,048 JSON files parse |
| diff-check | pass |

首次 full pytest 的真实结果为 `568 passed, 28 skipped, 2 failed`：
Case094/095 尚未进入 numbered-case identity allowlist，以及 lint-only import
变化尚未在 Task034 numerical-blob checker 分类。两者都属于集成合同失败，
不是 PDE failure；修正后 targeted 27 tests 通过，最终 full suite 全绿。

## 8. Git 与 clean 状态

执行序列：

```text
master@5002636852ffb67b4711443da70eb536c303e34e
  -> file-level selective integration commit
     06c3e95eda2a0239ac23ecd4df5e7e7687c5bb25
  -> no-ff merge commit on master
     1fb144d3ca50208c22b5f0733e140bfac8d9c47c
```

远程 master 已从 `5002636...` 推进到 `1fb144d...`。merge 前后没有
reset、rebase、force push、stash 或 whole-branch merge。`.codex/config.toml`
保持用户本地文件，只由 `.gitignore` 排除，未修改、删除或提交。

master merge 后：

```text
branch = master
HEAD = 1fb144d3ca50208c22b5f0733e140bfac8d9c47c
worktree = clean
origin/master = pushed
```

Review V3 授权的下一步是从该干净 master 创建
`codex/20260726-task35b-high-order-local-hp-resource-envelope`，继续
static-condensed local-FE Hybrid 与 h13-seeded 两层精度 Gate。该新分支的
后续研究不在本 response 中伪报为已运行。
