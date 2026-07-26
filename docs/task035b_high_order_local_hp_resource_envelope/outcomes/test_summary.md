# Task035b 测试总结

## 环境

```text
qualified activation = 1
python = /home/Projects/MyFEniCS/.venv/bin/python
Python = 3.12.3
PETSc.ScalarType = numpy.complex128
PETSc.IntType = numpy.int32
formal PDE MPI = 8
ordinary default changed = false
```

所有命令均在同一 WSL Ubuntu shell 中执行：

```bash
cd /home/Projects/MyFEniCS
source scripts/activate_myfenics_wsl.sh
```

## Review V3 选择性合并后 H0/H1-A 最终验证

```text
selective merge master =
1fb144d3ca50208c22b5f0733e140bfac8d9c47c
numerical PDE source =
148729c28c3f9aefec8e5646cc644c5c4e2332da
metadata delivery head =
documentation-only successor reported in final Git handoff
```

| layer | command scope | result |
|---|---|---|
| selective-merge pre-master full repository | M0–M4 integrated tree | **`570 passed, 28 skipped`** |
| H0/H1-A focused serial | Task032/033 Hybrid、watchdogs、public backend、static condensation、compact record、registry | **`124 passed in 261.92 s`** |
| H0 static-condensation MPI8 | `test_179`，8 ranks | each rank **`5 passed in 4.61–4.62 s`** |
| evidence/registry initial contract | H1-A record、registry、public backend | **`27 passed in 2.84 s`** |
| docs/Case095 contract | benchmark/docs/retrospective/Case095/registry/H1-A | **`34 passed in 1.07 s`** |
| full repository，first | final numerical + draft metadata | `581 passed, 28 skipped, 1 failed in 452.37 s`；Task034 numerical-blob checker 未分类两个 H0 successor |
| governance fix targeted | Task034 blob checker + H1-A + registry | **`7 passed in 0.69 s`** |
| final relevant regression | Task034 hardening + static Hybrid + H1-A + registry | **`24 passed in 4.40 s`** |
| full repository，final | qualified complex ABI；610 collected | **`582 passed, 28 skipped in 452.93 s`** |
| changed-Python Ruff | checker、hardening test、H1-A record test | pass |
| compileall | `src`、`benchmarks` | pass |
| tracked-tree JSON parse | artifacts excluded；tracked/project JSON | 892 files pass |
| `git diff --check` / links / worktree | post-writeback rerun | reported in final Git handoff |

第一次 full repository 的唯一失败不是数值结果失败。H0 合法改变了
`src/coupling/hybrid_internal_modes.py` 和
`src/solvers/hybrid_local_dtn.py`，并已在 source
`148729c28c3f9aefec8e5646cc644c5c4e2332da` 上完成 p2/h5 MPI8
standard/static Full3D、M120 和 M160 anchors；旧 Task034 checker
尚未给两条路径追加 “numerical kernel intentionally changed and requires
PDE rerun” 分类。修复只更新 fail-closed classification 和测试期望，没有
修改数值代码或 PDE record。第二次 full repository 全部通过。

H1-A 的 PDE numerical Gate 仍真实失败：static Full3D ↔ static Hybrid
只有 3/12 power + 2/12 amplitude；测试通过不改变其
`controlled_negative` 状态。

## Review V2 最终验证

```text
final tested source/evidence head =
56ed6cdb44e90a820274092ac6661c1e6a95f934
metadata delivery head =
documentation-only successor reported in final Git handoff
```

| layer | command scope | result |
|---|---|---|
| ABI preflight | qualified activation、Python、PETSc identity | pass；Python `3.12.3`、PETSc `complex128/int32` |
| Task035b focused serial | DtN modes、structured axis、全部 `test_*task035b*.py` | **`491 passed, 28 skipped in 507.27 s`** at `b2545ba`；final full pytest 再覆盖 |
| Task035b MPI2，final source | selective trace、DtN、Schur、recovery、partition、matrix-free | each rank **`95 passed, 24 skipped in 151.72/151.64 s`** |
| Task035b MPI8，final source | fixed rectangular DtN end-to-end smoke | each rank **`1 passed in 1.94–2.01 s`** |
| Task034/035 regression，final | Case093、Phase A–D、tetra、DWR/R5、Review V5/V6 | **`245 passed, 3 skipped in 67.82 s`** at `1d8b190`；final full pytest 再覆盖 |
| full repository，final tested HEAD | qualified complex ABI、1179 collected | **`1130 passed, 49 skipped in 884.08 s`** |
| changed-Python Ruff | Review V2 commit `d547e9d7` 到 final tested HEAD 的 95 个 Python files | pass |
| compileall | `src`、`benchmarks`、root `conftest.py` | pass |
| JSON/candidate audit | tracked JSON、candidate identity、record hashes | 992 JSON parse；68/68 unique rows；63 hash-bound records pass |
| documentation/evidence | contracts、record tests、response links | 48 tests pass；60 evidence paths pass；capability-v4 absent |
| `git diff --check` | final tested HEAD | pass |
| worktree | before metadata-only writeback | clean |

全仓 Ruff 仍报告 15 个 inherited findings，位于本轮未修改的
`src/postprocessing/diffraction_3d.py`、`full3d_reference.py`、
`hybrid_field_reconstruction.py`、`solve_maxwell_3d_common_old.py` 和
`run_3d_memory_profile.py`。changed-Python scoped Ruff 全部通过；本轮不把
无关数值重构混入 Task035b。

### Review V2 验证失败与修复链

| attempt | observed result | preserved root cause / action |
|---|---|---|
| focused combined，first | `489 passed, 28 skipped, 2 errors in 498.46 s` | `test_171` cross-module fixture 在组合收集时未注册 |
| focused combined，second | `490 passed, 28 skipped, 1 failed in 509.86 s` | 直接导入 fixture 改变历史 capability-v2 绑定的 test hash；撤回该做法 |
| focused combined，final | `491 passed, 28 skipped in 507.27 s` | root-level shared plugin registration；历史 `test_171` hash 恢复 |
| Task034/035，first | `243 passed, 3 skipped, 2 failed in 68.61 s` | current `mesh_builder_3d.py` successor 未绑定；不改冻结 manifest，只追加 Review V2 successor |
| Task034/035，final | `245 passed, 3 skipped in 67.82 s` | governance binding pass |
| full repository，first | collection error；0 tests executed | `pytest_plugins` 位于 `src/test/` 下的 non-top-level conftest |
| full repository，final | `1130 passed, 49 skipped in 884.08 s` | plugin registration moved to repository-root `conftest.py` |

上述失败属于测试收集、历史哈希和 governance 证据，不是 PDE accuracy
failure；原始输出和修复语义均保留。最终收口没有重跑 heavy PDE，没有修改
ordinary default，也没有 merge `master`。

## Review V1 最终验证

```text
final tested source/evidence head =
aa87534158bc84be7362d14e55ad56e7286a5e2a
```

| layer | command scope | result |
|---|---|---|
| ABI preflight | qualified activation、Python、PETSc/SLEPc/DOLFINx/MPI4Py identity | pass；Python `3.12.3`、PETSc `complex128/int32` |
| Task035b focused serial | DtN modes、structured axis、全部 `test_*task035b*.py` | **`216 passed, 10 skipped in 414.24 s`** |
| Task035b MPI2 | condensation、collective fail-fast、regionwise/fixed-trace、periodic identity | each rank **`13 passed in 668.12/668.16 s`** |
| Task035b MPI8 smoke | fixed rectangular DtN end-to-end | each rank **`1 passed in 5.03 s`** |
| Task034/035 regression，首次 | stacked baseline | `243 passed, 3 skipped, 2 failed in 68.12 s`；发现 geometry successor binding 过期 |
| successor-binding targeted | Task035 Phase A hermetic manifest | **`9 passed in 0.03 s`** |
| Task034/035 regression，final | Case093、Phase A–D、tetra、DWR/R5、Review V5/V6 | **`245 passed, 3 skipped in 66.28 s`** |
| full repository，final tested HEAD | qualified complex ABI | **`845 passed, 31 skipped in 778.93 s`** |

首次 Task034/035 regression 的两个失败都为
`identity_files[3]:tracked_hash_mismatch`。Task035 冻结 manifest 未改写；
Task035b successor record 改为绑定 directional/R5 profile 后的当前
`mesh_builder_3d.py` SHA256
`8e248eed4d617400e797cccc9f4ef1379b86548a89ba90429d46a3705270e303`，
并增加 h13 与 R5-slab authority。该 governance 修复提交为
`aa87534158bc84be7362d14e55ad56e7286a5e2a`，不改变数值算法或已有 PDE
结果。

## Review V1 最终 Gate

| check | result |
|---|---|
| qualified complex full repository pytest | `845 passed, 31 skipped` |
| Review V1 以来 changed-Python scoped Ruff | pass |
| full repository Ruff | 15 inherited findings in five files untouched by Task035b |
| compileall `src benchmarks` | pass |
| all tracked JSON parse | 970 files pass |
| all_candidates JSON/CSV identity | `58/58 rows, unique IDs, same order` |
| direct candidate-record SHA audit | 44 records pass |
| response local evidence links | 26 links pass |
| final documentation contract | 28 tests pass |
| final modified-Markdown link/table audit | pass |
| `git diff --check` | pass |
| tested-HEAD worktree | clean before metadata-only writeback |
| ordinary default / master | unchanged / not merged |

第一次 scoped Ruff 调用把 `-z` 放在 pathspec 后，导致 Ruff 将换行文件列表
误读为一个路径并报命令级 `E902`；正确的 NUL-delimited 命令随后通过。该错误
不是源码 lint finding。全仓 Ruff 的 15 条 inherited findings 位于
`src/postprocessing/diffraction_3d.py`、`full3d_reference.py`、
`hybrid_field_reconstruction.py`、`solve_maxwell_3d_common_old.py` 和
`run_3d_memory_profile.py`。为避免把无关数值重构混入 Task035b，本轮没有
自动修复。

最终 `test_summary.md` 与 `response_v2.md` 写回只包含测试/交付 metadata；
按仓库测试金字塔，无需重复 full pytest 或 heavy PDE。写回后的文档合同、
链接/表格、JSON parse 与 `git diff --check` 仍需重新执行并在交付时报告。

MPI2 命令只验证 partition/collective identity，不替代 formal MPI8 resource
authority。正式 PDE records 均来自 MPI8；本轮收口没有重复 heavy PDE。

## Review V1 前历史测试（保留）

| layer | command scope | result |
|---|---|---|
| Task035b focused serial | documentation、high-order topology、R5/watchdog、classifier、resource audit、cell/assembly condensation、regionwise-p、same-error | `100 passed, 7 skipped in 371.69 s` |
| Task035b MPI2 | high-order Floquet/resource audit、projection snapshot、collective invalid-input、condensation MPI identity | each rank `17 passed in 67.63 s` |
| Task034/035 regression | Case093、MPI/reference、Phase A–D、periodic tetra、DWR/R5、adaptive/uniform controls、Review V5 records | `173 passed, 3 skipped in 32.14 s` |
| full repository，首次 audit | qualified complex ABI | `679 passed, 28 skipped, 1 failed`；发现 formal runner 隐藏 untracked path |
| provenance fix targeted | Task034 hardening + Task035b same-error | `20 passed in 2.02 s`；Ruff pass |
| full repository，当时 final source | qualified complex ABI | **`680 passed, 28 skipped in 679.89 s`** |

## Review V1 前历史 Gate（保留）

| check | result |
|---|---|
| qualified complex full repository pytest | `680 passed, 28 skipped` |
| Task035b scoped Ruff | pass |
| full repository Ruff | 15 inherited findings in files untouched by Task035b |
| compileall `src benchmarks` | pass |
| all tracked JSON parse | 945 files pass |
| all_candidates JSON/CSV identity | `42/42 rows, unique IDs, same order` |
| referenced candidate paths | pass |
| documentation/hardening rerun | `27 passed` |
| Task035b Markdown basic table Gate | 14 files pass |
| `git diff --check` | pass |
| complete `git status` | historical pending final commit |

首次 full pytest 暴露
`benchmarks/task035b_same_error.py` 使用
`git status --untracked-files=no`，会漏掉所有 untracked path。现已改为
`--untracked-files=all`，preflight 和 post-run stability audit 都要求完整
工作树干净；这不改变数值算法或已有 PDE evidence。

这些历史计数绑定早期 HEAD，不是 Review V1 最终计数；上方最终验证取代其
当前性，但保留原测试与失败修复证据。

## 已验证的关键负面语义

- historical `formal_not_pass` records 未删除；
- N62 保持 `controlled_negative_non_exact_sequence_space`；
- h15 两个资源候选保持 diffraction-channel controlled negative；
- classifier v3 保持 `production_qualified=false`；
- Hybrid、M funnel 和 0.7 nm PDE 保持 `stopped_by_gate/not_run`；
- 不规则几何保持 `out_of_scope_by_user/not_run/not_a_completion_gate`。
