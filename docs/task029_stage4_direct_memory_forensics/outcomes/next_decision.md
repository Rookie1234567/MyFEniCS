# Task029 下一步判断

## 立即动作

1. 推送 `response_v1.md`、P0-A/B/C/D 更正、线程审计和合同测试。
2. 等待 Task29 final review；若仍有可执行意见，继续在同一分支修正。
3. final review 通过且用户明确许可后，合并建议保留的遥测、benchmark、治理合同和低风险生命周期基础设施；不提升 low-memory/threaded direct profile。

## 技术方向

继续微调 direct ordering 或对象生命周期不太可能补足所需降幅。h=3 的 KSPSetUp 对主峰贡献约 6.47 GiB，factor estimated storage 约为 augmented storage 的 12.45 倍；base 提前释放只节省 5.46%，最佳 rank-count 改动也只有 15.12%。下一轮内存研究应聚焦真正的 multilevel H(curl)、low-order-refined multigrid，或带有受控 coarse direct solve 的并行 physical Schwarz，而不是继续大范围扫描 direct-solver 参数。

当前镜像也不应继续扫描 BLAS 线程：PETSc/MUMPS 确实链接可控的 OpenBLAS pthread，但 MPI1×4 在 `during_ksp_setup_peak` 仍约 1 核，且相对 MPI1×1 Stage4 仅快 1.054×。只有更换为明确支持 threaded factorization 的构建后，才从固定四核 h5 capability audit 重新开始；本轮 threaded h3 明确 `not_run`。

COMSOL GMRES/TFQMR + GMG 结果仍只是一条定性架构线索：机器、四面体网格、偏振、block 宽度和衍射范围均不同。它支持研究完整多层层次，但不能作为 Task29 runtime、R/T/A 或每 DoF reference。

另外，Task28 尚未关闭的物理问题依然重要：residual 与能量闭合不能证明 R/T/A 已随 h 收敛。未来应先做 physical-convergence/reference-qualification，再进行大范围角度、波长或材料扫描；不要与本次已收口的 direct-memory profile 工作混在一起。

当前工作站不要运行 h=2 direct。若未来明确把 48–64 GB 机器纳入范围，应先实现并测试真实 watchdog/clean-abort 路径，再在最终 source 上重跑 h5/h3，之后才考虑一次 guarded h2。
