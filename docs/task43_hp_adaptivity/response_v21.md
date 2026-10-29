# Task43 Response V21：H67 空间门通过，正式 F1 的独立 A6 门失败

> 当前结论：一次 R10_H67 局部 h 细化通过了实际空间自由度门，但正式 F1 的独立 A6 原方程残差为 `2.1004005221911206e-8`，超过 `1e-8` 上限。F1 因此不是合格候选；C、F2、E1、E2 均未运行。accepted9/R9 不变。

## 本轮做了什么

V20 review §9 授权对被拒绝的 R10 诊断父态做一次单层局部 h 细化：请求单元是 global67 / forest root127，物理盒为 x=[16.5,33.5]、y=[10,15]、z=[90,120] nm。直观地说，h 细化把一个较大的有限元单元切成更小的单元，以改善局部空间分辨率；它改变网格和未知量数量，但不改变材料、物理方程、阶数或参考模型。R9/accepted9 保持唯一接受态，R10 继续只是被拒绝的诊断父态。

全程冻结 p6、q15/q28、Av 材料积分 q15、R13/612 通道、MUMPS、normal correction=1 和 extra correction=0。S/F实际构网，F实际装配、分解并求解一次；C没有启动，故没有新的共同点采样或比较背景重建。Av q15是冻结设置，实际Av积分和form留证尚未到达。没有变更共享数值核心、watchdog默认、activation或ABI，没有消费holdout/control，也没有新候选接受或状态迁移。

## 阶段结果

| 阶段 | 实际结果 | 解释和边界 |
|---|---|---|
| T1 | 16 passed、1 failed | 唯一失败为 `test_10_v21_pending_reader_recomputes_rebound_raw_packet[True]` 的异常文本正则不匹配。reader 正确拒绝混包，实际错误为 `V11 full-active reduced RHS/solution/residual do not match the returned system`；测试却期待 `saved raw-vector gates`。这是断言文字问题，不是 reader 放行。whole 95.217966388 s。 |
| T2 | 受影响的 3 个节点通过 | 只修正正则后重跑 runtime、raw valid/mixed 三节点；3/3通过。whole 9.091490977 s。它不是一次完整 T suite 重跑。 |
| S | 空间自由度门通过 | 215个叶单元，5次实际 split；FE=139,554=42,804 trace+96,750 interior，满足 `118800 < FE < 237600`。请求 root127；材料闭包 roots129/130/131/160，共4个；balance/periodic闭包均为0。carrier=151,032，hanging slaves=5,544，periodic slaves=5,934。returned rows=43,416是预测值，不是实测。whole 207.789824667 s，RSS采样峰1,419,935,744 B。 |
| F1 | **FAILED_OR_INCOMPLETE，非正式候选** | 唯一失败的 primary gate 是 `independent_A6_raw_relative_le_1e-8`：`2.1004005221911206e-8 > 1e-8`。full-active residual=`6.446061507221647e-13`、returned-condensed residual=`6.902765176289437e-13`，各自通过；但不能替代独立 A6 检查。normal correction恰好一次，把相对残差从`1.5364631556420623e-10`降至`6.902765176289437e-13`；extra correction=0。终态为`FAILED_OR_INCOMPLETE` / `failed_or_incomplete_nonofficial_h67_primary`，`official_result=false`、`endpoint_record=null`、selection与transition关闭。 |
| F2 / E1 / E2 / C | **NOT_RUN** | review §9.8 在 F1 数值门失败后不允许调用这些阶段。没有 q8/q10 端点、J/G、Av、改善量或接受结论。 |

A6 是独立路径重新检查完整原方程的残差，确认求得的场不只是满足某个经过凝聚或缩减的返回系统。F1 的缩减系统残差很小，但独立 A6 超过约定阈值，所以这次场不能升级为正式候选。这说明这一次运行未通过门槛；不表示该模型在所有网格或所有设置下都不可计算。

实际自由度代价是相对R10的118,800增加20,754（约17.47%）。F正式装配已实测returned矩阵43,416×43,416，NNZ used=37,660,296、allocated=45,453,492；它与S的行数预测一致。空间满足目标范围，但输出收益尚未建立，不能把较低自由度本身当作精度成功。

## F1 终态、资源与证据边界

F1 root 为 `benchmarks/artifacts/task43/v21_r10_h67/formal/R10_H67_attempt1`，运行 HEAD 为 `5796d78b642b58c0963ef47d181f70b96b728786`。从 launcher 入口到终态记账为 `4,813.658310916 s`；watchdog 自身记录的 elapsed 为 `4,811.279815596 s`，二者是不同计时边界，不相加重复计费。7200 s whole limit 通过；launcher/watchdog终态码均为2，未记录外部信号；worker exit=1，watchdog分类为`WORKER_FAILED`，并已清空后代。

watchdog记录6,904个资源样本，进程树RSS采样峰为`7,900,602,368 B`，task VmSwap峰为0。root读完1,859条trace；第6,900号资源样本有一个worker `vanished`，其后四条资源记录均无后代，这是退出竞态，不能写成“全程没有 vanished”。主控全流检查没有报告trace/resource解析问题。**worker自身的source/input结束快照没有到达**；主控退出后另行进行的source/input哈希核查单独登记，不等同于worker端结束快照。共享缓存监测列表为空，因此没有共享缓存稳定性结论。

完整42数组包虽已保存，但它对应的primary被明确标成`official_result=false`，且独立 A6 门失败；“数组文件完整”不等于“primary合格”。失败前写出的端口功率中间值 `R_total=0.25135798908917745`、`T_total=0.05712756085951156` 不是通过门后生成的 official R/T/A；体积吸收Av和完整summary没有到达。不能从这些中间值推断J/G、R10_H67收益、每FE收益或R10对R9的合格优劣。

主控用标准库读取全部42组NPY原始字节及头部，核对11组恢复系数/网格/dofmap与早期检查点的身份，并独立核算保存标量的范数比值和全部612行模态功率求和。A6为`2.2197718044678094e-8 / 1.0568326283561202 = 2.1004005221911206e-8`，是上限的2.1004倍。这里没有在监控外重新计算场数组范数或施加算子；数值原数组审计来自F1 worker。A6与凝聚残差差异的具体分量和原因仍为UNKNOWN，本轮未开启原因扫描。

审阅入口为[机器结果](outcomes/records/v21_r10_h67_results_v1.json)与[来源和终态证据目录](outcomes/records/v21_r10_h67_sources/)。S独立空间审计在`benchmarks/artifacts/task43/v21_r10_h67/support/space_attempt1/root_independent_audit.json`；F1主场原件位于`benchmarks/artifacts/task43/v21_r10_h67/formal/R10_H67_attempt1/`。证据记录中的source/input清单和worker结束后hash核验应分别阅读。

## 测试、费用和当前资格

支持阶段T1/T2/S共3次，whole合计`312.099282032 s`；本次F1是1次正式调用，launcher入口至终态为`4,813.658310916 s`，按上述两个阶段记账合计`5,125.757592948 s`。F1 watchdog elapsed另为`4,811.279815596 s`，不可再叠加到该合计。正式额度当前10/12；支持额度当前3/7。F2/E1/E2/C不得因剩余额度而自动启动。T1、regex修正后的T2和F1分别使用HEAD `535b23d6274b750ab8a8ffd55faf4048d93c1b2e`、`5796d78b642b58c0963ef47d181f70b96b728786`、`5796d78b642b58c0963ef47d181f70b96b728786`；阶段身份仍按各自manifest记录，不拼成单一源码身份。

最终测试文件SHA256为`456d2c31f0b8b99d634bed2d0a05c6127b0f56d4d06aa4f2518a13e5c63bec5c`。17个不同节点中，14个复用T1未改变的通过证据，3个在T2实测通过；不是一次最终17项批次通过。T3未调用。历史最后一槽仍封存，F2剩余额度不适用于本次数值失败。C只有fixture覆盖，真实三场恢复/采样路径未验证。

静态收口另有两次文件打包失败：先误要求T2存在未创建的可选phase文件，随后派生索引的空字段兼容检查失败；均局部修正并保留记录，没有调用stage shell。更早的静态路径和主控草稿纠错见机器结果。文档/人工检查部分费用为NOT_MEASURED，不补造整轮总wall。主控最终三项已测静态复核分别为1.3856730270、0.4737555841、0.5149478870秒，单列而不混入工作流费用。

最终文档静态核对解析了52份JSON、检查17个当前相对链接和6张当前表格，未发现问题；该次标准库检查耗时0.055181717秒。review与最终测试文件hash仍匹配冻结值，未因文档更新重跑动态测试。

暂存后全量`git diff --cached --check`发现T1原字节`tests.xml`中的12处历史错误栈行尾空格。该XML按原件hash复制，为保留失败证据不修剪；排除此原件后的新增文档/代码格式检查通过。该次检查失败不是新增测试或运行，耗时未单独计量。

## 对V20问题的回应

| 问题 | 本轮处理与未闭合处 |
|---|---|
| V20-01 | 实际执行唯一H67，但独立A6硬失败；J/G及612通道对参考的响应没有完成，科学问题未闭合。 |
| V20-02 | 显式保留R10=REJECTED、accepted9/R9不变；真实S空间合格。新共同分区有fixture验证，真实C未运行。 |
| V20-03 | 使用本轮固定阶段身份、输入快照和新路径测试；不授予历史别名或通用恢复资格。 |
| V20-04 | 主控读取新trace/resource/primary原件、核全612模态表；轻量摘录和原件hash可外审，完整原数组仍在工作站。没有补跑旧审计器。 |
| V20-05 | 仅增加opt-in研究组合、测试及合同，未改共享核心；旧四槽标题已澄清。研究入口增量仍须代码审查，不因工程测试通过而获得生产资格。 |

| 能力 | 当前状态 | 本轮根据 |
|---|---|---|
| 空间 | PARTIAL | H67单次空间审计通过，但不是已接受模型 |
| 选择 | PARTIAL | 没有经过qualified端点的误差选择结论 |
| 精度 | NOT_PASSED | F1独立 A6 raw residual超限；Av/J/G未到达 |
| 同精度全过程成本 | NOT_ESTABLISHED | 没有合格端点和精度匹配比较 |
| 迭代 | NOT_RUN / NOT_QUALIFIED | 本轮没有迭代资格化 |

accepted9/R9仍保持，R10/H67不接受；不授予新的运行或自动恢复授权，也没有生产资格或merge approval。V20四槽失败、U1及更早历史保持原记录，不追认、不回写。
