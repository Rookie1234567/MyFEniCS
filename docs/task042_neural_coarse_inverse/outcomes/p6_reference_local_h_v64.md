# V64：p6完整准备与固定局部h容量否决

目标是在同一有限0.7nm三维NOTCH上获得统一p6场和局部细化p4场。没有取得新完整场：P6独立原式核对未在完整单例配额内完成，L4实际相容网格超形状上限。已完成准备不能替代解与准确性，所有场/功率门保持。[完整回应](../response_v64.md)解释方法、物理身份、失败与费用。

| 对象 | measured/derived结果 | 验收分类 |
|---|---|---|
| 固定标记 | θ=.5；1267/7680单元；覆盖.5001897305 | 最小前缀/周期/材料/父体积通过 |
| L4实际网格 | 25576tet；FE1042964；1043792行 | 超19200tet/800000行，PDE NOT_RUN |
| P6实际空间 | 7680tet/p6；FE980352/native1005528；981180行 | 空间/装配容量通过；numeric资格NOT_RUN |
| P6准备 | mesh/MPC、完整UFL体、q47/q63各828模式 | 保存；独立完整体gate NOT_COMPLETED |
| 新完整解/全物理输出 | 0；没有solution数组 | 方程/六场/240点/复模式/功率/吸收/能量NOT_RUN |
| 失败完整进程 | 15056.335016s；采样33.351GiB；gap2.008412s；观察swap0 | 审核/输出预留停止，非OOM或解失败 |
| 独立partial消费 | 4NPZ/25成员；边界最大操作差3.53175e−15 | 准备对象资格；不是物理场资格 |

原P6阶段mesh/MPC17.924943s、q47/q63为60.583201/63.998702s、body12203.710183s；原式未完成段至少2490.803052s包含在失败入口中，不再相加。实际nnz、symbolic、fill、numeric峰和成功T_N1未知；P6矩阵图397744956是保守上界，不是实测存储。原监督WORKER_FAILED/-15逐字保留，受控停止有另存理由、自身PGID/birth和时间。L4没有PDE失败，标记及准备的实际费用不为零。

| required配对 | 新场 | 六场/240点1e−4 | 复通道/逐mode/能量 |
|---|---|---|---|
| B/P6 | P6未返回 | NOT_RUN | NOT_RUN |
| A/L4、B/L4 | L4不准入 | NOT_RUN | NOT_RUN |
| P6/L4 | 两场均无 | NOT_RUN | NOT_RUN |

历史A/B散射E/H约4.89487e−4/5.08576e−4、240点2.32882e−3仍FAIL；两父场生成链8016.232864s已计历史，不能作为免费训练或细化前置。本批只用保存差分，没有重复父solve、FLAT或旧完整审计。

精确cache库存1118键，每类约10.81MiB，512MiB可驻47类，原cell遍历重算有5932 miss/4814重复重建。这只给出一个可定位费用候选，未经逐类运行计时不称唯一根因。唯一下一pilot为系数先变换的独立PUBLIC_BASIX向量积分及新的同空间P6完整场；没有在当前已冻结队列中接入或追加计算。目标正确网格、模式、fill、迭代、同时RSS和完整冷N1仍unknown，原尺寸2TB/48h与NN20未资格。

完整[容量/分子分母](records/capacity_and_marking_v64.json)、[原始科学](records/scientific_checks_v64.json)、[独立检查](records/independent_saved_pair_checks_v64.json)、[失败部署/对象寿命](records/deployment_failure_v64.json)、[父费用边界](records/parent_lineage_and_limits_v64.json)、[最终费用](records/resource_costs_final_v64.json)、[来源](records/source_bindings_v64.json)、[原始归档](records/raw_archive_index_v64.json)和[交付](records/delivery_index_v64.json)提供可重算证据；大数组ignored，旧历史不改。无NN训练/新Krylov/邻支实验；GitHub视觉NOT_VERIFIED、本地targeted测试不称CI。
