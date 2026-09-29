# V8：变量列尺度与等价计算成本，分别验收

本轮做了两种不同的改变：列尺度重新标定每个未知量的单位，尝试使迭代更容易处理不同大小的系数；batch8把同一个网络的八个单元一起计算，减少常量转换和逐单元调用成本。前者可能影响收敛，后者只改变执行方式。另修复异常停机时的参数保存边界；三项不能互相替代。

| 项目／身份 | 本轮实际结论 | 证据 |
|---|---|---|
| C0复用 | 原action／q15 moment／三冻结state／标量历史hash通过；准确参考只先核对身份，不解码解 | [run index](records/run_index_v8.json) |
| C1停机 | 实际strong-Wolfe首个／后续试探及初始／非有限异常可复现旧缺陷；7测试恢复参数和optimizer，不退回消耗计数 | [事务测试](records/optimizer_stop_semantics_v8.json) |
| C2唯一尺度 | SCALING_SETUP_USES_SMALL_ASSEMBLED_S，矩阵/action配对通过；严格失败，预登记十倍＋散射误差研究信号也失败 | [列尺度](records/column_scaling_v8.json)、[物理对照](records/scaled_lsqr_comparison_v8.csv) |
| C3等价 | 零网络参数＋非零port、预登记非零见证、V7冻结参数均通过；最大梯度相对差5.338e-13，FD最大1.794e-9 | [等价记录](records/batch_equivalence_v8.json)、[独立重算](records/independent_calibration_gates_v8.json) |
| C3成本 | 三对完整步中位降幅的中位值48.55%；仅shared-workstation micro工程正信号 | [全部36评估](records/batch_costs_v8.csv) |
| 最终目标 | 微型问题仍NOT_QUALIFIED；神经数值增量NOT_DEMONSTRATED，目标0.7nm／48h未知 | [独立决定](records/gate_decisions_v8.json) |

## 固定数据与原方程

固定对象为原384 hex／p3／h0.175 nm三维缺口，wavelength0.7 nm、grazing1°／azimuth0／s、双Floquet／layered DtN。FE34050、独立trace18144、内部13824、slave2082、reduced18184，完整top20＋bottom20=40复port。材料仍为唯一canonical表`input/materials/si_optical_constants_v1.json`，ID `SI_OPTICAL_CONSTANTS_USER_20260929_V1`、SHA `55aa34e55c5e3cc35f6849eddbd3bcc72d3b694d32bc4885299ef373acd676a2`；Si n=0.999885140474+4.32477054e-6i、epsilon=n*n，精确0.699999988→nominal0.7 alias不变。physical SHA `2b532f91550316b16a304f3be9ae78605816b5a2aba556f548b5bd794f82e6de`，mode SHA `93795b53d7c5aef69af66b4ff0a56fa46515771f1ec43332ec929970270ea262`。原材料、入射、RHS、master/MPC、方程及验算均未改。

原S/action packet SHA `9196edb807b534217d0c0eb78882125341342784a48ef20ebe2d9421fe636454`、载荷209239672B；原完整q15 moment SHA `72ec5a28dd073b4217fdb36d4bbfe2383c6cda7b232d239da0ae4392292abd42`。真实N1与材料独立映射按原source＋数组复用；不重建F0，不再读旧384对teacher或seed420620池。参考NPZ SHA `a0610a5a55e7508196b17277e706595c33e4398ace82b245f70b656e6b9ed355` 只在C2最终state/hash冻结、进程退出之后解码验证，没有新symbolic/numeric/solve。

trace是跨单元公共边／面的独立有限元系数；内部未知量在单元内恢复；port是边界衍射通道的复振幅。Schur残差核对消去内部未知后的方程，native残差核对完整原有限元方程，均以原固定RHS作分母。场L2相对差则直接衡量所得场与同离散参考的偏离。

## C1：停止恢复到哪一个状态

已安装PyTorch2.7.1+cpu的LBFGS源码SHA `5be8478f3dbd6b1973c3fdb9f4c2230ea99265cd7e3ffec7aad1996159e13a50`，未修改。Task adapter在每个Adam或L-BFGS外层调用前同时保存参数、梯度和optimizer；只有正常返回才提交。异常恢复已声明的 `LAST_COMPLETED_OUTER_STEP`，不称最近内部Wolfe接受点。单独保存committed与last_trial；committed一致的optimizer checkpoint经磁盘重载测试，trial为参数快照、不可直接续跑。

所有试探closure、S/Sᴴ、时间保留消耗；closure调用id与完成计算数分列。V7不能反推接受状态，新增说明 `V7_ACCEPTANCE_STATE_UNKNOWN`；原向量已经独立审核，其负结果及原数值仍有效。没有为此重跑两小时NN/FREE。小测试还覆盖旧语义确实留下试探参数、新语义恢复、正常完成和Adam异常。

## C2：一次列尺度对照

```math
c_j=\lVert S e_j\rVert_2,\quad D_{jj}=c_j^{-1},\quad z=Dy,\quad \widetilde S=SD,\quad \widetilde S^H v=D^H S^H v.
```

先以原装配函数合并重复贡献、Floquet复相位和完整端口，再求每列范数。小CSR18184行／3901384 NNZ仅存在setup，未保存、分解或求解，setup退出后释放。8预定列、3固定复向量配对最大4.479e-16。所有列均正且可表示；c范围1.475620298–1125.406275、动态比762.6666，trace范围33.19426–1125.40627，port范围1.47562–17.27358。D范围0.000888568–0.677681109，hash `176c40775d6e7538e511f758bea953e48fd95886196d5a0b31b8629784e5ea02`。setup成本组装0.941337s、列范数0.379580s、配对1.111717s、输出0.003841s，整树wall6.818829s/RSS641200128B；从零成本不能忽略它。

候选从y=0开始；原LSQR递推不改，无row scaling、clipping、damping、SᴴS、ILU/Riesz或准确解幅值。真实复dot/recovery/loss Gate通过。最终1915步，S1999/Sᴴ1919（含Gate、初始、审核及最终），旧V7为1921步/S1999/Sᴴ1922；在相同或更少作用内比较，不挑checkpoint。仅动作工作量可比，长路线时间在共享环境不据此宣称加速。

| measured原物理坐标；分母沿原RHS | V7原LSQR | V8列尺度LSQR | 标准／解释 |
|---|---:|---:|---|
| Schur相对残差 | 0.071602579856 | 0.068283273738 | 严格1e-6；研究需≤0.0071602580 |
| native散射相对残差 | 0.028727751543 | 0.026675035784 | 严格1e-6；研究需≤0.0028727752 |
| port绝对残差 | 0.000176176371 | 0.000121462209 | 不是只比较可变operation分母 |
| port固定RHS相对残差 | 0.000826358089 | 0.000569720434 | 严格1e-6 |
| port operation-relative | 0.656567940780 | 0.049261505581 | 严格1e-6；分母随作用幅度变化 |
| recovery相对缺陷 | 1.726e-15 | 2.860e-15 | 限1e-10；slave最大仍0 |
| 全场L2相对差 | 0.1046399326 | 0.1044981633 | 限1e-4，背景不能掩盖散射误差 |
| 散射场L2相对差 | 0.9999532575 | 0.9985984907 | 严格1e-4；研究需≤0.5 |
| 全场scaled-curl相对差 | 0.1046402486 | 0.1044977156 | 限1e-4；旧精确值见CSV |

最终仍约100%散射误差，只有小幅残差改善，不能宣布恢复真实散射。独立total native=0.0092562210，selected E/H差=0.1045072671/0.1045072941；全部超原标准。能量及全40复port／逐channel也重算：[原始盲验证](records/scaled_blind_validation_v8.json)。候选R/T/A_balance/A_volume=0.113599941512/0.885520488781/0.000879569707/0.005314482517，均仅diagnostic；参考仍0.117645819323/0.877047782934/0.005306397743/0.005306397746，未输出official候选结果或连续收敛声明。

**所有权限制如实披露：**初次C2 adapter额外读取了3369888B原moment包，LSQR核心未用它，实际RSS/时间已包含；raw中“packet+D only”的简写不足以证明最小所有权。结束后在 `9915f6168ec4035470870a5d8c3c3bbfe0e6277a` 最小修复为仅C0/C3读取，2输入边界回归通过，未重跑负结果，也不冒充修复后的完整部署实测。原候选没有CSR、参考、global p4/p3因子、私有audit CSR或hidden fallback；setup明确是有小规模装配的例外，不能声称全流程无矩阵。目标规模D计算未验证。

## C3：相同未知量、更便宜的一步

仍是11696个FP64参数、3×64 tanh、8固定载波；网络经全边／面矩、Piola、方向变换及唯一owner进入原18144 trace，内部13824用原局部恢复，40复port完整保留。本轮只评估固定参数，不训练或读取目标准确解。V6见证参数未持久化，如实使用预登记seed420908、0.005小扰动；零网络参数采用相同预登记非零port见证，V7参数仅作等价输入，接受状态unknown不影响函数比较。

所有384 owner-cell、每cell507采样点和144局部矩均保留，不删高阶矩、不降低q15。新增持久缓存35107584B（33.48MiB），全是固定几何／相位／映射；单batch图与临时对象保守上界107078400B、总新增分配规划246463744B，构造前以自有树RSS加此界检查12GiB，实际树峰816152576B。原MPC/参数顺序/完整原loss和复梯度不变；3个非零实方向的9项FD稳定区通过，克隆Adam只作一次等价测试，不继续训练。

| pair／顺序 | batch1完整步中位s | batch8完整步中位s | 降幅 |
|---|---:|---:|---:|
| 1／1→8 | 4.756740 | 2.285877 | 51.94% |
| 2／8→1 | 4.891869 | 2.516729 | 48.55% |
| 3／1→8 | 4.594245 | 2.451498 | 46.64% |

每进程1 warm-up＋5测量，共36次完整前向／矩映射／S／Sᴴ／VJP，S/Sᴴ各36，无参数更新；cold缓存setup和launcher成本另列，不只计小MLP。paired降幅中位48.55%超过20%阈值。三对均CPU0／同source／同参数hash／同作用次数；共享负载无法证明绝对零争用，只称observed shared-workstation micro工程正信号，不是神经数值增量或无争用求解加速。

## 全过程费用、身份与未运行项

11个one-run正式阶段，supervised整树wall=791.658916180s；含准入launcher wall=809.987740805s。两者与worker、exclusive、嵌套closure不是可相加的多项。peak同时采样树RSS816152576B、own swap0、Task042 GPU未使用；完整有界辅助、失败和后续检查继续加到V7 carry8751.379832064034s，4h新增／10h累计两预算均未重置，最终逐秒结算仅见[费用账](records/resource_costs_v8.json)。编辑/Git/整个交互会话未连续测RSS或wall，不能把数值阶段峰冒充所有时刻。

运行使用自有锁、实时核、MPI1、数学/Torch1、DataLoader0、nice10/idle IO、独立FE/ML/缓存。原资源规则hard16GiB/warn12GiB/own swap0、系统max128GiB或10%＋邻增长128GiB＋task16GiB、disk≥50GiB/artifacts≤20GiB保持。没有cgroup委派，0.5s树监督是真实机制，不宣称内核连续限制。低开销health无持续PSI触线；邻任务可读阶段保持运行，缺可比吞吐，影响INCONCLUSIVE，无任何邻任务改绑核/优先级/信号/锁/环境操作。

| 实际source（完整SHA） | 运行范围 |
|---|---|
| 1a2984a44ca48573bbe18ffe8a7f8c5d6bdacc05 | C0、列尺度setup、scaled-LSQR、独立物理审核 |
| 52d47d35656c5a763bed07e07f827fb6fb285bb7 | 真实batch等价＋六个micro |
| 9915f6168ec4035470870a5d8c3c3bbfe0e6277a | 结束后的输入所有权接线修复，只有针对性回归，无新数值运行 |

CLI附加`--mode fe`参数错误、C4 CSV字段重名TypeError及临时checker的同名README片段路径误报均保留；前者随后正确ABI检查，后者仅修聚合，不重放FE。未单独计时的CLI错误另扣1.001622s保守上界，另为短Ruff／输入／记录／文档命令扣120s预算保留；这些不是实测wall，RSS未知，不伪造实测。正式FE源均clean且一dat一stage，后续文档HEAD不代替source。最终16相关pure pytest＋2 raw checker反例、7optimizer测试、batch tiny矩/VJP与预算回归均通过；full pytest/MPI2/4/CI不声称通过。Review V5实际GitHub4表／2公式通过；新文档的publication检查另见记录。

not_run：新长训练／V7续训、监督准确解拟合、p4 enrichment、GPU、短波／更大网格、p6/F5、旧teacher／seed420620、official候选R/T/A。旧p4路线仍CLOSED_RESEARCH_NEGATIVE。最终目标几何/DoF/完整步成本/所需训练步/完整DtN存储和离散误差均unknown；micro不能外推48h。

唯一下一最小建议（**未实施，等待review**）：固定pilot上仅对已经冻结的误差方向做原S/恢复/端口分量审核，复用已有p3参考作离线核对，定位残差下降为何没有恢复散射；不训练、不建新PC、不扫描。 这只核对固定误差方向与原方程、场的关系，不回旧p4路线或创建新网络。
