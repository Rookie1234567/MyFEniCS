# Task42extra 首轮预登记

网络把三维复电场转为全部有限元边、面和内部矩；用原方程误差训练。DUAL 用固定正定 Gram 给不同测试方向正确计量，代价为研究专用全局稀疏 Gram 因子。

| 对象 / 单位 | 身份 / 当前状态 | 冻结配置 / 证据 |
|---|---|---|
| Git | measured | canonical linked worktree；发布 SHA 为当前 HEAD |
| M5 / nm | not_run | 5nm，384 hex / p3，非可分缺口；[预登记](records/design_v1.json) |
| 三路线 | not_run | EUC、DUAL、FREE-DUAL；相同零散射初值、500 Adam / 4000 closure / 3h |
| 完整未知量 | derived | 31968 独立复 FE；内部13824，待现场核验 |
| Riesz | not_run | ell=5nm；RESEARCH_ONLY_GLOBAL_RIESZ_FACTOR，symbolic 后准入 |
| 资源 / GiB | planning | 单核 / MPI1 / 线程1；hard16 / warn12 / own swap0；邻增长预留384 |
| p4 / 目标尺寸 | not_run | p4 条件准入；目标5nm和0.7nm PDE 本轮不运行 |

正式运行在 clean 实现提交之后。残差 / 场 / 功率 / 离散 / 资源 / 神经增量分别判定，不使用旧Task042准确解。
