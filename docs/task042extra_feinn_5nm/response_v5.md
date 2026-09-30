# Task42extra Response V5：固定特征的输出层投影

| 身份 | 准确值 |
| --- | --- |
| branch / canonical worktree | `task42extra_feinn_5nm` / `/home/fenics/Projects/NN-Lab-V2`，工作站原生Linux |
| common Git | `/home/fenics/Projects/Maxwell3D-Lab/task-repository.git`，现场登记一致 |
| 本页生成前HEAD | `e7bc94a49a454229cfa7772f870e140511051653`；后续文档HEAD单列 |
| S0 / 唯一S1 / ML重建 / FE审核实际source | `a6ac769027384525e406537f3069607043bc4a67`，四个one-run启动时均clean |
| review发布 / 审阅基线 | `28fabffd41f042c8a4bdda6339810bb1f98a887d` / `653acdf15e8484ce3df211ca2dfb8114a107f315` |
| 原冻结base | `fbac3d8777fcfd897d93b898cb9f460f79ddd6ff`，祖先核对通过 |
| upstream配置 / 有效核对 | remote=`origin`，merge=`refs/heads/task42extra_feinn_5nm`；共享fetch映射不含该分支，`@{upstream}`不可解析；按命令级精确refspec与显式tracking ref核对 |

最终交付HEAD、显式tracking ref的ahead/behind和工作树状态由最终推送回执报告；后续文档HEAD不冒充上述实际source。

本轮取得了**稳定、实际可回写网络的固定隐藏层投影**，去掉了V4剩余G误差能量的30.180006%，但未获得表示门限或严格物理资格。G场误差 `0.0138716912975` → `0.0115909576376`，散射curl误差下降；散射E L2 `0.0132512476647` → `0.0139354062682`、native `1.60884472011` → `1.97790914967`、复通道和能量闭合反而变差。分类为 `REPRESENTATION_OR_FIT_OPTIMIZATION_UNRESOLVED`。固定特征的线性子问题已通过最优性审核；这个分类保留的是整个可变隐藏层网络及PDE求解的未决范围，不表示本轮线性优化又未完成。

## S0–S2实际完成与方法边界

本方法先把V4网络中已经学到的64个隐藏特征固定，再加常数1表示bias，只重新组合这65个特征来产生三个复电场分量。它检验现有特征里是否还有联合优化未用好的线性组合，收益是把一个非凸训练环节拆成一次小型线性诊断；代价是保存31968×195的Phi、G内积正交基及小矩阵分解，且需要已知参考标签。它不是新Maxwell求解器，也不实现完整VarPro。完整Nédélec边、面、内部矩、Piola、orientation和原MPC仍保持原接口。

冻结8576个实隐藏参数以及center/half_width坐标buffers，只改变末层390个实参数（195复系数）。6行输出按实虚两两配对，三分量各64权重＋bias。Phi只由V4最终隐藏权重和原完整矩规则构造，没有加入参考场、参考误差、POD或A逆生成的列；参考只在列已冻结后作为拟合右端项。模型始终M5、5nm Si/air、384hex、p3/q15、31968独立复FE（边3744、面14400、内部13824）、40端口。

S0用V4的最终committed NPZ与durable PT互核，未用last_trial、Adam500或最佳历史态。原a0线性映射差3.07702e-15；三个seed421501非零复向量、纯虚方向、三分量bias、内部/边/面分组与batch1/8均通过1e-10，原锚点通过1e-12。Phi只构造一次：48个≤8cell隐藏前向批、1296个有界矩列批，14.8060s、99740160B数组payload；经S0文件hash资格后S1复用，未重复195次完整网络前后向。Phi数组hash为 `13967e9173bb00e0b8f02d031f4d505124780d645aa0dbfc13094ecf5b001af2`。

小型复SPD测试覆盖满秩、重复列、近相关列、不同尺度与纯虚系数，与独立Cholesky白化SVD所得场配对；小合成矩阵factor仅用于验证。新计时的持久dummy实测导入延迟0.663786s，150s收口与至少120s留白通过，退出147.705s，过期窗口数值工作0；这不追认V4旧120s偏差。资格与原始light证据见[readout checks](outcomes/records/readout_checks_v5.json)。

新参数状态同时原子保存完整模型/buffers/参数顺序和实际c1，temporary＋flush/fsync＋原子替换。它明确是parameter-only监督诊断状态，没有optimizer，也没有混入旧L-BFGS历史。有效保全是已经成功落盘的锚点、完整Phi及新终态，不承诺SIGKILL执行finally。最终NPZ hash `2d166478509bbf14638c7beb0afcff321a5330b37f34f72c2e8737477d9cd58c`；新model-only PT hash `9d81e01df9aab13bd4e03dfb2ceebbd0e9ba7b459365356ec5ca4abcaf6909eb`。完整文件路径、hash和source见[run index](outcomes/records/run_index_v5.json)。

reference_used_for_training=true；pde_only_solve=false；production_initialization_allowed=false；pde_only_solver_qualified=false；official_candidate_results=false。只读取V4 final与V1准确散射标签，没有旧状态择优、参考生成额外列、非线性训练、G逆或新因子。主阶段只启动一次。

## 稳定性与同口径物理结果

| 固定规则 / measured、无量纲 | 实际值 | 实现Gate |
| --- | ---: | --- |
| QR门限 / SVD rcond | 1e-12 / 1e-12 | 无扫描、无ridge、无正规方程逆 |
| QR / 最终数值秩 | 195 / 195 | 无零列、无截断方向 |
| 小R最大 / 最小奇异值 | 7.42718454416 / 8.71567128684e-05 | SVD cutoff=7.42718454416e-12；仅是小R，非全局A条件数 |
| G列尺度min / max | 6.00394859055 / 225.926243866 | 正且finite，不取abs或epsilon补值 |
| Q_eff G正交性F范数 | 2.32430494152e-13 | ≤1e-9，通过 |
| 归一化Phi的QR G-F重构差 | 2.1570718079e-14 | ≤1e-9，通过 |
| 实际网络保留空间最优性 | 1.3942497013e-13 | ≤1e-9，通过；全部原列相关性另存 |
| c1对列场：欧氏 / G相对差 | 1.21297349019e-14 / 7.22686029954e-14 | ≤1e-10 / ≤1e-9，通过 |
| c1对理想投影：欧氏 / G相对差 | 6.67810729924e-13 / 1.59719321037e-13 | ≤1e-10 / ≤1e-9，通过 |
| E0² / E1² / 消除的相对能量 | 0.000192423819453 / 0.000134350298956 / 5.80735204977e-05 | 不增性通过，允许舍入增量1e-10 |
| 勾股配对缺陷 / gamma | 3.4558944248e-19 / 0.301800061254 | ≤1e-8，通过；gamma只描述此固定空间 |
| 原末层 / 修正 / 新末层复权重范数 | 2.01793620144 / 11.8324177229 / 12.100495873 | 新最大幅3.82722960787；取消放大18417.3464111，回写仍通过 |
| hidden / buffers | 字节hash完全不变 | PT与NPZ、原V4最终状态逐位核对 |

| 同p3参考 / measured、无量纲 | V4 final | V5实际网络c1 | 门限 |
| --- | ---: | ---: | --- |
| G场误差 | 0.0138716912975 | 0.0115909576376 | 表示正/部分要求三项均≤0.001/0.01，未通过 |
| 散射E L2 | 0.0132512476647 | 0.0139354062682 | 严格≤1e-4，未通过 |
| 散射scaled-curl / 完整H_code L2 | 0.0138870027008 | 0.0115255720568 | 严格≤1e-4，未通过 |
| total E L2 | 0.00908709789134 | 0.00955626248333 | 严格≤1e-4，未通过 |
| total scaled-curl / 完整H_code L2 | 0.00949580596642 | 0.00788108119955 | 严格≤1e-4，未通过 |
| 六点total复E | 0.00975197801709 | 0.00979563175999 | 严格≤1e-4，未通过 |
| 六点total复H_code | 0.00716738817286 | 0.00774628935817 | 严格≤1e-4，未通过 |
| 六点scattered复E | 0.0144133908755 | 0.0144779109614 | 严格≤1e-4，未通过 |
| 六点scattered复H_code | 0.0106715966193 | 0.0115335284392 | 严格≤1e-4，未通过 |
| native / augmented | 1.60884472011 | 1.97790914967 | 各≤1e-6，未通过 |
| 原total augmented | 0.762112577426 | 0.936939047704 | ≤1e-6，未通过 |
| 独立DOLFINx total原方程 | 0.762112577426 | 0.936939047704 | ≤1e-6，未通过 |

| 功率 / measured、入射功率归一 | 同p3参考 | V4 final | V5实际网络c1 |
| --- | ---: | ---: | ---: |
| R | 0.812426499057 | 0.813057790084 | 0.813166677492 |
| T | 0.0324623960953 | 0.0327381741782 | 0.0327293240969 |
| A_balance | 0.155111104848 | 0.154204035738 | 0.154103998411 |
| A_volume | 0.155111104847 | 0.155388025694 | 0.155420108597 |
| R00_s | 0.812256818464 | 0.812608163311 | 0.812222944068 |
| R00_p | 1.25634444139e-26 | 5.02695584979e-05 | 0.000626436218627 |
| R00_total | 0.812256818464 | 0.81265843287 | 0.812849380286 |
| abs(R+T+A_volume−1) | 2.97762e-13 | 0.00118398995593 | 0.0013161101857 |
| 最大逐级功率差 | 0 | 0.000351344847336 | 0.000626436218627 |

195列全部保留，固定线性子空间的最优性和实际网络回写已独立核验；G下降不是所有场/方程改善。完整四类40级复通道及分母、六点复E/H、逐级功率和原区域见[详细诊断](outcomes/frozen_hidden_readout_v5.md)及[原字段Gate](outcomes/records/gate_decisions_v5.json)。q15参数重建差0，q30/q15差7.89338e-13；端口与MPC恢复通过但严格方程1e-6、场/通道1e-4、功率/能量1e-5/逐级1e-6均失败。表示三项也未均≤1e-2，更未≤1e-3；不能宣称whole-network数学不可表示。

## 资源与收口

| 阶段 / measured | 监督wall / s | 完整launcher单调wall / s | 采样同时树峰 / B | own swap / B |
| --- | ---: | ---: | ---: | ---: |
| v5_readout_checks | 29.1011772191 | 30.969128705 | 711270400 | 0 |
| FEINN-FROZEN-HIDDEN-READOUT-G | 362.10759266 | 364.272690128 | 1673396224 | 0 |
| v5_readout_reconstruct | 17.1475315631 | 19.403170257 | 517783552 | 0 |
| v5_readout_compare_only | 18.6208139439 | 20.795906125 | 462159872 | 0 |

全部阶段在独立持久launcher＋watchdog＋worker链中串行，原one-run入口及分别的ML/FE activation保留；不是裸worker或无监督后台重试。CPU-only/MPI1、数学/Torch1、每次现场空闲核准入（本批CPU12），系统余量216310038528B＋至少384GiB邻任务增长＋自身预算；邻任务环境、锁、affinity、watchdog和全机swap/BLAS/CUDA未改。

本轮新Gram factor/Gsolve/Maxwell factor为0。原稀疏G payload146851456B，装配与V1因子/参考历史费用保留，新装配/分解实耗为0。S0＋S1原G作用1180列，独立checker591列，FE审核2列，合计1773≤2500；matmat按每列计数，合成小G另属light验证成本。S1 G作用嵌套35.0148s包含在父wall；完整列构造、QR/SVD、加载、hash、存盘、审核均计费。Phi/Q等数组bytes不是RSS。

数值阶段树峰1673396224B（约1.55847GiB），light checker峰1136852992B，全部自有树采样swap0并清场；tmux管理服务器在树外，launch及运行稀疏样本约4.6MB、swap0，不能当连续峰值。无cgroup委派，约0.5s整树同时RSS采样，不冒称连续内核hard limit或零干扰。主阶段完整launcher单调wall364.272690s，退出剩3235.727309s，150s cutoff从launcher准入起计时，包含导入/加载，至少120s保存余量通过。

旧保守累计44119.848638203344s及失联3284s不删除。数值及首次checker时的V5保守快照578.289767848s含直接/当前/最终120s留白，原总账44698.1384061s；这是发布前快照，后续文档/浏览器/最后checker费用继续追加在[最终资源账](outcomes/records/resource_costs_v5.json)，不重置基数。预算本批7200s、S0累计1200s、主阶段3600s及原57600s均分别检查；共享时间不用于声称算法提速。

已排除本次最终状态丢失、末层复数布局/bias/内部矩映射错误、所测G-QR正交与回写不稳、q15求积漂移、端口恢复及错误使用total/slave标签等因素。仍未证明可变隐藏层网络的表示下限、PDE残差优化的有效策略、p/h连续精度或目标规模可用性。

**下一最小建议：由review决定是否授权一个能区分隐藏特征改进与原方程约束的单项诊断；本轮不实施。** 本固定隐藏层仅重求末层不足以达到表示门限，不能推广为整个网络类不可表示；不自动继续hidden训练、VarPro、PDE微调、载波/更大网络或更多seed。目标尺寸5nm仍需另行冻结非可分几何、网格与可扩展G/求解策略后才有准入，本轮目标尺寸5nm、p4和0.7nm全部not_run。没有神经求解增量或生产/合并资格。

完整records：[设计](outcomes/records/readout_design_v5.json)、[检查](outcomes/records/readout_checks_v5.json)、[投影](outcomes/records/readout_projection_v5.json)、[对照CSV](outcomes/records/readout_comparison_v5.csv)、[run/source/hash](outcomes/records/run_index_v5.json)、[资源账](outcomes/records/resource_costs_v5.json)、[Gate](outcomes/records/gate_decisions_v5.json)、[GitHub渲染](outcomes/records/render_check_v5.json)。无full pytest、重装环境或旧heavy重跑。仅推 `HEAD:refs/heads/task42extra_feinn_5nm`，不amend/强推/merge，随后停止等待review。
