# Task042 V6：神经 FE 单次求解 pilot 的材料阻塞与接口实测

终态 **MATERIAL_0P7NM_BLOCKED**。按 [Review V3](../review_report_v3.md) 关闭旧“小局部块＋固定低秩空间／系数网络”路线，V5 port-only augmentation 未实施；旧代码与全部负结果保持。完成 N0 几何／容量局部核查和 N1 材料独立接口，N2／N3未准入。最终0.7nm／48h仍 **NOT_QUALIFIED**。

新方法让小网络先产生三维复向量，再用原有限元的边、面积分规则把它变成可进入原方程的系数。单元内部计划由原局部恢复计算，外部端口幅值另作未知量；希望省去大规模全局分解，代价是新增优化、矩积分和正反向算子成本。本轮只验证前半段表示和导数，缺失材料使原物理方程及收益比较尚无法测量。

| 完成项／证据身份 | measured / derived / not_run 结果 | 证据入口 |
|---|---|---|
| Git / 执行合同 | 原 `0caf151a8274f87363d7dc804d89070f7ba9eb7d` 安全快进到 Review V3 `d5f45787168123a1680523ccf8e73c33de7c7a34`，未回退；只用原执行分支 | [review渲染](records/review_render_check_v6.json) |
| N0 材料 | MATERIAL_0P7NM_BLOCKED；Si n、epsilon、原始来源／版本未取得；原Task039报告也明确输入不足，不猜填或使用旧波长值 | [初始审计](records/material_source_audit_v6.json)、[原源核验](records/historical_material_lookup_v6.json) |
| N0 几何 | 384 hexa、p3；actual FE34050、trace20226、独立trace18144、内部13824、MPC slave2082；8个缺口cell | [材料／几何身份](records/material_geometry_identity_v6.json) |
| N0 通道 | 已知空气侧10个order／20个极化通道，derived；Si侧及总量unknown，不沿用80 | [完整库存边界](records/material_geometry_identity_v6.json) |
| N1 FE矩／约束 | 两套求积的独立DOLFINx插值相对差1.748529652e-15／1.854285005e-15，MPC展开缺陷0；96个非平凡orientation cell、5类变换 | [N1局部检查](records/adjoint_gradient_checks_v6.json) |
| N1 网络／导数 | FP64、3×64 tanh、8载波、11696参数；q15对q30相对差1.169526811e-15；合成非Hermitian导数检查通过 | [梯度与求积](records/adjoint_gradient_checks_v6.json) |
| N1 真实S／恢复 | not_run；材料和完整port库存未冻结，真实S/Sᴴ/native/port/局部物理恢复未构造／审核 | [独立Gate](records/neural_fe_gate_decisions_v6.json) |
| N2 / N3 | 三条求解路线、准确p3参考及p4 enrichment均not_run，无任何目标训练／准确解读取 | [三路线表](records/neural_fe_comparison_v6.csv) |
| N4 | 目标尺寸／通道／资源配额／完整步成本／所需步数unknown，不计算可负担步数，不外推成功 | [48h账](records/target_48h_budget_v6.json) |

## 材料、几何与实际数据身份

现有输入和 `src/common` 没有可核实的0.7nm Si数值；原 Task039 [边界审计](../../task038_extra_full3d_iterative_0p7nm/outcomes/task39_boundary_audit.md) §4.2 明确写明缺delta/beta。其引用的 `f4073adabb91bffe5c3954b8ae8b63270efa3e15` 不在本地Git对象库，初始审计如实记录了这个限制；随后通过只读HTTP完整读取该提交的原始 `feasibility_0p7nm.md`，HTTP200、文件SHA `bea19b69512acacad72d4b22cdadbec8af61ad0d8cfd4ad88d6b0ab203162cd9`，原文同样明确 `0P7NM_MATERIAL_INPUT_INCOMPLETE`。这核实了原报告的阻塞状态，没有补出缺失常数；[原源记录](records/historical_material_lookup_v6.json)保留URL与身份。另对当前可读 common object `64ca6048ca7e1fd7cc66a9b1b1fb2a858a0bd5aa` 的 input／src/common 做只读检索，也无匹配；没有获取其他分支或操作其他worktree。材料采用nm真空波长、原exp(-iωt)约定，但Si复数n、epsilon和有来源的能量字段保持null。

唯一几何按review冻结：x[-0.7,0.7]、y[-0.525,0.525]、z[-0.175,1.225]nm；基底z<0，Si块x[-0.35,0.35]、全y、z[0,1.05]，空气缺口x[0,0.35]、y[-0.175,0.175]、z[0.35,0.70]。实际标签 air200／substrate48／block136，缺口8。仅标签的材料空间分布已具有y/z变化，尚无这些Si标签的光学常数。六面边界facet数48/48/64/64/48/48。解析条件参考p4 FE78936／独立trace33792，未构造。

canonical mesh SHA `7f19322a0e3d610a2ef4080118dd3ac1c535e52ac888085266ea632e8c63e8e3`；canonical geometry/tag SHA `459c2fe77aa175edf70d30d6b9a7bee7dee7759b00a96097cbac089fa1787ced`。设计 SHA `18ea629790245764460eb7aad331b5ce7d042a4e4707de17112507b677742445` 绑定包含未知材料的预登记，**physical operator SHA 为null**；manifest原通用 `physical_model_sha256` 字段在本profile明确标注为unresolved design hash，不能当正式物理身份。

10个已知top order为(-3,-1/0/1)、(-2,-1/0/1)、(-1,-1/0/1)、(0,0)，每阶两极化。只在已知air上应用原传播判据；Si底端口和总库存不调用旧“缺省空气”属性。未知port导致整体候选／参考容量Gate未完成；本轮没有虚构完整0.7nm DtN系统。

## N1：表示和梯度的实测边界

网络输入为归一化坐标，3层64、tanh，48个FP64实输出组成8组三分量复包络，乘±x/±y/±z、入射、镜面反射真空载波后叠加；这些载波不是DtN通道。seed420906、末层零，原散射trace／计划port从零开始。仅非零接口见证复制末层并以seed420907生成固定小扰动，未训练，不改变候选初始化。实际生成的是18144个独立master trace系数；2082个slave由原MPC展开。13824个内部物理未知量尚未恢复，完整物理port尚未生成或优化。

p3每cell 144矩，其中36边矩、72面矩、36内部矩；所有108 trace矩保留，不用节点值或高阶清零。新矩规则从Basix原x/M提取同一多项式积分泛函，独立更高阶求积保留原基；真实DOLFINx参考插值使用相同的完整矩定义，原FE算子degree15没有改动，也没有构造原FE算子。Piola pullback、native inverse-transpose orientation和首incident-cell唯一master owner先作用，周期相位仅由原MPC展开；没有给每个DoF加embedding。矩packet包含用于插值见证的内部采样／临时矩，但内部系数不进入网络未知量或保留结果。

两套packet合计payload11082816B，q15／q30独立hash见身份记录。q15与q30原基相对差5.995575212e-16／8.442945943e-16，实际非零复多项式插值相对差约1.8e-15；slave输入零、回代缺陷0。网络全trace的NumPy独立前向与Torch配对差3.332059934e-16，非零系数范数0.828817168；q15对q30差9.693238990e-16，相对1.169526811e-15，满足1e-8，q60未运行。

预登记的目标loss与导数仍是：

```math
L(w)=\frac{\lVert b-Sz(w)\rVert_2^2}{2\lVert b\rVert_2^2},\qquad
g_z=-S^H(b-Sz)/\lVert b\rVert_2^2.
```

本轮实际梯度见证是**195×195合成非Hermitian矩阵**，192个两cell trace系数＋3个非零复测试port；它没有代表真实0.7nm S或通道。非Hermitian相对缺陷0.817847008，dot adjoint差1.232247961e-15；hidden／末层／port三非零实参数方向，h=1e-4/1e-5/1e-6的9个中心差分相对误差最大9.761170441e-9。chunk和两cell一体autograd梯度相对差6.804866968e-16，单步参数更新比较差1.751595803e-18；实际optimizer update为0。合成loss0.500470136653与残差norm19.66823858仅是接口见证数，不记为原Schur/native/port残差。分块每cell重建图，完整梯度累积后才计划更新；未建立全mesh autograd图。

真实S正向、Sᴴ乘法及其与独立原FE作用配对、完整native残差、物理port、内部恢复均not_run。现有实现只提供矩／复数VJP接线，尚没有已资格化的单层物理S/Sᴴ训练接口。没有把合成算子或插值身份检查升级为完整N1通过。[独立精简checker](records/independent_evidence_checks_v6.json) 从analytic/FD原字段重算9个相对误差及canonical tags/hash；未额外重放FE／网络。部分向量缺陷只保存运行测量，没有独立raw差向量，资格边界保持局部接口。

## 三路线、原方程和物理验算

| 路线 | optimizer／closure／原S/Sᴴ次数 | 完整原Schur/native/port | E/H、全通道、R/T/A/A_volume及功率 | 状态／原因 |
|---|---|---|---|---|
| NEURAL-TRACE | 0/0/0/0，未启动 | not_run | not_run | 材料、真实S与完整N1 Gate不足 |
| FREE-FE-OPT | 0/0/0/0，未启动 | not_run | not_run | 同一物理身份不足，不用假材料对照 |
| FE-LSQR | 0/0/0/0，未启动 | not_run | not_run | 无真实S/Sᴴ，不能形成合法baseline |

未创建teacher/dataset、未读取任何目标参考或旧准确解；两checkpoint是未训练零初始化和确定性接口扰动。没有目标方程loss历史、持续训练、LSQR、准确p3参考、p4 enrichment、非零物理散射或同离散场／功率结果。神经增量 **UNKNOWN_NOT_EVALUATED**，不能由参数少或正确梯度推断。旧15个非零粗逆RHS全失败、V3–V5负结果逐字保留，旧seed420620封存；F5／p6和目标级模型均未运行。

## 资源、源码与全过程成本

第一实现source `64c128c3541887e22788343692cc4f7832a45696` 的FE接口在3.329931s配对失败：原配置x/y为[0,L]，新网格居中，载体未适配。一次明确最小修复以research subclass覆写四个坐标边界，原config/Floquet不改；新的唯一run artifact＋hash pointer保留失败输出。修复source **`2a2cb4af78ba869a26a1254b4b4b76c9ac158366`**。两次成功接口均绑定此clean source；文档HEAD不是运行源码。失败费用计入本轮，预算未重置。

| one-run阶段／shared-workstation | CPU（现场选） | 整树wall s | 同时RSS采样峰 B | own swap B | 子树清场 |
|---|---|---|---|---|---|
| FE接口首次失败／C1 | 0 | 3.329930612 | 184963072 | 0 | 已清场 |
| FE矩／MPC成功／C2 | 0 | 11.031095668 | 314408960 | 0 | 已清场 |
| ML矩／VJP成功／C2 | 12 | 11.775670884 | 304984064 | 0 | 已清场 |

正式监督wall共26.136697164s，顺序运行同时峰取最大314408960B（0.292816GiB）。辅助ABI／测试／静态／渲染／聚合见[初始辅助账](records/auxiliary_costs_v6.json)和[后续完整汇总](records/post_checks_v6.json)，含所有失败，不删除成本；全部监督检查的最大同时树RSS为386977792B。交互编辑、Git／网络工具的整段会话未连续计量，不能称精确全会话峰；各自有监督树的完整成本已列。

| worker内分项（s；嵌套于上述wall，不重复相加） | measured |
|---|---|
| FE mesh/space；Floquet | 0.017014069；0.713308874 |
| q15矩构造／插值审核／I/O合计；q30合计 | 1.473338956；6.187553300，未另拆审核／I/O |
| 网络初始化；完整trace q15前向／矩 | 0.005486429；1.079316755 |
| q30求积见证；合成梯度测试；独立NumPy packet | 5.591783780；0.107262606；0.781087872 |
| 目标S、Sᴴ、训练、线搜索、teacher、参考／恢复 | not_run，无对应计时，不把partial forward称完整步 |

继续用户对Task042的受控共享授权，覆盖原task §2.3 heavy／全机锁，不改邻合同，不宣称F0取得正式review。现场拓扑及邻worker/监督器/加载线程活动检查后FE选CPU0、ML重选CPU12，避开忙碌物理核／SMT；MPI1、实际FE三OpenBLAS池1、ML OpenBLAS1、Torch intra/inter-op1、DataLoader0。自身nice10／idle I/O、独立FE/ML解释器、src及所有cache/JIT/TMP/bytecode/output；原native prefix只读，无包／ABI重装，ML实际无MPI/PETSc载入。两GPU均持续100%利用率，本任务GPU／VRAM分配为0。

整树16GiB hard／12GiB warn、own swap0、自有nonblocking锁、0.5s采样监督所有后代；无cgroup写委派，**不是内核连续限额**。构造前接口对象预测2.5GiB，实际远低于上限；包含两packet、方向矩阵、小多项式拟合临时、mesh/MPC/场、库及编译余量。物理port、局部物理LU、真实S工作区、optimizer/历史未构造，整个求解器容量仍unknown。未构造全局目标或p4因子、Riesz逆、ILU、private audit CSR或fallback。

三次基线MemAvailable约946.7–948.0GB，磁盘约3.45TB；系统reserve216310038528B＋邻增长137438953472B＋自身16GiB保留。只读观察19–21个邻进程及其关联监督器/加载线程，健康记录没有持续压力或触线，memory PSI some avg10最大0；缺可比邻阶段耗时，影响与性能比较 **INCONCLUSIVE**，不承诺零干扰／无争用加速。没有修改、暂停、终止、改绑核或调整邻任务及其watchdog、锁、环境、优先级。全部原始baseline／supervision与input/hash见[run index](records/run_index_v6.json)。

## 测试、停止与唯一下一步

最终相关23 pytest通过，另两项CPU-only ML断言通过，新增代码Ruff/format、compileall、两dat验证通过。预检查的配置字段/complex类型错误及ML缺pytest均保留；先局部修复／标准库运行，不重装环境。正式接口一次居中坐标修复后成功；没有按数值停滞改参数或重复训练。[最终静态检查](records/static_checks_v6.json)核实13个实现文件与成功run source逐字相同，116个原权威／响应／记录逐字保留，summary旧suffix及四总账旧prefix保留；[Git现场身份](records/git_pre_delivery_v6.json)确认无Task042活跃运行、锁已释放及其他worktree登记／HEAD未变。Review V3实际GitHub HTML **4表／4math-renderer**，列一致且无裸math，原review未改；新文档发布渲染证据另归档。无full pytest／MPI2／MPI4／CI声明，无关旧model registry checker缺口不清理。

停止条件是材料来源不足；N0/N1的独立可做部分完成。最终目标几何尺寸、精度、真实通道、实际资源配额、目标完整步耗时与所需步数未冻结。微型单胞仅数个波长，1.0793s的前向不含真实S/Sᴴ、优化、审核／恢复，不能用它算48h能力。**唯一下一最小步骤：补齐并审核Si0.7nm复光学常数的原始来源、版本、单位、符号及数值身份。** 后续真实S／完整N1和三路线需在这个身份下继续受审；本轮不自动实施、不启动目标规模，不回旧p4路线。仅推送原执行分支等待review，不merge。

| Selective merge依赖组 | 实际内容／依赖／证据 | 建议边界 |
|---|---|---|
| production numerical/core | 无新增资格化物理求解；原S/A4/A6/Floquet/default不改 | 不提升默认 |
| research-only numerical | 新参数化micro标签、完整moment packet、固定MLP、复数loss/VJP核 | 23相关测试、两ML断言、两个真实接口记录；尚无目标S资格 |
| reusable runner/watchdog | 原run_case／shared launcher仅两个显式接口opt-in，原监督器复用 | 小输入／原profile回归；一阶段一dat、独立运行artifact |
| checker/compact evidence/docs | FD原字段与canonical tags/hash聚合、材料blocker、响应／总账新段 | 原结果／权威保护，发布渲染核对 |
| do-not-merge | packet／checkpoint／mesh／日志／cache／环境／临时helper | ignored，保留本机，不提交大型数据 |
