# Response V7：材料解除，真实接口通过，三条求解路线均未资格化

**V7_MATERIAL_FIXED_NEURAL_FE_CONTINUATION 已完成 M0–M4 的适用部分。材料状态为 MATERIAL_READY_USER_SUPPLIED；真实 N1 通过，三候选全部为受控数值负结果。独立同网格 p3 参考合格，条件 p4 enrichment 不准入。神经增量未证明，最终 0.7 nm／48 小时仍 NOT_QUALIFIED。**

整理本响应时的完整实现 HEAD 为 `1ff6f8ba3dcb48dee0fd41f762bf624822ea1457`；最终文档提交 HEAD 在本轮 Git 交付回报中报告，文件不填自指 SHA。分支逐字符为 `task42_neural_coarse_inverse`，工作树 `/home/fenics/Projects/NN-Lab`，upstream `origin/task42_neural_coarse_inverse`，common Git directory `/home/fenics/Projects/Maxwell3D-Lab/task-repository.git`。从干净的 `255ca88e6f4aa2c15252a512d1d499f34c95f042` 非交互获取、仅安全快进到实际远端 Review V4 `18084a6213570e26a0a0941e628717f2c63fd00a`；运行前确认没有 Task042 活跃负载。base `ccd357885f7f9be84efe3be07868cc94f13d93fc`、初始任务文档 `f8c51c8e614edc806cf72120ac2cfd14ae8b62f7` 均为当前历史祖先。无 reset、旧工作树操作或其他分支合并。

本轮先完整读取原合同、Review V3/V4、最新响应和 outcomes。Review V4 实际 GitHub richText HTML **4 表／1 math-renderer**通过，列一致、无裸 math；review 原文未改。[渲染记录](outcomes/records/review_render_check_v7.json)。V6 材料阻塞记录及更早负结果原样保留，本轮在新记录中解除。

## 材料与实际对象

唯一 canonical 记录是 [si_optical_constants_v1.json](../../input/materials/si_optical_constants_v1.json)，ID `SI_OPTICAL_CONSTANTS_USER_20260929_V1`，内容 SHA256 `55aa34e55c5e3cc35f6849eddbd3bcc72d3b694d32bc4885299ef373acd676a2`。保留原始十进制字符串、用户原表、来源类型、review commit 和旧输入 commit/blob；不伪造数据库版本。四行均已离线加载／回归，不代表四波长扫描。

| nominal nm | Delta 原字符串 | Beta 原字符串 | 实际 n 的实／虚部 | 来源 |
|---|---|---|---|---|
| 0.7 | 0.000114859526 | 4.32477054E-06 | 0.999885140474 / 0.00000432477054 | user_supplied／user_authorized |
| 2 | 0.00119851693 | 0.000213688647 | 0.99880148307 / 0.000213688647 | user_supplied／user_authorized |
| 5 | 0.00603145547 | 0.00435380777 | 0.99396854453 / 0.00435380777 | 冻结历史输入一致 |
| 13.5 | 0.000997695141 | 0.00182649365 | 0.999002304859 / 0.00182649365 | 冻结历史输入一致 |

本次明确 `source_wavelength_nm="0.699999988"`、`nominal_wavelength_nm="0.7"`，求解仍用 0.7，不插值，只接受登记的精确 alias。沿用 exp(-iωt)，epsilon=n*n，实际 0.7 nm epsilon=`0.9997702941220071+8.648547597811433e-6i`。substrate、grating、layered background 与底端口使用同一 Si；air n=1、mu=1。[载入值](outcomes/records/material_loaded_v7.json)、[身份](outcomes/records/material_geometry_identity_v7.json)。

保持原 384-cell／p3 三维缺口：FE34050、独立 trace18144、内部13824、MPC slave2082；air200／substrate48／block136、缺口8，包含 y/z 材料变化。真实完整库存为 **top20＋bottom20＝40**，不是旧80或空气侧20总量。physical SHA `2b532f91550316b16a304f3be9ae78605816b5a2aba556f548b5bd794f82e6de`，mode SHA `93795b53d7c5aef69af66b4ff0a56fa46515771f1ec43332ec929970270ea262`；[全部通道](outcomes/records/channel_inventory_v7.csv)。

## 实际数值结果

网络产生三维复向量，经完整 Nédélec 边／面矩、方向、唯一 owner 与原 MPC 变成18144个 trace 系数；13824个内部未知量用原局部恢复，40个复 port 独立优化。网络为固定 FP64、3×64 tanh、8载波、11696参数，另80个 port 实参数。三条路线的散射 trace／port 都从零开始；已知解析背景只作原方程的精确仿射换元，内部非零初值是原局部载荷恢复，不是准确目标解或路线间 warm start。

真实 N1：原 S 配对最大2.605e-16、Sᴴ dot 最大1.917e-15、独立 native 配对最大8.491e-15；非零内部 RHS164.996、port RHS8.10559 均验证。真实方程三非零方向／9项中心差分最大1.8213e-9，分块 VJP 与一体配对0。Sᴴ仅矩阵作用，无伴随求逆。[原字段与独立复算](outcomes/records/adjoint_gradient_checks_v7.json)。

以下 native 使用固定散射 RHS 分母；未凝聚、total native 及两种 port 固定分母另存，未更换尺度制造通过。

| 路线 | 实际预算停止 | Schur | 原 native | port operation-relative | 同离散全场 L2 差 | 资格 |
|---|---|---|---|---|---|---|
| NEURAL-TRACE | wall；1611 closure，Adam500＋48完整 L-BFGS 外层调用 | 0.913263145 | 0.661163226 | 0.003140447 | 0.069196457 | 全部失败 |
| FREE-FE-OPT | 2000 closure，Adam500＋69外层调用 | 0.797338565 | 2.179411163 | 0.446120482 | 0.105509404 | 全部失败 |
| FE-LSQR | 作用预算；1921步，含审核 S1999／Sᴴ1922 | 0.071602580 | 0.028727752 | 0.656567941 | 0.104639933 | 全部失败 |

方程标准1e-6、同离散场1e-4均未满足；恢复缺陷和 slave-zero 则合格。NN 时间用尽，没有完成2000次 closure，不补跑；最后一个未完成外层调用内的 closure 全部计入。FREE的早期残差上冲原样保留。LSQR采用包括审核作用的保守2000配对上限，实际步数不冒称2000。[全审核轨迹](outcomes/records/convergence_checkpoints_v7.csv)、[对照](outcomes/records/neural_fe_comparison_v7.csv)、[独立 Gate](outcomes/records/neural_fe_gate_decisions_v7.json)。

三状态/hash 冻结后，独立 p3 小参考一次 symbolic／numeric／solve，CSR3901384 NNZ、18184 reduced rows，仅验证进程存在全局 p3 因子；symbolic603 MB，单次 ICNTL23准入9592 MB，无 OOC。因子销毁后再作独立 FE／E/H／功率。首次后处理 UFL Form 除法错误保留14.456428306s；唯一最小修复只重放受影响的后处理25.633409183s，**没有第二次分解／求解或训练**。错误前内部细分 timer 未持久化，费用包含在原整树 wall，不猜填分拆。

参考 Schur/native=`6.42415e-12/3.01796e-12`，独立 DOLFINx total native=`1.43744e-12`，R/T/A=`0.117645819/0.877047783/0.005306398`，A_volume=`0.005306398`，能量闭合2.90634e-12。它是同离散准确参考，未证明连续极限。三候选 selected E/H 与 ordered port 向量差均约0.069–0.106，能量闭合分别0.0703412／0.00733968／0.00337133，均不合格，其 RTA只作明确未资格化诊断。[复数通道与逐级功率](outcomes/records/channel_observables_v7.csv)、[E/H／盲验证](outcomes/records/independent_blind_validation_v7.json)。

NN 散射场相对差0.6613，FREE/LSQR约1.0083/0.99995；参考散射 L2=0.200411、total L2=1.91515，不能用零散射蒙混。NN得到部分场信号，仍无合格解；LSQR残差下降不等于散射误差下降。**无神经增量正结论，也不确定唯一失效原因。**

## 源码、全过程资源与边界

| 正式运行源码（完整 SHA） | 实际阶段 |
|---|---|
| `70f5f5437533693e343ede67a37363e89b062330` | M0、真实 FE N1、真实梯度 N1 |
| `7c4037a279cefd8546c51e8ae6cf0172c3eab89d` | 三条冻结路线 |
| `19adac7e3babb50c0028714684c220b713979196` | 唯一 p3 参考／后处理失败 |
| `1ff6f8ba3dcb48dee0fd41f762bf624822ea1457` | 范数最小修复后的验证重放 |

八正式阶段整树 wall **8579.825040766s**；最大同时采样树RSS **1073967104 B（1.000210 GiB）**，own swap0、GPU/VRAM0，全部后代清场。NEURAL/FREE/LSQR分别7149.384083／592.483452／564.795250s。含V6 carry101.861302031s、全部有界辅助检查／失败／后续发布费用的最终累计见[资源账](outcomes/records/resource_costs_v7.json)，低于总10h，不重置预算，不把 worker 子计时再加到父 wall。参考前异常的 symbolic/numeric/solve 单独耗时未存，不重复 LU 来补数。[各 run／环境／真实 source](outcomes/records/run_index_v7.json)、[模型与 RHS](outcomes/records/dataset_model_provenance_v7.json)。

继续用户既有 **Task042受控共享CPU授权**：仅覆盖本任务原§2.3已有heavy禁用／独占全机锁要求，原 task/review历史不改，也不宣称F0获正式review。实时拓扑、邻worker/监督器/加载线程与SMT、MemAvailable/cgroup、磁盘、GPU低开销核查后重选核，M0 CPU12、其余正式阶段CPU0；这些编号不是永久保留。MPI1、数学/Torch intra/inter-op1、DataLoader0，编译也1；仅自身nice10／idle I/O、自有锁、独立FE/ML与全部缓存／输出，原库前缀只读。16GiB hard／12GiB warn、own swap0和原系统＋128GiB邻增长余量保留。无cgroup委派，使用已有整树采样停止监督，**不冒称连续内核限额**。无不可读树样本、warning、持续PSI触发；缺可比邻阶段速率，影响及无争用性能INCONCLUSIVE，不承诺零干扰。未修改邻任务及锁、环境、亲和性、优先级、watchdog。[现场资源](outcomes/records/resource_observations_v7.json)。

候选从构建起没有 global p4 层／因子、global FE CSR/LU、Riesz/ILU逆、private audit CSR、hidden fallback 或目标teacher；保留的是局部原张量／恢复和完整端口数组，209239672B packet 加上optimizer/激活/工作向量，并非只占网络参数内存。参考 p3 LU与候选分进程，已释放。旧路线、384 teacher、seed420620、GPU、F5/p6、最大模型与四波长扫描均未运行；p4 enrichment因无同离散合格候选不准入。

最终32相关pytest、CPU-only完整closure预算回归、Ruff/format/compileall及局部文档／身份检查见[test_summary](outcomes/test_summary.md)。一次测试文件名误写已局部修正，失败费保留，无环境安装／ABI变化。没有full pytest、MPI2/4或CI通过声明，不清理继承旧checker问题。

唯一建议的下一最小试验：**只在这个固定pilot预登记一个不依赖目标准确解的对角变量尺度均衡 FE-LSQR 对照，原loss和完整验算不变**，检验残差下降却遗漏散射响应的尺度／病态因素；这是待review建议，未实施，不增加网络或重开p4路线。目标级几何、通道库存、资源配额、完整步成本和所需步数仍unknown，不由这个几个波长的micro模型外推48h。[48h账](outcomes/records/target_48h_budget_v7.json)。只推送执行分支后停止等待review，不merge。
