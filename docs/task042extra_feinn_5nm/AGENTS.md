# Task42extra目录规则

本文件作用于 `docs/task042extra_feinn_5nm/`；根AGENTS、docs/AGENTS与仓库原则继续适用。当前任务范围仅由用户本轮指令、本目录task及以后本目录正式review确定。

1. 本支线唯一执行分支为 `task42extra_feinn_5nm`，工作树根为 `/home/fenics/Projects/NN-Lab-V2`。用户只创建空目录，Codex负责登记Git worktree与后续工作；不得嵌套第二个repo目录。
2. 先完整读取本目录 [task.md](task.md) 和 [README.md](README.md)。冻结base为 `fbac3d8777fcfd897d93b898cb9f460f79ddd6ff`。Task042历史是只读技术依据，不把其V8命令和剩余预算当本任务执行合同。
3. 用户本轮明确授权ChatGPT新建远程分支；后续实现/测试/运行/outcomes/response由Codex完成。任务书和review由ChatGPT维护，Codex不得覆盖，修改建议写response。
4. 环境为工作站原生Linux。只在新worktree写入；旧NN-Lab及另外活跃项目不checkout/pull/install，不更改它们的环境、锁、CPU affinity、优先级或watchdog。受控共享只按task资源Gate；不足时停止自身数值阶段，不抢占邻任务。
5. 首轮是完整Nédélec插值和native全FE残差，不是旧p4逆或仅trace参数化。保留内部矩、双Floquet、完整DtN和正式5nm材料。Gram因子的辅助成本必须单列，不能宣传为无全局因子路线。
6. 新结果只写本任务outcomes/response并更新本分支总账，不改旧Task042及其他任务的历史证据。严格区分实测、推导、预测、诊断、未运行、失败和受控停止。
7. 所有正式FE通过one-run dat主入口；源码/输入/环境/材料/网格/端口/Gram/模型与资源hash完整绑定。不能用loss或优化器success代替原方程与物理Gate。
8. 只推送本分支，不amend/强推、不合并master/其他活动分支。完成一轮提交response并等待review；不自动扩大几何、网络或波长范围。
