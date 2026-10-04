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

正式完整5 nm唯一尝试绑定clean运行source `2b0a7c1d6e5a20c5d0323469cd018deeb73898c2`，现已按上节记录为中断。没有启动2 nm full/P2或0.7 nm模型，没有再做p4逆研究，也没有改默认或V6历史结果。

## 唯一5 nm p3完整场终态

运行`20261004T085614.837316Z`绑定clean source `2b0a7c1d6e5a20c5d0323469cd018deeb73898c2`、p6/h4细层与A3/p3粗算子；stage记录真实3780 cells、600 modes（SHA `dde3aee7ee25bc5d68617a503eebec720a1527c9d044125bfb09acaa6d0b6645`）。workflow起点到solve同钟setup为`1117.064241 s`。symbolic/numeric API为`2.104244/69.681804 s` wall；H6 diagonal `5.026990 s`、power10子项`93.157356 s`、H6 parent `107.943479 s`，都是嵌套计时，不相加。

watchdog的`USER_CONTROLLED_STOP`只表明父进程接收SIGINT/SIGTERM的处理路径，sender与信号号未保存。stop event为`2026-10-04T17:20:08.361441Z`，清场end为`17:20:12.868272Z`；主审于`17:22:54Z`确认原进程已消失。run_summary full workflow为`30238.071031911997 s`；root CLI exit 3由peer exec session 52614读回，与run_summary、worker及watchdog leader exit 1分列。最后完整outer为544、Schur residual `0.0036393393688062795`；A6最近已完成检查在536为`0.0038091382027435404`，step544没有已完成检查记录（`NOT_RECORDED_COMPLETED`），运行可能在该检查进行中被中断。最新512检查点为solution-only、residual `0.004015580499214017`，不承诺免setup恢复。`iterations.jsonl`末条`last_logged_solve_seconds`不是正常KSP返回API计时，后者unknown。

与既有q4 F5只比较相同i0→i120的`solve_seconds`窗口，再除以120：p3 `52.973319714 s/step`、q4 `79.389986392 s/step`，观察值比`1.49868x`。该口径包含窗口中的监控和输出，但不含i120回调后A6检查；两场不是配对控制，也不等于总time-to-solution。相同step120的原A6是p3 `0.0489090873604`、q4 `1.06532658799e-6`。较低单步时间没有弥补p3的收敛退化，因此本run未取得数值或物理资格。

watchdog summary报告93536样本、RSS峰`18428985344 B`、tree swap峰0、PSS disabled、hard RSS线`1300000000000 B`、无时限和后代清场。约995 MB资源日志未全扫；仅核首尾样本并与summary交叉，末样本距clock_end `0.046385312 s`，全程样本可读性仍unknown。全机pswpin增10页/pswpout增0页的归因unknown。终态和匹配窗口的主审回执hash见[终态compact](outcomes/records/p3_full5nm_terminal_compact_v1.json)。
