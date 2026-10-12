# V77：真实子域阻抗配置的完整迭代负结果

局部逆用于近似处理全域残差。本轮把“选中行的全域主子块”改成“halo单元并集中的Maxwell方程加真实外面的一阶出射边界”，希望减少人工切口反射；代价是新的38块组装、symbolic和numeric。原完整方程未改变，粗层仍旧Z0/E0。实际rho32=0.919289591408>0.30，比Jacobi32更差，固定配置关闭。

| 准备/求解/审核，measured | 实际数据 | 裁决 |
|---|---|---|
| halo-only体作用、三角Pt/Piola/方向/MPC复对偶 | 两真实块独立差<=7.37e-15；所有38halo库存重算相同 | 数学组件通过，非全域解 |
| 周期mate、材料内面、物理z面 | 周期商先分类；域内材料面无阻抗；局部与全局DtN身份分开 | 新局部模型，不伪装原主子块 |
| 38CSR，最大68680行；7068粗层 | 368317250存储项；67.835674GiB双倍symbolic | 80GiB子门通过，39numeric实际完成 |
| RIGHT/restart128/max256，独立zero retained | 实际1个KSP/32步，原true=0.917996117703 | 0.30效果门FAIL，64/128/256 NOT_RUN |
| q15 PUBLIC_BASIX体＋完整q63 | 原true/native/augmented/port均FAIL；独立向量差0 | 非bug性数值负结果，原门不改 |
| 全部FE/port系数与恢复 | MPC/恢复/Schur-original<=1e-10；39因子释放后RSS下降 | 保存可消费完整候选 |
| 六场/240点/828评分/RTA/体吸收 | original>1e-2，NOT_RUN_BY_FAIL_FAST_POLICY | 无official场或物理功率，不生成昂贵坏场表 |

body只加入halo_cells，不能由旧CSR减/加项伪造。本批q13/q15生产面见证和CSR对独立q15完整作用、排除域外作用向量均已保存；checker重算整体CSR/体+面向量与halo清单。其证明对象是局部方程和实现，不能据此认定一阶阻抗充分描述斜入射传播。高频困难的唯一根因未被证明。

| 成本与生命周期，measured | 值 | 边界 |
|---|---:|---|
| 科学prepared-start执行链 | 2580.144881s | 含预检、准备、正式迭代和独立VERIFY；父packet/Z/E0另列 |
| ITERATE完整失败attempt | 1272.633110s | 从Python启动到原式、保存和清场；无完整成功N=1 |
| 39numeric阶段 | 353.885297s | 207.351s numeric子计时含在内；首因子校准后留用 |
| KSP与显式检查 | 521.866566s | PC内部原作用已收费，不按32个外层作用冒充全部 |
| 同时采样树峰 | 37.080410GiB | 来源全部新监督，非显式载荷，连续峰unknown |
| 最大真实采样间隔 | 1.333710s | 配置0.5s不是连续硬峰 |
| 因子释放前/后 | 35.308/7.277GiB | 先释放再恢复，swap/OOC0 |
| 原式全域调用＋局部作用资格 | 73+2 | 带VERIFY，800上限安全；详见最终费用计数 |

完整输入/source/ABI/物理/材料/mode/map/局部CSR/父状态hash绑定见[source与数组](records/source_array_bindings_v77.json)、[原始增量](records/increment_manifest_v77.json)、[四one-run索引](records/run_index_v77.json)。88新NPZ/334成员逐文件hash与物理库存相符，完整数组ignored；旧数据不重复嵌套进Git。

历史前缀和研究重复不免费：V71核心区域/插值/E0准备2928.727022s已记录，V70 packet与fine-S共享准备未分离为packet-only冷路线，必要份额unknown。当前命令下界、全部历史下界、源码与实际采样数据见[费用](records/resource_costs_v77.json)。未同精度成功，既不授生产速度/内存改善，也不授连续精度、原尺寸2TB/48h或NN20。

最终10项新增math/strategy/checker回归、Ruff/compile和4dat validate通过，文档合同一次运行；修复/未运行分类见[决策](records/decisions_repairs_v77.json)。普通错误仅补测试或消费，科学求解重放0。GitHub视觉NOT_VERIFIED；ordinary default不变，selective merge未批准。

唯一下一pilot前提为不同传播/粗层机制的独立证据，保留Jacobi对照；不再投资本固定38块阻抗配置的系数、组合或restart扫描，不自动执行V78。
