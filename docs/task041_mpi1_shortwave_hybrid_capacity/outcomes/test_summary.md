# Test and evidence summary

## H4 当前结果证据与边界

H2/H3 的正式 raw comparison 已由 frozen comparator 独立重算；本轮 H4 不重跑
PDE、MPI、producer、QEP 或 full repository pytest。H3 comparator 命令在 native
环境退出 `1`，但 `numerical_pass=true`、`comparison_contract_pass=true`；exit1
来自 candidate public supervisor/resource evidence 缺失，不是数值失败。原始结果和
`TASK041_SIDE_BALH_NUMERICAL_OR_RESOURCE_FAIL` 分类保持不变。

| 证据 | 结果与绑定 |
|---|---|
| H2 13.5 nm comparison | `TASK041_SIDE_BALH_COMPARISON_PASS`；80 channels 全行保留；artifact SHA=`c8d3c7bf259d8d78a0b8d1152f7184216156824bf764c8366604fb72d374387d` |
| H3 5 nm comparison | numerical/comparison contract PASS；600 channels、4 canonical role 和 8 checkpoint shard 均有 hash-bound raw evidence；comparison SHA=`7c3838fe565c10fac0b880b0fc2d7dce99f8cfcfef88d56e4f820df1f2f6a969` |
| H3 resource/exit | consumer resource false；public parent/summary 缺失，orphan terminal row false，TERM/KILL 与 notification failure 如实保留；最终分类 `RESOURCE_COMPARISON_INCONCLUSIVE` |
| H4 文件 | [中心报告](side_balh_transfer_v1.md)、[compact record](records/task041_side_balh_transfer_v1.json)、[completion audit](../../../results/task041_side_balh_component_audit/h3h_final_20260914_51694bbc/h3_completion_audit.json) |
| H4 未运行 | Full3D secondary、新 producer/QEP、全仓 pytest、CI；只做文档/JSON合同检查 |

H3 candidate 的 worker 数值结果和内部 cleanup 仍保留；不能以缺失的 public
summary 抹掉数值结果，也不能用 worker-local `rss_drop` 补成 MPI 全树资源通过。

## H3f-B 已审核的 focused evidence

| 范围 | 结果与绑定 |
|---|---|
| focused tests | `96 passed`；最终 fixture `61 passed`；MPI2 每 rank `1 passed` |
| 静态检查 | scoped Ruff、compileall、`git diff --check` 通过 |
| 证据绑定 | [`h3f_b_validation_summary.json`](../../../results/task041_side_balh_component_audit/h3f_b_validation_summary.json)、[`h3f_b_result_index.json`](../../../results/task041_side_balh_component_audit/h3f_b_result_index.json)；index 中 11 个 `source_files` hash 与最终源码一致 |

这些是最终源码上的轻量/接口证据，不替代 H2/H3 正式 PDE；full repository pytest、CI 和
未运行的 Full3D secondary 仍明确为 `not_run`。

## H4 文档检查

| 命令 | 结果与原始日志 |
|---|---|
| `source .venv/bin/activate_myfenics_native.sh && python -c 'import json,sys,numpy as np; from mpi4py import MPI; from petsc4py import PETSc; import basix,dolfinx,mpi4py,petsc4py; print(json.dumps({"marker": __import__("os").environ["MYFENICS_NATIVE_COMPLEX_ENV"], "executable": sys.executable, "python": sys.version.split()[0], "numpy": np.__version__, "mpi_size": MPI.COMM_WORLD.size, "petsc_scalar": str(np.dtype(PETSc.ScalarType)), "petsc_int": str(np.dtype(PETSc.IntType)), "basix": basix.__file__, "dolfinx": dolfinx.__file__, "mpi4py": mpi4py.__file__, "petsc4py": petsc4py.__file__}, sort_keys=True))'` | exit `0`；[`h4_doc_abi_preflight.log`](../../../results/task041_side_balh_component_audit/h4_doc_abi_preflight.log) |
| `source .venv/bin/activate_myfenics_native.sh && python -m pytest -q src/test/test_26_documentation_contract.py src/test/test_development_model_registry_contract.py` | `15 passed`，exit `0`；[`h4_document_contracts_pytest_final.log`](../../../results/task041_side_balh_component_audit/h4_document_contracts_pytest_final.log) |

## 历史 response_v1 docs-only

历史 response_v1 阶段只修订 evidence 文档和 checkpoint v2；没有重跑 pytest、MPI、PDE、
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
