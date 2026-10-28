# Task43 V19：已有四场的局部误差—动作响应诊断

本轮已完成 V18 review §9 授权的保存数组诊断。**q8/q10 一致表明：P8 在目标单元内有效且方向对准，但该处只占原全域场差平方约 1.24%；H8 在目标单元内也有改善，却被闭包区和其余域的恶化超过。** 这解释了场差响应，不证明局部 R00 误差、选择器或连续真解精度。原输出精度和冻结尺度下的明确收益仍未通过。

执行过程中有一次已定位的 checker 索引错误，D2 在同一受监控 worker 内验证修复后完成两阶。另有监督偏差：代理违反“只读源码/JSON”的限定，在 D1 后执行了两次未受监控的标准库数组操作；另一次 `python` 启动以 shell127 失败。收口还发现新合同三处残留状态/launch hash冲突，详见第5节。上述缺陷单列，不隐入静态工作或合格槽位，不宣称本轮全部执行符合授权或合同元数据完全一致。最终科学数字来自独立重新完成 owner 核对的受监控 D2，未采用这些额外操作作为验收证据。

## 1. 身份、范围与数据口径

| 项目 | 实际绑定 |
|---|---|
| 分支／canonical | `task43_hp_adaptivity`；`/home/fenics/Projects/NN-Lab-V2` |
| 本轮权威 | `5586112bf5bee924cc603253a5cbf7dd6c4a0863` 的 [V18 review §9](review_report_v18.md#9-下一轮唯一执行授权已有四场的局部误差动作响应诊断) |
| 数值基线 | `405e3aff42ac421a4c99315df1ed9b96941ecbe4` |
| T1、D1 实际源码 | `8898f7e5fab82234786c51ffbd0cdeb167b379fe` |
| D2 实际源码 | `f066305d7e95b438a5ef8b223f2d5928bc6d79d9`；后续文档提交不追认为运行 HEAD |
| 数据 | 固定 R9/H8/P8/Y6_1；四份旧 NPZ、modal、Av、plan、原 comparison；路径和 hash 见[合同](outcomes/records/v19_saved_hp_response_contract.json) |
| 新增行为 | 标准库/NumPy 读取保存数组、算术分解和小 fixture；新增 PDE、场恢复、采样、背景和算子作用均为 0 |

这里的“误差”是相对固定离散参考 Y6_1 的场差，不是已知连续真误差。h 将单元切小，p 在原单元内增加多项式表达能力；本轮只解释两次已有动作，没有再次执行动作。R9/H8/P8 的 FE 为 110472/116740/110722，增加 6268/250；Y6_1 是 380160 FE，不能与另一个 6×10×6 p6 对照的 237600 FE 混同。

按原共同点权将积分分到 R9 的 180 个单元。令 `e=Y6_1−R9`、`d=动作−R9`：B 是原差异平方，D 是动作改变的场量平方，X=2Re⟨e,d⟩表示是否朝参考方向变化；I=X−D 是净改善，正数改善、负数恶化。另从 `B−⟨e−d,e−d⟩` 独立计算 I。各项拆分 E 与 curl/k0，单位沿原 nm/nm³ 及场单位；归一化使用同一个全域分母 `max(reference G norm, incident floor)²≈700000`，不把单元开方结果相加。共享背景只在差中相消；散射参考范数/下限明确复用旧 comparison，没有新造背景。

## 2. 差异在哪里，动作改变了哪里

q10 为主，q8 核稳健性。原全域未归一化 B=`0.0011175840214348934`。下表 I 同为未归一化 G 内积单位；“D 占比”表示动作场变化的空间分布，不是自由度或物理功率占比。

| R9 空间区域 | 原 B 占比 | H8 的 D 占比 | H8 净改善 I | P8 的 D 占比 | P8 净改善 I |
|---|---:|---:|---:|---:|---:|
| 请求 root4/global8，1 单元 | 1.243361895% | 4.882898933% | +1.0013599456388371e-5 | 92.051705717% | +1.3719067924065197e-5 |
| H8 必需闭包 root34/global14，1 单元 | 0.212150546% | 10.530828378% | −3.397776995376554e-5 | 7.858728105% | +1.1753099505539893e-6 |
| 其余 178 单元 | 98.544487558% | 84.586272689% | −3.0594387947085664e-4 | 0.089566178% | +5.389711173405981e-7 |

请求 box 为 `[16.5,5,−10]→[33.5,10,0] nm`，闭包 box 为 `[16.5,5,0]→[33.5,10,30] nm`。P8 没有请求 root34，但用相同分区配对。global14 是保存点/owner 与原几何 box 的唯一对应，不是计划列表第67行对应 global67。

原差异不是集中在一个单元：最大的 global8 仅占 1.24336%；前十单元合计 12.398394%。它们位于 x=16.5…33.5、z=−10…0 的十个 y 区间。按完整 z 层汇总，B 占比依次为 34.345033%（−10…0）、6.168801%（0…30）、7.885977%（30…60）、15.164530%（60…90）、25.692266%（90…120）、10.743393%（120…130）。这些只是原场差分布，不是新的选 seed 指标或目标敏感度。

P8 在请求区的方向相关度为 0.993628357，局部 B 减少约 98.73%，且 92.05% 的 D 位于此处；它并非“局部没有响应”。但原差异在别处占绝大部分，所以全域 B 只减少约 1.380956%。P8 的 180 个单元 I 均为正，没有以域外恶化抵消其收益。

H8 请求区方向相关度为 0.883378922，局部 B 减少约 72.06%。然而闭包和其余域的负 I 合计 `−3.399216494246222e-4`，约为请求区正 I 的 33.95 倍；只有请求单元 G 的 I 为正，其余 179 个为负，全域 B 增加约 29.519754%。按 `1−|净I|/(正I之和+|负I之和|)` 定义的抵消比为 0.057231156；该指标小表示负项占主导，不能误写成“改善抵消了94%恶化”。此外 H8 请求区的 E 项 I 为负（−1.479192656860199e-6），curl/k0 项为正（+1.149279211324857e-5）；局部 G 改善也不等于每一场分量都改善。

| 阶次／动作 | 全域净改善 I | 重现 G | G² 相对原 B 变化 | J |
|---|---:|---:|---:|---:|
| q8 H8 | −3.299080499681754e-4 | 4.547357272406128e-5 | 恶化29.519754% | 3.9745473239816143 |
| q10 H8 | −3.299080499682338e-4 | 4.547357272405789e-5 | 恶化29.519754% | 3.9745473239816143 |
| q8 P8 | +1.543334899197045e-5 | 3.967998186281262e-5 | 改善1.380956% | 4.020864574738603 |
| q10 P8 | +1.5433348991959785e-5 | 3.967998186280788e-5 | 改善1.380956% | 4.020864574738603 |

原 R9 的 G q8/q10 为 `3.995683423458671e-5 / 3.9956834234581814e-5`，J=`4.065061945224269`。两阶的分块符号、空间分布和解释一致，没有因这一诊断增加采样阶次。

## 3. 612 通道与 R00/T00：场差和输出并不同步

每阶完整表包含四场各 612 个复幅/保存功率、候选减 Y6_1 与动作减 R9 的带符号差和绝对差。以下是全部功率差超过原 `1e−6` 门限的项，两阶相同；其他 610 个通道键在每个候选上均未超该门。

| 候选 | 顶端 (0,0,s)：R00_s 差 | 底端 (0,0,s)：T00_s 差 |
|---|---:|---:|
| R9−Y6_1 | +4.065061945224269e-6 | −2.1482450713386503e-6 |
| H8−Y6_1 | +3.974547323981614e-6 | −2.1129819847975906e-6 |
| P8−Y6_1 | +4.020864574738603e-6 | −2.083962419685559e-6 |

H8 的 R00_s 更接近参考，但 G 反而变差；P8 的 G 改善且 T00_s 更接近参考，却仍超输出门。G 是整个体积的场差平方积分，R00/T00 是全局端口模态投影得到的输出；不能把局部 G 贡献解释成某单元的 R00 误差。J 是按旧门限归一后的完整 16 项输出差最大值，三者的最大 witness 均为 `power.R00_s`。

完整 E/curl/H-total/G/J 重现按原 relative≤3e−11、absolute≤1e−15 尺度核验，结果逐项保存在 diagnostic JSON。散射 E/H 分母/下限和聚合差复用 hash-bound comparison，逐通道保存功率差及直接聚合另行核算；没有独立重装配物理功率。`|a+δa|²−|a|²` 的代数拆分与物理功率分列，`independent_modal_power_reassembly=NOT_PERFORMED`；保留 evanescent 复幅，不从极小幅值反除物理权重。

εJ=`0.12716416232413652`、εG=`9.088158796603444e-6` 不变。H8/P8 的 ΔJ 分别 `.09051462124265441 / .04419737048566574`，均小于 εJ。P8 q10 ΔG=`2.768523717739272e-7` 仍小于 εG。H8/P8 的 ΔJ/ΔFE 分别 `1.4440750038713213e-5 / 1.7678948194266297e-4`；原冻结尺度下区间分别 `[-5.847086962584893e-6,3.472858704001132e-5]` 和 `[-3.318671673538831e-4,6.854461312392091e-4]`，均跨零。诊断提供原因解释，没有形成 p 优于 h 的接受结论。

## 4. 实现、失败、恢复与逐次费用

只新增保存数组 checker、小测试、新 V19 规则合同及任务内 launch/快照，没有修改旧三个 runner、V18 launch、数值核心、共享 watchdog、activation/ABI 或旧合同。tracked 合同不自包含 commit SHA；每个 ignored run-manifest 在源码冻结提交后绑定实际 HEAD、source/input/script/argv/env。

| 槽 | 实际结果／退出 worker/watchdog/supervisor | 入口至清理 whole 秒 | 树 RSS 采样峰 B | 测试字节 |
|---|---|---:|---:|---|
| T1 | 12 passed；0/0/0 | 4.016669398 | 107126784 | 8898f7e5…；pytest内部1.05秒，不重复计费 |
| T2 | NOT_RUN；T1通过，无使用条件 | NOT_RUN | NOT_RUN | 未运行，不可转用 |
| D1 | checker owner 索引拒绝；2/2/2；q8/q10均未完成 | 13.085514464 | 349720576 | 8898f7e5…，失败保留 |
| D2 | 同 worker 3 affected tests passed 后完成 q8/q10；0/0/0 | 88.164291237 | 892551168 | f066305d…；内部测试0.69秒，不重复计费 |
| 合计 | 3 次授权 shell 调用 | **105.266475099** | 不跨运行相加 | 不是一次最终13项批次，不声称CI |

D1 的 `EvidenceError: root target requested global cell ID/box mismatch` 来自把几何 plan 行号当成 mesh global ID。原请求 box 是 plan row66，闭包 box 是 row67；原 R9 代码按几何 box 关联而非数组行号。修复只在 checker 内从保存 owner 点组与固定 box 建立180项双射，保留 global8/root4、root34 几何以及全部输入/门限。D2 在同一受监控 Python 中先跑三项 owner/重排/加和测试，再从原数组重算两阶；D1 没有已完成阶次可复用。D1 原合同版本、快照、失败目录和记录均保留在原提交/原 root；当前 V19 合同的 owner 派生修正是新版本绑定，没有改旧科学合同。

T1 是初始12项字节证据；最终三项受影响节点覆盖 owner 修复，其余不受影响部分引用初始测试，不能拼成最终全套通过。主控静态脚本的 source-index dict/list、AST tuple/list、不存在的可选配置路径及误读 D2 `summary.json` 路径等机械错误均在读取/归档范围内修正，未重跑动态入口；实际 summary 位于 `watchdog/summary.json`。静态准备、人工审阅、归档和上述失败耗时 **NOT_MEASURED**，不补造整轮 wall。

**监督偏差单列：**两次额外标准库 NPZ 读取分别筛选 box/owner、核 `ids[slots]`，无写入、NumPy、项目/native import 或 PDE；但它们仍是授权槽外的数组诊断，不是普通文本/hash准备。另一次未找到 `python` 以127结束。准确 wall、绝对解释器、PID及两次成功返回的数值退出码没有保存，均不补造；不计成 T2、不抵扣 D2、不作为科学证据。操作自述和原脚本见[偏差记录](outcomes/records/v19_saved_hp_response_sources/unmonitored_operations_self_report.md)。主控已限制代理停止数组工作，D2 自行重新核实 owner/完整性；这不追溯消除越界事实，需外审判断监督整改。

## 5. 主控独立复核与边界

主控亲读 T1/D1/D2 全部最终 raw trace（含栈和退出尾段），分别340/177/232行；完整 getter 均为CPU1，没有 setter。正常 SIGCHLD 与已知 exit0/exit2 逐项分类。逐行解析8/28/132条资源，未见 task swap、CPU偏离、活进程失联或超限；D1 通用审计器原将非零退出标待分类，其原记录不改，本轮明确归为 checker 已知异常，不冒充成功。

D2 worker PID/start_ticks=`3615316/312156949`，直接 watchdog=`3615313/312156873`，tracer=`3615320/312156954`。开始/结束身份、CPU1、六线程变量1、局部关闭pytest插件自动加载、原资格化解释器/NumPy1.26.4均有原值。没有使用 MPI，不以环境变量声称MPI/ABI资格。D2 watchdog内部86.53078653058037秒；入口whole88.164291237秒，末行资源86.39749308582395秒且exit0、无后代；已记录的本任务进程在 host 复查时全部不存在。

所有动态槽受8GiB及原64GiB/15% reserve门取严约束，task swap峰0；全局swap单独记录。RSS是同步采样树峰，不是连续高水位。trace始于taskset之后，短命子进程未被采样者没有start_ticks；空cache metadata也不能证明缓存稳定，均不扩大保证范围。

主控另用标准库从**已完成 CSV/JSON**逐单元独立核算 `X−D` 与 `B−after`、E+curl=G、三块加和、全域G、完整612差值/超限、幅值平方恒等式和16项J最大值。q8/q10最大全单元相对算术偏差分别 `1.405140784852484e-15 / 1.1942041466872019e-15`，均小于 `1e-10`。这不是重新打开原NPZ、重跑checker或新增支持driver。原数组dtype/shape/hash/finite、565248/1104000点、正权、350000nm³、owner/42数组目录由受监控D2实际核验；主控读取这些运行manifest并核来源，不能冒称自己再次执行了原数组计算。

旧 V18 F/C 退出窗口、三条 F setter 与栈、身份/清理摘录及原42数组复核JSON已按§9.2复制/摘录，保留原hash、原行号、epoch/monotonic区别，没有重跑旧审计器。通用resume接口只在fixture覆盖，D2没有使用 `resume-from`；不授予未来任意恢复资格。最终资格依据 D2 data manifest、runtime end、watchdog/launcher 和主控终态联合读取，不能只凭较早写出的 diagnostic成功标签。

**合同元数据收口订正（保留运行原字节）：**最终静态审阅发现三处遗漏：`contract_state=FROZEN_REVIEW_CANDIDATE_NO_DYNAMIC_AUTHORIZATION` 没有随本轮授权执行更新；`no_follow_on_authority` 仍写 T2/D2 未启用，与 `execution.slots.D2.armed=true`、`recovery_reason` 冲突；`entrypoints.stage_launch.sha256` 仍为旧值 `87b60b762bb9b9977727d4ccfef82891b774c9ee832c092d3b11ed10026aa52d`，而 `launch_files` 同路径条目、tracked归档、实际脚本及D2 run-manifest一致为 `fc9db4ce99b0bcc1bf912acf5d4d0cdbe0c7c76b37ba78674ff03dd857e2b8f2`。这是主控冻结预审漏项；不能宣称所有合同声明一致，也不能将旧hash解释为实际运行hash。

当前事实由V18 §9.8的D2条件授权、提交前恢复决策、真实source/launch快照和最终终态分别说明：D2已执行且用尽，T2未执行且不可转用，没有下一次运行权。此处明确订正读法，但不事后改写已消费的合同/快照，不声称历史冲突因此不存在；实际来源可追溯不等于合同整体验收通过。D2数值诊断完整，**工程整体资格保留合同一致性与监督偏差待审项**，不新增运行来掩盖元数据问题。

收口仅做 JSON、复制 hash、新增相对链接及格式静态核对，未因文档变化重跑测试。首次全文件链接检查命中了模型总账中未改动的 Task40 临时 receipt 旧断链，保留失败并限定复查新增 V19 链接；不借此修写历史。默认 `git diff --check` 将四份原样CSV的CRLF报为尾随空白（exit2）；保留原字节，仅命令级 `core.whitespace=cr-at-eol` 检查通过，不改共享Git配置。详见[静态收口记录](outcomes/records/v19_saved_hp_response_sources/static_delivery_validation.json)。

## 6. 交付、权限与下一步

- [机器结果、实值、费用和身份](outcomes/records/v19_saved_hp_response_results_v1.json)
- [q8：180单元表](outcomes/records/v19_saved_hp_response_sources/decomposition_recovery1/data/q8/cells.csv) · [612通道表](outcomes/records/v19_saved_hp_response_sources/decomposition_recovery1/data/q8/modes_612.csv) · [逐项诊断](outcomes/records/v19_saved_hp_response_sources/decomposition_recovery1/data/q8/diagnostic.json)
- [q10：180单元表](outcomes/records/v19_saved_hp_response_sources/decomposition_recovery1/data/q10/cells.csv) · [612通道表](outcomes/records/v19_saved_hp_response_sources/decomposition_recovery1/data/q10/modes_612.csv) · [逐项诊断](outcomes/records/v19_saved_hp_response_sources/decomposition_recovery1/data/q10/diagnostic.json)
- [主控表格核算](outcomes/records/v19_saved_hp_response_sources/root_scientific_table_audit.json) · [原件副本索引](outcomes/records/v19_saved_hp_response_sources/delivery_copy_index.json) · [D2决策与D1失败](outcomes/records/v19_saved_hp_response_sources/d2_recovery_decision.json)

工程结论：D2的固定保存数组诊断完成，外审需同时处理上述监督偏差与合同元数据冲突；不宣称整轮无偏离。科学结论：P8局部有效但全域影响小，H8域外恶化占主导，G与R00/T00不同步；两阶一致，但输出精度和明确收益仍未通过。合并结论：没有任何merge approval，研究代码不提升production默认。

正式新增0，历史9/10且末槽封存；旧支持槽不恢复，T2不可转用，D2已用尽。accepted9/R9、R10拒绝及全部历史失败保持。空间PARTIAL；选择PARTIAL；精度NOT_PASSED；同精度全过程成本NOT_ESTABLISHED；迭代NOT_RUN/NOT_QUALIFIED。未生成transition10。下一项科学动作和预算需正式审阅明确指定；本轮不继续计算，不提交master、不合并。
