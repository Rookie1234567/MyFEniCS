# Task034 Phase F：p2/h1 S 偏振受控负结果

## 结论

用户新增的 `p2/h1`、S polarization 点已按 Full-3D 与 Hybrid 两条路径执行资源 Gate。该点不能登记为数值或物理通过，但已完整形成不可改写的受控负结果：

- Full-3D 在 assembly-only Gate 后停止；三个独立 factorization 预测中心均超过固定 termination threshold，未启动 `KSPSetUp` 或 full solve。
- Hybrid M160 通过 launch、source、memory authority Gate，完成两侧 local factorization、Schur contribution 与 modal Schur solve，但在 `field_recovery` 达到固定 7200 秒 watchdog 上限，被受控终止。
- 两条路径均无 swap，未放宽内存阈值或延长 timeout，也没有重跑以改写负结果。
- 因 Hybrid 未生成 terminal solver record，本点没有 true residual、official R/T/A、field closure 或物理收敛资格。

## Full-3D staged Gate

Assembly watchdog：

- record：`benchmarks/artifacts/task034/phase_f/records/p2_h1_assembly_mpi8_69b807c_s.json`
- SHA256：`520cf7f5a2b8bd3327540d7da808e31abed5b036b66e1aec11001c5f5193b649`
- peak memory：`67.922901 GiB`
- exact rows：`4,379,832`
- exact assembled NNZ：`461,122,320`
- swap：`0`

基于实测 assembly 与既有同 degree anchors 得到的 factorization 预测中心为 `217.584 / 227.187 / 279.214 GiB`，保守上界为 `418.821 GiB`；均高于固定 termination threshold `184.163 GiB`。因此 Full-3D 的正式状态是 `not_run_by_conservative_resource_gate_after_assembly`。

## Hybrid M160 watchdog

运行身份：

- source SHA：`9937747c0f69f0e07e7320081add3abf037a4315`
- MPI：`8`
- modes/candidate pool：`160/320`
- solver path：`modal-schur-memory-minimal`
- authority SHA256：`df11f8146957fb26f3d9b82271419a2aa3c1fa673d31fb83e4ef0cf9acf9521d`
- summary SHA256：`ff48998bbe45fe40cbce778a9e91666ad458b3d7754bea27eb47ef40f0ba7162`

关键阶段边界：

- bottom local factor 完成：`2731.663 s`
- bottom Schur contribution 完成：`3172.848 s`
- top local factor 完成：`5205.347 s`
- top Schur contribution / modal Schur solve 完成：约 `5542.727 s`
- field recovery 开始：`5542.752 s`
- watchdog timeout：`7200 s`

资源终态：

- peak live authority：`95.878723 GiB`，发生于 `field_recovery`
- warning triggered：`false`
- terminated for memory：`false`
- terminated for timeout：`true`
- process-tree/cgroup swap：`0`
- launch Gate、memory authority Gate、source Gate：全部通过

该结果说明 p2/h1 Hybrid 的主要瓶颈在固定时间预算内的直接分解与 field recovery 总时长，而非本工作站的内存容量；但本任务不据此放宽 timeout，也不将未完成 solve 解释为可计算通过。

## 测试与审计

- Task034 Gate targeted tests：`17 passed`
- 普通 WSL 完整测试：`463 passed, 18 skipped in 268.84s`
- 完整测试日志 SHA256：`19b5b6a92bb5c0957384d20278e87a6a27cce1eb2636978f476fca5d8bb85af5`
- transient systemd cgroup 导致的环境敏感测试负结果已单独保留；普通 WSL 定向复测通过，未修改断言或阈值。

机器可读摘要位于 `benchmarks/cases/092_workstation_wsl_adaptive_scalability/records/p2_h1_execution_outcome.json`。后续 convergence、adaptive、Case093 或 0.7 nm 结论不得把本点作为 physical pass 使用。
