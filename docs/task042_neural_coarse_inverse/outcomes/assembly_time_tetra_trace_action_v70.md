# V70：装配时形成四面体接口系统与独立局部作用

本轮保持0.7nm真实三维NOTCH、冻结25576个四面体/p5、原κ、完整Cκ和828模式。几何仍为s=7/135有限参照，x/y周期为50×(7/135)与25×(7/135)nm，不是50×25nm原尺寸目标。新的流程直接从每个单元的原体核解出30个内部未知量，把110个边/面未知量的完整贡献累加到接口系统，再恢复所有内部场。这样避免先形成或读取完整全局K；它改变计算组织，保留同一物理方程和全部场方向，仍付出局部LU、接口S和全局稀疏LU的成本。

正式Review V68 commit `7eb964ce194748d5c3510a4dc1798e312282aa57`，blob `997db3c9238437ec632bc66ebdb711843e279165`，SHA256 `34583e6b20d79b3d5a007d7e3c7f282dae552477960b6f9d0783c56f1713af6a`；base `ccd357885f7f9be84efe3be07868cc94f13d93fc`。实际Q/BUILD/ACTION/SOLVE/VERIFY数值source为 `0490af3085f32940787f0a02f0d801578ab87b73`，库存消费修复source为 `d6cd48cf449a0e613146c0f4aff01caac48f68c8`，只改变有界文件读取；最终文档HEAD另列。[完整身份与source](records/authority_identity_v70.json)。

| 实际对象 | 规模/性质 | 资格边界 |
|---|---|---|
| 完整原FE场 | 1943745 FE＋828端口；native FE1979985 | 全部767280单元内部系数恢复，不删方向 |
| 接口系统 | retained FE1176465＋828＝1177293行 | 原完整空间的精确消元，不是低阶/低秩解 |
| 新局部包 | 实际10660个精确核类、25576个单元映射 | 真坐标、材料及方向身份；不round合类 |
| 独立ACTION | 两个固定complex128接口向量 | 只用新局部包/边界，无全局K/S、无factor |

生产full_body_assemble_matrix、old_full_K_reads、full_A_materializations、old_condensed_packet_reads均为0。原DG0 epsilon按实际积分索引和cell行打包，完整trial/test相位项先形成raw再消元；Kti不由Kit猜造，Ci/Di/fi/g全部保留，MPC共轭拉回和端口scale各一次。旧C5的S只由独立compare-only进程读取，用于两次作用比较；旧C5场直到候选冻结后才读取，不参与初值、RHS、类缓存或停止。

| 新资格见证 | measured最大误差 | 门限/结果 |
|---|---:|---|
| 8个预登记真实cell：新核/独立Basix | 3.39145789537e-15 | 1e-10 / PASS |
| 这8个cell精确平移体核 | 0 | 1e-10 / PASS；不缓存相位RHS/边界 |
| 非零内部/端口RHS完整恢复＋独立原式 | 1.46568401648e-14 | 1e-10 / PASS |
| compare-only：新S/旧C5 S作用 | 2.1090500946e-16 | 1e-10 / PASS |
| ACTION：局部作用/保存S作用 | 1.64775892845e-15 | 1e-10 / PASS |

独立原式采用PUBLIC_BASIX q15体积分和新q63完整边界，不读生产raw或S来自证。全长和FE/port分块尺度分列；数学Gate通过后完成唯一计划物理零初值求解，没有追加旧控制PDE。[单元/恢复/无K证据](records/assembly_time_checkpoint_v70.json) · [独立ACTION与compare-only](records/trace_action_qualification_v70.json)。

| 完整物理结果 | V70新解 | 原门 |
|---|---:|---|
| production retained true | 3.82968086492e-12 | 1e-6 |
| 独立true | 3.35623167109e-10 | 1e-6 |
| 独立native | 3.35623167109e-10 | 1e-6 |
| 独立augmented | 3.35623171036e-10 | 1e-6 |
| 独立port | 5.87622187275e-16 | 1e-6 |
| 独立direct严格目标 | FAIL | 1e-10，单列 |
| 内部恢复操作尺度 | 5.80061896558e-16 | 1e-10 |
| R | 0.0762185592265 | 完整828模式功率求和 |
| T | 0.90566516113 | 完整828模式功率求和 |
| A=1−R−T | 0.0181162796431 | 单列收支值 |
| A_volume | 0.0181162796389 | 独立总场材料体积分 |
| energy | -4.219735672e-12 | 1e-5 |
| R00_s | 0.0762181437711 | 零级s |
| R00_p | 2.54710536068e-16 | 零级p |
| R00_total | 0.0762181437711 | 两极化之和 |

六场为total/scattered复E、H及完整相位curl；保存完整系数、六场积分和原240点复矢量，保留每个模式的物理键/侧/偏振/参考面/归一化、复振幅与功率。体吸收独立积分，不用1−R−T替代，不拟合幅相或重新归一化。actor原式和冻结后新进程checker分列：[完整物理](records/complete_physics_v70.json)、[独立科学checker](records/scientific_checks_v70.json)、[全模式复算](records/modal_recalculation_v70.json)。

| 新解/C5严格同离散比较 | measured | 原门 |
|---|---:|---|
| E_total | 1.06436990006e-12 | 1e-6 |
| H_total | 1.06369927018e-12 | 1e-6 |
| curl_total | 1.06369927018e-12 | 1e-6 |
| E_scattered | 7.40937013119e-12 | 1e-6 |
| H_scattered | 7.4048021928e-12 | 1e-6 |
| curl_scattered | 7.4048021928e-12 | 1e-6 |
| 原240点最大六矢量相对差 | 7.64504628296e-12 | 1e-6 |
| 参考面完整复通道差 | 1.38679728795e-12 | 1e-6 |
| 新增296物理通道分区差 | 3.23394808852e-08 | 单列诊断，1e-6以内 |
| 原点外推辅助幅度相对差 | 1.14371513594 | 诊断，不作物理参考面Gate |
| 逐mode功率最大绝对差 | 9.78522818329e-14 | 1e-9 |
| R/T/A/A_volume最大差 | 9.77828928939e-14 | 1e-8 |
| 严格再现总裁决 | PASS | 与连续精度分开 |

原点外推辅助幅度的最大绝对差为1.94615632296e+101；强倏逝坐标尺度与物理参考面幅度分列，不宣称原点辅助坐标逐系数再现。物理面使用原传播因子和规范，没有重新校准幅相；严格验收仍按合同的物理参考面量。

仅在原基/几何/DOF逐位一致后先相减系数，再在原共同物理域求差场；不是投影一方。q31独立差场见证与原2e-6操作门保持，原分母/floor不改。原倏逝辅助坐标差和物理参考面振幅分别保存。旧P6/L5散射E/H约1.14449e-4/1.23013e-4、240点约9.56042e-4，仍FAIL原1e-4门；同离散工程再现不授连续准确性。[完整分子、分母、原复量及checker](records/paired_results_v70.json)。

| 实际存储与容量 | measured或明确口径 |
|---|---:|
| 真实图预分配上界 | 318344949 |
| S stored entries | 266599917 |
| S exact nonzero / explicit zero | 266599916 / 1 |
| 新S显式载荷B | 6436072032 |
| 新局部packet载荷B | 4172648576 |
| 实际局部LU/精确类数 | 10660 |
| BUILD局部cache峰B | 3497759200；限4GiB |
| symbolic估计decimal MB | 104461 |
| numeric实时RSS＋2倍symbolic＋2GiB规划GiB | 220.388491273；限256 |
| INFOG9原编码 / 实际fill项 | -5093 / unknown |
| BUILD sampled整树峰GiB | 18.4390258789 |
| ACTION sampled整树峰GiB | 4.23936462402 |
| SOLVE sampled整树峰GiB | 111.277801514 |

最终S仍为266599917项，与C5相同，不靠drop减少图。精确类共享不等于跨case因子共享；opaque global LU未保存。新retained向量先持久保存，factor、PETSc矩阵、S/scaled及mmap拥有者释放后，同一worker的RSS从107.282337189降到2.94794082642GiB，再完整恢复和输出。[真实图/因子/拥有者](records/capacity_and_lifetimes_v70.json) · [含NPY的完整封存库存](records/sealed_array_manifest_inventory_v70.json)。

| 实际费用 | 秒 | 范围 |
|---|---:|---|
| 成功BUILD＋SOLVE必要分段 | 22313.3740884 | 构建/原式/求解/恢复/六场/端口/吸收/provenance/IO/清场 |
| SOLVE prepared-start完整链 | 12666.5476045 | 新S/packet只读重载；不是fresh构建 |
| 本次numeric factor实测 | 8857.6219858 | 包含于SOLVE；不再额外相加 |
| 第一BUILD启动至SOLVE结束实际elapsed | 22797.054979 | 含中间compare/ACTION/等待，不再与分段重复相加 |
| ACTION初始packet/边界冷读 | 5.92251753714 | 尚未读取全部局部类 |
| ACTION首次作用 | 101.378834659 | 含10660类实际读取/解码/校验 |
| ACTION第二次作用 | 34.456206552 | 同进程局部cache复用；非冷N=1 |
| 原V67必要full-K准备 | 12095.1191837 | 历史链继续收费一次；本次生产不读取 |
| 旧C5已备K部署链 | 7559.58426938 | 历史观察，缓存/宿主争用未配平 |

numeric事前预测上界为8000s；本次实测超过预测，原累计时间与资源门继续有效，未刷新预算或重启factor。共享工作站运行未配平，不能据此授速度比。

BUILD实际mesh/MPC 55.7434314599s，q47/q63分别54.4953358609/58.233597233s，form/JIT 0.00917251594365s，实际分区/图70.4201916899s。体核调用、局部LU、直接ADD与单元块IO合并计时8560.4155957s；其内部独立费用未记录，保留unknown，不填0、不为补计时重跑。完整形成/封存父区间与子计时不得重复相加。

ACTION实际读取局部类文件3513173560B，完成2次接口作用和1024次局部三角解。新S/局部包读取、每份场与数组IO、失败重放、辅助和文档全部计费。OS/JIT未清空，BUILD命中已有JIT明确记录；必要分段与中间研究费用分开，不能把本次完整构建链对旧ready-K时间授生产加速比。[部署边界](records/deployment_cost_boundary_v70.json) · [全部最终费用](records/resource_costs_final_v70.json)。

截至科学及增量归集的17份有采样运行，最大实际采样gap为12.106373908s；最终含文档辅助的全库存值见最终费用。0.5s只是配置，sampled峰不等于连续硬峰，未采样瞬态unknown。所有观察到的ownswap为0，OOC/GPU/新Krylov均0；原PSI/cgroup/宿主/邻增长与CPU-SMT门保持。

三个失败preflight保留：DG0积分pack键的第一假设未解决实际index0，随后按installed native pack实现重新定位；FFCx可选None header另作身份序列化修复。仅定点复验，实际数学未改；3轮修复、2个根因，无第三次盲重试。另两次辅助在CPU/SMT准入前拒绝，未启动actor，原门恢复后有界复核。科学actor资源kill/重启0，没有因writer重factor，所有失败source/stdout/stderr/费用保留。[修复](records/repair_journal_v70.json) · [有界修复时间](records/repair_budget_v70.json) · [执行链](records/execution_chain_v70.json)。

增量归集第一轮触发原2GiB辅助RSS守卫，峰约2.34GiB，控制退出与日志保留；新S整张mmap的驻留页增长是已定位原因。改为16MiB分块读取后，两项新定点库存测试及静态检查通过；唯一一次重入在停止后449.22s发起、约497.83s实际启动，2GiB门未提高，PDE与独立科学VERIFY均未重放。修复/冷却和失败消费继续收费。

已封存packet与S可只读重开；中断的部分PETSc ADD重建/续算未实测，不授通用partial-resume资格。ACTION交付apply_trace、condense_rhs、recover和lift_residual，实际支持任意非零内部/port载荷；伴随接口、PC、Krylov和distributed尚未实现/运行。只授串行局部数据驱动的无global-S作用，整个direct求解仍有global S/LU。[可消费接口合同](records/retained_operator_contract_v70.json)。

本批没有新p/h/M、NN训练、邻支集成或目标尺寸运行。全FE向量与trace＋port向量分开计费，derived字节不当作RSS；未授同精度生产时间/峰值比、连续真解、原尺寸2TB48h或NN20。[目标缺口与维数边界](records/target_gap_v70.json) · [依赖分组合入建议](records/selective_merge_manifest_v70.json)。

唯一下一pilot：为这份冻结原算子集中立一个有明确PC与作用/内存预算的有界trace迭代及数据分布验证，继续使用完整原式和C5同离散再现验收；先针对已测第二次局部作用34.46s和global LU成本核算可行性，不自动启动、不扩大全局direct或物理空间。连续精度FAIL另行保留。

本地仅新增数学/接线targeted测试、相关Ruff/compile、5项dat validate及一次紧凑文档合同；GitHub视觉NOT_VERIFIED，CI_NOT_RUN。最终closed/active null、后代清场、锁释放、完整remote SHA和clean/upstream核对后交付暂停，不通知邻窗口。
