# Test summary

QEP focused suite 在 native ABI、线程全1下完成；本轮未运行 PDE、formal、full suite、ruff 或 compileall。

新增 controlled-stop node 首次仅因 fake config 缺 `n_air` 失败，最小修正测试夹具后=`1 passed`（wall=`2.15 s`）；最终四节点 serial=`4 passed`（wall=`1.32 s`），MPI2 每 rank=`4 passed`（wall=`1.69 s`）。此前 `1.34 s` 是不存在 test node 的 collection 命令拼写错误（`no tests ran`），不是代码失败。

| 项目 | 状态 | 说明 |
|---|---|---|
| 20260907 3 nm fresh | 已有 artifact | consumer_exit(solution_snapshot_destroyed)，IMPLEMENTATION_FAILURE；五残差仅 diagnostic marker only，formal_result/gates/physics=null；资源与 cleanup lifecycle 保留 |
| 20260908 3 nm retry | 已有 artifact | solve/recovery mechanics通过，own physics closure失败；candidate only |
| 5 nm Task039 inherited MPI8 | 已有 authority | full numerical/recovery/physics pass；不是本机复现 |
| 5 nm Task041 local MPI8 | 已有 authority | solve/recovery/physics pass；独立本机 reproduction |
| 5 nm source-only S1 | 已有 audit | keys/roundtrip/repeat通过，但 source semantics Gate失败 |
| 5 nm MPI1 | 四次 attempt | 保留 producer/resource、external-key 和 terminal-sample 的精确失败层次；equivalence未建立 |
| 2 nm、3 nm后续 M/MPI1 | not_run | NOT_RUN_DUE_TO_3NM_M800_PHYSICS_GATE |

20260907 producer 事实：qep_begin=0.192512509 s、qep_ready=17998.540383 s、producer peak=16.784275055 GiB、packet bytes=913401973、packet write max-rank=0.963676714 s、consumer_qep_required=false。qep_begin 到 qep_ready 不被统称为 eigensolve。

优化记录：旧 reciprocal mass overlap 为 `3PN` MatMult（M800=`1,920,000`、M1200=`4,320,000`），新实现为 `P+N`（1600/2400），仍保留完整 P×N dots/Hungarian assignment；K0/K1/K2 Frobenius norms 每 operator tuple 一次，公式/Gate不变；`timings[reciprocal_pairing]` 已进入 producer controlled-stop record。新归约顺序只承诺 Gate 内浮点等价；下一次 packet 是新的 source-bound hash，仍须通过 canonical/selection Gate，不承诺与旧 packet byte-identical。当前无 post-change formal performance 数据，M1200 尚未启动；M800 own-physics negative 和原 task stop 结论永久保留，不改写为 pass；用户后续已明确授权在更严格的 phase 资源合同下继续一次 M1200 formal，属于受控 M-ladder 诊断/续跑；该授权不能追溯使 M800 通过，M qualification 仍要求各 run own Gate 及相邻 M Gate。

完整 raw factor_inventory 已保存在 ignored roots；compact docs 仅摘录 bottom/top corrected NNZ、MUMPS factor-only、ICNTL14=40 和关键 lifecycle 字段，本轮不倾倒 raw。仍缺：5 nm MPI1 合格 packet、consumer/workflow 内存 authority 和完整 equivalence；3 nm official RTA、M/grid convergence；2 nm 全部结果；逐 rank 或分阶段 PSS/USS；完整 raw 数组和逐通道复核。上述项目均标为 NA 或 not_run，不补猜值。

## 分阶段资源合同与最终 focused verification

本阶段代码范围为 `src/io/input_validation.py`、`src/runners/task041_supervisor.py`、`benchmarks/task041_exact_side_workflow.py`、两个 3 nm official input 以及 `test_341`/`test_343`/`test_344` 的相关回归。central workflow envelope 为 warning=`224 GiB`、hard=`256 GiB` (`274877906944 B`)、total wall=`39600 s`、swap=`0`；shortwave producer 为 `176/192 GiB`、`18000 s`，consumer 为 `224/256 GiB`、`21600 s`。supervisor 与 worker 使用同一 phase policy，shortwave timeout 按 phase elapsed，workflow peak 为 `max(producer, consumer)`；5 nm legacy 合同保持不变。

最终 focused serial verification 使用 native ABI：PETSc ScalarType=`complex128`、IntType=`int32`，五个数学线程均为 `1`；20 个 parameterized test instances passed，pytest internal=`4.21 s`，outer wall=`4.54 s`。覆盖 official M800/M1200 execution identity、central phase policy 与 fail-closed、worker producer/consumer limits、MPI8 child argv/CPU0–7 mock、shortwave phase timeout、legacy workflow timeout、peak=max、memory/swap stop 及 process-group cleanup，并保留 actual GMRES10/input FGMRES90 身份断言。

本轮未运行 MPI2、任何 heavy/PDE/formal、full repository suite、ruff 或 compileall；M1200 仍未启动。由于两个 official dat 改变，input/resolved hash 已改变；正式 run 必须在提交后重新执行 source、ABI、input/resolved identity 与资源合同 preflight。
