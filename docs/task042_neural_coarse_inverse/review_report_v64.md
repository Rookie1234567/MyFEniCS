# Review V64：消费已冻结局部网格，以完整h对照裁决精度与成本

## 0. 裁决、目标与唯一身份

**V65按`pass_with_qualifications`接受：同一P6完整方程、全场输出、系数先收缩审核和可恢复体矩阵已经实现；p5/p6完整空间增量仍FAIL，不能授连续精度、原尺寸2TB/48h或NN收益。** 本轮不重算P6、不追加p7、不再开发一个审核器。授权 **V66_FROZEN_LOCAL_H_FIELD_AND_COST**：实际求解V64已经保存、但从未求解的L4网格；取得与P6的完整交叉空间比较。只有该比较联合通过，才允许同一局部网格的一次1188模式对照。

消除的blocker是：**全域升p的实际准备和因子成本增长，场增量仅缓慢缩小；已有相容局部网格却因当时形状许可停留在未运行状态，尚无实际成本与物理场可供比较。** 先消费已有科学资产，比继续生成新标记、再交一份规划更直接。本轮不是保证局部h有效，也不把P6当真值。

```text
repository             = Rookie1234567/MyFEniCS
execution_branch       = task42_neural_coarse_inverse
canonical_worktree     = /home/fenics/Projects/NN-Lab
review_date            = 2026-10-09 Asia/Singapore
reviewed_HEAD          = 23118c3c26ecbd8eceb6902548e51c02546182b7
latest_commit_UTC      = 2026-10-09T04:38:49Z
latest_commit_local    = 2026-10-09 12:38:49 +08:00
latest_response        = response_v65.md
previous_review        = review_report_v63.md
previous_review_commit = 1cc254583559969b3fdeb9385104011d5f479a50
previous_review_sha256 = 11297b97131b61da489dc42ee27625e209452179839827004cef8324bf0279f1
original_base          = ccd357885f7f9be84efe3be07868cc94f13d93fc
campaign               = V66_FROZEN_LOCAL_H_FIELD_AND_COST
required_response      = response_v66.md
ordinary_default       = UNCHANGED
NN_training_PC         = NOT_AUTHORIZED
merge                  = NOT_APPROVED
```

最终目标仍为真空0.7nm、原50×25nm周期/z=-10..130nm、周期单胞内任意非可分三维材料/几何、complex128 Nédélec H(curl)、双Floquet、Fourier-DtN和完整E/H/衍射/吸收，必要构建至独立验收≤172800s。十进制约2e12B为整机物理内存且须留余量。本轮仍是s=7/135有限参照，不授权原尺寸全局LU。

本报告明确覆盖旧V63“不重启L4”、V62的19200tet/800000行许可和旧条件模式禁令，但**只允许下列已冻结网格及条件M**。不改旧报告、V64的NOT_RUN分类或费用。研究内存总上限不超过已授P6的192GiB规划；新增允许的行数不等于numeric内存准入。

## 1. 审阅证据与最新收益

本次读取最新response/summary、根及docs规则、仓库原则、原task身份、相关源码及成本/标记记录，核对上份review之后6次提交。上一review从挂载完整副本读取并核对原SHA256，原task与规则同blob历史正文继承；目录未检出新独立supplement或Review V64。没有SSH、工作站新PDE或完整大数组重算，不声称逐行审遍全部仓库。下表measured均来自已发布记录。

主要依据：[Response V65](response_v65.md)、[完整费用](outcomes/records/deployment_cost_v65.json)、[物理与独立消费](outcomes/records/complete_physics_v65.json)、[配对](outcomes/records/paired_comparison_v65.json)、[核资格](outcomes/records/kernel_qualification_v65.json)、[准备包](outcomes/records/body_checkpoint_v65.json)、[V64标记容量](outcomes/records/capacity_and_marking_v64.json)、[旧网格数组](outcomes/records/array_inventory_v64.json)。

| recorded measured：V65 P6 | 数值 | 边界 |
|---|---:|---|
| tet / 独立FE / native / 含端口行 | 7680 / 980352 / 1005528 / 981180 | 全部内部未知量在系统，无凝聚 |
| body K / 增广存储项 | 323539200 / 362966076 | 实际nnz，不是factor fill |
| 独立true / port | 2.32584924e-10 / 1.04881637e-15 | formal1e-6通过，direct1e-10失败 |
| R / T / A_volume | 0.0762185598 / 0.905665158 / 0.0181162824 | 828完整模式，能量差约2.54e-12 |
| PREPARE / prepared-start SOLVE | 12240.424729s / 2508.029019s | 两次完整进程，边界复用明确计费 |
| 成功链 / 加最终VERIFY | 14748.453748s / 15023.402500s | 约4.097h；不是全新JIT/边界冷启动 |
| 采样树峰 / 最大已报告gap | 88.523769GiB / 1.369836s | 非连续硬峰；观测ownswap/OOC0 |
| 独立body单列 | 49.7807044s | 系数收缩核，未读生产矩阵 |

新核24实际cell配对约1.22e-15、保存p5完整作用约6.23e-12；17.51s→0.189s仅为该局部批次计时，不授整case约93倍加速。原失败中未完成的2490s检查不能当作配平旧全域耗时。准备包已实际保存并重开；不得重做同一优化或重验全套旧Q。

**主要成本已被分清：JIT/form仅0.00373s，PETSc体装配12036.19s，约占成功链81.61%；numeric和线性求解合计约9.85%。** 不能再把3.4h称为编译，也不应只优化末端PC来解释全部48h差距。这个比例不外推原尺寸，确定性改进不归NN。

| V63 B / V65 P6 | 全域相对差 | 240点完整复向量相对差 |
|---|---:|---:|
| total E | 5.81857645e-5 | 6.26211352e-5 |
| total H / curl | 5.89962028e-5 | 1.69896141e-4 |
| scattered E | 4.05047017e-4 | 4.32840746e-4 |
| scattered H / curl | 4.10694274e-4 | 1.17438869e-3 |

原1e-4全场门仍失败；828物理复通道3.92351e-5及功率通过不能覆盖它。p4/p5到p5/p6的散射E/H增量只缩小约17.25%/19.25%（derived），不能据此拟合可靠收敛阶、指定p6真值或继续自动p7。

V65已完成队列，不是卡在writer；但forecast在PREPARE开始后才保存的provenance缺口必须保留。SOLVE实际仍持有部分K/mmap引用，后续释放修复只有定向证据，不能追改这次PDE峰。下一次真实case记录实际对象释放与RSS。

## 2. 为什么本轮消费旧L4，而不重新标记

V64从V63 A/B差分中固定theta=0.5，选1267/7680个父cell；mate-only周期闭合通过，只补2条边，没有全周期边界同步。相容细分最终25576tet、独立FE1042964、含828为1043792行；1000个NOTCH tet，父体积差2.75e-15。该空间只因旧19200/800000形状门未运行，装配规划当时为21.778GiB，**没有numeric内存实测或方法失败**。

新P6已实际求得约98万行完整解，因此旧104万行p4值得一次真实容量分析，而非继续只凭行数否决。L4行数比P6仅多6.38%，但p4单元维数84而p6为216。原始cell连接贡献代理分别为25576×84²=180464256与7680×216²=358318080，约50.36%；这是未计MPC展开/重复合并/边界/fill的derived工作量，**不预测内存减半或速度翻倍**。实际图、fill及总成本必须测量。

本轮明确不采纳“立即重新用B/P6标记另一张网格”作为主工作：既有网格未曾消费，继续规划会再次失去完整对照。旧L4在P6产生前就已冻结，因此P6可作为未参与该网格选择的交叉候选；这不是盲测、也不是reference truth。允许用新B/P6保存差分计算一次旧细化区域覆盖率，仅供解释，不能改标记、theta、网格或准入选择。

## 3. 唯一主模型与源数据边界

| planned角色 | 网格/阶数/模式 | 独立FE / 全局行数 | 数值任务 |
|---|---|---|---|
| L4F | 已冻结25576tet / p4 / 828 | 1042964 / 1043792 | 必须争取完成的完整物理零初值求解 |
| L4M，条件 | 同网格同p4 / 1188 | 1042964 / 1044152 | 仅L4F/P6联合空间检查通过后做一次模式对照 |

物理沿V65：s=7/135、真实未舍入NOTCH、lambda0.7nm、grazing1°/azimuth5°/s/幅值1、kappa=(8.94046081729244,0.7821889682108057,0)。Si n=0.999885140474+4.32477054e-6i，epsilon=n*n，mu=1；canonical材料hash为`55aa34e55c5e3cc35f6849eddbd3bcc72d3b694d32bc4885299ef373acd676a2`。材料ready，不再索要或联网替换。保留完整相位弱式、所有内部未知量、复杂周期对偶、q47生产/q63独立DtN、非零载荷及端口等价坐标。

冻结网格位于V64 array_inventory所列`mesh_mate.npz`，文件SHA256：

```text
c470274ab6c64cee0b8eef09dbcdadadfac4c6ca229d7fc2b6e608ded62f540c
```

其原`local_mesh_spec.json`指针hash为`7e3aab7b2458ec65db37762fcab0dee84ad3c4f060a46fbab3a27fbe33dcea1e`。只读原数组和父关系，在V66生成新spec和准入记录；原`admitted=false`、旧窗口和报告不改。核对geometry、dofmap、cell/regular tags、original_parent_cell及周期平移，1000个NOTCH tet不能回退旧192断言。实际新MPC再次确认1042964独立行。

不重新调用freeze_marking或refine以产生另一张网格。直接父包确实缺失/损坏时，先核对原归档指针一次；无法取得则单列ASSET_BLOCKED，不猜造旧hash、不换mesh凑完成。P6及B只读保存的已合格解用于比较，不读取其因子、不重求旧场、不用其系数作初值或构造RHS。

## 4. 最短实现：复用已有核，避免再形成一个大runner

复用`tetra_mesh_override`、`independent_tetra_reference/study`、`tetra_coefficient_action`、`tetra_body_checkpoint`和已有polynomial comparator。新scope和dat只负责本批参数/预算/父包，不复制p6_completion_study或local_h_pilot全体数值核心。公共改动留src，默认和旧source资格不静默改变。

**先修已知接线风险，不做新算法研究：** p6 `setup_identity`目前固定body_q=15，`readonly_boundaries`固定216及P6形状，不能原样给L4套壳。将新case必要identity从真实spec/element/form取得：p4 production q11、独立body q13（实际superdegree仍核对）；旧p6对应值不变。L4的新三角包必须真实构造，不能把P6数值包或K当成其准备；沿reachable_owner_support保留全部可能写入行及小非零项。

只补一次已保存p4原式向量的系数核消费，或复用同blob已有等价p4证据；不重跑旧PDE。真实L4构建后沿两固定复向量的标准UFL/独立Basix全域配对。p4、非均匀J、实际方向/MPC都进入检查，不以抽查代替原全域门。额外测试目标30分钟，适配目标90分钟；普通API修复计入总窗，数学不可信不能强行跳过。

体K使用标准UFL/FFCx，JIT、装配、CSR、周期拉回、IO分别计时。形成K后立即原子保存未缩放CSR、完整body identity、mesh/tag/P/basis/q及boundary引用；先标ASSEMBLED_NOT_YET_ORACLE_VERIFIED，后续另加作用资格。新body_q与原q不能假称相同。没有必要重新保存一套factor，禁止OOC。PREPARE不暗藏numeric。

SOLVE从合法K重开，先两列独立作用，再可靠symbolic和numeric。物理零初值，原MUMPS、原ordering/shift/端口坐标，最多两次既有精化，不扫描PC/ILU/BLR。返回立即保存完整x/u/port和真实source；独立原式后销毁factor、生产矩阵及所有prepared/mmap引用，记录实际释放，再做完整输出。引用修复不以人为预期RSS降幅作数值Gate，不能删除唯一原式能力。

## 5. 比较、判断和条件M：不用改变分母制造通过

必须输出全部total/scattered复E/H/curl、固定240点六向量、828物理复振幅/逐mode功率、R/T/A/A_volume与独立能量；不投回旧空间。formal true/native/augmented/port各≤1e-6；direct内部1e-10单列，恢复/MPC/identity≤1e-10。独立direct略超不抹掉，也不无限精化；formal安全时完成物理输出。

主比较是**P6/L4F**；辅助A/L4F检验同p4的局部h变化，B/L4F可由同一积分批次完成。旧A/B不够准确，不能要求L4F同时贴近所有旧端点才继续。只比较本批列明对象，不重算旧B/P6或所有历史hex配对。

L4子tet作为共同积分域，按保存parent关系并核对顶点包含，分别评价原场。较高p在粗网格上不等于积分网格更细。沿已有`comparison(first=P6,second=L4F)`计算一次分子；该函数原分母取second，所以保留它的L4F归一化结果，同时用保存P6范数对**同一分子**计算固定P6归一化结果。240点同样保留两端范数，物理复通道沿原mode_comparison约定。不能为了取P6分母反转网格顺序，导致把跨单元函数误当成一个单元多项式；也不能把L4每cell分子与P6不同长度的每cell分母硬拼。

空间交叉资格要求上述两个明确标记的归一化下，六场/240点各≤1e-4，原参考面复通道≤1e-4、逐mode功率≤1e-6、RTA/A_volume差及独立能量≤1e-5；保持原floor、背景、单位，不校幅相、不删点。相同实carrier可复用精确差分分子，但散射分母继续原q23/q31，至少一组保留原独立抽核。原checker接口不适合双归一化时，增加小的纯数组score记录，不另写求解器或重复全积分。

P6/L4F通过仅标BOUNDED_CROSS_SPACE_AGREEMENT，不证明二者均达到连续1e-4；P6也未曾取得连续真值资格。只有该联合检查、两场formal门及时间/资源均合格，才执行L4M：同mesh/p4、m±13/n±5/上下×s,p，1188模式，新增360模式全部实际计算。旧L4F场在新增模式上实际投影，不补零、不覆盖其原828端口；比较L4F/L4M的全场与共同物理通道，保持原门。

M可只读复用L4F的体K，但必须核对独立body fingerprint（真实mesh/tag/P/basis/p/k0/kappa/mu/epsilon/form/q），另绑定新的边界/RHS/模式和全局因子；不得跳过整个manifest比较或把旧边界当新边界。q47/63若实际不足，按旧已授权规则一次63/79，保存真实q，不删倏逝通道。

L4F与P6不一致时保存区域/分量和原分子，不执行M、不自动p7或重标记。若与P6更一致但代价更大，明确没有效率优势；若图/资源先否决，记录实际证据而非宣称局部方法不可能。本批不新建第三个物理方案。

## 6. 时间、资源与不中断执行

新12h总研发窗口（43200s），科学有载≤10h，最后1h交付；全部实现/失败/修复/等待/IO计费，不刷新V64/V65。L4F准备、求解、审核、输出与恢复的累计上限8h；条件M累计≤3h，均同时受总窗约束。forecast必须在昂贵准备前记录，分开预测与实测；参考旧p4装配和实际cell图，不把P6的JIT命中当免费矩阵。numeric前真实剩余必须容纳预计numeric及至少4500s原式/输出/比较/收尾，预算紧先取消M和可选B比较。

| V66 role | planning / warning / sampled stop | 形状许可 |
|---|---|---|
| preflight与无factor消费者 | 64 / 80 / 96GiB | 不暗藏全域solve |
| 唯一L4F及条件L4M | 192 / 224 / 256GiB | 仅冻结25576tet；系统行≤1050000 |

这是对旧L4许可的明确提升，但不高于已有P6研究内存上限。装配规划21.778GiB只是旧record，不是factor准入。numeric仍为live树RSS+2×可靠INFOG16/17(decimal MB)+2GiB≤192GiB；实际fill未测不预测通过，INFOG9未知负编码不能硬当项数。每层dat/plan/resolved/Journal/launcher/watchdog/assembly/factor/collector必须使用同一profile，不能遗留800000/1000000门，也不能仅改admitted=True。

MPI1/math1/CPU1、GPU0/Loader0、complex128及原int64 ABI、ownswap/OOC0、ICNTL22=0、原PSI/cgroup/宿主/384GiB邻增长及空闲物理核避忙SMT条件保持。一个自身heavy actor/一个factor，不改邻任务、系统BLAS/CUDA/swap或共享Git。不以标称2TB绕过现场余量，不OOM探路。额外workspace≤2GiB；K/PETSc副本、oracle、恢复和引用同时计入。

新增ignored≤64GiB、Task去重累计≤408GiB、free≥50GiB、证据余量≥512MiB。求解前核算K、场、独立向量与原子双份；只检查本批和直接父包，旧失败不删除。K/完整解合法返回后只补消费，JSON/路径/collector/README错误不得触发重新factor或装配。

通常L4F一次numeric，M一次；**总计最多两次新全域numeric/solve attempts，包含科学修复或无返回中断后的重试**。科学修复占第二槽即取消M。每个体K主构建最多一次；数学未变的中断从checkpoint重开，不重支付准备。普通bug不按数量停工，累计修复/重放≤2.5h；同根因两次无效换诊断或正确同数学实现，不盲重试。真实原式/身份/ABI/安全错误先隔离，科学FAIL不是软件bug。

不例行full pytest/CI、全仓索引、历史hash扫描、旧FLAT/Q0/15表/慢oracle/P6重算或第二轮网格标记。只测改动的p4参数化、mesh加载/父映射、容量传播、checkpoint及比较计分；同blob健康证据复用。紧凑文档检查做一次，不以网页渲染阻止已许可科学队列；未取得视觉证据如实NOT_VERIFIED。

## 7. 成本裁决、目标连接与邻支去重

L4F的单次必要链从启动到mesh/MPC、新body/triangle、factor/solve、全部物理输出/原式/IO/清场计费；PREPARE与SOLVE拆进程就分别给出及求和，不伪造一次连续冷运行。比较、选区诊断和文档单列研究费用。父A/B生成、V64标记/闭合、旧P6失败及本次新费用在项目账只收费一次；标记不是免费oracle。V65成功链复用了边界，L4F新生成边界，要并列说明，不能直接把两个未经配平数相除授生产加速比。

交付至少一张实际精度/费用表：A、B、P6、L4F及条件M的空间、nnz、可靠factor统计、T_N1/恢复链、采样峰/gap与全部场资格。L4相对P6只有行数相近，若同一有限响应内更便宜，才是局部分辨的有限工程信号；否则收口这份配置。不用通道稳定替代完整场，也不以未过门的一份解定义精度真值。

本轮没有运行原尺寸，不能把s=7/135网格线性外推为目标需求。下一生产主线仍须在准确空间上采用局部消元、凝聚trace迭代、分布式matrix-free、流式DtN、有界粗问题和分块恢复。审核向量核不是已经合格的可扩展PC；全矩阵checkpoint只属有限参照，不能推为目标长期存储策略。48h包含必要构建和验收，2TB是整机且保留余量。提交一个带物理/空间/原作用契约的候选参照入口即可，不复制旧十亿DOF情景表或启动另一分支集成。

邻支本次只读核对：Task42extra `3733eb71183da58317f1fb471ee8fc08c5700f42`为V34复波矢神经表示合同；工程 `f23d907bbb60249cbd2844921ca86cfd43f84658`处于V19精确route/零端口RHS与生命周期接线；dot `15713d3e09b63f65511c7b7f61fa043fdb23dca5`、NN-V3 `1f01ae46bbe21f17200350a46513ef5f33e5cf6a`仅核对ref。不得复制它们的训练/M5/teacher、参考PC、通用CSR或流式模式研究，不推断未推送本机状态，不通知或修改邻工作树。

## 8. 提交计划与正式入口

C1：新薄scope、冻结mesh引用、p4参数化身份与192GiB/1050000行许可传播；C2：复用prepare/solve与保存消费者、双归一化纯数组评分和条件M。公共小改动进src，相关targeted回归、commit clean、validate后才正式运行；活动actor的受检HEAD不热改。

以下入口本轮待创建，均经既有资格activation及监督，每dat一项明确计算，共享同一预算：

```bash
python scripts/run_case.py input/task042_neural_coarse_inverse/v66_frozen_local_mesh_preflight.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v66_local_p4_prepare.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v66_local_p4_solve_complete.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v66_local_p4_m1188.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v66_compare_verify_cost.dat
```

preflight/PREPARE/VERIFY不暗藏numeric；M没有联合准入不运行。L4F必要比较完成后原子记录分流，再条件M，最终只消费未完成项，不冻结队列过早锁死已授权M。

交付`response_v66.md`、`outcomes/frozen_local_h_field_cost_v66.md`和紧凑records：冻结mesh/来源/准入、K与完整场、原式和所有物理量、P6/L4F双分母与辅助h差、条件M决定、实际图/fill/费用/RSS/gap、修复/未运行原因及唯一下一pilot。旧task/review/response/raw不改，summary/README/development_progress/development_model_registry追加简明结果；重型数组留ignored，Git只交本批必要身份与父hash。

```bash
git push origin HEAD:refs/heads/task42_neural_coarse_inverse
```

最终核对remote完整SHA/upstream/clean、closed/active null、后代清场与锁释放，交付用户后暂停；不merge、不改master或邻支、不自动开新窗口。报告发布和下载必须核对同一Git blob，不能再出现同编号两份不同合同。

## 方法依据与审阅端边界

[Nédélec第一族定义](https://defelement.org/elements/nedelec1.html)的tet维数采用subdegree k；本项目Basix p=k+1，局部维数为p(p+2)(p+3)/2，因此p4为84、p6为216。[DOLFINx 0.10 mesh接口](https://docs.fenicsproject.org/dolfinx/v0.10.0.post3/python/generated/dolfinx.mesh.html)支持由真实拓扑/坐标重建及父标签关系；本轮消费已保存相容网格，不重新细化、不升级ABI。以上尺寸和作用量不是收敛定理。

审阅端进行了源码/记录交叉核对、维数与费用比例计算、文档结构与文件身份检查；没有运行新FEniCS/PDE、工作站大数组或新性能测试。所有L4F/条件M准确性和资源结论仍须由V66实测取得。GitHub页面视觉未取得时保持NOT_VERIFIED。
