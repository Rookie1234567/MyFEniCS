# Task41extra Review V2：纠正分域资源门，复用完整端口 checkpoint，以单份数据继续 B0

## 0. 决策与冻结身份

**接受13.5 nm A出口；接受0.7 nm完整carrier已经持久化的阶段成果与原始停止事实。下一轮不重做64,120模式生成，不换PC，不升cap；先修分域判断，严格导入旧checkpoint，并让原生/凝聚动作共享同一只读端口数据源，随后在原窗口内继续完整B0。修复误判不等于后续容量已经通过。**

| 项目 | 本次冻结记录 |
|---|---|
| 审阅日期 | 2026-10-18，Asia/Singapore |
| 仓库 / 唯一执行分支 | `Rookie1234567/MyFEniCS` / `task41extra_phi90_p50x50_g17x20` |
| 结果 base / 审阅时远端 HEAD | `5907493d539172af44aaf5e1defa67ce5e5b9079` |
| 原B0科学 source | `c52d0d3c0ec6b46c52c3bcf464ee53164308f1c5` |
| 原正式 attempt | `20261017T103223.933995Z` |
| 当前任务 / 回应 | 本目录 `task.md` / `response_v1.md`；本目录未发现独立补充任务书或编号review |
| 本次写入 | 仅本review；Codex负责代码、定向测试、获准计算和`response_v2.md` |
| 类型 | 现有算子的数据表示、对象生命周期、资源判断与续作接线；不是新物理/新PC |

原source至结果HEAD只有一笔文档/证据提交。任务书blob仍为`5b669c109006fa91fdeebba2a81d97ba17b640b0`，本次按其完整内容及根规则审查。本Chat读取远端源码和轻量证据、复算标明为derived的字节/资源算术；没有登录工作站、重读363 GB载荷、重算大向量、运行FE、factor或项目pytest。旧数组的实读结论来自保存证据，本review不把它们冒充Chat的新数值测量。

物理与离散不变：50×50 nm周期，居中17×20×120 nm Si主体，无额外缺口，z=[-10,130] nm；0.7 nm、掠角1°、方位90°、S、p6、10×200×14；完整当前二维传播模式64,120项。继续准确p6 reference-q修正、FGMRES32/zero/max2048、原MUMPS及complex128/int32、MPI1/math1。不是Task39para的572-N0/p4 BAL_H路线。当前工程网格和传播模式截断仍未取得最终精度资格。[R1][R2][T]

## 1. 接受范围和真实停止原因

| 对象 | 已有证据 / 本次判断 |
|---|---|
| 13.5 nm A1/A2 | A出口继续有效。A1原A6=1.7449656226232747e-10；A2原A6=7.381572880480822e-8。保存场E/scaled-curl相对差约6.84e-9，功率差通过。原attempt7失败与后续checker-only PASS分列，不重跑这批场。 |
| B0六个真实端口代表模式 | 对照资格按原输入/算子范围继承；不称全部64,120项逐项独立再积分通过。 |
| B0 carrier | checkpoint记录64,120/64,120、363,791,051,840 B。完整文件尚未在此次收口重新hash，`cache_metadata_stable=false`；新consumer必须先完成第3节验收，不能直接写跨source复用PASS。 |
| B0 solver | 停在assembly，无q numeric、FGMRES、完整A6、场或official R/T/A。200q中143个有端口，57个无端口；空q仍保留FE部分。 |
| 成本 | workflow父段62,890.795663617086 s；carrier父段28,042.209265219048 s是子项，不能相加。后者包含的component/积分/MPC/筛选子计时保持原口径，缺项不以差额归因。 |
| 内存 | 同时tree RSS峰1,271,718,285,312 B；cgroup峰1,580,571,795,456 B；PSS未采样。二者不相加、不由其差额推断对象。 |
| 停止 / 清场 | `RESOURCE_CONTROLLED_STOP`由错误reserve谓词触发，非时间门/数值/OOM结论。旧summary清场false及`EVIDENCE_INCOMPLETE`保留；04:16:04.696333 UTC的后续清场观察独立记录，不追改旧收据。 |

A出口依据[R3]的原求解、保存输出及checker记录；B0依据[R1][R2]。A1/A2通过不是0.7 nm收敛保证，局部软件改变也不自动撤销数学上未受影响的历史成果。

### 1.1 分域错误已经由源码与同一原始样本确认

通用watchdog在`reserve_domains_separated=true`时仍执行`effective_available_bytes < reserve_bytes`；worker `_V14Runtime.sample`已分开检查host与cgroup。前者把host预留再次施加在两域较小的cgroup余量上。[C1][C2]

| 触发样本，B | 实际值 |
|---|---:|
| host MemAvailable | 854,915,547,136 |
| host reserve | 68,719,476,736 |
| host扣一次reserve后 | 786,196,070,400 |
| 最紧task/ancestor cgroup剩余 | 68,698,267,648 |
| task-cgroup自身reserve | 0 |
| 错误比较的超出量 | 21,209,088 |

正确分域reserve违约条件为：**原始host可用量小于host reserve，或原始最紧cgroup剩余小于其自身reserve**。增量准入使用两域分别扣完各自预留后的较小值；不得再减host reserve。保持RSS动态/显式cap、task/ancestor实际限额、任务swap和监控有效性检查。原样本两项reserve违约均为false，不表示可继续任意分配。

实际cgroup峰值已到cap的约95.835%（derived）。纠正误判只是恢复本来约64 GiB的末段余量；不能据此推断下游转换、reference因子组和恢复都放得下。

## 2. 源码定位：必须同时改变数据消费，而非只翻一个开关

### 2.1 三处确实存在的额外开销

1. `_ResumableSurfaceFunctionalStream.open()`核验前缀时把所有frames加入`entries`列表；`FullspaceDtnCarrier`随后经`_sparse_entries`排序/高级索引再产生规范数组。因此，旧checkpoint恢复接口不是有界只读入口。[C3]
2. `build_target_context`仍调用`build_p6_cell_condensed_action_from_carrier(... port_coupling_mode="cached")`，没有启用bounded direct路径。默认`consume`逐条创建Python行号/complex列表，随后转换数组；`_prepare_direct_terms`又复制、concatenate，并分别保存original/active行和值。[C4][C5]
3. `bounded_direct_term_build=True`仍逐行Python映射，分配源长度输出，且再复制active values。仅启用它不满足本轮目标。相反，现有`P6GlobalDirectCarrierProvider`已支持逐模式factory、`map_original_rows`向量映射、原H/模式绑定、full/reduced动作和direct贡献接口；应优先复用这个明确接口。[C5][C6]

这些是源码行为，不是历史实测热点占比。本场没有最后内部游标，不能声称具体循环就是SIGKILL时正在执行的位置；`_boundary_support`、凝聚、carrier规范化及下游转换都要在下次必要运行中分项观测。

### 2.2 数据体积算术及其限定

现有frame头为`<qQQd`，32 B；每个B或D稀疏行值项为int32+complex128，20 B。[C3]

| 从已保存格式推导 | 字节/数量 |
|---|---:|
| 64,120个frame头 | 2,051,840 B |
| B+D行值项总数 | 18,189,450,000 |
| 全部complex128数值 | 291,031,200,000 B |
| 全部int32原行号 | 72,757,800,000 B |
| 原数组载荷，不含头 | 363,789,000,000 B |

**条件情景：若所有这些项都进入direct trace缓存，源carrier、original direct、active direct三套行/值载荷就约1,091,367,000,000 B。**这不包含构建时的parts、concatenate、Python对象、映射、局部缓存和其他对象。它不是本次实测对象账，也没有证明全部项是trace，更不能记为已节省1.09 TB。

本轮选择：保留一个权威的只读端口backing，完整原生A6/DtN与凝聚P6消费者共享它；active行映射按模式/有界块临时产生，数值不复制一整份。read-only mmap或有限frame读取均可，按真实效果选择；文件页、dirty和mmap仍入cgroup账，不能记零内存。可利用OS文件页缓存，但不承诺磁盘流每次作用很快。

## 3. 严格导入旧checkpoint：只改consumer，不重写producer

原数据根（相对工作站仓库根）：

```text
results/task41extra_phi90_p50x50_g17x20/task41extra_b0_p6_phi90_07nm_iterative__full3d_iterative__mpi1__Mna/20261017T103223.933995Z/task41_b0_target_surface_checkpoint/global/
```

该根中的`carrier_surface_functionals.bin`及`.checkpoint.json`、`.manifest.json`只读。关键预期来自[R2]，正式以实际文件和原producer链再核对：

| 绑定项 | 固定值 |
|---|---|
| checkpoint JSON SHA256 | `66ec8f305382060c044822459d50aa6d323d85bcdfffd531b46ff5d74e43e57a` |
| manifest SHA256 | `46cd5e3cecf2c0dac694bdbba1fef91eae10642e878a487fc63e216ddcc1f142` |
| committed prefix SHA256 | `2595b9518e2422bfadbc2f1a6640e619d60501525b07bda48a068a8ec478a10e` |
| producer identity SHA256 | `c89c2c5b06d6b8d727d5ea59e3b4ccad9ecf2ff1627f2a13c60f200eee66cf28` |
| 科学input SHA256 | `a0c45d0475bd2b41d2d19589831086468a62f39fdca5b74734b62751df1485c1` |
| physical SHA256 | `0e272beec0cbbd946d62220f1947f60e11e61411b1fec32e62a9979ec922145d` |
| frozen mode manifest SHA256 | `80527cc4770abe0bc47db20c8d1f0ae8e13b75b5e090498f78cbfa75c120d0e0` |

执行规则：

1. **新执行合同显式指定require-existing donor。** 不再只在新attempt输出根寻找checkpoint；缺失、不完整、身份错误时在生成端口前拒绝，禁止静默fallback生成。新输出使用独立attempt，原DAT物理不改，新consumer source/contract独立绑定同一原window。
2. 先核旧producer source/input/window/contract、原manifest和checkpoint本身。`_resumable_carrier_mode_identity`的嵌套assembly context包含source/config哈希；不能仅删顶层source检查便宣称数学一致。把物理参数、模式及q分配、真实mesh/dofmap/方向/MPC、基函数、积分/phase gauge/归一化、ABI及端口生成代码依赖逐字段对齐。只对经diff证明与端口数学无关的执行source/路径字段建立显式等价桥，不全局忽略hash。[C3]
3. 用必要的fresh FE/MPC/volume/凝聚对象核验实际编号与算子身份；旧进程的Python/PETSc owner已不存在。允许这些未保存对象的必要重建，但**不能为了得到它们再进入全量surface builder或六模式重新积分**。优先沿已有owner/data注入接口拆开metadata准备与生成；保持旧raw对照资格及实际输入。若新编号不同，明确映射并验证，不能以相同行数替代。
4. 对`cache_metadata_stable=false`核查原run记录的具体缓存路径与变化项。区分JIT/执行缓存变化和本bin/manifest/checkpoint变化；不能直接忽略，也不能仅凭false废弃所有数值数据。写新的稳定性审计，保留旧false。存在未解释的数学依赖变化则停止该donor导入。
5. 在受监督的**一次顺序校验**中，复算完整committed-prefix hash，核对64,120帧的index/H/长度、排序唯一、有限值、行界、mode keys、q assignment及文件末尾恰到363,791,051,840 B。frame offsets/counts、支持分类和必要总量一起获得，避免多遍全文件扫描。与原prefix逐字节hash相等才授予载荷完整性；读旧值不是重跑producer。元数据与文件身份在读前/读后核验稳定，若文件变化/尾部多字节/破损则保留失败，不truncate或重新生成。
6. 新consumer receipt绑定旧三文件/producer身份、数学字段对照、当前source/ABI、同一window、验证后的offset索引和完整性结论。旧mode identity中的producer assembly hash不重署名。不得把`committed_prefix_sha256`未复算的旧文本直接称为本次已验证。

原生A6、P6作用和后处理必须共享同一个验证后数据源。现有`_surface_frame_arrays`的字段定义和校验可复用；其`body[offset:stop]`产生bytes切片，可在本改动里用`frombuffer(body, offset=...)`或等价只读view避免单frame内额外复制。不得经旧`open()`、FullspaceDtnCarrier规范化构造器或`tuple(iterator)`重新保留所有frame。

全量校验期间所有输出标diagnostic；完整hash通过后才可提升后续数值资格。建立小型frame/offset索引即可，不开发通用存储系统；宽offset至少int64，不能按PETSc int32截断数百GB文件偏移。

## 4. 接入现有动作接口，保持数学而减少库存

### 4.1 优先实现的最小路径

以既有`P6GlobalDirectCarrierProvider(entry_factory=...)`消费验证后、可重复打开的旧frame流，接入`build_p6_cell_condensed_action_from_generated`。这里generated表示按需供数，**不是重新做积分**。若原生`FullspaceDtnAction`需要按batch/索引访问entries，给它同一源的有限只读视图/迭代接口，不能为满足该接口再创建第二个resident carrier。[C3][C6]

凝聚动作的direct provider覆盖所有trace B/D；数值数组只读借用。已有`map_original_rows`可调用时直接使用；没有时只建一次数值型original→active表或排序映射，slave/unknown用明确无效值并拒绝，不能走逐条Python字典fallback。原carrier已经MPC回拉，**这里只映射编号，不再做一次MPC、附加相位、缩放或共轭**。D保持原定义，不能由B的共轭推导；原H保持显式对角接口，B/D与H的归一化不改变。

同一次必要读取逐模式分别分类B/D的interior、active trace、slave/invalid，保留原值和tiny项。只有完整当前数据支持时才能记录本B0内部支撑为零；不能借旧Task40的零证书。若存在实际内部支撑，使用现有cell-local Bi/Di接口累积**实际命中项**，并保留内部Schur、RHS和恢复修正；provider只处理非重叠trace部分。不能直接把`interior_rows_are_managed=True`作为正确性证明，必须绑定真实cell/port值。不创建全cell×全mode稠密块或零Hlocal。

范围只覆盖这条真实B0消费链，不重写所有历史factory。显式老路径保留用于受影响的小回归，B0新路径禁止进入旧全direct物化。逐模式临时对象、重复原行号、active行号与数值共享关系写入对象账；Python闭包、generator最后一次yield、native action和checker不能暗中延长大backing生命周期。

### 4.2 一次接通全部直接消费者

必须覆盖完整B/D、DtN的B H^-1 D、retained作用、非零FE/port RHS凝聚、内部恢复、原A6残差和需要的模式输出/贡献接口。只改`target_action`最终一行，而前面仍重建完整cached carrier，不算完成。只让reduced matvec通过、原native/checker又把全文件读入list，也不算完成。

利用旧六模式raw pairing做精确读回和新旧接口对照；这只是定向回归，不用新小面板替代B0。随后在完整B0大小的两组不同非零FE/port输入上，利用同一次源遍历的原行作用与active作用验证映射、B/D/H分量、RHS/恢复和原生一致性；符合原门后立即继续求解准备，不为这些输入建立单独完整PDE。保存旧raw的独立积分资格与本轮消费恒等式的区别，不能把共享数据流的两路消费者称为重新独立积分。

不复制已废弃的wrapper、不放宽原数值门：映射身份沿原1e-12；适用算子/CSR-native沿原1e-11；原恢复/凝聚恒等式沿实际冻结profile；每q两RHS真残差1e-10；完整A6 1e-6；物理/体吸收1e-5。近零参考输出使用原合同尺度，不能临时换分母。

### 4.3 时间收益也要落实到完整动作

复用完整producer有望避免再次积分/写出28,042 s的carrier父工作，但新必要hash、读取、FE重建和映射都有成本。provider可减少重复常驻数据，却可能在每次A6/PC时扫描文件。记录实际read_bytes、seek/replay次数、冷/后续完整B/D与DtN作用时间；原生DtN同一batch的D和B应借同一batch数据，避免无意义重复读。禁止以理论I/O带宽或代表模式时间推导整场PASS。

不在每次matvec重新hash363 GB，也不取消首次完整验证；同次已验证只读owner的生命周期内复用验证状态，关闭/新进程后按可审计的文件身份处理。没有可靠任意断点游标就从完整操作安全边界重做，不对半成品重复累加。

## 5. 连续执行合同：产物优先，不另开诊断项目

| 阶段 | 必须交付 / 继续条件 |
|---|---|
| P0 | 分域predicate、require-existing donor、只读源到现有动作接口、真实stage接线及少量相关回归；主控冻结clean source。 |
| P1 | 同一受监督B0 continuation：原窗口余额与资源核验，fresh必要布局、旧checkpoint完整验收、只读索引/支持与稳定性receipt。生产模式生成调用数为0。 |
| P2 | 完整target体积/凝聚/P6及原A6数据源接通，actual backing和分项成本，适用动作/RHS/恢复检查。通过后不在此自动停审。 |
| P3 | 继续现有参考sector生产、200q CSR/native、准确因子与完整参考PC资格。100个两胞sector的局部行号/相位不同，global donor不能未经数学映射直接当local数组。已存在且同身份的数据可复用，缺少的真实新工作允许正常生成。 |
| P4 | 全对象账/真实INFOG/原门通过后保留ALL_Q_RESIDENT，严格每q两RHS、完整PC，剩余预算许可直接原尺寸FGMRES、恢复、输出与checker。 |
| 收口 | 数学、资源或原截止门停止依赖路径；已完成的checkpoint/索引/矩阵不抹掉。记录完整或精确PARTIAL，给下次实际断点。 |

200q中57个无端口，不可删FE块；top/bottom为32,062/32,058，不硬配相同数量。13.5 nm A出口继续复用，无需重新direct/iterative；其six-step结果不预测0.7 nm迭代。若公共数值核心确有变化，仅验证受影响anchor，不自动重放整个历史campaign。

reference和target共享边界数据，仅限实际FE编号/MPC、边界几何、外介质、积分/gauge/H等边界泛函依赖经明确等价核验的情形；不同内域材料的完整算子身份依旧分开。global→local sector不能仅靠same-period/相同行数继承。

最终完整共驻账包含：file-backed carrier实际页、所有仍保留的canonical/direct数据、metadata/map/分类器、FE/MPC及JIT、局部LU/Schur/recovery、全q CSR/PETSc输入及转换、所有live factor、Krylov/恢复/输出/checker。共享backing只计一次；不把该表混成与RSS相加的第二份内存，不把旧峰值或q0乘200当实测。保持1.5 TiB上限及实时host/ancestor余量；若未来对象不准入，保存明确新增请求、共驻量和缺口，不靠修复误判绕过真实Gate。

## 6. 原窗口不刷新，正式入口不换框架

| 固定项 | 继续使用 |
|---|---|
| 工作站/目录 | 既有`fenics-ws:/home/fenics/Projects/laptop_share`；Codex项目/对话不变 |
| task cap | 1,649,267,441,664 B |
| host reserve / task-cgroup reserve | 68,719,476,736 B / 0 B；修正的是作用域，不是门限 |
| T0 | 2026-10-17T05:43:44Z |
| 数值截止 / 总截止 | 2026-10-19T05:23:44Z / 2026-10-19T05:43:44Z |
| 新加坡时间 | 数值截止10月19日13:23:44，总截止13:43:44 |
| 原window SHA256 | `87dd4ec560a208122e9959987a392bf878162793c61582877969206686d922e6` |
| 原producer contract SHA256 | `5657d456d67f2b9e3b94aa19a0666a1b011dece6e7b6c7043eb929b45d711f5d` |

接收review、修复冻结和每次heavy前，用现有Task41合同API读取实际UTC/单调钟/账本余额及boot身份；数值可用量不得超过原数值截止。不能以172800−62890.80取代实际余时，因为后者漏掉启动前准备、停机、修复和等待。到数值截止不启动新heavy；仅在原总截止内完成受监督收口。到期后保全产物并报告余额不足，不自动新开窗口，也不以“新source”复活旧T0。

本次用户明确要求在原资源和余额允许时继续，故修复/冻结并通过必要准入后连续执行，不另索取相同cap/目录授权。新consumer contract绑定本review/新source及原window，producer原合同只读；两种身份不能混用。实际输入物理SHA不变；若只加执行级donor配置，记录其执行差异，不伪造原文件hash。

沿`python scripts/run_case.py input/task41extra_phi90_p50x50_g17x20/b0_p6_07nm_iterative.dat`的既有Task41 service/prepare生成正式命令和continuation参数。**当前冻结版没有已资格的require-existing跨source读取，因此本review不虚构一个立即可用的新CLI。** Codex在原`src.runners.task41_p0_contract`/worker链内完成窄接线并输出真实命令，禁止绕过监督直接启动裸worker，禁止新建一套V2 service基础设施。

任务tree/cgroup swap=0，MPI1/math1、原ABI/exact MUMPS不变；保留共享主机现有授权和动态准入，不停止或修改邻任务。旧错误predicate的资源样本用于纯回归，不为复现误杀重跑旧B0。SIGKILL后退出线程迟滞的历史缺口保留；新运行收口根据真实存活后代执行有限等待/清理，在剩余总窗内监督checker，不改写旧summary为PASS。

## 7. 最小测试、停止条件和提交

本轮定向验证限于三组：

- **资源分域**：原触发样本修复后不再因reserve停止；host确实低于reserve、cgroup自身reserve不足、更紧ancestor、RSS/cgroup耗尽、任务swap及缺失/非法采样仍拒绝。测试非零task reserve与旧non-split路径，保留既定等号边界。让parent/worker使用同一判断或直接测试二者语义一致，不写第三套规则。
- **真实恢复链**：producer与consumer source不同但数学同一、原window未刷新可读取；损坏hash/长度/模式/H/MPC不通过；require-existing缺失不进生成；完整旧数据只读，应用不复用可写工作buffer。使用真实parser/worker路由，昂贵内核可替身，不把被测接线全部mock。
- **表示恒等式**：已有raw模式及最小真实接口，非平凡复相位、非零FE/port RHS、实际内部项和0端口q；old/new full与reduced作用、恢复、模式顺序及共享backing正确。它们是全B0开跑前的短回归，不是新小PDE项目。

不得默认全仓pytest、旧A1/A2重解、全仓清理、替代PC、参数扫描或新网格。普通shape/path/schema/iterator生命周期bug在本窗最小修复并继续；真实身份/非有限值/原残差/资源/任务swap/磁盘/索引/监控/截止门停止相应依赖链。源码冻结后不热改运行进程。

主控集中提交到当前分支：①必要修复和相关测试；②真实checkpoint消费与B0结果/负结果。ChatGPT本次只新增review。提交`response_v2.md`、更新现有run_index/summary/test_summary及两级总账；新增最少的checkpoint adoption、action inventory/performance证据即可，不为每个检查复制权威文件。旧失败、费用和unknown全部保留，不合并master。

Response先回答：是否完整验证并复用了363 GB文件；新生成模式数是否为0；完整target action是否建立；实际常驻/临时backing和完整动作时间；200q/reference/FGMRES走到哪里；剩余具体瓶颈和可恢复产物。测试数量/接口提交不能替代数值进展。62,890.80 s与carrier子时间不重复相加；重读/修复/重建必要对象/后续q和求解成本入各自父账。warm续作不冒充首次冷流程≤48 h，当前及最终网格/mode精度分别报告。

## 8. 给Codex的执行摘要

继续同一Task41项目和分支，完整读取本Review V2。接受A1/A2历史资格，当前B0是carrier持久化完成、assembly未闭合。先按同一原始样本修generic watchdog分域reserve谓词，保留1.5TiB cap、64GiB host reserve、task reserve0及原swap/监控门；不是放宽资源限制。

在现有Task41正式调用链增加require-existing donor输入：指向本报告第3节原checkpoint，旧source/input/window/contract与数据原样保留。新consumer source/合同分开；修复后仍用原window。找明cache_metadata_stable=false涉及的路径；按原manifest/committed-prefix做一次完整稳定性与字节hash验证，结合必要fresh FE/MPC核数学身份，建立只读offset/entry源。不要调用旧eager open把全部frame放入list，也不让旧FullspaceDtnCarrier规范化再复制整份数据；缺失或身份失败不回退生成。

优先接现有P6GlobalDirectCarrierProvider和向量map_original_rows；原生DtN/A6、P6、RHS/恢复/模式输出共享同一只读backing。分类并保留真实内部Bi/Di；不借旧内部零证书，不双做MPC，不改变B/D/H或筛选。仅bounded开关不算修复；禁止逐项Python展开和全份original/active数值复制。用已保存模式和短调用链回归，随后进入完整B0，不另跑小面板或全仓测试。

在真实函数内计checkpoint读取/hash、map、分类、凝聚、端口动作、q生产/native/factor和FGMRES父子时间，记录bytes、sweep次数、实际owner/峰值。每阶段完成即保存；冷/后续动作分别记录，不把7.79小时旧carrier父成本当每次PC时间，也不隐去新I/O。

保持原T0=2026-10-17T05:43:44Z、数值截止2026-10-19T05:23:44Z、总截止05:43:44Z，接收/冻结/启动均读实际余额，不刷新、不新开48小时。代码和针对性测试通过、主控冻结source后，用现有prepare生成实际受监督continuation命令。资源和余时允许就继续完整target action、200q、ALL_Q_RESIDENT、完整参考和原尺寸FGMRES；57个空端口q的FE块仍必需。所有原数值门保留，下一阶段新增内存照常准入，修误判不宣称全场已放得下。

原窗口到期或真实资源/数值门失败时保留所有已完成产物和准确原因，仅收口当前可做项；普通工程bug本窗定向修复后继续。提交response_v2和精确source/run/hash、原失败及费用、库存/时间/残差/清场证据到同一分支，不改母Task40、Task39para、Hybrid或master。不要声称未运行的0.7nm完整场、最终精度或2TB/48h通过。

## 参考证据与源码（均固定于审阅base）

[R1]: https://github.com/Rookie1234567/MyFEniCS/blob/5907493d539172af44aaf5e1defa67ce5e5b9079/docs/task41extra_phi90_p50x50_g17x20/response_v1.md
[R2]: https://github.com/Rookie1234567/MyFEniCS/blob/5907493d539172af44aaf5e1defa67ce5e5b9079/docs/task41extra_phi90_p50x50_g17x20/outcomes/b0_resource_controlled_stop_20261018.json
[R3]: https://github.com/Rookie1234567/MyFEniCS/blob/5907493d539172af44aaf5e1defa67ce5e5b9079/docs/task41extra_phi90_p50x50_g17x20/outcomes/a2_saved_output_checker_retry3.json
[T]: https://github.com/Rookie1234567/MyFEniCS/blob/5907493d539172af44aaf5e1defa67ce5e5b9079/docs/task41extra_phi90_p50x50_g17x20/task.md
[C1]: https://github.com/Rookie1234567/MyFEniCS/blob/5907493d539172af44aaf5e1defa67ce5e5b9079/benchmarks/subreaper_watchdog.py#L1244-L1310
[C2]: https://github.com/Rookie1234567/MyFEniCS/blob/5907493d539172af44aaf5e1defa67ce5e5b9079/src/runners/physical_p4_schur_v14.py#L1180-L1241
[C3]: https://github.com/Rookie1234567/MyFEniCS/blob/5907493d539172af44aaf5e1defa67ce5e5b9079/src/solvers/fullspace_dtn_action.py
[C4]: https://github.com/Rookie1234567/MyFEniCS/blob/5907493d539172af44aaf5e1defa67ce5e5b9079/src/runners/task40_v10_worker.py#L8530-L8773
[C5]: https://github.com/Rookie1234567/MyFEniCS/blob/5907493d539172af44aaf5e1defa67ce5e5b9079/src/solvers/p6_cell_condensed_action.py#L1490-L1614
[C6]: https://github.com/Rookie1234567/MyFEniCS/blob/5907493d539172af44aaf5e1defa67ce5e5b9079/src/solvers/p6_cell_condensed_action.py#L206-L655
