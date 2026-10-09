# Review V65：局部p5与独立模式对照，分别裁决空间精度和边界截断

## 0. 正式裁决与唯一身份

**V66按`pass_with_qualifications`接受：冻结L4网格的完整方程、全场、独立审核和费用链已完成；不授完整空间准确性、同精度加速、NN收益或原尺寸2TB/48h资格。** 普通接线已完成，本轮不是补跑V66。授权 **V67_LOCAL_P5_AND_INDEPENDENT_DTN_CHECK**：在同一冻结局部网格上完成一次p5/828完整场，并独立完成一次p4/1188完整模式对照。后者不再以前者或旧P6/L4一致为前提。

要消除的blocker有两个：局部网格是否仍受p4表示限制；当前四面体体系是否受828模式截断影响。过去一直要求空间先通过才检查模式，会让两个误差源长期混在一起。此次只补两项有判别力的完整计算，不再重标记、全域p7、换载波、换单元家族或训练网络。

```text
repository             = Rookie1234567/MyFEniCS
execution_branch       = task42_neural_coarse_inverse
canonical_worktree     = /home/fenics/Projects/NN-Lab
review_date            = 2026-10-09 Asia/Singapore
reviewed_HEAD          = d1939336d5e8ab0c623a4786cdf5616d41443d0d
latest_commit_UTC      = 2026-10-09T08:22:02Z
latest_commit_local    = 2026-10-09 16:22:02 +08:00
latest_response        = response_v66.md
previous_review        = review_report_v64.md
previous_review_commit = 5a6689d321b74233b104c8b0ce5bab7d7bd8e39e
previous_review_blob   = 798dcc32b4496e646809554c34e9b90b0449390e
original_base          = ccd357885f7f9be84efe3be07868cc94f13d93fc
campaign               = V67_LOCAL_P5_AND_INDEPENDENT_DTN_CHECK
required_response      = response_v67.md
ordinary_default       = UNCHANGED
NN_training_PC         = NOT_AUTHORIZED
merge                  = NOT_APPROVED
```

目标仍为真空0.7nm、原50×25nm周期/z=-10..130nm内任意非可分三维材料/几何、complex128 Nédélec H(curl)、双Floquet、Fourier-DtN、完整复E/H/衍射/R/T/A/独立体吸收；必要构建至输出和验收不超过172800s。十进制约2e12B为整机内存，须留系统余量。本批s=7/135缩尺问题只是有限参照，不授权原尺寸全局LU。

本报告明确覆盖V64只准p4/1050000行、以及空间比较PASS才准模式计算的本批限制；仅L5有限参照新增256GiB规划许可。旧V66条件M的NOT_RUN正确且不可改写。新实验有独立输入、窗口、费用与身份，不复活旧账。

## 1. 已审依据、阶段进展与当前边界

实际读取冻结HEAD的根/文档规则、仓库原则、原task身份、最新response/summary、容量、最终资源、来源与相关源码；核对上个review以来3次提交。上一完整review由挂载副本读取并核对已入库blob；目录未检出新的独立supplement或Review V65。没有SSH、工作站新PDE或大型场数组重演；measured均指仓库已交付记录，不是审阅端复测。

核心证据：[Response V66](response_v66.md)、[容量/生命周期](outcomes/records/capacity_and_lifetimes_v66.json)、[最终资源](outcomes/records/resource_costs_final_v66.json)、[身份](outcomes/records/report_identity_v66.json)、[完整比较](outcomes/records/paired_comparison_v66.json)、[同分母checker](outcomes/records/paired_saved_checks_v66.json)、[模型费用](outcomes/records/model_cost_comparison_v66.json)。全部正式V66阶段source=`d87a08478db6a6ccaf665eda3132818533e291f3`，末次文档HEAD不是运行source。

这条线最初研究神经辅助粗逆，随后转向完整方程和物理准确性：早期神经修正/表示/编码未形成合格净收益；V51固定解析相位取得FLAT解析E/H约4e-8误差；V60局部装配在同空间再现下显著减少存储；V62建立标准完整四面体独立参照；V65把慢原式审核改为系数收缩并保存昂贵K；V66终于消费冻结局部网格。上述成果分别属于表示、装配、审核、恢复和有限参照，不能归到NN，也不能将旧不同模型资格合成一个目标PASS。历史证据分别见response_v48/v51/v60/v62/v65.md及原summary，旧失败保留。

| recorded measured | V65 P6 | V66 L4F |
|---|---:|---:|
| tetra / p | 7680 / 6 | 25576 / 4 |
| 独立FE / 含828行 | 980352 / 981180 | 1042964 / 1043792 |
| 实际增广nnz | 362966076 | 165965686 |
| 独立true/native | 2.32584924e-10 | 2.27244591e-10 |
| 必要成功链/s | 14748.453748 | 4843.293469 |
| sampled树峰/GiB | 88.523769 | 54.461544 |
| 全域散射E/H相对增量，P6分母 | — | 3.40423976e-4 / 3.49950066e-4 |
| 240点散射E/H完整复向量增量，P6分母 | — | 7.56043124e-4 / 1.86103089e-3 |

记录相除得到：L4F比P6多6.38%行，少54.28%矩阵存储项，成功链短67.16%，采样峰低38.48%。**这是不同离散、未满足同完整精度且缓存前提不同的观察，不是同精度生产加速/内存比。** 父A/B、标记、相容闭合和旧失败费用不免费；不把这些比值标为NN收益。

L4F R/T/A_volume=0.0762184733/0.905665213/0.0181163135，能量差约1.73e-12；formal1e-6通过、direct1e-10失败。P6/L4物理复模式差7.2583e-5、逐mode功率差2.0687e-7通过，但六场/240点失败。两种固定分母给出同一失败，不是换分母可解决的问题。辅助A/L4同p4场增量约6.8e-4也失败。不要以total范数、RTA稳定或守恒覆盖散射场。

L4F实际PREPARE=2784.742089s，SOLVE=2058.551381s；其中体装配2582.44659s、numeric+solve=949.9477045s、体积分852.404437s，分别约占成功链53.32%、19.61%、17.60%。JIT/form仅0.0044s，不再将装配称为编译。最大观测采样gap=2.047918574s，峰58477637632B，观测ownswap/OOC0，不宣称连续硬峰或绝对零干扰。INFOG9=2143620280为本次正的reported项数，历史负编码继续unknown。

## 2. 下一步的取舍：一次升阶，但不再把模式检查锁在空间门后

L4F与P6不一致有空间和边界两类未排除因素。原式很小证明各自离散方程求解完成，不证明空间或DtN截断充分。四面体从V62起尚未实际完成1188模式全场；旧hex的模式证据不能直接移植。有限元误差与DtN截断误差应分别控制，文献也明确区分这两项，不能据此搬用其定理作为本模型资格。

| 本批角色 | 冻结改变 | 不改变 | 直接目的 |
|---|---|---|---|
| L5 | 同25576tet升p4→p5，828模式 | 几何、材料、载波、入射与模式库存 | 检验局部网格上的阶数敏感性 |
| M4 | 已有L4F同网格/p4，828→1188模式 | 体离散及体K | 单独检验该空间的边界截断 |

L5不要求先接近旧场才继续；M4也不要求L5成功或L4/P6一致才运行。两条共用可靠物理基础，但数值准入与结果独立。M4是新合同下的独立实验，不是把旧条件M的失败改成通过。

**不能要求L5同时距L4F和P6都小于1e-4。** 两旧场在同范数下相差约3.5e-4，三角不等式已排除它们都贴近同一新场的这一要求。L4/L5用于记录同网格p增量，P6/L5用于交叉空间比较，各自判定，不设置追溯修好旧粗场的总门。

本批最多两次新的全域numeric/solve attempts，包含科学修复。没有第三张网格、局部p6、全域p7、第二次标记、1188以上模式或新载波。若L5容量不准入，优先仍完成可行M4，不为凑结果改变问题。若两项均不解释主要差异，收口这一固定实验，不自动续扫p/h/M。

## 3. 冻结物理和实际规模

原样消费V64/V66的mesh_mate.npz，SHA256=`c470274ab6c64cee0b8eef09dbcdadadfac4c6ca229d7fc2b6e608ded62f540c`。25576tet、1000个NOTCH tet、原parent映射和未舍入坐标保留；不调用refine或freeze_marking。几何文件只作为物理资产，p4空间身份不能冒充p5身份。

lambda=0.7nm、grazing1°/azimuth5°/s/幅值1，kappa=(8.94046081729244,0.7821889682108057,0)。Si n=0.999885140474+4.32477054e-6i，epsilon=n*n，mu=1；canonical材料SHA256=`55aa34e55c5e3cc35f6849eddbd3bcc72d3b694d32bc4885299ef373acd676a2`。材料ready，不再索要或联网替换。E=exp(i*kappa·x)u，完整Ckappa、trial/test交叉项、物理RHS、双周期与全部内部未知量保留。

L5的Basix p5局部维数140，production body q13、独立body q15，实际superdegree/变换核对。独立全局数由实际周期实体/MPC计数；不要用p4数乘一个经验系数。对于同一匹配周期tetra拓扑，令Ne/Nf/Nc为独立边、面、单元数：

```math
N_p=pN_e+p(p-1)N_f+\frac{p(p-1)(p-2)}2N_c.
```

已知N4=1042964、Nc=25576，可得Ne+3Nf=184013，N5=1687345+5Nf。由于Ne非负，推导N5+828<2000000。它是该拓扑假设下的上界，不是实测编号、nnz或RSS。新spec记录实际Ne/Nf、native、independent、rows和MPC rank；异常不静默放大形状门。

M4独立FE仍1042964，1188端口后1044152行；m=-13..13、n=-5..5、上下侧×s/p，原828键全部保留。新增360模式的物理波矢、出射beta、导纳、参考面及非零载荷按原定义生成，不改物理入射cfg来迁就库存。

## 4. 最短实现与计算顺序

只作薄V67 scope/配置扩展，复用`frozen_local_h_study`、参数化prepare、`tetra_body_checkpoint`、`CoefficientFullAction`及标准完整UFL/FFCx管线。不静态凝聚、不启用旧hex15表、不改求解器，不重新开发通用runner或CSR系统。

先消除已读源码中的p4硬接线：preflight中的(84,4)、q11/q13、action_factory固定q13，以及旧1050000行都不能漏到L5；从真实spec统一取得。V65已经有p5系数核完整作用资格，blob和依赖不变就复用，不再求旧p5或重跑全套局部24cell测试。新L5仍做两列完整生产/独立作用配对，不以旧证据替代新mesh/MPC的全域检查。

PREFLIGHT只做资产、实际空间、预算、最小接线资格及forecast。L5先新构建q47/q63边界和p5体K；不能重用p4/P6矩阵或边界数值包。昂贵K形成后立刻原子保存未缩放CSR、mesh/tag/P/basis/p/q/kappa/source；先标ASSEMBLED_NOT_YET_ORACLE_VERIFIED，独立资格另存。科学算法未变的中断必须重载K，不重装配。

L5 SOLVE从checkpoint读取，完成两列作用、可靠symbolic、numeric、物理零初值求解、立即保存完整x/u/port，最多两次既有精化。独立原式后释放factor、生产矩阵和prepared/mmap所有引用再输出。所有内部场保留；因子不保存，不用OOC。

M4优先只读复用V66的p4体K及独立body fingerprint，不能依赖本轮L5 PREPARE指针。明确指定producer_role/parent，而非让旧prepared_provider拿错最新K。新1188边界/RHS/全局因子独立生成，不能复用旧828因子。body fingerprint相同不代表边界hash相同；由已存在的allow_mode_change窄规则核验，不跳过整个manifest。旧p4 K确实不可用则记ASSET_BLOCKED，不默认重建以消耗主解预算。

新边界q47/q63各构造一次，作用不足才按既有规则一次63/79并冻结真实q；不得删倏逝通道。用保存L4F场实际投影新增360模式，不能补零、用功率反推相位或覆盖旧candidate端口。所有成功进程均保存完整输出后，再交由消费者评分。

建议顺序：PREFLIGHT→L5 PREPARE→L5 SOLVE与必要输出→M4→唯一增量VERIFY。L5被真实容量或已定位局部接口问题阻塞，允许先完成M4；共享数学/身份不可信时先隔离两者。比较FAIL不是取消另一独立case的条件。

## 5. 完整判定，不增加重复物理检查

formal true/native/augmented/port各≤1e-6；独立direct1e-10单列；恢复/MPC/identity≤1e-10。原生产与独立残差不能互替，略超direct子门不增加第三次精化。完整total/scattered复E/H/curl、原240点六向量、所有物理复模式/逐mode功率、R/T/A/A_volume和能量都输出，原单位/floor不变。

主比较只做L4F/L5、P6/L5、L4F/M4；可选同p5的B/L5复用同一积分批次，预算不足明确not_run。前两项共同积分网格用冻结L4子tet，不将P6粗单元作为跨不连续子域的单多项式积分域。复用V66的一次分子/两固定分母评分，双方全域与240点门各1e-4；不投影、不校幅相、不删评分点，也不重复完整积分来换分母。

物理参考面复通道≤1e-4，逐mode功率≤1e-6，R/T/A/A_volume差及每份独立能量≤1e-5。M比较将保存L4场在新360模式上真实投影，与M4的1188完整物理向量配对，并另存公共828与新增子集的绝对量/范数。近零子集相对差可能很大，不能直接拿它代替原完整向量门，也不能隐藏绝对差。旧辅助倏逝坐标的raw相对差不是物理振幅误差。

资格必须分四栏：离散方程求解；有限空间增量；有限模式增量；连续/目标资格。任何一对相近只授对应的有限证据。L4F/M4通过不能自动证明L5在828模式上充分；L5/P6相近也不证明二者均达连续1e-4。没有新的收敛证明就保留unknown。

结果解释预先固定：L5改变大说明p4空间有敏感性，不自动证明更高阶更准；M4改变大说明该空间的828截断不可忽略；两者都小而跨空间仍大则停止原样升p/M，提交唯一具体离散/误差定位问题，不能开启无预算新扫描。不要因旧L4/P6不同，要求新解同时追溯满足互相不相容的旧门。

## 6. 资源、完整预算与普通bug的继续路径

本批14h总研发窗口、科学有载≤11h、最后1h交付。L5的准备/检查/求解/输出/恢复合计≤10h；M4≤3h，均同时服从总窗。首次真实UTC/monotonic/boot冻结，失败/实现/等待/IO计费，不刷新V66。forecast在昂贵准备前保存，依据实际p5本地维数、p4局部网格实测和已有p5成本给出区间，不承诺线性外推。numeric前必须容纳预计numeric加至少4500s验收/写出余量；资源blocked时保存K，不为花完预算硬factor。

| 唯一role | planning / warning / sampled tree stop | 形状许可 |
|---|---|---|
| preflight、无factor消费者 | 64 / 80 / 96GiB | 不暗藏求解 |
| L5有限准确性参照 | 256 / 320 / 384GiB | 同25576tet/p5；含端口≤2000000行 |
| M4有限模式对照 | 192 / 224 / 256GiB | 同25576tet/p4；1044152行 |

L5增加到256GiB是本报告对唯一有限case的明确许可，不是放宽全局默认或预测实际需要256GiB。numeric仍要求live树RSS+2×可靠INFOG16/17(decimal MB)+2GiB≤该role规划；实际fill未测，不能按行数比例批准，INFOG9负编码保留unknown。profile必须贯通dat/plan/resolved/Journal/launcher/watchdog/assembly/factor/collector；单改admitted或行门无效。

维持原complex128/int64 ABI、MPI1/math1/CPU1/GPU0/Loader0、ownswap/OOC0、ICNTL22=0、原PSI/cgroup/宿主保留及384GiB邻增长余量、合格物理核避忙SMT。一个自身heavy actor/一个global factor；不得改邻任务、系统、BLAS/CUDA/swap、共享Git或关闭监督。不用标称2TB替代现场余量，不靠OOM试容量。额外表workspace≤2GiB，K/PETSc/边界/原式/恢复/IO副本同时入账。

新增ignored≤72GiB、Task去重总量≤480GiB、free≥50GiB、证据余量≥512MiB。这是上限，不要求复制这么多；只保存新K/场/新边界与简短父引用。原子写入双份空间在solve前核算，旧失败不删除。本批最多两次numeric/完整solve attempts，科学修复占第二槽则取消尚未运行的另一case，不自动第三次。

普通API/shape/dtype/路径/cache/writer错误，同轮定位→最小修复→受影响targeted回归→继续。不按bug数停；同根因两次无效换诊断或原正确同数学路径，累计修复/重放≤2.5h。已返回合法场不因JSON/checker/文档再次factor；只有确认数学改变才占科学修复槽。新case特有接口不阻止另一条健康路径，公共原式/ABI/身份/监督不可信必须先隔离。

不例行full pytest/CI、历史hash扫描、全仓索引、旧FLAT/P6/L4重求、慢oracle、旧24弱试验或重新标记。只验证p5参数化、两种独立parent、1188完整输出、预算与保存链；健康同blob数学资格复用。文档检查一次，不把网页视觉作为再次运行PDE的条件，未取得视觉如实NOT_VERIFIED。

## 7. 让本轮结果接向2TB/48h，而不是再累计一个版本号

部署费用从case启动到必要mesh/MPC、body/JIT/边界、factor/solve、原式、全部场/240点/模式/吸收、IO与清场。PREPARE/SOLVE拆进程则分别列出并求和；M4复用p4 K的prepared-start、其上游生成费和新边界费分别保留，研究比较另列且不重复加历史。未获得同精度配平控制，不授生产加速比。

交付一个只读`discrete_reference_contract_v67.json`及简短说明，指向现有/新场、输入/材料/mesh/MPC/mode/source、完整原作用接口、费用和失败项；不复制全套大数组，不向邻支发命令或集成。明确`discrete_equation_qualified=true`与`continuum_accuracy_qualified=false/unknown`可以并存。求解器可在完全相同离散问题上检验代数正确性，但不能据此宣称物理准确性；不必把所有可扩展架构研究无限锁在一个连续精度门之后。

本批结束不给“自动再升一阶”的建议。若证据足以选有限基准，说明它只服务哪类比较；若仍不稳定，限定一个下一blocker和可证伪方案。以误差—资源表、保存可用参照和明确否决替代报告数量。48h并非仅factor/solve时间；2TB需包括所有MPI复制、Krylov、DtN、恢复及系统余量。

生产必要方向保持：高阶准确表示、局部消元和凝聚trace空间上的分布式迭代、matrix-free全局作用、流式DtN、有界粗问题、按块恢复。当前完整tetra全局LU只是有限authority，禁止直接外推。新p5参照不是新的可扩展PC；NN何时再入取决于真实瓶颈与完整净收益，不因分支名带neural而强行训练。

邻支只读快照：Task42extra `936fdcff435a772619ae720119e2a22de0dabccd`已交付V34复波矢学习，M5联合门及NN增量仍未达；工程`71042327e5f3a77cd39a1be7b5dfa46afe52db6b`最新为V19 Ny8保存见证接线修复，不能从旧README或未推送状态推断新大算例通过；dot `15713d3e09b63f65511c7b7f61fa043fdb23dca5`、NN-V3 `1f01ae46bbe21f17200350a46513ef5f33e5cf6a`仅核对ref。本支不复制其NN/M5/teacher、参考PC、通用CSR或流式模式研究，不通知/修改邻工作树。

## 8. 提交与正式入口

先最小公共参数化和薄scope，targeted回归、commit clean、validate，再正式PDE。当前已有`prepared_provider`读取scope.stage('PREPARE')，M4必须明确指向V66 p4准备而不是本批p5准备；`CoefficientFullAction` q从实际degree取得。活跃actor期间不得修改其受检HEAD。

以下为本轮待创建one-run入口，不提前宣称可运行：

```bash
python scripts/run_case.py input/task042_neural_coarse_inverse/v67_local_p5_mode_preflight.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v67_local_p5_prepare.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v67_local_p5_solve_complete.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v67_local_p4_m1188.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v67_compare_verify_cost.dat
```

preflight/PREPARE/VERIFY不暗藏numeric。M4准入是本报告的新独立授权，不读旧space_gate false后直接返回。每dat绑定真实input_original/resolved/manifest/input_sha/physical_sha/source_sha/环境/MPI/资源/artifact身份。

交付`response_v67.md`、`outcomes/local_p5_independent_dtn_v67.md`、紧凑records与参照契约：实际L5规模/图/fill/全场，M4全mode投影及场，三项比较原分子与分母，原式/精度/费用分栏，全部source/峰/gap/失败与唯一下一步。旧task/review/response/raw不改，summary/README/两总账短追加，不复制数千条已存在父manifest作为新科学数据。

```bash
git push origin HEAD:refs/heads/task42_neural_coarse_inverse
```

最终核对完整remote SHA/upstream/clean、closed/active null、后代清场及锁释放后交付用户暂停。不merge、不改master/邻支、不自动开新窗口。报告发布与下载核对同一blob，禁止再产生同编号的两个不同执行版本。

## 参考与审阅端边界

[双周期Maxwell有限元/DtN误差研究](https://arxiv.org/abs/1811.12449)将空间近似与边界截断分别控制；本报告只使用这一问题分解，不声称实现其完整后验估计。[Nédélec第一族定义](https://defelement.org/elements/nedelec1.html)采用subdegree k，本项目Basix p=k+1，tet局部维数p(p+2)(p+3)/2。尺寸上界与预算不是收敛定理。

审阅端只做远程文档/源码核对、比例与实体维数代数、文档结构和身份检查，没有执行新FEniCS/PDE、工作站大数组或性能测试；新L5/M4结果必须由执行端取得。GitHub页面视觉没有证据时保持NOT_VERIFIED。
