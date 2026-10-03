# Response V12：保存轨迹归因完成，暂停神经主求解器晋级

本轮停止神经主求解器晋级：`FEINN_MAIN_SOLVER_ON_HOLD`、`NO_VERIFIED_NN_INCREMENT`。没有新训练、监督拟合、权重/尺度扫描、传统求解器复制或参考重求。已冻结18个指定保存场，重算退化段，完成两态局部参数诊断；所有前向见证立即恢复原参数。中间改善、最终退化与未运行项均保留。参考场只在标记为 `REFERENCE_EXPOSED_DIAGNOSTIC_ONLY` 的分析中使用，未形成新PDE-only候选。

原残差衡量有限元场代入方程后还差多少；场误差衡量它离同一p3准确参考有多远。Riesz对偶loss用G的逆给残差加权，E_G用G衡量电场和空间旋转（curl）的误差。二者并非同一个尺子。本轮只读取已保存模型和场、计算真实更新的方向贡献；局部投影用于解释附近参数能生成什么变化，不作为新解或训练初值。

| 身份 | 值 |
| --- | --- |
| branch / explicit tracking | task42extra_feinn_5nm / refs/remotes/origin/task42extra_feinn_5nm |
| Review V11发布（已包含） | bafc9570110bbdcd28de455e9cd4552f3cd80215 |
| 冻结base | fbac3d8777fcfd897d93b898cb9f460f79ddd6ff |
| canonical / worktree | /home/fenics/Projects/Maxwell3D-Lab/task-repository.git / /home/fenics/Projects/NN-Lab-V2 |
| 环境 | 工作站原生Linux，既有FE complex128/int64/MPI1与ML CPU FP64，线程1 |
| 最终文档HEAD / 推送后tracking | 结束回复精确核报；文档HEAD不冒充运行source |
| production / merge | false / NOT_APPROVED |

| 阶段 | 真实运行source |
| --- | --- |
| v12_local_parameter_diagnostic / COMPLETED | bc4c2026f8a9510c90424d24f1808a288413bba4 |
| v12_saved_field_attribution / RESOURCE_WINDOW_UNAVAILABLE | worker未启动；见原manifest |
| v12_saved_field_attribution / COMPLETED | bc4c2026f8a9510c90424d24f1808a288413bba4 |
| v12_saved_field_integrals / RESOURCE_WINDOW_UNAVAILABLE | worker未启动；见原manifest |
| v12_saved_state_freeze / COMPLETED | 521b9bd6efc387de0ba6ce414ea2bfd0abf3bb1a |
| v12_test_space_witness / WORKER_FAILED | bc4c2026f8a9510c90424d24f1808a288413bba4 |
| v12_test_space_witness / COMPLETED | 6c8440e991ba1a960f0c0556319f3cc60148d0e1 |

## 相对V1–V11新增知识

A冻结12+6场，完整GN参数/buffers/optimizer/RNG/c保留；V2/V6缺optimizer/RNG明确NOT_RETAINED。B恒等式最大3.83e-13，六次真实更新的G交叉全部为正、对偶交叉为负；总变化+6.29082 G能量和−1.7034e-5对偶残差能量，排除仅归一化假象。8列观察空间rank5、放大范围有限方向相差约446倍，不是全局条件数。

C1两态同方向集合里参考投影可去除97.41%/98.74% G误差能量，残差投影只去除0.161%/0.576%残差能量且使场误差更差。固定小幅前向支持目标/方向不一致；参数立即恢复，不输出新权重。JVP/VJP独立配对0、实伴随≤7.87e-18、FD≤2.40e-9。不是整个网络类表达下限，不证明使用标签后可独立求解。

| 保存态 | native原残差 | 散射E L2 | 散射curl/H | E_G | 原Riesz对偶loss |
| --- | --- | --- | --- | --- | --- |
| phase75 | 0.978821198632 | 0.362017880269 | 0.362633734179 | 0.36261857554 | 0.23467076194 |
| M3600 | 0.885852183253 | 0.0933002764708 | 0.0935415151962 | 0.0935355798945 | 0.094314671576 |
| Mfinal | 0.846541904928 | 0.122944519716 | 0.123039105854 | 0.123036776653 | 0.0872060784095 |
| Ifinal | 0.984363547288 | 0.15960198092 | 0.160305545482 | 0.160288250677 | 0.153600031731 |
| V10phasefit | 0.53147218171 | 0.00955792520676 | 0.0100342087994 | 0.0100227477417 | 0.275158308964 |

| 保存态，功率均diagnostic | R_total | T_total | A_balance | A_volume | R00_s | R00_p | R00_total | 能量闭合差 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| M3600 | 0.788817182333 | 0.0269769009664 | 0.1842059167 | 0.138201163764 | 0.788743998879 | 1.7473985426e-06 | 0.788745746278 | 0.0460047529365 |
| Mfinal | 0.795461317421 | 0.0250470810956 | 0.179491601483 | 0.13026336919 | 0.795391017878 | 1.98764166035e-06 | 0.79539300552 | 0.0492282322929 |
| Ifinal | 0.798616960425 | 0.0385522797318 | 0.162830759843 | 0.192157048548 | 0.798574485565 | 6.36199208866e-07 | 0.798575121764 | 0.0293262887055 |
| phase75 | 0.794315997762 | 0.0513415797058 | 0.154342422532 | 0.247090170825 | 0.794296464658 | 4.64479356959e-07 | 0.794296929137 | 0.0927477482932 |
| V10phasefit | 0.812382059735 | 0.0325867236767 | 0.155031216588 | 0.155125874747 | 0.812305177419 | 5.79143279275e-07 | 0.812305756562 | 9.46581584893e-05 |

严格原方程1e-6、场/通道1e-4、功率/能量1e-5及逐级功率1e-6没有放宽；NN保存态仍全部失败，R/T/A均diagnostic。完整分母、六点E/H、四类40通道、功率/区域见[专题](outcomes/diagnostic_attribution_v12.md)及[复用记录](outcomes/records/saved_physics_reuse_v12.json)。

## 受控失败、修复与未运行

B首次无空闲物理核拒绝，61.43s保留；一次新原准入窗口后B完成。新FE交叉/邻层积分再次资源拒绝61.41s，没有循环重新准入，未运行项保留。C1独立完成；C2状态`EXISTING_P4_TEST_SPACE_WITNESS_COMPLETE`。C2首次c/c_scattered字段接线失败95.04s保留，核对V8原schema、增加定向损坏字段/形状测试后最小修复；不新factor、不重求p4。初始QR取消余项尺度修复亦保留失败费用。本批最多两次工程修复，已用两次；资源重新准入不是调参或训练重启。

D0已直接否决当前轨迹的单次NN初始化：原完整baseline672.46s，NN前缀下界15758.74s；时间/内存均无20%净收益资格。D1按条件不运行。监督约1%压缩精度也未达1e-4；没有虚构多查询摊销或新监督训练。

## 全部资源、证据与交付边界

| 阶段/attempt | 分类 | 完整收费s | 树峰GiB | 自身swap | 清场 |
| --- | --- | --- | --- | --- | --- |
| task42extra_v12_local_parameter_diagnostic_20261003T000944472791Z | COMPLETED | 380.331780125 | 3.06216430664 | 0 | 1 |
| task42extra_v12_saved_field_attribution_20261003T000141837992Z | RESOURCE_WINDOW_UNAVAILABLE | 61.4299889749 | NOT_SAMPLED_WORKER_NOT_STARTED | NOT_SAMPLED | 1 |
| task42extra_v12_saved_field_attribution_20261003T000343740364Z | COMPLETED | 222.962651554 | 1.02564239502 | 0 | 1 |
| task42extra_v12_saved_field_integrals_20261003T000753949348Z | RESOURCE_WINDOW_UNAVAILABLE | 61.4147667839 | NOT_SAMPLED_WORKER_NOT_STARTED | NOT_SAMPLED | 1 |
| task42extra_v12_saved_state_freeze_20261002T235004967432Z | COMPLETED | 67.273354323 | 0.284664154053 | 0 | 1 |
| task42extra_v12_test_space_witness_20261003T001657648749Z | WORKER_FAILED | 95.0364578021 | 0.26989364624 | 0 | 1 |
| task42extra_v12_test_space_witness_20261003T002021620377Z | COMPLETED | 98.596716948 | 0.288215637207 | 0 | 1 |

B/C1各一个RESEARCH_ONLY_GLOBAL_RIESZ_FACTOR，完整setup/solve/release收费；B A52/Gsolve52/Gmv86，C1 A42/AH2/Gsolve43/Gmv86，JVP36/VJP8，固定前向8次。不是整条路线无全局因子。没有新Maxwell因子、G4、PDE参考或训练。父子计时不相加，原G工作空间容量门、整树warn12/hard16GiB、轻2GiB、自身swap/OOC0、系统余量+384GiB邻增长均保留；仅管理自身，已完成阶段全部清场。

| Gram阶段，31968行/7336179 NNZ | 完整setup s（含symbolic/numeric） | 所有solve s/次数 | 释放前/后worker RSS B | 最大solve真残差 |
| --- | --- | --- | --- | --- |
| B，CSR payload146851456 B | 130.912333（0.284899/128.888888） | 21.193984/52 | 919330816/408231936 | 3.65862e-13 |
| C1，同一因子用于两态 | 142.768210（0.374993/139.785018） | 17.270223/43 | 3231465472/2720362496 | 1.40112e-12 |

上表是worker生命周期采样，整树同时峰值另见阶段表，不能把数组bytes或单进程RSS当整树峰值；子计时已包含在完整launcher费用中。

新增上限21600s；当前原始stage/轻测收费1017.209998700s，保守整批墙钟上界3234.677681s，后续发布尾段在资源记录补记。历史154319.25454592914s不清零，已知审阅尾段2.783112721s另列，缺计时可选拒绝仍NOT_RETAINED不删除。整批墙钟上界覆盖未分项的读取、代码、IO和发布，非数值worker耗时，不与worker相加。

定向代数、损坏记录、schema、8-cell FE接线、独立checker、Ruff/compileall与新页解析分别见[tests](outcomes/records/targeted_tests_v12.json)。不full pytest、不重复缓存benchmark/旧资格、不重装ABI/BLAS/CUDA；FE顶层无Torch。浏览器真实GitHub渲染与本地解析分列见[render](outcomes/records/render_check_v12.json)，若服务错误或准入拒绝不伪造PASS。

分组件已有绑定source/hash的通过证据；最后合并24项的调用因没有空闲物理核而未启动，明确`NOT_RUN_RESOURCE_WINDOW_UNAVAILABLE`，没有把它写成24/24通过，也没有原样重跑。独立checker的新6项正/损坏记录测试及原向量重算分别完成。

[run/source/hash](outcomes/records/run_index_v12.json)、[完整账](outcomes/records/resource_costs_v12.json)、[原字段Gate](outcomes/records/gate_decisions_v12.json)、[独立checker](outcomes/records/independent_checker_v12.json)、[修复](outcomes/records/repair_log_v12.json)、[依赖组manifest](outcomes/records/publication_manifest_v12.json)。同步summary、progress、模型总账、tests和changed_files；大数组/PT/optimizer/完整history留ignored。

原尺寸.7nm、十进制2TB整机和48h完整工作流程目标不变，未资格化。下一步为暂停FEINN主解及当前初始化探索；新的无标签联合改进干预与非NN对照须由主控预登记，不把本次参考梯度接入训练。本批只推送精确FEINN分支，清场后等待审阅，不合并master。
