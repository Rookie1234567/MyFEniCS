# Task41extra Review V16：先量出全域余差的结构，不再盲目构建owner

## 0. 裁决与固定身份

**接受V15的完整两列产品及修复后的独立审核：有界同LU校正确实改善全域一致性，但两列仍不合格。否决原样再次构建28,000键。本轮唯一执行包是“保存向量差分与误差能量分布＋已有star终态交叉绑定＋新探针缺项清单”；默认不新增积分、分解或GETRS，不修改生产数值算法。**

要消除的blocker：目前知道改动发生在RHS缩减侧，却不知道剩余误差是否集中、旧局部机制是否仍代表当前余差，以及新最大行是否有足够数据可重放。先用已经支付全域成本取得的产品回答这些问题，不能因最大行换了就重新走一次长构建。

| 身份 | 固定值 |
|---|---|
| 仓库／执行分支 | `Rookie1234567/MyFEniCS`／`task41extra_phi90_p50x50_g17x20` |
| 被审结果HEAD | `3b2b8f683eebfa8ec86503378913c67a29dae086`；审阅回读与用户一致 |
| 科学source／run | `3b8e7f5327ce1905deae658bd0bbb0fa94dba5ad`／`20261026T081134.584306Z` |
| 独立checker source | `c14dcdb4f3df5e1f488de6747008edf6d58c0c3f` |
| Review V15 | `611f3497c4b977b10e783444bcd9c9a8aea9a9c5`；原文blob `16976bf1bb1ce4690e4ff6e83187f0acc874abac` |
| 日期／类别 | 2026-10-27，Asia/Singapore；算子一致性、保存数据分析、执行控制 |
| 冻结目标 | 0.7 nm、50×50×140 nm域、居中17×20×120 nm Si、方位90°、掠角1°、S、p6、10×200×14、64,120模式；最终完整冷流程≤48 h、十进制2 TB含余量 |

本Chat核对远端response、compact、原始两列audit、独立checker、索引、当前源码和修复提交，并继承未变task/根与docs规则。没有登录工作站、读取其NPY或运行项目测试。本报告中的数值是远端实测或明确标出的算术推导；提交review不构成新窗口批准或新科学PASS。[R1] [R2] [R3] [R4]

## 1. V15正式接收范围

| 项目 | 结论与边界 |
|---|---|
| 全域构建 | 28,000 actual-qmetric对象完成；旧owner已退出，不假称仍存活 |
| 两列action | 绝对L2 `1.2824501485040357e-7`／`2.6981026336315675e-7`；冻结相对差 `5.762574483583106e-11`／`1.2123684643571926e-10`，均高于 `1e-11` |
| 跨run变化 | 新y与V9对应列逐元素一致；port行不变；观察到的改善来自g的trace侧。这不证明y已经准确，也不证明剩余全部来自g |
| 策略计数 | 56,000初解＋112,000校正，168,000 GETRS；实际执行了两列的二次校正。总计数不替代逐cell精度资格 |
| 独立审核 | `audit_completed=true`、`data_integrity=true`、`NUMERICAL_FAIL`、`errors=[]`；不是checker崩溃 |
| 恢复与下游 | 恢复 `NOT_RUN_ACTION_GATE_FAILED`；200q、因子、完整参考、FGMRES、A6和官方场未运行；旧donor PASS不转授 |
| 控制与清场 | 原worker exit−9、producer_cleanup_passed=false保留；最终descendants_cleared=true另列，不能合并成正常运行成功 |

错误下游是独立的工程失败：helper已返回验收终态，外层未传播而继续surface/carrier。提交 `f36909b4850eab61f1fa0b9c51bec63f018fbaf7` 已把真实外层分支改为检查并返回终态，相关fixture覆盖PASS/FAIL/PARTIAL及finally。接受这项窄修，不为它重建owner。原错误surface约671秒、carrier仅64/64,120模式，不能写成完成全carrier，也不能从历史账删除。[C1]

摘要修复同样接收：artifact digest按producer的shape/dtype头加payload计算；旧recovery-state raw digest保持原定义。原失败审核不覆盖，新只读审核不重署名旧source。下一轮复用该读取规则，不再安排重复终态补审。[C2] [R4]

## 2. 为什么改善4.6倍仍不够：已经知道与尚不知道

校正只改内部RHS解与其投影，未重算S/R/T/J或改变原native RHS。源码仍以binary64乘积形成残差，再用fsum改善累加；它不会自动消除乘积舍入、Schur形成误差、native/local差异、原RHS制造误差或最终组装相消。上述都是待区分项，不是已确认的剩余根因。[C3] [C4]

全域新y不变只证明本次两个输入上的作用输出不变。一个固定存在于y或native RHS中的差异，也会留在新的 `y−g` 中。不能据“Δy=0”宣布S/native已经正确，再把全部剩余责任交给GETRS。

新最大行1622464的两个最大分量为 `8.314219327161011e-10`、`1.674771706629432e-9`。由它们与全域L2推导：[R3]

| 派生量 | 列0 | 列1 |
|---|---:|---:|
| 当前相对误差／原门 | 5.7626 | 12.1237 |
| 最大单行占当前误差平方和 | 0.004203% | 0.003853% |
| 只把该行置零时L2最多相对下降 | 0.002102% | 0.001926% |
| 若其余行不变，要过门至少需消除的当前误差能量 | 96.9886% | 99.3197% |

最后一行是假设所修行误差可完全消除的理想必要覆盖量，不是实现建议，更不允许把差向量清零。它表明：单行可暴露机制，但不能作为新全域试验的代表性依据。下一轮必须量出top-k和类别的实际能量覆盖，再选择探针；旧87567或4766937的比例不能移用到新行。

## 3. 唯一执行包A：保存产品上的全域差分与能量地图

### A0. 统一只读视图，不迁移旧数据

V9的y/g各是 `[5752120,2]`，V15改为四个 `[5752120]` 数组；四个新文件合计368,136,192 B，精确路径/hash见R2/R5。读取器按明确layout和column提供相同的列视图，不直接比较两种NPY文件SHA来证明列不同，也不复制成新的全矩阵。文件SHA、带shape/dtype的artifact摘要、旧raw-state摘要按各自定义核验，不混用。

绑定同一known、native/full-volume RHS、active/slave maps、模式/Bα、材料、积分、evaluator/cache和原分母。只对实际消费的输入核验一次；不是重新运行已通过的全套terminal checker。V6/V9已接受比较可继承，核心新增工作是V9→V15；V6只作补充参照，不重做旧V11分析。

### A1. 一次分块比较形成带符号的变化账

令 `d_k=y_k−g_k`、`s=g15−g9`。分别计算Δy、Δg，先验证当前保存列的绑定，再记录下式的实际浮点闭合余差：

```math
\Delta d=\Delta y-\Delta g,\qquad
\Delta y=0\ \Longrightarrow\ d_{15}=d_9-s,
\qquad
\|d_{15}\|_2^2=\|d_9\|_2^2+\|s\|_2^2-2\operatorname{Re}\langle d_9,s\rangle.
```

每列报告trace/port的绝对L2、固定D归一化值、最大行、复内积、改好/变差行的数量及能量，而不只报告一个改善倍数。读取分块固定，统计求和可用稳定标量累加；不得改变保存向量或科学判门算法。上式是诊断恒等式，不用其余差直接宣称生产正确。

从当前 `abs(d15)^2` 提取top-k覆盖，至少给k=1/10/100/1000/10000及达到50%、90%、99%能量的最小行数；同时给达到第2节理想必要覆盖量的行数。只保存有限top行/分组表，整向量差、排序副本可在内存中有界处理后释放，不新增全长复数差文件。列间比较使用统一选择集（两列top行并集），不能为每个方案挑最有利的行。

不拟合一个系数去重新组合y/g，不将 `y9−g15` 或其他交叉量包装成新解；原动态及冻结分母和 `1e-11` 一直保留。

### A2. 不重复计数的材料/方向/MPC分组

优先利用已有cell maps、trace expansion、tag/方向和actual-key清单，建立每个active trace行的全部incident集合，包含周期slave经E贡献的cell。旧局部metadata只覆盖旧行，不能冒称覆盖1622464。

材料边界上的一行可能属于多个材料；**不把同一行的完整误差能量分别记给每个cell或材料再相加。** 使用互斥的incident签名分组，例如“全部关联tag的集合＋方向类别集合＋关联数＋是否有非平凡MPC”，每行只进入一个组。按组报告行数、总能量、能量占比、每行均方量、V9/V15变化与有符号交叉项。材料/方向表均是统计关联，不是误差因果分摊。

方向permutation表示离散基函数/编号变换，不等于物理波的传播方向。几何宽度/位置分箱若有帮助，只用于标注，不能重新round actual几何或恢复canonical数值共享。

全域整数map可以扫描一次，但不生成矩阵。必要字段缺失时先查旧donor索引；确无完整可用映射，允许在已批准的小包内一次metadata-only mesh/space/MPC补建，严格回读原编号/布局/hash，仅产生元数据。禁止调用先建立完整condensed owner的高层入口；无体积kernel、surface、carrier或LU。把这一步如实记为metadata工作，而非“完全无FE”。

## 4. 执行包B：把已有局部终态接回本次全域输出

不再重跑V14的两个star或Decimal资格。直接读取V14保存的初解/最终z、实际correction、S/J、原known/native RHS、MPC及既有lambda；候选算法、K/LU生成身份和输入必须一致。初态、最终态、j0/j3分别绑定；不能以旧donor恢复PASS转授。

对旧87567和4766937两个完整star，按**原生产顺序**独立重放S作用和g：b_t先写一次、各cell与trace/MPC次序不变、使用保存的最终correction、Bα只加一次。比较本次y15和g15的对应分量，分别报告实/虚差，不只匹配d。若不一致，先查source、布局、BLAS/线程和中间态；标明局部包未绑定本次，不为追求吻合更换累加顺序。

若能够绑定，这两份旧包就可用于分析“校正之后”仍存的误差，而无需再求解。只新增需要的最终态组合，不重复V13的8组完整归因或旧审核。对已有同身份lambda的cell，用最终z形成真实残差并复用其投影，保留伴随残差；没有lambda就不新增伴随解。

精确存储数语义下，对known内部场u、trace t，定义：

```math
r_f=b_i-Kz_f,\quad E_R=KR+G,\quad C_S=S-L-JR,\quad
\delta_i=Ku_i+Gt-b_i,\quad
\delta_t=\sum_c E_c^H(J_cu_{i,c}+L_ct_c)-b_t^{\mathrm{volume}}.
```

若完整RHS与端口拆分满足相应定义，则理想代数关系为：

```math
d=\delta_t+\sum_c E_c^H\left[C_{S,c}t_c+J_cK_c^{-1}(E_{R,c}t_c-\delta_{i,c}-r_{f,c})\right].
```

令RHS制造差为 `ε_t=(b_full−b_volume−Bα)_t`；实际d还应包含 `−ε_t` 及matvec、scatter和末级相减的有符号求值余差。本式不是允许计算新的逆或修补d。局部/global native项的配对与只扣一次规则沿V13。

允许在已有小矩阵上对固定z_f重算残差及点积，比较原binary64/fsum与独立较宽求值；必要时仅核验少量关键分量的Decimal。**较宽结果只测量残差求值的分辨能力，不驱动新校正，不改变生产精度。** 本轮新GETRS/factor/原生FE作用均为0。区分残差求值误差、剩余Kz解误差的投影、J/scatter求值差、S/native或RHS不一致；不能只以一个范数变小认定原因。

全域分组可否支持旧star的代表性，必须用A2实际覆盖率回答。若已有包只覆盖低能量类别，其机制只作为该类证据，不用于批准全域改动。

## 5. 新最大行1622464：先定位与列缺项，不默认重算

通过原active map取得真实original row，列出全部MPC incident cells、局部位置、tag/perm、actual坐标/键及全部投影系数；不得沿用旧original250113、cells360/446，也不预设仍有两个cell。优先关注能量主导分组中的代表行，1622464作为必查入口；最多额外选两个不同主导签名的行用于**元数据与现有证据覆盖盘点**，不是新增局部实验。

当前索引只确认四个新完整y/g及回执，尚未确认保存新行完整K/J/LU包。缺项逐项报告：

| 必要量 | 用途／可否替代 |
|---|---|
| 原cell编号、actual坐标、I/T位置、E及active ids | 证明所有贡献齐全、正确状态/方向与MPC；不能从行号猜 |
| 同candidate的原K/G/J/L、S/R/T、LU/pivots | 区分张量、消元和求解误差；LU不能反推K，reference块不能替candidate |
| 原b_i/t、实际初解与最终z/correction或可验证的生成链 | 重现该run的求值；已有known不能作校正答案 |
| 原native内部/trace切片与Bα、保存y15/g15分量 | 各自绑定两侧，global项各计一次；不从全域差倒推cell贡献 |

若保存数值量确缺，本轮输出**一个最小补证方案**，而非自动运行：优先一个完整incident star，列精确cell数、缺失块、用途、预计载荷/时间及原生独立性。建议上限8个新candidate cell，超过须另裁决，不截取部分冒充完整star。补建需要新积分/分解时须另行明确批准；当前包不授权它。将来重建的块应标RECONSTRUCTED_SELECTED_CELL，并分别重现旧y15/g15后才用于解释旧失败，不称原live LU重开。

## 6. 科学出口与具体生产函数

当前没有足够证据选择第二数值算法。生产 `project_internal_rhs_same_lu`、`P6CellCondensedAction.reduce_rhs`、actual evaluator、R/T/S及所有阈值保持不变。V16交付必须给出下面一种明确出口：

| 观察到的证据 | 可以得出的结论／下一最小位置 |
|---|---|
| 某类/布局未按预期校正或旧star与本run无法绑定 | 先定位策略/身份/接口；只有真实证据支持才修对应传播函数，不重建全域验证路径错误 |
| 固定最终z的残差求值误差或JK逆残差投影仍主导，且有覆盖边界 | 指向RHS核心的准确性研究，但不自动增加第3次校正或升级精度 |
| 固定z后的J或scatter贡献主导 | 指向核心J乘法/`reduce_rhs`累加；不能混同GETRS时间/精度 |
| S/native、local/native或制造RHS差占主导 | 明确否决“只改RHS求解足够”，列原生/局部算子所缺的最小见证 |
| 余差广泛分布且已有局部包不具代表性 | 用实际能量分组选择最小补证；不给单行改善外推，也不批准全域长跑 |

“统计集中”不是“因果确认”；现有y/g只有组装后的结果，不包含每cell有符号分量，不能从能量表唯一恢复这些分量。新报告要写具体证据、对应函数、解释了哪些行/多少能量、还剩什么，而不是只写继续查舍入。任何saved分析通过均不能解锁candidate恢复、200q、factor、完整参考、FGMRES或官方物理场。

## 7. 成本、资源、窗口与实现边界

本次实际owner39,972.508249 s，不是旧57小时预测。两列action父段合计7,778.180630 s；RHS core7,480.509984 s内fsum6,422.241584 s（约85.85%），GETRS533.677784 s（约7.13%）。只对RHS核心可作此分项判断；全owner kernel/LU/Schur排他成本仍UNKNOWN。V15 service60,758.813495 s包含错误下游和清场，不能再加owner/action/carrier子段，也不能用差额猜热点。新只读recheck是独立父段。全部历史费用保留。[R1] [R2]

新数值包仍需一次明确窗口授权；**技术上同意本报告范围，不自动复活V15 T0。** 旧窗口T0=2026-10-25T14:39:21.578055399Z，数值截止=2026-10-27T02:19:21.578055399Z，总截止=02:39:21.578055399Z（新加坡10:19:21／10:39:21）。接收时读实际时钟：尚有墙钟余额也不把已收口的全域scope改成新分析scope；到期更不能刷新。建议复用现有saved-diagnostics合同建立**6小时实例：总21600／数值20400／收口1200秒，PENDING_USER_APPROVAL**。先完成窄实现、真实命令和fixture，再从首项正式准入/读取开始计新T0；开发账另记。

主机/项目仍为既有 `fenics-ws:/home/fenics/Projects/laptop_share`；原task cap1,649,267,441,664 B、host reserve68,719,476,736 B、task reserve0、complex128/int32、MPI1/math1、task swap0、磁盘余量≥2 GiB不变。工作集按本包实际计，不借沿用大cap分配数百GB；目标新增工作区≤16 GiB，新增保存≤128 MiB且不得突破现有累计16 GiB。旧公式余量不是实时可用量，启动前实读。PSS未采样仍null，tree/cgroup/host swap分开。统计输出不能新增全长复数场副本。

复用V11保存比较器、现有元数据读取器和V15列artifact loader。旧V11固定两矩阵/窗口/行号约束不能直接套到四个新列；新增明确的输入manifest/layout参数，不把旧常量替换成新SHA来破坏历史重放。旧producer/source/window/hash保持原样，新consumer另绑定新scope；不要求旧窗口现在有效或新source必须不同。新scope禁止到达owner/surface/q回调，独立入口失败也不回退到producer。

只做三个直接相关小回归：两种数组layout与摘要绑定/篡改拒绝；有符号能量恒等式及跨材料/MPC不重复计数；真实saved入口的新窗/旧donor传递及禁止builder。复用已修terminal返回和只读checker，不重跑其全套审核、不大重构、不全仓pytest。普通path/JSON/状态错误同包定向修复后只读已有产品继续；产品每阶段立即保存，不因checker故障重做前段。数值/身份/资源/截止门真失败则保全并终止受影响路径。

## 8. 交付与Codex摘要

主控冻结及集中提交同一分支；先提交窄reader/统计接线与定向回归，获准后执行一个连续saved分析包，提交 `response_v16.md`、小型compact/分组表、准确hash索引、窗口/父子费用与缺项清单，更新既有summary/run_index/test_summary及项目总账。不修改master、其他任务或旧负结果，不另建V16求解器/PC/监督框架。

首屏必须给：V9→V15逐侧与带符号变化、top-k/类别覆盖、两旧star与V15终态是否绑定、新最大行全部incident及可用数据、最小因果结论或唯一缺项方案；不是又一次checker完成报告。

```text
读取同分支review_report_v16.md；结果base=3b2b8f683eebfa8ec86503378913c67a29dae086。
接受V15完整产品和最终独立审核，但action两列仍FAIL；恢复/200q未运行。
本轮只做保存向量分解、已有star终态交叉绑定和新探针缺项盘点，不改生产算法。

旧V9两矩阵与V15四列NPY按真实schema/column/hash提供统一只读视图。
复用输入与math identity，保持动态/冻结分母。一次分块计算Δy、Δg、d9/d15、
带符号内积和能量恒等式，trace/port分开；不复制全长差数组或拟合补答案。
给top-k、50/90/99%覆盖及理想过门所需覆盖；最大1622464不是全域代表。

用已有maps建立完整MPC incident签名，按互斥tag/perm/关联数类别计能量，
同一行不得给多个cell各记一次完整能量。缺必要元数据时一次metadata-only补建，
不建数值owner、不积分。方向perm不是物理传播方向。
先复用V14保存最终z/correction、S/J和原输入，分别重放旧两star的y15/g15；
不能仅匹配差d，j0/j3不得混态。绑定后只补当前最终态的局部代数分解，
已有lambda只读复用，新GETRS/factor/native FE作用均为0；宽算术只诊断。

核1622464真实original和全部incident，不猜cell数，不沿用旧360/446。
缺新行K/G/J/L、LU/R/T/S、状态/投影时列准确缺项和用途，提出一个完整star
的最小补证方案。新积分/分解尚未授权，不因缺文件启动28,000键。
无live owner，不重跑carrier、模式扫描、A1/A2、旧审核、旧归因和全域比较。

复用现有saved service，先窄fixture与实际命令再冻结；旧producer与新consumer分开。
新6h范围21600/20400/1200秒待用户一次明确批准，不刷新V15旧T0。
主机/cap/reserve/ABI/线程/swap0及累计16GiB不变；新增小证据≤128MiB。
普通接口bug定向修复继续，科学结论保持真实FAIL；不自动解锁200q或新全域实验。
response_v16给分布、因果边界与具体函数/缺项，不以统计或局部PASS冒充修复成功。
只提交本分支，保留所有负结果与UNKNOWN，不合并master。
```

## 固定来源

[R1]: https://github.com/Rookie1234567/MyFEniCS/blob/3b2b8f683eebfa8ec86503378913c67a29dae086/docs/task41extra_phi90_p50x50_g17x20/response_v15.md
[R2]: https://github.com/Rookie1234567/MyFEniCS/blob/3b2b8f683eebfa8ec86503378913c67a29dae086/docs/task41extra_phi90_p50x50_g17x20/outcomes/v15_closeout/operator_resource_compact.json
[R3]: https://github.com/Rookie1234567/MyFEniCS/blob/3b2b8f683eebfa8ec86503378913c67a29dae086/docs/task41extra_phi90_p50x50_g17x20/outcomes/v15_closeout/run/task41_p0_b0_v9_compact_volume_audit.json
[R4]: https://github.com/Rookie1234567/MyFEniCS/blob/3b2b8f683eebfa8ec86503378913c67a29dae086/docs/task41extra_phi90_p50x50_g17x20/outcomes/v15_closeout/service/task41_p0_checker_result_recheck_c14dcdb4f3df5e1f488de6747008edf6d58c0c3f.json
[R5]: https://github.com/Rookie1234567/MyFEniCS/blob/3b2b8f683eebfa8ec86503378913c67a29dae086/docs/task41extra_phi90_p50x50_g17x20/outcomes/v15_closeout/evidence_index.json
[C1]: https://github.com/Rookie1234567/MyFEniCS/commit/f36909b4850eab61f1fa0b9c51bec63f018fbaf7
[C2]: https://github.com/Rookie1234567/MyFEniCS/commit/bcbbec081e5df4b11b4e0f25b1985dcd4c04481d
[C3]: https://github.com/Rookie1234567/MyFEniCS/blob/3b2b8f683eebfa8ec86503378913c67a29dae086/src/solvers/hcurl_assembly_time_condensation.py#L169-L231
[C4]: https://github.com/Rookie1234567/MyFEniCS/blob/3b2b8f683eebfa8ec86503378913c67a29dae086/src/solvers/task41_v4_volume_only_audit.py#L1950-L2235
[C5]: https://github.com/Rookie1234567/MyFEniCS/blob/3b2b8f683eebfa8ec86503378913c67a29dae086/src/runners/task41_p0_v4_volume_only_audit.py

文档提交前核对静态公式/表格、固定来源及单文件范围。线上可视渲染若只能取得原文，单列未确认；不把原文回读当作rendered验证。本次没有工作站科学计算或项目测试。
