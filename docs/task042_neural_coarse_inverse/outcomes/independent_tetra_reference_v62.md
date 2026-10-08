# V62：完整四面体相位计算与独立参照限制

本档记录怎样从冻结物理dat得到四份完整场及真实费用。四面体空间把每个原盒分成六个单元，所有内部、边、面和828端口直接进入全局矩阵，仅去除周期重复未知量；其作用是绕开原六面体张量和局部凝聚链来判别长期两簇场分歧，代价是有限全局稀疏LU。它是新候选参照，没有预先授真值。完整解释与统一物理表见[Response V62](../response_v62.md)。

## 数学与依赖边界

```math
E=e^{i\kappa\cdot x}u,\qquad C_\kappa u=\nabla\times u+i\kappa\times u,
\qquad a(u,v)=\int\mu_r^{-1}C_\kappa u\cdot\overline{C_\kappa v}-k_0^2\epsilon_r u\cdot\overline v.
```

标准UFL/FFCx完整装配后，只按真实periodic primal P作Hermitian拉回；非互伴端口分别保留C/D，全828 H和非零物理RHS保留，端口等价坐标仅一次。独立PUBLIC_BASIX按真实3×3 J/covariant Piola/DOF变换生成完整向量，不读取生产矩阵；tetra未使用hex逐轴除宽公式。p4/p5局部84/140，p3局部45，生产body q11/q13/q9，独立q13/q15/q11，Fourier三角边界生产47/独立63各真正生成一次，后续只读重载；场体吸收及跨空间共同积分q23/q31不降q。

复用Task035现有确定性tetra构造器、periodic entity/MPC、通用MUMPS、activation、监督和物理载荷/模式约定，不重跑其旧DWR/adaptive；新矩阵不消费15表/raw/Schur/ChildBlock/MacroResponse/TraceRestriction/FaceMacroResponse/旧内部LU。共享DOLFINx/Basix及相位/物理规则仍是共同依赖，不能宣称不同软件完全独立。旧局部低存储收益和失败均保留，不改或启动邻支。

## 实际冷执行及释放

| case | 完整行/828 | 实测nnz | 后端factor项 | factor载荷/decimal MB | numeric规划/GiB | sampled树峰/GiB | 完整进程链T_N1/s | solve采样最大gap/s |
|---|---|---|---|---|---|---|---|---|
| F4 | 40444 | 9307708 | 39069432 | 625.093248 | 5.319067 | 2.460529 | 432.848145 | 1.584938 |
| T4 | 40444 | 9307708 | 39070936 | 625.093248 | 5.316496 | 2.426861 | 357.761297 | 2.274196 |
| T5 | 74508 | 22757388 | 88709832 | 1419.357312 | 9.056005 | 4.847828 | 985.805547 | 2.567597 |
| TH3 | 144252 | 19517436 | 212453298 | 3399.244992 | 13.348288 | 6.813831 | 744.207395 | 3.163811 |

上表N1包含独立进程启动、对象构造、原作用、symbolic/numeric、最多两次既有精化、完整u/port保存、独立原式、矩阵/因子释放、完整E/H/curl/240/828、体吸收、必要provenance/IO及清场；没有以准备结束或小残差结束计时。研究比较不加入N1。F4是原启动+保存补审恢复链，不是一个fresh成功进程，观察跨度670.654265s；T4/T5/TH3各只有一个成功独立完整进程。系统/OS/JIT cache未清空，case数值对象未复用另一场，环境/cache namespace在run_manifest。

`GLOBAL_FINITE_LU_PRESENT`与`FULL_UNCONDENSED_TETRA_N1CURL_PHASE_UFL`明确登记。backend factor items、decimal MB、实际nnz、visible numpy owner、磁盘与sampled树RSS分别统计，见[生命周期](records/storage_lifecycle_deployment_v62.json)。最高numeric计划13.348288GiB不是实测，最大树峰6.813831GiB不是连续硬峰。V62所有numeric依据live RSS+2倍可靠INFOG16/17+2GiB≤64GiB；完整矩阵行≤200000，warn80/stop96GiB不变，ICNTL22=0、现有ordering且ICNTL23两倍decimal MB限制。因子释放后独立原作用仍可读，不因保存解删除唯一oracle。

## 科学判别与真实消费

F4解析三场约1e−7，通过全部场/240/828/功率/吸收门；F4/T4 formal原式≤1e−6通过，但独立direct1e−10分别1.74749e−10/1.51150e−10，明确FAIL；T5/TH3达到该独立direct目标。新进程VERIFY分别重建解释系数必要的tet mesh/space/MPC，保存q63包只读，原残差与producer差0，切向E共享/周期面最大7.8002e−15，四份完整mode-power从原port重新复算。没有新矩阵、factor或solve。正式新freeze时间05:26:24Z，旧FXY/R7系数首次在其后读取，不能参与初值、RHS或分流。

| 比较/原1e−4场门 | scattered E | scattered H/scaled-curl | 240点最大六向量指标 | 物理复通道 | 逐mode功率/原1e−6门 | 判定 |
|---|---|---|---|---|---|---|
| T4_T5 | 0.00386079578297 | 0.00384664078519 | 0.00659582950621 | 0.000341177672077 | 4.16566392214e-06 | FAIL |
| T5_TH3 | 0.000881614705835 | 0.000899373323589 | 0.00215234416687 | 9.44890049357e-05 | 4.39575178271e-07 | FAIL |
| FXY_T5 | 0.000920210359448 | 0.000911457862705 | 0.000909532692962 | 0.000111801006823 | 4.6325107983e-07 | FAIL |
| R7_T5 | 0.0340367805544 | 0.034007623682 | 0.0271593270223 | 0.000937434359868 | 3.16143007397e-05 | FAIL |

两个新的p/h对照仍失败，TH3也不同意T5，故不能只挑接近FXY的T5发布收敛。240点不是点值绝对最大；共同积分分别评价两原空间物理场，不先投影，方向/真实Piola保持。全部共同q23/q31操作差≤1.622563552e−12，q39不触发；功率/守恒小差不覆盖场FAIL。新p更高只扩大空间，不等于先验准确；TH3更细但阶数较低，是非嵌套h/p交叉，不预设它真值。

T4/T5的误差平方约52.48%在空气区、38.64%在Si光栅、4.65%在substrate、4.24%在缺口空气；T5/TH3约53.52%/39.27%/4.09%/3.12%。这些冻结后的区域分账不是误差界，也未用于选解。

T4/T5最坏物理振幅在bottom (−2,0,s)差1.892837692e−4，最坏功率在bottom(0,0,s)差4.165663922e−6；T5/TH3振幅在top(−6,0,s)差5.480719088e−5，功率top(0,0,s)差4.395751783e−7。辅助衰减模大坐标与真实参考面复振幅分列，不校幅相或删模式。全部复向量、物理键及区域/分量在[独立保存checker](records/independent_saved_pair_checks_v62.json)和[冻结区域分账](records/physical_error_regions_v62.json)。

## 费用、失败和可复现链

两NOTCH主case及TH3数值准备/因子/场输出在单独数值进程冷对象中完成；FFCx和OS缓存实况保留。四case必要进程共2520.622384s；研究VERIFY独立4538.095313s，全研发UTC从04:03:39Z计入实现/失败/等待/修复/IO。互斥timers与树RSS/采样gap见[最终费用](records/resource_costs_final_v62.json)，旧已知下界212227.2468480551s保留且unknown不填0。T5仅numeric+solve约21.0135s，占985.8055s约2.13%，即便免费删除也不能对这条有限链取得NN20%；更强同准确性传统控制和原尺寸成本仍未测，不伪称最终机会被普遍否定。

R1保存F4port=1原FAIL，只修零portRHS附近审核分母，原数组和输出不变，补审0新factor/solve。R2纠正macro=2与tet24/192、补齐raw/source/恢复链费用。R3补FLAT双Gate与完整保存checker；其定点测试的显式mode路径KeyError及QUAL04费用保留，单行lazy fallback修复后QUAL05的8 tests/12 compile和关键Ruff/8dat验证通过。没有因writer/测试/文档再次求解。早期未activation命令的零PDE启动失败仅有tool记录、没有原stderr归档/精确CPU，保持unknown，不造新“原始”日志。

[run/index](records/run_index_v62.json) · [science](records/scientific_checks_v62.json) · [source×文件](records/source_bindings_v62.json) · [新数组库存](records/array_inventory_v62.json) · [ignored原始归档索引](records/raw_archive_index_v62.json) · [repair](records/repair_journal_v62.json) · [最终尾部](records/final_settlement_tail_v62.json) · [依赖分组](records/selective_merge_v62.json) · [交付](records/delivery_index_v62.json)。新增数组和原始文件完整保存在ignored目录；旧父仅按hash链接，不再次嵌入旧大manifest。GitHub视觉NOT_VERIFIED，最终本地字节合同另记。

## 收口与唯一下一pilot

本授权四份新完整solve/四numeric均完成，F5因FLAT准确未准入，备用科学重解槽未用，TH3不是合格最佳参照而未追加其旧场比较；不再追加PDE。唯一后续建议是同一7680tet/p4/828的NOTCH完整h/p交叉：derived独立FE314624、加port315452，超过本批200000行权限，须新合同及实际图/可靠symbolic/64GiB规划再决定执行；目前fill/RSS/T_N1 unknown。当前不构造该网格空间/矩阵/factor。原尺寸准确性网格/实际模式/PC迭代/同时峰/≤172800s仍unknown，2TB48h和NN20未资格。无同精度基础，不算生产加速或内存改善比。

最终只推本执行分支，closed/active null、清场和锁释放后暂停，不通知邻窗，不merge或自动新窗口。