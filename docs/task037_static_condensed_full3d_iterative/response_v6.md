# Task037 V6 E0 Formal Closeout

## 1. 决策总览

这次 E0 是一个“只检查组件动作”的正式 Gate：它只验证 80 个端口模态是否能把矩阵自由动作与显式参考动作对齐，不执行正式场求解。矩阵自由的意思是只保存“给定向量后如何作用”的计算方式，而不是把完整大矩阵存下来。

| 项目 | 结果 | 边界 |
|---|---|---|
| V6-E0 MPI1 formal | MATRIX_FREE_DTN_FORMAL_80MODE_GATE_FAILED | 在 probe audit 产生前发生实现异常 |
| Worker | exit 1 | PETSc Error 56 |
| Watchdog 外层 | exit 2，task037_e0_matrix_free_dtn_gate_not_pass | 资格检查失败 |
| MPI2/MPI4 | not_run | E0 失败后的硬停止 |
| E1–E5 | not_run | E0 失败后的硬停止 |
| E6 | completed_closeout | 两份结项文件完成；publication carrier SHA 与 push 后 clean 由外部交付报告提供 |
| Candidate E | not_run | 不产生容量结论 |

Selective merge 建议为 `do_not_merge / not_qualified`：E0 implementation formal Gate 失败，轻量 E0 专属 8/8 只属于 research evidence，不能被误读为通用路径合入资格。

本次不是科学容量负结果，也不是 M120 coarse 无容量结论。它是 V6 规定的 E0 implementation failure：程序还没有生成可用于科学判断的 probe audit，就被 PETSc 对 Python 类型矩阵的统计调用中止。

## 2. 停止链

1. 测试身份为 fbefca0250980a790eba3d464ad37b86d2d02abf，分支、upstream 和工作树在运行前一致且 clean。
2. qualified activation、PETSc complex128/int32、authority hash 和 MPI1 范围均通过。
3. 80 个模态已经准备完成：top/bottom 为 40/40，active rows 为 51192，有限元 DoFs 为 173802。
4. 在 stage4_dtn_port_assembly_and_solve 完成后，通用 summary 路径对 action-only 的 MatPython 对象调用了 _petsc_matrix_stats(system_A)。
5. Mat.getInfo() 对该对象不支持，抛出 PETSc Error 56；probe audit、run summary 和完整 E0 identity 没有产生。
6. Worker exit 1，watchdog exit 2；按 V6 hard stop 冻结 MPI2/MPI4 和 E1–E5。

## 3. E0 implementation checkpoint

checkpoint commit 为 fbefca0250980a790eba3d464ad37b86d2d02abf，提交了以下 8 个文件：

| 文件 | 作用 |
|---|---|
| benchmarks/run_task033_full3d_watchdog.py | E0 flag、scope、worker sentinel、parent/worker provenance |
| src/solvers/common_3d_case_flow.py | 两个 probe bool 和四个 summary 字段透传 |
| src/solvers/condensed_dtn.py | MatrixFreeDtnProbe carrier、双 sink、audit 生命周期 |
| src/solvers/dtn_port_3d.py | 80-mode component-only 组装与 primary/oracle 路径 |
| src/solvers/solve_maxwell_3d_stage_4b_block_grating.py | public wrapper 布线 |
| src/test/test_219_task037_external_solver_runtime.py | wrapper/public bool 转发与默认关闭 |
| src/test/test_230_task037_dtn_direct_blocks.py | synthetic probe 核心测试 |
| src/test/test_249_task037_e0_wiring.py | E0 qualification、scope 和 parent→worker 测试 |

轻量证据按已发生事实记录如下：

| 检查 | 结果 |
|---|---|
| E0 专属 test219 + test230 + test249 | 8/8 passed |
| Ruff check | pass |
| Ruff format check | pass |
| compileall | pass |
| git diff --check | pass |
| 额外 legacy test217 | 11 passed / 2 failed |

test217 的两项失败来自其既有 SimpleNamespace fixture 缺少旧 worker 已读取的 task037_m2c_never_materialized 字段。这是透明保留的 legacy fixture debt，不归因于 E0 专属测试，也没有为绿灯修改 fixture、删除测试或重跑。

## 4. Formal 命令与 ABI

唯一 formal 尝试是 MPI1；没有启动 MPI2、MPI4 或第二个副本。

~~~text
python -m benchmarks.run_task033_full3d_watchdog --degree 6 --h-nm 10 --polarization-kind s --run-kind full-solve --mpi-size 1 --profile default --stage4-full3d-assembly-backend assembly_time_static_condensed --task035c-p6-h10-gate --task035c-p6-preflight-authority benchmarks/cases/095_high_order_local_hp_resource_envelope/records/global_hexa_p1_p6_h10_p6_assembly_time_condensed_independent_mpi8.json --task035c-p6-preflight-sha256 96ac3949efc236393d4c2dbc6e1fa334ad5ccb0e9796bdeba13fbe0515577dd8 --verified-clean-sha fbefca0250980a790eba3d464ad37b86d2d02abf --task037-e0-matrix-free-dtn-gate --poll-interval 0.25 --warning-gib 10 --terminate-gib 14 --timeout-seconds 3600 --run-dir benchmarks/artifacts/task037/e0_v6_matrix_free_dtn_fbefca02/mpi1
~~~

| 项目 | 实测值 |
|---|---|
| Activation | _MYFENICS_WSL_QUALIFIED_ACTIVATION=1 |
| Python | /home/Projects/MyFEniCS/.venv/bin/python |
| PETSc | ScalarType complex128，IntType int32 |
| MPI | 1 |
| Authority SHA256 | 96ac3949efc236393d4c2dbc6e1fa334ad5ccb0e9796bdeba13fbe0515577dd8 |
| Source SHA | fbefca0250980a790eba3d464ad37b86d2d02abf |

## 5. Formal 失败与完整 Error 56 栈

错误发生在 probe audit 之前，因此下列栈是实现失败证据，不是 E0 scientific pass/fail 数值证据。

~~~text
Traceback (most recent call last):
  File "<frozen runpy>", line 198, in _run_module_as_main
  File "<frozen runpy>", line 88, in _run_code
  File "/home/Projects/MyFEniCS/benchmarks/run_task033_full3d_watchdog.py", line 5024, in <module>
    raise SystemExit(main())
                     ^^^^^^
  File "/home/Projects/MyFEniCS/benchmarks/run_task033_full3d_watchdog.py", line 5019, in main
    return _worker(args)
           ^^^^^^^^^^^^^
  File "/home/Projects/MyFEniCS/benchmarks/run_task033_full3d_watchdog.py", line 1513, in _worker
    run_stage4b_block_grating_3d_case(
  File "/home/Projects/MyFEniCS/src/solvers/solve_maxwell_3d_stage_4b_block_grating.py", line 44, in run_stage4b_block_grating_3d_case
    return run_prepared_3d_case_flow(
           ^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/Projects/MyFEniCS/src/solvers/common_3d_case_flow.py", line 1483, in run_prepared_3d_case_flow
    else _petsc_matrix_stats(system_A)
         ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/Projects/MyFEniCS/src/solvers/common_3d_solve.py", line 391, in _petsc_matrix_stats
    info = A.getInfo()
           ^^^^^^^^^^^
  File "petsc4py/PETSc/Mat.pyx", line 805, in petsc4py.PETSc.Mat.getInfo
petsc4py.PETSc.Error: error code 56
[0] MatGetInfo() at ./src/mat/interface/matrix.c:3006
[0] No support for this operation for this object type
[0] No method getinfo for Mat of type python
--------------------------------------------------------------------------
Primary job  terminated normally, but 1 process returned
a non-zero exit code. Per user-direction, the job has been aborted.
--------------------------------------------------------------------------
--------------------------------------------------------------------------
mpiexec detected that one or more processes exited with non-zero status, thus causing
the job to be terminated. The first process to do so was:

  Process name: [[3818,1],0]
  Exit code:    1
--------------------------------------------------------------------------
~~~

## 6. E0 逐 Gate 结果

PASS 表示该字段在原始输出中直接测得并满足要求；NOT_OBSERVED 表示程序在产生该证据前退出，不能用代码意图补写为通过。

| Gate | 状态 | 数据分类 | 实际证据 |
|---|---|---|---|
| qualified ABI/authority/source | PASS | measured | activation、ABI、SHA、clean source 均通过 |
| 80-mode preparation | PASS | measured | 80；top/bottom 40/40；active rows 51192；FE DoFs 173802 |
| 完整 mode key/beta/polarization/power/Rayleigh identity | NOT_OBSERVED | not_observed | probe audit 未生成 |
| 3 deterministic seeds + physical active RHS | NOT_OBSERVED | not_observed | 4 source labels 未生成 |
| forward action <=1e-11 | NOT_OBSERVED | not_observed | 最大误差未生成 |
| auxiliary recovery <=1e-11 | NOT_OBSERVED | not_observed | 最大误差未生成 |
| physical RHS identity <=1e-12 | NOT_OBSERVED | not_observed | 误差未生成 |
| primary matrix-free / explicit C,D = 0/0 | NOT_OBSERVED | not_observed | audit materialization 未生成 |
| oracle explicit C,D = 1/1 | NOT_OBSERVED | not_observed | audit materialization 未生成 |
| primary/oracle profile 分离 | NOT_OBSERVED | not_observed | audit 未生成 |
| component-only/probe/ordinary-default summary | NOT_OBSERVED | not_observed | run summary 未生成 |
| factorization/KSP-specific solve event absence | NOT_OBSERVED | not_observed | 原始 progress/stdout 未见 KSP-specific event，但 completed formal Gate 未产生 |
| KSP iterations = 0 | NOT_OBSERVED | not_observed | 未生成 completed solver summary |
| official result/postprocess | NOT_OBSERVED | not_observed | 未生成 completed solver summary |
| no swap、非内存/非 timeout 停止 | PASS | measured | no_swap=true，三个 termination flag 均 false |
| E0 overall | FAIL | derived from measured exit | MATRIX_FREE_DTN_FORMAL_80MODE_GATE_FAILED |

“没有 KSP-specific solve event”不等于 component Gate 通过；程序是在完成模态准备后、形成完整 summary 前崩溃的。

## 7. 资源与运行时间

| 指标 | 实测值 | 口径 |
|---|---:|---|
| 最后 timeline elapsed | 334.50361661892384 s | watchdog memory_timeline.csv 最后样本 |
| DtN assembly/solve stage elapsed | 330.5629061110085 s | progress event |
| watchdog max_process_tree_rss_mb | 675.91015625 MB | 正式 process-tree authority |
| simultaneous worker RSS | 661.3984375 MB | rank 0 |
| simultaneous worker PSS | 608.1591796875 MB | rank 0 smaps |
| simultaneous worker USS | 562.8671875 MB | rank 0 smaps |
| process-tree swap | 0.0 MB | watchdog |
| no_swap | true | watchdog |
| memory termination | false | watchdog |
| timeout termination | false | watchdog |

这里的 675.91015625 MB 是 watchdog 的正式 process-tree 峰值；不能把它写成完整 PDE solver 的成功峰值，也不能把失败归类为内存停止。

## 8. 阶段与 Candidate E 边界

| 阶段 | 状态 | 说明 |
|---|---|---|
| E0 | completed_controlled_failure | implementation failure，精确分类见上 |
| E1 | not_run | E0 hard stop |
| E2 | not_run | E0 hard stop |
| E3 | not_run | E0 hard stop |
| E4 | not_run | E0 hard stop |
| E5 | not_run | E0 hard stop |
| E6 | completed_closeout | 两份结项文件完成；publication carrier SHA 与 push 后 clean 由外部交付报告提供 |
| Candidate E | not_run | 因 E0 implementation failure 停止；没有 E2 capacity negative 结论 |

因此，本轮不开发或运行 Candidate E，不扫 MPI2/MPI4，不进入任何后续 PDE 或容量实验，也不声称 M120 coarse 无容量。
Selective merge 建议保持 `do_not_merge / not_qualified`；轻量 E0 专属 8/8 仅是 research evidence，不足以使该路径取得通用合入资格。

## 9. Raw 与 compact evidence

compact record：[task037_v6_e0_matrix_free_dtn_formal_failure.json](../../benchmarks/cases/100_static_condensed_full3d_iterative/records/task037_v6_e0_matrix_free_dtn_formal_failure.json)

原始 ignored artifact 目录：

~~~text
/home/Projects/MyFEniCS/benchmarks/artifacts/task037/e0_v6_matrix_free_dtn_fbefca02/mpi1/
~~~

| Raw 文件 | bytes | SHA256 |
|---|---:|---|
| parent_launch_descriptor.json | 1493 | 6549eb98c481f66e507be54d658efc52d9ec773727d73e328546fe05efcfa18d |
| progress_3d.jsonl | 30787 | 175b1a568a213e6b90f885849a1143b965093bd48a7c0d24999c8f1b044b90a2 |
| worker_stdout.txt | 5164 | 090eea790832c8a18fa92f627d812d3911734d730d7d6e9e46f6afddf7bb3b4f |
| watchdog_summary.json | 17948 | dbcd12ded0ff54de1fbf81c99ff9f4ff15e7959907ce874dbc387bf993649fd0 |
| memory_timeline.csv | 1097883 | 6210ce033672d472bb5a0d42680f5f440ab19275ab11364ca4a0ae67616f0fd1 |

run_summary.json、dtn_port_diffraction_orders_3d.json 和 field shard 均未生成；因此不能把缺失文件当成空的通过记录。

## 10. Git 与发布边界

数值证据身份为 checkpoint commit fbefca0250980a790eba3d464ad37b86d2d02abf。formal 运行前 HEAD/upstream 相同、ahead/behind 为 0/0、工作树 clean；E6 结项由本 record 与 response_v6.md 完成。publication carrier SHA 与 push 后 clean 状态按发布边界由外部交付报告提供，不嵌入自身以避免自引用。除这两份 E6 closeout 文件外，没有修改 Python、测试、阈值、ordinary defaults、review 或 task 文档；该 research-only 结果的 selective merge 建议为 `do_not_merge / not_qualified`。
