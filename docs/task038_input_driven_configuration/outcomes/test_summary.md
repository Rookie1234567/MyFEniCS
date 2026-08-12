# Task38 测试与 Gate 摘要

所有阶段均绑定各自完整 source SHA；纯测试使用 qualified activation，正式数值结果另见 [`summary.md`](summary.md) 与五份 compact JSON。`pass` 只表示对应 Gate 实际运行并通过，`not_run` 不表示隐含通过。

## 阶段矩阵

| 阶段 | source SHA | 测试/Gate | 结果 |
|---|---|---|---|
| T0 | handoff baseline `b81ad33b97a6b33accd81eb460a31592f6b55b47`；audit/doc source `d587792a748ea283d49aa51cc84f7163bd435ac3` | 文档/静态审计、dirty/index/ref Gate | pass；未跑 PDE |
| T1 | `1c7224371e5288b6b629498b820571bb99a92ae4` | `test_260`；TOML parse、schema/README key-unit-applicability、Ruff、compileall、diff-check | pass；focused 73 passed |
| T2 | `13b605b5f846ebe6b339e11bb71caaa5bc472963` | `test_260` + `test_261`；hash、immutability、strict validation、resolved writer、Ruff、compileall、diff-check | pass；focused 40 passed |
| T3 | `60296f6e1c53fcb3b7646d5c46ab9e97207d380c` | `test_260`–`263`；CLI/plan/worker/launcher contract；MPI1/2/4 contract probe | pass；serial focused 73 passed；无 PDE |
| T4 | `f4f2619aaef234fc12fa4db7e6a6075b383b3205` | T2–T4 focused、旧 direct entry/config contract、Ruff、format、compileall、diff-check | pass；随后 MPI1 old/new formal contract pass |
| T5 | `535c285e8d565b6c79e99cad9a2c899a5ff1658a` | T2–T5 focused、legacy parser/contract、Ruff、format、compileall、diff-check | pass；formal MPI4 task contract pass；exact NNZ diagnostic preserved |
| T6 | `870a3f9ff1097256ab6ef4b8f50d83a05a010473` | T2–T6 focused、Task37c parser/profile contracts、Ruff、format、compileall、diff-check | pass；唯一正式 MPI8 second attempt pass；attempt1 adapter contract failure preserved |
| T7 | `f86a7e42dc2c44d36c8e5ab6dfa1d9bb8ef8ed42` | `test_260`–`267`、`test_13/16/26/27/178` 及相关 pure tests；Ruff/format/compileall、links、JSON、benchmark check | pass；T7/T9 focused 295 passed、2 skipped；4 轻量 PDE 对照通过 |
| T8 | `7f57f7a7dab45c7c8cae67bf0f5271db110aa339` | main alias、benchmark caller、current-guide contracts | pass；无新 PDE/MPI |
| T9 | `de2e1880fa90a442996ada58ea321c774752a5ca` | `test_13/16/26/27/178/260/261/267`、文档/benchmark contracts、Ruff/定向 format/compileall、`check_benchmarks --no-write` | pass；295 passed、2 skipped；302/302 benchmark check；T10 扩大 format 审计见下 |
| T10 文档前 Gate | `de2e1880fa90a442996ada58ea321c774752a5ca` | qualified `test_26 + test_260`、Markdown relative links、5 JSON parse、diff-check | pass；17 passed，11 Markdown files、5 JSON files |
| T10 full Gate（source-branch inherited） | `de2e1880fa90a442996ada58ea321c774752a5ca` | ABI/source preflight 后精确 `python -m pytest -q`，无 deselect/并行 | inherited evidence；1119 passed、48 skipped、0 failed，1514.73s，不是当前 integration 结论 |
| T10 integration full attempt | `04bf4ea36d2936e0a9c1f258052b999301b9ac42` | 同一 qualified shell 的精确 `python -m pytest -q` | 用户运行中授权 controlled stop；约 243s、最后 `[12%]`，未形成最终计数 |

### T10 final docs-only static Gate

47 个 focused tests、Markdown/link contract、5 个 compact JSON parse、Ruff lint、compileall、`benchmarks/check_benchmarks.py --no-write`（302/302）和 `git diff --check` 均通过。Ruff format 的精确裁决为：base..de2e 的 A/C/M Python 集合共 30 个，其中 27 个通过；`benchmarks/run_task032_phase6_augmented.py`、`src/common/config_3d.py`、`src/postprocessing/diffraction_3d.py` 在 base 与 current 均不合格，临时 formatter 输出的 AST 与源码等价。本轮不为清理继承债制造大范围格式噪声；三项归类为 **accepted inherited formatting qualification**，不是 format pass。全目录 192 项继续只作 baseline diagnostic。

## 证据索引

| record | 关键结论 |
|---|---|
| [`t4_full3d_direct_mpi1_equivalence_v1.json`](records/t4_full3d_direct_mpi1_equivalence_v1.json) | Full3D direct MPI1；cfg 除 case_name 相同，canonical not_run_by_capability |
| [`t5_hybrid_direct_exact_nnz_diagnostic_v1.json`](records/t5_hybrid_direct_exact_nnz_diagnostic_v1.json) | exact NNZ controlled diagnostic failure，未改写为 pass |
| [`t5_hybrid_direct_mpi4_equivalence_v1.json`](records/t5_hybrid_direct_mpi4_equivalence_v1.json) | formal task contract pass + NNZ diagnostic |
| [`t6_hybrid_iterative_mpi8_equivalence_v1.json`](records/t6_hybrid_iterative_mpi8_equivalence_v1.json) | MPI8 pass，attempt1 adapter source-after error preserved |
| [`t7_preset_migration_equivalence_v1.json`](records/t7_preset_migration_equivalence_v1.json) | 11 项静态迁移、4 次 old/new 轻量 PDE |

## T10 三阶段 full/环境验证记录

| 阶段 | 命令与环境 | 结果 | 判定 |
|---|---|---|---|
| attempt 1 full | `python -m pytest -q`；parent `de2e1880...`；隔离 worktree 无 `.venv` | 1118 passed、48 skipped、1 failed，1352.60s，exit1 | diagnostic failure，保留，不改代码 |
| targeted | 仅 `test_73_task034_hardening.py::Task034HardeningTests::test_dolfinx_mpc_probe_requires_project_complex_abi`；临时 `.venv` symlink；同一 parent | 1 passed，0.98s，exit0；probe 9/9 true | 环境 identity 验证，不是代码修复 |
| source-branch final full | `python -m pytest -q`；同一 `de2e1880...`，仅纠正 `.venv` identity | 1119 passed、48 skipped、0 failed，1514.73s，exit0 | inherited source evidence，不是当前 integration 结果 |
| current integration attempt | `python -m pytest -q`；HEAD `04bf4ea3...` | 用户授权 controlled stop，约 243s，最后 `[12%]`；SIGINT 后 wrapper exit 1；日志 SHA256 `d55e20c83f5171207b8462d1a89c4a6ebfb4f8c7a630d9cd94a186209c40cfc5` | `user-authorized skipped/controlled stop`；不计 pass，不归因代码 failure |

两次 full 的 code/config parent 相同；第二次只纠正 worktree 到 canonical qualified venv 的 identity 接线。临时 symlink/excludes 已清理，首轮 failure excerpt 仍完整保留如下。

## 首轮 full pytest 原始 failure excerpt

执行命令：`python -m pytest -q`；returncode=`1`；耗时=`1352.60s (0:22:32)`。首轮 qualified preflight 字段为：`_MYFENICS_WSL_QUALIFIED_ACTIVATION=1`、`sys.executable=/home/Projects/MyFEniCS/.venv/bin/python`、`src.__file__=/tmp/myfenics-task38-input-driven-configuration-20260812/src/__init__.py`、`PETSc.ScalarType=<class 'numpy.complex128'>`、`PETSc.IntType=<class 'numpy.int32'>`。

失败 nodeid：`src/test/test_73_task034_hardening.py::Task034HardeningTests::test_dolfinx_mpc_probe_requires_project_complex_abi`。原始 assertion/probe excerpt：

```text
self.assertTrue(probe["pass"], probe)
AssertionError: False is not true
{'pass': False,
 'module_path': '/home/Projects/MyFEniCS/.venv/lib/python3.12/site-packages/dolfinx_mpc/__init__.py',
 'extension_path': '/home/Projects/MyFEniCS/.venv/lib/python3.12/site-packages/dolfinx_mpc/cpp.cpython-312-x86_64-linux-gnu.so',
 'checks': {'python_module_from_project_venv': False,
            'extension_from_project_venv': False,
            'project_complex_mpc_library_loaded': False,
            'dolfinx_complex_loaded': True,
            'petsc_complex_loaded': True,
            'no_dolfinx_real_loaded': True,
            'no_petsc_real_loaded': True,
            'ldd_succeeded': True}}
1 failed, 1118 passed, 48 skipped in 1352.60s (0:22:32)
```

pytest session没有单独输出 stderr block；上述为工具捕获的 combined stdout/stderr failure excerpt，未另行猜测。测试代码配置/parent 仍是 Task38 `de2e1880fa90a442996ada58ea321c774752a5ca`，没有代码、测试、default 或 ABI 配置修改。首轮按原 T10 合同停止；随后用户明确授权，仅纠正隔离 worktree 的 venv identity 接线后执行 targeted 与 final full；始终未删除测试、放宽阈值或修改代码。

MPI1 结项边界：Task §17.4 的 MPI1 条件由 inherited accepted MPI1 record 满足（record SHA `a38d3c280cb655481f63e79baf658c5353a2e86823e46fcefb54a148b2baec5f`，source `f2d7719...`，1472 iterations、1751.3203125 MiB、1903.92164 s）；当前 Task38 MPI1 dat 只 validate/dry-run，不是 current same-SHA formal comparator，也未冒充本轮重跑。Task38 fresh formal 是 MPI8。
