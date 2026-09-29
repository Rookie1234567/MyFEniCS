# Task042 Response V6

**MATERIAL_0P7NM_BLOCKED**：完成N0几何与N1材料独立接口，三条真实求解路线尚未启动。按 [Review V3](review_report_v3.md) 关闭旧p4低秩／系数网络路线，V5 port-only augmentation未实施；旧源码、V1–V5负结果及seed420620封存池保持。

| 本轮必答项 | 实际结果／边界 |
|---|---|
| Git／源码 | 原HEAD `0caf151a8274f87363d7dc804d89070f7ba9eb7d` 安全FF至review `d5f45787168123a1680523ccf8e73c33de7c7a34`。成功接口run source **`2a2cb4af78ba869a26a1254b4b4b76c9ac158366`**；初次失败source `64c128c3541887e22788343692cc4f7832a45696`保留。文档HEAD不冒充run source。 |
| Si0.7nm／新几何 | Si n／epsilon及原源版本不足；完整读取Task039原提交报告，确认 `0P7NM_MATERIAL_INPUT_INCOMPLETE`，不猜填或用13.5/2nm。实际384-cell p3缺口网格，air200／substrate48／block136、notch8，y/z变化真实；FE34050、独立trace18144、slave2082。 |
| 网络实际计算什么 | FP64、3×64 tanh、8三分量复包络、11696参数；通过完整36边＋72面矩、Piola、orientation和原MPC产生18144 master trace系数。13824内部物理未知量未恢复，完整物理port未建；3个非零测试port仅用于合成接口见证。 |
| 插值／导数 | FE矩配对约1.8e-15，MPC展开缺陷0；q15/q30 NN矩相对差1.1695e-15。合成非Hermitian3实方向FD最大相对差9.7612e-9，chunk／一体梯度差6.8049e-16。真实S/Sᴴ/native/port/recovery均not_run，完整N1未通过。 |
| 三路线／神经增量 | NEURAL-TRACE、FREE-FE-OPT、FE-LSQR均not_run，优化更新／closure／原S次数均0；无准确参考、teacher、训练或warm start。神经增量UNKNOWN_NOT_EVALUATED。 |
| 完整原残差与E/H／功率 | 原Schur、未凝聚增广native、port、恢复、同离散E/H、全复通道、R/T/A/A_volume／能量闭合均not_run，未生成official物理解。空气侧20通道仅derived，底侧及总量unknown，不复用80。 |
| 资源／共享影响 | 三次正式接口启动含一次失败共26.136697164s，整树采样峰314408960B、own swap0；FE现场CPU0、ML重选CPU12，MPI1／实际数学线程1。自有锁、16/12GiB树监督、独立FE/ML/cache、GPU分配0。无cgroup委派，真实0.5s采样；没有触线或持续压力，缺可比邻阶段指标，影响inconclusive。 |
| 48h差距 | 材料、目标级尺寸／精度／完整通道／资源配额、真实S/Sᴴ及完整步成本／所需步数unknown。micro不是最终目标，最终0.7nm／48h NOT_QUALIFIED。 |

保留用户对Task042受控共享CPU的授权，覆盖原task §2.3 heavy／独占要求，不改邻任务及其监督器、锁、环境、亲和性或优先级，也不宣称F0已经正式review。全部成本标shared-workstation。没有全局目标或p4因子、Riesz／ILU隐藏逆、fallback、private audit CSR、目标准确解读取或旧teacher重跑。

第一次FE配对失败源于原配置使用[0,L]而新网格居中；一次research-only坐标载体修复后重放成功，原config/Floquet/default保持，失败3.329931s计入预算。23相关pytest和两ML断言、新增Ruff/format/compileall及输入检查通过；ML缺pytest用标准库执行同样断言，未安装包。Review V3实际GitHub渲染4表／4math通过，原review不改。继承总账checker问题如实保留，未进行full pytest／CI或全仓清理。

完整阶段与内存／计时口径见 [本轮结果](outcomes/neural_fe_single_solve_v6.md)、[source／资源账](outcomes/records/run_index_v6.json)、[独立Gate](outcomes/records/neural_fe_gate_decisions_v6.json)、[48h未知项](outcomes/records/target_48h_budget_v6.json)。[辅助／发布成本](outcomes/records/post_checks_v6.json)包含失败与后续静态费用，全部监督检查同时树RSS峰386977792B；交互编辑／Git的全会话峰未连续计量，不伪称精确。

**唯一下一最小步骤：补齐并审核Si0.7nm复光学常数的原始来源／版本／单位／符号／数值。** 本批已按材料停止条件收口，只提交并推送 `task42_neural_coarse_inverse` 等review，不自动实施下一阶段、不启动目标规模、不merge master。原base `ccd357885f7f9be84efe3be07868cc94f13d93fc` 与初始任务锚点均在当前历史中。
