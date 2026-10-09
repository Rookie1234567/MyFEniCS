# V35：冻结神经空间的精度与投入审计

本轮不再训练波形。先检查已有神经函数怎样组合才能使原方程残差最小，再独立问：即使给出准确参考，这些固定函数最多能表示多准确。这两项回答不同问题；后者使用参考标签，永远不能充当无标签求解成功。

执行权威为 [Review V34](../review_report_v34.md)。唯一 M5 为 5nm、384hex、p3、31968 个独立复 FE 系数、40 端口；材料、MPC、原 A/f、体及 DtN q15、网络 q30/末态 q60 均沿用原件。学习空间先做，强控制随后，分别只用 V34 最终 committed 的 1377 槽、246 块。原 q/kappa、窗口、T 和保留列掩码全部冻结，不选 best、不回更早模型。

| 阶段 | 输入与计算 | 数值限定 |
|---|---|---|
| A 无标签读出 | 原 U、复用 QR/小 R SVD，原 A 复算；三个非零复组合走点值→完整矩 | rcond=1e-12；秩不足时仅给截断空间上界；参考读取为零 |
| B 最佳场投影 | 原 V1 p3 散射参考、原 G 乘法、列归一化/确定主元/两遍 G-QR/小 R SVD | 每空间一次；流式作用≤8列；不求 G 逆或任何全局因子 |
| C 独立验收 | 新模型写回幅值、点值 q30/q60、FE compare-only、另进程保存数组 checker | 原方程、场、通道、功率、恢复及求积门全部沿用；逐位旧场复用旧验收 |
| D 投入决定 | 原数值、秩/稳定性、前缀和完整成本 | 无证据则 NO_SUPPORTED_NEXT_NEURAL_PRODUCTION_CANDIDATE；不开发下一架构 |

全部科学阈值来自 Review V34，不新增近零单通道相对门。G 内积为 E 的体积分加 25 倍 curl 体积分（ell=5nm）；独立积分必须与其配对。浮点最优性缺口不是区间证明，截断后失败也不能排除全部神经函数。

B 的 manifest、模型和结果永久标记 reference_used_for_training=true、reference_used_for_coefficient_fit=true、pde_only_solve=false、production_initialization_allowed=false、pde_only_solver_qualified=false、official_candidate_results=false。A 先封存，标签投影不允许改变 A 的状态。标签和幅值不得用于 Task42 或 0.7nm。

四个 one-run 输入和 [冻结设计](../../../input/task042extra_feinn_5nm/design_v35.json) 在实现提交中一起冻结；正式运行 source 是 clean 实现提交，不是后续文档 HEAD。既有持久 launcher、watchdog、activation 和 run_case 入口逐项串行使用。新增预算 14400s 含首项准备；A/B 共用不可重置的 7200s 数值窗，末段至少 1800s。数值树 warn12/hard16GiB、保守对象规划≤12GiB、轻树2GiB、单物理核/线程1、ownswap/OOC0、原 PSI/系统余量和 384GiB 邻增长预留不变；新增 artifact≤8GiB。

当前全局稠密波库求解族关闭。原尺寸 0.7nm、十进制 2TB 与 48h 单场冷流程目标尚未资格化；本轮不运行或注册新的波长、p/h、端口、训练或传统完成器。
