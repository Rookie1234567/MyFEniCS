# Task037b 测试汇总

## 已完成 Gate

| 阶段 | 命令/范围 | 结果 |
|---|---|---|
| H0 继承 focused suite | 12 个指定文件 | 76 passed / 1 skipped，225.86 s |
| H0 轻量重核 | test24 + test26 | 21 passed |
| H1-A implementation Gate | test181、test53 hash、test59、test79 | 40 passed |
| H1-A static | Ruff check、Ruff format-check、compileall、git diff --check | 全部 pass |
| H1 preflight | ABI、authority hash、pinned reference gate、parser/launch admission、资源/空 run-dir | pass |

所有测试均为本地结果，不表示 CI 结果。

## H1 首次 formal（3f72ef3）

H1 唯一 MPI8 formal 返回 1，并在生成解以前失败。分类是 failed_before_solve / controlled_stop / inherited correctness regression；不是 residual、R/T/A 或物理 Gate 的负结果。由于停止点早于最终 targeted Gate，H1 formal 后没有再运行 full pytest，也没有重跑 H1。

## H1 post-fix recovery（2990f357）

| 项目 | 结果 |
|---|---|
| post-fix formal return/status | 0 / measured_shard_pass |
| true residual | 1.4476013948489319e-12 |
| task.md §9 H1 numerical contract | pass；frozen-reference power/amplitude 12/12 + 12/12，Full3D pairwise 12/12 + 12/12 |
| post-fix targeted tests | 14 passed |
| H1-A targeted tests | 43 passed |
| Ruff check / format-check | pass |
| compileall / git diff --check | pass |
| early unified session | 12 dots、无 exit；infrastructure_indeterminate，不计入 pass/fail |
| full pytest / CI | 未运行 / 不声称 CI |

post-fix H1 只修复近简并分组与 partition audit 范数语义的窄回归，未放宽 `1e-6`、未加入 fallback/retry、未改变 ordinary defaults。上述 post-fix formal 与离线既有 comparator 证据均绑定 source `2990f357f7dec23b1713bd0088bdc43c3ce6f5bc`。

## H0-H10 测试状态

| 阶段 | 状态 |
|---|---|
| H0 | pass |
| H1 | pass（post-fix；首次 failed_before_solve 历史保留） |
| H2a | pass；assembled-block MatPython action identity |
| H2b | pass；Matrix-free local endcap exact action identity |
| H3 | pass；exact block-LDU formal、offline 12+12 完成 |
| H4 | pass；H4a exact Sₘ 与 H4b bounded diagnostic 完成 |
| H5a | pass；direct local reference bottom/top 各 11/11 |
| H5b | controlled negative；bottom `1/11`、top `0/11` |
| H5c-H10 | not_run；H5b 数值 Gate 未过后按顺序停止 |

## 运行边界

H1 recovery checkpoint 当时没有修改 H1 solver、没有放宽阈值、没有扫描 M/角度/p-h；随后完成 H2a 与 H2b code checkpoint。ignored artifacts 保留在本地证据目录，tracked docs 只保存路径和 SHA 引用。

## H2a assembled-block action identity

| 范围 | 结果 |
|---|---|
| focused test | `src/test/test_234_task037b_hybrid_block_operator.py` |
| MPI1 / MPI2 / MPI4 | 3 passed / 每 rank 3 passed / 每 rank 3 passed |
| existing direct minimal regression | 1 passed |
| action Gate | global 与 bottom/top/modal block relative error 全部 `<=1e-11` |
| layout / pack-split | missing/extra/duplicates `0/0/0`；三项 pack/split `0` |
| H3 | 本 H2a checkpoint 当时未运行；随后已完成 exact block-LDU formal |

完整 H2a 逐 probe 数值与 H2b 汇总见 [block identity](block_operator_identity.md)。

## H2b Matrix-free local endcap exact action identity

| 范围 | 结果 |
|---|---|
| H2b-L MPI1 | `1 passed`；bottom action/recovery/RHS `3.058e-16 / 4.352e-16 / 0`，top `3.730e-16 / 4.297e-16 / 6.993e-17`；均通过 `1e-11` |
| H2a+H2b MPI1 | `5 passed`，6.04 s |
| H2a+H2b MPI2 | 每 rank `5 passed`，4.52 s |
| H2a+H2b MPI4 | 每 rank `5 passed`，9.11 s |
| 相关回归 test224/test230/test231 | `5 passed / 1 skipped`，5.89 s |
| static Gate | import、Ruff check/format-check、compileall、git diff --check 全部 pass |

H2b-G 每个 MPI 的七 probes、global/bottom/top/modal 四块合计最大 relative error
分别为 MPI1/MPI2/MPI4 的 `2.942e-16 / 2.988e-16 / 3.539e-16`，每行四块逐项均不
超过该行总体最大值，且均低于 `1e-11`；MPI1/2/4 的 pack/split bottom/top/modal
均为 `0`，mapping missing/extra/duplicates 均为 `0/0/0`。
H2b production 从构造开始使用 matrix-free local-Schur 与 matrix-free DtN action；
test-only oracle 才使用 explicit-condensed local blocks。

## H5 formal local inverse

| 项目 | 结果 |
|---|---|
| H5a exact/direct reference | bottom/top `11/11 + 11/11`；bottom/top direct max=`2.107282966996484e-12 / 2.1971754846774315e-12`，action max=`2.0973803488508764e-12 / 2.1957548735380243e-12`；factors 逐侧释放 |
| H5b worker numerical Gate | bottom `1/11`、top `0/11`；其余 `reason=-3`、`max_it=300`；最大 true residual `0.9422475005587448 / 0.9427702892133474` |
| H5 repeat | repeat solution relative error `0`；仅说明 deterministic，不说明 convergence |
| H5 implementation closure | `40 passed`；Ruff check、compileall、git diff --check pass |
| H5 formal | return `2`；`LOCAL_INVERSE_FAMILY_NEGATIVE`；完整 record 后受控停止 |
| H5 official R/T/A、field、12+12 | not_run |
| full pytest / CI | not_run；本地 docs closeout 不声称 CI |

H5a/H5b 的阶段内存、逐 RHS 表、1/2/4/8 fixed-apply 诊断和 raw evidence hash 见
[H5 local endcap evidence](local_endcap_inverse_matrix.md)。H5b 重复解一致不能抵消 true residual
远高于 `1e-8` 的数值事实。

## H3/H4 formal evidence

| 阶段 | formal/diagnostic | 关键结果 | 资源与额外边界 |
|---|---|---|---|
| H3 | `return=0`，formal/numeric/no-swap pass | outer=1；true residual global/bottom/top/modal=`2.892237294698294e-12 / 3.610918199454199e-12 / 2.0470485206121342e-12 / 9.879221339086588e-13`；offline 12+12=`12/12 + 12/12` | total `507.2017102949321 s`；peak `9.585384368896484 GiB`；factors released |
| H4a | exact Sₘ pass | outer=1；true residual global/bottom/top/modal=`2.7239301070596716e-12 / 3.982460029685523e-12 / 1.7429945983458624e-12 / 1.001248228432052e-12` | total `540.3976704040542 s`；peak `9.802722930908203 GiB`；swap=0 |
| H4b | `task037b_h4_diagnostic_complete` | outer=3、reason=-3、finite/evidence/lifecycle pass；solution/modal error=`0.004900532829746777 / 0.009905532844701982` | G-only 残差不作失败判定；H4 不要求 12+12 |

H3/H4 的完整 residual、Sₘ/G feedback、operator inventory、factor before/after 与
hash-bound artifact 见 [exact block-LDU oracle](exact_block_ldu_oracle.md)。

## V1 R1–R5 implementation 与 formal 测试收口

| 范围 | 结果 |
|---|---|
| V1 serial implementation / contract | 52 passed |
| MPI2 focused | 1 passed / 每 rank |
| MPI4 focused | 1 passed / 每 rank |
| R1–R5 formal MPI8 | 每阶段仅启动一次；raw solver record、watchdog summary、timeline、stages、stdout 均写出 |
| Ruff check | pass |
| Ruff format-check | pass |
| compileall | pass |
| git diff --check | pass |
| full pytest / CI | not_run；不声称 CI |

V1-R1 是 component action identity pass；R2、R3 和 R5 是合法 numerical negative；
R4 exact Woodbury oracle pass。R5 的 negative 是完整记录后的受控研究结论，不是 parser、
MPI ownership、资源、serialization 或 lifecycle infrastructure failure。R5 official R/T/A、
field 和 12+12 未运行；H6–H10 因 stop rule not_run。

## Review V2 focused 与 formal Gate

| 范围 | 结果 |
|---|---|
| Review V2 MPI focused | 已沿用同一 source-bound evidence：MPI1/2/4 action、Schur、pack/split、lifecycle 均通过 |
| V2-B formal MPI8 | 唯一一次 bottom approximate / top exact；contract/numeric pass，screen final 0.26797784324787316 |
| V2-T formal MPI8 | 唯一一次 top approximate / bottom exact；contract pass、合法 numerical negative，screen final 0.3518371324843258 |
| V2 double 20/100/200 | not_run_due_to_one_sided_gate |
| V2 official physics | field、R/T/A、external diffraction、12+12、Full3D comparison 全部 not_run |
| V2 source | 5b94060eae3a2ce02dd87e8a8c2075b635711346；未因 docs closeout 改变 |
| test242 serial | 3 passed，3.20 s，exit 0 |
| watchdog Ruff check/format-check/compileall | exit 0；All checks passed、1 file already formatted、compileall pass |
| compact JSON | python -m json.tool、两套 raw artifact path/SHA 核对、Markdown 相对链接核对、git diff --check 全部 pass |
| full pytest / CI | not_run；不声称 CI |

V2-T 的 formal_record_pass=true 仅说明实现、source/launch/resource authority、完整 raw
record 和安全清理均完成；它不覆盖 worker_numerical_pass=false。两次 formal 各只启动一个
parent watchdog，均 swap=0、无 orphan，且没有重跑 V2-B、没有启动 double。

## Review V3 focused 与唯一 formal Gate

V3 只在 source `c7b6aa3ddaac4dbfb9f86aab8f59801330d63a16` 上运行一次 MPI8 double
fixed-action screen；没有因结果或资源分类重跑。最终测试账本如下：

| 范围 | 实测结果 | 边界 |
|---|---|---|
| final serial test239 + test241 + test242 + test59 | 46 passed，exit 0 | focused only |
| MPI1 test239 + test241 + test242 | 13 passed / rank | tiny/action fixture，不是 PDE |
| MPI2 test239 + test241 + test242 | 13 passed / rank | tiny/action fixture，不是 PDE |
| MPI4 test239 + test241 + test242 | 13 passed / rank | pack/split/lifecycle fixture，不是 PDE |
| Ruff check | pass | 五个 V3 touched Python files |
| Ruff format-check | pass | 五个 V3 touched Python files |
| five-file py_compile | pass | syntax/static only |
| git diff --check | pass | final source checkpoint |
| formal MPI8 | 唯一一次，exit 0 | raw record、summary、timeline、stages、stdout 均写出 |
| full pytest / CI | not_run | 不声称 CI |
| test240 / additional PDE | not_run | Review V3 明确禁止 |

V3 的 callback、same-action modal Schur、direct=0/0 与 ILU=1/1、online apply count、
progressive checkpoint、release/no-swap/no-orphan 均由 raw record 保存。数值分类为 pass；
process-tree peak 超过 6 GiB 只产生独立 resource review，不改写 numerical disposition。官方
field recovery、R/T/A、A_volume、diffraction orders、12+12 和 Full3D comparison 全部
not_run。

## Review V4 focused 与唯一 formal run

V4 使用 source `eb1fc88483dd4d9cb5eabb071f8af0e87f91ba49`，只启动一次 MPI8 full solve；不因
bottom local-block Gate miss 重跑。测试和静态结果如下：

| 范围 | 结果 | 语义 |
|---|---|---|
| focused serial | `18 passed` | test239/test241/test242/test235/test243 的最终节点 |
| MPI2 key action/lifecycle | `5 passed` per rank | tiny fixture，不是 PDE |
| MPI4 key action/lifecycle | `5 passed` per rank | tiny fixture，不是 PDE |
| Ruff check | pass | 五个 touched Python files |
| Ruff format-check | pass | 五个 touched Python files |
| compileall | pass | 五个 touched Python files |
| git diff --check | pass | source checkpoint |
| independent checker | exit 0 | evidence integrity pass only；不是 full qualification pass |
| full pytest / CI | `not_run` | 不声称 CI |
| test240 / additional PDE | `not_run` | Review V4 边界外 |

五个 touched Python files 指 `run_task032_phase6_augmented.py`、
`run_task033_memory_watchdog.py`、`hybrid_fem_modal_block_ldu.py`、
`task037b_v4_full_qualification_checker.py` 与 `test_243_task037b_v4_full_qualification.py`。
此前全仓 format-check 对 257 个历史无关文件的发现不属于本轮 Gate，也没有改动那些文件。

V4 数值失败后 official recovery/field/R/T/A/orders/12+12/Full3D 均 not_run；checker
`evidence_integrity_pass=true`、`candidate_evidence_pass=true`、`authority_bindings_pass=true`，
但 `pass=false`，唯一 failure 为 `h1_authority_payload_gap`。完整数值、资源、lifecycle 与
artifact hash 见 [V4 full qualification](full_mpi8_qualification.md) 和
[V4 compact record](../../../benchmarks/cases/101_hybrid_iterative_block_solver/records/task037b_v4_mpi8_full_qualification_v1.json)。

## Review V5 测试与 postprocessor 记录

| 阶段 | 结果 | 范围 |
|---|---|---|
| preformal serial | `29 passed` | test241–test244 focused |
| preformal MPI2 | `5 passed per rank` | 指定 action/lifecycle 节点 |
| preformal MPI4 | `5 passed per rank` | 指定 action/lifecycle 节点 |
| preformal static | pass | touched-file Ruff check/format-check、compileall、diff-check |
| postprocessor correction | `test244: 9 passed`；test59/test74相关节点 `4 passed` | 只读 raw/evaluator 合同修正 |
| postprocessor static | pass | 两文件 Ruff check/format-check、compileall、diff-check |
| full pytest / CI | `not_run` | 不声称 CI 或全仓通过 |

postprocessor 是对同一 raw solver record 的纯函数分类修正，不是第二次数值运行；没有
重跑 MPI8、没有修改 raw artifacts，也没有开展 Full3D、direct export 或 physics postprocess。

## M1–M10 结项 focused Gate

以下是已经实际运行并在各阶段 turn/record 中保留的 focused Gate；它不是 full repository 统计。每轮对应的 source、raw summary 和 checker SHA 见 [closeout compact record](../../../benchmarks/cases/101_hybrid_iterative_block_solver/records/task037b_v6_memory_optimization_closeout_v1.json)。

| 阶段 | serial focused | MPI focused | static Gate | 独立 offline checker |
|---|---|---|---|---|
| V6 preformal | `test243/test244/test245` 合计 `29 passed`；test243 `12 passed`；test246 `12 passed` | 指定 action/lifecycle `5 passed/rank`，MPI2/MPI4 | touched Ruff check/format、compileall、diff-check pass | final V6 checker `pass=true` |
| M1 | test243/test244/test245；recorded pass，exact count not consolidated | cleanup lifecycle node；recorded MPI2 pass，exact per-rank count not consolidated | recorded static pass，exact command output not consolidated | `v6_m1_offline...` pass；exit 0 |
| M2 | test243/test244/test245；recorded pass，exact count not consolidated | recovery cleanup lifecycle node；recorded MPI2 pass，exact per-rank count not consolidated | recorded static pass，exact command output not consolidated | `v6_m2_offline...` pass；exit 0 |
| M3 | test243/test244/test245；recorded pass，exact count not consolidated | canonical ordering/lifecycle node；recorded MPI2 pass，exact per-rank count not consolidated | recorded static pass，exact command output not consolidated | `v6_m3_offline...` pass；exit 0 |
| M4 | test227/test245；recorded serial pass，exact count not consolidated | owner-local artifact/lifecycle node；recorded MPI2 pass，exact per-rank count not consolidated | recorded static pass，exact command output not consolidated | `v6_m4_offline...` pass；exit 0 |
| M5 | test226/test227；recorded serial pass，exact count not consolidated | test226/test227；recorded MPI2 pass，exact per-rank count not consolidated | recorded static pass，exact command output not consolidated | `v6_m5_offline...` pass；exit 0 |
| M6 | test226/test227；recorded serial pass，exact count not consolidated | test226/test227；recorded MPI2 pass，exact per-rank count not consolidated | recorded static pass，exact command output not consolidated | `v6_m6_offline...` pass；exit 0 |
| M7 | test226/test227；recorded serial pass，exact count not consolidated | test226/test227；recorded MPI2 pass，exact per-rank count not consolidated | recorded static pass，exact command output not consolidated | `v6_m7_offline...` pass；exit 0 |
| M8 | test226/test227；recorded serial pass，exact count not consolidated | test226/test227；recorded MPI2 pass，exact per-rank count not consolidated | recorded static pass，exact command output not consolidated | `v6_m8_offline...` pass；exit 0 |
| M9 | test226/test227/test228；recorded serial pass，exact count not consolidated | 同三文件；recorded MPI2 pass，exact per-rank count not consolidated | recorded static pass，exact command output not consolidated | `v6_m9_offline...` pass；exit 0 |
| M10 | test245（含 pre-canonical lifecycle contract）；recorded serial pass，exact count not consolidated | test245；recorded MPI2 pass，exact per-rank count not consolidated | recorded static pass，exact command output not consolidated | `v6_m10_offline...` pass；exit 0 |

M1–M10 的 focused tests 只证明各自局部生命周期/packet/API 合同和 source/static Gate；online numerical/physics 与独立 checker 结论分别由对应 raw artifact 记录。M9 的 `-0.40625 MiB` 负收益没有被测试或文档改写成通过。

## 未运行项

| 项目 | 状态 |
|---|---|
| full repository pytest | `not_run` |
| CI/GitHub Actions | `not_run`；不声称 CI 通过 |
| MPI reduction | `not_run`；MPI8 已满足严格 6 GiB |
| M11 implementation/formal | `not_run`；只完成 read-only feasibility stop |
| 新 PDE、MPI4/8 candidate 或 checker retry | `not_run` |
