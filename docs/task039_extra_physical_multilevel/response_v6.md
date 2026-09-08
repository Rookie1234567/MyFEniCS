# Response V6：补充授权的真实难误差定位完成

本轮回应用户“授权，直到把真实难误差定位了”的补充范围，不是Review V4原始授权，也不改写response_v5或旧review/negative。

| 交付 | 结果 |
|---|---|
| source/base | task39extra；实际诊断source2251d7d0d3d3e8498ee34d38f8ec70f70d2f0d98；base2dc2e7305f10dc391a13970c6f0f0340cb87b6ee |
| 匹配离散参考 | f09476792d9928d6169cae8cc16b4c008f9bc694；原A6 residual1.6160304782604192e-11≤1e-10；非连续真解 |
| 三真实失败快照 | 相对L2误差22.46%/24.92%/31.34%，M0相位无关相关0.99757575/0.99981986/0.99852676，几乎同一难误差形状 |
| 表示/精度 | p4无法表示部分仅0.8300%/0.8421%/0.8225%的范数；3次投影均98步，共437.9988s；原A4四RHS≤1e-10且零精化；range identity2.53e-12 |
| 主机制 | 很小互补场产生几乎等大反向粗RHS；cross约−0.9992至−0.9994，相消比1.7–2.0%，粗响应差/互补范数57–59倍；能量与粗方程闭合 |
| 粗修正/MR | 单位粗修正剩余场约48%而原细层残差增22–53倍；MR约1e-4步长使场近乎不动。不是MR公式bug，不建议强制alpha=1 |
| 其他响应/空间 | 6互补平滑仅有限降低小互补场；9旧PC场比近1；72–74%未加材料权重误差L2能量在air、26–27%在grating，上部占优，不是吸收或边界bug证明 |
| 参考资源 | peak7,229,845,504 B/574.7957s、swap0；一次分解/两MatSolve/一修正，factor释放后才native action |
| 诊断资源 | peak3,881,811,968 B/1510.7222s、swap0；4RHS/4MatSolve/0refinement/1factor、6smooth/0new fullPC；5302样本违规0、清场通过 |

投影衡量“低阶空间能否表示”，物理粗修正衡量“按低阶方程实际会给什么修正”。本次闭合证据不支持把主因归为p4表示容量或解精度缺口，而定位到物理粗层—细层互补耦合失衡及残差MR抑制；不宣称条件数/色散定理/整体近共振或生产收敛谱。

**唯一优先下一修改对象是现有physical p4粗修正与p6互补的耦合/平衡**：避免延回细层的粗修正注入巨大的细层残差，并让互补响应一致反馈到粗修正。这是下一轮待资格化的设计要求，当前没有选定/实现新PC、新粗空间、参数扫描或强制单位步长。取得真实误差并定位主机制的授权范围完成；2GB生产迭代、非可分、0.7nm、official仍未通过。两批峰值分别报告，不相加，不冒作2GB资格；reference correction sensitivity也不是严格前向界。

旧首次fine参考原A6残差7.926904173050276e-8失败，经保存RHS差定位后仅做default-off incident degree25窄修，再取得新参考。所有旧失败保留。V4通用首新RHS的ORIGINAL_REJECTION_NOT_REPRODUCED枚举不适用本批新g，不是旧第八输入replay，不重分类旧negative。

详见[中心说明](outcomes/actual_error_diagnosis_v5.md)、[中心JSON](outcomes/records/actual_error_diagnosis_v5.json)与[测试索引](outcomes/test_summary.md)。中心记录绑定全阶段audit、九旧packet的JSON/NPZ来源/hash及两份精确bytes保存的research审计脚本。M0场量为正式runtime测量；saved-only代数独立复算不冒称重新FE验证。时间采用conservative_realtime，monotonic/BOOTTIME/UTC差异保留，不声称一致。

本次收口仅文档/紧凑证据及最小JSON/hash/link/历史/diff检查，无新FE/factor/PC/PDE或数值改动、不重复昂贵Gate/full pytest，无CI通过声明。本轮诊断证据已由主任务审阅，提交同一task39extra；精确交付HEAD、upstream与工作树状态由最终消息报告。停止等待集中review，不合并master。
