# Test and evidence summary

## 本轮 docs-only

本轮只修订 evidence 文档和 checkpoint v2；没有重跑 pytest、MPI、PDE、
QEP、MUMPS、FGMRES、full suite、Ruff 或 compileall，没有启动新 heavy。
以下为此前最终代码阶段已审核的 focused evidence，不把主控审核代替为
测试结果。

## P1 sampled exact-side

| 命令/范围 | 结果 |
|---|---|
| python -m pytest -q src/test/test_task037c_exact_one_cell_traction.py -k sampled_direct_relift_contract | 6 passed, 16 deselected |
| python -m pytest -q src/test/test_343_task041_exact_side_consumer.py -k 'sampled_contract_requires_selected_mode_packet_manifest or fresh_sampled_contract_is_bound_to_current_manifest or run_task041_consumer_full_mock_keeps_release_and_authority_evidence' | 6 passed, 35 deselected |
| real P2 serial: test_real_p2_double_floquet_endpoint_and_local_interface_identity | 1 passed |
| real P2 MPI2: mpiexec -n 2 同一 node | 每 rank 1 passed |
| compileall / diff-check | pass |
| Ruff | 仅历史 baseline，无 fix |

P1 证明 fixed 8-column sampled direct relift、full operator transfer 和
identity mapping；没有缩小最终 operator，也没有改变物理或 solver identity。

## P2 sparse telemetry 与 terminal race

| 命令/范围 | 结果 |
|---|---|
| python -m pytest -q src/test/test_344_task041_public_supervisor.py | 42 passed |
| python -m pytest -q src/test/test_263_task038_launcher_contract.py::test_task039_default_sampler_requests_smaps_without_changing_fake_sampler | 1 passed |
| TemporaryDirectory + supervisor._run_phase + real mpiexec -n 2 teardown smoke | returncode=0；process_group_gone=true；sample_count=6；swap=0；smaps_complete=1 |
| compileall 两个 production 文件及 test_344 | pass |
| diff-check | pass |
| Ruff | 无新增诊断；仅历史 baseline |

smoke 使用资格化环境、Barrier/sleep child 和真实 process-group teardown，
不是 PDE。途中 fake probe 的缺目录和参数名仅是 implementation harness
纠正，不构成数值或正式运行证据。

## P3 lifecycle 与 modal condition

| 命令/范围 | 结果 |
|---|---|
| test_344 selected focused nodes | 4 passed，0.59 s |
| test_241 selected focused nodes | 3 passed，1.42 s |
| packet lifecycle focused node | 1 passed，1.59 s |
| compileall / diff-check | pass |
| Ruff | 15 项历史 baseline，无 fix |

P3 的 packet consumer cleanup、terminal authority transition 和 singular
value condition path 均有 targeted evidence；没有以这些测试推断 heavy
性能改善。

## ABI、未覆盖与证据边界

上述测试均使用 native complex128/int32 栈，五个数学线程为1。M800/M1200
正式 roots 的 residual、physics、resource 和 lifecycle 另由 raw
summary/marker/telemetry 记录；本轮不复制大型对象。

没有 post-change QEP performance isolation，没有 M1600/2 nm formal，也没有
5 nm MPI1 full equivalence。M1200 已运行一次受控 consumer continuation，
其 own physics negative；不能写成“本轮未运行”。

M800/M1200 own physics negative 不被测试或 scalar comparison 改写为 pass；
workflow peak=max(producer,consumer)，producer 退出后才启动 consumer。
当前 M1200 candidate 采用更严格的 224/256 GiB workflow envelope 和
21600 s consumer phase cap；它不替换 task.md 原 1.50 TiB 历史规划。
