# Task41extra Response V11：全域变化定位到缩减侧，局部数值重放未获时间准入

本轮是审阅V9执行及V10准备落实后的窄续作。**已完成受监督失败补审、V6/V9完整保存向量分解，以及87567行完整关联单元定位；没有完成该行的候选数值重放，也没有修复全域action。** V9仍FAIL，candidate恢复、200q与原尺寸完整求解仍未运行。

## 1. 实际科学结果与边界

这里的“作用y”是给定场经过离散算子的输出，“缩减RHS g”是消去内部自由度后的右端项。分别比较两侧，才能知道总差y−g变大来自哪里；这不需要重建已退出的全域owner。

| 保存数据比较（原冻结分母不变） | 列0 | 列1 | 结论 |
|---|---:|---:|---|
| Δy=y9−y6 | 0 | 0 | 两份完整y文件SHA相同 |
| ‖Δg‖₂ | 6.723134900297747e-7 | 1.4118220109544058e-6 | 只在trace，port为0 |
| ‖Δg‖₂/D | 3.02098024405359e-10 | 6.343896863043521e-10 | 不是新通过门 |
| V6 ‖d6‖₂/D | 1.718320912670999e-10 | 3.618052243395783e-10 | 原FAIL保留 |
| V9 ‖d9‖₂/D | 2.6749770637124364e-10 | 5.613598120039757e-10 | 原限1e-11，仍FAIL |
| 87567行占V9误差平方和 | 0.00627258% | 0.00664272% | 只是机制探针，不能代表全域 |

D分别为2225.481253487629、2225.4807123031883。读取范围为5752120×2 complex128：5688000 trace rows及64120 ports。独立分块统计重算了Δd=Δy−Δg、有符号内积、平方和、top-k及交叉y9−g6/y6−g9。两列有符号交叉项为−2.4384680445423955e-13、−1.0808341277076866e-12；误差平方和增加2.0815862442177648e-13、9.124072629076552e-13。能量恒等式浮点余差0、−2.0194839173657902e-28。top10仅占V9的d9误差能量约0.04693%/0.04287%，误差并非集中在一行。完整数值、符号及索引见[原始比较](outcomes/v11_closeout/runs/saved_y_g_comparison/attempt02/task41_p0_b0_saved_y_g_comparison.json)。

**可排除本次跨run恶化来自y侧变化或port变化；尚不能将它全部归因于GETRS、J乘法、重建矩阵或累加次序。** 旧全量逐key LU/J数值hash不齐，新局部数值未产生；同名evaluator/key不能证明旧内存逐位相同。本轮没有提出未经证据验证的第二种算法。

## 2. 失败终态补审与87567局部包

新受监督补审完整读取V9真实compact及两NPY，audit_completed=true、data_integrity=true，复现action FAIL，recovery=NOT_RUN_ACTION_GATE_FAILED、official=false。旧V9 service terminal checker的NOT_RUN不倒填为成功。新补审与旧compact audit是不同consumer/source/window，见[补审原件](outcomes/v11_closeout/runs/v9_failed_terminal_audit/attempt03/task41_p0_b0_v9_failed_terminal_audit.json)。

87567 active行经保存编号映射为original250113。metadata-only检查得到全部incident cells **[360,446]**，包含对周期slave贡献的检查；本行实际两份系数均为1+0j，不能外推其他行。cell360为tag2/permutation4680/local trace375，cell446为tag1/permutation0/local trace75。actual坐标、I/T位置、完整E映射及hash均已保存，可直接接续，无需重建这批metadata。

| selected attempt | 实际结果 | 数值是否开始 |
|---|---|---|
| attempt01 | donor budget读取了错误层级，后续未初始化budget错误曾覆盖首错；已修并保留旧失败 | 否 |
| attempt02 | COMPLETED_METADATA_ONLY；完整关联数2≤8 | 只有FE/MPC元数据，无候选张量 |
| attempt03，source 2b085de826b6cddf5727c68e53359f56d2fadaf1 | 误把账本path与window JSON path比较；保留原失败 | 否 |
| attempt04，source f1697498699d9b4c2c4c4919b97e4a1e2bba22f5 | 身份接线已通过，CANDIDATE_NOT_ADMITTED | 否 |

attempt04在2026-10-23T10:44:28.135394Z的真实数值余额**996.109秒**，低于已登记900秒工作估计＋120秒终止预留=**1020秒**。这是**时间准入停止**，不是截止瞬间杀计算，不是新数值FAIL，也不是内存不足。没有降低估计/预留来重复启动，没有刷新T0。普通工程错误及准备消耗了当前窗口；不能把全部六小时写成数值计算时间。

当前没有新candidate K/G/J/L、LU/R/T/S或该行y9/g9重放结果。局部诊断代码已接通，但不得以fixture或metadata通过替代真实局部资格。原完整action/recovery状态不变，200q保持锁定。

## 3. 时间、内存和清理

父service包含其watchdog/checker子段，**下表父子不能相加**。tree RSS为同时采样的进程树口径，cgroup、systemd另列在原件；PSS未采为null。

| 本轮阶段 | service父秒 | 已记录子秒 | tree RSS峰值B | 状态 |
|---|---:|---:|---:|---|
| 失败终态补审 attempt03 | 175.031547463 | 见原watchdog | 552013824 | 完整审核，确认负结果 |
| 全域y/g comparison attempt02 | 39.381449460051954 | checker24.584（约） | 1132597248 | 分解完成 |
| 87567 metadata attempt02 | 111.71154267387465 | watchdog98.68195200897753 | 2603089920 | cgroup2336821248B，metadata完成 |
| selected attempt03 | 47.917511329986155 | 36.088314762338996 | 671997952 | 接线错误，未数值 |
| selected attempt04 | 49.320757986977696 | 37.93014527019113 | 671363072 | 时间未准入 |

attempt03/04的watchdog cgroup峰为497053696/498778112B；稍后systemd读回491286528/299757568B，采样范围不同，不与tree数相减解释“节省”。所有已核验运行task swap0，后代已清场；末两次宿主swap-in/out增量均0。原监控字段global scope遗留“WSL”标签，但实际执行主机为native fenics-ws，不能据该标签认成本机WSL。原service numerical_work_started=true表示worker已启动；新compact明确两attempt候选张量阶段未开始。required_checker=not_applicable_local_candidate_replay不是独立数值PASS。

固定窗T0=2026-10-23T05:21:04.242015987Z，数值截止11:01:04.242015987Z，总截止11:21:04.242015987Z；window SHA bc646b17157eed567e2c5391df79e4eda681ab4028f9e86901e8c7fcfd9222b4。旧V9费用/unknown保留，未刷新。账本快照的采样时刻、累计收费及尚未结算的收口边界见[窗口快照](outcomes/records/v11_campaign_snapshot_20261023.json)，各service排他父账见[阶段账](outcomes/records/v11_service_stage_ledger_20261023.json)。本轮收口采样累计收费20085.307234秒（包含工程准备/等待/服务，不能另加各service父时间）；该采样后最终commit/push成本尚未计入此快照。工程准备/等待计入窗口，缺少历史细分的部分继续UNKNOWN，不用父时间差猜热点。

既有cap1.5TiB、host reserve64GiB、task reserve0、MPI1/math1、complex128/int32不变。旧累计raw14990282640B，本包上限512MiB、累计16GiB、磁盘底线2GiB；原NPY未复制或改写，没有新增全长差数组。轻量记录的实际字节见证据索引，不能把这些小进程峰值外推为完整模型内存。

## 4. 修复、验证和可直接接续产物

本轮修复现有失败service产物选择与监督审核、y/g checker的consumer环境传播、metadata预算真实字段/首错保存、局部候选重放的生产累加次序与同LU返回量检查，以及末次账本path接线。没有新PC、全仓重构或新环境。

最终科学source：**f1697498699d9b4c2c4c4919b97e4a1e2bba22f5**；最后一处修复父source：2b085de826b6cddf5727c68e53359f56d2fadaf1。真实metadata提炼fixture保留正/错路径判别。主控本机资格化ABI下1 passed/0.06s，执行者1 passed/0.15s；之前直接受影响5项回归通过。diff检查通过；未跑全仓测试，未声明CI，ruff本机不可用未记通过。详见[test summary](outcomes/test_summary.md)。

下一次只需在新的明确授权窗口下：复用attempt02 metadata及全部保存donor → 构建cells360/446缺失candidate块并逐cell持久化 → 原生产顺序分别重放保存y9/g9 → 复算同LU残差缩减与各有符号项。完整operator/source/hash检查保留，不重做全域分解或旧恢复，不新建约19小时owner。即使该局部重放完成，也只提供覆盖约0.0063%/0.0066%误差能量的一行机制证据，不自动准入全域、200q或最终求解。

实际service argv、activation、consumer合同及旧donor引用保存在attempt04原收据，当前固定窗不能作为未来可直接启动许可。精确旧metadata与原始负结果路径/hash见[证据索引](outcomes/v11_closeout/evidence_index.json)和[compact](outcomes/b0_v11_saved_diagnostics_20261023.json)。所有大数组仍在fenics-ws:/home/fenics/Projects/laptop_share下ignored results；本次只推送当前执行分支，不合并master。完整场、最终精度、2TB/48h均未通过。
