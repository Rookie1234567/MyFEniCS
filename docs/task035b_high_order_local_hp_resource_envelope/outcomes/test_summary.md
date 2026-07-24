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

## 已完成测试

| layer | command scope | result |
|---|---|---|
| Task035b focused serial | documentation、high-order topology、R5/watchdog、classifier、resource audit、cell/assembly condensation、regionwise-p、same-error | `100 passed, 7 skipped in 371.69 s` |
| Task035b MPI2 | high-order Floquet/resource audit、projection snapshot、collective invalid-input、condensation MPI identity | each rank `17 passed in 67.63 s` |
| Task034/035 regression | Case093、MPI/reference、Phase A–D、periodic tetra、DWR/R5、adaptive/uniform controls、Review V5 records | `173 passed, 3 skipped in 32.14 s` |
| full repository，首次 audit | qualified complex ABI | `679 passed, 28 skipped, 1 failed`；发现 formal runner 隐藏 untracked path |
| provenance fix targeted | Task034 hardening + Task035b same-error | `20 passed in 2.02 s`；Ruff pass |
| full repository，final source | qualified complex ABI | **`680 passed, 28 skipped in 679.89 s`** |

MPI2 命令只验证 partition/collective identity，不替代 formal MPI8 resource
authority。正式 PDE records 均来自 MPI8；本轮收口没有重复 heavy PDE。

## 最终 Gate

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
| complete `git status` | pending final commit |

首次 full pytest 暴露
`benchmarks/task035b_same_error.py` 使用
`git status --untracked-files=no`，会漏掉所有 untracked path。现已改为
`--untracked-files=all`，preflight 和 post-run stability audit 都要求完整
工作树干净；这不改变数值算法或已有 PDE evidence。

全仓 Ruff 的 15 条 inherited findings 位于本 Task 未修改的
`src/postprocessing/diffraction_3d.py`、`full3d_reference.py`、
`hybrid_field_reconstruction.py`、`solve_maxwell_3d_common_old.py` 和
`run_3d_memory_profile.py`。为避免把无关数值重构混入 Task035b，本轮没有
自动修复；从 Task035b 起全部 Python 变更文件的 scoped Ruff 通过。

## 已验证的关键负面语义

- historical `formal_not_pass` records 未删除；
- N62 保持 `controlled_negative_non_exact_sequence_space`；
- h15 两个资源候选保持 diffraction-channel controlled negative；
- classifier v3 保持 `production_qualified=false`；
- Hybrid、M funnel 和 0.7 nm PDE 保持 `stopped_by_gate/not_run`；
- 不规则几何保持 `out_of_scope_by_user/not_run/not_a_completion_gate`。
