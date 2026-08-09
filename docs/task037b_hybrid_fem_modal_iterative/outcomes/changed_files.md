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
| H3 | 已通过 exact block-LDU formal 与 offline 12+12 |
| H4 | 已通过 exact Sₘ；G-only 为 bounded diagnostic complete |
| H5 | 下一阶段：approximate local inverse |
| H6-H10 | 按顺序未开始 |
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

## H2a-H4 后续准确提交链

| SHA | subject | 角色 |
|---|---|---|
| `41f692d2a7a8fce81ac49859c0f52cbcfda542e6` | `feat(task037b): add assembled Hybrid block action oracle` | H2a assembled-block MatPython action 与 focused oracle |
| `90fd03f5d39c3716703378e98b95081f70113568` | `docs(task037b): record H2a block action identity` | H2a evidence checkpoint |
| `8b283f033e48e3ebee85f741c1a89a83315a6c6f` | `feat(task037b): add matrix-free Hybrid endcap action` | H2b local-Schur/DtN action-only carrier |
| `384f164fd08587d3d8fc6bdfc8893cc37feb0df9` | `docs(task037b): record H2b endcap action identity` | H2b evidence checkpoint |
| `cffcc825a9fa7499b12f4fa5b106e2e7c1006572` | `feat(task037b): add exact block-LDU iterative oracle` | H3 exact block-LDU core 与 focused test |
| `e187275cd3d194dcedb9453d36e52bb035ad34dc` | `feat(task037b): wire H3 exact block-LDU authority` | H3 frozen runner/watchdog wiring与 formal source |
| `98046b7297b5de23d121b60898afe9e9007abc6e` | `feat(task037b): add H4 modal-block diagnostic` | H4 exact Sₘ + bounded G-only diagnostic、operator/lifecycle Gate |

上述 H3/H4 direct-factor oracle 只用于受控证据，不改变 ordinary defaults，也不等同于最终低内存候选。

## H5 local inverse qualification

| SHA | subject | 文件与职责 |
|---|---|---|
| `1990cd8ad287668774025e9789675ef53d6edd5e` | `feat(task037b): add local iterative inverse` | `src/solvers/physical_slab_two_level.py`：coordinate-axis 与 payload telemetry；`src/solvers/hybrid_local_iterative_inverse.py`：partition ASM、shifted ILU(0)、right FGMRES、true residual 与生命周期；`src/test/test_232_task037_owner_local_slab_assembler.py`、`src/test/test_233_task037_owner_local_slab_smoother.py`、`src/test/test_237_task037b_hybrid_local_iterative_inverse.py`：Stage A focused tests |
| `216437c6f13b3a3bf46e74451f63779189453c6f` | `feat(task037b): wire H5 local inverse qualification` | `benchmarks/run_task032_phase6_augmented.py`：H5 frozen mode/RHS、H5a/H5b early qualification path；`benchmarks/run_task033_memory_watchdog.py`：H5 parser、launch、terminal drain、阶段内存摘要与 no-swap semantics；`src/test/test_181_task035c_p6_h10_runner_gates.py`、`src/test/test_59_task033_memory_watchdog_contract.py`、`src/test/test_238_task037b_h5_fixture_helpers.py`：H5 contracts |

H5a exact reference 通过，H5b 冻结 local inverse family 为 `LOCAL_INVERSE_FAMILY_NEGATIVE`；H5c、H6-H10 按顺序未运行。上述代码保持 H5 explicit opt-in，ordinary defaults unchanged；没有把该 candidate、Hybrid-P 或低秩 direct Hybrid 提升为 production-qualified。H5 raw artifacts 为 ignored 文件，只由 docs 以路径和 SHA 引用。

## V1 R1–R5 research-only source chain

| SHA | subject | 角色与边界 |
|---|---|---|
| e2e57675867dcb3476441f27b33eb45a0d90b040 | feat(task037b): add V1 endcap action identity gate | R1 action decomposition、唯一 V1 entry；research-only |
| a9ee7067503879ce082145430169acc8aeb48b7b | feat(task037b): add V1 R2 F-only diagnostic | R2 six-slab F-only diagnostic；research-only |
| 31d30842f0bcf24edde2113217db7a6dfc1264c1 | feat(task037b): add V1 R3 whole-endcap baseline | R3 whole-endcap ILU(0) baseline；research-only |
| 53faebb14960f8ddbaf88f54f8ceae511ccd7764 | feat(task037b): qualify exact DtN Woodbury oracle | R4 exact F inverse Woodbury oracle；research-only |
| 2a2ef3d37514e4ab30d50209065af84c1dafd59b | feat(task037b): qualify DtN-aware whole-endcap inverse | R5 DtN-aware local inverse candidate与正式 negative evidence；research-only |

上述 source/runner/checker 路径均保持 ordinary defaults unchanged；R5 candidate、Hybrid-P 和
低秩 direct Hybrid 均不得 production-qualified。compact research record 位于
../../../benchmarks/cases/101_hybrid_iterative_block_solver/records/task037b_v1_r1_r5_research_closeout_v1.json。
未经新的 review 与用户授权，不整体 merge 到 master。

## 文件角色与选择性边界

| 分组 | 文件/范围 | 选择性边界 |
|---|---|---|
| research-only numerical/core | src/solvers/hybrid_local_dtn_action.py；src/solvers/hybrid_local_iterative_inverse.py；src/solvers/hybrid_local_dtn_woodbury.py | 仅保留已审 research evidence，不提升为 ordinary production |
| explicit-opt-in runner/watchdog | benchmarks/run_task032_phase6_augmented.py；benchmarks/run_task033_memory_watchdog.py | 仅用于显式 opt-in 的 V1 路径；ordinary defaults unchanged |
| tests/independent checker-contract | src/test/test_181_task035c_p6_h10_runner_gates.py；src/test/test_59_task033_memory_watchdog_contract.py；src/test/test_235_task037b_hybrid_local_dtn_action.py；src/test/test_237_task037b_hybrid_local_iterative_inverse.py；src/test/test_239_task037b_hybrid_local_dtn_woodbury.py；src/test/test_240_task037b_hybrid_local_dtn_woodbury_local_inverse.py | focused tests 与 independent checker contracts |
| compact evidence/docs | 本轮 exact 9 files：docs/development_progress.md；本 outcomes 目录下的 changed_files.md、local_endcap_inverse_matrix.md、resource_ledger.md、summary.md、test_summary.md；docs/task037b_hybrid_fem_modal_iterative/response_v2.md；benchmarks/cases/101_hybrid_iterative_block_solver/README.md；benchmarks/cases/101_hybrid_iterative_block_solver/records/task037b_v1_r1_r5_research_closeout_v1.json | 仅为可审 compact evidence，不纳入 heavy raw arrays |
| do-not-merge | ignored raw artifacts/heavy timeline；ordinary defaults；任何 production qualification | 保留研究证据，不整体合入 |

以上分组属于 research closeout；后续如需选择性合入，必须按依赖组重新 review，不能整体 merge Task37b。

## Review V2 单侧 block-PC screen source 与证据

| SHA | subject | 角色与边界 |
|---|---|---|
| a42938eb912c2d24acc15e64a668649dfafc7dbe | feat(task037b): add fixed one-apply R5 action | fixed Woodbury callback carrier；research-only，ordinary defaults unchanged |
| 25d5a211b8df5a59784bfa0e60a8324f890eeed8 | feat(task037b): add same-action block LDU | same-action modal Schur/block-LDU core；research-only，ordinary defaults unchanged |
| e75ce90256d53cc12c295eb0b2fbd5d4b4dc4343 | feat(task037b): add bounded block screen core | bounded outer screen core；research-only，ordinary defaults unchanged |
| 3baa695c0c8e1933d2c36923f8d4f96dffde8e82 | feat(task037b): add bounded block screen runner | frozen V2 flags/runner；research-only，ordinary defaults unchanged |
| 733a1cb0ee533639e29b3a5ce60becf6a29162ec | feat(task037b): add V2 block screen watchdog | V2 explicit parser/worker/watchdog 接线；首次 B 在 worker/PDE 前因 scoped Case090 evidence wiring 停止，不是数值 screen |
| 5b94060eae3a2ce02dd87e8a8c2075b635711346 | fix(task037b): exempt V2 scoped launch from Case090 evidence | 单行 scoped launch exemption；正式 V2-B/T 各只运行一次，source stable |

V2 使用已审的 fixed one-apply callback、action block-LDU 和 outer true-residual screen；
不调用 LocalInverse.solve，不创建 nested local FGMRES/KSP，不改 ordinary defaults。V2-B
与 V2-T 的 ignored raw solver record、summary、timeline、stages、stdout 只以路径和
SHA 保留在 compact evidence，不纳入 Git。

## Review V2 closeout 文件角色

本次 code-free closeout 的精确九文件为：

| 分组 | 文件 | 选择性边界 |
|---|---|---|
| compact evidence record | benchmarks/cases/101_hybrid_iterative_block_solver/records/task037b_v2_block_pc_screen_v1.json | hash-bound V2-B/T、完整 0–20 history、double not_run 和 official not_run；不是 production schema |
| outcomes | docs/task037b_hybrid_fem_modal_iterative/outcomes/one_sided_replacement.md；double_iterative_funnel.md；resource_ledger.md；summary.md；test_summary.md；changed_files.md | 追加式 V2 研究结项；保留既有 H5/R5 原文 |
| project progress | docs/development_progress.md | 记录 V2 单侧停止与 TOP_APPROXIMATE_SIDE_NEGATIVE |
| response | docs/task037b_hybrid_fem_modal_iterative/response_v3.md | 面向审阅的 V2 closeout；不替换 response_v1/v2 |

以上仅是 research closeout/选择性 review 材料。ignored raw artifacts、heavy timeline、
ordinary defaults、未资格化 production candidate 和整体 Task37b merge 均属于 do-not-merge；
任何后续算法家族都必须取得新的 review。

## Review V3 source and code-free evidence boundary

V3 formal source 为 `c7b6aa3ddaac4dbfb9f86aab8f59801330d63a16`，parent 为
`9e01280df6c241932242a75d70db27210ceed46e`；subject 为
`feat(task037b): add V3 double fixed-action screen`。它只把已审的 bounded screen 接线
扩展到一个无参数、显式 opt-in 的 double progressive screen；ordinary defaults、V2 flags、
V2 schema 和既有历史结果不变。

| 分组 | 文件/证据 | 选择性边界 |
|---|---|---|
| V3 research-only source | benchmarks/run_task032_phase6_augmented.py；benchmarks/run_task033_memory_watchdog.py；src/solvers/hybrid_fem_modal_block_ldu.py | V3 runner/watchdog/core；仅显式 V3 gate，ordinary defaults unchanged |
| V3 independent contracts | src/test/test_242_task037b_v2_block_screen_runner.py；src/test/test_59_task033_memory_watchdog_contract.py | focused progressive/checker tests；不声称 CI/full pytest |
| compact evidence | benchmarks/cases/101_hybrid_iterative_block_solver/records/task037b_v3_double_block_pc_screen_v1.json | hash-bound source、argv、17 checkpoints、Gate、资源与 official not_run |
| V3 closeout docs | docs/task037b_hybrid_fem_modal_iterative/outcomes/double_iterative_funnel.md；resource_ledger.md；test_summary.md；changed_files.md；summary.md；docs/development_progress.md；docs/task037b_hybrid_fem_modal_iterative/response_v4.md | 追加式 research closeout；保留 V2、response_v3 和旧负结果 |
| do-not-merge | ignored raw artifacts/heavy timeline；任何 full solve、field/R/T/A、production qualification、ordinary default change | 不整体 merge Task37b |

V3 没有触碰 `hybrid_local_dtn_woodbury.py` 或 `hybrid_local_iterative_inverse.py`，没有调用
LocalInverse.solve、nested local FGMRES/KSP 或 fallback。raw artifact 仍只以相对路径和
SHA256 绑定，heavy timeline 与 solver arrays 不进入 Git。

## Review V4 source checkpoint 与本次 code-free evidence

V4 source checkpoint 为 `eb1fc88483dd4d9cb5eabb071f8af0e87f91ba49`，parent 为
`d3b15af96d4719f04dcf006c6caf98d1a2503366`，subject 为
`feat(task037b): qualify frozen MPI8 full block solve`。该提交的 research-only scope 如下：

| 分组 | 文件/职责 | ordinary/default 边界 |
|---|---|---|
| V4 solver/core | `src/solvers/hybrid_fem_modal_block_ldu.py` | full-solve API、deferred modal release、snapshot；explicit opt-in |
| V4 runner | `benchmarks/run_task032_phase6_augmented.py` | frozen p6/h10/MPI8 full-solve route；ordinary defaults unchanged |
| V4 watchdog | `benchmarks/run_task033_memory_watchdog.py` | source/authority/resource/process-group route；ordinary defaults unchanged |
| V4 checker | `benchmarks/task037b_v4_full_qualification_checker.py` | offline read-only candidate/authority evidence checker |
| V4 focused test | `src/test/test_243_task037b_v4_full_qualification.py` | tiny serial/MPI action/lifecycle/recovery contracts |

上述 source 文件没有调用 `LocalInverse.solve`，没有 nested local FGMRES/KSP、direct fallback 或
ordinary default 变更。V4 这次 code-free closeout 只新增/更新下列八个 tracked 文件，raw
solver、timeline、stages、stdout 和 checker 仍保留在 ignored artifact 目录：

| 类别 | 文件 |
|---|---|
| compact record | `benchmarks/cases/101_hybrid_iterative_block_solver/records/task037b_v4_mpi8_full_qualification_v1.json` |
| response | `docs/task037b_hybrid_fem_modal_iterative/response_v5.md` |
| outcome | `docs/task037b_hybrid_fem_modal_iterative/outcomes/full_mpi8_qualification.md` |
| outcome updates | `outcomes/summary.md`、`outcomes/resource_ledger.md`、`outcomes/test_summary.md`、`outcomes/changed_files.md` |
| project progress | `docs/development_progress.md` |

本次 closeout 不修改 Python、测试、task/review、response_v1–v4 或 ordinary defaults，不重跑
pytest、Ruff、checker、MPI 或 PDE；只将已完成的唯一 formal evidence 写成 hash-bound compact
记录和可审阅文档。
