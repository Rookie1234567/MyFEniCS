# Task41extra Review V11：否决当前全域候选，复用保存向量完成交叉归因与失败收口

## 0. 裁决、身份和唯一下一步

**V9 的 `same_lu_rhs_solve` 已完成一次真实全域检验，但不是合格生产修复：两列完整 action 均 FAIL。接受局部筛选、完整构建和已保存负结果；不把终态 checker 缺口当成数值失败的原因。下一轮唯一执行包为“V6/V9 完整保存向量交叉分解＋新最大行87567的有界生产重放＋失败终态监督审核”。禁止再次盲建28,000键、重扫carrier或启动200q。**

本轮对科学候选给出明确否决，而不是预先指定另一种未经证实的算法。局部更接近并不能保证全域更准确；先用已经付费取得的两侧完整输出，查明全域恶化发生在哪一侧。允许修正确定的失败收口接口；只有证据直接定位到某个数值操作后，才提出一个有局部重放支持的生产修复，不自动进入下一次全域实验。

| 身份 | 冻结值 |
|---|---|
| 仓库 / 唯一执行分支 | `Rookie1234567/MyFEniCS` / `task41extra_phi90_p50x50_g17x20` |
| 本次结果 HEAD | `a1db9bcd1e7a82293de1490feba9e624fa9e839f`，审阅时远端回读一致 |
| V9 科学 source / run | `59722cca5e35eac65efead9fd27f7d7fc0c70419` / `20261022T052401.200732Z` |
| 原 review | V9 `b24b6ce6577225af7fb03e4a62bef80126efc9b8`；V10 `9e9ecf0e0ee7f658fc7d84e7302d8df936e7ca0f` |
| V6 对照生产者 | `210fbbf271faa14c62ac30153b80332d0e645982`；结果索引沿 `bc305e02861968d9c790472a85af67acf42fbc8f` |
| 原 donor | `afbe91e5947ed18fb74d7105097e129c1b8b4cc7` / `20261019T053402.514018Z` |
| 审阅日期 / 类别 | 2026-10-23，Asia/Singapore；离散算子一致性、数值稳定性、失败收口 |
| 目标 | 原0.7 nm、50×50×140 nm域、居中17×20×120 nm Si、方位90°、p6/10×200×14；完整Full3D场、十进制2 TB含余量、任务swap0、必要冷流程≤48 h |

本次读取 response_v9、V9 compact/独立audit/service与分阶段账、准备落实记录、测试/运行索引及实际源代码，结合完整V9/V10任务约束审阅。V10至当前的提交差异未修改根/docs治理、task.md或旧review；科学source至结果HEAD仅有文档/证据更新。本Chat只提交本报告，不运行工作站、不重新读取其大型NPY；下述数值取自远端原记录，比例/字节另标推导。没有项目测试或实时进程观察声明。[R1][R2][R3][R4][R5]

## 1. V9结果及V10落实裁决

| 对象 | 接受范围 / 尚未闭合边界 |
|---|---|
| V10三项窄修 | 源码已消费返回correction，局部筛选区分旧分组与生产累加次序；拥有owner的action在改变销毁状态前检查其他J借用者。相关定向回归与真实saved-local READY可接受；无需再重做这些准备。[R6][C2][C3] |
| 真实生产入口 | actual owner策略/J、compact两列和独立compact checker已实际使用，不再称“只是未接通生产”。同进程owner交接在源码中存在，但本场数值失败前未到成功交接、reference或target，不能写成真实交接资格通过。 |
| 全域action | col0动态/冻结误差2.674977063720297e-10 / 2.6749770637124157e-10；col1为5.613598120037966e-10 / 5.613598120039712e-10。原门1e-11，均FAIL。[R2] |
| 恢复 / 后续 | candidate恢复为NOT_RUN_ACTION_GATE_FAILED；不是新增恢复FAIL，也不能继承donor PASS。200q、factor、参考、FGMRES、A6、物理场全部NOT_RUN。 |
| 两种checker | compact独立audit完成、errors=[]，忠实确认action FAIL；正式service终态checker因缺numerical-output目录未执行。两者不可互换。[R3][R4] |
| 数值候选结论 | 当前同LU缩减不能单独关闭全域门；不采用为合格默认，不再原样全域重跑。保留显式实验分支和全部负证据。 |

V6冻结尺度误差为1.7183209126709868e-10 / 3.6180522433957604e-10；V9分别约为其**1.55674倍、1.55155倍**（推导）。这说明整体没有改善；在逐侧身份与向量对比前，还不能把增长全部归因于GETRS、J乘法或某个累加循环。

### 1.1 为什么不再把一个最大行改善当作全域成功预测

V9两列绝对L2为5.953111308801364e-7、1.2492954342769817e-6；最大分量为4.714842990596683e-9、1.018211453698345e-8，均在active行87567。由已记录数值计算，该单行仅占对应误差平方和的**0.0062726%和0.0066427%**。即使只将它精确修为零，整体L2也仅下降约0.00314%/0.00332%。这是数学推导，不是新数组实测。[R2]

因此87567是机制探针，不是全域误差的主要总量。下一轮必须先有全域保存向量分解和误差分布，再用该行验证具体操作；旧4766937局部PASS不推广，新87567局部PASS同样不推广。

### 1.2 成本按原口径保留

workflow父69966.90540991211 s；owner子68236.865869666 s；两列action子165.831110179 / 135.274287935 s。末次launcher累计85045.9879224967 s包含workflow，不再相加。tree RSS450117619712 B、cgroup450366337024 B、systemd449658327040 B分别报告；task swap0、宿主54页swap-in只作宿主观察，PSS未采样。J的87091200000 B只是派生载荷。[R1][R5]

当前没有完整全域GETRS/J/张量子计时。不得把约19小时全部归给Gram、LU、J新增或本次策略。只读检索现有进度/构建audit中已经存在的phase数据，能恢复就按原时间域引用；缺项保持UNKNOWN，不为补计时重建owner。研究累计费用、warm消费与最终必要cold流程分列。

## 2. 第一阶段：仅用保存数组，先分清全域变化发生在哪一侧

### 2.1 必须复用的精确输入

V9原run根：
`/home/fenics/Projects/laptop_share/results/task41extra_phi90_p50x50_g17x20/task41extra_b0_p6_phi90_07nm_iterative__full3d_iterative__mpi1__Mna/20261022T052401.200732Z/`

两份NPY均为[5752120,2] complex128，各184067968 B：

- `task41_p0_b0_v9_compact_candidate_full_p6.npy`，文件SHA256 `740eae4b52d810060e334e96a62979626a7f13fe0464cf86f87670bd98c9eaac`；
- `task41_p0_b0_v9_compact_candidate_full_reduced_rhs.npy`，文件SHA256 `ac5a86b9c06656d6d8461ec20db973ea8df0c6635a42af9d79d207b44362a55b`。

文件SHA与compact中的array-payload SHA分开，不混为同一hash。复用V6保存的full_p6/full_reduced_rhs、原donor known/native_rhs/native_volume_rhs、active/slave/maps、两份稀疏Bα、port_rhs、V6/V8局部块与exact-key清单。不读取363GB carrier，不做64,120模式遍历，也不重复验证未改变的A1/A2或恢复产品。只核本包真正读取的文件及依赖，旧producer身份与新consumer分开。

先确认两run的shape、dtype、列、known/RHS、active排序、MPC相位、Bα/H/mode次序及材料/积分/actual坐标语义。比较具体evaluator/kernel与cache身份，不仅比较实现名称。不同source允许，但不能默默认作逐位同算子；所有比较前提和发现的差异记录。V9 compact没有全量逐键数值hash，其他原始audit也未保存时明确为缺项，不由同名key推定旧LU/J仍存在。

### 2.2 分别比较完整输出，不直接从d猜根因

令y为保存完整作用（trace含S作用及Bα），g为保存缩减RHS。使用相同列和冻结D0=2225.481253487629、D1=2225.4807123031883，分块读取：

```math
 d_6=y_6-g_6,\qquad d_9=y_9-g_9,\qquad
 \Delta y=y_9-y_6,\quad \Delta g=g_9-g_6,
 \quad d_9-d_6=\Delta y-\Delta g.
```

逐项输出trace/port的norm、max/row、实虚分量、原尺度比和逐块平方和。计算最后恒等式的浮点余差；用独立的分块补偿标量累计检查norm/内积，不能把恒等式右侧写回任何原action数组。若y相同而g改变，才能把这一次跨run变化定位在缩减侧；若y也改变，先查S、输入、布局与作用次序，不把全部变化归给RHS候选。

计算两个明确标记的诊断交叉量 `y9-g6` 与 `y6-g9`，以及有符号能量关系：

```math
 \|d_9\|_2^2-\|d_6\|_2^2
 =2\operatorname{Re}\langle d_6,\Delta y-\Delta g\rangle
   +\|\Delta y-\Delta g\|_2^2.
```

单独记录该等式的实际浮点余差。交叉量只区分两侧变化及抵消，既不是新的生产输出，也不是新的PASS标准。分母固定，不能换成约1e9的未凝聚RHS范数。

分布只做一次廉价全向量统计：按固定连续row块累加误差能量，报告top行及top-k覆盖率、是否落在Bα支持或periodic slave闭包类别；使用现成映射时可增加方向/材料类别。无现成物理分类就保留未分类，不为图表构建FE。保留旧4766937、新87567的同列y/g/d和变化；若旧行局部筛选改善而它的真实全域d没有改善，应先追查重放身份/次序而不是继续用该筛选作预测。不要再保存一批全长差向量，只保存统计和必要索引切片。

## 3. 第二阶段：87567的最小完整incident重放，先证明能重现生产

### 3.1 数值块的准入范围

新87567是active编号，先由原active_original映射取得真实full-storage行，不猜原行号或cell数。优先使用现有全域映射，找齐E展开意义上的所有incident cells，包括周期slave贡献及同一cell多原行汇入的情况。若缺少所需整数映射，只复用V8的metadata-only路径补建；不得先构造完整数值owner再调用selected helper。

本轮仅一个新目标星形邻域，外加旧4766937已保存局部包作控制，不开始多行随机抽样。最多准入**8个新incident cells**的必要局部数值；实际完整关联数超过8则报告真实清单与费用，不能截断成“全部”，也不擅自扩大。附加证据预算见§6。

每个缺失cell只重建与V9同actual-qmetric/积分/方向的candidate K/G/J/L、同源LU/R/T/S，或读取已匹配的存量块；原图/输入/几何hash验证通过才计算。首次生产重放只需要candidate，不默认把每格昂贵FFCx reference也重做。能用现成reference块就用；确需区分local/native积分且缺参考时，最多对一个证据主导cell补一次原FFCx张量，并保存全部必要块。局部rank-1作用只有同样存在缺项且已指明用途时才补，绝不构造全surface/native owner。

旧进程已退出；新局部LU属于 `RECONSTRUCTED_SELECTED_CELL`，不称旧factor复活。若原V9逐键hash未保存，不能声称新块就是旧内存的逐位拷贝；必须用新块经原生产顺序重现保存的**y9和g9各自的目标行**，而不只重现d。差超过可解释的末次求值重放范围时标 `LOCAL_REPLAY_UNBOUND` 并停止根因结论，不放宽全域门。

### 3.2 保持真实生产次序的三列局部核对

从同一known trace、原native RHS与实际E开始，分别记录：S@t的完整局部向量及E^H投影；原stored_T的完整T@b_i；`same_lu_rhs_solve`实际返回的z与−Jz。b_t按原生产写入一次、再按cell/trace/MPC顺序累加；Bα在作用侧按原位置加入一次。端口输出不改。使用完整matvec后选行，不用选行乘法改变计算结果。

先复现新y9/g9，再比较在**同一新局部矩阵**下stored_T与same-LU的变化，避免把不同producer的矩阵混成策略差。j0/j3只能用于已配对的原生作用/残差分析；known、初始恢复、最终donor和本场未运行恢复不能混用。局部成功仍不代表全域成功。

记局部块K/G/J/L、原R/T/S和独立native状态n。对同LU缩减，正确的残差缩减也应使用同一solve路径；不能继续把T*r_i当作新reducer的精确结果。固定原RHS与trace，定义：

```math
\begin{aligned}
 &Kz_b\simeq b_i,\quad Kz_r\simeq r_i=b_i-n_i,\qquad
 \delta_i=Ku_i+Gt-n_i,\quad \delta_t=Ju_i+Lt-n_t,\\
 &r_b=b_i-Kz_b,\quad r_r=r_i-Kz_r,\quad E_R=KR+G,\quad C_S=S-L-JR,\\
 &d_{LU}+\mathcal R_{LU}(r)
   =\delta_t+C_St+J(Rt+z_b-z_r-u_i),\\
 &K(Rt+z_b-z_r-u_i)=E_Rt-\delta_i-r_b+r_r.
\end{aligned}
```

以上先按同一存储矩阵的精确代数定义；实际乘加、投影、RHS制造/相减余差另列。全域native trace只计一次，局部项再按E^H装配；不得逐cell重复扣全局b_t或n_t。公式只用于定位误差，不生成生产答案。需要r_i时读取原donor已保存状态的native内部作用，不重新跑旧恢复。

对新星形邻域保存上述有符号贡献，以及旧诊断 `T b_i+Jz_b=(J+TK)z_b+T r_b`，区分：原始local/native差、Schur/恢复缺陷、solve残差和最后投影/累加。宽算术只评估同一存储数据的求值敏感性，不替换complex128验收、不从norm反推向量。若只改变最后的诊断重组就变小，这不是生产修复。

### 3.3 本轮数值出口

**明确否决**当前单独same-LU替换作为足够的全域修复；保持旧默认与实验记录，不自动撤销源码或换PC。saved全域分解与绑定的局部重放完成后，必须写出一个可验证的原因边界：定位到哪项、证据覆盖多少误差能量、具体涉及哪个生产函数。若确有确定的状态/索引/漏项错误，可在原候选内做最小修正并用已保存局部包验证；不能仅凭局部改善再批准全域。

若数值误差来源仍混合，则给出本轮已排除项和精确剩余缺项，不再用“继续研究几何一致性”替代结果。不得在本包内尝试多个新消元算法、增加第4次精化、改输入/积分/精度/分母，或再次启动约19小时owner。真正新的数值方案和全域重验须依据本次可复算证据另行裁决；200q始终锁定。

## 4. 确定的生产修复：让数值FAIL也能走受监督终态审核

当前普通Task41 service沿run manifest的 `numerical_output_directory` 准备正式checker输入，并要求正式numerical summary等成功/完整场路径；本run在action gate之前没有这些目录。compact auditor则可读取现有数组并正确返回FAIL。这是两个不同入口，修compact函数不自动修复service收口。[C4][R3][R4]

最小修改是在**现有service/Task41 checker**的产物选择边界加入“完整compact action产品、数值未通过”的窄分支，在验证成功物理输出路径之前选择它；用本run的run_manifest、run_summary、worker阶段信息、compact JSON及两个NPY构造hash-bound失败审核输入。不得创建假的官方输出目录、复制旧run snapshot，不能把成功路径的缺文件检查整体删掉。

该分支仍经过原ABI、source/producer区分、paths/hash允许清单、required-checker supervisor、资源与closeout截止；以现有compact独立计算为核心复算两列并核验NOT_RUN恢复原因。输出至少区分 `audit_completed`、`data_integrity`、`action_passed`、`recovery_status`、`official_result` 和执行退出分类。**审核完成且数据完整地确认FAIL是合格的负结果收口，不是scientific PASS；旧worker4/service3事实保留。**损坏/跨run/缺真正数组则拒绝，不仅相信compact status。

本run原窗口已结束，原terminal checker永久记录NOT_RUN。新窗口内可以做一次独立的 `retrospective_failure_terminal_audit`，绑定旧producer和新consumer/source/时间；新收据补充事实，但不能倒填旧窗口、修改旧receipt或称“当时终态checker已执行”。失败snapshot只描述实际存在产物，不为补收据重算PDE。

先用无物理输出目录但有完整失败数组的fixture走真实service选择→授权→watchdog→checker；资源/进程可替身化，选择、身份、负结果输出不得全部mock。另加坏hash/跨run拒绝与既有成功路径不变的最少回归。正式补审仍须实际监督收据，不能将fixture或裸CLI写为已通过。

## 5. 顺序、停止条件与交付

1. P0：确定失败审核分支与saved交叉比较入口，完成直接相关fixture、冻结source和真实命令。无需全仓测试/新框架；普通接口bug同范围定向修复。
2. 获准新窗后，先对本run做受监督的补充失败审核及§2完整保存向量比较；hash/输入身份不闭合则只停相应比较，不删除旧资格。
3. 只有缺失项真的阻止定位时，按§3完成87567全incident元数据和有界局部补算。每个张量/映射完成即保存，后续checker问题只重读产品，不重新生成。
4. 交一份能够明确否决或支持某个具体下一修复的报告；本轮不重建全域、不跑200q，不以终态审核完成或局部PASS改写action FAIL。

Codex写 `response_v11.md`，注明“审阅V9执行及V10准备落实后的窄续作”；保留正式 `response_v9.md`。更新现有summary/run_index/两级账，不新建重复权威文件。准备文档中的历史NOT_RUN/待批准文字若仍作当前状态，增加时间戳和链接澄清，不删历史记录；run index的 `not_run: ["0.7nm"]`应细化为完整场/完整求解未运行，避免把已经发生的0.7nm组件计算抹去。

首次提交为当前service失败分支及saved对比/相关测试；第二次为真实有界证据和结果。主控集中提交同一分支，不amend、强推、修改master/其他任务或删除负结果。错误源、修复源、复核源分别绑定。未完成的数据、缺失性能项及工程准备保留UNKNOWN。

## 6. 新固定窗口与资源

旧V9 T0为2026-10-22T01:12:42.209257168Z，数值截止2026-10-23T00:52:42.209257168Z，总截止2026-10-23T01:12:42.209257168Z。2026-10-23新加坡09:21:05时钟查询已晚于总截止（新加坡09:12:42），不能继续消费旧余额。

**新窄包提案：总21600秒（6小时），数值20400秒、收口1200秒，PENDING_USER_APPROVAL。**范围仅saved审核/向量分解、必要metadata和最多8个新incident cell候选块及至多1个新FFCx参考块；不包含全域owner、carrier或200q。先做代码准备；正式工作站数据计算从获准后的第一项必要准备起计T0，一次授权后在同包内继续，修bug不刷新时钟。本review不是用户批准，不自动创建新窗。

沿原主机与目录、task cap1.5 TiB=1649267441664 B、host reserve64 GiB=68719476736 B、task reserve0、complex128/int32、MPI1/math1、exact MUMPS、task tree/cgroup swap0，PSS默认不采样；实际host/ancestor/磁盘可用量取更紧者，不影响其他任务。

原累计证据14990282640 B，16 GiB上限剩余约2189586544 B（由记录推导，启动实读）。本窄包新输出最多512 MiB，并受实际剩余额度及2 GiB磁盘底线更紧约束。只读mmap分块，最多保存小型统计、行切片和选中局部块，不新增全长差向量、不复制已有约15GB数据。selected cell全张量与分块视图避免重复持久化；LU pivots重开时按原安全规则复制可写int32，旧文件保持只读。

每个service父时间、只读扫描/局部生成/审核子时间及峰值范围分别记录；新事后审核成本不回填旧service。19小时旧owner、7.79小时旧carrier等不同版本阶段不可拼成已测完整cold成绩；也不能从较低RSS预报最终2TB/48h已可行。最终全域action/recovery、q/native/因子、全参考、A6/物理及网格/mode精度门均不变。

## 7. 给Codex的连续执行摘要

```text
读取同分支review_report_v11.md，base=a1db9bcd1e7a82293de1490feba9e624fa9e839f。
V9 same_lu_rhs_solve已真实全域FAIL，不批准原样再次构建；V10三项窄修保留。
本包只有失败终态审核、V6/V9保存向量交叉分解和条件87567局部重放。

先修现有service的数值FAIL分支：用本run真实manifest/summary/compact/两NPY
选择受监督审核，不要求成功物理输出目录；不造目录、不拿旧run snapshot。
新审核分列audit完成、数据完整、action FAIL、recovery NOT_RUN及official=false。
原terminal NOT_RUN不可回写；新补审绑定独立consumer/source/window/费用。

读取V6与V9完整y/g及原donor/maps，核同列/编号/物理/积分/evaluator身份。
分别算Delta_y、Delta_g和d9-d6，原冻结分母不变，trace/port分开；
报告有符号内积、误差能量分布、top-k覆盖率和交叉诊断y9-g6/y6-g9。
先回答是作用侧、缩减侧还是双方变化，不能只用candidate/reference gap。
不写新的全长差数组，不重扫carrier；两份原NPY hash见review第2节。

原最大行87567只占L2误差平方和约0.0063%/0.0066%，不能用一行改善推全域。
先由保存active map取原行、找齐全部MPC incident贡献；缺metadata才窄补。
只补确缺的87567 incident cells，最多8个candidate局部块；FFCx至多1个且有依据。
不先构造完整owner。保持原actual-qmetric、坐标/方向/kernel和LU公式；
新重建块必须重放保存y9与g9各自的行值，不能只匹配d或假称旧LU仍live。
先生产序分别重放S@t和−J solve(K,b_i)，b_t/Balpha/MPC各一次。
同LU残差缩减需同LU，不能用旧T*r当新reducer精确输出；按review恒等式
区分原生/局部差、solve/Schur缺陷和最后累加。宽算术仅诊断，不改生产答案。

当前候选明确不合格；本轮给具体生产函数、因果证据及覆盖边界，
没有证据不改第二算法。局部PASS/补审完成不解锁全域或200q。
普通路径/字段bug定向修复并复用产品，不重算已完成阶段。

旧窗已结束。新6小时包21600/20400/1200秒待用户一次明确批准；
沿原主机、1.5TiB/64GiB、ABI/线程/swap0和16GiB证据上限，新增证据最多512MiB。
不自动启动或刷新T0。只跑修改相关fixture，不全仓测试、不建V11框架。
提交response_v11与实际路径/hash/审核/归因/成本到同分支，不合并master，
不重跑A1/A2、carrier、64120模式、旧恢复或28000键；不宣称完整场/最终精度/2TB48h通过。
```

## 固定证据与源码入口

[R1]: https://github.com/Rookie1234567/MyFEniCS/blob/a1db9bcd1e7a82293de1490feba9e624fa9e839f/docs/task41extra_phi90_p50x50_g17x20/response_v9.md
[R2]: https://github.com/Rookie1234567/MyFEniCS/blob/a1db9bcd1e7a82293de1490feba9e624fa9e839f/docs/task41extra_phi90_p50x50_g17x20/outcomes/v9_closeout/task41_p0_b0_v9_compact_volume_audit.json
[R3]: https://github.com/Rookie1234567/MyFEniCS/blob/a1db9bcd1e7a82293de1490feba9e624fa9e839f/docs/task41extra_phi90_p50x50_g17x20/outcomes/v9_closeout/task41_p0_b0_v9_compact_independent_check.json
[R4]: https://github.com/Rookie1234567/MyFEniCS/blob/a1db9bcd1e7a82293de1490feba9e624fa9e839f/docs/task41extra_phi90_p50x50_g17x20/outcomes/v9_closeout/task41_p0_service_receipt.json
[R5]: https://github.com/Rookie1234567/MyFEniCS/blob/a1db9bcd1e7a82293de1490feba9e624fa9e839f/docs/task41extra_phi90_p50x50_g17x20/outcomes/records/v9_run_stage_ledger_20261022.json
[R6]: https://github.com/Rookie1234567/MyFEniCS/blob/a1db9bcd1e7a82293de1490feba9e624fa9e839f/docs/task41extra_phi90_p50x50_g17x20/outcomes/v9_preparation.md
[C1]: https://github.com/Rookie1234567/MyFEniCS/blob/a1db9bcd1e7a82293de1490feba9e624fa9e839f/src/solvers/task41_v4_volume_only_audit.py
[C2]: https://github.com/Rookie1234567/MyFEniCS/blob/a1db9bcd1e7a82293de1490feba9e624fa9e839f/src/solvers/p6_cell_condensed_action.py
[C3]: https://github.com/Rookie1234567/MyFEniCS/blob/a1db9bcd1e7a82293de1490feba9e624fa9e839f/src/runners/task41_p0_checker.py
[C4]: https://github.com/Rookie1234567/MyFEniCS/blob/a1db9bcd1e7a82293de1490feba9e624fa9e839f/scripts/task40_v20_service_workflow.py
