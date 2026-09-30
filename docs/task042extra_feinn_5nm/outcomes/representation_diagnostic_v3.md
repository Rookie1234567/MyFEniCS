# Task42extra V3：参考已暴露的固定网络表示诊断

本批问题是：原来的网络训练未解出 Maxwell 方程，是因为固定坐标网络难以产生所需有限元场，还是因为以原方程残差优化参数太困难？为把两者分开，P0仅观察既有终态的误差与梯度，P1明确把**已保存的同离散准确散射场**作为训练标签，P2再用独立 FE 进程核对冻结网络。P1是监督表示诊断，`reference_used_for_training=true`、`pde_only_solve=false`、`production_initialization_allowed=false`；即使场与准确参考接近，也不是无标签 Maxwell 求解器通过。

| 身份 / 单位 | 固定值或来源 | 意义 |
| --- | --- | --- |
| 模型 | 5 nm Si/air、真实非可分三维缺口、384 hex、Nédélec p3/q15 | 只在原 M5 同一离散内比较 |
| 未知量 | 31968 个独立复 FE 系数：边 3744、面 14400、内部 13824；2082 slave；40 端口 | 网络仍经完整矩产生全部系数，端口由原关系恢复 |
| 网络 | 3→64→64→64→6 tanh、8966 实参数、FP64、seed 421001 | 隐藏层固定随机初始化，末层零初始化，无旧权重热启动 |
| 标签 | V1 独立参考 `reference_state.npz` 中 master 顺序的散射系数 | hash 与原 native、Gram、材料、mesh/mode/背景绑定；不是 total 场或含 slave 存储 |
| 对照边界 | V1/V2 无标签负结果原样保留；p4、目标尺寸 5 nm 与 0.7 nm 均未运行 | 不把监督权重接回旧路线或其他任务 |

## P0：有限误差与原残差几何

误差用同一正定 Gram `G` 计量；残差仍用原 `A` 和 `f`，没有形成 Maxwell 全局因子。`E_G` 是候选场到同 p3 参考的相对 G 距离；`R_G` 是两者原方程残差差在 G 对偶范数中的相对长度。余弦 1 表示原负梯度正指向参考修正，0 表示几乎正交；它只描述已保存状态的一个方向，不是全局条件数。

```math
e=c-c_{\rm ref},\quad r=Ac-f,\quad
E_G=\sqrt{e^*Ge/(c_{\rm ref}^*Gc_{\rm ref})},\quad
R_G=\sqrt{(Ae)^*G^{-1}(Ae)/(f^*G^{-1}f)}.
```

| 已保存状态 / measured | native 相对残差 | E_G | R_G | 负梯度与参考修正的实余弦 | 原对偶 loss |
| --- | ---: | ---: | ---: | ---: | ---: |
| 零态 | 1.000000 | 1.000000 | 1.000000 | 0.001213 | 0.500000 |
| V1 FREE 最终提交态 | 0.596914 | 0.991760 | 0.455849 | 0.023057 | 0.103899 |
| V2 Gram-diag FREE 最终实际 c | 0.607772 | 0.954121 | 0.444984 | 0.005079 | 0.0990053 |
| V1 FEINN-DUAL 最终提交态 | 1.102645 | 0.998906 | 0.810249 | 0.000824 | 0.328252 |

四态 `A(c-c_ref)=r-r_ref` 的最大 operation-scaled 差约 `3.45e-13`，明确计算了参考原残差 `6.78884e-12`，没有把它设为零。V1/V2 FREE 的原负梯度各只作一次解析最优**实**步长见证，不更新训练状态：V1 `t*=1.44619e-7` 后 native `0.596914→0.596909`、E_G `0.991759665171→0.991759665043`；V2 `t*=2.37120e-7` 后 native `0.607772→0.606907`、E_G `0.954120675438→0.954120669454`。它们只说明这两个局部负梯度方向对场修正几乎无帮助，不能推断其他方向不可能改善。

P0只建立一次 `RESEARCH_ONLY_GLOBAL_RIESZ_FACTOR`：31968 行、symbolic L NNZ 18839705、setup `96.8800 s`、11 次准确 Gsolve 共 `3.46563 s`、最大 true relative `2.15e-13`，结束释放。A/Aᴴ 各 11/4 次，worker `102.974 s`，正式监督 `104.833 s`，同时进程树采样 RSS 峰 `1,038,958,592 B`、自身 swap `0`。这些 Gram 费用在 P0 实耗，不隐藏到拟合里；P1 闭包不建 G 因子。

## P1：唯一监督拟合

P1 固定目标只衡量完整 FE 插值系数与已知参考的 G 场距离。和原 Maxwell 残差训练相比，它不在每个 closure 调用 A、Aᴴ 或 Gsolve；代价是准确解已经暴露给训练，因而结果只能判定这组参数是否能重构**这个**参考。一个 closure 指一次完整的网络前向、loss 与反向梯度评价，不等同于数据集训练中的 epoch。

```math
J_{\rm fit}=\frac{(c(\theta)-c_{\rm ref})^*G(c(\theta)-c_{\rm ref})}{2c_{\rm ref}^*Gc_{\rm ref}},\quad
g_c=\frac{G(c(\theta)-c_{\rm ref})}{c_{\rm ref}^*Gc_{\rm ref}}.
```

真实 M5 检查已通过：合成复数目标相对梯度差 `3.01e-11`；batch1/8 的 c/loss/实参数梯度差分别 `4.22e-16/0/7.96e-16`；三个非零实方向在 `1e-4/1e-5/1e-6` 中心差分的最佳相对误差均低于 `1e-5`；事务异常后参数逐位恢复。检查没有调用 A/Aᴴ/Gsolve。训练仍是 Adam500（lr1e-3、无 WD）加原 L-BFGS（history20、strong-Wolfe、max_iter20/max_eval25、原停止门限），一次 seed、最多 4000 完整 closure/3h，含加载审核保存。

P1 唯一训练没有正常结束：执行会话在约第825次完整closure后消失，原监督器未留下`run_summary`，也未保存final或last_trial checkpoint。最近一次第817次已提交参数审核为`E_G=0.0603363`、native`8.19881`，但其参数为`NOT_RETAINED`，不能当作可复验终态。原始zero和Adam500参数checkpoint字节hash完整，后者是最后可重建的提交态，`E_G=0.200821`、native`14.26346`。原始采样至少3097.314s，按“启动到首次确认进程消失”保守计3284s，树RSS峰697479168B、自身swap0；中断原因没有被监督日志确认，不能写成数值失败或预算正常停止。[中断记录](records/fit_interruption_v3.json)。本批不重启/续训，也不从Adam500补跑后期历史。

中间日志中的 `parameter_update_norm` 在 Adam 更新前采样，所列 0 不是实际接受步长；对应逐 25 closure 的真实更新范数未保存，最终证据将标 `NOT_RETAINED`。该遥测缺口不改变拟合目标或冻结场，但不应改写为完整通过的历史 Gate；本批不重跑唯一候选补录。

## P2：冻结后独立 FE 复验

**PENDING_RETAINED_SNAPSHOT_COMPARE**。审核只从Adam500留存参数重新生成全部q15系数，并只作一次q30求积复核；独立FE进程只加载V1参考，不调用MUMPS symbolic/numeric/solve。除散射和total E/H、scaled-curl、40个有序复通道、R/T/A、A_volume与能量闭合，还用同一场积分计算air/substrate/grating/材料跃迁双侧单元的局部误差。原方程与场/功率严格门限保持不变，`official_candidate_results=false`和`pde_only_solver_qualified=false`是数据使用策略，不覆盖真实数值检查字段。失去最终参数意味着不能将该快照的研究阈值分类冒充完整P1结论。

## 研究判断、成本及边界

**PENDING_RETAINED_SNAPSHOT_COMPARE**。V1/V2 的三路线无标签负结果、p4 未准入和目标尺寸未运行状态不改。中断让最终表示能力判断保持未解决；仅存快照即使有数值改善，也不是完整训练终态或无标签解。任何拟合权重都不得用作旧路线、Task042 或 0.7 nm 的初始化。
