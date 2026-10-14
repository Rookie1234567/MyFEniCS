# Task041 Review V15：统一PC模态行后向误差、销毁前取证与有条件恢复M400

## 0. 裁决与身份

**批准修正“只要RHS非零就单除以该RHS”的PC模态行判据，改用所有RHS统一的、按原模态行未相消组成项定标的后向误差。批准先修复销毁前取证并完成定向验证；这些条件通过后，使用V14尚未使用的第2场大型构造额度继续同一个M400候选。不是立即重跑，不新增一套PC，不放宽最终原方程/物理验收，也不把历史M400失败改成舍入误差已证实或PASS。**

```text
repository              = Rookie1234567/MyFEniCS
branch                  = codex/20260902-task41-mpi1-shortwave-hybrid-capacity
review_date             = 2026-10-14 Asia/Singapore
reviewed_HEAD           = 52bfb6eae1f3ee05a970457a794ac3aeb32b3c50
latest_commit           = docs(task041): finalize V14 evidence attribution
runtime_source          = f969d413bde02339b673a9636f42582a1879f657
runtime_Invocation      = 686efe6ec9324b5bbe75a796a758d545
previous_review         = review_report_v14.md
reviewed_response       = response_v16.md
response_required       = response_v17.md
solver_policy_keep      = task041_v13_consistent_fixed_balh_modal_surrogate
new_audit_contract      = task041.v15.original_modal_row.terms_backward.v1
primary_case            = W0.7 / 10x5 nm / p6 h0.70 / M400 / MPI8x1
memory_policy           = system_default_unbound
swap_policy             = observe_only
W5_weak_channel         = DEFERRED_BY_USER
merge_approval          = NO
```

本轮消除“相消到近零的PC模态分量触发不合适的相对判据，以及异常清理使根因证据丢失”两个blocker，属于数值验收和生命周期修复。最终目标仍是0.7 nm、目标50×25 nm周期单胞、约2 TB整机内存及余量、48 h完整计算；Hybrid仅用于满足内部模态传播假设的结构，不代表任意三维Full3D已通过。

Response V16已回应V14，故新增本报告。明确覆盖V13/V14关于PC原模态行“非零RHS必须相对除以RHS、只有精确零用组成项”的规则；只改变此项内部一致性检查，不改变owner S_B求解门、原A4门、最终五残差与物理门。旧指标和失败原样保留。新判据是不同误差度量，不以“数字仍为1e-10”冒充未改变合同。

## 1. 本次证据与不能推出的结论

已核对当前分支/目录、Response V16、summary、machine record，以及PC检查函数、原HybridBlockOperator和相关提交。当前AGENTS及repository_work_principles与此前已读blob一致，task与V14的blob亦已核对；任务目录未列额外补充任务书。工作站ignored大工件未在本环境直接读取，依据提交的具体摘要及hash索引，不声称完成了本机FE复现。[R1–R5]

| 对象 | 已记录事实 | 裁决 |
|---|---|---|
| 正式M400构造 | 800列S_B全部完成、owner LU ready、fresh aggregate authority通过 | 旧启动/资源回调问题已在本场越过，不再以它们解释本次停止 |
| 正式outer第1步 | global约0.85618、modal约7.6030e-14，仍ITERATING | 不同于随后某次PC输入/输出的模态行检查；不代表最终收敛 |
| 正式PC行失败 | legacy relative=1.039223>1e-10；分子、分母、组成项、精确apply序号未保存 | 无法求出绝对误差，不能确认与tiny同根因；也不能由这个比值判定场误差为104% |
| tiny第2次PC | 非零RHS范数2.646487008256017e-15，残差5.299281747526413e-16，相除0.20023834354730255；owner S_B同次通过 | 证明现行判据可能敏感；非零分支未保存的组成项不能借用第1次的0.9404675尺度代算 |
| 已确认取证缺陷 | 异常后销毁KSP/context，再读borrowed side diagnostics产生次生RuntimeError | 必须先冻结数值证据；不能靠修正销毁后getter补出缺失的旧向量 |
| 时间/资源 | S_B列构造11355.683221373 s；服务12811.423691891 s；service tree峰46615474176 B | 分别约3.154 h、3.559 h、46.62 GB；非内存停止，尚不是成功运行时间 |

继续保存旧IMPLEMENTATION_FAILURE分类，并另列根因解释状态。正式M400根因仍为UNCONFIRMED；tiny旧门拒绝与证据生命周期问题已复现/确认。不能将“tiny pytest 1 passed（捕获成功）”写成数值通过。Response V16预算段把M称作外部模态数的措辞应更正：M400是每方向内部保留模式数，2M=800是S_B阶数；P4 external_mode_count=646是另一独立库存，修文档即可。[R1–R3]

## 2. 为什么应修合同，而不是坚持旧门到取得不可能的历史证明

一致PC在精确算术中满足：

```math
S_B=C-LBG,\qquad y=Br_s,\qquad S_Ba=r_m-Ly,\qquad z_s=y-BGa,
```

```math
Lz_s+Ca=r_m,\qquad (\mathcal A\mathcal P^{-1})_{\mathrm{modal},:}=[0\ \ I].
```

因此，当初始残差的模态块为零时，精确算术下对应Krylov子空间的模态块保持为零；有限精度计算/正交化可产生极小非零分量。这是该块结构下合理的数值情形，不应将近零分量当成必须相对精确至十位的小型独立物理激励。此推导说明合同的结构性风险，不证明M400未保存的失败向量恰好属于此情形。[R4–R5][S1]

tiny第2次旧门实际要求绝对行残差约不超过2.6465e-25。如果行由量级较大的贡献项相消而成，这个要求可远低于这些项的浮点运算误差；反之，若所有贡献项本来只有1e-15量级，5.3e-16也可能是不小的误差。**是否合格必须看该次真实组成项，不能只看绝对误差小。**

本报告修正之前review对精确零/非零的过硬分支设计。这种设计风险已有数学依据和tiny证据，修合同不必等待无法恢复的旧M400分子分母；但历史根因仍保留未知，必须在新运行中取证。

## 3. 唯一批准的新PC行判据

### 3.1 分子始终来自原全局算子

对当前PC输入r及实际输出z，独立调用原全局A得到w。把原modal行按其真实符号与布局分解为下列800维向量；bottom/top项按原布局嵌入各自半区：

```math
w_m=(\mathcal A_{\mathrm{original}}z)_m,\quad
 t_b=L_bz_b,\quad t_t=L_tz_t,\quad t_c=Ca,\quad
 d=w_m-r_m.
```

不得用S_B a-g替代d，也不能从PC内部已算好的抵消结果反推t。组成项必须来自原HybridBlockOperator的projection和modal_constraint，与本次原A作用绑定。

### 3.2 所有RHS使用同一公式，不引入near-zero阈值

```math
s_i=|(t_b)_i|+|(t_t)_i|+|(t_c)_i|+|(r_m)_i|,\qquad
\eta_{\mathrm{terms},\infty}=\max_i\frac{|d_i|}{s_i}.
```

**新的决定性门是eta_terms_inf<=1e-10，且数据、布局、原A身份与来源检查通过。** 复数绝对值使用复模；对s_i=0，仅d_i精确为零时该项记0，否则拒绝。NaN/Inf、错误形状、缺少组成项、陈旧调用数据均拒绝。不得使用max(norm,1)、max(norm,epsilon)、固定绝对atol、epsilon分支或把near-zero改成zero。

同步报告直观的范数版，不把它作为弱化逐行门的替代：

```math
\eta_{\mathrm{terms},2}=
\frac{\|d\|_2}{\|t_b\|_2+\|t_t\|_2+\|t_c\|_2+\|r_m\|_2}.
```

也保留legacy的RHS相对误差及其pass/false。精确零时旧相对指标记not_defined，不制造无穷大通过。新门pass而旧门fail应明确记为LEGACY_RHS_RELATIVE_REJECTED_BACKWARD_ACCEPTED，不回填历史。所有范数/比例须避免自身overflow/underflow，允许由实际数据最大模构造的等价缩放，禁止引入单位无关的1作为地板；极端数据无法可靠评估时拒绝并记录。

### 3.3 数值依据与适用边界

本指标是**组成向量加和方程**的分量后向误差，而不是直接把|A z|冒充|A||z|。对每行，允许对t_b、t_t、t_c和r_m各自作相对于其模的扰动。三角不等式给出最小共同相对扰动至少为|d_i|/s_i；沿d_i方向按各项模分配扰动即可达到该界（零项不扰动）。因此公式有明确扰动解释，不是经验性放大分母。

全体向量乘任意非零复数alpha时，分子分母同乘|alpha|；各模态行作一致非零尺度变换时，逐行指标也不变。在精确乘积下，|Lz|<=|L||z|，因此本组成项指标比标准矩阵元素级BERR更保守，不等同于LAPACK的BERR。有限精度下需用tiny高精度独立乘法校验分子和组成项。[S2–S3]

分量门防止某一弱行的明显错误被其他大行的范数掩盖。但任何后向误差都不保证病态问题的前向场误差小，也不能证明一个被一致改错的原A是正确物理模型；保留输入/算子身份、独立作用等价和最终物理门。未批准把本判据推广到owner S_B、p4或最终原方程验收。

### 3.4 最小实现与成本边界

当前原HybridBlockOperator.mult已经计算C@a、bottom projection和top projection，再按既定顺序相加。优先在该原算子上下文加仅V13启用的只读取证出口：同一次MatMult复制相加前的三个O(M)向量并立即交给检查器，保持原求和次序/符号及数学输出不变；绑定原operator handle、本次作用序号和目标向量身份，拒绝旧缓存。不要重复执行B、P4或构造全局A来获取分母，不另建绝对值大矩阵。

检查函数不再规定“非零只返回None组成项/零必须两次MatMult”；新合同对所有RHS取得同次原A作用和组成项。tiny独立确认w与三项之和一致，实际运行也记录此分解差并以同尺度1e-10门核对。不得读取PC surrogate的C来假装独立原A项。新增小数组/标量的payload计入原预算并计时，不增加资源上限或新资源调度框架。

## 4. 销毁前保存：先留现场，再报错清理

在_check_v13_original_modal_row作出决定时，立即构造**只含自有标量和数组副本**的record；失败证据在抛出FloatingPointError前冻结并写出，不依赖context.destroy之后的diagnostics property。

每次PC入口递增attempted_apply序号，成功数另计；不再把仅成功后递增的pc_apply_count当失败调用序号。记录last_completed_outer_iteration及是否确知当前KSP序号，无法确知就写unknown，不由apply次数猜测。

每次记录：实际Invocation/runtime SHA、PC与原A身份、apply序号、owner、modal key/布局hash、r_m/w_m/t_b/t_t/t_c/d范数、legacy相对值、新两项误差、最大分量及其分子/分母、分解差、finite/zero/输入未改/alias结果，以及**同次**owner S_B残差、solve序号与B/P4计数。record不得含借用PETSc对象、可变NumPy视图或后续才求值的getter。

owner小NPZ保存r_m、w_m、t_b/t_t/t_c、d、a和本次S_B右端g；每场只留一个成功control、首个legacy-fail/new-pass，以及独立保留额度的terminal failure。终态槽不能被首个普通目标miss用完。索引记录SHA、原modal keys、shape/dtype及数值源；不把大数组base64塞进response。

若发生真正新门失败，在预算允许的情况下逐rank流式保存该PC完整source/target的owned部分、ownership range和hash，用于进一步重放；不gather全场到owner，不保存p4因子。若完整向量无法安全落盘，至少小modal现场和全部标量必须先保存，并明确缺项；不能因某个可选全场快照缺少而丢掉已有小证据。

在原A作用和既有collective校验正常返回的安全点统一判定，owner写入后广播写入状态，再一致抛错/清理。任意rank在PETSc collective中异常时，不盲目新增allgather/Barrier；只保存当时可信的rank-local信息并由既有监督链清场。写入/清理异常为secondary_error，不能覆盖首个数学拒绝；测试必须证明销毁后只读冻结副本即可取得原证据。

## 5. 定向验证与第2场准入

按同一批实现→定向serial→MPI2收口执行下列紧凑矩阵。复用test350实际PC/owner LU/RIGHT FGMRES及已有registered tiny FE，不新建独立诊断框架或重跑W5。纯测试/记录修改不影响已通过的启动链，除非实际触及其代码。

| 测试 | 必须证明 |
|---|---|
| 旧tiny复现与新判据 | 先保留旧两次apply原值；重新取得第2次的真实组成项，不能挪用第1次尺度。新门通过需由实际计算证明，并让同一个tiny FGMRES连续完成原系统残差检查，不能再把“捕获异常成功”当解算通过 |
| 零、近零、一般RHS及尺度 | 测精确零相消、非零近零相消、无相消、所有项都极小但相对错的情况。以2^-200、2^-40、1、2^40、2^200及非实复相位一致缩放完整输入/输出/组成项；结果应一致。逐行缩放也保持分量判断；边界以外选样，不要求浮点比值逐bit相同 |
| 独立高精度小矩阵oracle | 用已有可用高精度工具或标准库decimal复数实虚分解，独立计算原A模态行及各项。核对新记录不是由surrogate自证；不以机器longdouble名称推定有效精度，不安装新运行环境 |
| 必须拒绝真实错误 | 在非退化tiny原PC输出后注入错号、正负/行排列、漏一项或相对1e-6量级污染；owner S_B仍可通过，但原modal行新门必须拒绝。加入“其他行很大、只有一弱行错误”和整体缩小版本，防止范数或固定atol掩盖错误；不以落在原modal行零空间的扰动作为必须被此门检测的反例 |
| 输入/生命周期/MPI2 | alias或输入被改、错shape、NaN/Inf、陈旧term序号均拒绝；在拒绝点后使所有live diagnostics getter抛错，冻结现场仍可读。MPI2覆盖owner/non-owner与写入失败，首因不被清理覆盖、不死锁；测试失败用轻量fixture修，不支付大构造 |

**准入决定：** 上述与改动相关的测试在最终相关源码上通过、原A4/owner S_B/真实tiny最终残差均通过、没有未解释的注入错误漏检，且既有资源/ABI/输入门通过后，主控可使用V14剩余的第2场大型构造额度，无需再次申请同一范围。不能因旧M400数据已经不可恢复而循环禁止验证修正；也不能仅依据tiny“误差绝对值小”就启动。

本轮只授权判据/取证修复后的同一候选。若tiny真正的新后向门仍失败，先利用其完整小数据定位，不提高1e-10、不换更多分母，不直接开展大场。普通路径/fixture/schema问题沿V14最小修复后继续；大型额度不因新review标题重置。

## 6. 正式继续、复用与交付

冻结W0.7、10×5 nm、p6/h0.70、M400、MPI8、接口2/22、matched L20/N29、PORD、entity_closure、一致固定B及其固定一次数学精化。原A4物理/增广门1e-10、owner S_B门1e-10、最终五项原残差各5e-9，以及全部接口、外部通道、能量/体吸收与E/H检查不变。不得恢复side128/modal32嵌套KSP或改变模式、网格来取得PASS。

保留system_default_unbound、显式请求rank map（最近为[0,1,13,14,15,16,17,18]，启动前重核）、80/72/8 GiB、双节点合计384 GiB reserve及现行node1可用性门；swap仅观测。一次一个heavy，不改BIOS、不误停邻任务；W5弱显著级继续延期，W2不抢占主线。

复用合格QEP。已退出作业的p4因子不能恢复。先检查800列S_B是否有完整已保存数组及既有合法复用入口：只有原A/B/mesh/MPC/模式坐标与布局、dtype、原矩阵hash和构造完成身份充分匹配，且原action对照通过时才复用；无文件或无成熟入口就本次构造一次，不为开发缓存框架推迟运行。本场S_B ready后将约10.24 MB矩阵和必要身份封存到ignored结果，避免以后纯后处理/判据变更再丢掉所有列；不把保存矩阵称作保存p4因子。

通过新门后在同一存活因子周期连续走原outer、五残差、恢复与完整物理输出，不在第2次PC通过后又主动退出重建。记录首个legacy拒绝但新门通过的真实M400现场：它可检验当前运行是否呈现tiny机制，但不能倒改旧Invocation根因。若新门仍拒绝，则必须有该次具体分子/分母/组成项与同次owner记录；若新门通过但原outer停滞，按V13原有限收口条件处理，那是独立的PC质量问题，不再次放宽行检查。

M400完整收敛后才推进已授权的M/h资格与更大几何。48 h按QEP、setup、S_B、全部outer及恢复/核验/清理计；warm、旧producer+warm组合、研发账本分列。现有S_B约3.154 h说明一次重复构造有实际成本，但不能由outer第1步预测总完成时间。当前46.62 GB不是目标50×25 nm或任意三维2 TB容量证明。

输出response_v17.md及轻量中心record、summary顶部、测试证据与模型总账。必须区分：判据合同缺陷得到修正；tiny实际解算通过；旧正式根因仍未知或新证据支持；新M400原方程/物理是否通过。保留V5旧278项与历史费用，只追加新attempt/Invocation，不重写旧FAIL。只在原分支普通commit/push，不amend、force-push、覆盖stash或merge master。ChatGPT本轮仅审阅与提交本文，未执行工作站修复/测试/计算。

## 7. 固定依据

- [R1 Response V16](https://github.com/Rookie1234567/MyFEniCS/blob/52bfb6eae1f3ee05a970457a794ac3aeb32b3c50/docs/task041_mpi1_shortwave_hybrid_capacity/response_v16.md)：正式与tiny数值、未知字段和运行边界。
- [R2 machine record](https://github.com/Rookie1234567/MyFEniCS/blob/52bfb6eae1f3ee05a970457a794ac3aeb32b3c50/docs/task041_mpi1_shortwave_hybrid_capacity/outcomes/records/task041_v14_modal_row_terminal_20261014.json)：Invocation、同次/ready快照区分、时间与资源。
- [R3 summary](https://github.com/Rookie1234567/MyFEniCS/blob/52bfb6eae1f3ee05a970457a794ac3aeb32b3c50/docs/task041_mpi1_shortwave_hybrid_capacity/outcomes/summary.md)：阶段结果与历史限定。
- [R4 PC实现](https://github.com/Rookie1234567/MyFEniCS/blob/52bfb6eae1f3ee05a970457a794ac3aeb32b3c50/src/solvers/hybrid_fem_modal_block_ldu.py)：bind_v13_original_global_operator、_check_v13_original_modal_row、apply、destroy。
- [R5 原HybridBlockOperator](https://github.com/Rookie1234567/MyFEniCS/blob/52bfb6eae1f3ee05a970457a794ac3aeb32b3c50/src/solvers/hybrid_fem_modal_iterative.py)：原模态行的C与两侧projection组成；全局保持MatPython，无需物化。
- [S1 PETSc KSPFGMRES](https://petsc.org/release/manualpages/KSP/KSPFGMRES/)：RIGHT FGMRES及不精确PC语义；块不变子空间为本文从一致PC恒等式推导，不冒充文档结论。
- [S2 LAPACK error bounds](https://netlib.org/lapack/lug/node81.html)：标准normwise与componentwise backward error以及前向误差区别。
- [S3 LAPACK improved bounds](https://netlib.org/lapack/lug/node79.html)：整体范数可掩盖小分量，逐分量度量的意义。本文使用组成项扰动模型并给出推导，不声称直接调用了LAPACK BERR。
