# V50完整物理准确性与成本：积分修复后，原有限空间仍不足

## 1. 问题、流程及资格边界

本轮依[Review V48](../review_report_v48.md)检查完整有限物理计算的准确性，为下一种神经学习对象建立可信输入、传统控制和全费用边界。积分一致性、代数求解、连续物理准确性是三件不同的事：积分规定有限元方程；小残差表示已解出该方程；解析场与相邻离散比较才检验它是否逼近真实波。本轮前两项有实际进展，第三项仍失败。

完整532通道积分核对后，做有解析答案的平界面FLAT和唯一传统六Gram控制。六Gram是预先积分六个参考矩阵，再按真实几何／材料精确组合单元张量；它省重复积分，不学习参数。固定四空间表示门失败后，停止依赖的相邻NOTCH和最细FLAT，没有追加网格或训练。

| 范围 | 固定身份与实际行为 |
|---|---|
| 几何／波长 | 80hex，s=7/135；λ=0.7nm，grazing1°、azimuth5°、s偏振；原三维周期域，不是原尺寸530856cell |
| x/y/z切分 | s×(0,16.5,25,33.5,50)；s×(0,6.25,12.5,18.75,25)；s×(−10,0,40,80,120,130) |
| 材料 | canonical `input/materials/si_optical_constants_v1.json`；nSi=0.999885140474+4.32477054e−6i，epsilon=n²，mu=1；air n=1 |
| 来源／alias | `SI_OPTICAL_CONSTANTS_USER_20260929_V1`，user_supplied；原标签0.699999988明确alias0.7，不插值／联网换值 |
| FLAT | z>0空气64cell、z<0基底16cell；独立控制，不能把光栅的R当解析平界面R |
| NOTCH | 原cell38/52两cell缺口；40普通air、2notch air、16substrate、22Si block；没有沿y复制缺口 |
| 端口 | m=−9..9、n=−3..3，上下两侧／s,p完整532；参考面z_top=6.7407407407407405、z_bottom=−0.5185185185185185nm |
| p5未知量 | native32865、独立FE30800、trace11600、内部19200、凝聚trace＋port12132行；全trace/内部/532通道保留 |
| 算法／因子 | Assembly-time condensation消去单元内部再恢复；FLAT29／NOTCH30局部完整LU，各一个有限全局p5 MUMPS因子；非factor-free |
| 新完整solve | FLAT_P5与GRAM_CONTROL各一次合法返回；失败准备没有解；5槽中实际2solve，条件3槽not_run |
| 不授资格 | `ACCURACY_ANCHOR_ON_FIXED_532`、continuum convergence、原尺寸0.7nm、2TB／48h、NN20均未授 |

普通默认保持。新代码与输入仅opt-in；没有全局p4生产PC、NN训练、旧codec／固定A修正、目标网格、dot实验或GPU。V49原q同离散资格及V42等历史FAIL原样保留。

## 2. 全库存边界积分与旧方程差异

表面Fourier相位不是多项式，不能由体积多项式求积理由跳过。生产q47使用分离方向积分；独立q63使用公开Basix二维求值，全basis、完整C/D/H及入射traction/projection、真实Piola／orientation／Floquet散布，无小项删减。端口F/C不互当共轭。双向见证作用原完整向量，保留极小的非零系数。

| degree | q47对q63最大相对差，门1e−11 | 原native未截断q对q63最大差 | 统一q47下旧NOTCH场rho | q47/q63该rho |
|---|---|---|---|---|
| p4 | 7.7268457243e−14，PASS | q23：0.0104594332，FAIL | 0.24645100083006513 | 0.24645100083005428 |
| p5 | 7.7218494057e−14，PASS | q25：0.00119619755，FAIL | 0.42493880660924543 | 0.4249388066092322 |

完整正向／共轭转置及操作尺度1e−10门通过；[独立checker](records/boundary_independent_checks_v50.json.gz)绑定每degree、每532项及完整作用数组。V49旧实现还在小行／小耦合处截断；它与“q不足”分开测，不能把截断差都归于求积。

| 固定旧场的边界作用变化 | p4 | p5 |
|---|---|---|
| 旧截断q→完整q63，累加后范数 | 0.3597739797452616 | 0.7314095587031372 |
| 未截断原q→q63，纯求积范数 | 0.000262277348182588 | 0.000332812650393966 |
| 截断变化的各mode平方项和 | 0.301115956238562 | 0.687152531773374 |
| 截断变化的交叉项 | −0.171678639736818 | −0.152192589211056 |
| 完整原残差差恒等式操作缺陷 | 1.2050004727e−16 | 2.6904660267e−16 |
| 最大mode项 | top/s，m=3,n=0，范数0.4181400 | top/s，m=3,n=0，范数0.6806406 |
| 最大原native行及复变化 | 行9848：−0.0605753441+0.0388709478i | 行14225：−0.0791998537−0.00078832415i |

每mode先经共享行散布，再组装求范数；负交叉项说明贡献会相消，不是把532个范数直接相加。RHS变化1.20471e−13／5.58e−14远小于边界作用变化。具体每side/m/n/polarization、所有行和分子／分母见[COST原始归因](records/opportunity_decision_v50.json.gz)及其`all532_boundary_effects.json`父hash。不能由最大的一项宣称唯一根因，更不能回写V49旧q残差为失败或成功。

体积分另验：每p全部17个raw几何／材料类，实际方向0/576/4680/32769/36873；curl、mass、完整Maxwell张量分别对原FFCx，操作尺度约1e−15。p5真实FFCx form_data记录的规则为default、实际和estimated degree13，N1E/hexa p5、540维、covariant Piola。数学理由仅适用于仿射常材料多项式体项，不适用于入射／边界相位。原未凝聚体作用一直作为独立oracle，没有让新回调调用自己审自己。

## 3. 保存背景、总场和区域交叉项

固定共同q31积分点，分开解析层状背景、每p FE插值背景、total场和total减同一解析背景。旧散射定义不回写。令dT为总场差、dB为两插值背景差，则旧散射差dS=dT−dB；保留−2Re〈dT,dB〉，不能拿背景差“抵消”总场失败。

| 全域平方范数 | E | H_code／scaled-curl |
|---|---|---|
| 总场差² | 0.112104830476 | 0.114548784636 |
| 两FE背景差² | 0.902399290226 | 2.370736656289 |
| 交叉项 | 0.059327075141 | 0.065207118738 |
| 原每p散射差² | 1.073831195843 | 2.550492559663 |
| p4／p5总场² | 0.012854093395／0.180922435547 | 0.014458407342／0.185022893462 |
| 共同解析背景下p4／p5散射² | 35.463321352162／36.253814643065 | 35.458097788345／36.248392582647 |
| FE4／FE5背景对解析背景误差² | 1.382412273425／0.157436694464 | 3.343298860227／0.578359371457 |

恒等式最大缺陷6.20334e−16。区域的互斥主体是普通air40/notch air2/substrate16/Si22，其平方和核对全域；4个x条带各20cell也覆盖全域。“缺口邻域36cell”为重叠诊断mask，明确不当第五个互斥区域再相加。区域、方向、每项交叉量及原数组见[归因记录](records/saved_field_attribution_v50.json)和[旧场原方程审核](records/saved_field_equation_rechecks_v50.json)。背景表示误差是真实问题，但总E/H本身仍大差，不能通过重新命名散射场授精度。

## 4. FLAT完整控制与原弱式见证

解析控制采用exp(−iωt)、被动平方根、真实上／下参考面，完整E/H及curl与边界mode规范一致。H_code=curl(E)/(i k0 mu)，物理A/m需除eta0；功率沿该规范计算，体吸收用Im(epsilon_r)，不使用Im(n)或abs(n)²。解析零高阶／零散射的绝对检查以入射单位场或入射功率为尺度，避免近零分母。

| FLAT p5独立审核，q63边界 | 实际值 | 门 |
|---|---|---|
| 原true/native | 5.66631438697e−12 | 1e−6；直接内部目标1e−10，PASS |
| 增广／port | 3.52235258771e−12／1.96707933917e−13 | 1e−6，PASS |
| 原操作恒等式 | 2.65014245468e−16 | 1e−10，PASS |
| 内部恢复／最坏cell | 1.30759690586e−15／2.13426420033e−15 | 1e−10，PASS |
| split恢复恒等式／slave | 7.24630016210e−16／全slave-zero | 原规则，PASS |
| total E L2误差 | 1.01270192133 | 1e−4，FAIL |
| total H／scaled-curl误差 | 1.01269620637 | 1e−4，FAIL |
| selected total E／H误差 | 1.01694609695／约1.015861 | 1e−4，FAIL |
| 解析精确场代入原弱式 | relative4.55019582785e−12；operation2.03107647631e−12 | 1e−10，PASS |
| 解析切向E／H连续及dispersion | 0／9.98936e−15／0 | 解析约定通过，不检查法向伪连续 |

精确解析场的弱式见证不是FE背景插值：用完整原native basis、原Piola／方向、literal Floquet复对偶在共同q31积分，端口独立q63。它支持当前符号／源／参考面约定；不能据此宣称所有误差只有一个根因。实际FLAT界面H/curl固定点跳跃约4.88083e−4另作诊断；原场误差仍按完整门FAIL。

| FLAT有限域功率 | 实际FE | 解析控制 | 差／门 |
|---|---|---|---|
| R_total | 0.999826355426 | 0.113433408920 | 0.886392946506／1e−5，FAIL |
| T_total，下参考面含损耗传播 | 0.000173627882309 | 0.882458998614 | 0.882285370732／1e−5，FAIL |
| A_balance | 1.66919919121e−8 | 0.00410759246558 | 0.00410757577358／1e−5，FAIL |
| A_volume | 1.66916748868e−8 | 0.00410759246558 | 0.00410757577390／1e−5，FAIL |
| 最大逐mode功率差 | — | 全532检查 | 0.886216836707／1e−6，FAIL |
| 能量闭合 | −3.16968673530e−13 | 0 | 1e−5，PASS，不能替代上述FAIL |

FLAT实际R00_s=0.999650245627、R00_p=9.32084636442e−6、R00_total=0.999659566474。非零阶最大边界振幅差0.0105789252；入射完整投影q47/q63对解析最大差≤5.86546e−16。完整532键、side、偏振、归一化、reference_z、phase、复振幅、功率保存在结果JSON与NPZ，非只报R/T。完整原系数、total/scattered E/H/curl以及selected点均已保存。

## 5. 固定四空间筛选、表示下界和未运行项

筛选没有求解PDE，用解析FLAT完整FE插值经原Nédélec矩／Piola／方向/MPC和独立Function.eval检查，物理L2及curl在共同积分计算。q23/31还作积分配对；ORIGINAL/p6该配对自身不通过，明确保留，不借它夸大最细空间资格。

| 空间 | 独立FE数／cell | E插值相对误差 | H/curl插值相对误差 | q23/31配对 | 表示门1e−4 |
|---|---|---|---|---|---|
| ORIGINAL p5 | 30800／80 | 0.0667525598 | 0.127951220 | 5.37576e−11 | FAIL |
| ORIGINAL p6 | 52992／80 | 0.0191274788 | 0.0435204873 | 2.23492e−9，另FAIL | FAIL |
| X2 p5 | 61600／160 | 0.00155630247 | 0.00585405624 | 8.44090e−14 | FAIL |
| X2 p6 | 105984／160 | 0.000217094053 | 0.000950015279 | 1.51863e−12 | FAIL |

MPC相对误差7.37e−16..1.08e−15，native求值／独立映射通过。SCREEN中的notch坐标盒是固定区域诊断箱，不是把FLAT重新放入Si缺口；FLAT真实材料仍64air／16substrate。[筛选与完整场分区](records/representation_screen_v50.json.gz)保存所有问题，不从NOTCH最终场选赢家。

插值FAIL本身不等于最优表示下界。额外derived分析允许每cell任意多项式，故比连续/MPC空间更宽松：已知x向相位的第一项遗漏Legendre系数贡献为(2l+1)·spherical_jn(l,kx·h/2)²，按真实x长度与场分量权重相加。Nédélec Ey的x次数≤p，而Ex/curl_z≤p−1；解析H_z占平方范数0.9998362963。无FE对象／A作用／新空间扫描。

| 空间 | E相对误差derived下界 | H/curl相对误差derived下界 | 对1e−4门的含义 |
|---|---|---|---|
| ORIGINAL p5 | 0.0421647909 | 0.118153739 | 任意同空间系数也不足 |
| ORIGINAL p6 | 0.0124393386 | 0.0410405739 | 同上 |
| X2 p5 | 0.00106005292 | 0.00575259045 | 同上 |
| X2 p6 | 0.000153352778 | 0.000937459741 | 仍超门约9.37倍，不能靠更长迭代救场 |

这是float64解析公式在本冻结相位／次数假设下的derived界，不是区间认证的通用条件数或连续误差定理。x最大单元相位跨度约7.649rad；不能据此自动再细化或追加p。容量独立列出：实际p5 trace11600+532=12132；ORIGINAL p6理论17524行、X2 p5理论23732、X2 p6理论34516，需要数值factor时仍应实际MPC核对及symbolic估计。本轮科学表示已阻塞后两级，不做未准入factor来“证明容量”。

| 槽位 | 状态 | 具体原因 |
|---|---|---|
| FLAT_P5 | completed，accuracyFAIL | 真实完整方程／场已取得 |
| FLAT_SELECTED | not_run | 四空间全部未过表示门；较高端未准入 |
| NOTCH_LOW | not_run | 相邻高端未通过表示门，Review §6.4依赖不成立 |
| NOTCH_HIGH | not_run | 同上；不挪空槽跑第三p／320cell |
| GRAM_CONTROL | completed，有限传统准备检查通过 | 唯一独立授权原80NOTCH/p5控制 |

## 6. 精确准备控制与两种端口尺度

GRAM_CONTROL以相同raw几何／材料／basis构造六Gram，全部17raw／5orientation对原FFCx完整curl、mass及组合tensor通过；坐标无四舍五入，原FFCx未凝聚体oracle保留。新进程、物理零初值、新矩阵／局部和全局因子，不读旧场warm-start；资格数据复用费用单列。

| NOTCH/p5控制独立审核 | 实际值 | 结论 |
|---|---|---|
| 原true/native／增广／port | 7.02189798225e−12／3.19741790307e−12／2.38136305388e−13 | 原方程通过 |
| 恢复最坏cell／split恒等式 | 2.68958008522e−15／7.08853704521e−16 | 恢复通过，slave-zero |
| R00_s／p／total | 0.999620116316／9.27400602399e−6／0.999629390322 | 完整端口定义，不混R00与R_total |
| R_total／T_total | 0.999796579849／0.000173880774554 | measured，非准确性参考 |
| A_balance／A_volume | 2.95393762447e−5／2.95393759980e−5 | 两种独立功率途径 |
| 能量闭合 | −2.46691556072e−13 | 通过不等于场准确 |

与V49旧q25/clipped p5场的冻结后诊断：total E/H差0.0309187534／0.0329919726；同解析背景下散射差0.00218419462／0.00235709258；边界复振幅相对差0.0163768306，最大单mode功率差2.28495e−6。R/T/A_volume差8.72360e−7／2.72931e−6／1.85192e−6。q与截断都改变了，不能把这些差拿来宣称六Gram改变原方程或纯优化加速；也不能拿总体功率小差授完整场资格。

消逝mode使用指数reference-plane尺度，raw系数可极大：最小H权重1.07200e−194、最小boundary_phase8.13213e−98。q63重新闭合仅作诊断，最终audit始终用保存candidate端口，不偷换成更好的向量。

| q47保存port对q63重闭合 | FLAT_P5 | GRAM_CONTROL |
|---|---|---|
| raw port相对差 | 0.0256795806 | 6.79041085469e−5 |
| raw差最大绝对值 | 4.31242e81 | 5.90187e81 |
| 原H加权port行相对差 | 1.96703e−13 | 2.38141e−13 |
| 已知参考面phase后的最大复振幅差 | 1.02592e−13 | 1.54565e−13 |

全532 raw、行作用、boundary值独立保存；没有用拟合幅相、clipping、伪逆或丢通道消除差。raw不是原port行残差，也不是可混用的场尺度；本轮没有跨q原始坐标一致性的过强声明。

## 7. 真实时间、生命周期与资源

| 成功路线的排他阶段s（父子不重复相加） | FLAT_P5 | GRAM_CONTROL |
|---|---|---|
| mesh／MPC | 0.432940 | 0.367186 |
| 原体form＋完整C/D/H | 21.644941 | 21.355145 |
| 物理RHS | 0.126426 | 0.129166 |
| 凝聚／局部因子／装配整段 | 24.954478 | 25.175703 |
| 全局有限factor | 11.103522 | 11.243065 |
| solve／最小恢复 | 0.550314 | 0.551248 |
| E/H/curl输出 | 21.245674 | 1.067894 |
| 全532功率／体吸收 | 3.690500 | 4.991795 |
| 完整dat launch测量下界 | 136.127185 | 100.210978 |
| worker / supervised s | 116.409095／120.979058 | 80.818298／85.035558 |

输出JIT命中不同，shared-workstation争用不配平；不授无争用加速。成功FLAT重用已付费失败准备tensor，NOTCH用了已付费资格父数组；不是从几何开始、所有依赖免费fresh cold。完整N1应增加所需参考资格／失败／审核与未知启动费用；[冷费用记录](records/cold_n1_costs_v50.json)将这些明确列为依赖。不能把成功两次运行相除当优化速度。

| 凝聚build_audit内部子计时s（已包含在上表，不再相加） | FLAT_P5 | GRAM_CONTROL |
|---|---|---|
| kernel callback | 7.732044 | 8.252091 |
| 局部Schur／内部LU | 2.650351 | 2.609620 |
| 插入 | 0.497674 | 0.479420 |
| trace预分配 | 0.605841 | 0.468734 |
| 本build总段 | 12.062904 | 12.184649 |
| raw／oriented Schur类 | 16／29 | 17／30 |
| 原完整audit tensor载荷B | 135302400 | 139968000 |
| 保留Schur载荷B | 41760000 | 43200000 |

失败FLAT准备kernel约750.04158s含全／curl／mass资格工作，不是全LU或不可避免的生产准备。没有补造V49已释放对象的剖面。unique-owner可见数组字节是下界，PETSc/MUMPS隐式workspaceunknown，已纳入整树采样而非拿数组总和冒充RSS。

两solve在12132行、局部540维下事前满稠密与缓存重叠包络9817879936B，低于16GiB规划门；不是实际factor载荷。实际采样树峰2079211520／2072502272B。返回向量在factor仍合法时先原子保存；FLAT约72.774s、NOTCH约72.942s释放全局factor，随后凝聚矩阵释放，再生成输出。原体oracle与最小恢复包一直保留，[生命周期](records/object_lifetimes_v50.json)绑定实际事件。

| 其他实际科学／收费工作 | supervised秒 | 状态 |
|---|---|---|
| 最终完整BOUNDARY | 208.317974 | 成功 |
| 最终ATTRIBUTION | 1250.989447 | 成功 |
| 四空间SCREEN | 198.042946 | 四个准确性负结果 |
| 独立VERIFY | 293.329448 | 原式／恢复通过，物理精度FAIL保留 |
| COST | 11.592638 | 归因／必要界完成 |
| 第一版BOUNDARY | 237.006996 | downstream小项截断未完整，旧包保留，非最终authority |
| 第一版ATTRIBUTION主动中断 | 131.818827 | 先修已定位边界截断接线 |
| ATTRIBUTION stale自身JIT marker | 124.984983 | FFcx未完成.so；新隔离cache后继续，旧文件保留 |
| FLAT metadata API失败准备 | 808.156467 | form_datas/form_data错误；solve之前，无返回场，费用不消失 |

自有deadline覆盖JIT/BLAS/全部后代，1s超时／清场反例通过。原窗口05:10:55.885225580Z→heavy11:25:55.885225Z→交付12:10:55.885225Z未刷新。MPI1/math1/GPU0/Loader0/ownswap0，qualified native Linux复数PETSc，隔离cache/TMP/bytecode/模型目录；未重装环境／改ABI／邻任务。

监督配置0.5s，但实际全集最大间隔16.948009s在qual01的慢存储统计；修复后正式科学阶段最大3.826928s，不能写成始终0.5s。树sampled hard24GiB/warn20GiB，实际峰约1.94GiB，不存在可写cgroup连续硬峰证明。未观测资源／PSI停机；邻任务可比阶段不可得，无法保证绝对零干扰。所有cost标shared-workstation。

最终累计、所有准入核号／SMT、样本间隔、存储去重、free和新raw/archive成本见[最终资源账](records/resource_costs_final_v50.json)，不同采样／费用snapshot明确区分。历史已知下界92100.10441544611s继续累计，所有失败／重放／测试收费；整个elapsed与已知有载下界不混用，unknown实现和历史细分不补0。

## 8. 神经20%必要条件与唯一下一建议

当前没有准确同物理非神经baseline，因此没有合格NN性能分母。唯一保留的未来学习对象是完整物理FE＋DtN系数生成，避免真正昂贵的准备；它需要不同的相位表示，而不是重复旧固定A修正或同空间系数学习。传统六Gram与完整边界修正已经作为强控制。

令完整传统费用T_B=C+V，V为可能替代步骤，f为可省比例，H为全部数据／teacher／训练／加载／审核差额／纠错。必要条件为fV−H≥0.2T_B；它不是充分条件，且同时峰另一项仍合规。

| 缓存／共享下诊断费用下界，非合格性能分母 | T_B s | 乐观可替代V s | f=1时H最大s | factor＋solve完全免费最多省 |
|---|---|---|---|---|
| FLAT_P5成功dat | 136.127185 | 36.608313 | 9.382877 | 8.560991% |
| GRAM_CONTROL成功dat | 100.210978 | 36.970016 | 16.927820 | 11.769482% |

完整同case teacher已超过该H允许量，故这种冷N=1监督提案被当前乐观必要界排除；只替代尾部也不够20%。不能因失败准备很慢而拿它当最佳传统分母，更不能删除独立审核费用“制造机会”。若提无teacher路线，仍需实际输入、不同表示、学习/推理/纠错上限与完整同正确性控制；本轮不授权训练。

内存诊断中，两route完整peak可比性与连续峰均未证明；20%条件应针对同一路线真实同时峰，而非拼接两条route的最低时间/最低内存。数据／标签／网络激活／optimizer／port缓存及因子重叠必须一起计。原尺寸2TB不能由本80cell直接外推。

唯一下一建议：集中规划显式保留已知Bloch／入射相位、只表示慢变化部分的完整物理离散与神经系数生成合同。先用同解析FLAT及完整NOTCH确认表示与物理精度、绑定最强传统准备控制和可核算冷N=1费用空间，再允许真正学习；这不是安排另一轮单纯FE演示，亦不要求先完成原尺寸才允许有限神经pilot。本批不自动实现／训练／提高p或扩域。

## 9. 源码、证据、修复与交付

| 实际阶段 | clean run source |
|---|---|
| 最终BOUNDARY | `0fd75a7ba02b25ff9c2e0514c3c0b351447c8a56` |
| 最终ATTRIBUTION | `0495fcc83552a8b6b2e6ea691454c9877afa10fd` |
| SCREEN | `50866b0d2047527f89fd283384f10029233065ff` |
| 两成功solve | `ba6644fae8ec62ba191a7bac04f2d21006c8264c` |
| 独立VERIFY | `e82b713ec9bc86b124ef9f623a981664ffe93ce2` |
| COST／最终focused／collector | `f2173db00b8116a00f7b87e78b9e585ed83b38fa` |
| 文档／交付HEAD | 最终Git报告；不代替上述任何运行源 |

source manifest与Git blob初次逐版本核对1151组；raw初次归档618条，结算尾部另补，不能把早期快照当最终库存。100个科学NPZ、521实际成员、1197627632B数值payload；完整包hash和逐成员父receipt/headers分开，未伪称所有header都有新member hash。详细[初次source](records/source_bindings_v50.json.gz)、[结算source](records/source_bindings_final_v50.json.gz)、[数组](records/array_inventory_v50.json)、[headers](records/array_headers_v50.json.gz)、[run index](records/run_index_v50.json)、[物理/输入绑定](records/physical_identity_bindings_v50.json)、[初次raw](records/raw_archive_index_v50.json.gz)、[结算raw](records/post_settlement_archive_v50.json.gz)及[delivery](records/delivery_index_v50.json)可重算。

普通bug同轮修复：全历史存储每tick统计、边界下游小项截断接线、自身中断留下的JIT marker、formal launcher费用reader、实际FFCx元数据API。API错误后从完整身份checkpoint继续，不重算已合法返回场。第一份raw/class资格、失败日志、时间和旧source全部保留。没有把普通不收敛当bug扫参数。修复journal另有[preserved记录](records/repair_journal_v50.json)。旧successful resolved_config里的继承说明文本仍写旧表面规则，而实际显式degree47及factory为q47；最新loader已修正说明，旧字节不动，新identity记录明确勘误。实际form_data与稳定Basix元素身份在独立VERIFY另补，不让内存地址repr成为“元素hash”。

10个one-run dat真实validate；最终18focused、相关Ruff、完整source compile、独立deadline清场测试通过。最终15文档合同和Review V48／response／本结果的实际字节、链接／表格另验；没有全仓PDE重复或CI声明。精确GitHub页未取得视觉证据，NOT_VERIFIED。

Selective merge按依赖组见[changed_files](records/changed_files_v50.json)：共享numerical/core仅opt-in hook，runner/watchdog与checker可复用；V50学习决策／科学入口仍research-only，旧负结果docs保留，不升级production default。没有merge approval。按用户最新指令，最终closed／active null、无后代／锁释放、推送同一分支并核实remote／clean/upstream后暂停，本次不通知隔壁审阅窗口。
