# 0.7 nm G2及条件G3粗网格筛选准备

用户提供RCWA结果后，授权先计算G2，保持M8及q81/q15，等待当前B_M8自然完成清场，再独立fresh和systemd启动。随后明确本轮不要求R/T/A达到某个RCWA精度，只寻找脱离近全反射的平台。故原Y3及其“B_M8截断比较三组PASS才启动”的依赖不再适用于本次G2；旧证据保留。

| case | 网格 | y三段/z三段 | air/substrate/grating | 状态 |
|---|---|---|---|---|
| G2_M8 | 6×68×8，3264 cells | 20/28/20；2/4/2 | 2224/816/224 | 已实现，未运行 |
| G3_M8 | 6×100×8，4800 cells | 30/40/30；2/4/2 | 3280/1200/320 | 条件备选，未运行 |

两场都独立采用冻结坐标，x与B相同，材料界面不变；G2/G3相对B改变y、z。live mesh QA新增明确的多轴声明校验，不能把这两场误报成只改y。原B/Y1/Y2/B_M8/Y3_M8 profile事实完整比对未改变；未改数值装配、因子或输出算法。

M8为m=-8…8、n=-143…1，含上下端口和s/p，共9860通道；表面q81、体积q15 default、relative-only cutoff 1e-13不变。完整fresh保持64GiB host available floor、无固定RSS cap、swap observe-only、PSS/USS off、默认拒绝未知/活动邻树。

原B_M8继续使用其冻结源码。新改动只在canonical仓库登记的隔离worktree准备，待B_M8自然清场后才能fast-forward到新提交；若源码偏离、工作树不干净或清场未确认，停止部署。G2与G3均至多一次FE attempt，每场独立fresh、独立systemd、Restart=no，不直接exec FE、不自动重试。

G2完成后记录R、T(-10nm)、A与用户给出的RCWA 0.12138682、0.72430380、0.15430938的差值；不设差值通过门。将R≥0.999作为“仍近全反射”的排程触发条件，满足单场数值/能量门且自然清场后才考虑G3；R<0.999则先结束本轮粗筛。该条件不是收敛或物理正确性声明。残差、有限性、能量门不变；求解失败不触发下一场来替代重试。

隔离源码定向测试21 passed，包含formal loader→真实模式库存→worker admission，以及真实无求解网格的标签/轴检查及错误声明拒绝。Ruff E/F、compileall、diff-check通过。没有在准备阶段启动FE；运行源及旧结果未修改。

FULL_DTN_NOT_VERIFIED、canonical sidewall NOT_MEASURED保留。用户先前只授权推送babb1f43提交；此后新提交只作本地冻结，未继承新的远端写入授权。
