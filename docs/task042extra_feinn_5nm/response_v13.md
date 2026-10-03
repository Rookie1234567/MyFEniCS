# Response V13：保存证据与背景转换收口，暂停 FEINN 数值探索

本轮 A/B/C 交付完成，维持 `FEINN_MAIN_SOLVER_ON_HOLD`、`NO_VERIFIED_NN_INCREMENT`。C1 分类已从保存向量重算；八个见证范数直接复用审阅核验。唯一背景转换仅用了2次A4，配对通过，但没有消除旧大基线：p3参考的p4原分母残差由3.55236增至5.20557。没有新训练、网络前向、G作用/逆、新因子、参考重求或初始化对照。同 p3 NN 求解失败、有限已测局部方向的目标分歧成立、网络全局表达极限未知，三者分开。原 native/增广门1e-6、场/复通道1e-4、功率/能量1e-5、逐级功率1e-6均不改变。较好中间态M3600、最终退化Mfinal、全部失败/失联/PSI/重放费用与未验证项保留。

## 身份与实际范围

| 对象 | 完整身份 / 实际状态 |
| --- | --- |
| 精确分支 / 收到的 Review V12 HEAD | `task42extra_feinn_5nm` / `db4611c4092cd8a0ba4c68a391f58964685f945c` |
| 固定 base；Review V11 提交已包含 | `fbac3d8777fcfd897d93b898cb9f460f79ddd6ff`；`bafc9570110bbdcd28de455e9cd4552f3cd80215` |
| canonical / linked worktree | `/home/fenics/Projects/Maxwell3D-Lab/task-repository.git` / `/home/fenics/Projects/NN-Lab-V2` |
| 实际 B 数值 source | `8000ee893a42e2f3cef288fe4652ee1052d511e7`；先 clean 实现提交再启动 |
| 本批正式入口 | `python scripts/launch_task42extra_durable.py input/task042extra_feinn_5nm/v13_background_transfer.dat`；包装选择FE activation后调用run_case |
| 独立 stage/index | `v13_background_transfer`；没有覆盖V1–V12 |
| 同步 / 交付 | 精确refspec fetch/ff；初始显式tracking为0/0；最终完整交付SHA/0/0/clean和清场在本次最终Git回执报告 |

原生Linux、M5/5nm/384hex、p3 31968与p4 75264独立复FE、40端口、Si/air、三维缺口、q15、双Floquet和原材料/模式身份未改变。p4只作既有测试空间；本轮既未生成新参考，也未读取NN模型执行前向。运行source与后续文档提交严格分开，见[run index](outcomes/records/run_index_v13.json)。

## A：分类、范数与状态纠正

检查器现从e/Ge/r/qr、X/GX/Y/WY与实参数α重新计算两类投影的场/残差前后能量、去除比例、符号交叉项、更新能量及闭合，逐项配对记录再按实际比例分类。它只读向量，不是新求解器。54项checker测试先通过；最终73项定向资格包含这些重复项目，不能相加为127项。被独立破坏的两类去除比例、全部交叉字段及非有限原向量均被拒绝，复非Hermitian小例与真实V12正例通过。零能量输出未定义比例和绝对量；不加epsilon/ridge、不裁掉负去除量、不改门限。

| 状态 | 参考投影去除G误差能量 | 残差投影去除残差能量 | 残差投影的G场能量去除比例 | 独立分类 |
| --- | --- | --- | --- | --- |
| M3600 | 0.974072726506 | 0.00161114304683 | -0.194551158932 | LOCAL_OBJECTIVE_DIRECTION_MISMATCH |
| Mfinal | 0.987418366388 | 0.00575734462851 | -0.11552596425 | LOCAL_OBJECTIVE_DIRECTION_MISMATCH |

负场去除比例表示场误差反而增大；这里只检查固定16列实参数方向，不是8966参数的全切空间。八个已经保存的非线性见证和三种范数全部保留在[专题表](outcomes/evidence_closure_v13.md)与[核验复用记录](outcomes/records/witness_norm_reuse_v13.json)。对偶范数偏差最大约5.003%，不能用系数范数的约1.02%代替。未新增这八次前向或任何JVP/VJP。

D0确实执行过完整成本预检，新的映射为 `COST_VETO_CONFIRMED`；D1为 `NOT_RUN_COST_VETO`。旧JSON不追改，见[状态对照](outcomes/records/status_mapping_v13.json)。baseline完整672.462895285s/1.16026306152GiB，20%时间阈值537.970316228s，NN前缀已15758.7400951s/峰值下界2.39972305298GiB，当前初始化不具备净收益。多查询至少30次仅是零单次费用假设下的必要条件，不是已验证业务或代理资格。

## B：同总场的仿射背景检查

总电场由背景与散射相加组成。p3/p4分别插值背景；直接搬移散射系数并不保持同一个总场。本轮只把旧b3完整恢复并用旧合格P34移到p4，减去旧b4，所有三份保存残差共享一次A4d_b。它补准跨阶解释，代价是一次背景恢复/插值、公共E/curl积分和2次原算子作用。

```math
d_b=P_{34}b_3-b_4,\qquad
c_{4,\mathrm{same\ total}}=P_{34}c_3+d_b,\qquad
r_{4,\mathrm{same\ total}}=r_{4,\mathrm{saved}}+A_4d_b.
```

| 保存场 | 原残差绝对范数 | 修正后绝对范数 | 原相对值 | 修正后相对值 | 符号交叉能量 | 能量变化 |
| --- | --- | --- | --- | --- | --- | --- |
| p3reference | 1.29375244734 | 1.89584252061 | 3.55236349556 | 5.20557219228 | -8.12272379429 | 1.92042346797 |
| M3600 | 1.42632981023 | 1.83234955298 | 3.91639216676 | 5.03123428018 | -8.72005910551 | 1.32308815675 |
| Mfinal | 1.47138647844 | 1.78121793112 | 4.04010800106 | 4.89083794134 | -9.03538811307 | 1.00775914919 |

三行沿用同一原f4分母 **0.36419483787438633**，不是G4对偶范数。A4d_b绝对范数3.1690924982173136、自身能量10.043147262257254；尽管交叉项为负，自身项更大，所以三场残差能量均增大。d_b系数范数0.10149461017625（基依赖，不称物理场误差）。另列总场右端范数0.7414638056605587，对应诊断相对值2.55689152476/2.47125960699/2.4022992323，绝不代替原分母或Gate。

公共背景E/curl差1.19e-15/7.58e-15、MPC≤7.95e-17；直接重算参考修正场与保存残差加法差5.44e-14，能量闭合≤2.80e-16。两候选减参考的误差像仍为0.325782556578/0.330392025659，不变性≤1.82e-17。修正后的p4残差不能用于按参考挑更好NN状态，更不能取代同p3评分。该假设未支持“背景转换消除大基线”；仍有明显余量，但无G4/全空间稳定性证明，不能独断为纯测试空间或网络表达问题。见[原字段/向量](outcomes/records/background_conversion_v13.json)、[独立checker](outcomes/records/independent_checker_v13.json)。

## 保留的数值边界与资源

| 保存态（沿用 V12/V11，非新求解） | native 原残差 | 散射 E L2 相对误差 | curl/H 相对误差 | E_G | 原 Riesz loss |
| --- | --- | --- | --- | --- | --- |
| M3600 | 0.885852183253 | 0.0933002764708 | 0.0935415151962 | 0.0935355798945 | 0.094314671576 |
| Mfinal | 0.846541904928 | 0.122944519716 | 0.123039105854 | 0.123036776653 | 0.0872060784095 |

上述误差未更新，M3600的改善和Mfinal的退化同时保留。原全场/六点E/H、四类40级复通道及分母、逐级功率、R/T/A/A_volume/R00和区域证据沿用[保存物理记录](outcomes/records/saved_physics_reuse_v12.json)及V11/V12结果；本轮不重算或提升official。新独立E/curl交叉与邻层积分仍资源未运行，V2/V6缺失optimizer/RNG仍NOT_RETAINED；p/h/端口/连续解边界不改变。

| 本批实测 | 完整时间 / 内存 / 操作 |
| --- | --- |
| 唯一B launcher（含导入、60s PSI、准备、保存、清场） | 77.4764841361s；监督树采样峰304291840B（0.283394GiB），swap0，清场 |
| B操作与配对 | A4=2（累计预留2≤4）；AH/G/Gsolve/new factor/new reference/network forward=0 |
| 定向最终FE+pure资格 | 73通过；监督3.453360579s，完整包装4.783610774s（含监督，不叠加），峰208031744B |
| 冻结后独立原向量checker | 4.038011292s；峰185360384B，swap0，清场 |
| 整批与历史账 | [resource_costs_v13.json](outcomes/records/resource_costs_v13.json)：完整墙钟上界收费含实现/阅读/IO/失败/发布，不仅上述worker；历史158041.7009986502s与已知审阅34.7259556688s均保留 |

CPU现场选择10，物理核及SMT同胞避开邻worker；MPI1/数学及Torch线程1/CPU-only，原warn12/hard16GiB、轻任务2GiB、系统预留和384GiB邻增长、自身swap/OOC0均保留。一次轻测试先因无空闲核未启动；观察到新合格窗口后使用唯一重新准入并通过。没有阈值放宽、其他项目修改或自动轮询。局部文档转义修复1/2（不重跑数值），正式数值重试0。完整成本、未知单项与保留失败见[资源](outcomes/records/resource_costs_v13.json)、[repair](outcomes/records/repair_log_v13.json)；未知单项不写0。

## 收口、文档与后续

Review V12实际GitHub视觉证据直接复用其hash绑定审阅记录；本回执/专题只有限检查新页，结果独立记在[render_check_v13.json](outcomes/records/render_check_v13.json)，不以结构解析代替浏览器。仅本地定向测试、Ruff/compileall及选定新页parser，无full pytest/CI或环境重装。原 task/review、历史JSON和其他分支未改。[六组依赖清单](outcomes/records/selective_merge_manifest_v13.json)无production晋级，数值诊断保持research-only。

交付后暂停FEINN数值探索，不继续hidden/范数/尺度/权重扫描、长训练、初始化对照或传统求解器复制。未来只能由新review明确授权一个无参考标签的具体干预、能区分解释的保存数据预检、同成本非NN对照、原全部精度Gate及完整预算；本轮不执行。task40extra/dot分别按自己的合同负责精度与存储/恢复，FEINN不复制其工作。最终目标仍是原尺寸50×25×140nm、17nm宽/120nm高Si线光栅、λ=0.7nm、非可分三维缺口的完整三维FE，十进制2,000,000,000,000B整机、swap0、172800s完整流程；仍NOT_RUN/NOT_QUALIFIED。

只推送 `git push origin HEAD:refs/heads/task42extra_feinn_5nm`，随后等待review；无master merge approval，不合并或强推。
