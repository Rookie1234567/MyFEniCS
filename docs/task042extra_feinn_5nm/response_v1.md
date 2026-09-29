# Task42extra Response V1

分支 `task42extra_feinn_5nm`；本响应生成前HEAD `7a79b3007d92a9b699e0451d0c8b6dfdacee7ad9`（数值阶段source分别见下面run表，后续文档提交不是运行源码）。冻结base `fbac3d8777fcfd897d93b898cb9f460f79ddd6ff` 与任务发布 `3b8474bff1b3cb9321a89afbca36868a9b95153d` 均为祖先。最终交付HEAD由本响应所在Git提交链和最终推送报告给出，避免自引用hash。

仓库根为原生Linux工作站 `/home/fenics/Projects/NN-Lab-V2`，已登记到现场核对的 `/home/fenics/Projects/Maxwell3D-Lab/task-repository.git`，是独立linked worktree。upstream配置为remote `origin`、merge `refs/heads/task42extra_feinn_5nm`；以命令级fetch refspec核对 `origin/task42extra_feinn_5nm`，共享origin/fetch和全局配置未改。正式阶段branch/HEAD/status核验clean，base/publish ancestry通过。推送后的准确HEAD/upstream与clean状态由最终报告确认。

E0环境与Git完成，E1完整接口通过，E2三条独立路线已冻结；E3参考/物理结果和E4条件p4见下表，E5完整资源账及目标容量已提交。小型M5三路线同离散通过 0/3；更大5nm与0.7nm未运行。

本轮比较的是同一M5、同全部独立FE、同原方程/材料/模式/初值的三条路线。坐标网络通过积分产生边、面和内部矩；FREE直接优化完整复系数。DUAL用正定测试内积衡量弱残差，增加真实稀疏Gram因子成本。LE与LD不能直接按数字大小比较精度。

| 路线 | native / augmented | 散射E L2 / scaled-curl | selected total E/H | 出射复通道 | R/T/A_balance/A_volume |
| --- | --- | --- | --- | --- | --- |
| FEINN-EUC | 0.928287/0.928287 | 0.999215/0.999234 | 0.678586/0.671902 | 0.270177 | 0.837415/0.113261/0.0493242/0.465089 |
| FEINN-DUAL | 1.10264/1.10264 | 0.998885/0.998906 | 0.678322/0.671303 | 0.270119 | 0.837391/0.113257/0.0493519/0.464992 |
| FREE-FE-DUAL | 0.596914/0.596914 | 0.991925/0.991755 | 0.672954/0.670815 | 0.27518 | 0.845194/0.115246/0.0395601/0.459627 |

| 场身份 | R00_s / R00_p / R00_total | 最大逐级功率绝对差 | abs(R+T+A_volume−1) |
| --- | --- | --- | --- |
| REFERENCE | 0.812257/1.25634e-26/0.812257 | reference | 2.97762e-13 |
| FEINN-EUC | 0.837279/6.91785e-10/0.837279 | 0.080903 | 0.415764 |
| FEINN-DUAL | 0.837271/7.0838e-11/0.837271 | 0.0808367 | 0.41564 |
| FREE-FE-DUAL | 0.844749/1.02397e-08/0.844749 | 0.0825716 | 0.420067 |

| 路线 | 实际停止 | 方程 / 场 / 功率 | 状态 |
| --- | --- | --- | --- |
| FEINN-EUC | WALL_BUDGET | False/False/False | FEINN_OPTIMIZATION_NEGATIVE |
| FEINN-DUAL | WALL_BUDGET | False/False/False | FEINN_OPTIMIZATION_NEGATIVE |
| FREE-FE-DUAL | CLOSURE_BUDGET | False/False/False | FEINN_OPTIMIZATION_NEGATIVE |

三候选checkpoint/hash冻结后，独立DOLFINx原体矩阵和完整未凝聚增广系统建立一次MUMPS准确参考；factor/matrix销毁且RSS下降后才后处理。参考从未反馈训练。它是同p3离散authority，不是连续解。

| 独立参考量 / 单位 | 实测值 | 资格边界 |
| --- | --- | --- |
| native / augmented | 6.78884e-12/6.78884e-12 | 目标各≤1e-10 |
| original total / 独立DOLFINx native | 3.51452e-12/3.26042e-12 | 原RHS，无训练反馈 |
| R / T / A_balance / A_volume | 0.812426/0.0324624/0.155111/0.155111 | 同mesh/p3 authority；不是连续解 |
| R+T+A_volume−1 / A_balance−A_volume | 2.97762e-13/2.97734e-13 | 独立吸收闭合≤1e-5 |
| Maxwell symbolic / numeric / solve / s | 0.43006/5.97992/0.361829 | reference ONLY，禁止训练fallback |
| 释放前 / 后 worker RSS / B | 1.08556e+09/2.31522e+08 | 释放factor和matrix并确认下降后才后处理 |
| reference qualified | True | 方程、能量、资源分别审核 |

全部独立31968复FE保留，其中13824内部矩由网络直接产生，未退回trace或内部局部物理恢复。原端口 `[V B;-D H]` 按alpha=solve(H,gp+Dc)准确消去；原native/增广/total方程与非零port/内部载荷、共轭转置、完整VJP通过接口资格。场/功率不能用loss替代，候选RTA未资格化时为diagnostic，原port系数与真正出射复幅都完整保留。

| 辅助量 / 单位 | 实测值 | 含义 |
| --- | --- | --- |
| Gram rows / NNZ | 31968 / 7336179 | 全部独立p3；材料无关正定测试内积 |
| Gram CSR payload / B | 146851456 | 数组体积，不是RSS |
| 首次装配 / s | 648.765 | 完整计入DUAL/FREE从零成本，研究实账只计实际一次 |
| 资格factor setup / s | 110.571 | RESEARCH_ONLY_GLOBAL_RIESZ_FACTOR；LLᴴ/AMD |
| symbolic L NNZ | 1.88397e+07 | symbolic后容量Gate，非dense inverse |
| CHOLMOD current / peak B | 5.44919e+08 / 6.33593e+08 | 辅助因子也计资源 |
| 资格Gsolve max true relative | 9.13339e-12 | 限值1e-11；训练各路线另逐次检查 |

| 路线 / research-only | fresh setup / s | 全部Gsolve / s / count | max true residual | factor current / peak B |
| --- | --- | --- | --- | --- |
| FEINN-EUC | 0 | 0 / 0 | not_run | not_run/not_run |
| FEINN-DUAL | 128.442 | 810.233 / 2390 | 6.10176e-13 | 5.44919e+08/6.33593e+08 |
| FREE-FE-DUAL | 113.025 | 1394.34 / 4003 | 7.53354e-13 | 5.44919e+08/6.33593e+08 |

小模型Gram factor明确为RESEARCH_ONLY_GLOBAL_RIESZ_FACTOR，每条DUAL/FREE各计完整装配和fresh factor；EUC不加载factor。没有global Maxwell factor/CSR进入训练，没有目标准确解、teacher、旧checkpoint或监督初值。

| 路线 | closure尝试 / 完成 / 完整外层 | 实际完整wall / s (derived) | 从零归属 / s | 运行树峰 / GiB | own swap / B |
| --- | --- | --- | --- | --- | --- |
| FEINN-EUC | 2219/2219/578 | 10692.4 | 10783.2 | 0.65601 | 0 |
| FEINN-DUAL | 2387/2387/586 | 10689.9 | 11429.5 | 1.31262 | 0 |
| FREE-FE-DUAL | 4000/4000/649 | 2903.75 | 3643.38 | 1.27242 | 0 |

一个新数值stage一个进程，任务独立lock/cache/output/env；MPI1，数学/Torch线程1，CPU-only，每阶段现场选空闲物理核并避开忙碌SMT同胞（实际核号见run index），优先级只降低自身。warn12/hard16GiB、自身swap0；轻测试hard2GiB。无cgroup委派，目标0.5s采样自有subreaper及后代，不冒称内核连续限额。系统余量max128GiB/10%加384GiB邻增长预留和本任务预算；Task39/Task041/Metrology只读盘点，不修改或停止其他项目。未证明零干扰，性能/邻影响inconclusive。

度量信号 `inconclusive_not_equal_accuracy`；神经增量 `inconclusive_not_equal_accuracy`。L_E/L_D数值不能直接当同类误差；同准确性未具备时不宣称20%收益。p4 `DISCRETIZATION_NOT_QUALIFIED`，不能据同p3authority声称continuum、目标5nm或0.7nm/48h。

本任务文档实际render证据见outcomes/records/render_check_v1.json：已检查GitHub发布task实际rich-text HTML；浏览器/公式/表格视图与最终blob一致性以该记录为准，失败明确保留，不伪造截图。详细复验见[outcomes/summary](outcomes/summary.md)、[测试](outcomes/test_summary.md)、[成本](outcomes/accuracy_performance_memory.md)、[目标设计](outcomes/target_5nm_scale_plan.md)。

建议后续review只授权固定M5的一条FREE-FE-DUAL变量尺度诊断：用正定Gram对角给全部FE系数统一单位尺度，原loss、零初值、closure/wall和全部验收不变。该诊断不使用目标准确解训练、不调用Maxwell逆、不扩大模型；用于先区分优化条件问题与神经表示问题。本轮未实施。

只提交/推送本执行分支；不修改Task042历史，不amend/强推、不merge，不启动更大模型或更多波长。本轮交付后停止等待review。
