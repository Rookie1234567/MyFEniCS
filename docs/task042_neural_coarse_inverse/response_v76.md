# Response V76：Review V74执行结果

Jacobi确实降低了原残差：32步为0.388826586390，合法续算至64步为0.341713600189；但未达64步的0.1效果门，也远未达原方程1e-6门。SMR64步原残差0.360076582954，反而稍差，prepared-start费用2401.451秒，新增39个因子。本组固定低维粗修正加当前主子块RAS的组合微调关闭，不补尾部、不继续提高restart或扩大粗空间；没有合格物理解。

残差1代表原方程尚有与原RHS同量级的不平衡；本轮用它判断实际改善。复对角Jacobi仅按每个未知量对自身的真实复数作用作缩放，不加shift或阻尼。SMR把原输入、旧粗修正、局部修正各作为独立方向，用原算子作用求三个复权重，避免把坏局部方向固定加上；它是非线性右PC，增加原作用与三角解费用，不是神经训练或新粗空间。

| 同25576tet/p5/828、0.7nm NOTCH（measured） | 累计步数 | 未凝聚原true | scaled retained true | 必要prepared-start wrapper/s | 新numeric |
|---|---:|---:|---:|---:|---:|
| B0 | 32 | 1.93460766967 | 0.376872295207 | 520.729 | 0 |
| BJ | 32 | 0.38882658639 | 0.379105019552 | 526.966 | 0 |
| PROMOTED | 64 | 0.341713600189 | 0.33941522177 | 546.174 | 0 |
| SMR | 64 | 0.360076582954 | 0.147596138687 | 2401.451 | 39 |

PROMOTED为Jacobi本批32步状态的合法续算，新KSP未保留旧Arnoldi基；Jacobi路线总费用为1073.140750秒、累计64步，表中两段没有免费复用因子。B0与BJ的32步对照均未建立局部/粗numeric；父packet中原内部LU仍存在，不能称factor-free。廉价预检加两32步全过程1326.535687秒，低于1800秒预算。

## 原方程及严格出口

B0接口残差降到0.37687，完整原残差却升至1.93461，32步rho未过0.5而停止。Jacobi32步rho=0.38883通过，64步rho=0.34171未过0.1。SMR32步rho=0.42960通过，64步rho=0.36008未过0.1；没有128/256步尾部。rho始终取原true与接口true的较大值，原RHS分母、材料、κ、双周期及全部828模式未变。

四个合法返回都保存完整retained/RHS/左右尺度、全部1943745个独立FE系数与828port、native/MPC/κ/几何及独立原式向量。唯一新进程VERIFY重算q15 PUBLIC_BASIX body和全部q63边界，四态producer-consumer原式差均为0，39因子实际残差/容量及两个SMR方向见证也通过。所有formal方程及strict场资格仍FAIL；direct1e-10目标单列FAIL，恢复与Schur-original恒等式均≤1e-10。

四态原残差均>1e-2，因此六场积分、240点、衍射评分、RTA及体吸收为NOT_RUN_BY_FAIL_FAST_POLICY，official=False。完整系数可只读补消费，未把未运行写为通过。没有读取V70正确场初始化、选权或评分。[原式与独立checker](outcomes/records/scientific_checks_v76.json) · [全部曲线/效果门](outcomes/records/residual_history_v76.json) · [完整系数身份](outcomes/records/source_array_bindings_v76.json)

## 作用与PC证据

真实热作用配对差5.21846573096e-16；对角含完整MPC复对偶和重复id累加，两个实际单位向量分量差0，零对角数量0。旧Z0 SHA保持536758160a20d38c5fc87781a192fd853d6f387164774181c12595d0daa3880e，旧E0为7068行、38块未重建，harmonic新基未使用。

SMR首输入的实际残差比0.419787242309，旧固定和约60.713044；最优单粗方向约0.437599。首步KSP接口true=0.419787242315、原true=0.424322752474，实际桥接吻合。两个资格W为满3秩；直接SVD、rcond1e-12只识别三列相关性，不删PDE未知量。每次真实A返回复查最大运算尺度差8.0388726803e-13；额外LS工作区规划上界489753888B≤512MiB，不形成正规方程。后续较小的接口残差不能替代原式：SMR64步接口0.14760仍对应原true0.36008。[对角、39因子与非线性保护](outcomes/records/operator_PC_checks_v76.json)

## 实际资源、费用和身份

唯一worktree=/home/fenics/Projects/NN-Lab，分支task42_neural_coarse_inverse；base=ccd357885f7f9be84efe3be07868cc94f13d93fc，Review commit=3f40d40f55c798f55d07c413a6492241db59a6ad、正文SHA与指定相同。预检source32e298ad0c69a65149269f882b191b99d2e0428f；三个廉价计算source f68af698a7fe42a0b3c79860ae934f690d056016；SMR/VERIFY实际source fb403eeba4734bb931d4f72a8eae865286a2ecec。文档HEAD另见最终Git交付收据，不冒充运行source。

全批4次KSP、实际160个新Arnoldi步；原作用计数最终见费用记录，均≤1800，KSP有载合计≤10800秒。生产global fine K/S读取/形成/因子均0，新分区/Z/Galerkin/harmonic构建0。SMR每因子按live RSS+全部未分解双倍symbolic+future≥12GiB准入；因子双倍symbolic合计74.805691838GiB≤80GiB，最大共驻规划94.390645146GiB≤96GiB。

当前全监督集合sampled树峰41.453971863GiB、最大实际gap1.36729622912s；0.5s为配置，连续峰unknown，ownswap/OOC=0。MPI1/math/CPU1/GPU0、ABI和宿主/邻增长/PSI/SMT保护保持。已知不重叠wrapper及增量归档费用5249.666626878s；有效完整解冷N1、生产速度/峰值比例均无资格。父V70/V71必要准备不免费；历史已知下界390402.368519秒与本批研究总账分列，unknown不填0。[完整费用/采样](outcomes/records/resource_costs_v76.json)

11项最终源码定点测试、相关compile/Ruff及六dat校验通过；唯一文档检查与最终closed/清场/Git状态见交付记录。归档helper相对路径错误已同窗修复，旧partial和失败费用保留，无科学重放。GitHub视觉NOT_VERIFIED；未修改邻任务、系统或其他worktree，未训练NN、未授连续精度/原尺寸/2TB48h/NN20资格。

唯一下一建议：停止这组组合微调；若另立完整合同，只研究与已失败主子块Dirichlet/RAS不同的物理阻抗局部传输及有分辨依据的波动空间，先证明它对同RHS能产生优于廉价Jacobi的有效全局方向及可核算成本。本轮不实施、不自动开V77、不通知邻窗口、不merge。

[紧凑专题](outcomes/baseline_residual_minimization_v76.md) · [决策与修复](outcomes/records/decisions_repairs_v76.json) · [接口契约](outcomes/records/retained_iterative_contract_v76.json)。科学冻结与费用快照实际UTC：2026-10-12T05:01:13.509996+00:00；最终交付时刻由最终Git收据记录。
