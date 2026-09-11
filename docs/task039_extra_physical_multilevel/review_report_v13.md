# Task39extra Review V13：定位p4修正能力瓶颈，交付唯一下一方法与实施蓝图

## 0. 身份、结论与本轮交付

```text
repository             = Rookie1234567/MyFEniCS
branch                 = task39extra
review_date            = 2026-09-11
reviewed_HEAD          = 4cbfadc4880c20aea775142168e6dd4e71870fda
last_outer_source      = d39261bb17e8d9042c03d4d4990258da5043b621
original_task_base     = 2dc2e7305f10dc391a13970c6f0f0340cb87b6ee
previous_materials     = review_report_v12.md / response_v13.md
new_profile            = physical_p4_direction_diagnosis_v13
execution              = P0 -> P1 -> P2 -> P3 -> P4
response_required      = response_v14.md
new_p6_long_solve      = NOT_AUTHORIZED
new_global_reference   = NOT_AUTHORIZED
ordinary_default       = unchanged
master_merge           = NOT_APPROVED
```

**本轮消除的blocker：已经知道当前低存储p4修正很弱，但尚未分清“搜索方向缺少必要信息”“现有方向的系数选择不合适”以及“局部响应合并和全局纠错遗漏了什么”。没有这一判断，继续换块、rank、restart或内层步数会重复试错。**

本轮不是再次追求四步p4收敛，也不是再制造一条长程残差曲线。用最多三份已有匹配参考的真实p4输入，复用一次构建，完成可复算的方向空间与耦合分析；最后必须提交**一个优先改进方法、明确的改动接口、公式、成本模型及下一次真实验证计划**。不能只交“建议进一步研究粗空间/子域/AMG”的清单。

完整诊断允许得出“现有四个方向不够，不能靠换系数修好”；不允许得出“所有低内存逆不存在”。下一方法的选择是有证据的工程决策，不是保证一次解决0.7 nm的定理。确有输入、参考或数值可信度缺口时必须如实给出阻断，不能为了交付一个算法名称伪造确定性。

本review接受并关闭V12冻结宏块配置的性能负结果；不恢复其长跑，不补完已由用户停止的R64，不追溯改判旧Gate。V5准确p4逆支持的original/notch成功继续保留，V6–V12负结果原样保留。当前任务的终止后重新执行许可由本文限定为诊断；旧V12的O2/O3继续授权不自动延续到本批。

最终目标仍为约2 TB整机物理内存内的0.7 nm、complex128、Nedelec H(curl)、双Floquet、Fourier-DtN及任意非可分三维周期单胞。5 nm工作已在另一条线执行，本机不等待、不重复、不修改其分支、目录、进程或预算。

## 1. 接受的最新证据：不再重复定位已排除的问题

以下来自[最新回应](response_v13.md)、[V12补充中心结果](outcomes/physical_macro_v12.md)和[补充证据包](outcomes/records/v12_supplement/README.md)，不是本review新测量。残差均明确区分原A6、原A4及局部方程，时间不把父子阶段相加。

| 已有事实 | 数值/结果 | 本轮解释与边界 |
|---|---:|---|
| 全部局部块 | 42/42，覆盖48960个p4独立行 | measured；局部完备覆盖不是全局逆有效 |
| 局部回代最大相对残差 | 2.1772149386553977e-15 | measured；不继续提高局部LU精度 |
| 宏块四步I4 | 128次正式外层调用，0次达到1e-4 | measured；合法近似已真正接入外层 |
| R32第32/64步A6残差 | 0.8025891203479081 / 0.7666389832389989 | measured；不是系统OOM |
| 第32/64步参考场L2误差 | 0.9384007607744688 / 0.9488237463600627 | measured；残差下降而场误差后段增大 |
| 第64步求解节点/完整candidate时间 | 1540.2073412299874 / 1542.916955076985 s | conservative；两者不同终点，不与单调子计时混算 |
| 修复R32进程树RSS峰 | 3350794240 B，job/global swap增量0 | sampled；非完整生产求解内存资格 |
| ONE/BAL场误差几何比/操作时间比 | 1.000603999343256 / 0.6368202549964133 | measured-derived；ONE便宜但两者都弱，旧选择规则不证明BAL最优 |
| R64 | 到24步用户停止，已存前缀与R32相同 | controlled_stop；未完成restart优劣对照 |

局部矩阵、native/cached A4及已持久化记账有相应一致性证据，但不是所有潜在实现错误已被数学证明排除。本轮首先检查新捕获数据是否忠实重现实际I4，不把任何代数PASS当作求解器PASS。

## 2. 冻结模型、输入、参考和数学身份

### 2.1 固定13.5 nm真实离散，不制造更容易的模型

沿用原始1度grazing、azimuth0、s偏振、50×25 nm周期、z=-10…130 nm、原Si/air损耗、p6/h10、252个六面体、80模式、MPI1、线程1及合格Linux complex128/int32 ABI。

```text
physical_model_sha256 = 9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f
ordered_mode_sha256   = dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2
p6 independent/storage = 164592 / 173802
p4 independent/storage = 48960 / 53084
```

真实A6/b、A4、材料、quadrature、Floquet映射和DtN均不变。保留42块、实际C_U（W/P、单元内部响应及S/p2）、输出端1/multiplicity权重和V11的symbolic-sized MUMPS策略。本轮不同时构建旧1566实体或full252因子；不重新测试MUMPS收缩接口。

### 2.2 三份输入在计算前固定

从现有六份hash-bound calibration inventory取下列三份，不按本轮结果挑选：

| 顺序 | 精确stem | 角色 |
|---:|---|---|
| 1 | A2R160_BAL_H_p4_01 | 第一类困难g1，主分析 |
| 2 | A2R160_BAL_H_p4_02 | 反馈g2，对照不同右端项类型 |
| 3 | LIGHT448_BAL_H_p4_09 | 第二个困难g1，留出核验；不得据它改分组/选择规则 |

stem中的BAL_H是历史packet标签，不表示本轮运行完整p6 PC。第三份也是同一个物理模型的历史样本，**不是独立结构、随机统计样本或0.7 nm验证**。

P0必须先确认三份g、对应c_ref、A4c_ref、canonical map、原四步返回c及hash真实存在。使用现有load_recursive_calibration与packet索引；不能从最终残差反推丢失向量。c_ref是匹配离散参考，不是连续真解。检查原生A4参考残差不高于1e-10，并保存有限的r_ref，不将其强制视为零。

缺件先在现有索引/合法artifact中定位，不重建全局p4/p6参考因子。某份无法恢复则标REFERENCE_UNAVAILABLE；不替换成更容易的输入。可继续独立合法项目，但不足两个困难输入时不得标完整方法选择通过，须具体给出缺口，而非编造下一方案已验证。

### 2.3 原算子与实际近似不能混淆

```math
A=A_4,\qquad Ac_*=g,\qquad r_{\rm ref}=g-Ac_{\rm ref}.
```

单次基础PC仍按当前真实代码执行：

```math
a=C_Ug,\quad h=g-Aa,\quad d=M_Dh,\quad t=C_U(Ad),\quad B_4g=a+d-t.
```

I4仍为right FGMRES、零初值、一个至多4维周期、最多4次新B4、无跨RHS复用，原25/30秒返回和费用规则不变。参考绝不进入B4、KSP、方向筛选、初值或正式系数计算。本轮允许的参考辅助最优组合必须标记ORACLE_DIAGNOSTIC_ONLY，不能成为下一PC保存的答案库。

## 3. P0：先准备能回答问题的数据，再支付一次构建

读取根/docs及适用目录AGENTS、工作原则、task、V12、本review、最新response/summary和V12补充记录。任务目录当前未列出额外补充task文件；用户补充授权及其实际记录应通过最新response/outcomes核对，不从旧summary推断本轮权限。

先完成三份输入的轻量可用性审计和诊断接口准备，再构建一次现有macro stack。新的实际计算统一通过`python scripts/run_case.py input/path/to/case.dat`，一个dat表示一场确定的P1–P3诊断workflow；source、input和profile另算hash。现有runner扩展一个明确诊断入口即可，不复制物理求解核心或新增第二套ledger框架。

只增加默认关闭的向量观察/复制接口。优先在solve_physical_i4的counted_pc周围捕获实际预条件输出；不能用普通Arnoldi基V替代右预条件方向Z，不访问私有PETSc结构。保留每次输入、输出、序号、操作身份；原KSP返回值不变。保存耗时计入本轮，不能为了避开25/30秒线暂停算法时钟。若观察本身触发截止，只报告实际m，不补造四个方向。

新实例的局部回代与必要native检查沿已有builder执行；已未变的ABI和MUMPS策略资格复用。没有已资格化因子持久化时需要fresh重建，计费而不另开发序列化。正式诊断前提交clean source SHA。

## 4. P1：实际四个方向能否组合出需要的解？

### 4.1 捕获真实右预条件方向，不替换求解器

每份输入至多执行一次原四步I4。设实际完成m步，m不超过4：

```math
Z=[z_1,\ldots,z_m]\in\mathbb C^{N_4\times m},\qquad Q=AZ.
```

捕获z_j为PC对本次Krylov输入的实际返回值，深复制后与PETSc工作向量分离。AZ可以在求解结束后用相同合格A4逐列计算，单独记为diagnostic action；不混入原I4计数。原始r_ref、g和返回c都保存。实际工作可由已存完整方向复用，但不能假定V12存过Z。

用稳定QR/SVD验证c属于range(Z)，并独立计算同一Z上的最小原残差解。重建误差按max(norm(c),norm(Z)norm(y),tiny)归一化不高于1e-10；原残差最小值与KSP实际残差按操作尺度核对1e-10。近奇异、happy breakdown、rank截断时单独报告后向误差和可辨识性；超限先查捕获、范数、conjugation和原实现，不立即归为新物理机制。

### 4.2 同一方向空间做三种小问题；只有一种使用参考

真实场度量为无材料权重的M0，以及scaled-curl。优先复用现有LosslessFEMetric及原P64评价路径；p4直接metric替代pullback必须先核对同quadrature/约束的等价，不能使用系数二范数冒充场误差。

```math
M_{0,4}=P_{64}^{H}M_{0,6}P_{64},\qquad
K_{0,4}=P_{64}^{H}(k_0^{-2}K_{{\rm curl},6})P_{64}.
```

对每个解c报告三个独立量：

```math
\rho(c)=\frac{\|g-Ac\|_2}{\|g\|_2},\qquad
\eta(c)=\frac{\|c_{\rm ref}-c\|_{M_{0,4}}}{\|c_{\rm ref}\|_{M_{0,4}}},\qquad
\eta_{\rm curl}(c)=\frac{\|c_{\rm ref}-c\|_{K_{0,4}}}{\|c_{\rm ref}\|_{K_{0,4}}}.
```

零分母报告绝对量，不硬加任意物理正则。以下小问题只改变离线系数，**不是三个新KSP运行**：

```math
\begin{aligned}
y_R&=\arg\min_y\|g-Qy\|_2,\\
y_M&=\arg\min_y\|c_{\rm ref}-Zy\|_{M_{0,4}},\\
y_D&=\arg\min_y\|D^{-1/2}(g-Qy)\|_2,
\qquad D=\operatorname{diag}(M_{0,4}).
\end{aligned}
```

- y_R应重现原残差最小化的效果；它没有参考输入。
- y_M给当前空间最有利的场误差下界；它使用参考，只作诊断，同时必须报告它的原残差和curl误差。
- y_D是唯一固定的reference-free度量候选：正质量对角近似的dual residual scaling，不拟合权重、不使用c_ref或真实误差调D。它并非精确场误差范数，不承诺一定改善。

不得通过求解D之外的全局质量逆得到更好结果；D由已有质量对角接口或等价原积分计算。必须为正且有限，不能用abs(A对角)临时替代。y_D仅在现有Z上比较；真正修改Krylov度量会生成不同后续方向，本轮不把离线改善当完整新solver证明。

### 4.3 稳定计算和有效结论

最多48列的后续空间也采用相同稳定QR/SVD核心。禁止显式逆正规方程；质量内积用两次重正交的weighted QR或等价稳定方法，不形成N4×N4稠密M0。列预缩放、秩和奇异值保留；dense SVD的相对阈值固定1e-12，接近截断边界一个数量级内则标RANK_SENSITIVE，不扫描阈值挑结论。近奇异时比较得到的向量、残差和后向误差，不比较不可唯一确定的系数。

核心判断：若最优eta(Zy_M)仍很大，则**保持这些方向不变，任何系数都不能达到小场误差**；这只针对这次实际Z，不否定完整p4空间或所有后续迭代。若eta(Zy_M)小而原残差解场误差大，还要看rho(Zy_M)：不允许以恶化原方程来宣称已解决。两种最优不能同时达到时，记录方向空间无法兼顾两个目标。

## 5. P2：局部—全局到底在何处丢失纠错能力？

每份输入增加至多一次bare B4(g)，捕获a、h、各块d_i、加权回填p_i、d及t；与原md_array累加顺序一致，不改变权重。逐项记录误差和残差：

```math
c_{\rm ref}\ \longrightarrow\ c_{\rm ref}-a
\ \longrightarrow\ c_{\rm ref}-a-d
\ \longrightarrow\ c_{\rm ref}-a-d+t.
```

同时保存C_U原有closure、实际不平衡大小及计时。不得把C_U称为M0最佳投影；它是物理响应，不是正交误差投影。不得从“位于空气中的误差多”直接判成DtN错误或边界反射。

### 5.1 用有限参考残差的精确恒等式检查块外影响

以下推导只在合法独立坐标上使用。令J_i=R_i^H R_i，e_h=c_ref-a，则：

```math
Ae_h=h-r_{\rm ref},\qquad
D_i d_i=R_i h+\ell_i,\qquad
\chi_i=R_i(Ae_h)-D_iR_i e_h.
```

```math
D_i(d_i-R_i e_h)=\chi_i+R_i r_{\rm ref}+\ell_i.
```

chi_i是在当前误差上的块外作用，ell_i是实测局部回代残差。它们可由已算的h、r_ref和局部矩阵乘法得到，不为每块再运行全局求解。验证局部恒等式、输出端partition of unity与以下全局重组：

```math
\sum_iR_i^H W_iR_i=I,\qquad
d-e_h=\sum_iR_i^H W_i(d_i-R_i e_h).
```

局部系数范数只作同块操作诊断；相邻块重叠，不能将局部范数相加当全局场能量。必须报告全局和的M0/curl范数及抵消，不能把若干向量范数解释成相加为100%的原因占比。恒等式的操作尺度误差要求1e-10；涉及已测局部求解误差的项保留，不归零。

这些等式验证的是分解，不直接证明应该使用PML、Robin或更大块。若块外项大，也要结合下一节的可组合性，区分“这些局部响应还能通过组合补偿”与“现有响应确实缺信息”。

## 6. P3：只做小矩阵上的可实现性对照，让诊断能选出方法

仅有“最优四维场误差大”仍不足以决定下一方法。本节复用P1/P2已生成的方向，最多增加逐列A/metric action，不新增PC迭代或因子。

### 6.1 一个有利的响应空间上界：不先将42块相加

令p_i=R_i^H W_i d_i，建立：

```math
L=[Z,\ a,\ p_1,\ldots,p_{42},\ -t],\qquad \dim\operatorname{range}(L)\le48.
```

在L上分别计算原残差最小解和参考场最优解，报告rho、eta及curl。由于含Z，最优场/残差不应比Z差，差别超过1e-9操作尺度须查秩处理。该空间只包含本次产生的有限局部响应，不等于全部局部有限元子空间，更不等于A4全空间。

若L也无法表达主要修正，继续对这批响应改加法/权重不会解决当前样本；若L明显优于Z，则“先相加导致可用方向被压成少量向量”具有证据，但尚需证明有不靠答案、成本有界的实现。

### 6.2 一个固定的可实现系数/方向选择：最多8个局部响应

本轮只允许以下一个reference-free选择器，不扫描rank或分组：始终保留a和-t；从42个p_i中最多选择8个。先对当前已保留方向的A像作秩揭示QR，得到原残差的投影余量。每轮选择与该余量具有最大归一化相关性的、经正交化后非零的A p_i；并列时取canonical block index最小者，加入后重新求原残差最小二乘。共至多8轮，零方向/数值相关方向按固定1e-12 rank规则跳过，不补更多方向。

得到不超过10列的L_10，再计算c_sel=L_10 y_sel。**选择只使用g、A像和已生成局部响应，不得接触c_ref、y_M、误差热点或留出样本答案。** 此处参考只在最后评价eta/curl。

这是“保留部分局部方向，让小型残差最小化统一选择组合”的有限原型，与此前跨RHS recycling不同；也不是从局部factor个数直接推断全局逆。相关多预条件Krylov思想见S3，但本原型不宣称复现某篇论文的完整算法。

成本必须诚实：为了选8个，仍可能要计算全部42个A p_i；不能只计被选中的8个。记录A像构建、局部回代、C_U、QR、存储的实际成本/派生载荷。当前分析为48列保存的代价不是未来生产长期存储承诺。不同RHS不共享方向、参考或选择结果。

### 6.3 固定的判断标准，不根据结果连续加变体

对唯一度量候选c_D=Zy_D和唯一分方向候选c_sel，分别与原c比较。称为STRONG_ACTION_SIGNAL须同时满足：两个困难g1（01和09）的eta均至少减半；三输入的curl误差均不超过原值1.10倍；反馈g2的eta不超过原值1.10倍；三输入原rho均不超过原值1.10倍。原值近零时采用操作绝对尺度而非比值。这些是一次工程筛选线，不是收敛定理或统计检验；临界/混合结果如实报告，不改阈值凑通过。

参考最优解不参加STRONG_ACTION_SIGNAL。c_D和c_sel的作用代价以本轮基础内核实测和明确调用次数建模，评价用reference/metric/采集成本另计；不得用已有材料列的免费离线重组时间冒充future PC apply。未实际实现的完整新KSP时间仍为predicted/unknown。

## 7. P4：必须交付“下一步采用什么”，不是新的候选列表

### 7.1 决策顺序及允许的单一主推荐

| 数据支持的情况 | 本轮应给出的下一主方法 | 必须具体说明的改动 |
|---|---|---|
| 捕获、真实残差最小化、映射或度量恒等式不可信 | IMPLEMENTATION_OR_METRIC_REPAIR | 指定出错接口、期望关系、最小修复；不得归为算法不存在 |
| c_D有STRONG_ACTION_SIGNAL且成本合理 | DUAL_MASS_SCALED_P4_KRYLOV | 用固定正质量对角的双侧尺度化改变p4内部Krylov度量；基础局部因子不变，原A4/A6残差照常核查 |
| c_sel有STRONG_ACTION_SIGNAL且库存/成本合理 | SELECTIVE_MULTIPRECONDITIONED_P4 | 不先把全部局部响应固定相加；用至多8个局部方向加a/-t作小型原残差最小化；保留一次setup、多RHS局部回代 |
| 两个便宜实现均无清楚收益 | PHYSICAL_INTERFACE_MULTILEVEL_REDESIGN | 停止微调当前有限I4，改为显式区分局部内部消元与全局接口响应，重新设计真实物理接口粗纠错；不是再增块/步数 |

前两种可实现候选同时合格时，比较包括全部A像构造的单次成本模型和常驻向量；成本不确定或相近时优先改动更小的度量路线。只输出一个primary_method，另一项至多作为未执行的条件备选。任何选择都需写confidence及反证；STRONG_ACTION_SIGNAL不等于完整p6通过。

最后一行是停止局部小修后的**架构优先选择**，不是从三份向量证明接口方法必定有效：若L的最优也很差，明确当前响应缺失；若L最优很好但L_10差，明确是经济压缩/选择尚不合格，不能把它错写成局部空间完全没有能力。两种情况下均不得自动把8扩到42或重开参数扫描；需要在蓝图中说明为什么转向结构化全局接口响应更值得投入。数据只支持低置信度时必须标明，不能把规则输出写成唯一数学根因。

### 7.2 三种方法的蓝图最低具体程度

**度量路线。** 在合法独立坐标定义S=D^(-1/2)，写清x=S x_hat、A_hat=S A S、g_hat=Sg与PC的对应输入输出变换；不是在正式结果后乘系数，不需要全局M0逆。说明新搜索方向会改变，需下一批完整外层验证，不能用本批固定Z的离线收益冒充已完成。说明为什么不同于旧逐段MR和旧正定B6平滑。

**分方向路线。** 写出L_10生成、可观测的残差相关性选择、复数QR、零/相关列删除、最终c=L_10y及真实残差记账。单次最多42个局部回代、必要C_U和最多42个局部A像构造均计费；不在里面再嵌套几百步。明确它不同于V7把各块预先相加、V8/V9跨RHS复用以及旧S6/p4/H6阶段MR。给出超过当前42块时的有界候选生成/分布式存储需求，不宣称当前N×42向量库存可无条件搬到0.7 nm。

**接口多层路线。** 必须给出实际未知量划分和对应矩阵，而不止写“做Schur/AMG”：

```math
A=\begin{bmatrix}A_{II}&A_{I\Gamma}\\ A_{\Gamma I}&A_{\Gamma\Gamma}\end{bmatrix},\qquad
S_\Gamma=A_{\Gamma\Gamma}-A_{\Gamma I}A_{II}^{-1}A_{I\Gamma}.
```

用现有映射计数：共享宏块自由度及具有非零DtN行/列支持的自由度进入Gamma；其余才可作候选局部内部I_i。检查体积分图是否仍有跨I_i耦合；存在时扩大Gamma的确定规则，不能假设A_II必为块对角。只做结构计数，不在本批另造S或factor。给出streaming S action与局部内部恢复的公式及接口规模/内存估计，不显式形成稠密全局S。

更重要的是：**Schur消元本身不提供强接口逆。** 蓝图必须选定一种reference-free的物理接口粗方向生成规则，写出小问题、选择准则、支撑与层间传递，并给出底层容量上限及超过上限后的分层求解策略；不得仍用不断增长的全局S/p2 LU作终点。根据P2/P3证据说明优先保留哪些跨块响应；不能只用三个参考误差的POD当通用粗空间。对照旧16-slab/75D、正定谱空间、PML及full252，逐项写真实差异。如果不能在本轮提出可执行的规则，要明确BLUEPRINT_INCOMPLETE及缺项，不能交一张AMG/GMG/Robin/PML菜单冒充结论。

三条路线在本轮只交蓝图和由已有数据得到的有限系数对照，**不自动授权实现新生产PC或新全局接口因子**。本文不是认定BAL_H最优：蓝图应明确保留还是改变其内部接口，或先取消对“p4必须少量步独立解准”的依赖；涉及新完整外层框架须下次明确授权。

### 7.3 必需决策卡：首屏就能看懂下一步

`next_method_decision.json`及`next_method_blueprint.md`至少包含：

```text
primary_method / confidence / decision_status
observed_bottleneck / evidence_ids / counter_evidence
what_is_preserved / what_is_replaced / exact_interface
operator_and_preconditioner_formulas / reference_free_construction
why_not_previous_entity_recycle_macro_variants
setup_cost / apply_counts / retained_bytes / temporary_bytes
local_factor_and_global_coarse_growth / 2TB_0p7nm_blocker_removed
first_original_test / conditional_notch_test / physics_gates
numerical_stop / cost_stop / resource_stop
remaining_unknowns / not_a_convergence_guarantee
```

完整方法选择应至少回答：**采用什么、为什么不是相邻旧变体、第一处代码改哪里、为什么有望低内存且不靠长内层、用哪一场真实计算裁决。** 只给“需要更强粗空间”判为DECISION_DELIVERY_INCOMPLETE。因真实缺件无法判断的结果不伪造通过，修复缺件本身应具体且有限。

## 8. 执行和资源：一批有限分析，不再让准备耗尽数值机会

| 限制 | 本轮冻结值 |
|---|---|
| 新p6/original/notch/restart长跑 | 0；历史曲线直接复用 |
| 新全局参考、p4/fine LU | 0；仅已有reference作评价 |
| 现有macro stack构建 | 正常路径1次，复用至所有输入完成 |
| 原I4重放 | 最多3次，每次最多4个新B4 |
| 额外bare B4(g) | 最多3次；每个输入一次P2分解 |
| 诊断额外B4总数 | 至多15次；每次局部42回代等嵌套另计 |
| 最大响应空间 | 每输入48列；只作诊断，不扩rank |
| p4 A像与metric作用 | 按实际列计数；所有新增各类action分列，总新增A4不超过200次，M0/curl各不超过240次 |
| 诊断新增常驻/工作数组 | 256 MiB，逐输入流式释放；大数组存ignored artifact，不塞JSON/Git |
| 局部库存/临时预留 | 2.5 GiB / 1 GiB，原V11配额与单实例512 MiB不变 |
| S/p2 | 8192总行/512 MiB上限不变；本轮不将其提升为生产底层 |
| 正式诊断workflow预算 | 7200 s；构建预检子预算1200 s；每个输入采集/分析1500 s；不得自动延期 |
| 工程活动计时 | 单独记录已知区间和unknown；不从正式7200 s里扣掉编写时间后再次让数值阶段几乎无法开始 |

7200 s是研究投入边界，不是完成时间承诺。含正式父workflow、所有新构建、诊断、保存和checker；父子时间不重复相加。若真实正确性bug需要修复，保留原负结果、提交新SHA，只允许一次受影响的修复重放，仍从同一总预算扣费；不存在数学失败的自动重试。新长时间监控/审计平台不在范围。

整机仍保留reserve=max(4 GiB,15% effective_total)，launch cap不高于min(12,000,000,000 B,effective_available-reserve)，按物理/cgroup限制及动态余量核对。process-tree包含Python/MPI/编译器和全部后代，zero-swap，一次一个heavy；硬安全先于保存，信号只请求安全停机。allocated、used、库存、RSS/PSS、derived和predicted分列；不直接提高cap或用used替换allocated绕Gate。

4列Z及AZ在53084存储行下的数值载荷为6,794,752 B；48列及其A像为81,537,024 B。两者是派生下界，未含metric像、QR副本和工作向量；256 MiB额外预算要按实际同时存活对象执行。避免保存N6×48的fine基，P64/metric用流式pullback；不能因“只是诊断”建立N4×N4密集矩阵。

## 9. 实现、证据、测试与提交

优先复用：`physical_recursive_coarse.py`的I4、`physical_macro_dd4.py`的局部作用/映射、`physical_recursive_controls.py`的packet loader、`physical_error_metric.py`的LosslessFEMetric、现有V12 runner与save_packet。观察接口和可复用小空间代数放合适的src模块；checker只读保存的数组/Gram/范数重算，不再次运行PC。

必要测试合并成一批：复数最小二乘、右预条件方向捕获、rank deficiency/零列、参考残差非零的局部恒等式、PoU重组、源不变、禁用捕获时历史行为不变、reference-free选择器不读取答案。玩具矩阵只验证这些恒等式，不替代三份真实输入；不用扩大成全部PDE回归。保存原测试stdout/stderr，说明本地测试与未运行的full pytest/CI。

建议普通commit顺序：诊断入口/默认关闭hook及小空间代数；真实诊断证据；单一方法蓝图与收口。每场真实动作前clean SHA；不amend、不强推、不删除历史负结果、不merge master。

紧凑交付只需：

```text
response_v14.md
outcomes/p4_direction_diagnosis_v13.md
outcomes/next_method_blueprint_v13.md
outcomes/records/p4_direction_diagnosis_v13.json
outcomes/records/next_method_decision_v13.json
outcomes/records/run_index.json / outcomes/summary.md / outcomes/test_summary.md
```

同时增量更新项目development_progress和development_model_registry，不重抄全部历史。raw方向、参考与大型数组保持ignored，Git只留hash、路径和必要小矩阵。报告按三输入一张表列actual、best-Z、scaled-Z、best-L、selected-L10的rho/eta/curl及有效rank；第二张表列a/d/t阶段误差和跨块重组；第三张表即下一方法决策卡。必须区分observed、derived、inference、proposed与not_run。

本轮成功状态为DIAGNOSIS_COMPLETE_WITH_SELECTED_NEXT_METHOD，而不是LOW_MEMORY_SOLVER_PASS。若数值可信度或必要参考缺口不能闭合，分别为DIAGNOSTIC_IDENTITY_BLOCKED、REFERENCE_UNAVAILABLE或DECISION_DELIVERY_INCOMPLETE，说明已能排除什么及单一下一修复。即使下一方法被推荐，p6残差1e-6、场/curl1e-4、R/T/A与体吸收及守恒1e-5、80模式复幅值1e-4和通道功率1e-6仍需将来完整求解验证；本批不发布official物理输出。

## 10. 依据与文献边界

| 编号 | 来源 | 本review实际使用范围 |
|---|---|---|
| S1 | [Response V13](response_v13.md)、[V12补充结果](outcomes/physical_macro_v12.md)、[内部记录审计](outcomes/records/v12_supplement/audits/task39extra-v12-supplement-p4-supervisor-audit.json) | 真实失败、参考身份、已保存量和不应重做的工作 |
| S2 | [PETSc FGMRES](https://petsc.org/release/manualpages/KSP/KSPFGMRES/) | 右预条件及非线性内部求解；不提供当前配置收敛保证，在线版本不替代本机ABI |
| S3 | [Greif–Rees–Szyld, Multi-preconditioned GMRES, UBC TR-2011-12](https://www.cs.ubc.ca/tr/2011/tr-2011-12) | 作者机构摘要支持多预条件方向与DD的联系；未在本review读取其PDF细节，不借其名声称本选择器具有论文保证 |
| S4 | [SciPy 1.11.4 lstsq](https://docs.scipy.org/doc/scipy-1.11.4/reference/generated/scipy.linalg.lstsq.html) | 复数最小二乘、有效rank、QR/SVD/LAPACK驱动的实现依据；不升级环境 |
| S5 | [PETSc virtual Schur complement](https://petsc.org/release/manualpages/KSP/MatCreateSchurComplement/) | Schur可以只计算作用，不必显式形成；并不提供一个现成鲁棒接口PC |
| S6 | [历史经验](prior_attempts_retrospective.md)、[真实误差定位](outcomes/actual_error_diagnosis_v5.md) | 与整个p4最佳投影、旧75D、谱空间、逐段MR和recycling区分 |

第4–6节最优性及局部恒等式由本文明确代数定义推出，不把它们称作已有Maxwell性能定理。第7节筛选阈值、方向数和架构优先级是本轮冻结的工程决策；没有文献证明三份样本足以保证任意三维或波长鲁棒性。

**终点：这轮结束后，用户应得到“下一步采用某一具体机制、修改某一接口、因为哪些实际数据支持、需要多少资源、第一场真实验证如何裁决”，而不是再收到一串局部PASS和一句‘继续探索’。**
