# Task40extra：0.7 nm可计算工程路线

执行分支：`task40extra_0p7nm_engineering`。初始base：`95dacd01e86f0f7f1d29ee2d5e5a16039bb41871`，来自已收口的Task39extra，不是既有Task040 Hybrid。

先读[任务书](task.md)，再读继承的[双凝聚最终报告](../task039_extra_physical_multilevel/final_report.md)。

首批目标是笔记本上真实0.7 nm材料、非可分三维缩小几何的完整有限元解及误差/容量证据。先用准确p4双凝聚取得可靠锚点；最终目标规模的路线转向有界局部求解、多层全局纠错和分布式trace/mode，不依赖无限增长的全局粗因子。

初始状态：`TASK_AUTHORED_NOT_RUN`。没有新PDE、没有新增性能结果、没有工作站迁移或master合并。材料值、网格实际行数、通道及资源合同由Codex在A1冻结，不能用旧13.5 nm常数代替。

按A0–A6连续执行，结果写`response_v1.md`和本目录`outcomes/`。旧PDE不因收口补账而重跑。合法资源或数值停止需要保存证据，不能以历史8 GiB或126步作为新硬线。
