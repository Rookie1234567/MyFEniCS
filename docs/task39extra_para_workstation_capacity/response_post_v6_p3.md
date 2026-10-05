# V6收口后追加p3候选：执行回应

本回应记录用户在Review V6收口后追加的“细层p6、粗修正p3”候选，不新建或伪称Review V7，也不回写V6历史结论。p3粗修正使用实际A3离散与准确MUMPS因子。已完成的18-cell组件只运行三次固定完整PC见证，没有外层FGMRES迭代；拟议正式5 nm路线才会由right FGMRES(32)求解p6凝聚trace加全部600个port空间。原完整未凝聚p6 A6继续用于full residual与相关核验，Aq、模式和物理门限保留。

## 本轮状态

| 项目 | 结果 |
|---|---|
| canonical共享迹传递 | 仅新显式V6_P3 profile启用；每局部映射432条p6细层迹行由共享边/面参考映射构造，450条内部行沿用原Basix；原owner绝对门`1e-11`不变。 |
| 5 nm / 2 nm组件 | 两个18-cell组件均由主审按各自有限scope接受；5 nm全port数600、2 nm全port数3904；各三次固定完整PC见证，每次两个C通过A3/端口检查，一个symbolic、一个numeric、8次solve、无额外精化。外层FGMRES没有在组件中运行。 |
| 组件资格边界 | 只证明已测真实FE/MPC组件与复用路径；完整5 nm/2 nm场、收敛、R/T/A新资格均未建立。 |
| 失败证据 | 5 nm曾有一次不适用`Di>0`夹具断言和一次原1e-11 owner Gate超限；均保留。阈值未修改，最终候选未过滤失败行。 |
| 资源/时间 | 2 nm组件RSS峰3.351 GB、watchdog清场；build 221.760 s不等于完整setup。5.145069 s PC均值对旧q4仅非配对小组件比较。 |
| 唯一5 nm完整回归 | 已按批准包启动；完成544个outer步后被watchdog归类`USER_CONTROLLED_STOP`。最后Schur `0.0036393393688062795`，最近独立原A6为step536的`0.0038091382027435404`，高于`1e-6`。 |
| 终态资格 | `NOT_QUALIFIED_INCOMPLETE_INTERRUPTED_RUN`；完整场/EH/modal/RTA/checker未完成。停止分类不能识别入站信号sender或signal编号，不能称用户亲自停止；不是数值Gate失败判定。 |
| 下一步 | 不重启、不续跑、不自动进2 nm/0.7 nm；只提交本次既有证据的轻量归档草案供主审复核。 |

详细指标、失败、hash和范围见[S3结果](outcomes/p3_mid_order_s3.md)、[组件compact](outcomes/records/p3_mid_order_s3_components_v1.json)及[5 nm终态compact](outcomes/records/p3_full5nm_terminal_compact_v1.json)。全场5 nm启动前命令草案保留在[p3_full5nm_p3_regression_launch_draft_v1.json](outcomes/records/p3_full5nm_p3_regression_launch_draft_v1.json)。

## 数值和范围边界

`P63`是把粗空间p3的修正映回细空间p6的矩阵。canonical共享实体映射改善了同一edge/face迹在相邻单元的浮点一致性，保存C2包原Gate复放由8行超`1e-11`变成0行超限；这不是把p3基函数任意当作p6低阶内部基函数。2 nm `Di`与诱导内部端口RHS均处近舍入量级，不称强耦合压力见证。旧`P4_RETURN_PASS`字符串只是共享状态枚举，实测算子字段为degree3/A3。

5 nm草案的自动完整同离散比较仍由现有profile映射进入旧的`compare_retained_5nm_output`，其旧5 nm同物理全场/600模式见证路径与独立已合格V6 F5性能记录分开。比较项和阈值照Review V6 §4，不把V6 F5写成当前runner的直接自动pair gate。runtime必须记录真实boundary-fitted cells；输入名义`[13,7,35]`不能代替同离散参考的3780实际cell数。

正式完整5 nm唯一p3尝试绑定clean运行source `2b0a7c1d6e5a20c5d0323469cd018deeb73898c2`，现已按上节记录为中断。本轮追加p3范围没有启动2 nm p3完整场、没有重跑或续接既有V6 q4 P2限域pilot，也没有启动0.7 nm模型；已有V6 q4 P2仍由原记录单独描述。没有再做p4逆研究，也没有改默认或V6历史结果。

## 唯一5 nm p3完整场终态

运行`20261004T085614.837316Z`绑定clean source `2b0a7c1d6e5a20c5d0323469cd018deeb73898c2`、p6/h4细层与A3/p3粗算子；stage记录真实3780 cells、600 modes（SHA `dde3aee7ee25bc5d68617a503eebec720a1527c9d044125bfb09acaa6d0b6645`）。workflow起点到solve同钟setup为`1117.064241 s`。symbolic/numeric API为`2.104244/69.681804 s` wall；H6 diagonal `5.026990 s`、power10子项`93.157356 s`、H6 parent `107.943479 s`，都是嵌套计时，不相加。

watchdog的`USER_CONTROLLED_STOP`只表明父进程接收SIGINT/SIGTERM的处理路径，sender与信号号未保存。stop event为`2026-10-04T17:20:08.361441Z`，清场end为`17:20:12.868272Z`；主审于`17:22:54Z`确认原进程已消失。run_summary full workflow为`30238.071031911997 s`；root CLI exit 3由peer exec session 52614读回，与run_summary、worker及watchdog leader exit 1分列。最后完整outer为544、Schur residual `0.0036393393688062795`；A6最近已完成检查在536为`0.0038091382027435404`，step544没有已完成检查记录（`NOT_RECORDED_COMPLETED`），运行可能在该检查进行中被中断。最新512检查点为solution-only、residual `0.004015580499214017`，不承诺免setup恢复。`iterations.jsonl`末条`last_logged_solve_seconds`不是正常KSP返回API计时，后者unknown。

与既有q4 F5只比较相同i0→i120的`solve_seconds`窗口，再除以120：p3 `52.973319714 s/step`、q4 `79.389986392 s/step`，观察值比`1.49868x`。该口径包含窗口中的监控和输出，但不含i120回调后A6检查；两场不是配对控制，也不等于总time-to-solution。相同step120的原A6是p3 `0.0489090873604`、q4 `1.06532658799e-6`。较低单步时间没有弥补p3的收敛退化，因此本run未取得数值或物理资格。

watchdog summary报告93536样本、RSS峰`18428985344 B`、tree swap峰0、PSS disabled、hard RSS线`1300000000000 B`、无时限和后代清场。约995 MB资源日志未全扫；仅核首尾样本并与summary交叉，末样本距clock_end `0.046385312 s`，全程样本可读性仍unknown。全机pswpin增10页/pswpout增0页的归因unknown。终态和匹配窗口的主审回执hash见[终态compact](outcomes/records/p3_full5nm_terminal_compact_v1.json)。

## 原13.5 nm p3 anchor 回归：保存场对照已接受（2026-10-05）

按追加授权，本轮在原13.5 nm/990-cell/80-mode模型上完成唯一p3 anchor：run `20261004T235056.532239Z`，source `a1a1e78a74a5497d7929a67f1de686965f30a066`，input `629b76c7ad6b187081ce10fb15c440e48eacf219eedfb7eb400d64c9f1243b8f`，physical `255837330af27827d15ef43dfb01876187589a3b5e129f1d0882e24b955484c0`，resolved `ad46d0c168805006e0b9c9a14fdefb9cb7ec6cb097e2c73910762600184ddd59`，80-mode SHA `d4380495d912f97f6d303a85756bb9b252a1117bad229b559f0ac8140e745fbb`。实际粗算子degree为3/A3；run自然exit0，361步，原A6 `9.454573485808941e-7`，独立输出门通过。candidate classification及reference authority均保持`BALANCED_OUTPUT_AUTHORITY_LIMITED` / `REFERENCE_AUTHORITY_LIMITED`。

| 同离散保存场对照 | measured差异 | 原限值 / 结果 |
|---|---:|---|
| 全场FE L2、scaled-curl | `6.0856e-10`、`6.1301e-10` | 各`1e-4`；PASS |
| 同坐标E/H、80-mode幅值 | `6.56e-10`、`6.11e-10`、`5.23e-10` | 各`1e-4`；PASS |
| 每通道R/T功率最大差；总R/T/A/A_volume最大差 | `3.11e-11`；`4.89e-10` | `1e-6` / `1e-5`；PASS |

与V5工作站保存场的比较状态是`NUMERICAL_PAIR_PASS`，由主审receipt `3c6dc11b5db883a659e0d354ee4b49f57b509572e49a19f3e406571fbfb2af41`接受为**原13.5 nm模型回归**。这是保存数组比较，不提升reference authority，不表示“p3核心新迁移成功”，也不外推5/2/0.7 nm。

旧→新工程计时：setup `5295.217→431.617 s`（12.27x）、KSP API `5521.324→5076.041 s`（1.09x）、workflow `10997.373→5709.358 s`（1.93x），两场均361步。准确A3 numeric前后的budget→numeric完成marker区间为`6.575→7.866 s`，没有变快；该区间不是独立MUMPS API计时。p6 build `4702.709→29.773 s`、A3 build（旧兼容字段名`p4_build`）`125.699→3.220 s`。新场实测raw geometry仍为96类；旧工作站V5实际记录raw tensor classes也为96，round12的12组是从保存geometry推导。新场tensor evaluations/groups为96→12，组键round12但代表坐标不舍入，属于显式近似分组。oriented Schur/LU类保持139→139，不能把tensor组变少说成实际几何类减少。父子计时重叠且两run非受控AB，不能将差异归因到单一优化。

本场资源审计17924样本，RSS峰`5294153728 B`、task swap0、PSS关闭、后代清场；global pswpin +1/out0页归因unknown。资源日志审计执行“一次JSON解析加一次顺序读取末行”，不是严格单遍文件I/O。比较子进程watchdog exit0、133.698 s、419样本、RSS峰`784523264 B`且清场。

### M0迁移链与当前入口差异

本轮原始问题是核实task39extra既有p3方案的迁移，并据证据评判0.7 nm。donor closure source为`3804ede8acfd120d0d8d312415ec5e7a2c296cd7`，V25 Q3源为`cad282e25ed53cad1f9e4a5a70c14f3dd40e6d32`（13.5 nm、p6/h7.5、990 cells、80 modes、361步、A6 `9.46014e-7`）。该路线此前已经在工作站source `6d989b4b9cbca12fcc35455d7ff381e66ef7ca6d`上完成同模型361步，A6 `9.467909430661342e-7`。所以当前a1a1e78a74a5497d7929a67f1de686965f30a066 run是V6显式入口的anchor回归，不是首次迁移或“新p3核心迁移成功”。

M0核对的核心流程仍是BAL_H按C→A→H→A→C、随后`zc+s-t`；粗解为准确A3/MUMPS因子。donor V25 默认安装`InexactBalanceLedger`，首次及每32次PC调用做额外`A(z)`与`PH(q-Az)`诊断，并按`1e-8` fail-closed 分类；通过时不改返回向量。成功的6d989工作站V5和当前V6未安装该ledger，所以差异是诊断/失败分类工作，不是已证实的通过向量变化。外层restart仍由`setGMRESRestart(32)`固定，input `outer_restart=0`不表示无restart。P/PH保持同一transfer与伴随关系；新V6 p3仅显式启用canonical共享边/面P63 trace映射。几何历史分三段：donor cad282 将 widths round12并用舍入width重写非零canonical坐标；6d989工作站V5显式使用`raw_unrounded`；当前V6 p3只将round12用于group key，代表坐标保持未舍入。本场raw geometry仍实测96类，tensor evaluations/groups 96→12，oriented Schur/LU 139→139；12是近似分组数，不是raw几何类数或精确等价。H6优化属于已有reference-metric/direct-natural路线；未发现BAL_H数学次序改变，单场H6 timing不能隔离归因。各阶段源码行与blob hash见[anchor compact](outcomes/records/p3_anchor_13p5nm_saved_field_pair_v1.json)。

### 0.7 nm容量/精度证据与缺口

既有planner按100×50×280轴得到1,400,000 cells和32,060 modes；周期拓扑公式派生p3/p4保留骨架加ports为63,122,060 / 117,792,060行，p6外层背景为277,592,060行。约65个p6维度complex128数组的`288,695,742,400 B`只是条件向量payload，不是RSS。P2控制中backend原始INFOG[22]=916713 MB；按cell比例推到约23.621 TB是敏感情景，单位/bytes换算与精确factor fill仍unknown，不能叫预测或下界。0.7 nm没有FE网格/全局矩阵/factor/PDE；材料模型和网格离散精度没有资格化，factor fill、setup/numeric wall time、收敛步数与0.7 nm field accuracy均unknown，48 h和2 TB目标仍`NOT_ESTABLISHED`。原planner record SHA `93d9c0cc8e479af528afc16d6a1165e26de49c433739440108c6ad35751bf25d`，planner script SHA `ac1b27c03e47ad77cf041ff0d6b414578bc0a76c78040b09fa4c58a90c8820a7`，production planner module SHA `042062a5d405c862b9470365515f25a01b1e50f51b63d4e3cf9faba83a8aa64e`，external-mode inventory SHA `806acae28c8efbe32c11d38ccfe79fc55e84ed2c11e27012fca58f2db105fa74`；mode manifest SHA、R48 review和其余公式见[anchor compact](outcomes/records/p3_anchor_13p5nm_saved_field_pair_v1.json)及[R48 plan](outcomes/records/v6_0p7nm_48h_capacity_plan.json)。

保存场对照和归档阶段没有新运行PDE、因子或性能实验；本节之前的13.5 nm anchor 是本轮已批准并完成的一次完整场run。5 nm p3中断负结果照旧保留，不晋级2 nm/0.7 nm。
