# Response V16：全空间校正对照按真实停止条件收口

本轮执行Review V13，原0.7nm/384hex/p3/q15/40端口与材料保持。已有方向Q先求其方程分量，再以LSQR求所有剩余原有限元系数；最终解不再限制于Qc。本批不训练hidden，网络只提供部分固定随机方向。

| 路线／同一0.7nm micro | 维数Q＋完整补空间 | GK更新／原作用次数 | 原Schur／native残差 | 停止原因 |
|---|---|---|---|---|
| CLOSED-LSQR-0 | 0+18144 | 4096／8523 | 0.0694190731／0.026920979 | STAGNATION_CONTROLLED_STOP |
| AUG-LSQR-GPOLY | 3098+15046 | 816／1698..1714上界 | 0.0126178958／0.00489326771 | RESOURCE_CONTROLLED_STOP；原审核768／向量仅256 |
| AUG-LSQR-GNN | 3098+15046 | 85／181..197上界 | 0.122363732／0.0474531179 | RESOURCE_CONTROLLED_STOP；原审核64／向量仅0 |


严格同离散资格 **0/6**。冻结后一次FE验证的total/scattered E/H、curl、selected复场、40复通道及功率见[完整结果](outcomes/augmented_full_trace_lsqr_v16.md)和[候选表](outcomes/records/candidate_comparison_v16.csv)，未合格功率仅diagnostic。原门限未改，micro结果不能代替最终0.7nm模型／48小时资格。

两增强路线因全局持续PSI由自有监督器受控清场，GPOLY最后标量816／原审核768但向量仅256；GNN最后标量85／原审核64但向量仅0。VERIFY核对这些实际快照，完整终态配对和神经优劣仍INCONCLUSIVE；其丢失的组件计数／叶计时保留unknown，预算使用保守上界。没有重启已停止路线或改变邻任务。

运行source **ef60675dada2556a5527101f90fc83540d60e242**；GPOLY A/U/R实际由 **01ed98655c9eb2949ea29a35fd82d1881a5a2508** 构造。首次随机压力恒等式1.1125765e-7超1e-8与watchdog尾部Mapping写出错误保留。两项最小修复后，物理尺度非零接口复核1.0282828e-12，通过原Gate；未重算A/QR、未重置费用与窗口。最终文档HEAD另以Git提交回执报告，不冒充运行源码。

正式监督wall新增下界 **4447.81145s**、同时整树RSS采样峰 **4003057664B**、own swap／GPU分配0；0.5s watchdog，无cgroup委派。统一每路线2700s包含设置与加载，旧formal下界／辅助unknown保留。所有成本为shared-workstation，同精度性能与邻任务可比吞吐尚不足以得出无争用加速结论。[费用](outcomes/records/resource_costs_v16.json)、[run index](outcomes/records/run_index_v16.json)、[原始Gate](outcomes/records/qualification_and_dispatch_v16.json)绑定实际source／input／数组。

候选没有全局FE S／p4因子、正规方程、隐藏fallback；3098阶薄QR三角块和40维Hhat小解的时间与内存已计入。独立原native审核仍组装原FE方程，不把这部分成本隐去。GPOLY与GNN共享神经G0，本批不声明hidden训练贡献。

唯一下一建议：在新的review授权和稳定资源准入下，仅做一次冻结GPOLY/GNN的有界配对复试，每64步审核以两个滚动槽先原子保存完整递推／候选，再写汇总，补齐中断终态及同工作量证据；算子、基、精度和迭代预算保持，本批不实施。 已同步summary、测试、导航与两份项目总账，旧task/review/response/raw保持。只推送本执行分支，清场后等待review，不merge。
