# Task037-extra Response V12：W8–W12 证据收口

本轮只收口已经完成的 W8–W12 研究证据，并保留所有旧 raw、watchdog、临时 JSON 和既有 compact。这里的“投影”是把残差在一个已经生成的候选方向集合上做最小二乘修正；它可以判断方向是否有用，但不能替代完整时谐 PDE、场恢复或 official R/T/A。

## 一页结论

| 路线 | 状态 | 关键事实 | 边界 |
|---|---|---|---|
| W8A/W8B | `W8B_NUMERIC_OR_AUTHORITY_FAIL` | 530 列在 W7 cumulative400 上 `rho530=0.9280021437706651`，相对改善 `0.050673555901245226` | recovery 只恢复可核验的旧 builder 数值/资源证据；不重写旧 RC1，不进入 W8C |
| W9A | `W9A_NUMERIC_OR_AUTHORITY_FAIL` | target `rho=0.9982181470553635`，captured energy `0.0035605308893762767` | control、rank、closure、重复性通过；target `rho<=0.90` 失败 |
| W10A | `W10A_OPTIMISTIC_TARGET_RHO_FAIL` | W5 201 列空间的 optimistic target rho `0.9793601827912443` | 这是可捕获量的乐观上限，不是可实施 PC；旧空间 mapping 路线关闭 |
| W11A | `W11A_PERSISTENT_DIRECTION_FAIL` | Q1 100 步 B0 true residual `2.8285584503326906e-06`；q/target rho `0.9261490705957542/0.9390855969756224` | 资源完成但 B0 固定升级 Gate 未达标 |
| W11B | `W11B_PROJECTION_FAIL` | B0 200 步 residual `4.233006159940796e-09`；q/target rho `0.8914688323899443/0.9101959562746206` | B0 通过，两个固定投影 Gate 失败；未保留失败 candidate |
| W12 | `W12_TRAJECTORY_RANGE_FAIL` | B0 residual `4.233006159940796e-09`；q rho `0.8857084974811911`、target rho `0.9050305821821468` | 这是数值 range Gate 失败，不是 timeout、内存或执行失败 |

## W12 的准确解释

W12 从零开始固定 200 步 right FGMRES，并在 20、100、150、200 步保存四个解，再在 B0 对象全部释放后对这四个解做四次 physical action。生命周期实际为 `b0_constructed → b0_released → physical_constructed → physical_released`，physical action count 为 4；进程树峰值为 `1,116,065,792 B`，swap 为 0，compiler descendants 为空，进程已清理。

W12 的 B0 true residual 是 `4.233006159940796e-09`，固定 B0、checkpoint、action、架构和资源证据均通过。失败只来自两个预先冻结的投影阈值：q 要求 `<=0.70`，实际 `0.8857084974811911`；untouched W7 cumulative400 target 要求 `<=0.90`，实际 `0.9050305821821468`。因此没有写出 `dX/dAX` candidate 文件，也没有资格进入下一轮 physical FGMRES。W12 不是 full PDE，也没有运行 official field/RTA 或 direct-authority physics comparison。

W11A/W11B/W12 都保持 `uncondensed_fullspace`、matrix-free DtN、无 global/augmented matrix、无 static condensation、无 trace-slab PC；预测 live set 与实测 process-tree peak 分开记录，预测不冒充实测。

## W8–W10 的停止关系

W8B 的固定 530 列 range 对 W5 iter200 的 `rho390=0.9764446942793938` 降到 `rho530=0.9266004470461771`，对 W7 cumulative400 仅从 `0.977537441982527` 降到 `0.9280021437706651`。W9A 四个 checkpoint 增量对 target 的 rho 仍为 `0.9982181470553635`；W10A 甚至把完整 W5 201 列 V 空间当作乐观可回收空间，target rho 仍为 `0.9793601827912443`。因此没有继续旧 Krylov mapping、bubble order/degree 扫描或 W8C。

## 未运行与证据索引

full time-harmonic PDE、official field/RTA、direct-authority physics comparison、W8C、新 W9B、新 W10 mapping 和任何后续 physical FGMRES 均为 `not_run`。最终 PDE process-tree RSS `<2,000,000,000 B` 也仍未测量。

详细 hash-bound consolidated record 为 [`m6b_w8_w12_consolidated_closeout.json`](../../benchmarks/cases/101_task37_extra_development/records/m6b_w8_w12_consolidated_closeout.json)，其 evidence SHA 为 `70ddc2c5b21ed5332bc84bac6fb836bd9b382df3ab278b5897f52008ab9d9ae1`。它列出每个阶段的 source、summary/watchdog 或离线 JSON SHA，并明确旧证据只读、失败分类不改写。

下一块 W13A 只实现并测试一个新的 action-only diagnostic：在当前 W5 ProjectedRangePC 与固定 75D range 组合中各做一次 beta=1.0 和 beta=0.5 的固定比较；它不重开旧 bare shifted-patch beta=0.5 路线，不包含 KSP、PDE、field 或 RTA。W13A 正式运行尚未授权，本响应不把它写成已运行结果。
