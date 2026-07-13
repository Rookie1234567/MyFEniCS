# 本轮改动文件

## Response V4

| 范围 | 文件与作用 |
|---|---|
| tracked-source Gate | `benchmarks/check_benchmarks.py`：对 5 份 lightweight canonical record 强制 `tracked_source_dirty=false` |
| runner provenance | Case002/003 `run.sh`：删除占位 digest，强制显式 `IMAGE_DIGEST` |
| contract regression | `src/test/test_25_benchmark_contract.py`：保护两个 runner 的 required-variable guard |
| 用户文档 | Case002/003 README 与两篇 Quick Start：命令同步加入真实 digest 参数 |
| 审查闭环 | `response_v4.md` 与 outcomes/index/status 更新 |

未修改 Task28 `task.md` 或任何 `review_report*.md`，未改 canonical JSON，未跟踪 `papers/` 或 Task23 raw runs。

## Response V3

| 范围 | 主要文件与作用 |
|---|---|
| 2D canonical harness | `benchmarks/run_2d_canonical.py`、Case002/003 records；完整 explicit/auxiliary 与 TM/TE lossy evidence |
| 2D solver stats/tests | `solve_*` matrix rows/nnz、solution observer、`test_20` lossless/lossy power regression |
| target config/presets | `config_3d::target_stage4_config`、17 preset metadata、demo/target 拆名、verbose resource identity |
| benchmark contract | 13 case 的 config/fixture、expected、run/test、SHA references；checker 143 Gates |
| Quick Start | 15 篇核心教程扩展为 16 节可跟随文档 |
| Walkthrough | 11 篇核心源码级深化；修复字段、PC 顺序、inverse、H=I 限制 |
| Theory | 统一符号表、2D/3D 功率常数、代码锚点和弱式排版 |
| Contract tests | `test_26` 增为 11 个结构/深度/record/技术准确性测试；`test_27` 保护 target identity |
| Task outcomes | `response_v3.md`、summary、metrics、parameters、run log、Gate、merge/decision 文档 |

V3 没有修改 `task.md` 或任何 `review_report*.md`，没有重跑 h2 direct/iterative，也没有跟踪用户 `papers/`、Task23 raw runs 或重型 artifacts。

## Response V2 源码

| 文件 | 作用 |
|---|---|
| `src/main.py` | 15 个安全命名 preset、Stage1 默认、CLI 列表与派发 |
| `src/runners/run_cases.py` | 2D complex refractive index parser |
| `src/common/config_3d.py` | 3D direct profile 公共配置 |
| `src/runners/run_3d_cases.py` | direct profile CLI 与 output 传递 |
| `src/solvers/common_3d_solve.py` | MUMPS default/OOC/BLR PETSc options |
| `src/solvers/stage4_runtime.py` | canonical physical model metadata |
| `src/solvers/solve_port_maxwell.py` | 有耗半空间传播模判定 |
| `src/postprocessing/power_metrics.py` | 实际端口面 modal power 与 complex beta 支持 |

## Benchmark 与 metadata

| 路径 | 作用 |
|---|---|
| `benchmarks/check_benchmarks.py` | benchmark ID、provenance、qualification、KSP、coarse、物理模型 Gate |
| `benchmarks/configs/workstation_p2.json` | canonical artifact root 和冻结物理模型 |
| `benchmarks/environment.json` | observed tag、digest、digest-pinned reference |
| `benchmarks/records/*.json` | ID、真实来源、canonical rerun、resolved config、physical model |
| `benchmarks/run_workstation_iterative.py` | 在新 record 中写入冻结物理模型 |
| `benchmarks/cases/` | 13 个独立功能 benchmark 目录 |
| `benchmarks/benchmark_summary.csv` | checker 生成的当前汇总 |
| `benchmarks/records/benchmark_gate_report.json` | 87/87 自动 Gate 报告 |

## 测试

| 文件 | 新增/修改覆盖 |
|---|---|
| `src/test/test_13_3d_stage_entrypoints.py` | 安全 Stage1 默认和显式 Stage4 preset |
| `src/test/test_18_3d_direct_solver_profile_cleanup.py` | BLR direct profile |
| `src/test/test_20_2d_lossy_port_modes.py` | 有耗传播模、cutoff、阶次和实际平面功率 |
| `src/test/test_25_benchmark_contract.py` | canonical artifact root 与 benchmark contract |
| `src/test/test_26_documentation_contract.py` | 文档索引、链接、13 cases/22 fields、状态 |
| `src/test/test_27_main_preset_contract.py` | 15 preset 唯一性和真实 parser acceptance |

## Quick Start

新增 `notes/quick_start/README.md` 及 16 篇编号教程：`00`-`02`、`10`-`13`、`20`-`23`、`30`-`32`、`40`、`50`。8 个旧指南保留，并增加 canonical 迁移说明。

## Code Walkthrough

`notes/reference/code_walkthrough.md` 改为总索引；新增目录 `notes/reference/code_walkthrough/`，其中 15 篇覆盖仓库架构、runner、2D、3D、DtN/RTA、direct、condensation、physical-slab PC、runtime、输出和测试。

## Theory

新增：

- `notes/theory/README.md`
- `maxwell_strong_weak_and_fem.md`
- `floquet_periodicity.md`
- `pml_robin_and_open_boundaries.md`
- `dtn_modal_ports_and_condensation.md`
- `official_and_diagnostic_rta_methods.md`
- `3d_stages_and_validation_ladder.md`
- `direct_solvers_and_factorization.md`
- `iterative_solver_and_preconditioner.md`
- `research_routes_and_negative_results.md`

## 总览与 Task28 outcomes

更新 `docs/README.md`、`docs/quick_start.md`、`docs/architecture_overview.md`、`docs/solver_guide.md`、`docs/benchmark.md`、`docs/capability_matrix.md`、`docs/development_progress.md` 和 `notes/reference/current_version_boundaries.md`。

新增 `response_v2.md`，并同步 summary、documentation audit、test summary、metrics、run log、Gate、merge recommendation 与 next decision。

## 明确保留不变

- 未修改 `task.md`、`review_report_v1.md`、`review_report_v2.md`。
- 未重跑 h=2 direct 或 iterative。
- 未跟踪 `results/`、`benchmarks/artifacts/` 下的大型 mesh、field、cache 或 raw run。
- 未合并 `master`，未启动 Task029。
