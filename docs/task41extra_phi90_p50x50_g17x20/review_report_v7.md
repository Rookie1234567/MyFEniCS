# Task41extra Review V7：修正归因的端口残差定义，先用保存数组闭合代数链

## 0. 本轮决定与冻结身份

**接受 V6 已完成28,000个 actual key、八键局部筛查及完整保存审核的事实；维持完整作用 FAIL、候选初次恢复 forward FAIL。下一轮严格采用 saved-only 路线：修正归因公式遗漏的 Bα，核对 donor/candidate 状态和矩阵身份，分解尚存差异。不重建完整候选，不重生成或扫描 carrier，不启动200q。**

本轮消除的 blocker 是“已有完整向量却仍不能用一致的代数恒等式解释失败”。归因修复不是生产算子修复，更不能作为绕过完整两列门的理由。

| 项目 | 冻结值 |
|---|---|
| repository / branch | `Rookie1234567/MyFEniCS` / `task41extra_phi90_p50x50_g17x20` |
| 本次结果 base | `bc305e02861968d9c790472a85af67acf42fbc8f` |
| V6 起点 / 科学生产 source | `dcc2737a9166e6c9185223ac084f811d5068ad4b` / `210fbbf271faa14c62ac30153b80332d0e645982` |
| V6 saved-checker source | `89e1e42114870ba1db752dfaf6d893ad13f923d6` |
| 历史 donor source | `afbe91e5947ed18fb74d7105097e129c1b8b4cc7` |
| 日期 / 角色 | 2026-10-21，Asia/Singapore；ChatGPT审阅，Codex实现/定向测试/受监督只读审核 |
| 新工作范围 | 归因定义、状态绑定、独立保存数组审计及现成局部块代数；无新PC、全仓重构、默认变更或master合并 |

已核对 response_v6、compact、hash index、summary、test_summary、run index、实际生产归因与checker源码。根/文档规则及task.md继承已读版本，V6增量比较未修改这些文件。V6 preparation明确记录用户指定archive附件为执行权威，故本轮按该来源审核，不把另一份同名V6中不同的局部筛查合同混入。两份历史文档均保留；后续本文件是新一轮唯一review入口。[R1–R5]

本审阅未登录工作站，未读取其大型NPY、运行FE或项目测试。真实结果依据远端证据；下文的源码缺陷和代数推导与“真实198闭合差已经被数值解释”严格区分。唯一新增实验为当前容器的独立小型复数分块代数例子，不是MyFEniCS资格。

## 1. 接受进展，但明确两项数值门仍未关闭

| 对象 | V6实测 / 结论 |
|---|---|
| actual构建 | 28,000 raw/oriented keys；八代表键完整张量、R/T/S通过执行合同的局部门 |
| 性能 | evaluator 19,641.249 s；owner 24,777.348 s；正式service 28,555.909 s。嵌套阶段不相加 |
| 完整两列 | 冻结分母2225.481253487629、2225.4807123031883；绝对差3.824090978625035e-7、8.051905483782545e-7；相对1.7183209126709868e-10、3.6180522433957604e-10，原门1e-11，FAIL |
| 新候选恢复 | forward 1.981377497384616e-11、1.979023053583157e-11，FAIL；native volume residual约1.44e-15，PASS；实际额外修正0次，不是三次额度用尽 |
| attribution | closure约198.180617、198.157859；只是DIAGNOSTIC_ONLY，不是解的误差或已确定舍入根因 |
| 资源 | 构建tree RSS 367,708,164,096 B；cgroup 366,622,593,024 B；task swap0。宿主+31/+58页分别保留，不归因任务；PSS未采样 |
| 数据 | 新174数组声明4,514,199,336 B；旧141数组9,379,882,344 B只读继承；174项hash核验及所需数组独立读取完成 |
| 总账 | 已知不重叠service父成本29,764.616 s；缺失回执对应费用及其他缺项保持UNKNOWN |
| 尚未取得 | 200q、准确因子组、完整参考逆、KSP/FGMRES、0.7 nm场、A6/物理结果、最终精度、完整冷流程2TB/48h资格 |

新候选恢复与donor V3三次修正后的PASS不是同一个对象。saved checker“audit_completed/data_integrity=true”说明审核执行完成、文件一致；不保证其归因公式正确，也不改变action FAIL。生产source到结果HEAD的差异未修改本次实际数值核心，主要为checker/监督/证据；对应生产问题可以在冻结源码中直接定位。[R1][R2][R3]

## 2. 已确认的归因定义缺陷：完整RHS减了体积作用，却未减Bα

`Task41V5VolumeAttributionAccumulator.finalize` 当前使用：

```python
r_t = native_rhs[active_original] - native_volume_action[active_original]
left = d + r_t + T_r_i
right = delta_t + attributed_terms
```

其中native_rhs含所选Bα，native_volume_action只含体积。另一方面，`delta_t`在observe/admit中由局部体积作用与native体积作用组成，且`d`来自已经包含并抵消端口耦合的完整P6/reduced-RHS差。这导致左侧多出一个Bα_trace。saved checker在自己的chunk loop中重复了相同遗漏，所以它能复现旧报告的198，却没有独立检验该等式的数学定义。[C1][C2]

这个缺陷是源码事实。真实闭合差是否主要等于Bα，必须比较**整个复数向量**，不是仅比较两个范数。预期需要检验 `C_legacy - beta_active`，不能先宣布它必然落到1e-11以下。也不能把这项减法用于修改保存的p6/reduced-RHS或原action误差。

当前容器的独立两cell复数例子保留非Hermitian局部块、复相位E、非零Bα和故意非零的消元缺陷。旧式闭合范数与Bα范数均为51.5636502109，二者向量差约2e-15–5e-15；正确式闭合约2e-15–4e-15。故意混用两个状态时仍有0.68005误差。该实验只验证符号与状态要求，不是工作站198误差的复算。

## 3. 统一符号：体积式和完整式都写清，保留消元缺陷

令V6当前局部体积块为K/G/J/L，已存消元算子为R/T/S；全局独立trace为t，单元物理trace为t_c=E_c t，E包含已有方向/Floquet映射。N(u)表示旧独立native体积作用的保存结果，已在原MPC dual/storage约定下。b为保存native_volume_rhs，f为保存native_rhs；beta为保存Bα，两者满足f≈b+beta，有限精度差不得抹去。当前已证Bi=0，仍先从保存数据核对f_i=b_i，beta不含内部/slave支撑。

```math
R_c\simeq-K_c^{-1}G_c,\qquad
T_c\simeq-J_cK_c^{-1},\qquad
S_c=L_c+J_cR_c.
```

对donor状态s（j0或j3）及其严格匹配的native作用n_s=N(u_s)，定义：

```math
\delta_{i,c}=K_cu_{i,c}+G_ct_c-n_{i,c},\qquad
\delta_t=\sum_c E_c^H(J_cu_{i,c}+L_ct_c)-n_t,
\qquad E_{T,c}=J_c+T_cK_c,\quad E_{S,c}=S_c-L_c-T_cG_c.
```

记U_s为保存的`T_r_i`，Q_s为保存的`attributed_terms`，其中U_s=ΣE_c^H T_c(b_i−n_i)，Q_s=ΣE_c^H[T_c δ_i+E_S t_c−E_T u_i]。全局b_t、n_t只能在全局减一次，不能在incident-cell循环各减一次。

```math
\begin{aligned}
g_v&=b_t+\sum_c E_c^H T_cb_{i,c},& d_v&=\sum_cE_c^HS_ct_c-g_v,\\
g_f&=f_t+\sum_c E_c^H T_cf_{i,c},& d_f&=\sum_cE_c^HS_ct_c+\beta_t-g_f,\\
r_{v,t}&=b_t-n_t,&r_{f,t}&=f_t-n_t-\beta_t,\\
d_v+r_{v,t}+U_s&=\delta_t+Q_s,&
 d_f+r_{f,t}+U_s&=\delta_t+Q_s.
\end{aligned}
```

这是精确算术恒等式；实际以保存向量衡量闭合及相减/累加差。d_v用已存`task41_v4_d_volume_trace_col*`，d_f用V6 full_p6−full_reduced_rhs，不能用V3旧d替代。两种式子都保留，另报epsilon_rhs=f−b−beta以及 `(d_f-d_v)+(f_t-b_t-beta_t)`。在Bi=0且内部RHS相同的条件下，后者应只留下两条生产路径的数值累加差；不能把它先强行置零。

完整门仍使用原动态分母定义及冻结D0/D1，均限1e-11；forward限1e-11、native残差原门不变。归因闭合另外报告绝对范数、原D尺度和相对真实d的大小，不新增一个能取代原门的宽松“归因PASS”。若闭合余量仍与d同量级，无法宣称已可靠区分d的主导来源。

## 4. 最小执行：保存数组上的一次完整审核，不调用新FE

### P0：只修定义与消费路径

窄修改现有finalize与saved-checker中的残差定义，优先显式提供volume/full两种scope；生产者和checker各用原保存字段重新计算，不让checker仅调用生产者函数确认自己。原V6 report、NPY、hash和失败status不覆盖；新report绑定V6 producer、旧donor与新consumer源码。

复用已有saved-candidate service、原activation/ABI和监督收口；该路由必须拒绝意外进入owner/mesh/JIT/FFCx/evaluator/carrier/factor，不创建新的V7框架。当前主线没有数值求解授权解锁，不能因新checker正常退出就自动执行200q。

### P1：列和状态身份表先通过

| 对象 | 允许的绑定 |
|---|---|
| known、原b/f、原Bα | donor `afbe91e...`、同一列16030或48090、原alpha与map；不得重新制造RHS |
| donor j0/j3 | 各自storage、native_volume_action、native_volume_residual及hash严格成组；二者trace均须与known相同 |
| V6候选初始恢复 | `...qmetric_candidate_recovered_storage_col*`及其保存native residual；不是donor j0，更不是经过三次修正的j3 |
| V6凝聚作用/缩减 | V6 full_p6、full_reduced_rhs、d_volume、reduce_r_volume/full；不能混入旧V3或canonical输出 |
| V6归因累加 | 每列×donor j0/j3各三向量：T_r_i、delta_t、attributed_terms；V6的T/S作用于donor状态是有意定义，不是自动错误 |
| 局部小块 | reference与candidate raw/oriented、R/T/S及其方向分别绑定；不可用FFCx reference K/G/J/L配Gram candidate T/S后称为同算子缺陷 |

重开受影响文件并验证内容hash、字节、dtype、shape、来源与严格path containment；一次验证后在同一只读会话复用，不反复全目录扫描。需要的是已保存数组和两个稀疏Bα包，不再扫描363 GB carrier。field storage 18,501,024行、active trace 5,688,000行、joint 5,752,120行、port64,120行；用原映射验证，不靠长度相同猜身份。[R3]

Bα的原行已按原MPC处理：通过`active_original_rows`的唯一逆映射scatter到active，不能再乘一次E^H、相位或共轭。局部未约束物理trace则使用原E_c展开、E_c^H组装；slave storage为零不等于物理slave trace为零。重复原行若生产约定允许，仍按原add-at累加，不能集合去重丢值。

### P2：先验证缺项，再分解真正的d

按每列×两个donor状态共4组，有界chunk执行以下检查，返回后即保存新报告：

1. 重现原action与初次恢复数值。复算p6/reduced port一致性及trace差，old arrays前后hash不变。两列action仍FAIL，是后续归因的固定事实。
2. 重现C_legacy，随后直接计算C_legacy−beta_active，以及第3节volume/full两条正确闭合。报告范数、最大行、复数方向/内积、支撑内外误差；不能只以“198≈B范数”定案。使用真实保存Bα，不用norm比例或拟合系数从C中减去某个向量。
3. 对每组保存的`reduce_r_volume`，独立比较 `rho_v` 与 `(b−n_s)_active+U_s`；前者来自生产reducer，后者来自保存raw-cell累加，是比“同一公式重复一次”更独立的交叉检查。再比 `d_v+rho_v` 与 `delta_t+Q_s`；full版本配对检查，保留原f−beta相减误差。
4. 重构诊断预测 `d_hat_s=delta_t+Q_s-r_v,t-U_s`，与同列d_v比较；j0/j3的d_hat应解释同一t下的同一个凝聚差，不比较候选初始恢复为j3。检查4组状态互换的负例会失败。
5. 对delta_t、Q_s、r_v,t、U_s报告原D尺度与相互抵消，不把范数相加当实际向量和。先计算闭合不确定度，再判断差异是否主要来自native/local作用、残差缩减、消元组合或尚未解释的状态/累加错误。

只需读取现有NPY进行上述检验，无需重新获取现场已销毁的348 GB级LU/R/T/S owner。若同一生产cache的值在保存前已丢失，状态必须写MISSING，不许用旧canonical类冒充。

### P3：仅在现有局部块上进一步分解

V6保存的是全域三类累加向量和少量局部完整块，并非全部28,000份K/G/J/L/T/S/LU。Q_s已经把Tδ_i、E_S t、−E_Tu_i相加；不能从三个标量局部范数或全局Q唯一恢复三个全域向量。

先在已保存的八键reference/candidate张量和R/T/S上做同输入代数，必要的小型GETRS只读已保存LU且复制为可写int32 pivots。完整owner不得重建。旧两cell26762/26897仍仅是局部见证；V6最大active误差行已变为4,766,937，不能继续假称旧主导行5,458,716代表新全域。利用现成全域map找新主导行的所有incident cells，检查它们的数值块是否真的已保存。

若需要的全域分项或某incident-cell块不在已有证据中，输出最小缺失清单：cell/key/producer、需要K/G/J/L还是T/S、所检验恒等式、预计如何用只读局部数据补足。**本轮不因此自动重建候选、retabulate全网格或补扫carrier。**全域归因不足时如实停止在已知边界，不能把局部改善提升为全域根因。

## 5. 必须区分两个出口

**归因定义修复成功：**旧198量级是否被保存Bα向量解释，正确闭合的剩余量和各状态一致性得到量化。它只关闭“诊断公式失配”，不改变原action向量。

**科学正确性关闭：**真实生产算子/缩减/恢复的受影响实现被定位并修复，原两列及受影响恢复通过原门，独立native/checker闭合。V7当前没有这项资格，也不授权以归因闭合代替它。

由于V6的原p6/reduced-RHS数组已独立确认超门，单独修checker不会使它们变成PASS。下一次需要数值重验时，必须先给出从本轮saved-only结论导出的具体最小生产修改和数据需求；不允许无依据再构建7小时，也不允许将已销毁owner描述为可继续精化。候选初始恢复0次额外修正的事实保留，donor三次修正PASS不转授，不盲加第4次。

普通路径、名字、字段或正确公式接线问题，在本范围内定向修复后继续saved-only审核；只在真实身份损坏、缺关键数组、非有限、资源/时间门或无法解释的闭合差处停止相应结论。不得因为一个普通接口bug整轮停审，也不添加新的PC/精度路线。

## 6. 资源、时间、测试与输出

沿既有`fenics-ws:/home/fenics/Projects/laptop_share`、complex128/int32、MPI1/math1、1.5 TiB task cap、64 GiB host reserve、task reserve0、task swap0；PSS未采样仍为null。saved-only实际工作集要有界，逐列逐state chunk读取；不把mmap页计为零。16 GiB证据配额和2 GiB磁盘余量不变，新旧路径按真实backing计一次，不复制315份旧数组或存四份稠密B。

优先只持久化新闭合差与小型表/来源，beta可继续引用原稀疏帧。所有文件hash验证一次后在同会话使用；新report/原向量的身份绑定明确。required checker继续受原监督和截止约束，不裸启动取消保护。

当前V6窗口，而非旧V3窗口：T0=`2026-10-20T10:21:59.261754681Z`，数值截止`2026-10-21T10:01:59.261754681Z`，总截止`2026-10-21T10:21:59.261754681Z`；对应新加坡10月21日18:01:59及18:21:59。审阅期间查到当地07:03:49，数值墙钟上界当时约10小时58分；该数不能当启动余额。接收/冻结/启动均读取现有账本、UTC和monotonic的更紧余额，不复制历史余额、不刷新T0。

本轮只是旧窗内的必要保存数据审阅和窄修；未到期且原资源可用即可连续执行，不另问相同主机/cap。若实际已到截止，停止新增受监督数值审核并按总截止收口；过总截止后新执行窗须一次明确授权，不自动续期。新日期/源码只改变consumer，不重署旧producer。

定向测试仅三类：①非零Bα、复MPC、非Hermitian块和非零消元缺陷的独立块代数，旧式必须显示B漏项；②j0/j3/candidate状态混配、旧d冒充新d、两次MPC/错相位的拒绝；③现有saved service入口无FE/owner/evaluator/carrier/factor调用、能保存数值FAIL与缺项。不要全仓pytest、不重装环境或重构目录。

修改最小范围为现有attribution finalize、saved-checker、相关fixture及必要参数传播；实际脚本命令由现有prepare/service生成并轻量验证，不把审阅文本中的伪CLI直接运行。用小fixture实际穿过被修改的路径，避免再只测helper而漏掉入口。

交`response_v7.md`及现有outcomes/run_index/两级总账更新，报告优先回答：B遗漏的实际向量检验；四组正确闭合及仍不能解释的尺度；donor/候选恢复各状态；原action FAIL是否保持；全域能分到哪一步、还缺什么最小数据。保留旧失败和unknown费用；父子不重复计费。只写本分支，不合并master、不将本轮归因修复宣称完整场/2TB/48h/最终精度PASS。

## 7. Codex 接续摘要

```text
继续Task41extra，读取review_report_v7.md。结果base=
bc305e02861968d9c790472a85af67acf42fbc8f；V6生产210fbbf271faa14c62ac30153b80332d0e645982，
旧donor afbe91e5947ed18fb74d7105097e129c1b8b4cc7，V6 checker 89e1e42114870ba1db752dfaf6d893ad13f923d6。

本轮saved-only，不重建28,000键、不生成/扫描carrier、不跑A1/A2、200q或FGMRES。
先修Task41V5VolumeAttributionAccumulator.finalize和saved checker同一遗漏：
r_t用了native_rhs-native_volume_action，却漏减Balpha。
d是含端口的完整凝聚差，delta_t/Q来自体积；必须用匹配的完整残差
f-N(u)-Balpha，或整套volume d_v与b-N(u)。两套都按review公式独立核验。
不修改旧NPY/报告，不把Balpha从原p6-reduced差向量里扣掉。

先用原保存Balpha、active map逐向量核C_legacy-beta；不是只对范数。
保留j0/j3 donor与V6初始恢复的明确身份：V6恢复forward仍FAIL、额外修正0次；
旧donor三次PASS不能转授。V6 T/S作用于donor j0/j3本身是合法的诊断定义。

只读复核原两列action、candidate恢复；再对每列每个donor state比较：
1) C_legacy与Balpha；2) corrected full/volume closure；
3) 已存reduce_r_volume与r_v,trace+T_r_i；
4) d_v+reduce_r_volume与delta_t+attributed_terms；
5) 两state得到的d_hat及原d的一致性。
保留epsilon_rhs、复向量相消及绝对/冻结D尺度；全局b_t/native trace只减一次，
Balpha原行只重编号，不再次MPC或共轭。full action/forward 1e-11不改。

现有174数组+141 donor+全域maps足够做上述第一轮；Q内各项没分别保存时
不得从norm反推全域分量。少量局部核验只使用已存同身份candidate/reference块，
不混用FFCx原块与Gram T/S后称同算子。最大active row为4766937，先由保存map
找全部incident cells；缺数值块则报最小缺项，不自动retabulate全网格。

源/状态/公式小fixture和实际saved service调用链通过后冻结，受监督完成一次
保存审核。普通接口bug定向修复继续，不全仓测试、不造V7框架。
归因闭合不等于action通过；旧d既已超门，本轮不能自动解锁后续求解。
输出具体最小生产修复依据或最小缺失证据，再决定下一数值验证。

沿原V6窗口：数值2026-10-21T10:01:59.261754681Z，总10:21:59.261754681Z；
读真实余额，不用旧V3截止、不刷新T0。既有主机/cap/reserve/ABI/线程/任务swap0、
16GiB证据和2GiB余量不变；已截止不启动，需新窗则另取明确授权。
主控集中提交同一分支，response_v7先给四组闭合与错误定义的实际证据，
再列测试。保留全部旧负结果、费用与UNKNOWN，不合并master。
```

## 固定证据入口

- [R1 response_v6](https://github.com/Rookie1234567/MyFEniCS/blob/bc305e02861968d9c790472a85af67acf42fbc8f/docs/task41extra_phi90_p50x50_g17x20/response_v6.md)
- [R2 V6 compact](https://github.com/Rookie1234567/MyFEniCS/blob/bc305e02861968d9c790472a85af67acf42fbc8f/docs/task41extra_phi90_p50x50_g17x20/outcomes/b0_v6_actual_qmetric_full_action_failed_20261021.json)
- [R3 174-array hash index](https://github.com/Rookie1234567/MyFEniCS/blob/bc305e02861968d9c790472a85af67acf42fbc8f/docs/task41extra_phi90_p50x50_g17x20/outcomes/b0_v6_actual_qmetric_hash_index_20261021.json)
- [R4 run index](https://github.com/Rookie1234567/MyFEniCS/blob/bc305e02861968d9c790472a85af67acf42fbc8f/docs/task41extra_phi90_p50x50_g17x20/outcomes/run_index.json)、[summary](https://github.com/Rookie1234567/MyFEniCS/blob/bc305e02861968d9c790472a85af67acf42fbc8f/docs/task41extra_phi90_p50x50_g17x20/outcomes/summary.md)、[test_summary](https://github.com/Rookie1234567/MyFEniCS/blob/bc305e02861968d9c790472a85af67acf42fbc8f/docs/task41extra_phi90_p50x50_g17x20/outcomes/test_summary.md)
- [R5 V6 preparation / 指定权威与实际入口](https://github.com/Rookie1234567/MyFEniCS/blob/bc305e02861968d9c790472a85af67acf42fbc8f/docs/task41extra_phi90_p50x50_g17x20/outcomes/v6_preparation.md)
- [C1 observe/admit/finalize](https://github.com/Rookie1234567/MyFEniCS/blob/bc305e02861968d9c790472a85af67acf42fbc8f/src/solvers/task41_v4_volume_only_audit.py#L193-L425)
- [C2 saved-checker的同一残差定义](https://github.com/Rookie1234567/MyFEniCS/blob/bc305e02861968d9c790472a85af67acf42fbc8f/src/runners/task41_p0_checker.py#L3480-L3575)
- [C3 候选恢复与完整/体积分支](https://github.com/Rookie1234567/MyFEniCS/blob/bc305e02861968d9c790472a85af67acf42fbc8f/src/solvers/task41_v4_volume_only_audit.py#L1560-L1950)
