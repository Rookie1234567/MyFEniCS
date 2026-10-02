# V25：原八块方向的残差消除上限

| 统一结果／身份 | 结论或证据 |
|---|---|
| 范围 | Review V22 §§5–7；0.7nm/384hex/p3/h0.175nm/q15/MPI1/40端口，原用户Si表／背景／MPC／RHS不变；新物理解0 |
| checker | 六场／四功率必需指标及40mode库存fail closed；52库存／93总focused通过；原V24重算0/5 |
| 三样本 | 固定V24-LZ-INITIAL、LZ-CYCLE4、LCZ-CYCLE4；已消费诊断，非fresh测试；原状态／原source／成员hash见input inventory |
| 完成／停止 | 三组DIAGNOSTIC_COMPLETE、rank8；两终态eta8≥0.9，按预登记EIGHT_DIRECTIONS_WEAK收口；不续跑V24 |
| 新资格 | 无新Schur/native／场／功率资格；旧五态FAIL保持；神经20% NOT_DEMONSTRATED，原尺寸0.7nm/2TB/48h NOT_QUALIFIED |
| provenance | 实际source `bc88fe5a81d086059dec705db333b9cf9bf2921e`；原packet `9196edb807b534217d0c0eb78882125341342784a48ef20ebe2d9421fe636454` |
| 资源／费用 | 25.665227s整树actor、峰1,832,550,400 B、ownswap/VRAM0；S39/SH0、LU40／三角80／reader1；全费用见resource_costs_v25 |
| 精度与merge | 没有放宽Gate、训练、global p4 LU、新局部factor或旧粗空间读取；未改dot／master，NOT_APPROVED |

把八块修正分开，是检查现有方向是否有用的方法：原方法统一相加，本次先测每块在全域原方程中的作用，再求最佳八系数组合。代价是八次原作用和一次很小的最小二乘；这只诊断一个给定残差，不构成新的迭代法。coef随残差变化，未来若部署通常是非线性，不能未经资格就当固定线性GMRES PC。

```math
q_j=E_j^H A_j^{-1}E_jr,\quad V=[Aq_1,\ldots,Aq_8],\quad
\eta_8=\min_{c\in\mathbb C^8}\frac{\|r-Vc\|}{\|r\|}.
```

| 样本 | unit剩余比例 | 单复系数最优比例 | 八系数最优比例 | 八系数范数下降 | 平方范数覆盖 |
|---|---:|---:|---:|---:|---:|
| 初始，仅控制 | 2.0283184653 | 0.8776402575 | 0.8641444186 | 13.585558% | 25.325442% |
| LZ4 | 2.8176911544 | 0.9999995996 | 0.9832369898 | 1.676301% | 3.324502% |
| LCZ4 | 3.9247610154 | 0.9999978273 | 0.9899246286 | 1.007537% | 2.004923% |

分母是各自**当前原trace残差**，不是REF7场、全物理b或任意改过的loss。端口按原b重闭合，保存残差与原A差/norm(b)≤5.99820e-17；全b规范固定0.0826782769485171。初始port闭合得到零，两个末态port非零，未强置零。齐次方向用零端口常数和原barA，不把内部特解加入方向，不作真实FE恢复。

原主块对角作用、原A(q)及原A(Σq_jc_j)的新作用与薄预测通过。独立重组最大差/norm(b)=1.42436e-15、差/norm(r)=2.72383e-15；驻点缺陷最大7.39952e-17；三个QR/正交相对缺陷均满足1e-10，数值秩按固定1e-12，未删列或扫阈值。列范数均衡只改坐标，不改方向集合；GELSD残差独立重算。8×8复交叉项记录矢量相消，不把各范数相加当残差，F不假定为Cᴴ。

两末态中八响应对残差近乎正交，最佳组合仍保留98%／99%左右范数。均衡后rank8与很小驻点缺陷说明本次负结果不能用缺秩或尚未求好这八系数解释；它不是原Maxwell条件数或全局谱判断。跨块作用很大并不足以证明哪个物理机制唯一负责。控制初态改善13.6%，不能代替末态研究分流或解释神经收益。

已有局部方向仍依赖LOCAL8_DENSE_LU_PRESENT，矩阵＋LU1,354,430,592 B，pivot另计；没有新的全局fine矩阵或factor构建。实际reader逐个核对原文件、shape／成员hash，独立重载16个解见证；3次L8各8解，合40解／80三角pass。Hhat准确40端口小分解1次、solve37次；不是Hp或隐藏p4逆。未读REF7／teacher／真误差／NN权重／T/U/coarse-R／D_L／旧循环方向。

| 生命周期口径 | wall／容量 |
|---|---:|
| 正式actor监督／launch | 25.665227／27.057488s |
| 已有factor只读hash与reload | 14.426483s，嵌套包含在actor |
| 原packet的39次S | 3.661436s，端口bar计时与它重叠，不再相加 |
| 三次L8／其中LU solve | 0.825618／0.672646s，嵌套 |
| 三次小LS | 0.007572／0.008259／0.052593s，包含在三状态诊断 |
| 同时规划／整树实测峰 | 5,813,108,752 B derived／1,832,550,400 B sampled RSS，不能互换 |
| 新持久数组＋provenance＋辅助证据 | 18,878,800 B，cache另列，未复制旧因子或U |
| 另计独立TMP／缓存／日志／records的保守总库存 | 27,368,703 B，低于128MiB；观察时刻和分项见resource_costs_v25 |
| 全Task042 artifacts | 17,537,999,211 B，≤20GiB；磁盘余量约3.39TB |

所有有载成本标shared-workstation；实际CPU0由现场空闲物理核及SMT核查选择，数学池实际1，MPI1／Loader0、无Torch/GPU/OOC／ownswap。原系统reserve、137,438,953,472 B邻增长余量、PSI与0.5s整树16/12GiB保护保持；没有delegated cgroup，不声称连续kernel上限。无触线，后代清场；已有阶段指标不够可比，影响INCONCLUSIVE。计时子项不得重复累加，历史研发下界77,128.294516s与暖解per-solution未知费用保持，25秒不是完整求解时间。

新窗口UTC23:01:15→heavy00:16:15→交付00:31:15不可刷新。接线测试、两次最小开发修正、一次无空闲核拒绝／一次有限复核、missing工具探针、实现与读写都计入总elapsed。没有正式重放或新因子reader重入。原V24的4/4历史修复／费用不清零。所有三个样本已完成，未运行的场／REF7／训练／V24追加周期由合同禁止，不能写通过；GitHub视觉NOT_VERIFIED，本地渲染合同独立记录。

**唯一下一建议**：下一review限定一个块5／7跨y=0联合方向的容量／资格试验，不立即实施。两终态原测7←5响应占源全域范数0.762103／0.778270；它提示检查不同的跨界面方向，而不是继续训练同八个系数。合计3888行，联合矩阵＋LU载荷483,729,408 B（derived）；装配、LU与工作区、40端口、旧因子重叠及完整原作用成本另计，时耗unknown。还需新设置／存储授权、该新方向独立原作用资格与最终完整PDE／物理资格，不能拿本批128MiB预算去构建它。

V5的方法论先例保留：它使用另一p4和重叠PC；V9是准确场误差定位；V23是p1作用像；V24是多周期求解。本轮新增的有限信息是此0.7nm/p3八个完整主块的同残差八方向上限，排除“只换这八系数即可大幅降低两个末态残差”。NN无法越过同空间精确LS；20%门槛需同正确性最佳合格非NN全链N=1对照，本批未测NN也未产生该对照。

[回应](../response_v25.md)／[输入](records/input_inventory_v25.json)／[指标](records/direction_metrics_v25.csv)／[8×8响应](records/block_response_v25.csv)／[相消](records/target_coherence_v25.csv)／[交叉](records/complex_cross_terms_v25.csv)／[独立缓存审核](records/cached_array_checker_v25.json)／[Gate](records/numerical_gates_v25.json)／[库存修复](records/checker_inventory_v25.json)／[费用](records/resource_costs_v25.json)／[失败](records/failures_and_not_run_v25.json)／[run index](records/run_index_v25.json)／[source](records/source_inventory_v25.json)／[交付](records/delivery_receipt_v25.json)。
