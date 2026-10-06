# V55：补齐父解审核并保存更细 H7 场

本轮把已算出的解交给独立进程重新检查，再增加 z 方向单元数，研究高阶场是否仍受空间分辨影响。旧三解审核已完成；新 H7 系数、恢复见证、物理场样本及全部828模式均保存。完整准确性比较未完成，原因是后处理 wall/JIT 与随后真实 CPU/SMT 门；这是部分交付，不是数值准确性通过，也不是证明离散方法失败。

## 物理对象与方法

固定0.7nm，缩尺 s=7/135，原 x/y/z 分段和真实三维缺口，不沿 y 复制缺口；grazing1°/azimuth5°/s/幅值1。Si n=0.999885140474+4.32477054e-6i、ε=n²、μ=1、air1，canonical材料 hash55aa34e55c5e3cc35f6849eddbd3bcc72d3b694d32bc4885299ef373acd676a2。物理场 E=g*u，g=exp(iκ·x)，κ=[8.94046081729244,0.7821889682108057,0]；H=g*(curl(u)+iκ×u)/(ik0μ)。完整弱式交叉项、包络双周期、内部特解及 DtN 保留，未将场投回旧多项式空间。

边界使用 m=-11..11,n=-4..4、上/下两侧与 s/p 全828模式；表格中的 trace 是共享边/面的未知量，内部是单元独有未知量。凝聚先消去内部再恢复它们，物理没有删掉内部场；本次复用原内核，局部与全局因子均计费。有限直接 authority 不代表原尺寸 production 架构。

| 模型/用途 | cells/p/模式 | 独立 FE/trace/内部/native | 含端口行 | 结果 |
| --- | --- | --- | --- | --- |
| R6，旧 p6 父对照 | 160/6/828 | 104832/32832/72000/110700 | 33660 | 旧保存对象本轮独立补审；不是重解 |
| R7，同 p7 h 父对照 | 160/7/828 | 166208/45248/120960/174174 | 46076 | 旧保存对象独立补审；旧跨 p FAIL 保留 |
| C，p7 模式父对照 | 160/7/1188 | 同 R7 | 46436 | 旧保存对象独立补审 |
| H7，新 z 细化 | 320/7/828 | 330848/88928/241920/346724 | 89756 | 完整返回已保存，最终场增量/energy缺项 |
| T6，条件横向 | 320/6/828 | derived209664/65664/144000 | 66492 | 容量通过，完整case时间预算不准入，not_run |

旧R6/R7行库存与[物理与源码绑定](records/physical_identity_bindings_v55.json)及父receipt配对；旧80cell/532模板只描述基准网格，实际 resolved/derived 和现场 mesh/MPC 明确为本case320/p7/828，未拿模板冒充实测。

## 原方程、内部恢复与连续性

以下是新进程 q63 原未凝聚体式/全端口与保存 checker 的结果，不读取旧factor。true/native/增广/port 门1e-6、直接目标1e-10；恢复/操作尺度1e-10。它们只说明同一离散方程解正确，不能替代空间精度。

| Q0实际父状态 | true/native | 增广 | port | 内部恢复操作误差 | 独立方程/恢复门 |
| --- | --- | --- | --- | --- | --- |
| R6 | 1.19126133444e-11 | 3.47143455339e-11 | 1.69389608966e-13 | 1.16438064349e-15 | PASS |
| R7 | 1.92618886776e-11 | 2.43247551882e-11 | 1.47245676198e-13 | 1.66518742548e-15 | PASS |
| C | 1.92501228548e-11 | 3.19459458922e-11 | 2.33136752282e-13 | 1.63805238398e-15 | PASS |

实际R6/R7各检查464面：384内部、40 x周期、40 y周期，每面8×8 Gauss点。R6整体切向包络E跳跃7.38412255368e-16、最坏面9.31057648118e-15；R7为9.38407700784e-16和9.39676329911e-15，门1e-10。完整 native 求值配对最大约2.80e-15。检查的是物理切向迹，不要求法向E/离散H强连续，也不以slave存储0代替它。每面数组和方向身份保留。[父审核](records/prior_audit_completion_v55.json)

H7 actor 原审核和独立已保存 q47 体作用＋q63 carrier 重算：true/native4.20391286913e-11，增广4.25154323597e-11，port5.47662588655e-15，身份5.46035870652e-16，slave0；内部恢复1.66744658543e-15，split作用身份2.67060457741e-15。保存检查 PASS，但 **fresh q63 FE/basis、A_volume/能量与共同几何积分 not_run**。独立已保存 carrier coupling 差1.37533915031e-13低于1e-10，只是该作用见证，不授完整场。[保存原式检查](records/partial_saved_checks_v55.json)

## 完整场、模式与准确性边界

H7完整 authority 是346724项 native包络、精确mesh/dofmap/MPC/basis/κ；保存320个cell-center total/scattered E/H/curl及全部828物理模式键、极化、参考面、复振幅和功率。这320点不冒充原要求的固定240点跨网格验算。恢复数组/字段与保存u配对，端口坐标误差0。A_volume编译尚未完成，能量不能由1−R−T自行宣布通过。

| 状态 | R_total | T_total | A_balance=1−R−T | A_volume / 独立能量 |
| --- | --- | --- | --- | --- |
| R6，独立全828复算 | 0.0762187041468 | 0.905665171695 | 0.0181161241578 | 已复算；能量1.38490e-13 |
| R7，独立全828复算 | 0.0762050387418 | 0.905659241932 | 0.0181357193259 | 已复算；能量2.46223e-13 |
| C，独立全1188复算 | 0.0762049712890 | 0.905659321829 | 0.0181357068820 | 已复算；能量4.52673e-13 |
| H7，保存输出、部分审核 | 0.0762050392207 | 0.905659241741 | 0.0181357190385 | not_run / not_run |

H7零级 R00_s=0.0761864135548、R00_p=3.18264848064e-14、R00_total=0.0761864135548，全模式输出保存在[模式/字段索引](records/field_mode_inventory_v55.json)，不由功率反推复振幅、不校幅相。父模式最大操作/功率缺陷≤7.78e-15。

下表为本轮从保存积分重判的旧有限比较，field_max涵盖total/scattered E/H/curl，selected为固定240点；场/selected/物理参考面复通道门1e-4，逐mode功率1e-6，RTA/体吸收与能量1e-5。原辅助坐标可有很大倏逝系数，科学比较用原物理参考面振幅，不改分母。

| 旧比较 | field_max | selected_max | 参考面复通道 | 逐mode功率最大差 | 完整增量 |
| --- | --- | --- | --- | --- | --- |
| B_R7 | 0.00054411833289 | 0.000447330676776 | 9.79660408959e-05 | 1.65478674563e-06 | FAIL |
| P_R6 | 3.18387392885e-07 | 1.89483025184e-07 | 3.01098854815e-07 | 1.39844573736e-11 | PASS |
| R7_R6 | 0.0341329393344 | 0.027169397695 | 0.000936145277365 | 3.18721409795e-05 | FAIL |
| R7_C | 8.33244814139e-05 | 6.46048589399e-05 | 1.87616951292e-05 | 3.21012967985e-07 | PASS |

同828跨p约3.413%的散射差保持失败；p7 532→828仍超门。H7的R/T接近R7不证明场接近，也不能推断R7→H7通过。新的R7_H7主比较、R6_H7跨p诊断全部not_run；未形成新h准确性锚点。[完整比较门及父hash](records/spatial_accuracy_checks_v55.json)

T6事前从R6散射包络选择x：q15指标x=4.69448034950e-5、y=2.77634598163e-6，固定(2,1,2)。原始核准备median预测3024.55s、保守4695.06s，已经超过剩余完整case额度，故不启动它；这是时间不足，不是T6数值失败。[T6冻结与准入](records/transverse_decision_v55.json)

## 真正复用、容量、生命周期与费用

只读核对其他任务的实际可访问记录，未找到H7相同几何/p7/828完整解。隔壁是5nm/p3/40学习wave greedy；dot可访问发布是原尺寸18cell/p6/12所选模式边界组件；工程冻结784cell/p6/340不同对象，最新remote对象不可本地读取。未整体merge/import活跃工作树或复跑其历史。该范围不是穷尽分支审计。[复用核对及限制](records/cross_branch_reuse_v55.json)

原`hcurl_assembly_time_condensation`、`hcurl_cell_static_condensation`、`phase_raw_tensor_reader`、`phase_tensor_checkpoint`源码未改。H738类 exact几何/tag无法命中旧Z2张量；全部完整Cκ原张量约1.023GiB payload已原子保存并逐位重开，另有cell_layout，不是39个数学类。72个方向Schur类，local1344=588trace+756内部。禁止近似合类，raw不是Schur/CSR/factor。[raw库存](records/raw_tensor_inventory_v55.json)

| H7计时范围，均 measured/s | 数值 | 解释 |
| --- | --- | --- |
| raw核生成 | 12393.2724637 | 38类，准备瓶颈；已经保存 |
| 单元内部消元数学核 | 52.7429328552 | 复用原凝聚，并非重新开发算法 |
| 稀疏插入/预分配 | 5.97768831183 / 3.50456824293 | 全贡献/共享/MPC保留 |
| build总时间 | 12460.0214764 | inclusive，不能再次加raw与消元 |
| 非raw凝聚阶段exclusive | 271.052527560 | 含其他组装/身份工作，不等于53s核时间 |
| symbolic / numeric | 5.43331655604 / 192.818016965 | 实际单一MUMPS factor，随后释放 |
| solve/恢复 / 一次精化 | 7.07480609487 / 7.15679812408 | 精化计费、未更改精度门 |
| 原dat链下界 | 13627.0547106 | 全准备/失败尾段均在内，不是纯solve时间 |
| Q0 dat链下界 | 1333.09409157 | 原三解补审，不factor/solve |

原live symbolic INFOG16/17=13052 decimal MB，2倍workspace＋RSS＋2GiB=41637240320B，低于64GiB。numeric ICNTL22=0/23=26104，原ordering规格不变，无OOC/shift/BLR扫描；INFOG19=19578MB是后端统计，不能当factor独立RSS。CSR89756阶、实际存储109014824 NNZ；未分配完整native全局矩阵。原oracle留存，factor和矩阵在后处理中断前已释放，独立体作用路径仍可消费。sampled simultaneous树峰22.8337974548GiB，不是continuous hard bound；全部swap0，原PSI/宿主/邻任务余量未降低。[容量与因子](records/capacity_factor_v55.json) · [生命周期](records/object_lifetimes_v55.json)

所有源/ABI/CPU与数学线程绑定在[manifest](records/run_index_v55.json)、[source](records/source_bindings_v55.json)。Q0/SETUP/H7实际CPU34/0/41，saved消费CPU21；MPI1/math1/GPU0。Supervisor目标0.5s采样，实际最大间隔由最终费用汇总统计（初次汇总最大1.626764477s），不声称每0.5s必采一次。树监督和deadline覆盖BLAS/JIT/后代；main达到wall后清理全部自有后代。

两次资源观察163.354742765s与156.967539921s，原CPU/SMT恢复才重入；最后一次拒绝的下次合法probe超出第二episode期限，没有第三次FE观察或绕门。失败收据逐核排除理由保存，episode02原CPU=null记录保留，在新证据用live manifest纠正为21。[拒绝/核排除](records/admission_refusals_v55.json) · [逐核CSV](records/cpu_exclusions_v55.csv)

三类费用分开：本批研究全部prepare/测试/失败/拒绝/补审；新case缓存增量；从几何开始fresh冷N=1及历史必要成本。最终费用[JSON](records/resource_costs_final_v55.json)保存所有lower/unknown，研究已测下界超过15400s，旧已知139828.48144973788s不清零，unknown不填0。等待包含总elapsed，不能重复加到嵌套actor费用；JIT/OS缓存未清，不宣称无争用速度比。最终storage/count/clock/closed见[结项](records/campaign_closed_v55.json)，大数组/JIT/raw均ignored，不删除旧失败。

## 修复、独立验收与未运行项

主dat在已有完整解后停止，saved消费不应被原“主solve预留”挡住；新增只读receipt绑定及累计16000s casecap分支，旧费用/全局/审核余量不刷新。两项测试检查剩余额度和篡改拒绝。第二个问题是mainkill留下自身独立JIT缓存0字节compilemarker；仅原子移走该精确marker并保存原件，没有清理邻任务缓存。随后resource门拒绝，未再次FE。部分输出用独立保存checker继续可做的审核。主stop、postconsumer失败、三个CPU拒绝、全部费用保留。[修复记录](records/repairs_v55.json)

最终8 focused tests、8dat真实schema validate、相关Ruff/compile通过；新切向审核、预算/阶段隔离、保存向量/manifest/byte篡改反例都有覆盖。只做必要模块测试，无fullpytest/全仓索引。一次15项文档合同、最终表格/链接/旧正文逐字保护见[检查](records/documentation_checks_v55.json)，GitHub视觉NOT_VERIFIED、CI未运行。数学kernel及正式source与文档HEAD分开，未追溯改写历史。[selective merge分组](records/selective_merge_manifest_v55.json)，没有merge approval。

未运行：H7 fresh FE q63/basis、A_volume/energy、共同q23/q31场、固定240点增量、R7/H7与R6/H7；T6及其审核/比较；fresh VERIFY_COST FE阶段。以轻量独立保存checker与费用collector收口，不能伪称后者代替FE。唯一下一完整工作是新合同下只消费这份现有H7保存解补齐这些审核/比较，再决定空间动作。不重factor/solve，不自动启动新空间、模式、NN或目标模型。原尺寸0.7nm/连续收敛/2TB48h/NN20均未资格。
