# V33固定容量回拟合预登记

本轮不增加函数数量，而是重新学习已保存的波矢。一次移除一个旧块，以其余块的原算子作用形成补空间；每个试探先解活动幅值，再重求其余全部幅值。最后用完整原方程残差接受或回滚。这样检验已有特征能否在固定内存容量内改善，代价包括删块QR、小SVD、完整矩、梯度、原作用和存盘；不能以局部线性代数速度授神经收益。

| frozen / derived / not_run | 预登记身份、限额及证据 |
|---|---|
| 权威 / base | Review V32，7aa0df9b41ee1722e7a29cafbaa4e02314f063f0；原base fbac3d8777fcfd897d93b898cb9f460f79ddd6ff |
| 唯一起点 | V32最终FIXED_MULTISCALE_WAVE_BLOCK；1377复方向、246块；committed SHA737dd067f2cc3ebe021f3c7f445992c87d993e562213c62cc7a40b148a33501e |
| 原native | 0.15743176704993547；保留完整31968复FE/40端口、所有内部矩 |
| 原物理 | M5/5nm/384hex/p3；Si/air三维缺口、双Floquet及完整DtN；体q15、网络q30、最终q60 |
| 固定地图 | 每块原T、列顺序、窗口和宽度不变；不释放被丢弃幅值方向 |
| 方法对照 | DETERMINISTIC_WAVE_BACKFIT与LEARNED_VARPRO_BACKFIT；均更新旧q并重求全部幅值；属于算法对照，不是纯有无NN消融 |
| 活动选择 | 每轮8个归一化q梯度最大块加8个持续尺度轮转块；一次公共A* r，seed4213301 |
| 控制 / 学习 | 固定pattern步1/8→1/16→1/32→1/64；学习L-BFGS-B/20iter/32实际评价/maxls12/maxcor10/ftol1e-12/gtol1e-10；q/k0分量±4 |
| 小系统 | 经济型QR删除/插回；活动块及非活动小R的SVD，固定rcond1e-12；无正规方程逆、A*A、Gram或Maxwell逆 |
| 两路线新上限 | 各10800s、64访问、2048完整试探，先到即止；加载、setup、暂停、审核、失败全计 |
| 验证调度 | 60min或16访问；必要时120min或32访问确认；仅隔离评分标量参与继续，不接收参考向量 |
| 早停 | 两节点原残差均未减半且散射E/H均≥0.01，则BACKFIT_NO_USEFUL_PROGRESS；一条停止不取消另一条 |
| 严格Gate | 方程1e-6；完整场/六点/复通道1e-4；功率/独立能量1e-5、逐级1e-6；重建/MPC/恢复1e-10；网络及原作用/FE求积1e-8 |
| 保存 | 不变旧原件、原子匹配全幅值/c/r/小R/队列/RNG；按块追加新q/T/U/AU，精确QR更新序列可恢复；trial不覆盖committed |
| 费用 | 共同前缀10186.178641493432s各路线归属，项目不重复收费；冷N=1 UNKNOWN；旧LEARNED只作历史成本 |
| 资源 | 一空闲物理核/MPI1/math1/CPU；数值warn12/hard16GiB、含临时规划≤12GiB；轻2GiB、ownswap/OOC0；384GiB邻增长及原PSI |
| 单总窗 | tmp/task42extra/v33/batch_window.json，43200s连续窗，源自首次准备，不重置；最终≥1800s |
| 条件0.7 | 仅学习M5联合PASS且余时≥7200s；否则NOT_RUN；正确缩放原函数后重新积分/材料/模式/背景/幅值，不能缩放FE系数 |

完整初态路径和逐文件旧hash在[input设计](../../../input/task042extra_feinn_5nm/design_v33.json)，来源[旧run索引](records/run_index_v32.json)及[provenance](records/provenance_v32.json)。预登记见证块取global/粗/中/细各最小旧block id，最多4×8次q试探，不提交起点修改。两条新路线恢复共同原态再独立分叉。

训练没有teacher/参考/监督权重、全FE逆或Gram逆；reference_used_for_training=false、benchmark_previously_seen=true、reference_used_for_validation=true、continuation_uses_validation_scalars=true。原误差门不变，未合格功率仅diagnostic。M3600较好/最终退化、D0成本否决/D1未运行、全部历史失败和UNKNOWN保留。最终原50×25×140nm/λ0.7完整3D FE、decimal2e12B整机/ownswap OOC0/172800s完整流程仍未资格化；本支只做神经，不返回W0/W1或其他任务。
