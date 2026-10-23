# V9 准备阶段：同一局部 LU 的 RHS 缩减与保存数据判别

> 当前状态（2026-10-23）：V9 全域候选已经 FAIL；本文件前文为历史准备记录。当前 V11 窄准备与待批准六小时入口见文末，尚未运行新的科学扫描。

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

## V9 owner prefix-audit registration follow-up (2026-10-22)

全域 attempt `20261022T041809.325937Z`（service `myfenics-case-20261022T041728-2705780.service`，run source `4dcea02bdaea4bbbeb50b935f655a6c94d8716e1`）在 `fresh_volume_owner` 阶段失败，worker exit 4；04:53:46.632Z 记录 owner phase `FAILED`，错误为 `RuntimeError: V6 eight-key original-kernel prefix qualification is incomplete or failed`。该 attempt 没有 official result。现存 summary 没有持久化本次逐键比较与 evaluator 审计记录；因此本次 V9 的逐键数值、比较布尔值和 audit 计数均记为 **UNKNOWN / NOT_PERSISTED**，不从旧资格记录补写成本次实测。没有触发资源或时间 gate，失败 attempt 与其证据保留。

源码调用路径显示，新 V9 callback 完成代表键 validator 后没有调用 evaluator 的 `record_prefix_qualification`；后续 builder 因此从空的 evaluator audit 读到不完整资格并拒绝。这是对失败门的源码控制流归因，不是缺失的逐键运行记录。既有 V6 报告 `task41_p0_v6_actual_qmetric_candidate.json`（SHA-256 `72c01eb9a7780ba86a7d8b8de6cfc1fd25e04fead2170788a5f492cd12ebd06e`）单独记录 8/8 PASS：其中 2 项来源为 `V4_SAVED_ACTUAL_BLOCKS` 且 witness 为 `NOT_REQUIRED_V4_SAVED_ACTUAL_BLOCKS`，另 6 项为 `ORIGINAL_FFCX_KERNEL_ORACLE` 且 witness 为 `BITWISE_EQUAL`，旧记录的比较限值为 `1e-11`。其 evaluator identity/cache identity 为 `task41extra_actual_qmetric_blocked_gram_ffcx_profile_v1` / `task41extra_actual_qmetric_blocked_gram_ffcx_profile_v1:abf508c661fd79892922d6a0a245fcbc50afeaf7df79f4f202345fe7b634c225`。这些是 V6 历史资格事实，不是本次 V9 的测量。

本地窄修复只补资格登记：对来源与 geometry witness 的允许配对、当前数组 dtype/shape、坐标/raw/oriented tensor 的 `numpy.array_equal` 结果及当前 evaluator/cache identity 全部核对后，才把原 V6 record 深拷贝登记到真实 evaluator。原 `source`、`reference_artifacts`、`geometry_witness` 和历史耗时保留；新信息单独写入 `qualification_origin`，绑定 V6 report/index/record 与当前数组 hash、evaluator identity。每键登记前后 audit 摘要写入事件日志和候选 summary。未知来源即使缺失 witness 也会拒绝，不能由 `None == None` 误通过。数值门、V6 限值和 full-admission builder 未改。

主控在合格 activation 下复验定向节点：`python -m pytest -q src/test/test_task41_v4_volume_only_audit.py -k 'v9_saved_v6_prefix_reuse or v6_volume_owner_forwards_selected_evaluator_to_actual_builder'`，结果 **5 passed, 38 deselected in 1.04 s**；`git diff --check` 通过。覆盖真实 evaluator 的八键登记及完整 audit、缺键不具备资格、数组不符与未知来源/缺失 witness 拒绝，并包含 owner evaluator 转发节点。测试原始日志 `benchmarks/artifacts/task41extra_phi90_p50x50_g17x20/v9_preparation_20261022/prefix_registration_controller.txt`，SHA-256 `0a4f71d9950e051ee0fc77fb244865219cb212d99f5dee01a99003bb856adfcb`。执行者另一次本地预检在 pytest 启动前停止，不计入验证；上述结果来自主控合格环境复验。

| 文件 | 当前内容 SHA-256 |
|---|---|
| `src/runners/task40_v10_worker.py` | `68b5008a8f88af8c26892e13b220b60a0bec1816d8f8272e166aa48f8270717e` |
| `src/test/test_task41_v4_volume_only_audit.py` | `57639f5ac7e5ef1ca26ce69ce6f9f15db9d583f9b2453207f53694e0014897fa` |

以上只是接线修复与 fixture/audit 验证。此记录不改判失败 attempt，不代表新 FE、full action/recovery、200q 或 official result 已通过；固定 V9 窗口保持原样，等待主控冻结后再依其指令续作。

## Review V11 窄准备（2026-10-23，当前状态）

上文 V9/V10 的 READY、待冻结和 NOT_RUN 均是历史记录。V9 后来的全域结果见 [response_v9](../response_v9.md)：两列 action 真实 FAIL，candidate 恢复 NOT_RUN。当前依据 [Review V11](../review_report_v11.md)，仅准备失败终态补审、V6/V9 保存 y/g 的交叉分解和有条件的87567局部机制核查。**新六小时窗口 PENDING_USER_APPROVAL，尚无真实 T0；正式 saved scan、事后补审和新局部数值均 NOT_RUN。**本准备不改变既有科学算法或门限。

保存对比逐块读取四份 complex128 NPY，把作用 y 与缩减 RHS g 分开，输出 trace/port 的变化、固定分母比值、误差能量分布和有符号内积。不会写新的全长差向量。共同 donor 的全局5688000 trace行、见证58000支撑行、213024 slave行和64120端口行分别核验；共同manifest绑定表示记录身份，不冒充重新核验旧局部数值缓存。

失败审核在现有 service/required-checker 中选择真实 run manifest、summary、compact 和数组，不要求不存在的官方输出目录。审核完成与数值通过分开：预期忠实复现 action FAIL、recovery NOT_RUN、official=false。原 terminal NOT_RUN 不回写。该审核仍复用旧 compact checker 的 donor loader，因此会读取其所需旧 donor 数组/映射/状态；不是只读两个NPY，也不重新执行恢复或FE。y/g比较使用轻量共同manifest绑定，不调用完整 donor loader。各项真实读取成本在获准运行后计量。

新输出按 `results/<model>/task41_p0_saved_diagnostics_6h/<window_sha>/<mode>/attemptNN` 隔离。新增512MiB是整个窗口总额，包含各attempt及其service输出；累计16GiB、磁盘余量2GiB仍受检查。旧累计14990282640 B是历史记录，启动实读文件大小另列，不把stat等同于内容hash验证。修复后的新attempt不删除旧目录、不刷新T0。准备函数对saved-only返回 `service_command=null`，避免给出普通DAT全场命令；现有service拒绝用此合同启动普通全场。条件87567接线尚未实施，只在保存分解证明必要后窄接，不据此放行全域或200q。

### 获准后的真实入口（当前未执行）

仅在主控同步已冻结科学源码、保全工作站已有改动、确认同分支干净并取得V11六小时明确批准后使用。以下命令在既有 `fenics-ws:/home/fenics/Projects/laptop_share` 执行；首条prepare登记唯一T0，后续修复重用同窗口。无需创建新环境或runner。

```bash
set -euo pipefail
cd /home/fenics/Projects/laptop_share
source scripts/task40_fresh_c1/activate_native_complex.sh \
  benchmarks/artifacts/task40extra_0p7nm_engineering/local_w0_wsl/runtime_prefix \
  benchmarks/artifacts/task40extra_0p7nm_engineering/local_v29_wsl/abi_receipt_v29_attempt2.json \
  benchmarks/artifacts/task40extra_0p7nm_engineering/local_v29_wsl/jit_cache native_linux
TASK41_V11_PREP=benchmarks/artifacts/task41extra_phi90_p50x50_g17x20/p0_b0_controller/prepared_saved_diagnostics_6h.json
python -m src.runners.task41_p0_contract --prepare --case B0 --b0-saved-diagnostics-6h \
  --runtime-prefix benchmarks/artifacts/task40extra_0p7nm_engineering/local_w0_wsl/runtime_prefix \
  --abi-receipt benchmarks/artifacts/task40extra_0p7nm_engineering/local_v29_wsl/abi_receipt_v29_attempt2.json \
  --jit-cache benchmarks/artifacts/task40extra_0p7nm_engineering/local_v29_wsl/jit_cache \
  > "$TASK41_V11_PREP"
TASK41_V11_CONTRACT=$(python -c 'import json,sys; print(json.load(open(sys.argv[1]))["contract_path"])' "$TASK41_V11_PREP")
TASK41_V11_OUT=$(python -c 'import json,sys; print(json.load(open(sys.argv[1]))["saved_diagnostics_output_root"])' "$TASK41_V11_PREP")
TASK41_V11_OLD=results/task41extra_phi90_p50x50_g17x20/task41extra_b0_p6_phi90_07nm_iterative__full3d_iterative__mpi1__Mna/20261022T052401.200732Z
TASK41_V11_RECEIPT=benchmarks/artifacts/task41extra_phi90_p50x50_g17x20/p0_b0/service_source_59722cca5e35eac65efead9fd27f7d7fc0c70419/task41_p0_service_receipt.json
TASK41_V11_PRODUCER=$(python -c 'import json,sys; print(json.load(open(sys.argv[1]))["contract_path"])' "$TASK41_V11_RECEIPT")
TASK41_V11_PRODUCER_SHA=$(python -c 'import json,sys; print(json.load(open(sys.argv[1]))["contract_sha256"])' "$TASK41_V11_RECEIPT")
bash scripts/run_case_in_user_service.sh \
  --task41-p0-saved-b0-v9-failed-terminal-audit \
  --producer-contract "$TASK41_V11_PRODUCER" --producer-contract-sha256 "$TASK41_V11_PRODUCER_SHA" \
  --run-root "$TASK41_V11_OLD" \
  --summary "$TASK41_V11_OLD/task40_v10_p6_candidate_summary.json" \
  --manifest "$TASK41_V11_OLD/run_manifest.json" \
  --output-dir "$TASK41_V11_OUT/v9_failed_terminal_audit/attempt01" \
  --task41-p0-execution-contract "$TASK41_V11_CONTRACT"
```

上面wrapper返回不表示审核完成。主控确认service/required-checker已退出并核对真实负结果补审后，再在同一已激活shell执行下一条；新shell须重做上述activation和变量赋值，不能创建新window。

```bash
TASK41_V11_V6=results/task41extra_phi90_p50x50_g17x20/task41_b0_v6_actual_qmetric_210fbbf2_20261020T124053Z_attempt10/task41_p0_v6_actual_qmetric_candidate.json
TASK41_V11_V9="$TASK41_V11_OLD/task41_p0_b0_v9_compact_volume_audit.json"
TASK41_V11_SUMMARY="$TASK41_V11_OLD/run_summary.json"
bash scripts/run_case_in_user_service.sh \
  --task41-p0-saved-b0-y-g-comparison \
  --v6-report "$TASK41_V11_V6" \
  --v6-report-sha256 72c01eb9a7780ba86a7d8b8de6cfc1fd25e04fead2170788a5f492cd12ebd06e \
  --v9-report "$TASK41_V11_V9" \
  --v9-report-sha256 e4db4e42b8a4f3b407ed0b00add8029f7e066aad6c38a2945d60e33ffbde7d93 \
  --v9-summary "$TASK41_V11_SUMMARY" \
  --v9-summary-sha256 "$(sha256sum "$TASK41_V11_SUMMARY" | cut -d ' ' -f1)" \
  --v9-service-receipt "$TASK41_V11_RECEIPT" \
  --v9-service-receipt-sha256 47ceec26e329d312f846f71ae575319382533947ba15bec5ba12b286c40c0661 \
  --output-dir "$TASK41_V11_OUT/saved_y_g_comparison/attempt01" \
  --task41-p0-execution-contract "$TASK41_V11_CONTRACT"
```

required-checker命令由现有service生成并写入其receipt/authorization，必须在监督下运行；不以裸checker命令代替正式补审。本机fixture仅验证选择、合同传播、真正checker调用和负结果分类；不代表工作站数据审核完成。

### V11 主控最终定向复验

最终科学改动后，资格化本机 activation 下八个直接相关测试节点（含参数化）**12 passed in 0.93 s**；覆盖负结果service选择、真实checker入口、旧成功compact路径、损坏hash/跨run/列顺序拒绝、两侧变化统计、共同donor计数语义、新窗口source接续及累计配额。Python `py_compile`、`bash -n scripts/run_case_in_user_service.sh`、`git diff --check` 通过。没有全仓测试、CI或正式工作站科学审核PASS声明。

最终日志：`benchmarks/artifacts/task41extra_phi90_p50x50_g17x20/v11_preparation_20261023/controller_targeted_final.txt`，SHA-256 `e1e7c05738de1958cb56efc46368627ec8c274a7c7e94db3a381fe6461f5f43c`。前次主控复验11通过/1失败（fixture使用未初始化window_sha）保留于同目录`controller_targeted.txt`，SHA-256 `b582ff5017fb0451f7a6d0a3fe3848591368510eb2436de57679d79bbb9cd294`。其后定位并修正selector错误导入与旧fixture缺少实际负结果结构，未放宽selector规则。编辑时遗漏activation的失败也不记作通过。

本机ABI为资格化WSL Python、PETSc complex128/int32；此处只证明本机定向测试环境，不冒充工作站ABI或正式数据审核。工作站原服务终态已退出，原写入与旧窗口不恢复；同步前仍须保全工作站未提交的历史文档。V11科学扫描及监督补审继续 **NOT_RUN / PENDING_USER_APPROVAL**，准备耗时未作完整父计时，记UNKNOWN，不并入旧科学成本。
