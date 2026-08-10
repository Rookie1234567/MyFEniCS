# Task037-extra H1R3.0：p6/h10 MPI1 warm-repeat 结果

本 outcome 记录 Review V5 授权的唯一一次 H1R3.0 正式运行。warm-repeat 是连续
重复调用同一个全空间局部 action，用来观察数值、内存和临时缓冲区是否稳定；它
不是 PDE 求解器，也不产生物理场或 R/T/A 结果。

## 1. 正式结论

| 阶段 | 状态 | 说明 |
|---|---|---|
| H1R3.0 | GATE_FAILED | candidate inventory evidence closure failure |
| watchdog | exit 1 / worker_failed | worker qualification 未通过 |
| checker | exit 1 / gate_failed | problems 为 worker.status_pass、worker.fresh_pass、watchdog.status、watchdog.return_code |
| controlled stop | null | 不是 timeout、内存或 swap controlled stop |
| H1R3.1 | not_run_by_gate | H1R3.0 未通过 |
| H1R3.2 | not_run_by_gate | H1R3.1 未运行 |
| H2/H3/H4/PDE/DtN/RTA | locked / not_run | 不在本轮范围 |
| G2 | G2_FAIL | 冻结结论 |
| G3 additive LOR-HX | prohibited | 不重开、不扫描 |
| old G4 sweep | prohibited | 保持禁止 |
| old H1.2 | CONTROLLED_STOP_TIMEOUT / NOT_QUALIFIED | 历史负证据保持 |
| ordinary default | unchanged | 没有改变普通默认路径 |

数值、时间、payload 和资源子 Gate 都通过，但不能据此改写 overall H1R3.0
状态为 PASS。

## 2. 根因与边界

candidate_action_audit 缺少当前 H1R3.0 qualification evaluator 要求的两个精确 inventory 字段：

| 缺失字段 | 独立 evaluator 结果 |
|---|---|
| cell_schur_matrix_nnz | false |
| slab_matrix_nnz | false |

checker 没有用默认 0 填补缺失字段，而是 fail-closed 拒绝。raw 中其他相关审计
明确记录了：

| 项目 | raw 值 |
|---|---|
| global matrix | false |
| global constraint matrix | false |
| global condensed Schur | false |
| dense cell tensor per apply | false |
| retained dense cell tensor | 0 |
| factor | 0 |
| KSP | false |
| DtN | false |

这些字段不能替代缺失的 cell_schur_matrix_nnz 和 slab_matrix_nnz，也不能据此
把整体状态写成通过。本轮按 Review V5 hard stop 保留真实证据，等待新的 review；
不在本轮修复后重跑。

## 3. 身份、环境与精确命令

| 项目 | 值 |
|---|---|
| branch | codex/20260806-task37-iterative-extra-development |
| source / implementation SHA | 003b8fa185b59bb424e60331d336d2d976d0563f |
| source start/end | 同一 SHA，均 clean |
| source / MPI / source count | seed_17037 / MPI1 / 1 source |
| frozen action | p6 / h10 / reference 1 / candidate 12 |
| runtime marker | _MYFENICS_WSL_QUALIFIED_ACTIVATION=1 |
| Python | /home/shenjh/Projects/MyFEniCS-Surrogate/.venv/bin/python |
| PETSc | complex128 / int32 |
| threads | OMP=1 / OPENBLAS=1 / MKL=1 / NUMEXPR=1 |

Python 路径是当前 qualified shared target；它与仓库 .venv 解析到同一 qualified
环境，不是 Windows/ABI 混用。

正式 watchdog 命令（本轮唯一一次）：

~~~bash
source scripts/activate_myfenics_wsl.sh
python -m benchmarks.run_task037_extra_candidate_h h1r3-warm-watchdog --run-dir benchmarks/artifacts/task037_extra_h1r3_warm_repeat_v5_003b8fa
~~~

compact checker 命令：

~~~bash
source scripts/activate_myfenics_wsl.sh
python -m benchmarks.run_task037_extra_candidate_h h1r3-warm-check --run-dir benchmarks/artifacts/task037_extra_h1r3_warm_repeat_v5_003b8fa --output benchmarks/cases/101_task37_extra_development/records/h1r3_warm_repeat.json
~~~

watchdog 与 checker 均只执行一次；没有原样重跑。

## 4. 实测 action、时间和确定性

| 项目 | 值 / 结论 |
|---|---:|
| global rows / constraints | 173802 / 9210 |
| reference apply | 1.1416714489459991 s |
| apply 5--12 median | 1.1308611669810489 s |
| median 限值 | 1.494291376147885 s，PASS |
| first error | 2.7326039504560278e-17 <= 1e-11，PASS |
| last error | 2.7326039504560278e-17 <= 1e-11，PASS |
| finite / deterministic / hash identity | true / true / true |
| output hash | f768296b487cf219ec67768ea17f3a184b27db1f98b96a34853df026926938d5 |

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

## 5. Payload、资源与 canonical

| 项目 | 值 / 结论 |
|---|---:|
| retained payload local/sum/max | 6151104 / 6151104 / 6151104 B |
| payload components | 闭合，12 次完全稳定 |
| packed temporary | 3556224 B，12 次完全稳定 |
| 每次 telemetry RSS/PSS/USS | 335015936 / 315051008 / 300912640 B |
| steady RSS span | 0 B |
| completed process-tree peak | 335233024 B <= 483183820 B，PASS |
| 用户 decimal <2,000,000,000 B | 335233024 B，PASS |
| swap | 0，PASS |
| completion / wall | 26.716238772962242 / 26.72631202498451 s |
| canonical export | 一次，且在 numerical Gate 后 |
| canonical packets / duplicates | 164592 / 0 |
| packet closure | 164592 = 173802 - 9210 |

用户提出的 decimal <2,000,000,000 B 目标也通过（实测 peak 335233024 B）；V5 的
0.45 GiB（483183820 B）是更严格的 Review authority。两个门槛分别记录，不混写。

Payload component 明细为：coefficient_function_local_array_bytes=2780832、
output_vector_local_storage_bytes=2780832、conjugated_master_coefficients_bytes=147360、
constraint_work_bytes=147360、owned_slave_work_bytes=147360；索引组件分别为
flat_slave_indices_bytes=36840、master_indices_bytes=36840、
owned_slave_indices_bytes=36840、slave_indices_bytes=36840，packed constants 为
0。总和为 6151104 B。

manifest：
canonical/seed_17037/candidate_manifest.json

## 6. Evidence 索引

Raw ignored directory：

/home/shenjh/Projects/MyFEniCSx_task37_extra/benchmarks/artifacts/task037_extra_h1r3_warm_repeat_v5_003b8fa

| raw file | SHA256 |
|---|---|
| run_summary.json | df3faae5bd9cd02db3b8a779d46183a49a86ba65fa6cf81bae6daaa6c5848617 |
| watchdog_summary.json | 9c8bd0531ca268fe7c867b327aa6abcdf47ee371ba207da0e09193cc423eb729 |
| watchdog_timeline.jsonl | e31961dd1678334e357f10555733378002a7d02b76f977c4e75cc3832aacd6cd |
| apply_telemetry.jsonl | 32a6eb59553933ec390ae58a37dba3b82f7c78810a4fd14b7b14dbefc5a551eb |
| worker_stdout.txt | 5ebdd5d7d0feb7430dce679d9e5dbdd37343d59003d1d6afe53def73e727ead8 |
| canonical/seed_17037/candidate_manifest.json | 279bf1c2a09608dbe4a0843bb8b745ee5053cd64fef11f32c31b3a3984a0e1bc |
| canonical/seed_17037/candidate_rank0.jsonl | 5e49562a9501f6921b452db9c7afe297b644f7fdb8e400879abf426fbc9d526a |

Tracked compact record：
[h1r3_warm_repeat.json](../../../benchmarks/cases/101_task37_extra_development/records/h1r3_warm_repeat.json)

| compact evidence | 值 |
|---|---|
| record byte SHA256 | 88bcd9461f8bc8cc961b481c588d1c2c56f5b2d50b60ae097be27a24874d9745 |
| embedded evidence_sha256 | a6ee19851a9211c4cdf6196b2fb240b2b7b99b4b5f926a25274f1078b3c514d7 |
| compact status | gate_failed |
| compact problems | worker.status_pass、worker.fresh_pass、watchdog.status、watchdog.return_code |

## 7. 测试与后续边界

| 验证 | 结果 |
|---|---|
| test283 | 19 passed |
| 六文件 focused suite（276/277/280/281/282/283） | 55 passed |
| compileall | 通过 |
| git diff --check | 通过 |
| Ruff | unavailable，未安装 |

普通 sandbox 的 test277 MPI probe 曾受 PMIx listener 限制；在授权的 qualified
环境中用同一测试命令重跑并通过。这不是 CI 结果。

未运行 H1R3.1、H1R3.2、H2、H3、H4、PDE、DtN、official field、RTA。正式运行开始后
未再修改 runner/test/compact/raw；正式运行使用已推送且 clean 的 003b8fa。下一步必须
等待新的 review；不得把本次已通过的数值子 Gate 推广为 H1R3.0 overall PASS。
因此无 H1R3.1 资格，也无 H2/H3 资格；H2/H3/H4 仍 locked。

详见 consolidated [response_v5.md](../response_v5.md)；冻结的 H1R2 authority
[response_v4.md](../response_v4.md) 保持不变。
