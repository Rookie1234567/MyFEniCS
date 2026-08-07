# Task037b code changes and provenance

## 代码提交链

| SHA | subject | 范围 |
|---|---|---|
| 26e48e2767d200b6ec58b39d117c354afbdba30c | docs(task037b): adopt fenced-math documentation standard | H0 文档公式治理与最小合同 |
| c1173a7d8de81b8bc80e0fca5e3eb28a912dc1d3 | test(task037b): freeze inherited Hybrid iterative baseline | H0 继承测试基线 |
| 3f72ef3eb4f3002246802af30ef7bca6b0080888 | feat(task037b): qualify direct Hybrid H1 authority | H1 explicit opt-in telemetry、pinned reference opening 与 launch wiring |
| 2990f357f7dec23b1713bd0088bdc43c3ce6f5bc | fix(task037b): align near-degenerate grouping with partition audit | H1 near-degenerate grouping 与最终 partition row-norm audit 对齐；只改 mode classification 与其现有测试 |
| 8b283f033e48e3ebee85f741c1a89a83315a6c6f | feat(task037b): add matrix-free Hybrid endcap action | H2b local-Schur/DtN action carrier、Hybrid operator inventory 与 H2b focused tests |

H1-A 的六个实现/测试文件已包含在第三个提交中。首次 H1 formal 使用的 clean source SHA 是 3f72ef3eb4f3002246802af30ef7bca6b0080888；post-fix H1 formal 使用的 clean source SHA 是 2990f357f7dec23b1713bd0088bdc43c3ce6f5bc。本 docs-only checkpoint 不修改 tracked code。

## H1-A 六文件角色

下列六个文件属于 H1-A commit；本 docs-only 结项没有再次修改它们。

| 文件 | 角色 |
|---|---|
| benchmarks/run_task032_phase6_augmented.py | direct Hybrid augmented 求解入口、H1 rows/hash/RTA/recovery telemetry |
| benchmarks/run_task033_memory_watchdog.py | H1 scoped launch、worker wiring、资源 watchdog 与 summary forwarding |
| benchmarks/task035c_p6_h10_gates.py | pinned historical Full3D reference gate |
| src/test/test_181_task035c_p6_h10_runner_gates.py | H1 parser、worker、summary 与 pinned authority 合同 |
| src/test/test_53_task033_high_order_hybrid_components.py | owned-local PETSc Vec 与 modal hash 合同 |
| src/test/test_79_task034_native_full3d_reference.py | 外部绝对 reference/archive path 合同 |

## 边界

| 项目 | 结论 |
|---|---|
| ordinary defaults | unchanged |
| H1 flag | explicit opt-in，仅 task037b-h1-gate |
| H1 §9 post-fix contract | pass；12+12 frozen-reference 与 Full3D pairwise 均通过 |
| master | 未合并 |
| H2a | 已通过 assembled-block action identity |
| H2b | 已通过 Matrix-free local endcap exact action identity |
| H3-H10 | 未开始；下一阶段为 H3 |
| ignored raw artifacts | 不提交 |
| tracked docs | 只保存 hash-bound evidence 引用 |

## H2a assembled-block action checkpoint

| SHA | subject | 文件与职责 |
|---|---|---|
| `41f692d2a7a8fce81ac49859c0f52cbcfda542e6` | `feat(task037b): add assembled Hybrid block action oracle` | `src/solvers/hybrid_fem_modal_iterative.py`：MatPython assembled-block action；`src/test/test_234_task037b_hybrid_block_operator.py`：MPI1/2/4 direct oracle、probe、ownership、lifecycle tests |

H2a 代码 checkpoint 只包含上述两个 Python 文件；没有修改 ordinary defaults、direct public
API、H1 文件或 JSON。H2b Matrix-free local endcap exact action identity 见下节；H3 第一次
outer FGMRES / exact block-LDU iterative oracle 未开始；raw artifacts、iterative solve 和
resource evidence 仍未创建。

## H2b Matrix-free local endcap action checkpoint

| 项目 | 事实 |
|---|---|
| code/test commit | `8b283f033e48e3ebee85f741c1a89a83315a6c6f` |
| 测试基线 | `90fd03f5d39c3716703378e98b95081f70113568` 上的 exact worktree content |
| provenance | 测试内容未再改变，随后固定为上述 H2b commit；`90fd03f5...` 不是包含 H2b 代码的 source SHA |
| production | `src/solvers/hybrid_local_dtn_action.py`：local-Schur/DtN action-only carrier；`src/solvers/hybrid_fem_modal_iterative.py`：真实 inventory 接线 |
| tests | `src/test/test_234_task037b_hybrid_block_operator.py`：H2a inventory/action 回归；`src/test/test_235_task037b_hybrid_local_dtn_action.py`：H2b-L/G local/global action、ownership、pack/split、lifecycle |
| inventory | global A=false、bottom/top F=false、explicit external C/D=0/0、p6 direct factor count=0；Krylov auxiliary rows=0 |
| result boundary | H2b action identity pass；不是 solver convergence、资源资格化或 H3 完成证明 |
