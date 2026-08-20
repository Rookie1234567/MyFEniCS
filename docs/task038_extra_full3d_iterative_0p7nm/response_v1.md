# Task038-extra response_v1

## 1. 本轮结论

Review V1 的 T5 hard Gate 已触发。本轮完成了一次 MPI1 formal authority；hard stop 后没有重跑 authority。本轮随后只做只读根因边界诊断和 compact evidence 收口，没有修改数值代码，也没有启动 MPI2、Candidate A/B/C、T6、T7–T9 或 0.7 nm PDE。

| stage | status |
|---|---|
| T1 | PASS |
| T2 | PASS |
| T3 | PASS |
| T4 | PASS |
| T5 | `BLOCKED_BY_LONG_TAIL_RESIDUAL_AUTHORITY` |
| T6 / T7–T9 / 0.7 nm | `not_run_by_gate` / `not_run` |

T5 MPI1 formal authority 的资源侧实测通过：process-tree peak RSS `981,893,120 B`，swap `0 B`，watchdog wall `34.103594134998275 s`。但 RHS bridge 的实际 relative coefficient L2 为 `10.934736136386151`，最大 packet absolute difference 为 `1.2846616424283923`；key/count/duplicate structure 通过。residual action/reference、repeat/action、MPI2 和 A/B/C 均为 `not_run_by_gate`。

## 2. 全批次身份、结果与 handoff

### 2.1 Git、批次和 ABI 身份

| identity | value |
|---|---|
| base master / merge-base | `438caf150439343ee7c4c58ad7e02a3da812a23c` |
| batch start / Review V1 authority | `80c3fa29d54813d0344a93ffa7768108ff15fa76` |
| T0 review-start commit | `90fdf43dbc4ed1140d4951679e76c4dd37cf1a0e` |
| branch | `codex/20260820-task38-extra-full3d-iterative-0p7nm` |
| formal source at T5 start | `e97db3680ee501350cc40dabe3b0b01d4c756651` |
| pre-evidence/formal source HEAD | `e97db3680ee501350cc40dabe3b0b01d4c756651` |
| final pushed handoff HEAD | 提交后在交付报告精确给出（文档无法自指自身 commit） |
| branch relation | ahead `14` / behind `0` relative to origin task branch |
| ABI | qualified WSL activation；repo `.venv` Python；PETSc `complex128` / `int32`；petsc4py、slepc4py、DOLFINx、Basix、mpi4py 同一 Linux ABI；线程限制为 1 |

### 2.2 各阶段 source/evidence 身份

| stage | formal/source SHA | evidence SHA / compact identity | result |
|---|---|---|---|
| T1 | `a18df1ac5e9c9f9c67245a4d33546925c4076aa1` | 同一 contract commit；无 formal compact aggregate | PASS，contract-only |
| T2 | `6d60bb5a9a59e88da98b027efeed8506d5dd7a82` | evidence commit `e4ea540078c4e86dfa0e5762d9dbf241a5c3a728`；aggregate `1b604df72dcaa20a7d23efc1a8dccf3e9564820bbdbf8ad54007f1c6869a7dcd` | PASS |
| T3 | `691ac261fd62258d356183cb3c0383307605b15e` | evidence commit `c44e6a19ee0955988bff3f6110d576cb4cc1fa09`；aggregate `f8fc4947c18d96120057dfefe5a286dc330ce0d3a30d3ff6f74b5d5e33aa6131` | PASS |
| T4 | `88e5cef8a007445270721b9076b0c33453f743f3` | evidence commit `a6a8ca7fea3f071e1769f58f38da3ff95f2577e3`；aggregate `c6f160facd0d843078788fd65c655aba3517d4f70017e3c003d58d8525ce5eb7` | PASS |
| T5 | `e97db3680ee501350cc40dabe3b0b01d4c756651` | record `ec91c5652580bcd6f922c58ee1741ae7b7063dedf9e531d24f701c5bdfa28dd1`；checker `ddafbabc9e5e120a09919b5db73ae644adccac8974f54368c9c42251deab8b8b`；watchdog `226dd35e661e4d00c05c438aab8f6f0cacdc74300e605bb4ab3f9689d0de1ece`；diagnostic `c4dad79358212d2440a9b66aee99861eb8170eb3ca03ae6f29d368aac2ef5237` | BLOCKED，evidence commit pending |

### 2.3 实际重构文件、依赖和未迁移对象

| lane | current-tree files and role |
|---|---|
| T1 input contract | `src/io/input_schema.py`、`src/io/input_validation.py`、`src/io/execution_plan.py`、`src/runners/task038_full3d_iterative.py`、`src/runners/task038_input_worker.py`；从 `.dat` 生成 resolved config 和 execution plan |
| T2 volume action | `src/solvers/fullspace_mpc_action.py`；owner-local finalized MPC/Floquet full-space matrix-free action |
| T3 dynamic DtN | `src/solvers/fullspace_dtn_action.py`；动态 mode inventory、显式 H normalization、固定 batch streaming、forward/recovery |
| T4 topology | `src/solvers/fullspace_slab_interface.py` 与通用 MPC action；两 slab owner-local topology、facet Robin action、R/P 和 phase-once audit |
| T5 authority bridge | `src/solvers/hcurl_canonical_vector.py`、`src/solvers/hcurl_canonical_vector_dolfinx.py` 的 dual canonical map，以及 `src/solvers/fullspace_physical_action.py` 的 current volume+DtN composite |
| evidence layer | `benchmarks/run_task038_full3d_t{2,3,4,5}.py` 与对应 `task038_full3d_t{2,3,4,5}_checker.py`；只编排 raw facts、canonical evidence 和 read-only checks |

共同依赖是当前 `src.io.load_and_resolve`、DOLFINx/PETSc/MPI、finalized MPC/Floquet 和 canonical packet utilities；没有把 numerical core 放入 benchmark checker。明确未迁移：旧 `hcurl_fullspace_dtn.py` 的 fixed-80/identity-H 假设、Task37 task-numbered runner、W8–W18/`hcurl_h2b_*`/`hcurl_m6b_*` PC、disk-backed Krylov/history、84 个 patch factors、fixed 75/390/530D range、Task039 Hybrid/QEP/Petrov/side-factor 路线，以及任何 global AIJ、Schur、dense interface matrix 或 slab factor。旧 W5 raw 只作 authority reference，不进入 production。

### 2.4 T2–T4 实测 Gate 摘要

| stage | numerical/identity facts | retained/work/resource facts |
|---|---|---|
| T2 | assembled/reference p2 `1.0623006934406839e-15`、p3 `3.571370033045663e-15`；p6/h10 MPI1/MPI2 `7.263059324300498e-17` / `7.120392279402028e-17`；physical source/action MPI identity `2.646028570711081e-16` / `1.1449579596647522e-13`；每案 12 repeat，最大差 `0.0` | h10→h5 retained exponent `0.9779306095631883`；retained global-max `6,151,104 B` → `38,290,752 B`；warm rank-max RSS span `0–8,192 B`；swap `0 B`；process-tree `not_measured_t2` |
| T3 | dynamic `80` modes = propagating `78` / near-cutoff `0` / evanescent `2`；manifest SHA `dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2`；batch size/count `8/10`；action `1.5267729283364925e-16`；recovery `8.148489733468128e-17`；repeat max `0.0`；MPI1/MPI2 source/action/reference/recovery canonical relative L2 `0.0` | retained numeric MPI1/MPI2 `2,875,480 / 1,447,312 B` rank-max；bounded batch work `256 B`；recovery output `1,280 B`；RSS warm span `61,440 / 45,056 B`；swap `0 B`；process-tree `not_measured_t3` |
| T4 | real two-slab/interface fixture；global/local facets `6/6`；owned trace rows p2/p3 `48/108`；R/P adjoint error `0.0`；nontrivial phase and finalized MPC once；Candidate A tangential Robin oracle max `1.1347e-15`；cross-MPI canonical max `7.1149e-15` | retained/work p2 MPI1/MPI2 `45,696/30,624 B` and `10,368 B`；p3 MPI1/MPI2 `127,296/85,968 B` and `27,648 B`；rank-max current RSS span `1,363,968–1,683,456 B`；swap `0 B`；process-tree `not_measured_t4` |

### 2.5 T5 五类 source × A/B/C

| source | Candidate A | Candidate B | Candidate C |
|---|---|---|---|
| physical RHS | `not_run_by_gate` | `not_run_by_gate` | `not_run_by_gate` |
| gradient-dominated residual | `not_run_by_gate` | `not_run_by_gate` | `not_run_by_gate` |
| curl-dominated residual | `not_run_by_gate` | `not_run_by_gate` | `not_run_by_gate` |
| checkerboard/high-frequency residual | `not_run_by_gate` | `not_run_by_gate` | `not_run_by_gate` |
| Task37-extra long-tail residual | `not_run_by_gate` | `not_run_by_gate` | `not_run_by_gate` |

这张表表示候选没有被数值比较判为失败；它们在 long-tail authority bridge 之前均未获准运行。已完成的 MPI1 bridge 事实是：old/current packet 各 `164592`，key/count/duplicate 结构通过，但 RHS relative `10.934736136386151`、最大 packet absolute difference `1.2846616424283923`，故 fail-closed。该 authority 运行资源为 process-tree RSS `981,893,120 B`、swap `0 B`、wall `34.103594134998275 s`，resource gate measured pass。

### 2.6 T6 完整 anchor 边界

| T6 item | status |
|---|---|
| true residual checkpoint 20 | `not_run_by_gate` |
| true residual checkpoint 100 | `not_run_by_gate` |
| 150→200 improvement | `not_run_by_gate` |
| true residual checkpoint 200 | `not_run_by_gate` |
| true residual final | `not_run_by_gate` |
| official E/H recovery | `not_run_by_gate` |
| R/T/A and `A_volume` | `not_run_by_gate` |
| diffraction channels | `not_run_by_gate` |
| frozen direct-authority comparison | `not_run_by_gate` |

### 2.7 分类和后续 handoff

| classification | 本批次实例 |
|---|---|
| measured | T2/T3/T4 numerical identity、repeat、RSS/swap；T5 bridge coefficient mismatch 和 watchdog resource；old W5 residual internal closure |
| derived | T2 h10→h5 retained exponent；T5 best complex alpha 与 scaled residual；warm RSS span |
| predicted | 当前批次没有用预测值代替 qualification；0.7 nm PDE 没有预测为通过 |
| failed | T5 RHS canonical value bridge / checker Gate |
| controlled_stop | T5 bridge failure 后的 fail-closed continuation stop；不是 OOM、不是 SIGKILL、不是算法性能结论 |
| not_run | T5 residual action/repeat/MPI2、A/B/C；T6；T7–T9；0.7 nm PDE |

T7/T8 当前均不建议开始；必须先解除 top-boundary dual authority blocker，并重新建立 hash-bound old/current physical dual coefficient semantics。所有测试和合同检查均为本地结果，不声称 CI。

### 2.8 Changed-file 与 test inventory

本批次实际变更文件按职责完整分组如下：

```text
input/README.md
input/templates/full3d_iterative_example.dat
src/io/{input_schema.py,input_validation.py,execution_plan.py}
src/runners/{task038_full3d_iterative.py,task038_input_worker.py}
src/solvers/{fullspace_mpc_action.py,fullspace_dtn_action.py,
             fullspace_slab_interface.py,hcurl_canonical_vector.py,
             hcurl_canonical_vector_dolfinx.py,fullspace_physical_action.py}
benchmarks/{run_task038_full3d_t2.py,task038_full3d_t2_checker.py,
            run_task038_full3d_t3.py,task038_full3d_t3_checker.py,
            run_task038_full3d_t4.py,task038_full3d_t4_checker.py,
            run_task038_full3d_t5.py,task038_full3d_t5_checker.py}
src/test/{test_260_task038_input_schema.py,test_262_task038_execution_plan_contract.py,
          test_268_task038_full3d_iterative_contract.py,
          test_269_task038_fullspace_matrix_free_action.py,
          test_270_task038_full3d_t2_runner_contract.py,
          test_271_task038_full3d_t3_dtn.py,test_272_task038_full3d_t4_slab_interface.py,
          test_273_task038_full3d_t4_runner_contract.py,
          test_274_task038_fullspace_dual_canonical.py,
          test_275_task038_fullspace_t5_authority.py}
docs/task038_extra_full3d_iterative_0p7nm/{task.md,review_report_v1.md,
  outcomes/{inherited_master_audit.md,task37_extra_selective_migration.md,
  task39_boundary_audit.md,matrix_free_action.md,dynamic_dtn.md,sweep_oracle.md,
  test_summary.md,records/t2_*.json,records/t3_*.json,records/t4_*.json,
  records/t5_mpi1_authority_v1_*.json},response_v1.md}
```

本地测试矩阵：T1 `test_260/test_262` 与 focused contract 共 `173 passed`，`test_268` `8 passed`；T2 `test_269/test_270` `18 passed`；T3 serial `10 passed, 1 skipped`、MPI2 regression `1 passed, 10 deselected`；T4 `test_272/test_273` targeted serial/MPI2/contract pass；T5 `test_274/test_275` focused pass，既有 `test_275` 为 `11 passed`；本轮文档合同 `test_26` 为 `14 passed`。compileall、AST duplicate-key 和 `git diff --check` 已通过；以上均为本地结果，不是 CI。

## 3. 只读诊断

old/current canonical packets 各有 `164592` 个 packet，key set 相同，duplicate/missing/extra 均为 `0`，全部有限。流式计算得到：

| quantity | value |
|---|---:|
| old norm | `13.197399418369045` |
| current norm | `1.3253714387502278` |
| difference norm | `14.492586965436216` |
| best complex global alpha | `-0.09791253215983536 - 0.019929962676216016 i` |
| scaled difference norm | `0.13293210647187068` |
| scaled difference / current norm | `0.10029800143967213` |

alpha 定义为 `argmin_a ||current-a*old||_2`。即使允许一个全局复数幅值/相位修正，仍有约 10% 的相对差异，不能安全搬运 old residual。key 完全一致只证明两边使用相同的物理实体身份和顺序；value 不一致则表示要施加的物理 dual/load 不同。把 old row array 直接送入当前 operator 会改变 forcing，故 bridge 必须 fail closed。

差异几乎全部来自 top boundary 的非零 modal packets：dimension-2 top old/current norm 为 `13.197393883461924` / `1.325370803357057`，difference norm 为 `14.492580806041088`；dimension-1 top difference norm 为 `0.013361553097537709`。bottom packet 全为零，side/volume packet 仅有约 `1e-12` 或更小的量。完整分组、key 与 hash 见 [`t5_mpi1_authority_v1_rhs_diagnostic.json`](outcomes/records/t5_mpi1_authority_v1_rhs_diagnostic.json)。

## 4. provenance 边界

旧 W5 provenance：source SHA `41cbbd454eb8336d9ea5378ed618447acfc60aac`，exact old mesh H5 SHA `ae9755890127023577a4e6b54a6d5b79aec4048a3ccbb48aec6c8c30e891bd13`，XDMF SHA `e40e1b05f3269101fe93e96416481f14bcaa64fb1df5f030381c747b484b9864`。old RHS/residual/outer_action/solution 的 file SHA、array SHA、shape/dtype 与 residual closure `1.742722222852365e-20` 已记录在 compact diagnostic 中。old/current mesh witness 的 cells、rows、constraints、geometry/connectivity digest 也一致。

源审计能够证明两条 composition 路径名义上都使用 incident top traction、top mode projection 和 `base + modal coupling`，并都使用 negative traction convention：old 为 `compose_m6b_physical_rhs -> dtn_action.compose_physical_rhs`，current 为 `FullspacePhysicalAction.compose_physical_rhs -> dtn_action.compose_physical_rhs`。但它不能证明 current MPC-aware surface assembler 的 component coefficients 与 old exact-component entries、或两次 dual coefficient 的 normalization/orientation/measure 语义完全相同。由于非零 top values 已明显不一致，本轮不猜测具体 sign/normalization 根因，也不改数值核心。

因此，旧 W5 的负结论保留为历史 evidence，只能说明旧运行的 residual 文件内部闭合；它不是当前算法性能失败。后续若要解除 hard stop，最小补证应是独立证明 old/current 非零物理 dual component 的 coefficient semantics 一致，再重新建立 residual packet bridge；在此之前禁止转换 residual 或启动 MPI2。

## 5. Formal identity and evidence

T5 authority 开始时：

- branch: `codex/20260820-task38-extra-full3d-iterative-0p7nm`；
- Review V1 authority/upstream: `80c3fa29d54813d0344a93ffa7768108ff15fa76`；
- clean source SHA: `e97db3680ee501350cc40dabe3b0b01d4c756651`；
- ahead/behind: `14/0`；
- expected/start/end source SHA: exact match；
- qualified activation: `_MYFENICS_WSL_QUALIFIED_ACTIVATION=1`，complex128，repo `.venv` executable。

本轮 pre-evidence/formal source HEAD 为 `e97db3680ee501350cc40dabe3b0b01d4c756651`；records 和本文件/两份 outcomes 文档随后作为 evidence commit 提交。final pushed handoff HEAD 在提交后由交付报告精确给出（文档无法自指自身 commit）；Review identity 没有变化。

Tracked compact evidence：

| artifact | SHA-256 |
|---|---|
| [`t5_mpi1_authority_v1_record.json`](outcomes/records/t5_mpi1_authority_v1_record.json) | `ec91c5652580bcd6f922c58ee1741ae7b7063dedf9e531d24f701c5bdfa28dd1` |
| [`t5_mpi1_authority_v1_checker.json`](outcomes/records/t5_mpi1_authority_v1_checker.json) | `ddafbabc9e5e120a09919b5db73ae644adccac8974f54368c9c42251deab8b8b` |
| [`t5_mpi1_authority_v1_watchdog.json`](outcomes/records/t5_mpi1_authority_v1_watchdog.json) | `226dd35e661e4d00c05c438aab8f6f0cacdc74300e605bb4ab3f9689d0de1ece` |
| [`t5_mpi1_authority_v1_rhs_diagnostic.json`](outcomes/records/t5_mpi1_authority_v1_rhs_diagnostic.json) | `c4dad79358212d2440a9b66aee99861eb8170eb3ca03ae6f29d368aac2ef5237` |

Raw vectors、92 MB old shard、mesh/JIT artifacts、watchdog raw 和日志仍保留在 ignored `benchmarks/artifacts/task038_extra_full3d_iterative_t5_authority_v1/mpi1/`，没有复制到 Git。

## 6. 本轮文件与验证

本轮只新增/修改以下 compact evidence/document 文件：

- `docs/task038_extra_full3d_iterative_0p7nm/outcomes/records/t5_mpi1_authority_v1_record.json`；
- `docs/task038_extra_full3d_iterative_0p7nm/outcomes/records/t5_mpi1_authority_v1_checker.json`；
- `docs/task038_extra_full3d_iterative_0p7nm/outcomes/records/t5_mpi1_authority_v1_watchdog.json`；
- `docs/task038_extra_full3d_iterative_0p7nm/outcomes/records/t5_mpi1_authority_v1_rhs_diagnostic.json`；
- `docs/task038_extra_full3d_iterative_0p7nm/outcomes/sweep_oracle.md`；
- `docs/task038_extra_full3d_iterative_0p7nm/outcomes/test_summary.md`；
- `docs/task038_extra_full3d_iterative_0p7nm/response_v1.md`。

已有 T5 code commit `e97db3680ee501350cc40dabe3b0b01d4c756651` 中的 `src/solvers/fullspace_physical_action.py`、`benchmarks/run_task038_full3d_t5.py`、`benchmarks/task038_full3d_t5_checker.py` 和 `src/test/test_275_task038_fullspace_t5_authority.py` 本轮未改动。此前 focused `test275` 为 `11 passed`，compileall、AST duplicate-key 和 `git diff --check` 已通过；本轮四份 T5 JSON parse、Markdown/table/fence、`test_26`（14 passed）和 diff check 均已通过。所有结果均为本地检查，不声称 CI 通过。
