# Task41extra Response V17：两单元诊断收口，完整作用仍失败

**状态：V17 两单元保存重放及独立 checker 已完成；结论仅限一个指定行、两个相邻单元和两列保存数据。全域 action 仍为 FAIL，V17 不解锁 full owner、200q、恢复求解、完整参考或官方物理结果。** attempt04执行了获准的两单元producer；随后attempt05、06、07复用其报告，只运行saved-only checker。attempt07和材料收口没有新启动worker或GETRS。

## 1. 做了什么，结果能说明什么

这个诊断把指定行的初始/最终保存值与两个相邻单元的局部项逐项对齐，用来判断这一个局部观测的变化是否来自矩阵乘法末位舍入。它能定位已保存数据里的局部数值变化；它不能代表其余数百万行，也不能证明完整算子的物理误差已经修复。

| 范围 | 实际结果 | 数据身份与边界 |
|---|---|---|
| V17 attempt04 producer | 两个指定单元、两列的候选项、局部状态和 RHS 校正链已生成并保存；attempt04 service 的下游 checker 授权绑定错误，原失败回执保留 | measured；只覆盖 row 1622464 / original row 5218672、cells 7873/8014、columns 0/1 |
| V17 attempt07 checker | 独立只读 checker 完成；`check_completed=true`、`data_integrity=true`、`errors=[]`；110 个 NPY 输入、75,253,856 B 的唯一证据通过 hash/形状/数值复核，精确重现报告值 | measured；状态 `LOCAL_REPLAY_COMPLETED`，不是全域或科学资格 |
| 原全域 action | 既有全域值 `5.7625744836007965e-11` / `1.212368464357194e-10`，限值 `1e-11`，仍为 FAIL | measured prior evidence；V17 没有重新计算或改变该判定 |
| 科学和官方结果 | `scientific_qualified=false`、`official_result=false`、`full_owner_unlocked=false` | attempt07 checker 原字段；没有 target field 或官方 R/T/A |

## 2. 指定行的 initial→final 归因

令 `d = y - g`，下表均是最终减初始的有符号复数变化。高精度列用保存的二进制64位输入在 80 位十进制精度下独立求值；它和二进制64位 `J` 乘法的舍入变化相加后，闭合到观测的 `Δd`。数值是无量纲保存向量分量，不外推到未检查的行。

| 列 | 观测 `Δd` | initial→final 精确 `ΣJ(z_final-z_initial)` | `J` 乘法舍入的变化 | 分量闭合差 |
|---:|---|---|---|---|
| 0 | `(3.78349795937538147e-10) + (-8.73114913702011108e-11)i` | `(8.24157992581579704e-11) + (-5.91287797091182407e-11)i` | `(2.95933996679380177e-10) + (-2.81827116610828702e-11)i` | `(2.8e-75, 7.1e-75)` |
| 1 | `(1.16415321826934814e-10) + (7.56699591875076294e-10)i` | `(7.89651224828448140e-11) + (1.64831598516315941e-10)i` | `(3.74501993440900005e-11) + (5.91867993358760353e-10)i` | `(2e-75, -5e-75)` |

在该两列局部记录中，`g` 的 binary64 scatter 舍入变化为 0，最终 `y-g` 相减舍入变化也为 0；局部/native `J u - b_{t,volume}` 的 initial→final 变化为 0。**精确的同单元 native rank-1/scatter 分解仍缺失，其他全域项也未闭合**；因此这只是指定行的舍入归因，不是全域根因结论或修复证明。

后续若主控仍需要一个最小诊断，可先核实保存数据是否含该行所有必要操作数，再对相同已保存初末向量比较 `project_internal_rhs_same_lu` 内普通与补偿/可复现的 `Jz` 求和，并核对 `P6CellCondensedAction.reduce_rhs` 的原累加。这个检查当前未运行、未实现，也不能替代缺失的同单元 rank-1/scatter 证据或原全域门。

## 3. 固定范围、source 与窗口

- 执行分支：`task41extra_phi90_p50x50_g17x20`；合同/checker source：`17df17b39379001cf2bd368f05ed1da9118762ac`。
- 固定对象：active row `1622464`、original row `5218672`、ordered cells `[7873, 8014]`、columns `[0, 1]`。
- V17 execution window SHA-256：`7d12b524c385f3d211579a5b49772f36b4e0f1198e9364a49a0afc2733dbbc54`；T0 `2026-10-28T09:17:39.097621720Z`；数值截止 `2026-10-28T14:57:39.097621720Z`；总截止 `2026-10-28T15:17:39.097621720Z`。窗口总计21,600 s，数值阶段20,400 s，收口保留1,200 s。窗口记录的 entry source 是 `611ec943e79e19a8749ae7c9c7baf13a406db8d6`；消费者合同/checker source 为 `17df…`，T0 和窗口字节未刷新。
- consumer contract SHA-256：`5ca97c97ab0c19d495a0f223c8fd39ce709b65a1723af054cd7fec103334c0e5`；authorization SHA-256：`fda2e65a17c980496733ffa77e755683650252e350e0e4f403717af32a948fc0`。
- attempt07 是复用 attempt04 完整 producer report 的只读 checker 路径：`new_worker_allowed=false`、`new_getrs_allowed=false`。producer report SHA-256 `4e6fce6680a0bb304ed0370542f8b5c6003d39940d94ff3e54f19322aeb1709b`；producer progress SHA-256 `bbf3bd03382f738cf4b0d22a167a29f6862028a06f4b6124ad3a07b0796223c6`。

## 4. attempt01–07 历史与两级成本账

| Attempt | 来源 / 状态 | 本次工作与边界 | 时间和资源 |
|---|---|---|---|
| 01 | source `611ec943e79e19a8749ae7c9c7baf13a406db8d6`；启动失败 | `NameError`：`b0_v8_selected_trace_star_audit_mode` 未定义；未生成attempt目录 | 独立服务时长 `UNKNOWN_NOT_MEASURED`；launcher日志 hash 见 [attempt index](outcomes/v17_closeout/attempt_index.json) |
| 02 | source `4496f833d2d30ff80ce280f9107ee6f6882c3a31`；启动失败 | checker-only route拒绝未绑定的saved-output snapshot；未生成attempt目录 | 独立服务时长 `UNKNOWN_NOT_MEASURED`；launcher日志 hash 见attempt index |
| 03 | source `2590796331697a1b0b3a9233b19e47e0daa35a5d`；worker失败 | watchdog `resource_snapshot` 将dict当作callable传入；malformed report是次级故障，不是首因 | parent 15.346485 s；嵌套worker watchdog 13.507745 s；tree RSS 306,782,208 B；swap 0；cgroup峰未记录 |
| 04 | source `56ff5a603d4ba17c8ba6c45974777e1abcbca35e`；producer完成、service因下游checker授权绑定失败 | 两个候选张量、2次LU、矩阵RHS GETRS 6次、向量RHS GETRS 12次；raw producer和失败回执均保留 | parent 128.293210 s；嵌套worker 126.412692 s；tree RSS 2,692,341,760 B；job cgroup峰 2,637,549,568 B；swap 0 |
| 05 | source `436bb69e9de61277b225d919faa7015abe901463`；saved-only checker完成 | 重用attempt04 producer；没有新worker/GETRS | parent 32.791400 s；嵌套checker watchdog 16.160619 s；tree RSS 452,767,744 B；swap 0 |
| 06 | source `adf3483d481a85c2d0b0ffdcfa7684118a27bbcf`；saved-only checker完成 | 重用attempt04 producer；没有新worker/GETRS | parent 36.671775 s；嵌套checker watchdog 16.900071 s；tree RSS 485,900,288 B；swap 0 |
| 07 | source `17df17b39379001cf2bd368f05ed1da9118762ac`；独立checker完成 | 重用attempt04 producer；没有新worker/GETRS；数据完整，errors为空 | parent 37.743761 s；嵌套checker watchdog 17.098682 s；tree RSS 479,342,592 B；cgroup峰 411,295,744 B；swap 0 |

这里的parent时间是campaign账本中该服务`task41_p0_service_entered`至其`watchdog_end`的相邻累计差；watchdog是parent内部子段，不能再次相加。attempt01/02没有单独终止计时回执，保留为UNKNOWN而不以相邻service启动间隔冒充运行时长。

## 5. 资源、时间和证据

| 项 | 结果 | 口径 |
|---|---:|---|
| attempt07 外层 service 窗口 | 37.743761 s | 固定账本 attempt entry 至 watchdog_end；内部 watchdog 已包含在内，不重复相加 |
| attempt07 独立 checker watchdog | 17.098682 s | 15个样本；leader exit 0；后代已清理 |
| 同时进程树 RSS 峰值 | 479,342,592 B | dedicated subreaper 与全部后代的采样同时 RSS |
| job cgroup 内存峰值 | 411,295,744 B | 单独的 task cgroup 指标，不与 RSS 相加 |
| 任务 swap 峰值 | 0 B | 同一进程树 VmSwap 与 job cgroup 均为0；全局计数采样增量为0页 |
| post-write 证据门 | PASS | 新窗口树77,936,866 B / 134,217,728 B；累计原始证据15,680,970,370 B / 17,179,869,184 B；空闲空间1,976,837,951,488 B，高于2,147,483,648 B底线 |
| 只读窗口快照 | 截至 `2026-10-28T11:18:49.180545Z`，固定账本最近持久序号179、累计6,579.047321 s；按同启动时钟投影到采样时点为7,270.083028 s，数值余量13,129.916972 s、总余量14,329.916972 s | 投影只读、未追加到账本；快照 hash、时钟和余额见 [window_snapshot.json](outcomes/v17_closeout/window_snapshot.json) |

原 watchdog 的 global-swap scope 字段保留了历史标签 `WSL-global`；实际 service 在工作站 native 环境运行。此标签不作为 job-specific swap 归因，原始回执未改写。

主要证据：attempt07 independent checker `7f8ea99a…f38bc43`；service receipt `d5c6f842…139aa5d6`；watchdog summary `6f032b5c…031719b2`；campaign accounting 212,117 B、SHA-256 `32da8874…2dd4097`。完整本地/远端路径、字节数和 hash 见 [V17 evidence index](outcomes/v17_closeout/evidence_index.json)。原始数组仍在 workstation ignored `results/`，没有复制进 Git。

## 6. 测试与交付边界

实现阶段的 qualified activation 定向测试记录为 `47 passed in 15.72s`；主控冻结快照的独立回归记录为 `48 passed in 15.74s`，含一项 V15 合同兼容测试。工作站 native ABI preflight 通过：PETSc complex128/int32、MPI1；ABI receipt SHA-256 为 `1c4277c83a0ac6daf02197086264b9e5b337caee1b33d7cc1dd22a7dfcefe57d`。attempt07 是正式授权下的真实只读服务收口，不是 pytest。本文档收口没有重跑测试；本地文档整理用时没有原始起止时钟，记为 UNKNOWN_NOT_MEASURED；后续各冻结源码的最小回归结果另列于[test_summary](outcomes/test_summary.md)，没有全仓测试或 CI 声明。

最终审核源码为 `17df17b39379001cf2bd368f05ed1da9118762ac`；科学producer源码为 `56ff5a603d4ba17c8ba6c45974777e1abcbca35e`。文档收口由主控集中提交，精确发布HEAD以最终Git回读为准。原全域 FAIL、旧 attempt 负记录与 ignored 原数组均保留。

主控最终仅做文档静态检查与小型原始回执hash读回：12个工作站小文件匹配，未新增数值或checker运行；11:20:38Z确认工作站工作树干净、无Task41 worker/checker。文档表格和本地链接已静态核对，GitHub线上渲染未核验。后续文档/发布时长未独立测量，不能把11:18:49窗口快照当作整轮最终费用。见[main_closeout_check](outcomes/v17_closeout/main_closeout_check.json)。
