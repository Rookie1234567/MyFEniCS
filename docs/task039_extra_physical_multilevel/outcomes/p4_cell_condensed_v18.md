# Task39extra Response V19 / Review V18：原始p6通过，notch按用户要求停止续算

| 研究问题/模型 | 已测结果与结论 |
|---|---|
| 同三RHS的准确p4凝聚 | 原A4残差≤7.52867e-11，场/旋度约5.2e-12；共享12类局部LU，trace+80端口仅一个21824行全局因子，NNZ8184464；完整恢复和slave-zero通过 |
| 同口径p4内存 | Q1全过程RSS2825973760 B→U2 1785585664 B，减少36.8152%；库存1776346158 B，临时134217728 B。不是完整p6内存百分比 |
| 唯一凝聚BLR tau1e-5 | 质量通过，条目减2.3564%，RSS反增1.4163%；保留负结果并选exact |
| original p6/h10，Full3D，13.5 nm，MPI1 | **564步，A6=9.92314718715201e-7，完整物理/资源PASS**；L2/curl=1.36448e-8/4.37143e-9；RSS2528460800 B，库存1830284886 B，临时396129600 B |
| original物理量 | R/T/A/A_volume=0.365625790969/0.0129906323212/0.621383576710/0.621383574597；80模式、近场和守恒通过；能量偏差2.11291e-9 |
| notch同配置 | 494步后父watchdog丢失；最后真实残差第488步5.478307207552461e-6，未到1e-6；第480步L2/curl=8.36579e-8/4.43005e-8。无最终official物理资格，只有收敛趋势 |
| 失败与修复 | original前两次计时实现失败保留，修复后第三次通过；notch外部父监控失联已用独立用户服务薄入口修正，仅ABI/help验证，最新用户要求不再恢复计算 |
| 完整成本 | original通过场monotonic6609.661379 s，保守结算7210.314085 s；五个已结算场保守总7709.181734 s，notch已见前缀另5704.197024 s，完整总耗时unknown |

单元凝聚先消去单元内部未知量，解共享边界与原端口后恢复完整场，以局部缓存费用换取较小全局因子。本批改进准确粗逆的存储组织，保留BAL_H/H6与同一FGMRES32；历史V5原始模型也需564步，因此没有迭代加速结论。基线复用Q1，旧宏块与BLR负结果保留，不新增参考或扫描参数。

notch的Codex空闲任务卸载记录与最后父心跳同秒，worker明确报专用watchdog不存在；具体退出信号和最终结算unknown。已见资源前缀安全、宿主进程清场确认，但缺父最终资源authority，不能称完整资源PASS。旧43200秒未结算预留以幂等记录转成政策占用，不改写为实测；无活动attempt、无基础设施重跑，原600秒unknown历史不改。

最新用户明确要求修正后不再计算：original收敛已有实证；notch不凭趋势升级PASS。106项相关测试通过，运行方式仅轻量验证。保持ordinary default与5nm工作线，等待统一审阅，不合并master。

| U0–U6 | 最终执行范围 |
|---|---|
| U0 | 小复数/实际单元/双单元、MPC dual、非零内部RHS及左右端口、sum-before-Schur、身份/重复/线性/owning清理、真实外层dispatch通过 |
| U1 | 复用已资格化Q1三RHS参考、环境与全树轨迹；未补matched full-p4，不因旧CSR缺hash重跑 |
| U2 | 新CSR内容hash在factor前后及调用后相同；3主RHS及3附加调用通过；1symbolic/1numeric/6MatSolve |
| U3 | 唯一新矩阵BLR控制，质量通过但RSS收益不足；选择exact，不追加epsilon |
| U4 | 两次实现失败之后，在用户授权下第三次完整original通过；原A6和全部物理检查保持 |
| U5 | 同配置notch实际执行，外部父监控失联后中断；修复运行方式，用户取消续算；无最终通过结论 |
| U6 | 完整证据/成本与未知字段保存，当前无活动计算；统一提交等待审阅 |

![仅已保存的完整真实残差](figures/v18_residual_history.png)

原始成功的独立checker记录包含保存向量hash、原A6恒等式、564次PC边界计数、完整物理与全过程资源；notch记录明确区分第494步报告残差、第488步真实残差和第480步场评价。所有精确source SHA、三RHS数值、allocated/used/RSS/PSS、setup/调用、失败与政策账见[response V19](../response_v19.md)。

证据：[compact](records/p4_cell_condensed_v18_compact.json)、[decision](records/p4_cell_condensed_v18_decision.json)、[run index](records/run_index.json)、[测试](test_summary.md)、[manifest](selective_merge_manifest_v19.md)。大型原始数据位于本地ignored的`results/euv_grazing1_phi0/task39extra_v18_*`和`benchmarks/artifacts/task39extra/p4_cell_condensed_v18/`。旧失败和负結果不改。
