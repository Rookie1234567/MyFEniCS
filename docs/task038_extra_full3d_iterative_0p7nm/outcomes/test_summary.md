# Review V16 最终 focused test record（2026-09-03）

本轮只做最终文档收口所需的 focused regression 与静态证据检查；没有重跑 Q1/Q2 formal、PDE、MPI case，也没有把测试通过解释成 numerical Gate。

| 项目 | 实际结果 | wall |
|---|---|---:|
| 八个指定测试文件的合并 suite（最终 lexical checkout `.venv` Python） | `91 passed`, `0 skipped` | `3.760 s`（pytest 内部 `3.41 s`） |
| 首次 activation 后裸 `python` 合并 suite | `90 passed`, `1 failed`；仅为 test339 的 symlink lexical-path 断言，非数值失败 | `5.813 s` |
| 相关 runner/checker/solver 依赖 compileall | PASS；限定 18 个 Python 文件 | — |
| checker 顶层 import boundary AST | PASS；4 个 checker 均无 runner/solver/PETSc/MPI/DOLFINx 等重型导入 | — |
| strict JSON duplicate-key/NaN | 5 passed | — |
| Q1/Q2 compact path+SHA 与 raw value 核对 | 25/25 PASS；W0 Q2 evidence/anchor 绑定一致 | — |
| Markdown links/fence/trailing whitespace | 8 files、140 local links passed | — |
| Ruff | unavailable；未安装、未声称 PASS | — |
| `git diff --check` | PASS | — |

最终测试使用同一 qualified WSL shell（`cd`、`source scripts/activate_myfenics_wsl.sh` 与命令在同一 shell）：

```bash
/home/shenjh/Projects/MyFEniCSx_task37_extra/.venv/bin/python -m pytest -q \
  src/test/test_24_repository_work_principles.py \
  src/test/test_338_task038_full3d_jit_precompile.py \
  src/test/test_339_task038_full3d_jit_staged.py \
  src/test/test_343_task038_full3d_physical_pcoarse.py \
  src/test/test_344_task038_full3d_physical_pcoarse_q1_runner.py \
  src/test/test_345_task038_full3d_physical_pcoarse_q1_action.py \
  src/test/test_346_task038_full3d_physical_pcoarse_q1_inner.py \
  src/test/test_347_task038_full3d_physical_pcoarse_q2.py
```

ABI 实测为 `_MYFENICS_WSL_QUALIFIED_ACTIVATION=1`、Open MPI 4.1.6、PETSc `complex128/int32`、OMP/OpenBLAS/MKL 线程均为 1。qualified activation 的 `.venv` 是指向 `/home/shenjh/Projects/MyFEniCS-Surrogate/.venv` 的 symlink；最终测试显式使用当前 checkout 的字面路径 `/home/shenjh/Projects/MyFEniCSx_task37_extra/.venv/bin/python`，因此首轮裸 `python` 的路径断言差异不构成代码回归。

compileall 的边界为 Q1/Q2 runner、checker、JIT staging parent/solver bundle，以及 `fullspace_same_mesh_physical_pcoarse.py`、其直接 pMG/Krylov/canonical/DtN 依赖，共 18 个明确路径；没有全仓库 compileall。Q1/Q2 formal 本回合均未重跑。Q2 的真实 numerical negative 仍绑定 source `9f18a6ccdf979f13fcb8eaab2bd57defb55f3c7b` 与既有 raw/checker，测试通过不改变其 `Q2_PHYSICAL_PCOARSE_REFERENCE_NUMERICAL_GATE_FAIL` 结论。

---

# 历史测试记录（永久保留）

# Review V16 Q1 implementation test record

| item | 已有结果 / 边界 |
|---|---|
| test343 | 4 passed |
| test301 | 15 passed, 1 skipped |
| compileall / AST / trailing / diff-check | PASS |
| Ruff | command unavailable；未声称 PASS |
| Q1 real h50 smoke/formal | not_run |
| checkpoint/JIT/MPI/PDE | not_run |

本轮纯文档检查实测：

| check | result |
|---|---|
| JSON strict duplicate-key/NaN rejection | 2 passed |
| Markdown fence/table/link/whitespace | 5 Markdown files, 107 local links passed |
| git diff --check | PASS |

这些是 Q1 core 的实现回归，不构成 p6/h50 R3 source authority 或 Q1 numerical
qualification。source-authority 预检见 [oracle closeout](physical_pcoarse_oracle_v16.md)
和 [authority compact](records/physical_pcoarse_q1_authority_v16.json)。

---

# Task038-extra T2 test and evidence summary

## 1. Source and environment identity

| item | value |
|---|---|
| branch | `codex/20260820-task38-extra-full3d-iterative-0p7nm` |
| implementation commit | `5ce75540ff97089f74021660876ab2022ffad1f9` |
| narrow serialization fix commit | `6d60bb5a9a59e88da98b027efeed8506d5dd7a82` |
| formal record source SHA | `6d60bb5a9a59e88da98b027efeed8506d5dd7a82` |
| upstream at formal start | `80c3fa29d54813d0344a93ffa7768108ff15fa76` |
| branch relation at formal start | ahead 4 / behind 0 |
| worktree before formal | clean; no nonignored untracked files |
| activation | `_MYFENICS_WSL_QUALIFIED_ACTIVATION=1` |
| Python | `/home/shenjh/Projects/MyFEniCS-Surrogate/.venv/bin/python` |
| platform | WSL2 Linux `6.6.114.1-microsoft-standard-WSL2-x86_64` |
| PETSc scalar / integer | `complex128` / `int32` |
| MPI world in serial preflight | 1 |
| MPI/PETSc/DOLFINx stack | qualified complex PETSc/SLEPc 3.19 stack; DOLFINx and Basix from the same activated environment |
| thread limits | OMP, OpenBLAS and MKL all `1` |

## 2. Commands and outcomes

The implementation and narrow fix were committed before formal execution. Every formal run used the same qualified activation and the exact expected source SHA below. Raw directories are ignored; the record path is inside the corresponding ignored attempt directory.

```bash
source scripts/activate_myfenics_wsl.sh
python -m pytest -q src/test/test_270_task038_full3d_t2_runner_contract.py src/test/test_269_task038_fullspace_matrix_free_action.py
# 18 passed in 1.13s

python -m benchmarks.run_task038_full3d_t2 run --case p2-h50 --raw-dir benchmarks/artifacts/task038_extra_full3d_iterative_t2/p2-h50-mpi1-rerun/raw --record benchmarks/artifacts/task038_extra_full3d_iterative_t2/p2-h50-mpi1-rerun/record.json --expected-source-sha 6d60bb5a9a59e88da98b027efeed8506d5dd7a82 --expected-mpi-size 1
python -m benchmarks.run_task038_full3d_t2 run --case p3-h50 --raw-dir benchmarks/artifacts/task038_extra_full3d_iterative_t2/p3-h50-mpi1/raw --record benchmarks/artifacts/task038_extra_full3d_iterative_t2/p3-h50-mpi1/record.json --expected-source-sha 6d60bb5a9a59e88da98b027efeed8506d5dd7a82 --expected-mpi-size 1
python -m benchmarks.run_task038_full3d_t2 run --case p6-h10 --raw-dir benchmarks/artifacts/task038_extra_full3d_iterative_t2/p6-h10-mpi1/raw --record benchmarks/artifacts/task038_extra_full3d_iterative_t2/p6-h10-mpi1/record.json --expected-source-sha 6d60bb5a9a59e88da98b027efeed8506d5dd7a82 --expected-mpi-size 1
mpiexec -n 2 python -m benchmarks.run_task038_full3d_t2 run --case p6-h10 --raw-dir benchmarks/artifacts/task038_extra_full3d_iterative_t2/p6-h10-mpi2/raw --record benchmarks/artifacts/task038_extra_full3d_iterative_t2/p6-h10-mpi2/record.json --expected-source-sha 6d60bb5a9a59e88da98b027efeed8506d5dd7a82 --expected-mpi-size 2
python -m benchmarks.run_task038_full3d_t2 run --case p6-h5 --raw-dir benchmarks/artifacts/task038_extra_full3d_iterative_t2/p6-h5-mpi1/raw --record benchmarks/artifacts/task038_extra_full3d_iterative_t2/p6-h5-mpi1/record.json --expected-source-sha 6d60bb5a9a59e88da98b027efeed8506d5dd7a82 --expected-mpi-size 1

python -m benchmarks.run_task038_full3d_t2 aggregate --p2-mpi1-record benchmarks/artifacts/task038_extra_full3d_iterative_t2/p2-h50-mpi1-rerun/record.json --p3-mpi1-record benchmarks/artifacts/task038_extra_full3d_iterative_t2/p3-h50-mpi1/record.json --p6-h10-mpi1-record benchmarks/artifacts/task038_extra_full3d_iterative_t2/p6-h10-mpi1/record.json --p6-h10-mpi2-record benchmarks/artifacts/task038_extra_full3d_iterative_t2/p6-h10-mpi2/record.json --p6-h5-mpi1-record benchmarks/artifacts/task038_extra_full3d_iterative_t2/p6-h5-mpi1/record.json
```

The actual runner wall times were p2-h50 MPI1 `1.48 s` after the authorized fix, p3-h50 MPI1 `10.47 s`, p6-h10 MPI1 `90.20 s`, p6-h10 MPI2 `19.66 s`, and p6-h5 MPI1 `97.79 s`. The aggregate checker took `73.42 s` and returned `T2_ACTION_PASS` with `exact_five_record_set`, `evidence`, `mpi_canonical_identity`, and `mandatory_h10_to_h5_scaling` all true.

## 3. Tracked compact records and hashes

| compact artifact | SHA-256 |
|---|---|
| [`t2_p2_h50_mpi1_v1.json`](records/t2_p2_h50_mpi1_v1.json) | `cda3924e0db671572b043481cda05492747c2935a63af329a8bcf80bb5821554` |
| [`t2_p3_h50_mpi1_v1.json`](records/t2_p3_h50_mpi1_v1.json) | `e8e7789fe69dc1bdbd6c34228f1332ff1c32352c7c80051de6f7fef7ee235700` |
| [`t2_p6_h10_mpi1_v1.json`](records/t2_p6_h10_mpi1_v1.json) | `dbf58723adbfd505f5863178c7e012dedd2b393c14b049e149e7e652d7f3dcde` |
| [`t2_p6_h10_mpi2_v1.json`](records/t2_p6_h10_mpi2_v1.json) | `76f0d3b9c306c1f11a169743c9f54a4d42263e006e7b151066ee45719bde5b1d` |
| [`t2_p6_h5_mpi1_v1.json`](records/t2_p6_h5_mpi1_v1.json) | `aba248e8d3c7d0a50a2c5b720e523f27dd1262e300a08756308a7d2e677e1f25` |
| [`t2_aggregate_check_v1.json`](records/t2_aggregate_check_v1.json) | `1b604df72dcaa20a7d23efc1a8dccf3e9564820bbdbf8ad54007f1c6869a7dcd` |

Each compact record retains the absolute ignored raw directory and the source/action/reference artifact SHA-256 descriptors. The raw roots are:

```text
benchmarks/artifacts/task038_extra_full3d_iterative_t2/p2-h50-mpi1-rerun/raw
benchmarks/artifacts/task038_extra_full3d_iterative_t2/p3-h50-mpi1/raw
benchmarks/artifacts/task038_extra_full3d_iterative_t2/p6-h10-mpi1/raw
benchmarks/artifacts/task038_extra_full3d_iterative_t2/p6-h10-mpi2/raw
benchmarks/artifacts/task038_extra_full3d_iterative_t2/p6-h5-mpi1/raw
```

## 4. Test and scope decision

| item | result | identity / evidence |
|---|---|---|
| focused test269 + test270 | 18 passed | exact formal source content; rerun after the fix commit |
| compileall | pass | qualified activation, runner/checker/action modules |
| `git diff --check` | pass | before formal and before evidence staging |
| T2 five-case aggregate | pass | compact aggregate record above |
| process-tree peak | not measured | T2 keeps `not_measured_t2`; no process-tree claim |
| KSP / PDE / DtN | not run | T2 action-only boundary |
| T3 | not started | stop for supervision review |
| T7/T8/T9 | not authorized | unchanged Review V1 boundary |

The first p2-h50 attempt at implementation SHA `5ce75540ff97089f74021660876ab2022ffad1f9` failed only during JSON serialization; its raw mesh and vectors remain ignored and were not deleted. The single narrow fix was committed as `6d60bb5a9a59e88da98b027efeed8506d5dd7a82`; the same p2 case was rerun once and passed. No other formal case was retried.

# Task038-extra T3 formal test and evidence summary

## 5. Source and formal identity

| item | result |
|---|---|
| T3 implementation source SHA | `b9ec1375d6e0727059b4f3c043561aa00bcf3ffc` |
| T3 narrow MPI initialization fix / formal source SHA | `691ac261fd62258d356183cb3c0383307605b15e` |
| upstream | `80c3fa29d54813d0344a93ffa7768108ff15fa76` |
| branch relation after fix | ahead 7 / behind 0 |
| frozen input | `input/templates/full3d_iterative_example.dat`, 2119 bytes, SHA `819fc99caea2dbc8ea22546917fbe3898c822a955d079b4582c4a27e34ebba41` |
| resolved config | 4076 bytes, SHA `78dc49b3a7ae212dec6374fde09eaaa231c131ce64790202da062b3ca2b09aad` |
| physical model | SHA `9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f` |
| formal identity | p6/h10, 13.5 nm, degree 6, h=10 nm, `full3d_scalable_v1`, `dtn_port`, `auto_propagating`, `auxiliary` |

T1 adapter 预检动态发现 80 modes：78 propagating、0 near-cutoff、2 evanescent；ordered manifest SHA 为 `dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2`。生产构造器没有写死 80；80 是本 frozen benchmark 的 authority assertion。

## 6. Checks and results

| check | result |
|---|---|
| serial T3 after narrow fix | `10 passed, 1 skipped` |
| MPI2 shared-directory regression | each rank `1 passed, 10 deselected`, wall `1.32 s` |
| T2 test269 + test270 regression | `18 passed` |
| compileall / `git diff --check` | pass |
| formal T3 MPI1 / MPI2 runner wall | `23.52 s` / `12.12 s` |
| independent MPI1/MPI2 checkers | both `T3_PASS` |
| aggregate | `T3_PASS`; canonical source/action/reference relative L2 `0.0`, recovery relative L2 `0.0` |

两条 formal record 都执行 12 次真实 apply，并在每次之后采集 elapsed、rank-max current RSS 与 swap。action error 为 `1.5267729283364925e-16`，recovery error 为 `8.148489733468128e-17`；RSS warm span 为 MPI1 `61440 B`、MPI2 `45056 B`，均低于 `64 MiB`，swap 均为 `0 B`。retained numeric bytes 与固定 batch work 在 [`dynamic_dtn.md`](dynamic_dtn.md) 和 tracked compact records 中分别保留。

## 7. Scope

T3 只完成 action/recovery formal；没有运行 KSP、Maxwell PDE、T4 或 0.7 nm full PDE。process-tree peak 明确为 `not_measured_t3`。MPI2 attempt1 的 TOCTOU traceback、空 raw 残留目录和 failure log 保留在 ignored `t3_formal_v1` artifact 下，未与新 `t3_formal_v2` SHA 混合。

## 8. T4 formal bounded transmission oracle

T4 用真实两-slab Full3D fixture 检查 owner-local interface topology 和 candidate A 一阶 tangential Robin/impedance transmission action。它只验证边界动作与独立 facet-quadrature oracle 的一致性，不建立 KSP、不解 PDE，也不声称 process-tree 峰值。四个冻结 case 是 p2/MPI1、p2/MPI2、p3/MPI1、p3/MPI2，均使用固定斜入射 s/p source family 和固定 s+p test field。

| item | result |
|---|---|
| formal implementation/fix SHA | `88e5cef8a007445270721b9076b0c33453f743f3` |
| expected/start/end SHA | exact same SHA in all four records |
| individual checker | 4 × `T4_PASS` |
| aggregate | `T4_AGGREGATE_PASS`; exact four-case set |
| max action/oracle relative error | `1.1347e-15` (limit `1e-11`) |
| max cross-MPI physical canonical relative L2 | `7.1149e-15` (limit `1e-12`) |
| R/P adjoint and reconstruction | all recorded values 0 |
| apply telemetry | 8 real applies/case; repeat differences 0 |
| warm rank-max current RSS span | 1,363,968–1,683,456 B; below 64 MiB |
| swap | 0 B in all cases; current process `VmSwap` semantics |
| process-tree | `not_measured_t4` |
| KSP / PDE / official physics | false / false / `not_run` |

Retained numeric payload/work was measured separately: p2/MPI1 `45,696/10,368 B`, p2/MPI2 `30,192/10,368 B` local retained/work, p3/MPI1 `127,296/27,648 B`, and p3/MPI2 `84,936/27,648 B` (global-max retained values are in the compact records). No numeric allgather, global AIJ, dense interface mass/Schur, or slab factor was materialized. The full T4 explanation and artifact hashes are in [`sweep_oracle.md`](sweep_oracle.md).

The first v1 p2/MPI1 checker result is retained as explicit negative evidence: the independent pairing passed, but the runner omitted the action manifest from the evidence registry. The narrow fix closed only that registry assignment; v2 reran all four cases and is the qualifying T4 result. The v1 record/check are [`t4_p2_h50_mpi1_v1_evidence_defect_record.json`](records/t4_p2_h50_mpi1_v1_evidence_defect_record.json) and [`t4_p2_h50_mpi1_v1_evidence_defect_check.json`](records/t4_p2_h50_mpi1_v1_evidence_defect_check.json). T6 and push remain unstarted; T5 is reported below as a hard-stopped authority attempt.

## 9. T5 long-tail authority bridge（hard stop）

T1、T2、T3、T4 的已审查结果保持 PASS。T5 MPI1 只完成 authority bridge 前置步骤，状态为 `BLOCKED_BY_LONG_TAIL_RESIDUAL_AUTHORITY`：old/current physical RHS canonical packet count 都是 `164592`，key set 完全一致，duplicate/missing/extra 都是 `0`，但实际 coefficient relative L2 为 `10.934736136386151`，最大 packet absolute difference 为 `1.2846616424283923`，均不能通过 canonical `1e-12` Gate。

这表示“地址相同，数值不同”。canonical key 像一张不随 MPI 分区变化的门牌清单；它证明两边在谈同一条边/同一个实体，却不证明门牌上写的 load 数值相同。old residual 是物理 dual/load，不是可以只按 row number 搬运的普通数组。若在 value bridge 未闭合时继续使用，它会把不同的物理 forcing 送入当前 action，所以 checker fail-closed，并不把该结果解释成算法性能失败。

旧 W5 文件内部仍有独立的 residual closure：`rhs - outer_action` 的 relative L2 为 `1.742722222852365e-20`，文件/array SHA、shape `[173802]`、`complex128`、exact mesh 和 old source SHA 均记录在 [`sweep_oracle.md`](sweep_oracle.md) 与 [`t5_mpi1_authority_v1_rhs_diagnostic.json`](records/t5_mpi1_authority_v1_rhs_diagnostic.json) 中。这只能证明旧运行自洽，不能证明 old dual convention 与 current T3 compose/extractor 的非零 top modal values 相同。

| T5 item | result |
|---|---|
| old/current key/count/duplicate structure | pass / `164592` each / `0` |
| RHS value bridge | fail; relative `10.934736136386151`, max abs `1.2846616424283923` |
| resource | measured pass; process-tree RSS `981,893,120 B`, swap `0 B` |
| residual action/reference and repeat | `not_run_by_gate` |
| MPI2 residual identity | `not_run_by_gate` |
| Candidate A/B/C and T6 | `not_run_by_gate` |
| T7–T9 and 0.7 nm | `not_run` |

The old W5 negative evidence is retained as historical evidence and is not an algorithm-performance result. T5 compact record/checker/watchdog and the read-only norm/alpha/position diagnostic are listed in [`sweep_oracle.md`](sweep_oracle.md). Formal source identity at start was `e97db3680ee501350cc40dabe3b0b01d4c756651`; the current documentation changes are pending and have not been committed or pushed. No CI claim is made; all listed checks are local.

# Review V2 R0–R4 closure

本节补充当前 Review V2 批次的最终边界；前面的 T2/T3/T4 数值表和 v1 negative evidence 保持不变。`action` 是当前离散物理算子的向量作用，`sweep` 是两 slab 的固定 forward/backward 残差传播，`transmission` 是 slab 间边界数据动作；三者都不能把一次 boundary apply 直接称为完整 PDE 求解。

## Identity and authority

| stage | source/evidence | result |
|---|---|---|
| R0 | final pre-formal source `ea7fc96b8c95eca13b5ee8055d7e0762f9ab02dc`; qualified activation; complex128/int32; clean preflight | PASS |
| R1 | clean source `cd1ca8dfe6fdcc7a526d2794d2963dd6cd81a470`; structured current/old identity records | PASS；`HISTORICAL_W5_NOT_SAME_PHYSICAL_RHS` |
| R2 | source `09b926428babc2f0a8dd4b4061b7e18d7dd23aba`; p2/p3 MPI1、p6/h10 MPI1+MPI2 component raw/check | PASS；current oracle independent and hash-bound |
| R3 | source `2c8fca90c7300b85b30021081868b699c0b306d2`; MPI1/MPI2 pair；process-tree watchdog未测 | PASS；`CURRENT_RECOMPUTED_RESIDUAL_AT_HISTORICAL_W5_STATE`，不含 process-tree resource qualification |

R1 old/current RHS key/count/duplicate structure passed with 164,592 packets each, but relative L2 was `10.934736136386151` and maximum packet difference `1.2846616424283923`; this is why old residual was not directly reused. R3 used the old primal solution only, with no empirical scaling: primal roundtrip `1.3336463445521434e-17`, current residual recompute `2.381515544959568e-18`, mapped primal MPI1/MPI2 `1.4389898139779045e-17`, residual cross-MPI `1.145631881739048e-14`, repeat `0`, swap `0 B`. R3 process-tree resource provenance was not measured; only rank-local RSS/VmSwap is present.

## R2 current component oracle

| case | max candidate/direct relative L2 | limit | H max error | all-mode/group recompose | repeat max | status |
|---|---:|---:|---:|---:|---:|---|
| p2/h50 MPI1 | `8.692664947436813e-15` | `1e-12` | `0` | `0` | `5.909031086016836e-17` | PASS |
| p3/h50 MPI1 | `2.5937308039595027e-14` | `1e-12` | `0` | `0` | `7.611020931512763e-17` | PASS |
| p6/h10 MPI1 | `4.559266389658486e-14` | `1e-11` | `3.2741809263825522e-15` | `0` | `4.8257303460951034e-17` | PASS |
| p6/h10 MPI2 | `4.559266389658486e-14` | `1e-11` | `3.2741809263825522e-15` | `0` | `4.8257303460951034e-17` | PASS |

## R4 Candidate A/B/C

| candidate | measured result | resource | classification |
|---|---|---|---|
| A physical_rhs MPI1 | rho `0.8145890334049838 > 0.60`; closure `1.2458376041083906e-16`; repeat `0` | peak `5,145,784,320 B`; wall `2812.015165732999 s`; swap `0` | numerical contraction FAIL；不是实现失败 |
| A gradient MPI1 | rho `0.8889127715646881 <= 0.90`; closure `1.271047984953834e-19`; repeat `0` | peak `1,323,728,896 B`; wall `2747.751835015006 s`; swap `0` | PASS |
| A remaining 8 cases | not started | not applicable | `not_run_by_fail_fast` |
| B | no rho/resource run | mixed Si–Si/Si-air interior; T3 only exterior authority | `NOT_APPLICABLE / CANDIDATE_B_INTERIOR_MODAL_AUTHORITY_NOT_QUALIFIED` |
| C physical_rhs MPI1 | focused authority/tests PASS；worker before record | watchdog peak `12,942,209,024 B`; wall `406.7977727999969 s`; swap `0`; return `-15`; `hard_stop_12_gib` | `CONTROLLED_STOP_HARD_12_GIB` |

C 的 decimal 6 GB 和 12 GiB Gate 都失败。由于没有 `record.json`，R4 checker 只产生 fail-closed 的缺失输入结论，未生成标准 `check.json`；C 的 rho、closure、repeat、finite、update counts、class manifest 和 formal payload 都是 `not_run_by_resource_hard_stop`，不能称数值失败。完整 watchdog raw/compact SHA 在 `t5_sweep_candidate_c_v2.json` 和 `sweep_oracle.md` 中。

## Validation boundary

本轮只新增/更新 compact JSON 与文档，没有修改 Python、没有重新启动 formal/PDE。文档内容不能自引用未来 commit；最终提交/push状态由交付报告给出。R4 overall 为 `FAIL / CONTROLLED_STOP_RESOURCE`；R5/T6-S、T6-F/EH/RTA、T7–T9 和 full 0.7 nm 均 `not_run_by_R4_gate` 或 `not_run`。A 的 5.145 GB cold peak 与 1.324 GB gradient warm-like peak 不是完整 PDE 的 `<2 GB` 证明。测试、compileall、AST、JSON 和 Markdown 检查均为本地结果，不声称 CI。

# Review V3 D0/D1 closeout

本节追加记录 Review V3 的 D0/D1；前面的 T2、T3、T4、T5 和 Review V2 历史内容不变。

## D0 transmission family 与 coarse preflight

| item | result |
|---|---|
| D0 commit | `79b33f86b22ba33a610c1167fe0c2287dc3d7b54` |
| Candidate A | 仅保留为完全冻结的 one forward+backward smoother oracle；transmission、two slabs、local GMRES 8/8 不变 |
| Candidate B | `NOT_APPLICABLE / CANDIDATE_B_INTERIOR_MODAL_AUTHORITY_NOT_QUALIFIED`；mixed Si–Si/Si–air interior authority 不足 |
| Candidate C / transmission family | research archive，`DO_NOT_RERUN / DO_NOT_OPTIMIZE / DO_NOT_MERGE`；保留源码和负证据，不表述为数学永远不可能 |
| coarse byte preflight | N=173802，complex128 full vector=2,780,832 B；Z+AZ 的 r=16/32/48/64 为 88,986,624 / 177,973,248 / 266,959,872 / 355,946,496 B |
| budget boundary | coarse metadata/work `<=64,000,000 B` 是内部 envelope；D0 的 `424,000,000 B` 不是 V4 N0 独立 Gate |

D0 明确区分 cold build/JIT/setup 与 online apply，owner-local sharding，不复制每 rank
完整 basis，不做 FE-sized numeric allgather，不建 global AIJ/Schur/sparse factor。

## D1 formal result

| item | result |
|---|---|
| implementation commit | `a650aae08957736eedf7b6c4842cce15c73da708` |
| formal source SHA | `ddf7801af3285a35ee1a53c728d552a15e8d6983` |
| cases | p2-MPI1、p2-MPI2、p3-MPI1、p3-MPI2；四个 individual PASS，aggregate PASS |
| serial algebra | p2/p3 MPI1 assembled oracle only；MPI2 serial algebra按固定 boundary `not_run` |
| cross-MPI | source/B/MΓ 五组每个 degree 均 `<=1e-12`，missing/extra/duplicate=0 |
| R/P / repeat / extension | adjoint=0；eigen repeat exact；extension error=0 |
| resources | rank-max current self RSS；216,186,880 / 114,843,648 / 1,046,962,176 / 120,438,784 B；VmSwap 全为 0 |
| process-tree | `not_measured` |
| next stages | D2/D3/D4、T6-F、T7–T9、full 0.7 nm `not_run` |

`adaptive_coarse_oracle.md` 保存完整的 B_i/MΓ/K defect、eigen residual/rank/repeat、
canonical role/count、cross-MPI relative L2、record/check SHA 和 ignored raw 路径。三次
启动层事件（sandbox PMIx、venv symlink provenance defect、首次脚本路径
`ModuleNotFoundError` 空 raw）均发生在数值之前，不计为 D1 formal failure；首次空 raw
目录保留。D1 通过的是小 fixture oracle，不是 p6 production coarse，也没有 process-tree
资源资格化或 PDE 结果。

## Review V3 D2 controlled negative

本节继续追加，不覆盖前面的 T2–T5、R0–R4 和 D0/D1 历史记录。D2 只执行了
`p6-h10-mpi1` 一次 formal attempt，源码绑定为
`cc8de60cc3e21b647aafb29ac9c10b46919823e7`；没有启动 MPI2、D3、D4 或 PDE。

| stage / item | result | classification |
|---|---|---|
| D0 memory preflight | rank64 `Z+AZ=355,946,496 B`; derived total `419,946,496 B` | derived/budget only |
| D1 p2/p3 oracle | 4 cases individual PASS, aggregate PASS | accepted/frozen |
| D2 MPI1 | `557.385958733 s` wall；marker monotonic `510.287976466 s` | controlled negative |
| D2 failure | slab 0 interior CG `-3` = `KSP_DIVERGED_ITS`，固定 500 步耗尽 | failed algebra/setup gate |
| D2 resource | process-tree peak `3,013,468,160 B`；process-tree swap `0 B`；natural exit rc=1 | not resource hard stop |
| D2 artifacts | marker `preflight→mesh_mpc_topology→trace_basis_build→failure`；无 Z/AZ/E | preserved negative |
| D2 MPI2 | 未运行 | `not_run_by_D2_rank64_hard_stop` |
| D3 coarse-only / two-level | 五类 source、rho、online `<2 GB` 均未运行 | `not_run_by_D2_rank64_hard_stop` |
| D4 / T6-S | 20/100/150/200 checkpoints 未运行 | `not_run_by_D2_rank64_hard_stop` |

本次不是 12 GiB 或 swap stop；固定局部 CG 在规定的 500 次迭代内没有收敛，Review
V3 hard stop #7/#12 禁止增加步数、调参或重跑。3,013,468,160 B 是 construction/JIT
阶段的 process-tree 峰值，不是 D3 online 内存测量，也不是完整 PDE 峰值。D2 worker
record、watchdog raw/compact 和 log 的路径与 SHA 见
`outcomes/adaptive_coarse_oracle.md`；raw 保持 ignored，compact record 保留在
预定 outcomes record 路径。独立 checker 对 controlled-negative backfill 返回
`passed=false`（`record schema or stage is invalid`），没有因为缺少成功字段而 PASS。

Candidate C 源码及负证据保持 `DO_NOT_RERUN / DO_NOT_OPTIMIZE / DO_NOT_MERGE`；D2
实现、runner、checker 因 rank64 未资格化列为 `research-only / do-not-merge`。D1
小 fixture 正证据仍可保留。T6-F、EH/RTA、T7–T9 和 full 0.7 nm 均未运行。

# Review V4 N0 capacity preflight

本节只追加 N0 的 docs/records-only 阶段矩阵，不覆盖前面的 T2–D2 历史结果。N0
把“自适应粗空间”冻结为一个固定 cell-block local spectral 设计：每个 hexahedral
cell 最多 882 个 owned active DoF，最多 32 个 exact local factor classes，每 patch
固定 8 个局部模式（3个坐标梯度+5个正谱方向）；regional `Z16` 作为 online level-1
correction 保留，再建立并保留 top rank32 `Z+AZ`。

| stage / gate | result | evidence boundary |
|---|---|---|
| N0 ABI/canonical worktree preflight | PASS；qualified marker `1`，complex128/int32，threads=1，canonical `.git-codex` | 轻量 preflight；没有启动 pytest/PDE |
| N0 central complete-workflow budget | `1,698,919,864 B < 1,800,000,000 B` | T2 current-self RSS baseline + 新增同时存活项 + central `32,000,000 B` runtime/process-tree baseline uncertainty reserve；derived/budget |
| N0 hard complete-workflow budget | `1,798,919,864 B < 2,000,000,000 B` | 含 factor/mode/coarse/Krylov/telemetry/recovery/allocator hard reserve + hard `64,000,000 B` baseline uncertainty reserve；不是当前实测 |
| N0 online runtime baseline | `951,054,336 B` | T2 MPI1 setup current-self RSS lower-bound/calibration；T2 retained `6,151,104 B`已包含 |
| N0 global class-factor ownership | `199,374,336 B` global/process-tree total；每 class 一个 deterministic owner，MPI2不复制32 factors | N1必须验证class-owner MPI identity；patch RHS/solution走bounded `882`-entry route |
| N0 coarse payload | `286,466,560 B` | regional `Z16=44,493,312` + top `Z32+AZ32=177,973,248` + metadata/work `64,000,000` |
| N0 regional online correction | `44,493,312 B` 与 top `Z+AZ` 同时计入 | distributed regional coarse level，不能 setup-only 释放 |
| N0 FGMRES vectors | `114,014,112 B` | right restart20为 `V_(m+1)+Z_m=41` full vectors |
| N0 D0 retained reference | `424,000,000 B` | 历史 D0 口径，不是 V4 N0 独立 Gate |
| N0 classification | `BOUNDED_LOCAL_SPECTRAL_MULTILEVEL_CAPACITY_PREFLIGHT_PASS_CONDITIONAL` | 只说明账本闭合；不授权 N1/N2 |
| N1/N2/D3/D4/T6-F/T7–T9 | `not_run` | 不因 N0 静态预算写成数值或 resource pass |

Preflight 实值：`MemAvailable=13,482,110,976 B`，system swap used
`17,149,952 B`，current process `VmSwap=0`；cgroup swap authority unavailable，故
记为 `not_measured`。当前 branch/HEAD 为 `codex/20260820-task38-extra-full3d-iterative-0p7nm` /
`5aaf5748fb24828c3d0d03411df9ff388b4cc2db`，upstream 同 SHA、ahead/behind `0/0`。
N0 文档与 compact record 的完整算术、引用、生命周期和禁止项在
[`local_spectral_multilevel_preflight.md`](local_spectral_multilevel_preflight.md)
与 [`records/n0_local_spectral_capacity_v1.json`](records/n0_local_spectral_capacity_v1.json)。

## Review V4 N2：local spectral setup controlled negative

本节追加在既有 T1–T4、D0/D1 和历史 T5/R4 记录之后，不覆盖旧结论。

|阶段/证据|结果|说明|
|---|---|---|
|N0|PASS_CONDITIONAL|docs-only capacity preflight；central 1,698,919,864 B、hard 1,798,919,864 B，不是 p6 setup 实测 pass|
|N1|PASS|p2/p3 × MPI1/MPI2 四个正式 local spectral oracle case及 aggregate通过|
|N2 MPI1|CONTROLLED_NEGATIVE_LOCAL_FACTOR_SOLVE_GATE|fixed RHS solve residual 1.0426245523812324e-11 > 1e-11，worker rc=1|
|N2 MPI2/N3/N4|not_run_by_gate|没有通过 N2 MPI1 local factor Gate|
|后续 T6-F/EH/RTA/T7–T9/full0.7nm|not_run|无 PDE/official physics|

N1/源码收口的本地测试记录为 27 passed, 1 skipped，test290 为 12 passed；p2 MPI1/MPI2 small smoke、compileall、AST/diff-check 均通过。这些都是本地非 CI 结果。更早的一次 MPI smoke session 后来被识别为本执行者留下的测试基础设施进程并终止，属于清理动作，不是 formal worker orphan；本次正式 N2 worker 的 watchdog 明确记录 worker 自行返回 rc=1，watchdog 未发 SIGTERM/SIGKILL，随后 already_exited、no orphan、无 SIGKILL。

N2 唯一一次正式 MPI1 setup 的 marker 为 preflight -> mesh_space_mpc -> JIT -> subdomain_inventory -> local_factor_build -> failure；worker marker wall 125.03350535 s，watchdog elapsed 126.7811168670014 s，127 samples，process-tree memory authority peak 1,506,271,232 B，process-tree swap 0 B。失败发生在 local factor build，未得到 post-setup retained、252 inventory最终闭合、modes/regional/top、Z/AZ/E、zero identity或MPI2证据。详情见 local_spectral_setup.md 与 response_v4.md。

## Review V5 continuation：当前 N2 lane

| 阶段 | 结果 | 证据边界 |
|---|---|---|
| marker allowlist focused regression | `31 passed`；compileall/AST/diff-check pass | 本地测试，未启动 heavy |
| LA0/LA1 v3 | LA0 reproduction PASS；independent LA1 Path T | 诊断证据，不是 N2 setup PASS |
| Path T production repair | commit `b20de496...`；`test287+290+291 = 39 passed, 1 skipped` | formal source commit；最终 push 状态见交付报告 |
| fresh N2 MPI1 | `CONTROLLED_NEGATIVE_LOCAL_FACTOR_SOLVE_GATE`；residual `1.1089747142000698e-11 > 1e-11` | worker/watchdog/checker `1/1/1`；失败点前 peak `1,504,804,864 B`、swap0；完整 setup 未资格化 |
| MPI2/N3/N4/T6-F/EH/RTA/T7–T9/full0.7nm | `not_run_by_gate` | 不写成数值或资源通过 |

本节由最终 docs closure commit 携带；final docs SHA 无法自引用，见交付报告；旧 T1–N2 v1 记录不覆盖，未作 CI 声明。

## Review V14 J9 docs-only closeout

本轮只对已经完成的 J5 v3 controlled-stop 事实做文档和轻量 compact 收口，没有重跑 336–339，也没有运行 checker、J6/J7/J8 或任何 heavy。此前同一 source SHA 下的 336–339 `23 passed` 作为已审阅事实复用，不把它写成本文档测试的重新执行结果。

| 检查 | 本轮边界 |
|---|---|
| JSON parse | J0 authority JSON 与新 J5 compact 必须严格解析 |
| Markdown/link/whitespace | 相关 outcomes、response 和 progress 文档的本地链接、表格列和空白检查 |
| `git diff --check` | docs-only diff |
| raw artifact | 1,020,808,306 B JSONL 继续 ignored；只绑定 SHA，不加入 Git |
| 结论 | J5 `CONTROLLED_STOP_USER_NUMERICAL_STAGNATION / NOT_QUALIFIED`；没有 CI/full pytest 声明 |

## Review V15 F1/F2/F3 与 F4 文档收口

| 检查/证据 | 真实结果 | 说明 |
|---|---|---|
| F1 v5 MPI1 runner | PASS | real small p3/h50；record 与四数组 NPZ 有 hash-bound evidence |
| F1 v5 MPI2 runner | PASS | real small p3/h50；canonical key identity 与 PC/modal Gate 通过 |
| F1 v5 independent checker | PASS | classification F1_REAL_SMALL_ORACLE_PASS |
| focused implementation test339 + test342 | 9 passed | 已审阅的实现/diagnostic focused tests |
| diagnostic source-import/CLI focused regression | 4 passed | diagnostic entry-point contract |
| compileall / AST / import boundary / diff-check | PASS | 本地检查，无 full repository CI 声明 |
| test_24 + test_26 | 22 passed | docs/repository principles 与 Markdown contract |
| strict JSON / local links / whitespace | PASS | 2 JSON、7 Markdown、106 个本地链接 |
| V15 formal artifact v3 F2/F3 | F2 PASS；F3 span Gate FAIL | captured 0.002179823642496248，rho 0.9989094935766222 |
| V15 formal artifact v3 independent checker | exit=1（预期） | classification FLOQUET_WAVE_CORRECTION_CLOSED_BY_SPAN_GATE |

F3 的 algebra、rank、QR、重复性、计数和资源事实通过，但固定 32 个波模未达到 span Gate；不能把该结果写成 solver/PDE PASS。J6/J7/J8、KSP、recovery 和 official physics 均未运行。没有 full repo CI 结果，以上均为本地或正式 artifact 事实。
