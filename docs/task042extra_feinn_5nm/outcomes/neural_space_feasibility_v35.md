# V35：固定神经空间的精度可达性

当一种网络已经产生了许多波形但解仍不准，需要区分“波形本身不够”和“幅值组合选得不好”。本轮将两份V34最终1377槽/246块冻结；任何q/kappa、窗口、T、原列掩码和MPC均不改变。A不知道参考，只最小化原方程误差；B在A封存后读取参考，只诊断最佳可表示场。代价是保存稠密列、进行G正交化和小系数因子运算，不是免费的网络预测。

| measured；M5/5nm/384hex/p3/31968复FE/40端口 | V34学习冻结空间 | V34确定性强控制空间 | 限值/含义 |
|---|---:|---:|---|
| 冻结槽 / 块 | 1377 / 246 | 1377 / 246 | 无新增容量、无新q/kappa学习 |
| A保留秩 | 1377 | 1377 | 固定rcond=1e-12 |
| A最佳native原残差 | 0.143187704283 | 0.14440693779 | 各≤1e-6，FAIL |
| A归一化一阶最优性 | 2.36446091522e-11 | 1.95701596676e-11 | ≤1e-9 |
| A全作用 / 小系统配对 | 1.92206580485e-11 | 1.20825734309e-11 | ≤1e-10 |
| A旧c/r逐位未变 | True | True | 复用原完整Gate |
| A旧实际散射E L2 | 0.0180687044393 | 0.019606287833 | ≤1e-4，FAIL；并非最佳G误差 |
| A旧实际散射H / scaled-curl | 0.0181871468678 | 0.0197167792543 | ≤1e-4，FAIL |
| A旧独立total原残差 | 0.067828267702 | 0.0684058207612 | ≤1e-6，FAIL；分子/分母见原Gate |
| A旧独立体吸收能量闭合 | 0.00483197020387 | 0.00522906780337 | ≤1e-5，FAIL |
| A旧最大逐级功率绝对差 | 0.00289648662723 | 0.00317414690233 | ≤1e-6，FAIL |
| B完成状态 | CONTROLLED_STOP_NUMERICAL_BUDGET | NOT_RUN_NUMERICAL_BUDGET | 未完成不是数学失败 |
| B最终保留秩 | UNKNOWN | UNKNOWN | 最后日志的930选列不是最终SVD数值秩 |
| B实际最佳G相对场误差 | UNKNOWN_NOT_COMPLETED | UNKNOWN_NOT_COMPLETED | 联合E/curl必要门1e-4 |
| B数值最优误差下估计 | UNKNOWN | UNKNOWN | 浮点估计，非区间证明 |
| B数值归因 | INCONCLUSIVE_NOT_COMPLETED | INCONCLUSIVE_NOT_COMPLETED | 仅当前固定空间 |
| B散射E L2 | NOT_RUN | NOT_RUN | 各≤1e-4；原参考分母 |
| B散射H / scaled-curl | NOT_RUN | NOT_RUN | 各≤1e-4；原参考分母 |
| B总E L2 | NOT_RUN | NOT_RUN | 各≤1e-4；原参考分母 |
| B总H / scaled-curl | NOT_RUN | NOT_RUN | 各≤1e-4；原参考分母 |
| B native原残差 | NOT_RUN | NOT_RUN | 各≤1e-6；oracle永远不是无标签求解 |
| B独立体吸收能量闭合 | NOT_RUN | NOT_RUN | ≤1e-5；diagnostic |
| B最大逐级功率绝对差 | NOT_RUN | NOT_RUN | ≤1e-6 |
| B模型完整矩重建 | NOT_RUN | NOT_RUN | ≤1e-10；实际与producer分别评分 |

A两空间和D投入决定完成；B触发不可重置的A/B共享7200s硬预算，随后因空间子目录缺失而写出失败。原WORKER_FAILED日志及费用保留；目录修复和5项定向测试通过后，C只恢复未完成元数据，并核对A两份旧场身份/复用原Gate。B没有已提交oracle场，最佳G场误差、最终秩、最优性及新场物理Gate均UNKNOWN/NOT_RUN；没有启动第二次投影。

## 数学和稳定性限定

用U表示当前固定波形经完整Nédélec边/面/内部矩后的幅值列，不代表全FE空间或该网络所有可能波形。

```math
a_r=\arg\min_a\|AUa-f\|_2,\qquad
a_G=\arg\min_a\|Ua-c_{\rm ref}\|_G.
```

G是原正定场内积，ell=5nm，误差直接形成差场再积分，不从两个相近大能量相减。

```math
\|e\|_G^2=\|E_e\|_{L^2}^2+25\|\mathrm{curl}E_e\|_{L^2}^2.
```

两遍正交化产生V，小M=V*GV用于测量正交缺陷和剩余最优性缺口。rho用M-I的F范数上估计；若rho<1，缺口上估计为s*s/(1-rho)，s=V*Ge。完整oracle本应核验原U反变换、实际点值完整矩和独立FE q15/q30；本次没有完成oracle，以上B资格均NOT_RUN。全秩/可靠误差远离1e-4时，只能排除当前固定空间同时达到E与curl门；若截断、稳定性不合格或误差近门，归因INCONCLUSIVE。它不是区间算术证明，更不是所有NN无解。

V34学习冻结空间：CONTROLLED_STOP_NUMERICAL_BUDGET；原A最佳残差仍FAIL，但B最佳场精度和表示归因保留UNKNOWN。

V34确定性强控制空间：NOT_RUN_NUMERICAL_BUDGET；原A最佳残差仍FAIL，但B最佳场精度和表示归因保留UNKNOWN。

## 实际审核与数据边界

A两态旧c/r逐位未变；原场Gate从已绑定V34独立数组checker复用。B未生成新幅值/模型，未运行新场FE/pure验收；C只核对旧场身份并复用旧实际网络/producer Gate，参考没有反馈A或训练。所有B输出永久参考暴露、PDE-only/生产初值/official均false。原参考是V1同p3散射场，hash=0c3c0574a8c1eddcadfb56268e00c08e55d5cb15d44c0c76e873fcea0c467ff7，不换p4/p5标签。

旧两态全部四类40复通道及原分母、每级功率、六点三分量、材料/界面区域继续绑定V34原CSV，[完整Gate](records/joint_gates_v35.json)引用原记录；本次没有新场CSV。旧场未重复健康FE后处理；未完成字段不标通过，oracle永远不是无标签求解。

[原最优性](records/unlabelled_optimality_v35.json)、[最佳场](records/field_oracle_v35.json)、[全部谱/尺度](records/rank_spectra_scales_v35.csv)、[秩/资格](records/rank_stability_v35.json)、[费用](records/cost_capacity_v35.json)、[修复](records/repair_journal_v35.json)、[run/source](records/run_index_v35.json)。大列库、QR、projection和全场数组保存在ignored目录，见[hash索引](records/raw_artifact_index_v35.json)。
