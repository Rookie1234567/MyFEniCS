# Task40extra Review V29 实际执行与可复核交接

q0 factor-only、两 RHS 与独立保存向量审计已完成。原 run source 为 bee9a1f0e33076e372607581f790bda3a4a0072f；checker source 为 9a9a9d31f4aebf1564d5f09177c1d3481d64371f。本轮唯一 factor 授权已经执行；以下是本次真实命令记录，**不授权重复分解或自动全 q/target PDE**。

窗口 UTC T0=2026-10-12T05:49:12.144309894Z，numeric cutoff11:29:12.144309894Z，deadline11:49:12.144309894Z，SHA68b19c507106a7ad003a6c7121cb3ba4461ed569bd4706e221970d59126bbf1e。批准512GiB task cap、64GiB host reserve、task swap0，native_linux/PETSc3.25.6 complex128/int32、MPI1/数学线程1。

## 已执行的 factor-only 命令

```bash
cd /home/fenics/Projects/laptop_share
bash scripts/run_case_in_user_service.sh benchmarks/artifacts/task40extra_0p7nm_engineering/local_v28_wsl/stage_inputs/selected_reference_q_csr/target_original_ny8_operator_probe_v22.dat --task40-v29-execution-contract benchmarks/artifacts/task40extra_0p7nm_engineering/local_v29_preparation/execution_contract_v29_fix01.json --task40-v29-factor-only-selector benchmarks/artifacts/task40extra_0p7nm_engineering/local_v29_preparation/factor_only_selector_v29_fix01.json
```

实际 contract4114d23deb54c7cfec38197fca6d6440368f7eae26b74eed4d6a4bb0e4905ef6，selector aa57f05a797c03da48c85ca8ee10acfc44b29f5841f2c0cea715ea4cd8d9d11f。原旧 PENDING contract 保留为历史，没有作为执行参数。

## 仅复验原数据的 checker 命令

以下核心命令在新512GiB/MemorySwapMax0 user-service中经现有 `_supervise_required_checker` 与独立 watchdog执行，parent/request/activation/source/campaign都实绑定；不能在未 activation 的裸 shell 运行后宣称符合监控。

```bash
cd /home/fenics/Projects/laptop_share
python scripts/task40_v20_service_workflow.py check-partial --input benchmarks/artifacts/task40extra_0p7nm_engineering/local_v28_wsl/stage_inputs/selected_reference_q_csr/target_original_ny8_operator_probe_v22.dat --summary results/task40extra_nonseparable_0p7nm/task40extra_0p7nm_target_original_ny8_operator_probe_v22__full3d_iterative__mpi1__Mna/20261012T071945.212305Z/run_summary.json --manifest results/task40extra_nonseparable_0p7nm/task40extra_0p7nm_target_original_ny8_operator_probe_v22__full3d_iterative__mpi1__Mna/20261012T071945.212305Z/run_manifest.json --numerical-output results/task40extra_nonseparable_0p7nm/task40extra_0p7nm_target_original_ny8_operator_probe_v22__full3d_iterative__mpi1__Mna/20261012T071945.212305Z --stop-stage selected_reference_q_csr --output NEW_CHECKER_OUTPUT.json
```

28项 metadata与7项完整保存向量审计分别记录；后者用原两个NPZ对全部777644行重算，4次新factor相关CSR MatVec，后台solve/factor0，旧native replay0。实际薄控制脚本原文/hash已发布在records/v29_main_checker_fix02_audit.py.txt、.sh.txt和v29_main_factor_saved_vectors_audit.py.txt/parent.py.txt/.sh.txt；源码调用既有watchdog，无新求解器。控制脚本中的原输出目录对应已完成审计，复现需要新的目录与显式后续授权，不覆盖旧记录。

## 结果与下一次准入

完整Fq742.097546059s（含loader30.286357418s）；lifecycle子Fq711.811188641s；raw repeated Sq12.919099297s。cgroup peak84891103232B，simultaneous tree RSS84767309824B，task swap0、PSSnull。两rho1.977628323114713e-14/1.6069609784650353e-14，原门1e-10。

下一批只在新授权/完整对象账准入后构建其余实际q，优先判断ALL_Q_RESIDENT是否可保存同一准确因子。源CSR/PETSc/因子/local/FE/port/Krylov/恢复输出与余量都需同时计量；q0乘8仅情景。cold首次producer/pattern/fill/JIT和缓存miss重建全部计入48h，不把已测q0误称全q或真实target场。

完整小凭据原字节和大文件索引见[v29_published_receipt_index.json](records/v29_published_receipt_index.json)、[response_v29](../response_v29.md)。大矩阵/向量仍ignored，保留在获批目标目录；旧预批准交接见[target_stage_handoff_v29_preapproval.md](target_stage_handoff_v29_preapproval.md)。
