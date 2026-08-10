# Task037-extra Response V5：H1R3.0 正式结果

本 response 是 Review V5 的 consolidated authority。它只固化本轮实际运行的
H1R3.0 结果，不授权后续阶段，也不改写冻结的
[response_v4.md](response_v4.md) H1R2 authority。

## 1. 总结结论

| 阶段 | 状态 | 解释 |
|---|---|---|
| H0 | H0_PASS | capability-only |
| H1R.0 | PASS | progress markers |
| H1R.1 | H1R.1_PASS | tiny action evidence |
| H1R2 | H1R2_PASS | p6/h10、MPI1、single-source action-only |
| H1R3.0 | GATE_FAILED | candidate inventory evidence closure failure |
| H1R3.1 | not_run_by_gate | H1R3.0 未通过 |
| H1R3.2 | not_run_by_gate | H1R3.1 未运行 |
| H2/H3/H4 | locked / not_run | 未授权、未运行 |
| G2 | G2_FAIL | 冻结 |
| G3 additive LOR-HX | prohibited | 冻结 |
| old G4 sweep | prohibited | 冻结 |
| old H1.2 | CONTROLLED_STOP_TIMEOUT / NOT_QUALIFIED | 历史负证据 |
| ordinary default | unchanged | 普通默认路径未改变 |

本次 watchdog exit 1、status=worker_failed；compact checker exit 1、
status=gate_failed。controlled_stop=null，worker 没有因 timeout、内存或 swap
被终止。数值、重复确定性、时间、payload 和资源子 Gate 均通过，但 overall
H1R3.0 不是 PASS。

## 2. 唯一失败根因

candidate_action_audit 没有写出当前 H1R3.0 qualification evaluator 要求的两个精确 inventory 字段：

| 字段 | 独立 evaluator |
|---|---|
| cell_schur_matrix_nnz | false |
| slab_matrix_nnz | false |

checker 的 fail-closed 语义拒绝了缺失字段，没有把缺失值当成 0。raw 中已经明确
写出的相邻审计字段包括 global matrix=false、global constraint matrix=false、
global condensed Schur=false、dense cell tensor per apply=false、retained dense
cell tensor=0、factor=0、KSP=false、DtN=false；这些事实不能替代上述两个缺失字段，
也不能把 overall status 改写为通过。

根据 Review V5 hard stop，本轮保留真实 raw 和 compact evidence，停止在
H1R3.0，等待新的 review；没有修复后重跑。

## 3. 身份、范围和命令

| 项目 | 值 |
|---|---|
| branch | codex/20260806-task37-iterative-extra-development |
| source / implementation SHA | 003b8fa185b59bb424e60331d336d2d976d0563f |
| source start/end | 同一 SHA，均 clean |
| source | seed_17037 |
| case | p6 / h10 / MPI1 |
| applies | reference=1、candidate=12 |
| runtime marker | _MYFENICS_WSL_QUALIFIED_ACTIVATION=1 |
| Python | /home/shenjh/Projects/MyFEniCS-Surrogate/.venv/bin/python |
| PETSc | complex128 / int32 |
| threads | OMP=1、OPENBLAS=1、MKL=1、NUMEXPR=1 |

Python 是当前 qualified shared target；仓库 .venv 解析到同一 qualified 环境，
不存在 Windows/ABI 混用。

正式 watchdog（唯一一次）：

~~~bash
source scripts/activate_myfenics_wsl.sh
python -m benchmarks.run_task037_extra_candidate_h h1r3-warm-watchdog --run-dir benchmarks/artifacts/task037_extra_h1r3_warm_repeat_v5_003b8fa
~~~

正式 checker（唯一一次）：

~~~bash
source scripts/activate_myfenics_wsl.sh
python -m benchmarks.run_task037_extra_candidate_h h1r3-warm-check --run-dir benchmarks/artifacts/task037_extra_h1r3_warm_repeat_v5_003b8fa --output benchmarks/cases/101_task37_extra_development/records/h1r3_warm_repeat.json
~~~

raw ignored directory：

/home/shenjh/Projects/MyFEniCSx_task37_extra/benchmarks/artifacts/task037_extra_h1r3_warm_repeat_v5_003b8fa

## 4. H1R3.0 实测结果

| 指标 | 实测值 / Gate |
|---|---:|
| global rows / constraints | 173802 / 9210 |
| reference apply | 1.1416714489459991 s |
| apply 5--12 median | 1.1308611669810489 s <= 1.494291376147885 s，PASS |
| first / last relative error | 2.7326039504560278e-17 / 2.7326039504560278e-17，PASS |
| finite / deterministic / output hash identity | true / true / true |
| output hash | f768296b487cf219ec67768ea17f3a184b27db1f98b96a34853df026926938d5 |
| retained payload local/sum/max | 6151104 / 6151104 / 6151104 B |
| payload components | 闭合、12 次稳定 |
| packed temporary | 3556224 B，12 次稳定 |
| 每次 RSS/PSS/USS | 335015936 / 315051008 / 300912640 B |
| steady RSS span | 0 B |
| completed process-tree peak | 335233024 B <= 483183820 B，PASS |
| 用户 decimal <2,000,000,000 B | 335233024 B，PASS |
| swap | 0，PASS |
| completion / wall | 26.716238772962242 / 26.72631202498451 s |
| canonical export | 一次，数值 Gate 后 |
| canonical packets / duplicates | 164592 / 0 |
| packet closure | 164592 = 173802 - 9210 |

用户提出的 decimal <2,000,000,000 B 目标也通过（实测 peak 335233024 B）；V5 的
0.45 GiB（483183820 B）是更严格的 Review authority。两个门槛分别记录，不混写。

candidate apply times：

| apply | seconds |
|---:|---:|
| 1 | 1.1630005359183997 |
| 2 | 1.1006533459294587 |
| 3 | 1.1194514660164714 |
| 4 | 1.1414172009099275 |
| 5 | 1.125559502048418 |
| 6 | 1.1669558121357113 |
| 7 | 1.10454658488743 |
| 8 | 1.107223390135914 |
| 9 | 1.159877564990893 |
| 10 | 1.1330805679317564 |
| 11 | 1.1286417660303414 |
| 12 | 1.1849818609189242 |

retained payload components 为 coefficient_function_local_array_bytes=2780832、
output_vector_local_storage_bytes=2780832、conjugated_master_coefficients_bytes=147360、
constraint_work_bytes=147360、owned_slave_work_bytes=147360；flat_slave_indices、
master_indices、owned_slave_indices、slave_indices 各为 36840 B，packed constants
为 0。总和为 6151104 B。

## 5. Evidence 与 compact record

| raw file | SHA256 |
|---|---|
| run_summary.json | df3faae5bd9cd02db3b8a779d46183a49a86ba65fa6cf81bae6daaa6c5848617 |
| watchdog_summary.json | 9c8bd0531ca268fe7c867b327aa6abcdf47ee371ba207da0e09193cc423eb729 |
| watchdog_timeline.jsonl | e31961dd1678334e357f10555733378002a7d02b76f977c4e75cc3832aacd6cd |
| apply_telemetry.jsonl | 32a6eb59553933ec390ae58a37dba3b82f7c78810a4fd14b7b14dbefc5a551eb |
| worker_stdout.txt | 5ebdd5d7d0feb7430dce679d9e5dbdd37343d59003d1d6afe53def73e727ead8 |
| canonical/seed_17037/candidate_manifest.json | 279bf1c2a09608dbe4a0843bb8b745ee5053cd64fef11f32c31b3a3984a0e1bc |
| canonical/seed_17037/candidate_rank0.jsonl | 5e49562a9501f6921b452db9c7afe297b644f7fdb8e400879abf426fbc9d526a |

compact record：
[h1r3_warm_repeat.json](../../benchmarks/cases/101_task37_extra_development/records/h1r3_warm_repeat.json)

| compact item | 值 |
|---|---|
| record byte SHA256 | 88bcd9461f8bc8cc961b481c588d1c2c56f5b2d50b60ae097be27a24874d9745 |
| embedded evidence_sha256 | a6ee19851a9211c4cdf6196b2fb240b2b7b99b4b5f926a25274f1078b3c514d7 |
| compact status | gate_failed |
| compact problems | worker.status_pass、worker.fresh_pass、watchdog.status、watchdog.return_code |

## 6. 验证与未运行项

| 验证 | 结果 |
|---|---|
| test283 | 19 passed |
| 六文件 focused suite（276/277/280/281/282/283） | 55 passed |
| compileall | 通过 |
| git diff --check | 通过 |
| Ruff | unavailable，未安装 |

普通 sandbox 的 test277 MPI probe 曾因 PMIx listener 被阻断；授权 qualified 环境
用相同 focused suite 重跑后通过。这不是 CI pass。

本轮未运行 H1R3.1、H1R3.2、H2、H3、H4、PDE、DtN、official field 或 RTA。正式运行开始后
未再修改 runner/test/compact/raw；正式运行使用已推送且 clean 的 003b8fa。compact record
由本次正式 checker 创建并保留。因此无 H1R3.1 资格，也无 H2/H3 资格；H1R3.1/H1R3.2
继续由 Gate 阻止，H2/H3/H4 继续 locked。

H1R3.0 outcome 见
[h1r3_warm_repeat.md](outcomes/h1r3_warm_repeat.md)。G2_FAIL、G3 prohibited、
old G4 prohibited、old H1.2 historical stop 和 ordinary default unchanged 均保持。
