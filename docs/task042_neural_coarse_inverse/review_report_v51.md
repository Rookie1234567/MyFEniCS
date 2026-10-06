# Review V51：补齐共同加密解，纠正交叉准入逻辑，推进0.7 nm准确三维场

## 0. 决定与身份

**接受V52的H/P完整方程、恢复、场比较和资源停止证据；原尺寸目标仍未通过。授权V53继续同一确定性相位有限元主线，优先取得缺失的Z4/p6完整解，再在已有Z2/p6之上作一次Z2/p7独立p增量。明确扩大本批有限authority的资源配额，减少重复准备和重复场求值，不以普通bug或旧16GiB授权界中断整个工作包。**

本批消除的blocker是：缺口的准确性尚未闭合，且共同加密算例在已经花费昂贵准备后被研究配额拦住。不能把它改叫NN问题，也不能把更小代数残差当作场准确性。本报告同时纠正上一份review的一个数学上不可能满足的交叉准入条件，见§2；不是降低任何数值门限。

```text
repository              = Rookie1234567/MyFEniCS
branch                  = task42_neural_coarse_inverse
worktree                = /home/fenics/Projects/NN-Lab
review_date             = 2026-10-06
reviewed_HEAD           = 287f00ee1d05abb94933c1f7e5613247bbfc62b4
reviewed_commit_UTC     = 2026-10-05T15:54:13Z
latest_response         = response_v52.md
previous_review         = review_report_v50.md
previous_review_commit = f89b4585c1e19e6e08f051dcbf65ec7643302ea8
original_base_SHA       = ccd357885f7f9be84efe3be07868cc94f13d93fc
sibling_branch          = task42extra_feinn_5nm
sibling_readonly_HEAD   = 8d617d4d206b08f38279320b67188db1b8ccd301
sibling_contract        = Review V29 / V30_ADAPTIVE_WAVE_NEURAL_GALERKIN
next_batch              = V53_PHASE_HP_COMPLETION_AND_FORWARD_ACCURACY
required_response       = response_v53.md
NN_training_and_NN_PC   = NOT_AUTHORIZED_THIS_BATCH
merge                   = NOT_APPROVED
```

用户要求沿主线连续推进、减少无用测试并同轮修bug。本报告据此明确覆盖V52的16GiB规划/24GiB采样停止上限、禁止新增p7及原交叉准入逻辑；仅限下列案例和资源，不改旧结果、其他任务或ordinary default。V52已closed，不重开其窗口。同一工作树只有一个执行者和一个数值actor；只由用户转交，不自动通知隔壁。

最终目标仍为原50×25nm周期、z=−10..130nm、17×25×120nm Si结构、λ0.7nm，并保留任意非可分三维能力；单次完整流程≤172800s、约2TB整机保留余量、ownswap/OOC=0。有限准确基准不等于目标尺寸或生产可扩展性。生产长期方向仍为准确高阶空间、分布式/matrix-free原作用、streaming DtN及有界可扩展迭代；本批全局直接因子只作有限authority。

本次审阅实际读取远程ref、最新目录/summary/review/response、V52源代码与7个后续提交的差异、运行/容量/费用和场比较记录，并核对隔壁ref未变。同blob的既有task、根/目录规则与补充限制继续复用，没有新增补充任务书。未SSH工作站、未解码全部ignored科学数组、未重跑FE或测现场资源；不把记录中的measured当成本次重新实测。以下新工作为planned/not_run。

## 1. V52裁决：区分科学负结果、资源停止和软件错误

依据：[Response V52](response_v52.md)、[完整结果](outcomes/phase_notch_hp_accuracy_v52.md)、[科学门](outcomes/records/hp_accuracy_checks_v52.json)、[运行](outcomes/records/run_index_v52.json)、[费用](outcomes/records/resource_costs_final_v52.json)。

| 对象；数据为recorded measured | 实际结果 | 裁决 |
|---|---|---|
| H：Z4/p5，320cell，44532凝聚行 | q63原true 9.44811e-12；dat下界2286.973s；采样峰5.72674GiB | 方程/恢复通过，不是准确连续解 |
| P：Z2/p6，160cell，33364凝聚行 | q63原true 1.15911e-11；dat下界5904.757s；采样峰6.98644GiB | 方程/恢复通过，优先保留的新高阶比较基点 |
| 旧B0→H | scattered E/H增量1.27963e-4/1.38358e-4；selected最坏1.52955e-4 | 仍超过1e-4；不能用total或功率通过替代 |
| H→P | scattered E/H增量6.74525e-4/7.02539e-4 | 两个端点尚不一致；不等于已知谁更接近连续真解 |
| HP：Z4/p6，320cell，65044行 | 准备+symbolic4746.490s；预计21.218934GiB超过16GiB；numeric/solve均0 | CAPACITY_BLOCKED，不是求解不收敛、OOM或bug |
| T/M | 时间准入不足 / 无准确性锚点 | not_run，不记数值失败 |

H/P全532功率与原增广/端口/内部恢复证据保留。元数据括号、资源标签问题已同轮修复，没有因它们重解H/P；不能把本轮未通过都归于bug。隔壁仍研究5nm起步的学习波动greedy；本支不做M5、神经字典、teacher、NN训练或NN-PC，不迁移新源码，不操作其工作树。

V52的P费用中局部tensor/凝聚约3027.56s、场配对约2406.24s，而全局symbolic+numeric约50.06s。HP准备约4463.41s，且没有保存完整可再消费tensor/Schur包。**下一批不能宣称免费续上旧factor，不能重复H/P来换新标签，也不应把主要投入转向末端线性求解器。**

## 2. 必须纠正的交叉门：新解不能让两个相互不一致的旧解都合格

旧规则要求H→HP与P→HP同时≤1e-4才准后续。对任一同一物理场分量，若二者都成立，三角不等式给出：

```math
\frac{\|H-P\|}{\|P\|}\leq\frac{2\varepsilon}{1-\varepsilon},\qquad\varepsilon=10^{-4}.
```

右侧为2.00020002e-4，而保存的H→P散射E/H为6.74525e-4/7.02539e-4。`common_difference`确实使用第二个场作为分母；这些非近零场不触发floor。因此**无论把HP解得多好，都不能令这两个旧端点同时满足原门**。这不是精度门应放宽，而是比较层级必须向前移动。所有旧FAIL保持，不能靠选择更大的分母、相位拟合或改selected点绕过。

V53把P=Z2/p6作为共同父级：一条增加z分辨得到A=Z4/p6，另一条提高p得到B=Z2/p7。检查P→A、P→B、A→B这组三角，不再把低阶H必须接近A作为新锚点的必要条件。H→A仍计算并如实记录，用于解释旧p5不足；它不是新队列的停工门。

三条新比较全过，才授本批`CROSSCHECKED_ACCURACY_ANCHOR_ON_FIXED_532`。若仅A/B彼此接近、但共同父级P增量失败，只能记`RICHER_ENDPOINT_AGREEMENT_ONLY`，不能称完整锚点或无限收敛。有限对照也不是严格连续误差上界。若再出现端点间距超过上述必要界，不再要求某个新场同时贴近不相容的旧端点。

## 3. 冻结物理与有限新队列

沿V51/V52完整descriptor：s=7/135；x=s×(0,16.5,25,33.5,50)，y=s×(0,6.25,12.5,18.75,25)，z=s×(−10,0,40,80,120,130)。λ0.7nm，grazing1°、azimuth5°、s极化、幅值1；Si n=0.999885140474+4.32477054e-6i，epsilon=n²、mu=1、air=1；材料表hash为55aa34e55c5e3cc35f6849eddbd3bcc72d3b694d32bc4885299ef373acd676a2。不索要或替换材料。

NOTCH按原全精度几何盒标记；原两cell缺口随网格细分，但不沿y复制。κ=(kx_inc,ky_inc,0)固定，E=g*u，Hcode=g*(curl(u)+iκ×u)/(i*k0*mu)，包络双周期。保持完整trial/test变换、物理RHS、全部内部与非零端口支撑、原未凝聚oracle，不改成paraxial、不把物理场投回旧多项式空间。

| 角色 | 三轴原区间划分倍数 / p | cells | 独立FE / trace / 内部，derived | 凝聚行含532 |
|---|---|---:|---|---:|
| A：HP_COMPLETE | (1,1,4) / 6 | 320 | 208512 / 64512 / 144000 | 65044 |
| B：P7_FORWARD | (1,1,2) / 7 | 160 | 166208 / 45248 / 120960 | 45780 |
| M：条件模式对照 | 固定P=(1,1,2)/6，828模式 | 160 | 104832 / 32832 / 72000 | 33660 |

拓扑须由现场MPC核对，不能删行对齐。B是明确授权的一次p7，不是p扫描；它以较少单元获得独立p方向证据，避免直接启动Z4/p7。它仍可能昂贵或不准确，不预设通过。**最多3个新完整solve；A/B为主，M有条件。** 不重解FLAT、H、P，不运行T、Z8、p8、新全域尺寸或新PC。

### 3.1 先实际接通容量，再进行一次必要重建

启动A前读取旧HP的symbolic记录及当前资源，提前核对§4全部预算通道。若新合同允许的容量没有真正传到factor接口，先修接线，不能又构建一小时才发现内部默认仍是16GiB。B也先做真实拓扑/存储规划，取得容量与完整p7张量/边界资格后独立运行；A场比较失败不取消B。

旧HP没有完整准备包。本批允许A一次新构建，并如实计入旧4746.49s损失及新费用。可读取身份完整的旧边界/符号检查记录，不据此伪造旧矩阵、因子或科学数组。开始前已知宿主/配额不够则不作昂贵准备；新symbolic比旧估计更大时仍须重新准入。

A与B均为真实物理零初值直接authority，不用H/P解造RHS或warm-start。固定现有复数MUMPS、端口等价坐标与至多两次残差精化；无ordering/shift/ILU/BLR/OOC扫描。每个返回状态立刻原子保存完整u/port/κ/实际descriptor/source，随后审核并释放factor/矩阵，再后处理。`AUDIT_PENDING`只补审，不再求解。

优先顺序：轻量接线及复用检查→A完整求解/保存→P/A及H/A比较→B完整求解/保存→P/B及A/B比较→条件M→一次增量独立VERIFY/COST。比较采用共同几何细分、固定selected点和原near-zero规则，不插值一方到另一方后冒充独立比较。旧H/P/B0比较和旧场独立审核不再重跑。

### 3.2 条件M与科学失败出口

仅P/A/B三条完整增量均通过、A/B原方程/恢复可信、且剩余时间含独立审核足够时，固定以**P=Z2/p6**为模式父case，m=−11..11、n=−4..4、上下×s/p=828；不根据参考误差重新挑有利端点。P是共同父级且已被两方向检查，所需规模小于A/B。

沿V52已实现的完整库存/投影接口，检查新828对象q47/q63；仅有实际不足才准一次63/79配对，不无限加q。旧532场对新增296模式必须实际投影，不填零。原场、公共键、新模式复量/功率及体吸收按同门比较；通过只授一次有限模式增量一致性。若积分或mode阶段有独立接线问题，不抹去已通过p/h证据。

P/A/B未全部通过时，不运行M，也不通过增加迭代或NN修补空间误差；完成差分场区域/分量与一张分辨方向判断表。同一保存场可作确定性误差诊断，不机械套NN训练的标签禁读规则。只提出一个后续更丰富空间或容量变化，不在本批自动再开p7/Z4或横向新case。若仅B容量/时间受阻，完成A真实场及可达比较，明确`P_DIRECTION_NOT_EVALUATED`，不虚称锚点已闭合。

## 4. 明确的新资源许可：不再用旧研究配额假扮数学不可行

**仅本V53有限案例允许：同时规划≤32GiB、warning40GiB、采样整树停止48GiB。** 这覆盖旧16/20/24GiB三层限额；不是每个子进程48GiB，不是允许用满整机。不得改其他任务或全局默认。稀疏装配/symbolic仍≤80000行，local p7维数1344，所有预分配/缓存/副本先计入。

新的numeric准入保持原倍数与单位：

```math
M_{\rm plan}=RSS_{\rm tree,live}+2\max(INFOG16,INFOG17)\,10^6+2\,2^{30}\leq32\,2^{30}\quad\text{bytes}.
```

旧HP给22,783,656,448B=21.218934GiB，落入新计划，但**这是新启动的规划依据，不是已测numeric峰，也不是现场免检票**。INFOG缺失/不可靠、实际包络超32GiB或宿主压力不安全仍拒绝numeric。固定ICNTL(22)=0，ICNTL(23)采用现场估计的原2倍decimal-MB额度；它是后端工作内存限制，不能当全进程RSS保证。

资源参数必须从V53真实resolved合同显式传到launcher、watchdog、assembly_capacity、CoordinateFactor/AnalyzedDirectFactor、numeric_plan和collector，不依赖改全局默认、monkeypatch或只修改一条admitted布尔值。以旧HP标量做一个轻量回归：旧16GiB拒绝、新32GiB通过规划、超过32GiB仍拒绝；测试不分解真实矩阵。旧V52窗口/JSON/FAIL不改写。

每个heavy前保留原effective/cgroup余量与PSI规则，并至少满足MemAvailable≥max(128GiB,有效物理内存10%)+384GiB邻任务增长余量+48GiB本任务停止预算；现有规则更严则沿更严者。MPI1、数学/CPU1、Loader0、GPU0、ownswap/OOC0；现场空闲物理核、避忙SMT，自有锁和全后代监督。2TB不是自动准入，remote未更新不代表邻任务idle。

一次只驻留一个全局因子。资源压力只清自身后代，至多一次≤600s前台冷却且全部原门恢复后重入；不改邻任务、系统swap、ABI/BLAS/CUDA、亲和性或锁。采样间隔实测报告，不把48GiB叫作连续cgroup硬峰，更不保证绝对零干扰。

## 5. 缩短昂贵准备和审核，不删科学检验

### 5.1 只作两个窄的执行优化，不另开优化campaign

代码`PhaseEvaluator.at`每次求值都重新tabulate(1,ref)，`common_difference`又为每个pair/q重建求值过程。这是可检查的重复工作；不能仅凭源码就保证它占全部2406s。允许按以下方式限时改进：

- 为相同元素/basis/变体/derivative/完整参考点建立只读、容量有界的tabulation cache；预计算同cell的DOF变换后系数和J逆。缓存键必须包含实际依赖，不四舍五入ref、宽度、κ或省略orientation。不同表可分块处理，额外cache/workspace≤2GiB并纳入32GiB总规划；记录命中率，零命中不伪称加速。
- 同一真实场在相同共同子网格/q上的物理值可在有限块内被多个pair消费。分子背景相消可以精确复用，但total/scattered的参考分母分别计算；完整H保留iκ×u。保持原q23/q31、selected、区域/分量与参考面，不降q、不换DG投影、不删cell或mode。

先在V52已保存H/P的固定少量实际子单元上，将新/旧求值、curl、加权积分配对；复数方向/Piola和新p7基函数还需相关小检查。操作尺度≤1e-11，并保留绝对差和小差分相对诊断。只做一次短配对；不为计时重跑全H/P比较。数学不通过或90min实现预算内接不齐，使用旧正确路径继续主解，调整剩余case时间，不等待新review。不得把旧oracle替换为新函数后自证正确。

### 5.2 准备状态和科学返回必须可持久消费

新构建中优先保存昂贵、确定性的**完整raw tensor按精确类的一份只读准备包**及cell→class、实际J、材料、κ、basis、dtype、数学依赖和producer hash；复用已有tensor-provider/原子writer，不设计通用缓存框架。无可靠现成小接入时可保持原构建，但不得捏造旧HP可复用；本批存储失败不销毁仍可继续的内存状态。不要序列化不受支持的MUMPS内部句柄。

缓存只覆盖实际写出并独立重开的数组；raw tensor不是完整Schur/矩阵/factor，恢复时仍计必要装配/局部LU。只可共享逐字节相同输入或已有数学资格的等价类，不能因坐标相近合类。已有六Gram不包含全部Cκ交叉项时不能直接替代。p6与p7不可串用缓存。

每个case至少保存最终完整系数和最小恢复依赖。后处理/元数据bug先保留原件、最小修复并补审；已完成新完整解不因README、collector或运行source文档变化重解。全局factor仍按release_before_recovery释放。新tensor缓存费用计入冷N=1；跨case命中另报，不把准备当免费。

### 5.3 测试范围收敛

不例行全库pytest、不重建全仓索引、不每轮重哈希全部旧artifacts、不重复V50求积/背景归因、不重解FLAT或H/P、不新建另一套runner。只做本次budget/p7/stage/缓存及必要数学targeted tests；相关Ruff/compile和一次紧凑文档检查，元数据检查目标累计≤20min。不扫描历史目录污染0.5s监督。

既有数学依赖/ABI/数组相同的资格直接复用。p6相同端面若布局或native编号变了，只重建必要散布与身份桥，不重新JIT全边界；p7的新全532边界仍须一次正确配对。全部新解在增量VERIFY用原未凝聚物理作用和独立q63审核一次，保存数据checker不再factor或求解。完整场准确性检验不能因“减少测试”取消。

## 6. 不变的数值门与解释

| Gate | 本批要求 |
|---|---|
| 原方程 | 独立未凝聚Cκ+完整DtN，true/native/增广/port各≤1e-6；直接内部目标≤1e-10，原最多两次精化 |
| 恢复/约束 | 全内部特解及非零内部port项，MPC/slave和操作恒等式≤1e-10；原slave-zero规则 |
| 场增量 | total/scattered E/H/scaled-curl、固定selected、参考面复通道各≤1e-4；分母/绝对floor继承V52 |
| 功率 | R/T/A/A_volume增量与独立体吸收能量闭合≤1e-5；逐mode最大功率差≤1e-6 |
| 积分 | 新全库存边界配对1e-11/操作1e-10；共同q23/q31操作门1e-10及原分子/分母 |

raw辅助端口、H加权端口行与物理参考面复振幅分开；不拟合相位、裁剪小项、归一化R+T+A或四舍五入过门。新相位空间对自己的原物理弱式验算，不强求满足旧普通多项式矩阵。小残差不是p/h收敛，有限p/h或532/828一致不是原尺寸资格。

旧H/P结果用于确定性精度比较，不是本批训练标签；本批没有NN。当前确定性收益不得归神经，未知上游/冷成本不补0。无新神经20%准入任务，避免再次把准确性主线拖回模型搜索。

## 7. 连续执行、时间、修复与交付

新窗口首项实际准备起7h总研发、科学有载≤5h、最后45min收尾；至少预留2000s给新增场独立审核/比较，并按已测实际速度上调预留或减少条件M，不削减门。所有实现、缓存资格、失败、重放、冷却、IO和交付计费。每次上下文恢复/新stage/commit前重读UTC、monotonic、boot_id和ledger，不重置旧窗口或用摘要估时间。

主工作是A与B；先分配其准备/真实求解/比较预算，不能先花整批重做缓存benchmark。按V52费用建立保守预计，p7未知准备明确列unknown并用本次早期实际类计时校准，不能沿用旧每stage任意短timeout。超预计时先节省重复求值、取消条件M，不以无限延长或取消独立审核救进度。

普通API/shape/dtype/路径/stage/缓存/writer错误，在本批累计2h修复/相关重放预算内定位→最小改动→针对性回归→继续；**不设bug个数式自动停工门**。同根因两次失败后必须更换诊断或用原正确实现，不能第三次盲重跑。原方程/ABI/输入/监督不可信先隔离；普通不收敛或空间不准确不是bug，不改材料/门限救成功。

新ignored≤12GiB，Task042去重累计≤58GiB、free≥50GiB且另留交付256MiB；这是本批显式增量许可，不删除旧失败或其他任务文件。只有准入和stage边界统计存储。准备包、场和独立检查的parent hash用增量manifest连接，不复制海量嵌套JSON。

完成A/B且有锚点时，继续条件M；无锚点时仍完成全部可达比较/分辨判断/费用，不在单个FAIL或代码commit处交棒。预算、安全或无法恢复的必要依赖可使真实未运行项收口，必须准确说明，不伪称目标已经实现。本批不启动更大几何。交付一个下一尺度所需的具体准确表示/通道/行数/准备和因子增长区间；factor fill、迭代和2TB/48h预测没有数据则保持unknown。

## 8. Git、正式入口与唯一交付

在canonical NN-Lab核对branch/HEAD/upstream/origin/worktree与活跃actor，安全fetch/ff-only本分支；不reset/stash/clean、不改共享Git或别的工作树。正式数学实现先clean commit，旧V52结果与closed ledger只读；新source不假称旧numeric续跑。旧task/review/response/raw不改。

复用`phase_notch_hp`、完整相位/凝聚/端口坐标/直接后端/补审/监督，只新增薄V53参数与队列；新可复用数值核进入src。待实现并validate的one-run入口：

```text
input/task042_neural_coarse_inverse/v53_capacity_resume_preflight.dat
input/task042_neural_coarse_inverse/v53_notch_z4_p6.dat
input/task042_neural_coarse_inverse/v53_notch_z2_p7.dat
input/task042_neural_coarse_inverse/v53_notch_modes828.dat
input/task042_neural_coarse_inverse/v53_verify_cost.dat
```

统一`python scripts/run_case.py <one-run.dat>`，尚未创建不声称可运行，不盲跑M。每run保存input_original.dat、resolved_config.json、run_manifest.json、input/physical/discretization/material/mode/source/array hash、run_summary与全过程资源；p/三轴/模式和32/40/48GiB预算必须是真实活动字段。

一次提交`response_v53.md`、`outcomes/phase_hp_completion_v53.md`及紧凑records：A/B状态、P/A/P/B/A/B及H/A比较、条件M、原方程/恢复/全场/模式/功率、symbolic/计划/实测峰、缓存正确性与实际命中/全成本、修复/补审及未运行原因。README/summary/两总账只追加短入口；本地测试不叫CI。GitHub渲染无法取得就写NOT_VERIFIED，不为网页重跑科学任务。

只推送`git push origin HEAD:refs/heads/task42_neural_coarse_inverse`。核对精确remote/HEAD、clean/upstream、closed/active null、清场和锁释放后交付用户并暂停。不通知/接管隔壁，不改dot/master，不merge，不自动开下一窗口。

外部接口依据：[PETSc MUMPS控制](https://petsc.org/release/manualpages/Mat/MATSOLVERMUMPS/)说明ICNTL(22)/(23)的in-core和每进程后端工作内存语义；[Basix 0.10.0 tabulate接口](https://docs.fenicsproject.org/basix/v0.10.0/python/_autosummary/basix.finite_element.html)说明求值表依赖元素、点和导数阶数。文档不证明本代码优化速度，不作为安装/升级或修改现场ABI的许可。
