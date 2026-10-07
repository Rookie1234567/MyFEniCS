# Review V55：共同弱平衡判别、完整相位张量快速准备与一次y向对照

## 0. 裁决：不再重复补审，也不把新的准备优化称为精度突破

**接受V56已经完成的H7全场/体吸收/独立原式和p7同模式z向增量；保留T6横向场增量FAIL、跨p约3.4%分歧、T6更严direct目标FAIL。后处理链已经闭合，下一轮不重跑H7消费、旧Q0或整套p嵌入。授权V57：一次有界、共同连续试验函数的弱平衡判别；将现有参考张量组合扩展到完整相位弱式并实际接入一个同离散基准；随后完成一个尚未做过的y向完整场对照。**

本批针对两个真实blocker：①同p的z加密稳定而跨p仍明显分歧，尚无准确的完整三维基准；②每个新几何类的高阶原张量生成反复耗时，直接阻碍48h目标。共同弱平衡是短判别，不另起诊断长线；快速准备不改变有限元空间，不能单独解决离散误差。实质交付为可实际消费的准备后端及完整物理解/比较，不能只有测试数量、示意图或下一轮建议。

```text
repository          = Rookie1234567/MyFEniCS
branch              = task42_neural_coarse_inverse
canonical_worktree  = /home/fenics/Projects/NN-Lab
review_date         = 2026-10-07
reviewed_HEAD       = feb7013db1110c9fb28b6104b235843cb7e78c49
latest_commit_UTC   = 2026-10-07T03:21:14Z
latest_response     = response_v56.md
previous_review     = review_report_v54.md
previous_review_SHA = 18e597ba6f3193f1c54a292a258d9af8891c9c84
original_base_SHA   = ccd357885f7f9be84efe3be07868cc94f13d93fc
next_batch          = V57_COMMON_WEAK_BALANCE_AND_PHASE_PREPARATION
required_response   = response_v57.md
NN_training_PC      = NOT_AUTHORIZED_THIS_BATCH
new_complete_solves = at_most_2_including_scientific_repair_replays
merge               = NOT_APPROVED
```

最终目标保持原50×25nm周期、z=−10..130nm、真空0.7nm、任意非可分三维周期材料/几何，单次必要准备至完整输出≤172800s；约2TB为整机物理内存，须保留系统余量、自身swap/OOC=0。本批仍是缩尺有限authority，不能直接外推生产资格；生产需准确空间、分布式/matrix-free原作用、流式DtN、有界粗问题及可扩展Full3D迭代。

本报告回应已关闭V56，覆盖旧“只准保存场消费及一项X对照”“不开发相位参考张量扩展”的范围限制；旧窗口、原门、FAIL及普通默认不改。当前根/目录规则、原则、task、最新结果/源码及相邻ref已读取；同blob旧合同复用，未发现新任务补充或同号review。未SSH、未消费工作站完整ignored数组、未运行新PDE；以下measured是仓库记录，不是审阅端新实测。新路线均为planned/not_run。

## 1. 综合结果与独立判断

依据：[Response V56](response_v56.md)、[专题](outcomes/saved_field_closure_target_bridge_v56.md)、[原式/物理门](outcomes/records/gate_verdict_v56.json)、[费用](outcomes/records/resource_costs_final_v56.json)、[目标情景](outcomes/records/target_gap_final_v56.json)。

| recorded measured | 实际值 | 接受范围 |
|---|---|---|
| H7保存场完成消费 | true/native3.93958617e−11；A_volume0.01813571903838；能量−1.2490e−13 | 原式、恢复、完整输出通过；H7本批未重solve |
| R7→H7，p7/828的Z2→Z4 | scattered E/H 1.9736919e−5 / 2.0035220e−5；全部增量PASS | 一个h方向稳定，不是连续真解证书 |
| R6→H7跨p | scattered E/H 0.03408908 / 0.03406000 | 约3.4%仍FAIL，不能默认高p为真解 |
| R6→T6，p6/828的X2Z2 | scattered E/H 7.4659456e−4 / 7.3508226e−4；selected6.2456152e−4 | 横向尚未过1e−4；不能说两个h方向均收敛 |
| R7→T6 | scattered E/H 0.03376614 / 0.03379747 | x细化未消除主要跨p分歧，不证明y是唯一原因 |
| T6独立原式 | true3.80416284e−11；augmented2.26331604e−10；port8.58161687e−13 | 正式1e−6 PASS；all-row direct1e−10目标仍FAIL，不增加第三次精化改判 |
| 无JIT吸收 | R7与旧定义差9.56523e−16；H7 q23/q31差7.65219e−16 | 保存场后处理已可用，不重复开发/验证 |
| 本批停止 | 全部已授权队列完成，合法结果与科学负结论保存 | 不是又因普通bug卡住；没有NN增量或原尺寸资格 |

T6总dat下界8369.14554s：raw3827.78365s、初始两套边界1276.99522s、独立body/port审核1593.52090s、symbolic+numeric+solve/精化221.27336s。raw约45.7%，后两类边界/审核约34.3%，末端因子/solve约2.64%（derived，同一非重叠账口径）。旧H7 raw12393s不能直接除以另一次T6总时间，也不能继续把原不完整H7的90.95%称为所有完整运行占比。H7两段实际dat下界合计17073.38292s，不是配平冷缓存的一次新运行。

**结论：现在没有理由优先恢复NN-PC或继续盲目Z8/p8。** 首先判别同一物理方程下的场差异，同时减少新case的必要准备。即便新准备后端很快，当前场是否准确仍必须单独通过；局部加速不承诺目标N=1节省20%或2TB可行。

### 1.1 不重复邻支

本次只读快照：`task42extra_feinn_5nm@8d617d4d206b08f38279320b67188db1b8ccd301`仍为Review29/V30学习波动greedy；NN-V3 `1f01ae46bbe21f17200350a46513ef5f33e5cf6a`仍是独立规划。工程线最新`0a442ba11a66525d5010d1b6cd6384d0de8d8eab`已发布V13 review/V14近似参考逆合同；dot `15713d3e09b63f65511c7b7f61fa043fdb23dca5`仍为已发布边界组件。读到合同不代表本机已运行或闲置。

本支不做M5/学习字典/teacher/NN-PC，不迁移工程近似逆、不重写dot流式边界。下面的参考积分组合**同分支已有**`hcurl_affine_isotropic_tensor.py`（blob `3b631a8eb8e827943954429fba2d8878ac186d40`），不是重新发明六Gram；只补它尚未包含的相位交叉/平方项并部署到本物理链。没有完全相同的已资格相位provider可直接启用；若现场发现字节/数学身份匹配的新实现，先复用并记录，不重复编码。

## 2. 固定物理与两种新完整计算

继续V56的未舍入descriptor：s=7/135，x=s×(0,16.5,25,33.5,50)，y=s×(0,6.25,12.5,18.75,25)，z=s×(−10,0,40,80,120,130)及原NOTCH盒。λ0.7nm，掠入射1°/方位5°/s/幅值1；Si n=0.999885140474+4.32477054e−6i，epsilon=n²、mu=1，air1；材料hash `55aa34e55c5e3cc35f6849eddbd3bcc72d3b694d32bc4885299ef373acd676a2`。

E=g*u，g=exp(iκ·x)，κ=(8.94046081729244,0.7821889682108057,0)。完整Cκ、trial/test、包络双周期、全部内部特解、原入射和全部828模式m±11/n±4/上下×s,p均保留。字段数值从receipt精确读取，不从本Markdown低位补造。旧R6/R7/H7/T6只读，不作为求解初值或teacher。

| 角色 | 三轴/阶数 | cells | independent FE / trace / interior | 含端口行；用途 |
|---|---|---:|---|---|
| B6 | (1,1,2)/p6 | 160 | 104832 / 32832 / 72000 | 33660；新快速provider对既有R6的同离散再现 |
| Y6 | (1,2,2)/p6 | 320 | 209664 / 65664 / 144000 | 66492；尚未独立做过的y向空间对照 |

数字为既有拓扑导出，须现场核对真实MPC；不能删行凑数。B6不是再次给旧R6求精确解以冒充新准确性，而是验证**新数值准备后端真的能供完整PDE消费**。Y6不是自动精度提升保证；它补充y方向信息，与X2的T6作对照。最多两次新完整solve，普通补审不算solve但收费。若证实公共原式错误，修复后的两个受影响父case占用全部槽，不再启动Y6；不能无限追加重算。

## 3. D：一次共同连续弱平衡判别，不能再变成长期测试线

**目的：四份场分别满足自己的FE测试空间，并不意味着它们对同一组更一般的物理试验都同样平衡。** 对冻结R6、T6、R7、H7计算同一连续泛函

```math
\rho_u(v)=\ell_M(v)-a_{\kappa,M}(u,v),\qquad
C_\kappa v=\nabla\times v+i\kappa\times v.
```

完整a包含curl、两相位交叉项、mass、全部828 DtN；ell由**同一物理入射牵引及compose_physical_rhs对应的模式项**独立积分，不能把某个p的离散b乘插值系数当通用载荷。公共试验函数直接评价，不先插回V6或V7，否则会把Galekin正交性误当跨空间正确性。

首次消费场前登记不超过24个确定性函数，参数只从几何和kappa产生，不拟合任一解：

1. 三个C1紧支撑标量窗口分别覆盖域内、NOTCH邻域/材料界面、z=0邻域；窗口使用各坐标t²(1−t)²及固定低频复指数，支撑边界加入共同积分划分。每个窗口产生三个分量方向v=phi*e_a及一个v=(grad+iκ)phi，共12个。支撑不得越过周期边后不做周期化；用域内窗口即可。对梯度函数解析使用Cκ(grad+iκ)phi=0，检验电通量弱平衡，不添加div惩罚，不要求法向E连续。
2. 12个有非零端口迹的周期函数：横向Fourier键(0,0)、(1,0)、(0,1)，x/y两个分量，线性z上/下lift各一组。完整边界与入射扣除只一次；不能只挑体内零边界函数而漏测DtN。

所有函数使用同一物理支撑和完整g*v，跨网格共同积分。记录每个复curl/mass/DtN/load值、残差real/imag、绝对值、域/材料拆分。求积q23/q31；若操作尺度差>1e−10，最多一次q39复核，仍不稳定就标该见证INCONCLUSIVE，不调门。用直接解析FLAT场作一次无PDE公式控制，并用预先固定非零扰动检查“总返回零”的反例；不重跑FLAT求解。

比较必须同时给绝对缺陷与同一参考尺度：例如以已知背景的正H(curl)范数乘该v的同范数及固定材料系数尺度作分母；四个候选分母完全一致。另列各自运算尺度只用于积分/浮点检查，不能拿变化的分母给候选排序。所有尺度定义在design中先冻结，不据结果改分母。

**D不是误差上界、全空间稳定性证书或训练loss。** 所有24个值小也不授1e−4场精度；某个值大通常是离散误差证据，不自动判为代码bug。只有独立恒等式/已知解析控制冲突且定位到实现时，才启动科学修复。共同弱缺陷的差异若能定位y/界面，辅助解释Y6；否则如实不确定。D总有载目标≤1800s、只一轮；新诊断适配受阻不取消已有可信物理路线，已知原式不可信则隔离依赖。不得只做D就交棒。

## 4. K：复用参考积分，补全相位项，而不是每个几何类重复昂贵生成

### 4.1 准确名称与适用边界

新后端名`AFFINE_PHASE_REFERENCE_TENSOR`，独立opt-in。复用同分支六Gram工厂的Basix/身份/存储基础及`phase_raw_tensor_reader`消费边界，不静默改变旧六Gram数学。适用于当前**轴对齐仿射hex、单元内常数标量epsilon/mu、实常kappa**；任意三维材料分布和真实NOTCH保持。曲单元、各向异性、PML、复kappa或单元内变材料拒绝此后端并回退已有正确核，不将其近似为适用情形。

它解决准备时间，不改变空间、材料或A的数学定义。参考张量/几何分解是已有H(curl)装配方法，非NN创新；本项目完整相位版本仍须实际资格。参考：[Rognes/Kirby/Logg原论文](https://doi.org/10.1137/08073901X)，[Basix0.10求积精确度定义](https://docs.fenicsproject.org/basix/v0.10.0/python/_autosummary/basix.quadrature.html)。不直接启用少了kappa项的旧六Gram。

### 4.2 可实施的15实矩阵形式

设J=diag(hx,hy,hz)、d=det(J)>0，参考实Nédélec基为Nhat、Chat=curlhat(Nhat)。定义b_a=h_a/d，Q_ac=([κ]_cross)_ac/h_c，则物理Cκ基的分量为b_a*Chat_a+i*sum_c Q_ac*Nhat_c。行i为test、列j为trial。预先计算：

```math
K^a_{ij}=\int\widehat C_{i,a}\widehat C_{j,a},\quad
M^{cd}_{ij}=\int\widehat N_{i,c}\widehat N_{j,d},\quad
G^{ac}_{ij}=\int\widehat C_{i,a}\widehat N_{j,c}.
```

只需3个K、6个c≤d的M（反向M为转置）、6个a≠c的G（Q_aa=0），合计15个实矩阵。完整局部矩阵为：

```math
A_e=\frac{d}{\mu_e}\sum_a\left[
 b_a^2K^a+\sum_{c,d'}Q_{ac}Q_{ad'}M^{cd'}
 +i b_a\sum_c Q_{ac}(G^{ac}-(G^{ac})^T)
\right]-d k_0^2\epsilon_e\sum_c h_c^{-2}M^{cc}.
```

不得漏两项cross、Q平方，或把test共轭施加到材料系数；不得强制整体复对称。实kappa使g*g共轭为1，体双线性式不含原点绝对相位，但RHS/边界仍按原物理坐标。几何宽度使用实际未舍入值；不是round合类。原方向变换/MPC在原外层只施加一次。先组合**完整**raw再静态凝聚，不分别凝聚K/M/cross后相加。

p6局部882维，15实数组载荷93,350,880B；p7局部1344维为216,760,320B，均为derived，不是RSS。每p最多构建一套，表/组合额外同时workspace≤2GiB，一次只输出一个raw。参考q保持原p6/q15、p7/q17，确认实际polyset精确度；没有必要新增高精度库、GPU或FFCx升级。p7只做保存类资格/成本，不新运行p7 PDE。

### 4.3 不只验证一个小矩阵，必须可进入原求解链

按实际raw manifest依次消费R6/T6的p6类、R7/H7的p7类，重复数学类只比较一次；reference construction、组合、I/O和workspace均记录。比较全矩阵Frobenius相对差≤1e−10，另以curl/phase/mass贡献和为运算尺度要求≤1e−12；最多两个固定复方向/类及两种实际局部内部恢复见证。原文件只读，新张量生产身份另建，不能伪造FFCx hash或称逐位相等。κ=0要退化到旧六Gram；非零κx/κy/κz的小代数反例检查漏cross/符号，实际部署κ不改。

只对预登记最小/最大长宽比的两个实际p6类做一次**新鲜原核与新组合**配对计时（合计目标≤900s），不重新生成所有FFCx类。参考表构建作为新case必需setup计费，不能用旧缓存读取秒数当传统控制，也不能拿p7历史时间除p6新时间。输出冷参考表+全部必需类、缓存载入、同对象旧核三种费用；没有同环境完整配对就不授端到端速度比。

通过数学门后以B6实际消费新provider；沿原raw-provider接口供完整tensor，凝聚/端口/求解器/独立原式不重写。B6与保存R6做同离散比较：完整total/scattered E/H/curl、selected、物理复通道≤1e−6，R/T/A/A_volume≤1e−8、逐mode功率≤1e−9；原方程门见§6。这个更严新backend再现门不是新的空间准确性门。若不通过，先查raw、方向、组装及舍入敏感性；不能调容差让后端合格。已返回B6只补审。

K实现/接口目标≤90min，p6优先。p7附加资格或成本配对超时可以partial，不能阻塞已合格p6的B6/Y6。p6后端不可靠则不运行B6，Y6按原正确核和完整case预算继续；有数学资格但无成本优势可以保留research-only并选原核，不无限调BLAS参数。**本批不能仅交一个15Gram微基准，而没有完成能安全执行的B6/Y6。**

## 5. Y6：实际y向完整对照及明确退出逻辑

顺序D→K→B6→Y6，阶段PASS或code commit不交棒。B6只在新后端可信时执行；若B6的backend再现通过，Y6用新后端，若失败则只允许定位后回退原核的Y6，不能把未资格后端带入新物理解。D是诊断，不要求四旧场先通过一个虚构共同弱残差门才允许Y6。

Y6从物理零初值求解，除网格y区间二分外物理不变；保持原MUMPS、精确端口坐标、最多两次既有精化。保存完整u/port/κ/mesh/MPC，释放factor/不再用矩阵，消费V56无JIT吸收/场和独立原式。新边界scatter依真实行，不能直接挪用旧native编号；原同几何数学积分可复用但逐项绑定。所有828项保留。

主比较R6→Y6，完整门沿§6；与R7及H7最多两组跨p诊断不强迫贴近高阶场。同格X2的T6可用已经保存的共同试验结果比较，不重复旧R6/T6全积分。对Y6再计算D中同一组预登记弱见证，不重新挑函数；可与场增量共用求值，但用途分列。

若Y6使分歧明显改变，只能说“y分辨参与”；若y与x/z增量都远小于跨p且共同弱见证未能解释，**收口当前固定单载波uniform hp/M试验序列**：交出场差的空间/界面分布与既有两簇解，下一步仅选择一个独立物理离散/稳定性验证，不自动Y4/p8/Z8或新模式。共同弱门小不证明绝对误差小，空间增量通过不证明无限维收敛。

若D或B6确认影响旧场的数学bug，先给原件与反例，修复并在两solve预算内重解受影响父模型；该情况下可取消Y6，不假装同时闭合全部旧case。普通writer/API错误用原合法向量继续；预算真实不够时保留最重要的实际结果和具体缺项，不能越窗追“完成”。

## 6. 原门、时间与硬件隔离

正式原true/native/增广/port各≤1e−6，内部direct目标≤1e−10单列；恢复/MPC/原作用identity≤1e−10。最多两次精化后，正式门通过但内部target失败须如T6明确分列，不能悄悄放宽内部目标。空间比较total/scattered E/H/scaled-curl、固定240点、参考面复通道≤1e−4；R/T/A/A_volume及独立能量≤1e−5；逐mode≤1e−6；共同q23/q31操作差≤1e−10。原分母、弱式、材料和参考面不改，不拟合幅相或归一化守恒。

新7h总研发窗、科学有载≤5h、最后45min收尾；实现/修复/等待/失败/交付均计入，首项实时时钟冻结，恢复上下文重读UTC/monotonic/boot_id。D≤1800s目标、K实现90min目标、必要kernel配对≤900s目标均受总窗；不要将各目标相加当无条件用满。启动B6/Y6前明确保留至少1800s用于其完整原式/场/输出及最后交付。准备端累计超期先放弃p7附加/重复计时，不删除科学审核；Y6必须使用实际缺raw成本预测，不把几小时原核当成几秒。

沿64GiB同时规划、80GiB警戒、96GiB采样整树停止、100000行上限，不继续增加配额；numeric需live RSS+2×可信INFOG16/17(decimal MB)+2GiB≤64GiB，ICNTL22=0、既有两倍后端额度。一个actor/一个factor、MPI1/math1/GPU0/Loader0、ownswap/OOC0；原宿主/PSI/cgroup余量、384GiB邻增长与空闲物理核/避忙SMT条件保持，不操作邻任务或系统ABI/BLAS/CUDA。

采样名义0.5s而V56最大9.57s是事实，不能宣称连续硬峰或把没触线当绝对安全；保留轻量整树监督/heartbeat、实际最大间隔和触线清场，重型hash/目录遍历不得进入采样热路径。只修实际监控异常，不为本轮引入必须提权的新cgroup依赖。

不按bug数量或资源episode次数机械停工。意外修复/受影响重放累计≤2h且受总窗；同根因两次无效后换诊断或本报告允许的正确回退，不能盲重跑。资源探测相隔≥120s、累计前台等待≤1800s，原Gate恢复才重入；不关闭保护或改邻核亲和性以“保持运行”。数据/ABI/原式/监督不可信必须先隔离依赖。

新ignored≤10GiB、Task042去重累计≤102GiB、free≥50GiB，既有负结果不删，必要时先依据现场实际used再准入。不例行全库pytest/CI/全仓索引/历史hash扫描；只做改动数学/接口的targeted回归、相关Ruff/compile及一次紧凑文档检查。已经完成的H7/Q0/旧D/旧mode/FLAT不重跑。

## 7. 2TB/48h裁决必须更具体

V56目标表是“保持当前极细物理单元尺度”的情景，不是accuracy-qualified最小网格：原尺寸p6/p7约16.59/26.35亿FE；p7一个完整向量约42.16GB，34个约1.43TB，还没加其他对象。268156是按现有manual截止外推的库存，不是已证实必需的传播通道数；旧32060也不能替代新角度/截断要求。二者不得写成精度下界或目标不可能证明。

本批不再重复生成两桥接网格表，直接消费V56 descriptor并增补：①新准备后端的实测冷参考构造与每类成本；②保留trace求解与恢复时向量/Krylov/局部表的实际作用域；③显式boundary-row×mode存储须改成streaming的接口；④global factor fill/迭代数仍unknown。明确全局物理尺寸增大不一定使精确几何类数同比增长，不能按cell数直接乘raw时间；也不能把类共享当作factor共享。

下一步架构选择以准确性结论和真实成本为基础：新kernel只删重复准备，不删除全局因子复杂度；最终必须将准确相位空间接到已有或后续可扩展Full3D迭代。工程近似参考逆未在该gVh/模式/RHS下资格化，不继承其步数，本批不重做。NN仍由独立支线探索，只有准确完整任务上有可替代瓶颈和全成本净收益才重新准入。

交付至少一项实际可复用能力（新准备kernel部署/同离散再现，或原后端完成Y6及可判别结果），而不是只一张预测表。若所有数值依赖真实受阻，明确partial、保存已完成数据并给唯一最小解除项；不得虚构2TB/48h结论。无需为了称“前进”贸然启动原尺寸模型。

## 8. Git、one-run与交付

读取canonical branch/HEAD/upstream/origin/worktree及活跃actor，安全fetch/ff-only同一分支，不reset/stash/clean、不改共享Git设置。只读邻支最新ref确认分工；有活动计算时不热改其受检源码。参考空间/数值核进src，复用原condensation、direct、no-JIT输出、原式与事务writer；不复制大型runner。

先实现、targeted回归、commit clean、validate，再按依赖和预算执行待创建入口：

```bash
python scripts/run_case.py input/task042_neural_coarse_inverse/v57_common_weak_balance.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v57_phase_tensor_setup.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v57_phase_tensor_baseline_p6.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v57_notch_y2z2_p6_m828.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v57_verify_cost.dat
```

D/K中不得暗藏完整solve；B6/Y6是分别明确的新物理计算，条件未准入写not_run，入口不存在前不声称可运行。相关补消费用明确父hash/子阶段，不刷新campaign。每run保存input_original.dat/resolved_config.json/run_manifest.json/run_summary、输入/物理/离散/模式/材料/source/数组hash与环境/资源。

提交计划：①窄数值核和接口回归；②D/K与B6阶段结果（actor退出后可安全提交），继续预授权Y6；③一次最终response_v57.md、outcomes/common_weak_phase_preparation_v57.md及紧凑records。至少包括共同弱分项/固定尺度、15Gram原件比较与费用、B6再现、Y6完整场/828输出、各自原门、全成本、实际峰/采样间隔、失败/修复、唯一下一pilot。旧task/review/response/raw不改；README/summary/development_progress/model_registry只追加简明入口，不再次嵌套百万字节旧JSON。

仅push `git push origin HEAD:refs/heads/task42_neural_coarse_inverse`。最终回读remote完整HEAD、clean/upstream、ledger closed/active null、后代清场及锁释放；不通知隔壁、不改dot/master、不merge、不自动开新窗口。网页视觉未取得就NOT_VERIFIED，不为网页或元数据重解科学问题。
