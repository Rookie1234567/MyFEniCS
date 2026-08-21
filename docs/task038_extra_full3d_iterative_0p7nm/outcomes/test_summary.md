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
