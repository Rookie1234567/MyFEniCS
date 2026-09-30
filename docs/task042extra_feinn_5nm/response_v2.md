# Task42extra Response V2：固定 M5 的 Gram 对角变量缩放诊断

执行分支为 `task42extra_feinn_5nm`，canonical linked worktree 为原生 Linux `/home/fenics/Projects/NN-Lab-V2`，common Git directory 是 `/home/fenics/Projects/Maxwell3D-Lab/task-repository.git`。本次从审阅基线 `8de092afa15d65ef7fa9dbaafcec8481787b80d5` 安全快进到 Review V1 发布提交 `0b61816c0189a2c05812044ab8e1d1513ef0407d`；冻结 base `fbac3d8777fcfd897d93b898cb9f460f79ddd6ff` 与任务发布提交 `3b8474bff1b3cb9321a89afbca36868a9b95153d` 均为祖先。upstream 的本地配置为 `remote=origin`、`merge=refs/heads/task42extra_feinn_5nm`，远端跟踪 ref 经仅本分支 fetch 核对；共享 `origin.fetch` 未映射此分支，所以 `@{upstream}` 符号解析不能作为已通过项。实现 source、最终交付 HEAD 和推送后 clean 状态分别报告；文档提交不能冒充运行源码。

Review V1 的 D0–D3 已完成。模型仍是 M5：5 nm Si/air 非可分三维缺口、384 hex、Nédélec p3、全部 31968 个独立复 FE 系数（边 3744、面 14400、内部 13824）、2082 个周期 slave 和准确恢复的 40 个 Fourier-DtN 端口。原材料表、mesh、mode、MPC 后全局 Gram `G`、原 `A/f/d_G/loss`、Adam500 与 L-BFGS 超参和严格物理门限均未改。只运行一次新 FREE-FE-DUAL-GRAM-DIAG；两条 FEINN 网络和 V1 三路线没有续跑。新参数 `y=0` 起步，实际物理系数始终是 `c=Dy`，其中 `D_j=1/sqrt(real(G_jj))`。梯度从原坐标 `g_c` 按 `g_y=D* g_c` 回传；所有原方程、场和端口审核恢复 `c`。`D` 来自已施加 MPC 的原 G，数组 SHA256 `3d1b8ab9d692c20f884271b4be88165c1e165b7afc83e28967246a87832a1693`，原 G 文件 SHA256 `2c984449248c02f01f4a41a681d00015bbe779add0ef30f0141d9eccf75b01c9`，原 native packet SHA256 `2dbd60267758c2c53ea62a722ee0b07fad16f3cfae3f772bb0ba4830f4e28215`。

缩放改变优化器衡量各 FE 系数步长的单位，不改变方程或散射物理。这次先检查同一固定目标中的变量尺度，目的是判断旧 FREE 即使不用网络仍未收敛，能否由简单单位均衡解释。D0 从零态和 V1 三路线最终提交态做了 4 次真实 loss/gradient 评价，逐边/面/内部族给出 `G_jj`、系数和原/缩放梯度的分位数及范数。Adam500 结束参数和可续训 optimizer state 未保存，明确标 `NOT_RETAINED`；没有回放旧训练或把 last_trial 当 committed。D1 的正性/finite、`diag(D*GD)`、3 个非零复向量、3 个非零实方向的三步长中心差分、复数共轭转置以及事务恢复均通过；最大对角偏差 `4.44e-16`，固定 M5 dot test 最大 `3.15e-15`，真实 Gsolve 最大相对残差 `1.66e-13`。合成非 Hermitian A/Hermitian 正定 G 也通过。[完整诊断](outcomes/scaling_diagnostic_v2.md)、[状态记录](outcomes/records/state_diagnostics_v2.json)、[D1记录](outcomes/records/scaling_checks_v2.json)。

| 同口径指标 / measured | V1 FREE-FE-DUAL | V2 scaled FREE | 判定 |
| --- | ---: | ---: | --- |
| 完整 closure / 完整外层 | 4000 / 649 | 4000 / 649 | 两者均 `CLOSURE_BUDGET` |
| 最终对偶 loss | 0.1038990913 | 0.0990052598 | loss 下降不代表方程收敛 |
| native / augmented 原相对残差 | 0.5969144472 / 0.5969144472 | 0.6077719288 / 0.6077719288 | 严格各≤1e-6；研究各≤0.05969144472114 |
| 原 total 增广残差 | 0.2827594249 | 0.2879026331 | 严格≤1e-6 |
| 散射 E L2 / scaled curl 相对误差 | 0.9919248991 / 0.9917554916 | 0.9542085842 / 0.9541184551 | 场严格≤1e-4；研究散射 E≤0.5 |
| total E L2 / selected total E/H | 0.680216602 / 0.672953696 / 0.670814663 | 0.654352483 / 0.646200248 / 0.644656951 | 同 p3 已保存参考 |
| 原 total port / 真出射复幅 / scattered port | 0.573349002 / 0.275179736 / 1.017927730 | 0.554438846 / 0.266103778 / 0.984354510 | 三种参考分母不同 |
| R/T/A_balance/A_volume | 0.845194/0.115246/0.0395601/0.459627 | 0.841893/0.109807/0.0483005/0.443408 | 候选未合格，仅 diagnostic |
| 最大逐级功率绝对差 / 能量闭合绝对差 | 0.0825716 / 0.420067 | 0.0765753 / 0.395107 | 严格≤1e-6 / ≤1e-5 |
| A / Aᴴ / 原方程 audit / Gsolve | 4002 / 4000 / 331 / 4003 | 4002 / 4000 / 331 / 4003 | 同数量，无隐藏更多 closure |

准确同 p3 参考的 R/T/A_balance/A_volume 是 `0.8124264991/0.0324623961/0.1551111048/0.1551111048`。V2 全 port 恢复相对误差约 `1.86e-16`、MPC slave 存储为零，但 native `0.60777`、散射 E `0.95421` 和能量闭合 `0.39511` 均未通过。独立 checker 从实际40级复向量和原 R/T/A_volume 重算 absolute、denominator、relative、逐级功率、方程与资源 Gate。严格离散资格 **false**，预登记研究正信号也 **false**，状态 `SCALING_DIAGNOSTIC_NEGATIVE`；只降低 loss 不能算求解进展。[独立 Gate](outcomes/records/gate_decisions_v2.json)、[同口径 CSV](outcomes/records/scaled_route_comparison_v2.csv)。

候选 checkpoint SHA256 `baa58092c4a6fdf18420f0169f08042e323e26d5c1ef6d188ec622f20f500aab` 已冻结。D0/D1/候选的实际 source 均为 `19c725efd27ae5daedba8e77d2ad98375711bb71`；compare-only 的实际 source 为修复 FE 进程错误导入后 clean commit `bfff1458a389b2c4a4d57112cc771bb33847c20a`。独立 compare-only 只读取 V1 已保存的同 p3 准确参考，不再次进行 MUMPS symbolic/numeric/solve（计数 0），也不创建训练用 Maxwell 全局 factor。第一次 compare 在 FE 环境因顶层 Torch 导入错误于组装前失败，修复后默认沙箱在 MPI 初始化时拒绝本地 socket；第三次受监督重试完成。两次早期失败的时间、source 和停止原因均保留，未覆盖旧 stage 或重新训练。[run index](outcomes/records/run_index_v2.json)。

小模型 `RESEARCH_ONLY_GLOBAL_RIESZ_FACTOR` 仍需每进程 fresh setup：D0/D1/候选分别 `97.1968/96.9274/101.0730 s`，对应 Gsolve `5/26/4003` 次、`1.28125/7.50272/1214.9791 s`；候选自身监督 wall `2539.8103 s`、同时树 RSS 峰 `1,365,712,896 B`、自身 swap `0`。V1 原 G 装配 `648.7655 s` 被复用，本批新增装配实耗 `0`；将其归属给候选从零成本是 `3188.576 s`，不再加入本批实际 wall。全机候选期间 `pswpin` 增 25 页，无法归因于本任务，采样自身 swap 为零。全批正式与有界轻检查实耗、浏览器及失败费用以[最终资源账](outcomes/records/resource_costs_v2.json)为准：4h 新增上限和保守原16h剩余额度均未触及；peak 是同时整树采样，不累加因子对象与阶段峰。无 cgroup 委派，约0.5s采样监督，不声称连续内核硬限或对邻任务零影响。MPI1、数学/Torch线程1、CPU-only、独立锁/cache/output、现场空闲物理核、warn12/hard16GiB、自身swap0及至少384GiB邻增长预留均沿用。

Review §8 复核了旧“出射复通道”表头：旧 FREE 的真实出射向量误差分子 `0.2512611606`、参考分母 `0.9130801711`、比值 `0.2751797362`；CSV 的原 total port 用同一分子但分母 `0.4382342339`，比值 `0.5733490017`；scattered port 又有独立分母 `0.2468359523`。V2 分别明确表头而保留 V1 原文。p4 实际 `not_run`，旧 `DISCRETIZATION_NOT_QUALIFIED` 是未准入。V1 数值峰约1.313GiB、含浏览器完整峰 `2,095,390,720 B`，口径不混同；历史 `WSL-global` 只是监测字段名。任务书 §5.4 仅按 Review V1 明示授权将 `\operatorname{Re}` 改为 `\mathrm{Re}`，旧/新 blob 分别是 `e231804fd8173acf7fc48cb17fc752e9b505c7ab` / `a0d3606aedbbce37066338de3763fe802590dedb`，数学和其他规则未改。[GitHub 实际渲染记录](outcomes/records/render_check_v2.json)显示新 review 6表/3公式、修正 task 6表/7公式无渲染错误，24张截图 hash 核验且抽查关键视图。第一次导航60秒超时、第二次仅改Firefox加载策略后成功；两次费用、树峰1,408,933,888/1,741,213,696 B及自身swap0均计入，不把第一次失败说成通过。

本次结果排除了“仅对原 G 对角做这一次固定单位均衡，就能让固定优化器取得本 M5 合格解”。散射场和部分通道略改善，但原残差更差，不能声称变量尺度是唯一根因；更一般的算子/损失几何、优化路径、开放 Maxwell 谱和网络表示仍未确定。缩放属于非神经 FREE 对照，**没有新的神经增量**。唯一后续建议是下一轮先用原算子和原损失的诊断，定位 FREE 优化在原方程与散射场双指标上停滞的具体机制，再决定是否授权新的优化试验；本批不实施其他 PC、网络训练、p4、目标尺寸5nm或0.7nm。只推送本分支后等待 review，不 merge。
