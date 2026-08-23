# T40-0 基线内存与阶段归因

## 口径

这里的 peak 指同一正式工作流中进程树的 simultaneous peak，不是把不同阶段的内存相加。阶段表保留历史测量口径；Task40 后续的 scalable candidate 还必须单独记录 setup、factor、apply、cleanup 和 swap。

## 继承的工作流基线

| 路线/阶段 | 进程树峰值 GiB | 解释 | 状态 |
|---|---:|---|---|
| direct full workflow | 93.377006531 | direct 全流程基线 | inherited measured |
| exact-side iterative full workflow | 80.025856018 | V7/V10 exact-side 全流程基线 | inherited measured |
| sequential component envelope: stage 1 | 23.195 | 早期组件阶段 | inherited measured |
| sequential component envelope: stage 2 | 49.313 | exact factor/setup 组件 | inherited measured |
| sequential component envelope: stage 3 | 79.464 | retained/full-side 组件阶段 | inherited measured |
| sequential component envelope: stage 4 | 80.025856018 | exact-side iterative完整工作流 | inherited measured |
| V11 bottom packet algebra component | 12.7808799744 | 只读 action/algebra component，不是完整 workflow | inherited measured negative |

工作流 peak 的组合规则是 max(bottom producer, top producer, consumer)，不是三者求和。Task40 的资源 tier 仍按 task.md 的 full-workflow参考值 74.701605225、65.363904572、56.026203919、46.688503266 GiB 解释；单个 12.7808799744 GiB component 不能声明相对 93.377006531 GiB 的 saving tier。

## 旧负结果与边界

| 继承路线 | 代表性结果 | 不能推出的结论 |
|---|---|---|
| J1 side action | 约 22.27 GiB，mandatory residual 约 45 | 不能称 scalable side inverse 通过 |
| SN2-J action | advancement probe 的 worst residual 约 17.09 | 不能称 side inverse 或生产预条件器 |
| J1-inner FGMRES | residual 约 0.997–0.999 的受限结果 | 不能把局部 Krylov 结果提升为 full Hybrid 资格 |
| V11 bottom packet algebra | projection 已在约 12.781 GiB完成，但 sampled AX、Schur/modal、bottom trace Gate未通过 | 不能宣称 packet 或 solver 正确 |

这些数据说明历史路线的对象生命周期与算法资格必须分开审计。Task40 不能因为一个 component 峰值较小，就把它当作完整 workflow saving；也不能因为之前的 45 GiB controlled stop 已通过 projection 修复，就省略新的 source、factor、rho、residual 和 lifecycle Gate。

## Task40 资源检查点

Task40 的 Level A/B candidate 必须保留 swap=0，并在 scalable candidate 中满足 task.md 的 max_local_rows≤1024、无 FE-sized numeric allgather、无 replicated growing factor，以及 post-setup 资源 Gate。Level A 的 cross-section exact factor 只可作为 oracle；其内存不得被冒充为 scalable final。

正式阶段还必须区分：单个对象的 retained size、单阶段 peak、同时进程树 peak、磁盘 scratch 和 swap。任何受控停止都必须保留 marker、process-tree sample、阶段和退出分类；资源停止不等于数值方法失败。

## T40-0 结论

当前只完成继承审计。没有新内存测量、没有新 factorization、没有新 response packet、没有新 PDE/MPI heavy。后续若进入正式阶段，必须以新的源码 SHA、阶段 marker 和资源样本绑定结果；历史基线在新阶段中仅作比较，不作自证。

## T40-3 measured component

T40-3 的正式 Level-A bottom bare-F action 只测量一个组件：process-tree peak 为
30,422,945,792 B，即 28.333576202392578 GiB；process-sample wall 为
660.6481867840048 s，marker interval 为 658.022411 s，swap 为 0 B。45 GiB
absolute hard stop 为 48,318,382,080 B。这个组件峰值不能当作完整 bottom/top/full workflow
峰值，也不能单独宣称相对 93.377006531 GiB direct baseline 的 saving tier。

正式 raw root 为
`results/task040_level_a_bare_f_mpi8_483275dc`，结果分类为
`TRANSMISSION_MECHANISM_FAIL`；详情见
[T40-3 transmission outcome](transmission_mechanism_oracle.md) 和
[compact record](../../../benchmarks/cases/104_5nm_hybrid_side_factor_pc/records/task040_level_a_bare_f_transmission_v1.json)。

## V1-8 Run B 资源停止

新的 Run B root 到达 `v1_2_exact_oracle_ready`（三个 factor），随后到达
`v1_2_exact_oracle_released`（factor count 为零）。watchdog 仍观测到
`48,380,153,856 B = 45.05752944946289 GiB`，略高于 `48,318,382,080 B` 的硬停止线，
并在 swap 为零时终止完整进程组。这是资源/生命周期边界，不是 projected transmission
的资格通过或失败。逻辑上的 factor 释放不表示 PETSc/MPI 分配或 allocator 页面已经同步
从 RSS 消失。

详见 [resource-stop compact record](../../../benchmarks/cases/104_5nm_hybrid_side_factor_pc/records/task040_v1_2_v1_3_run_b_resource_stop_v1.json)。
