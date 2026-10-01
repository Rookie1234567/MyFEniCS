# V9：全参数阻尼 Gauss–Newton 对照

本页说明本轮改变的训练方法。它先计算“网络参数的小改动会怎样改变原方程残差”，求一个受阻尼限制的方向，再用真实非线性目标检查是否接受。因此一次外层步可以包含很多完整方向作用和拒绝试探；它既不是一个 epoch，也不能与旧 L-BFGS 的一次 closure 等价。最终数值表将在本轮各状态冻结和独立验收后补齐，当前不得据此宣称求解通过。

固定问题仍为 M5、5 nm、384 hex、p3、体/DtN q15、31968 独立复 FE 和完整40端口。plain 和单入射相位网络保持3×64 tanh、6输出、8966实参数、FP64。全部隐藏层与末层都可以更新，全部 Nédélec 边、面和内部矩都进入同一原方程；这里没有冻结195维末层、扩大网络或改变物理离散。

## 更新方向与实际目标

网络及完整矩插值把实参数映射为复 FE 系数，JVP 表示沿参数方向的系数变化，VJP 把系数梯度拉回参数。它们不是空间导数。闭包按最多8个cell分块，不保存完整网格自动微分图、全 Jacobian 或大参数矩阵。

```math
r=A c(\theta)-f,\qquad d_G=f^*G^{-1}f,\qquad L=\frac{r^*G^{-1}r}{2d_G}.
```

```math
g=\frac{\mathrm{Re}(J^*A^*G^{-1}r)}{d_G},\qquad
Kv=\frac{\mathrm{Re}(J^*A^*G^{-1}AJv)}{d_G},\qquad
(K+\mu I)s=-g.
```

K 是参数空间的 GN 曲率，不是一般非线性 loss 的完整 Hessian；G 是有限元场的正定度量，也不是 K。每条 C 路线新建一个准确稀疏 G 因子，标 `RESEARCH_ONLY_GLOBAL_RIESZ_FACTOR`，并计入建立、求解、常驻 RSS 和释放。matrix-free 只指 J/K 以及既有 A 作用，不能称整套方法无全局因子。训练不建立 Maxwell 因子。

初始曲率尺度 h0 用 seed421901 的6次作用估计，不是条件数或严格谱界。μ初值为1e-3 h0，限定在[1e-12 h0,1e6 h0]。真实目标下降为正且实际/预测下降比η≥0.1才接受；η>0.75时μ除以3，η<0.25时乘2，拒绝则乘10，每outer最多8个试探。阻尼只控制更新，不加入正式 loss。

内层实 CG 默认40次、真相对线性残差目标0.01。有有效下降的未完全收敛方向仍可检查真实目标。连续3次慢 CG 触发固定 rank32 的随机range/Ritz参数辅助：用64次K作用构造小基，改善内层方向尺度；它不是全FE或Maxwell预条件器。C每条最多构造2次、D每条1次，PCG最多80次，旧基复用时明确来源。没有有效下降时仅使用预登记 Cauchy 保护，仍不能接受则保存 `GN_MODEL_STAGNATION`，不重置预算。

## 阶段边界、标签与保全

| 路线 | 读取的唯一 V8 Adam500 字节hash | 原前缀归属 / s | 本段性质 |
|---|---|---:|---|
| C plain | e976d3e629c433c1f1dc6b7ae3c343acaa5dfa5cd948818231e93a3a9298f9a0 | 1097.641308126 | 无标签原方程 GN |
| C phase | 07c77c468c175edc9455025651a058ac589f2313fc1f15d9b38c3c6628daffae | 1144.848724030 | 无标签原方程 GN |
| 条件 D plain | 1f3929eacd6afe3b19b5bc6552a37316326bd9b3434f14060cafd81c39716234 | 989.700669310 | 隔离监督 FIT-GN |
| 条件 D phase | 91c7696d34eec5c01e90be6559198bd8983fe81affa8640393a3be532d8041aa | 1019.104531524 | 隔离监督 FIT-GN |

只复用各自参数和buffers，不重做500次Adam，不加载旧optimizer历史。原边界source为 `bc052a3744528277f00a7a9a5566aa4a6d7393ed`；完整c、source、参数顺序、阶段、buffer及标签核对见[边界记录](records/prefix_identity_v9.json)。C白名单没有 reference_state、D模型、Phi/Q或p4/p5场。C声明 benchmark_previously_seen=true，reference_used_for_training=false、features_reference_exposed=false、pde_only_solve=true、production_initialization_allowed=false。

每个接受步先同步原子保存匹配模型/buffers/GN状态/μ/h0/RNG/预算/PC来源，再发布 committed 审核行；trial独立。更新量是返回后的参数差。异常恢复匹配状态，已经耗费的作用和时间保留。SIGKILL只能保证上一成功flush/fsync/原子替换边界，不能保证 finally 保存。

C两条终态冻结并独立比较后，phase未严格合格且共同资格/资源仍合格时，自动触发D。D只用原参考的G场拟合、G乘法和完整矩JVP/VJP，不逐步调用A/AH/Gsolve或Gram factor。其标签已暴露，PDE-only、production、official始终false，任何D权重都不反馈C或其他任务。

## 资格和比较口径

[真实 GN 资格](records/gn_checks_v9.json) 包含两个 C 边界的 hidden/last/random非零实方向差分、实伴随、解析切线、K对称和能量正性、batch1/8、输入冻结及准确Gsolve；[定向测试](records/targeted_tests_v9.json) 另有非Hermitian复小模型、拒绝回滚、原子加载与PC见证。既有环境和完整矩资格复用，没有整套旧回归或 full pytest。

冻结后独立ML从参数重建q15系数并用q30复核；FE compare-only只读V1原p3参考，审核total/scattered E/H/curl、六点复场、四类各40级复通道及分母、逐级功率、R/T/A/A_volume/R00和材料/界面区域。严格原残差≤1e-6、场/通道≤1e-4、功率/能量≤1e-5、逐级功率≤1e-6。研究信号还要求同表示、共同时间下native与augmented均比V8降低至少10倍，散射L2/curl均≤0.1且更好；这仍不是严格合格。

共同时间比较只选择两边真正保留的、目标时间之前最近 committed 状态，报告实际时间差，不插值造场、不用参考误差挑最佳状态。原L-BFGS作为已有对照，不重跑。历史前缀计入每条逻辑路径上限，但不在全项目账重复计费。训练墙钟包含导入/加载、fresh Gram/PC、拒绝试探、保存和原方程审核；独立验收及辅助费用另列全账。

## 本轮状态

当前 A/B 已完成，C仍在执行；本节将在 C/D/E 冻结后用实际终态、原残差、场/功率和全部资源数值替换。不得将这条过程状态作为最终交付或正常预算结束证据。
