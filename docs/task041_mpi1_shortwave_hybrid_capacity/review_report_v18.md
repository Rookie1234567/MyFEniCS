# Task041 Review V18：先分解已保存M400误差，不改门、不再盲重建

## 0. 正式裁决与身份

**接受本场为V15逐行数值合同未通过的真实负结果。批准利用同次存档作有界离线误差分解、必要的小型代数对照，以及仅在数据已存在时重算选定projection行。暂不改变生产判据、不删弱行、不换PC、不追加M400大型构造额度。2/2额度已消耗；本报告不是第三场warm授权。**

```text
repository           = Rookie1234567/MyFEniCS
branch               = codex/20260902-task41-mpi1-shortwave-hybrid-capacity
review_date          = 2026-10-16 Asia/Singapore
reviewed_HEAD        = f6a20dc724600063530b49bcfb5d9746a3be6d49
runtime_source       = c662a70b4af4d742f7a8305d0efd63342423c775
Invocation           = 6344a904b8df435a88a7466dd739da76
previous_review      = review_report_v17.md; V15行合同仍有效
reviewed_response    = response_v18.md
response_required    = response_v19.md
solver_policy_keep   = task041_v13_consistent_fixed_balh_modal_surrogate
row_contract_keep    = task041.v15.original_modal_row.terms_backward.v1
resource_policy_keep = task041_v16_memavailable_phase_v1
large_quota          = 2/2 consumed; 0 new large constructions authorized
merge_approval       = NO
```

本轮消除的blocker是“同一固定B的代数恒等式、浮点实现误差和PC逐行验收被混为一谈，因而无法选择正确修复”。最小产物是**同一失败调用的误差来源表**，不是再写一套框架、再次计算完整场，或只重复已有Decimal比值。

最终目标仍是0.7 nm、50×25 nm目标周期单胞、约2 TB整机RAM及余量、48 h完整计算。Hybrid仅适用于内部可作模态传播的结构，不能替代任意非可分三维Full3D资格。W5弱显著级继续按用户决定延期，W2、BIOS、GPU、node1排障均不占本轮。

## 1. 审阅证据与访问边界

已读取Response V18、summary、test_summary、machine record，以及runtime源码中的列构造、owner solve、PC apply/取证、原HybridBlockOperator、C构造。runtime到最新HEAD的compare仅列文档/record改动，未改变数值源码。根AGENTS、repository_work_principles已核对；任务目录tree中task及既有review的blob保持此前版本，无新补充任务书。V17本地全文与远端blob `cbf9e8568eb2b291c8544cf8c5b2f003fb0b7dc7`一致并已回读。[R1–R8]

**原始数据边界：** GitHub读取 `results/task041_v16_m400_offline_closeout_20261016/terminal_recompute.json` 返回404；这些ignored工件没有在本环境取得。可用文件检索也未找到对应原始数组。因此本审阅不是“已亲自重算800行与全部S/C数组”。已直接独立复算的是报告逐字给出的row259 binary64分量；其余800行、archive hash和清场状态依据已提交记录。P0要求Codex现场读取原件，不用摘要替代数组。

| 对象 | 已有结果 | 裁决 |
|---|---|---|
| tiny真实FE | serial R30 reason2/389、原残差4.97654e-9；MPI2 reason2/441、4.83780e-9 | 数值资格已有；serial原pytest因fixture/schema仍rc1，后续离线解释不改旧rc；不重跑以凑绿色 |
| 生产资源链 | V16 MemAvailable贯通，进入worker；peak tree49,616,527,360 B、job cgroup47,208,488,960 B | 不是容量拒绝；二者不相加，不重做资源政策 |
| 本次M400 | S_B 800列完成、owner LU建立；第1次PC apply拒绝，无完成的outer iteration | 不称原方程不收敛或代码bug已确定 |
| 行门 | eta_inf=0.017996403128522177；732/800超1e-10；row259最坏 | 当前合同真实FAIL，不能换eta_2宣布PASS |
| 其他指标 | eta_2=3.257659348665526e-14；owner字段1.9821704747745833e-16；分解差0，身份/捕获通过 | 各自只覆盖相应阶段；不能代替逐行或最终原方程验收 |
| 时间 | service唯一wall13,489.261149145 s，约3.747 h | 失败warm时间，不是成功cold时间；V5累计651,274.1059664167 s不是本场wall |
| 历史边界 | 旧V14 M400根因UNCONFIRMED；本次现场独立 | 不用本次数据倒证旧场；监督提醒保持用户已停用状态 |

machine record仍有 `hourly_watch_timer=active`，用户本轮及Response末段说明推送核验后已停用。将前者标为采样时状态、后者为后续状态；只读补一条时间/状态更正，不启停新timer、不改原收据。

## 2. 数学判断：哪一层已经排除，哪一层尚未解释

### 2.1 同一B的恒等式是代数条件，不是浮点逐行相对精度保证

合并两侧记为D、G、L；一致PC的精确算术定义为：

```math
S_B=C-LBG,\quad y=Br_s,\quad g=r_m-Ly,\quad S_Ba=g,\quad q=BGa,\quad z_s=y-q.
```

```math
Lz_s+Ca=r_m.
```

它对任意满足所需求解条件的**同一个线性B**成立，不要求B=D^{-1}。因此B近似原D逆较弱能解释外层慢，却不能单独解释该精确恒等式为何不成立。反过来，代码借用同一B对象并不意味着浮点作用在基向量、组合向量上严格线性，或不同路径的误差相等。

当前源码确实逐列计算 `C[:,j]-L_b B_b G_b e_j-L_t B_t G_t e_j`，而PC先算y、g、a、q，再以axpy形成z_s；原A随后重新作Lz_s与Ca。归档S不是无舍入的C-LBG。即使矩阵和对象身份正确，列构造、求解、y-q、projection与Ca乘法的误差仍须分别核对。[R4–R7]

### 2.2 row259排除了“最后一次加法/比值计算出错”的简单解释

本次r_modal为精确零。把Response中的两个复数组成项按 `Decimal.from_float` 转换到100位后直接相加，实部与虚部均**精确等于**存档d；分量和d没有再发生此次最后加法的表示误差。复模比值重算为0.0179964031285221265572…，与90位归档复算一致。

```math
|d_{259}|\simeq1.1476179207258\times10^{-18},\qquad
s_{259}\simeq6.3769293926683\times10^{-17},\qquad
10^{-10}s_{259}\simeq6.3769293926683\times10^{-27}.
```

所以不能说“把最后一次求和换高精度就会好”，也不能把比值1.8%叫作全场误差1.8%。**需要解释的是：为什么生成这两个约3.2e-17的贡献项时，留下了约1.15e-18的不平衡。** 它可能来自上游浮点误差/放大，也可能来自算子、列构造或PC作用不一致；当前未定位。

### 2.3 V15指标有明确含义，但不覆盖所有运算层级

V15分母为已计算结果的模长之和：

```math
s_i=|(L_bz_b)_i|+|(L_tz_t)_i|+|(Ca)_i|+|(r_m)_i|.
```

这是“这些组成向量的加和方程”的相对扰动模型，并不是矩阵乘法数据级误差模型。每个 `(Ca)_i` 本身可能是许多乘积相消后的结果，Lz也可能如此；这一级的未相消尺度通常涉及 `|C||a|` 与 `|L||z|`，不是 `|Ca|` 与 `|Lz|`。标准分量后向误差参考式为：

```math
\eta_{\rm data}=\max_i\frac{|(Lz_s+Ca-r_m)_i|}{(|L||z_s|+|C||a|+|r_m|)_i}.
```

LAPACK的BERR用逐元素绝对矩阵乘向量作为尺度；复数abs约定与本项目复模须注明，不直接把LAPACK返回值冒称完全相同。[S1] 点积误差也取决于乘积绝对值之和，而非已相消的点积结果。[S2]

这说明V15可能比实际算术可达到的精度更苛刻，也可能正确拒绝了真实错误；**本轮只分析，不授权用eta_data替换V15。** 不准仅因分母变大后通过，就宣布根因或正确性。eta_2小也不允许忽略732行；同样，732行大不能单独证明场有大误差。

还有一项命名问题：owner源码对非零g使用 `||S_B a-g||₂/||g||₂`，虽然字段名叫relative_backward_error。它不是逐分量BERR，也不是一般的 `||r||/(||S||||a||+||g||)`。本次先核实际g和分母，保留原字段并在派生分析说明语义，不为改名重跑。[R5]

## 3. P0：利用同一存档作可判别的误差分解——本轮第一优先

### 3.1 先读一次原件，不重复只做标量比值

从原index定位并核对S_B、C、同次a/g、r_modal/w_modal、t_bottom/t_top/t_constraint/d，以及16个rank-local source/target文件。源码 `_check_v13_original_modal_row`明确把a和g存入terminal数组；现场仍须证实实际键、shape和hash，不以“代码会保存”替代实际存在。[R6]

原件只读、新建派生目录。按原rank-major layout还原z_b、z_t和owner的a，不能把16份文件按猜测拼接。核对终态target中的a与snapshot a、source中的r_modal一致。S/C的archive SHA与array SHA分别校验，不混用。不能将占位Invocation字面串当直接身份，继续以原manifest/index建立外部绑定。

确认归档C来自surrogate还是原A；若没有原A的C字节证据，以下e_C首先称“约束作用一致性差”，直到核对相同C后才称纯乘法舍入。必要时只用合格packet和已有纯函数重建800×800 C作身份比较，不改mode顺序、phase或物理输入。

### 3.2 用a/g/S/C直接拆分，暂不调用A或B

下列hat均为本次存档binary64，HP表示对这些**已舍入输入**作高精度运算，不是重算原FE。记：

```math
 t=\hat t_b+\hat t_t,\quad p_C={\rm HP}(\hat C\hat a),\quad p_S={\rm HP}(\hat S\hat a),\quad r=\hat r_m.
```

```math
e_{\rm sub}=\hat d-(\hat w-r),\quad
e_{\rm sum}=\hat w-(t+\hat t_c),\quad
e_C=\hat t_c-p_C,\quad
e_S=p_S-\hat g,\quad
e_K=t+p_C-p_S+\hat g-r.
```

```math
\boxed{\hat d=e_{\rm sub}+e_{\rm sum}+e_C+e_S+e_K.}
```

这是可由已有数组检验的恒等分解：e_C定位C作用差；e_S定位存档小系统的真求解残差；e_K是**剩余的侧区/列构造/组合一致性差**，不是已证明的B错误。不能只比较这些向量的范数大小而忽略彼此相消，必须保留复数分量并验证闭合。

先对全部800行生成轻量binary64分类表；90/120位HP至少覆盖row259、最大绝对d的失败行、失败行分母中位控制和一个通过行（去重，固定选择规则）。明确主导方向后可在同一session扩展全部800行HP matvec。采用准确binary64→高精度转换，不从四舍五入打印值构造oracle。HP两档结果的差相对于各操作的未相消数据尺度应≤1e-30；这是分析精度检查，不是物理门。若有极端抵消导致不足，保留高精度不确定性，不盲加任意绝对floor。

每行表至少给原eta、|d|、s、五个复数误差项、闭合差、`(|C||a|)_i`、`(|S||a|+|g|)_i`、约束点积抵消比、Schur分量BERR和阶段可解释/缺失项。不要在binary64先形成C-S再当无误差反馈；优先用p_C-p_S，且明确即使HP形成C-S也不能恢复构造S时已经丢失的原列数据。

**重要：** 当前分解通过是账目闭合，不等于所求场通过。若e_S在整个范数下小、某些行相对其数据尺度仍大，才能针对小LU精度继续；若e_K占主导，就不要继续反复重算owner总体残差。

### 3.3 不可从存档唯一辨识的部分须明确标出

若定义F=LBG并记录了原列反馈，理想情况下：

```math
e_K=(Lz_s-Ly+Lq)+(\hat g-r+Ly)+[(C-\hat S)a-Lq].
```

三项分别对应减法/projection组合、g构造、逐列反馈与直接B组合的差异。若y、q、Ly、Lq或原反馈列未保存，仅凭S/C、最终z和a/g不能唯一拆开这些原因。**不得将r-g冒充实测Ly，也不得将C-S冒充无舍入LBG。** 缺什么就列准确对象；不因信息缺失重建两侧factor。

## 4. P1：只在P0指出方向后做最小分析性验证

| P0指向 | 本轮允许动作 | 不能作的结论/改动 |
|---|---|---|
| e_C明显 | 用同一C行与a做HP点积、binary64原次序与补偿求和对照；有原A C身份才能归为求值差 | 不改正式原A求值、不提升全场precision、不用离线改善冒充生产已修 |
| e_S明显 | 对已归档800×800 S作一次诊断LU，必要时同因子最多两次HP残差修正；报告分量BERR、变化和小矩阵condition estimate（可用GECON，不求全谱） | 不是恢复旧live factor；修正a后原z须随B重新变化，不能只改a或Ca就称PC闭合 |
| e_K明显且有L行数据 | 流式读取已存的实际projection行与z，用HP复算Lz和绝对乘积尺度，区分projection求值与更早的差异 | 不把mode向量直接当已装配L；无映射/权重/约束证据时不能重放 |
| e_K明显但缺L或中间量 | 给出缺项和一份最小下一次捕获方案；可用当前tiny已存在的作用级fixture验证捕获位置 | 不重建M400 FE/P4、QEP，不重算800列，不将已知欠定问题包装成完整根因 |
| 同次身份或符号/索引不匹配 | 先核manifest与实际原件，再在最小代数fixture复现 | 只有明确代码证据才定位实现缺陷；本报告不预先授权生产数学修补或新full run |

浮点误差预算应来自实际点积长度、dtype、求和/复乘流程和未相消乘积尺度。实数点积可参考nu或gamma_n的界；复数须按实虚操作保守展开或给出适用依据，不能直接照搬实数常数。出现underflow/overflow/flush-to-zero时单列，不能以一般gamma界覆盖。已舍入S/C/投影系数的输入误差不在一次matvec舍入界内。[S2]

**界内只说明相容，不证明因果；界外说明现有预算解释不了，不自动证明代码bug。** 不采用事后乘1000使每行落入的“经验误差界”。数据级eta和传播预算都只作diagnostic。

如需验证新分析器，最多一组小型代数fixture，覆盖：准确相消、所有输入都小但有真实相对错误、内部dot强相消、单个弱行注入错号/漏项、统一复尺度及行尺度、a/g交换或错layout拒绝。只测本次解析/分解，不重新运行389/441步tiny、全A/B/C、MPI8 ABI或公式全回归来重复已有资格。必要MPI2仅限已存分布式行读取的同一轻量路径，不求解FE。

## 5. 资源、额度与如何结束本轮

批准的计算是**离线数组分析和上述条件性小型代数运算**，不是额外M400试验。使用现有环境/薄分析入口、1进程、数学线程1；优先NumPy与已有Decimal，不安装新依赖，不造新的runner/supervisor。数组分析预算以2 GiB峰值为限，开跑前核对实际数组、临时空间和宿主/cgroup余量；需要全量archive扫描则逐文件流式读取。若无法在此范围完成，先交已得分解和具体新增对象需求，不擅自扩大到生产80 GiB。

允许一次P0主分析session，P1按结果做必要的同数据分析。普通读文件/shape/schema问题最小修复并在已有授权内继续，不每个matvec都请求审批；同根因两次出现先小fixture解决，不能重复整批读取和重算。保留旧raw、hash、账目与失败标签，不覆盖源矩阵/终态向量。沿既有V5真实口径唯一计账，不重复finalizer；用户已停用提醒，不新建或重启它。

本轮**禁止**新的QEP、P4 symbolic/numeric、M400/full tiny长迭代、M600/h细化、生产门修改、epsilon地板、eta_2代替eta_inf、删行/删模态、归零弱分量、任意相位对齐、隐藏direct fallback和PC参数扫描。

下列情形才提出新计算额度申请，而不是本轮自动启动：

1. P0/P1已把主要差异缩到需要真实B/P4才能分离的环节，明确列出缺失量、对应最小调用数、峰值与费用；新申请优先一次同冻结RHS的捕获/作用，不默认完整800列或全场。
2. 已找到可重复的局部实现错误，修复提案在小型受影响验证中得到支持，并说明旧S_B是否仍有效；真实生产修复和大型验证由下一次明确review授权。
3. 算术证据支持需重新定义数值合同：必须给实际逐行误差预算、错误注入拒绝证据和最终场保护，而不是只展示一个更宽指标通过。先提出合同，不在本轮实施。

仅仅“分析已通过”“eta_data更小”“owner LU通过”均不产生第三场授权。2/2消耗和旧V14根因边界保持。

## 6. 交付与目标关联

提交 `response_v19.md`、一个中心outcome和轻量机器记录，更新summary/test_summary。核心表按同一次apply列：旧指标；e_C/e_S/e_K等复数分解；实际数据尺度/预算；能够排除与仍不能区分的原因；下一步具体最小操作及是否需要大型额度。另附可复现命令、分析source/input hashes、正常/失败记录与资源/时间，不只写“继续怀疑roundoff”。

将read-only evidence状态、tiny数值资格、生产MemAvailable贯通和M400行失败分开；不重新审理已解决的启动/目录问题，也不为修finalizer次级policy标签跑PDE。若缺数据，不只写unknown，而应给可辨识的已知残差分解和准确缺项。

目前49.62 GB峰与3.747 h失败warm表明本次没有触及2 TB或48 h硬件/时间边界，却完全不证明目标单胞已可行。应先关闭此次PC一致性与验收的匹配问题，才能取得有效外层成本。后续目标预算仍按QEP、p4填充、DtN/trace、S_B、Krylov及恢复重叠分别建立；不能用小模型内存线性放大或把失败warm当总时间。

**最终裁决：ACCEPT_NEGATIVE_EVIDENCE_WITH_SCOPE_LIMITS；APPROVE_ARCHIVE_ERROR_DECOMPOSITION_ONLY；NO_NEW_LARGE_CONSTRUCTION。** 本review不宣称已找到根因、不修改PC/生产门，也不将前版V15的分量尺度继续当成对整个B/矩阵乘法流程自动有效的保证。

## 7. 固定来源

- [R1 Response V18](https://github.com/Rookie1234567/MyFEniCS/blob/f6a20dc724600063530b49bcfb5d9746a3be6d49/docs/task041_mpi1_shortwave_hybrid_capacity/response_v18.md)、[summary](https://github.com/Rookie1234567/MyFEniCS/blob/f6a20dc724600063530b49bcfb5d9746a3be6d49/docs/task041_mpi1_shortwave_hybrid_capacity/outcomes/summary.md)、[test_summary](https://github.com/Rookie1234567/MyFEniCS/blob/f6a20dc724600063530b49bcfb5d9746a3be6d49/docs/task041_mpi1_shortwave_hybrid_capacity/outcomes/test_summary.md)。
- [R2 machine record](https://github.com/Rookie1234567/MyFEniCS/blob/f6a20dc724600063530b49bcfb5d9746a3be6d49/docs/task041_mpi1_shortwave_hybrid_capacity/outcomes/records/task041_v16_m400_terminal_20261016.json)：同次数组身份/原始索引；ignored NPZ/JSON在本环境不可读。
- [R3 runtime到结果提交比较](https://github.com/Rookie1234567/MyFEniCS/compare/c662a70b4af4d742f7a8305d0efd63342423c775...f6a20dc724600063530b49bcfb5d9746a3be6d49)：仅文档/record。
- [R4–R6 block-LDU runtime](https://github.com/Rookie1234567/MyFEniCS/blob/c662a70b4af4d742f7a8305d0efd63342423c775/src/solvers/hybrid_fem_modal_block_ldu.py)：assemble_column、Task041V13ConsistentModalSurrogateSystem.solve、_apply_unwrapped、_check_v13_original_modal_row中的a/g存档。
- [R7 原HybridBlockOperator](https://github.com/Rookie1234567/MyFEniCS/blob/c662a70b4af4d742f7a8305d0efd63342423c775/src/solvers/hybrid_fem_modal_iterative.py)及[C构造](https://github.com/Rookie1234567/MyFEniCS/blob/c662a70b4af4d742f7a8305d0efd63342423c775/src/solvers/hybrid_fem_modal_augmented_direct.py)：原projection、Ca与同次组成项；C含传播/trace映射和内部消元修正，不假设为单位阵。
- [R8 Review V17](review_report_v17.md)、[V15](review_report_v15.md)、[task](task.md)、[仓库原则](../repository_work_principles.md)：本轮仅覆盖已消耗额度后的后续分析范围，不改历史。
- [S1 LAPACK componentwise BERR](https://netlib.org/lapack/explore-html/db/d65/group__la__lin__berr_ga29f9d2fe60477751b4c67e1c3cdff0cf.html)：abs(A)abs(x)+abs(b)数据尺度。
- [S2 Jeannerod–Rump, Improved Error Bounds for Inner Products in Floating-Point Arithmetic](https://epubs.siam.org/doi/10.1137/120894488)：点积/矩阵乘法的运算误差尺度；适用前提须核对，不将实数定理常数直接套全部复数/分布式流程。

ChatGPT本次仅提交review，并对公开列出的row259做了标量复算；未运行工作站、读取完整ignored数组或修改求解器。Markdown静态检查、远端blob核对与未能验证的GitHub视觉渲染分别报告。
