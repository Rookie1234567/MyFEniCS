# Task037-extra Response V12：W8–W16B 证据收口

本轮在保留 W8–W13A 研究证据的基础上，补充 W14A–W16B 的 action-only 结果，并保留所有旧 raw、watchdog、临时 JSON 和既有 compact。这里的“投影”是把残差在一个已经生成的候选方向集合上做最小二乘修正；它可以判断方向是否有用，但不能替代完整时谐 PDE、场恢复或 official R/T/A。

## 一页结论

| 路线 | 状态 | 关键事实 | 边界 |
|---|---|---|---|
| W8A/W8B | `W8B_NUMERIC_OR_AUTHORITY_FAIL` | 530 列在 W7 cumulative400 上 `rho530=0.9280021437706651`，相对改善 `0.050673555901245226` | recovery 只恢复可核验的旧 builder 数值/资源证据；不重写旧 RC1，不进入 W8C |
| W9A | `W9A_NUMERIC_OR_AUTHORITY_FAIL` | target `rho=0.9982181470553635`，captured energy `0.0035605308893762767` | control、rank、closure、重复性通过；target `rho<=0.90` 失败 |
| W10A | `W10A_OPTIMISTIC_TARGET_RHO_FAIL` | W5 201 列空间的 optimistic target rho `0.9793601827912443` | 这是可捕获量的乐观上限，不是可实施 PC；旧空间 mapping 路线关闭 |
| W11A | `W11A_PERSISTENT_DIRECTION_FAIL` | Q1 100 步 B0 true residual `2.8285584503326906e-06`；q/target rho `0.9261490705957542/0.9390855969756224` | 资源完成但 B0 固定升级 Gate 未达标 |
| W11B | `W11B_PROJECTION_FAIL` | B0 200 步 residual `4.233006159940796e-09`；q/target rho `0.8914688323899443/0.9101959562746206` | B0 通过，两个固定投影 Gate 失败；未保留失败 candidate |
| W12 | `W12_TRAJECTORY_RANGE_FAIL` | B0 residual `4.233006159940796e-09`；q rho `0.8857084974811911`、target rho `0.9050305821821468` | 这是数值 range Gate 失败，不是 timeout、内存或执行失败 |
| W13A | `W13A_DIAGNOSTIC_EXECUTION_COMPLETE`；W13B `W13B_FIXED_IMPROVEMENT_GATE_FAIL_LOCKED` | run3 完整完成；beta=1.0→0.5，W5 projected rho `0.9995565651228495→0.9940090684868385`，W7 projected rho `0.9999083283541277→0.9937069526556399` | 两个残差的改善仅 `0.5550%/0.6202%`，低于固定 5% 资格门；不解锁 W13B |

## W12 的准确解释

W12 从零开始固定 200 步 right FGMRES，并在 20、100、150、200 步保存四个解，再在 B0 对象全部释放后对这四个解做四次 physical action。生命周期实际为 `b0_constructed → b0_released → physical_constructed → physical_released`，physical action count 为 4；进程树峰值为 `1,116,065,792 B`，swap 为 0，compiler descendants 为空，进程已清理。

W12 的 B0 true residual 是 `4.233006159940796e-09`，固定 B0、checkpoint、action、架构和资源证据均通过。失败只来自两个预先冻结的投影阈值：q 要求 `<=0.70`，实际 `0.8857084974811911`；untouched W7 cumulative400 target 要求 `<=0.90`，实际 `0.9050305821821468`。因此没有写出 `dX/dAX` candidate 文件，也没有资格进入下一轮 physical FGMRES。W12 不是 full PDE，也没有运行 official field/RTA 或 direct-authority physics comparison。

W11A/W11B/W12 都保持 `uncondensed_fullspace`、matrix-free DtN、无 global/augmented matrix、无 static condensation、无 trace-slab PC；预测 live set 与实测 process-tree peak 分开记录，预测不冒充实测。

## W8–W10 的停止关系

W8B 的固定 530 列 range 对 W5 iter200 的 `rho390=0.9764446942793938` 降到 `rho530=0.9266004470461771`，对 W7 cumulative400 仅从 `0.977537441982527` 降到 `0.9280021437706651`。W9A 四个 checkpoint 增量对 target 的 rho 仍为 `0.9982181470553635`；W10A 甚至把完整 W5 201 列 V 空间当作乐观可回收空间，target rho 仍为 `0.9793601827912443`。因此没有继续旧 Krylov mapping、bubble order/degree 扫描或 W8C。

## 未运行与证据索引

full time-harmonic PDE、official field/RTA、direct-authority physics comparison、W8C、新 W9B、新 W10 mapping 和任何后续 physical FGMRES 均为 `not_run`。最终 PDE process-tree RSS `<2,000,000,000 B` 也仍未测量。

详细 hash-bound consolidated record 为 [`m6b_w8_w12_consolidated_closeout.json`](../../benchmarks/cases/101_task37_extra_development/records/m6b_w8_w12_consolidated_closeout.json)，其 evidence SHA 为 `70ddc2c5b21ed5332bc84bac6fb836bd9b382df3ab278b5897f52008ab9d9ae1`。它列出每个阶段的 source、summary/watchdog 或离线 JSON SHA，并明确旧证据只读、失败分类不改写。

## W13A：ProjectedRangePC 组合的固定 beta 比较

ProjectedRangePC 可以用通俗的话理解为“两步修正”：先用局部的 beta-shifted PC 给残差做一次局部处理，再把结果投影到冻结的 75D range 中做范围修正。W13A 只比较当前 W5 结构里的 beta=1.0 与 beta=0.5，先完成 beta=1.0，再释放其约 1.047 GB shifted store，最后运行 beta=0.5；它没有重开已经失败的旧 bare beta=0.5 PC，也没有运行 KSP、PDE、DtN、field 或 RTA。

run1 的 beta=1.0 路径在序列化 `numpy.bool_` 时执行失败，beta=0.5 没有启动；run2 的 beta=1.0 已完成，但 beta=0.5 被旧的 beta=1 guard 拦截。这两次都不是数值结论。run3 是修复后的完整 action-only 证据：process-tree peak 为 `1,717,895,168 B`，`/usr/bin/time` MaxRSS 为 `1,695,490,048 B`，swap 为 `0`，进程已清理，compiler descendants 为空。`1,726,081,915 B` 是在运行前按两个 residual 和一次只保留一个 shifted store 推导的 prediction，不是实测峰值，也不能冒充最终 PDE 内存测量。

W13B 的固定解锁门要求 beta=0.5 的 projected rho 至少比 beta=1.0 低 5%，也就是 `rho_beta05 <= 0.95 * rho_beta1`。这个门的意义是：只有一个明确、可重复的改善，才值得再花约 200 步的 screen 成本；局部或 range-only 数值看起来正常，不能替代这个最终组合 Gate。run3 的独立重算如下：

| residual | beta=1.0 projected rho | beta=0.5 projected rho | beta05/beta1 | 相对改善 | 5% 门 |
|---|---:|---:|---:|---:|---|
| W5 iter200 | `0.9995565651228495` | `0.9940090684868385` | `0.9944500423191865` | `0.005549957680813455`（0.5550%） | 失败 |
| W7 cumulative400 | `0.9999083283541277` | `0.9937069526556399` | `0.9937980557590761` | `0.006201944240923907`（0.6202%） | 失败 |

两组 beta 的 range-only rho 差均为 `0.0`，通过 `<=1e-12` 的身份检查；各 child 的 finite、重复、closure 和 action counts 也通过。可是两个 residual 都远低于 5% 改善门，所以 W13B_FIXED_200_STEP_SCREEN 被锁定，不应继续花费一次 200 步 screen。W13A 的 action-only peak 不是 full PDE peak；full time-harmonic PDE、official field/RTA、direct-authority physics comparison 和最终 `<2,000,000,000 B` PDE 测量仍为 `not_run`。

新的 hash-bound compact 是 [`m6b_w13a_projected_range_composition.json`](../../benchmarks/cases/101_task37_extra_development/records/m6b_w13a_projected_range_composition.json)。它保留 run1/run2 的执行边界、run3 的 top/child/watchdog/timeline/stdout/time/wrapper SHA，并从 raw numeric fields 独立重算上述 ratio、改善率和 Gate。

## W14A–W16B：统一 action-only 结果与边界

这些阶段都只把一个冻结残差送入若干已经定义好的算子，观察“修正方向是否真的能降低残差”。它们没有启动完整的物理方程求解：没有 physical KSP、没有 PDE、没有场恢复、没有 R/T/A。表中的 `rho` 越小表示修正后的残差越小；`inner residual` 只表示辅助内层方程解得怎样，不能代替最终 physical rho。

| 路线 | 固定动作 | 真实数值与资源 | 状态/边界 |
|---|---|---|---|
| W14A | 两次固定 global coercive B0 inner-PC，再做 physical action | physical rho `0.8943645606070599`；prediction `1,281,057,286 B`；peak `1,158,553,600 B`；swap `0` | action/resource closeout 通过；不是 PDE/RTA |
| W14B | 固定 4-step physical correction | rho `0.8943645606070647 → 0.869374076266045 → 0.8681485457234316`；inner4 residual `0.01751006766159766 > 0.01`；peak `1,185,300,480 B`；swap `0` | `W14B_FIXED4_CORRECTION_FAIL`；W14C locked |
| W15A | 用 W14B checkpoint1 residual 重做固定 rank-one correction | inner residual `0.00499608724120203`；local rho `0.9993168124994211`；cumulative rho `0.8937535419182971`；peak `1,162,047,488 B`；swap `0` | `W15A_RESTART1_NUMERIC_FAIL`；W15B locked |
| W16A | beta=1 shifted volume-only auxiliary，固定20 inner，physical rank-one | inner residual `0.061153888358888554 > 0.01`；physical rho `0.8806019129260008`；peak `1,395,236,864 B`；swap `0` | `W16A_GLOBAL_SHIFTED_INNER_NUMERIC_FAIL`；W16B 仅作为后续候选 |
| W16R | W16A 的 z20 作为初值，再固定追加 20 步至 40 步 | 两次 inner residual `0.008234328428613968`；physical rho `0.8814092210776835`；peak `1,398,456,320 B`；swap `0` | `W16R` 通过并解锁 W16B screen；仍不是 PDE |
| W16B | 两次完整 outer-2 screen，每个 outer PC 都是 fresh 20+20 inner | rho1 `0.8814092210776882`（anchor 通过）；rho2 `0.8796856414991869`；inner final `0.008234328428613734 / 0.003015056986064362`；peak `1,557,839,872 B`；swap `0` | rho2 `> sqrt(0.75)=0.8660254037844386`，所以数值 Gate 失败；历史 v1 compact 分类仍为 `W16B_EXECUTION_OR_EVIDENCE_FAIL` |

W16B 的历史分类必须与数值结论同时保留，不能择一叙述。唯一正式 run 自然完成，两次 screen 的数组 identity、资源和大部分证据闭合；但旧 checker 复用了 observer_count=1 的契约，而真实 W16B 四个 cycle 的 `observer_count` 都是 `0`，因此 v1 compact 被标成 execution/evidence fail。当前窄修复只给共享 fixed-20 audit 增加显式 `expected_observer_count`：W16A/W16R 仍默认 `1`，W16B 明确传 `0`；它不改变 action、solver 或数值 Gate，也不改写 compact v1（当前 file SHA：`1f59bdca7abc09ce6385f25b145f97a41f2b3e995b377855267d326bac37056d`）。即使修正这个分类缺陷，W16B 的 rho2 仍明确超过数值门，不能被写成 PASS；W16C 和 outer4 均未运行。

离线几何诊断进一步说明为什么不能盲跑 outer4。保存的残差范数为 `||r0||/||r1||/||r2|| = 1.6023954272 / 1.4123661053 / 1.4096042493`；第一步下降约 `11.8591%`，第二步只下降 `0.19555%`，`r1/r2` alignment 为 `0.9980445183`。要让后两步达到 `rho4<=0.75`，它们的累计因子必须不超过 `0.8525772897`，等效每步至少下降 `7.6649%`；按当前第二步趋势外推 `rho4≈0.8762485870`。这不是新运行或新物理 action，只是对现有 raw NPY 的离线检查。

### W17A：唯一 proposed、尚未运行的候选

W17A 只作为 proposed/not_run 记录：辅助算子改为 `beta=1.0` 的 shifted volume 加同一个 matrix-free DtN80，再用固定 40 步（zero-start 20 + restart 20）产生一个方向，随后做一次 physical action 并独立重复一次。它仍使用 direct beta=1 shifted row-complete local patch PC，不扫描 beta、步数或其他参数。预声明资格门为：每次 inner true residual `<=1e-2`、finite/deterministic/hash identity、physical `rho<=0.85`、normal closure/orthogonality `<=1e-11`，以及 derived prediction `<=1.75 GB`、formal watchdog `<1.95 GB`、swap `0`、compiler descendants 为空。任一门失败就停止，不进入 W17B；W17A 尚未运行，因而没有正式结果或资格结论，也不是 PDE/RTA 通过。

full time-harmonic PDE、official field/RTA、direct-authority physics comparison 和最终 `<2,000,000,000 B` 的 PDE process-tree 测量仍未完成。此前及本轮所有 action-only peak、derived prediction 和 checker 分类都不能替代这些未运行项目。

当前窄修复验证：test342 `26 passed`；tests338–342 `76 passed`；compileall、AST duplicate-key、diff-check 均通过；Ruff unavailable；没有 heavy rerun。
