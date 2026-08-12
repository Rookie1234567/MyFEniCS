# Repository readability cleanup 2026-08-12

## 范围与身份

这是从 Task38 closeout `7a756f3a3e934c9bff7059fbad63110f9f5eacd0` 开出的第一轮保守可读性清理分支：
`codex/20260812-repository-readability-cleanup`。本轮只删除已由当前调用图证明不可达的五个初始旧入口，并更新四份历史说明和导航；不宣称仓库已经没有其他 dead code。

这里不是创建两个 Task38，也不是另一个 repository/worktree：本地
`codex/20260812-task38-input-driven-configuration` 精确跟踪同名 origin 分支，closeout SHA 为
`7a756f3a3e934c9bff7059fbad63110f9f5eacd0`、状态为 `0/0`；本清理分支从该 SHA 独立审阅，且精确跟踪
`origin/codex/20260812-repository-readability-cleanup`。两者都位于同一个 canonical
`/home/Projects/MyFEniCS`；分支分名只是为了不污染已结项的 Task38。

canonical 与 Task38 closeout 在操作前均为 clean、`0/0`；Task38 的 `results/` 已保护到 canonical，`benchmarks/artifacts/` 已隔离到
`benchmarks/artifacts/_worktree_quarantine/task038_full_pytest_generated_20260812/`。其中隔离目录是 pytest 生成的非authority快照；canonical 原有同路径内容未覆盖。

## 删除项与替代入口

| 删除路径 | 静态证据 | 替代入口 |
|---|---|---|
| `run_demo.sh` | 初始提交旧 Docker wrapper；`src/`、`src/test/`、`scripts/`、`benchmarks/` 无 caller；指向退役包名与父目录 | `python scripts/run_case.py <one-case.dat>` |
| `run_demo_mpc.sh` | 同上；旧 `--constraint-backend both` facade | 独立 dat 的 `method.constraint_backend = "mpc_official"` |
| `run_demo_mpi.sh` | 同上；旧 `mpirun`/退役包名 wrapper | 由 dat 的 `execution.mpi_size` 与 launcher 管理 |
| `src/runners/run_grating_manual.py` | 初始提交硬编码 `SimulationConfig`；无当前代码 caller或动态注册 | 独立 dat 的 `method.constraint_backend = "manual"` |
| `src/runners/run_grating_mpc_official.py` | 初始提交硬编码 `SimulationConfig`；无当前代码 caller或动态注册 | 独立 dat 的 `method.constraint_backend = "mpc_official"` |

删除的是重复入口，不是删除 manual、`mpc_official` 或端口/Floquet solver能力。当前唯一普通入口是一个 `.dat`；完整键和示例见 [`input/README.md`](../input/README.md)。

## 明确保留

本轮保留 `src/runners/run_cases.py`、`src/runners/run_3d_cases.py`、`src/main.py` 的六个 research/history preset、Task37/37b/37c 数值核心与 authority、adaptivity/studies、benchmark replay、`Dockerfile.mpc`，以及其他未证明不可达的历史工具、research代码和records。

## Gate

本轮不运行 PDE、MPI 或 full pytest；Task38 closeout 已有 final full pytest `1119 passed/48 skipped`，本轮不重复该重型 Gate。

| 检查 | 实测结果 |
|---|---|
| ABI/source preflight | `qualified=1`；Python、源码和PETSc complex128/int32来自canonical |
| `pytest --collect-only -q` | `1167 tests collected`，exit 0 |
| focused入口/Task38 suite | 首次 `225 passed, 1 failed`；失败仅由ignored cache-only目录`benchmarks/cases/098_reference_blind_multilevel_hp_adaptivity`触发。删除该目录中2个`.pyc`（约84K缓存，实际72,697 bytes；无tracked evidence）后，最终 `226 passed`，exit 0 |
| public `validate-only` / `dry-run` | `input/examples/2d_euv_grating_direct.dat` 两命令均exit 0；dry-run无目录创建/solver启动 |
| `check_benchmarks.py --no-write` | `302/302 passed` |
| `compileall` | `python -m compileall -q src scripts benchmarks`，exit 0 |
| `git diff --check` | pass |
| deleted-entry caller audit | `src/`、`src/test/`、`scripts/`、`benchmarks/`无五个入口的当前引用或动态注册 |

本轮 focused 首次失败是可再生的ignored Python cache残留，随后只删除该精确目录并按原命令重跑；未修改测试、solver、配置、default或threshold。
