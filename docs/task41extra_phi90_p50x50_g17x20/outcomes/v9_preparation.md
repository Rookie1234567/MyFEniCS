# V9 准备阶段：同一局部 LU 的 RHS 缩减与保存数据判别

本文件继续记录 Review V9 的准备与局部筛选证据，不是 `response_v9` 或 official 结果。执行依据仍为 `review_report_v10.md`（V9 准备审查），V9 原始 review 为 `b24b6ce6577225af7fb03e4a62bef80126efc9b8`；旧结果基线为 `a63e51f39ee7ed35b03d521cb42fa3fe6c9f834f`。saved-local screen 已实测 READY；Review V10 要求的全域接线已在当前本机 diff 中完成并由局部调用 fixture 验证，但 full-domain FE/action/recovery 尚未运行。

## Review V10：V9 全域接线的局部回执

worker 现在在 saved surface donor 的完整模式扫描前，利用 builder 刚建立的 p6 volume action、FE space、Floquet 约束和 support inventory 构造 exact-geometry same-LU owner，执行两列 compact action/recovery 及 live 独立 checker。物理 builder 返回后立即把 condensed owner 登记到 worker 清理槽；随后目标 P6 action 复用同一个 compiled form 和 condensed owner。terminal checker 可从保存的 NPY 重开并重算 action/recovery 门，复用 live native-action receipt，不重建 FE；该窄路径将 support-certificate recheck 明确记为 `null`。

资格化 activation 下，9 个局部节点通过（compact pass/negative、损坏数组/列/source 拒绝、owner 策略转发、donor-scan 前置顺序及接管前异常清理）；相关 Python 文件 `py_compile` 与 `git diff --check` 通过。完整 pytest、CI 和正式 full-domain FE/action/recovery **NOT_RUN**；official 仍为 **false**。本回执证明接线和轻量 fixture 行为，不代表全域数值资格。

## Review V10 对 V9 准备代码的局部增量（2026-10-22）

本节补记 V10 对现有 V9 screen 的 A/B/C 窄修；不创建 V10 schema、合同或 `response_v9`。保存包的 saved-local screen 已由工作站服务实际读取并完成，状态为 `LOCAL_CANDIDATE_READY`；这不是全域 FE/action/recovery 结果，official 仍为 **false**。

| 项目 | 实施与边界 |
|---|---|
| A：生产 correction | screen 按 `(cell, role, column)` 同时缓存生产核心返回的 `z` 和 `correction`；j3 复用二者，不增加 GETRS。每次状态保留完整 `-(J @ z)` matvec，核对 correction 的 shape、dtype、finite、符号和逐值相等；新 gate 消费返回的 correction。保存绝对残差、`norm(Kz-b_i)/norm(b_i)` 与原 backward-scaled residual 三项。 |
| B：累加次序 | 原 V8 grouped replay 原样保留并继续对照 V8 d。新 RHS gate 从 `b_t` 开始，再按 cell `[23352,23493]`、每 cell 的 `original_trace` 行及复 MPC 系数逐项 `+=`，对应 `reduce_rhs`。新 S gate 先做完整 `S @ t_c`，再做稀疏 `Eᴴ @ local_action`，最后按 cell 累加，对应 `_apply_array`；不把 S 改写成 RHS scatter 或 `vdot`。T、S、J 均保留完整向量 matvec。 |
| B：候选门和数值精度 | candidate 自身两列、j0/j3 的生产序 d 是答案，reference 和 candidate-reference gap 不作为候选门。分别记录 V8 grouped/production 差和 longdouble/production 差；old/new 各自的不确定度取两项较大者。longdouble 差只作保守筛选量，不替代 complex128 d，也不是严格误差界；同时记录 `np.longdouble` 的真实 mantissa 位数。平台没有额外精度时，wide 比较标为不可评价，候选不能 READY。冻结 `D0/D1` 与选中原行保持固定。 |
| C：借用者释放 | owner action 在销毁任何 matrix 或状态前检查其他 retained-J 借用者；仍有其他借用者时抛错且对象保持可重试。其他借用者正常释放后，重试 owner 销毁成功。`stored_T` 默认/cache v1、旧 V8 helper 与旧 B0 authority/v1 行为保持不变。 |

定向负例包含：z 正确但 correction 被改成错 shape、错 dtype、非有限、反号或错数值时全部拒绝；分别更改 j3 的 `b_i`、`t_c`，同步更新数组 SHA 与报告/检查器身份后仍分别被配对门拒绝。强相消复 MPC fixture 直接调用现有小型 action 的 `reduce_rhs(..., rhs_is_mpc_dual=True)` 与 `apply`，并与 selected-row 重放逐位对照；分组次序和生产次序在 RHS 例子中得到不同结果。另有 grouped d 与 production d 相同、但更宽最终组合不同的 fixture，验证该差仍进入保守余量；没有宽精度时则不使用零余量。

最终局部验证：在资格化 activation 与 complex128 PETSc ABI 下，4 个变更 Python 文件 compileall 通过，**14 个受影响定向节点通过**；完整 argv、输出和环境绑定见 [V10 定向测试日志](../../../benchmarks/artifacts/task41extra_phi90_p50x50_g17x20/v9_preparation_20261022/final_targeted_v10.txt) 与 [V10 ABI 记录](../../../benchmarks/artifacts/task41extra_phi90_p50x50_g17x20/v9_preparation_20261022/abi_preflight_v10.txt)。它们是本机合成 fixture 结果，不是工作站 service、真实保存数组筛选或 FE 结果；执行者未自行 commit/push；由主控审查后集中提交推送。

## 当前状态与边界

| 项目 | 当前事实 |
|---|---|
| 科学候选 | `same_lu_rhs_solve`：每个非零内部 RHS 用原 LU 解一次 `Kz=b_i`，再计算 `-Jz`，避免先固化 T 后乘 RHS；不改 S、R、积分、native 或物理输入 |
| 实现 | 默认仍为 `stored_T`；实际同张量 J 按键只读保留并借用，Di 修正复用 z；新增计数、成本及释放检查 |
| 首个可执行阶段 | 现有 service/watchdog 中的 saved-star screen，只读 V8 两个 incident cells、四组已存 LU 及八个已存 z；不重新 factor 或积分 |
| 数值状态 | saved-local screen 已实测 `LOCAL_CANDIDATE_READY`；full action、candidate recovery、200q 与 FE 均 **NOT_RUN**，official=false |
| 固定窗口 | V9 窗口已由用户批准并固定：T0 `2026-10-22T01:12:42.209257168Z`，数值截止 `2026-10-23T00:52:42.209257168Z`，总截止 `2026-10-23T01:12:42.209257168Z`；86400/85200/1200 s。窗口 SHA `a7cac8f274dc17f552c57462da0a386a0c808580b8fc1172c1c88f0ee3075477`；旧 V6 账保持不变 |
| Review V10 接线 | volume-only owner、紧凑 action/recovery 输出、独立终态 checker 与 qualified owner 到目标 action 的同对象交接已接线；受影响局部 fixture 通过，正式 full-domain FE/action/recovery 仍 **NOT_RUN** |
| 历史数值 | V6 两列完整 action 的冻结尺度误差 `1.7183209126709868e-10` / `3.6180522433957604e-10` 仍超过 `1e-11`；候选初次恢复也仍 FAIL。V8 局部反事实不能转授全域 PASS |
| 完整缓存 | 旧进程已退出；保存的小块不是 28,000-key 完整可恢复 owner。不声称旧 LU/J 仍 live |
| 资源 | J 的 `87,091,200,000 B` 以及旧 numeric 加 J 的 `435,653,172,000 B` 是派生载荷，不是 RSS 或准入结论；原 cap/reserve/swap/证据门均未改变 |

代码准备发生于新正式窗口之前，不能隐藏为零费用。执行对话本轮实现开始时间为 `2026-10-21T13:19:04Z`；主控更早的只读核验、审查、等待及分项开发成本未完整记录，仍记 **UNKNOWN/NOT_RECORDED**。saved-local screen 服务在固定 T0 之后运行，已按同一窗口连续记账；其 service/watchdog 时间和资源见下表，不冒充 FE、全域 GETRS 或 production owner 成本。

## 只读输入绑定

两个报告保留原路径、字节、source 和窗口，consumer 单独绑定新合同与冻结源码：

| 输入 | SHA-256 |
|---|---|
| `results/task41extra_phi90_p50x50_g17x20/task41_b0_v8_selected_star_35fd1bbf_20261021T072801Z_attempt1/task41_p0_v8_selected_trace_star_audit.json` | `1bdd07ac38bce95d58a153bacdca0de6cf5941d08d2706dc127e8b00d8e2764f` |
| `results/task41extra_phi90_p50x50_g17x20/task41_b0_v8_saved_checker_3ce1a158_20261021T092516Z_attempt4/task41_p0_b0_saved_evidence_audit.json` | `b12af06f818dd4a93443498371aa653216b1646207418f8eaac265e09ddf78c6` |

真实根为 `/home/fenics/Projects/laptop_share`。原报告绑定的数组逐文件核验，不能只相信这里两项哈希，也不改写旧报告。A/B/C 的本机 fixture 仍只说明合成测试。此后工作站 saved-local screen 使用冻结 source/contract 与真实 V8 保存输入运行成功；服务证据及其范围单独列于下节，不代表 FE 或全域 owner 通过。

## 已执行的 saved-local screen 服务

本次只检查两个 V8 incident cells 和既存 LU/z 保存包，没有积分、factor、FE 重建或 carrier 扫描。冻结 source `708d0c3b99cde06561c13e89f85ed262f1756af7`、合同 SHA `37d287014e0b1d3a3cc9201d138ce4880263e2a8a5d2c5c2fbf687f52603a0ae`，固定窗口 SHA 如上。

| Attempt | 服务 | 结果 | 原始日志 SHA-256 |
|---|---|---|---|
| 1 | `task41-b0-v9-saved-star-screen-3d0dafa3-20261022t0122z-a1.service` | 路径 guard 拒绝：source/result 不在登记 B0 results tree；无数值结果 | `986e2949d7ec14c5ea84eba5b04144953b1b2942bc4cb8e2b81a6e3ed74efc13`（979 B）|
| 2 | `task41-b0-v9-saved-star-screen-3d0dafa3-20261022t0138z-a2.service` | qualified activation 未被 service 接受；无数值结果 | `19bb58ae0b18a6ed86d82e5b46f439a034d260316ffaaa51a17776cea60e4ce6`（1042 B）|
| 3 | `task41-b0-v9-saved-star-screen-708d0c3b-20261022t0133z-a3.service` | service receipt `completed`；screen `LOCAL_CANDIDATE_READY` | `1fa46ee41b42a21d28e10c80176c975319249401e48a6796cf5f6e0f012cf2d7`（213 B；仅启动 warning，无 traceback）|

前两次是受控工程失败，未删除或覆盖。Attempt 3 在原生 Linux `fenics-ws` 工作站 service 下完成。原始输出为 [`task41_p0_b0_v9_saved_star_screen.json`](../../../results/task41extra_phi90_p50x50_g17x20/task41_b0_v9_saved_star_screen_708d0c3b_20261022T0133Z_attempt3/task41_p0_b0_v9_saved_star_screen.json)：138,731 B，SHA-256 `c3be6adeb8c9b5e27d193c597302117db9be78118592e444bd45801b30535684`；service receipt 711,522 B，SHA-256 `7d14eaf65585a29a4de736a5008a4377dea9b89b372581301e6cce609909b246`。原始记录绑定 source、合同、两份 V8 输入和窗口；`candidate_gate_blockers=[]`，identity replay 与 production-core replay 均闭合。

两列 candidate 自身生产序 d（j0/j3 成对数值相同）如下。`d_new`/`d_old` 保留完整复数分量；门基于 candidate 自身的 `|d|` 改善和最后组合不确定度余量，不用 reference gap 代替。

| 列 | 状态 | `d_new` | `d_old` | `|d_new|` / `|d_old|` | 新/旧末次组合不确定度 | 扣除不确定度后改善余量 |
|---:|---|---|---|---:|---:|---:|
| 0 | j0、j3 | `(6.366462912410498e-10, -5.334186425898224e-10)` | `(-2.5320332497358322e-09, -1.3897079043090343e-09)` | `8.305744689149506e-10 / 2.8883352362679107e-09` | `6.185232682007811e-12 / 7.275957614183426e-12` | `2.044299577056769e-09` |
| 1 | j0、j3 | `(8.409954954657906e-10, 1.556608397734749e-09)` | `(3.1201892181087487e-09, -4.780750684219015e-09)` | `1.7692662680591898e-09 / 5.708866600426276e-09` | `9.094947017729282e-12 / 1.4551915228366852e-11` | `3.91595347012099e-09` |

两列均超过各自不确定度并通过局部门。`longdouble` 的 significand 为64 bit；宽算术只参与保守比较，不替代 complex128 d，也不是严格误差界。reference 两列没有改善，但只作对照，不是 candidate 门。

资源与时钟必须按口径区分：service receipt 的外层 elapsed 为 **21.348425770 s**；watchdog 内 worker 工作流保守墙钟预算为 **11.742834750 s**（原 clock interval elapsed 11.742659116 s，watchdog记录 elapsed 11.735384863 s）。先前 systemd transient unit snapshot 报告 **27.481 s CPU time**，这是累计 CPU 时间，不是墙钟；它可以与并行进程树/外层 service wall 不同。systemd/cgroup memory peak 为 **201,084,928 B（约191.7 MiB）**，而 watchdog 抽样进程树 RSS peak 为 **378,245,120 B（约360.7 MiB）**，不可混称。cgroup swap peak 与抽样进程树 VmSwap peak 均为 **0 B**；工作站宿主机 global swap 进出页增量均为0，但仅作诊断，未作为 job gate。watchdog覆盖完整子进程身份，`remaining_child_pids=[]`、`descendants_cleared=true`；service 退出后没有残留 worker。

parent service clock 从 `2026-10-22T01:44:31.318539927Z` 起算，service receipt elapsed 21.348425770 s；watchdog clock interval 到 `2026-10-22T01:44:43.061272468Z`，窗口 watchdog-end 样本为 `2026-10-22T01:44:43.067090741Z`。连续账本由 entry sequence 10 的累计 `1900.315109208 s` 到 end sequence 11 的 `1920.857901097 s`；没有重置 T0 或开新窗口。

V9 saved-local screen 是前置依赖。Review V10 的实际 volume-only owner 策略/J绑定、两列 action 与 candidate recovery、紧凑终态证据及独立 checker、qualified owner 同对象交接已接线，但尚无新 FE/PDE 结果；在主控冻结并确认现场准入前不写 official PASS。

## 测试与已发现的工程问题

第一次最终定向组合为 **26 passed in 1.04 s**；本地合格 activation 的 fixture，不是 FE 结果。随后主控发现旧 V8 helper 不必改变、有符号恒等式诊断遗漏、旧 B0 authority/v1 新字段兼容问题，要求窄修后再跑受影响节点；该最终增量结果以冻结时的 test summary 为准。

保留工程负记录：早期 fixture 缺 pytest 导入、临时合同路径/source 变量及 service 参数 guard/JSON reader 问题已定向修复；另一次扩到旧合同文件的运行有 3 项因历史 fixed window 过期失败，未通过改生产时间门或重跑 PDE 消除。Ruff 在现有环境不可用（NOT_RUN），未安装新环境或依赖。`bash -n`、相关 compileall 与 `git diff --check` 通过。没有全仓 pytest 或 CI PASS 声明。


冻结前修正已完成：旧 V8 helper 精确恢复；旧 stored_T cache identity v1 保留；旧 B0 authority/v1 不强迫新增字段，V9/v2 缺字段仍拒绝。有符号诊断真实计算选中行 `(J+TK)z` 并另列重组余差；candidate gate 仍由原完整 `T@bi`、`S@t`、`-(J@z)` 生成，诊断不能改变判门。最终执行者受影响节点 **10 passed in 0.54 s**；主控同工作树复验 **10 passed in 0.51 s**。其中故意污染诊断投影的 fixture 要求原 d 逐浮点列表不变。新增 fixture 首次预期遗漏诊断偏置，9 passed/1 failed，修正测试预期后通过，未放宽生产门。

完整节点命令、测试日志和冻结前源码内容 hash 见 [准备回执](v9_preparation.json)。日志 SHA-256：`3489eb2434195e306846bfcca847a76580c07ad48fe60931d3b8ca824d487e2e`；本机 ABI 日志 SHA-256：`9c5f454497bb6e17f1cdf5017c8234052fe1c9f4f57293f6eb10b3bcf4716cd1`。这些日志留 ignored artifacts，没有复制旧科学数组。
## V9 worker saved-source binding repair

本次全域 attempt `20261022T034957.536640Z` 在构造 volume-only owner 前以 `WORKER_FAILED` 终止（worker exit 4）。保留的 `watchdog/worker.log` 与 worker summary 只记录 `IsADirectoryError: [Errno 21] Is a directory: '/home/fenics/Projects/laptop_share'`，没有保存 Python traceback 或栈行。源码检查将缺陷定位到 `src/runners/task40_v10_worker.py` 的 pre-donor callback：它从 `candidate_evaluator_audit` 顶层读取 `source_path` 和 `source_sha256`，而 hash-bound V6 报告将两者保存在 `candidate_evaluator_audit.geometry_helper` 下。缺失路径默认解析成工作目录，随后被传给文件哈希函数。原 run 目录、summary、事件日志、资源记录和 service 日志均保持原样。没有触发资源或时间门限，也没有生成正式结果或 owner。

worker 现从保存报告的嵌套字段读取路径和哈希；在构造 owner 前拒绝缺失路径、非文件、canonical repository 之外的路径及哈希不匹配，并将同一已验证哈希写入 prefix receipt。donor 路径、数值方法、阈值和固定窗口未变。

使用合格的本机 WSL activation 与现有 Linux complex ABI preflight 后，定向运行 source-binding fixtures 和 pre-donor owner 生命周期节点：**9 passed, 30 deselected in 0.21 s**。这只是 fixture 验证；没有重跑失败的全域 attempt。

| 文件 | SHA-256 |
|---|---|
| `src/runners/task40_v10_worker.py` | `2772a9f07f9c61a95be711ad051e2fff323246836becc9670097004c5b84bb0d` |
| `src/test/test_task41_v4_volume_only_audit.py` | `47e153bdd786ef1448e9c5196d7012fa09814d391dfc3ca2e3baea9e3b01aa17` |
