# 工作站 PSTDDM 波长试验

本目录记录用户授权的有限宽三维 Si 小光栅试验，执行分支为 `task40extra_dot_parallel_cloud`。它补充父目录的历史 cloud pilot，不替换历史结论或证据。

- [本轮范围与固定配置](task.md)
- [本轮结果回应](response_v1.md)
- [p6直接解与CSV修复阶段回应](response_v2.md)
- [结果汇总](outcomes/summary.md)

PSTDDM把一个区域中的源逐步传递到相邻区域，用局部求解组成全局近似，再由原方程残差检验结果。本轮比较固定网格上的直接参考解与两种分区数，检验计算方法及资源成本；这不等于已经验证真实光学精度。

工作站专用根为 `/home/fenics/Projects/laptop_share/benchmarks/artifacts/pstddm_workstation`。源码在 `source`，正式原始结果在 `runs`，只读审核在 `reviews`。大型场和矩阵保留在 ignored artifacts，轻量报告记录其路径及内容 hash。主控负责冻结和提交，Luna 执行者负责实现、运行及整理证据；不修改邻项目。
