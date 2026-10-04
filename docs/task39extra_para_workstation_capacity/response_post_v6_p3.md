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
| 下一步 | 只准备了一次完整5 nm p6/p3正式回归草案，尚未启动，需主审审核clean source SHA、自动reference接线和fresh准入包。 |

详细指标、失败、hash和范围见[S3结果](outcomes/p3_mid_order_s3.md)及[结构化compact](outcomes/records/p3_mid_order_s3_components_v1.json)。全场5 nm命令草案见[p3_full5nm_p3_regression_launch_draft_v1.json](outcomes/records/p3_full5nm_p3_regression_launch_draft_v1.json)。

## 数值和范围边界

`P63`是把粗空间p3的修正映回细空间p6的矩阵。canonical共享实体映射改善了同一edge/face迹在相邻单元的浮点一致性，保存C2包原Gate复放由8行超`1e-11`变成0行超限；这不是把p3基函数任意当作p6低阶内部基函数。2 nm `Di`与诱导内部端口RHS均处近舍入量级，不称强耦合压力见证。旧`P4_RETURN_PASS`字符串只是共享状态枚举，实测算子字段为degree3/A3。

5 nm草案的自动完整同离散比较仍由现有profile映射进入旧的`compare_retained_5nm_output`，其旧5 nm同物理全场/600模式见证路径与独立已合格V6 F5性能记录分开。比较项和阈值照Review V6 §4，不把V6 F5写成当前runner的直接自动pair gate。runtime必须记录真实boundary-fitted cells；输入名义`[13,7,35]`不能代替同离散参考的3780实际cell数。

source尚未形成最终clean运行SHA，正式完整5 nm没有启动。没有启动2 nm full/P2或0.7 nm模型，没有再做p4逆研究，也没有改默认或V6历史结果。
