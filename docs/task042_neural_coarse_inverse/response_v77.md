# Response V77：Review V75执行结果

**固定物理阻抗配置失败并关闭。** 实际完成38块新矩阵、39个numeric与一次连续RIGHT FGMRES；32步独立原残差0.917996117703，接口残差0.919289591408，rho未过0.30门，也未超过Jacobi32步的0.388826586390。没有合格物理场，不补尾部、不改阻抗、粗层或restart。

本轮让局部波动修正穿过真实子域的人工切口：只累加保存halo单元的原Maxwell体作用，再在真实三角外面加入固定一阶出射阻抗。它改变局部预条件器，不改变全域828模式Fourier-DtN或RHS。阻抗是近似边界，局部数学通过不保证全域传播有效，也未证明边界反射是唯一根因。本批无NN。

| 同0.7nm NOTCH/25576tet/p5/828，measured | 步数 | 原true | 接口true | KSP含检查/s | 运行wrapper/s |
|---|---:|---:|---:|---:|---:|
| V76 Jacobi，历史只读 | 32 | 0.388826586390 | 0.379105019552 | 174.050 | 526.966 |
| V77物理阻抗+原粗层 | 32 | 0.917996117703 | 0.919289591408 | 521.867 | 1272.633 |

新配置更慢且残差更大。两者均未达到同正确性门，表中不是生产加速比；旧Jacobi64为丢弃旧Arnoldi基后的续算，不重跑换标签。[曲线和效果门](outcomes/records/residual_history_v77.json)

## 数学与完整原式

两实际块为最大ID36及含内部材料界面的最小ID0；新CSR对PUBLIC_BASIX局部恢复体作用加直接q15面作用差6.90e-15/7.37e-15，q13/q15逐面生产见证最大5.59e-15。周期mate先合并，域内材料界面不吸收；所有38块body cell清单与原halo逐一相等。两块分别排除了895/703个域外接触单元，排除作用范数45756.5/47067.4，证明新块不是旧主子块简单加质量。没有幅值drop、重分区或新粗空间。

独立保存数组checker重新读取新CSR、halo库存、39因子见证和PC复线性，均通过；新进程完整q15体/q63边界原式向量与producer差为0。原true/native=0.917996117703、augmented=0.919289520719、port=0.000512822009613都未过1e-6；retained未过1e-11，direct1e-10目标FAIL。MPC、恢复、Schur-original恒等式均<=1e-10。[独立数学/原式](outcomes/records/mathematical_qualification_v77.json)

完整1943745 FE、828port、native/MPC/κ、RHS/尺度及独立原式已保存。原残差>1e-2，六场积分、原240点、衍射评分、RTA和体吸收为NOT_RUN_BY_FAIL_FAST_POLICY，official=False；没有读取V70正确场作初值、PC或评分。旧连续精度FAIL及2TB/48h/NN20资格不升级。[source与全部数组](outcomes/records/source_array_bindings_v77.json)

## 实际成本、内存与身份

| V77当前增量，measured；父成本另列 | 数据 |
|---|---|
| 两块预检/38块准备/迭代完整失败尝试/独立VERIFY wrapper | 290.153 / 695.045 / 1272.633 / 322.314 s |
| 科学执行链prepared-start合计 | 2580.144881 s；不能冒称fresh成功N=1 |
| 新局部CSR存储项 / 显式载荷 | 368317250 / 8855010992 B |
| 因子双倍symbolic总估计 / 最大共驻规划 | 67.835674 / 87.453185 GiB，分别<=80/96 |
| numeric全阶段 / 其中numeric子计时 | 353.885 / 207.351 s，不相加 |
| 全监督采样树峰 / 最大实际gap | 37.080410 GiB / 1.333710 s；0.5s仅配置，连续峰unknown |
| 原作用 / 新factor / KSP | 73全域+2局部检查 / 38local+1coarse / 1次32步；全域<=800 |

释放因子后RSS从35.308 GiB降至7.277 GiB，再恢复/审核完整系数；ownswap/OOC=0，MPI1/math1/GPU0。unique-owner数组载荷不当RSS。必要父Z0/E0/core准备实测2928.727s保留；V70 packet与fine-S共享准备8766.781s不可免费，也不能假作packet-only冷费用。成功完整冷N=1未取得，packet-only未配平份额保留unknown。当前命令、历史下界和未计区间见[完整费用](outcomes/records/resource_costs_v77.json)，不重复相加嵌套计时。

唯一worktree=/home/fenics/Projects/NN-Lab，分支task42_neural_coarse_inverse；base=ccd357885f7f9be84efe3be07868cc94f13d93fc，Review=fc02a8612f1aa31b2c52366cc645acee6b5f8daf，正文SHA匹配。科学source=a1c46fb3ef5e22336d10e4d0b3b9ec9ffb2a0311；独立VERIFY source=1a972d11cd5d0b97549549d9e3895edf8e147d05；最终文档HEAD另见交付收据，不冒称运行source。原ABI未变，未操作邻支/工作树或系统。首个只读探针时钟未保留，采用前次交付更早且同boot的时刻作保守V77预算锚，未知间隔未扣除；旧V76仍closed。[身份](outcomes/records/authority_identity_v77.json)

普通缩进、测试activation和元数据类型错误同窗定点修复，均未造成PDE或factor重放；失败保留。最终10项targeted、相关Ruff/compile与4dat验证通过，最终文档一次紧凑检查见tests记录；无full pytest/CI。GitHub视觉NOT_VERIFIED。

**唯一下一建议：关闭本固定阻抗配置；先取得不同传播/粗空间机制的独立证据，再集中立下一完整pilot，保留廉价Jacobi作对照。** 本窗不自动研究新机制、训练、通知邻窗口或开V78。交付后closed/active null、清场/锁释放、只push本分支，暂停等待review。
