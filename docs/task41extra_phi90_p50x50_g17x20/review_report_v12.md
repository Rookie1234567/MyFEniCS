# Task41extra Review V12：复用已完成证据，直接完成360/446两单元生产重放

## 0. 裁决与身份

**接受V11的受监督负结果补审、全域保存向量分解和完整incident metadata。下一轮不重做这三个阶段，只完成active87567/original250113对应cells360、446的candidate局部构建、生产顺序重放及保存数据复核。当前same_lu_rhs_solve仍不合格；没有证据支持再次全域构建或另换数值算法。**

本轮消除的blocker是：已知变化在RHS缩减侧，但尚缺这两个真实关联单元的数值块，无法将差异分解到具体操作。最小收益是用两个单元取代约19小时全域owner重建；代价仍包括必要form/evaluator准备、两份张量与LU和局部求解。本报告不是数值修复PASS，也不是新窗口授权。

| 身份 | 固定值 |
|---|---|
| 仓库 / 分支 | `Rookie1234567/MyFEniCS` / `task41extra_phi90_p50x50_g17x20` |
| 审阅结果HEAD | `709f19209a9321dc1073ee7408de145df09e665b` |
| V11最终科学source | `f1697498699d9b4c2c4c4919b97e4a1e2bba22f5` |
| 上份review | `3cddb4a09f6efa59c2ab7ce330cda8b1d6ab779f` / `review_report_v11.md` |
| 原失败全域producer | V9 source `59722cca5e35eac65efead9fd27f7d7fc0c70419`，run `20261022T052401.200732Z` |
| 日期 / 工作类别 | 2026-10-23，Asia/Singapore；RHS缩减一致性与有限范围接续 |
| 最终目标 | 原0.7 nm、50×50×140 nm域、居中17×20×120 nm Si、方位90°；完整Full3D场，十进制2 TB含余量、任务swap0、必要冷流程≤48 h |

本次核对远端HEAD、response_v11、compact、证据索引、attempt04原收据、summary/run_index/test_summary和实际源码；读取根/docs规则、task及V11全文。没有在工作站运行代码、读取大NPY或执行项目测试。下述实测来自仓库证据；源码结论与新执行要求分开。ChatGPT只新增本review，Codex实现/测试/获准执行，不改master或其他任务。[R1][R2][R3][R4]

## 1. V11已证明什么，尚未证明什么

| 对象 | 接受结论与边界 |
|---|---|
| 全域作用侧 | 保存y6/y9文件SHA相同，两个已知输入上Δy=0；不等于证明所有输入上的完整矩阵或所有旧LU/J逐位相同 |
| RHS缩减侧 | Δg的L2为6.723134900297747e-7、1.4118220109544058e-6，只在trace，port为0；本次输出恶化完全体现为g侧变化 |
| 原科学门 | V9冻结尺度误差2.6749770637124364e-10、5.613598120039757e-10，原门1e-11仍FAIL；本轮没有新action/recovery |
| 机制尚未知 | 尚不能把Δg单独归因于GETRS、J乘法、数值矩阵重建或散射累加；也不能证明V6全部原误差都来自RHS侧 |
| 负结果收口 | 事后受监督audit完整确认FAIL；旧V9 terminal NOT_RUN保持。接口问题已经关闭，不重跑补审 |
| 完整关联 | active87567→original250113；全部cells=[360,446]；本行各一份系数1+0j，周期MPC覆盖已检查，不外推其他行 |
| 局部数值 | attempt04在996.109 s余额下不满足900+120=1020 s，CANDIDATE_NOT_ADMITTED；不是新数学FAIL，也不是OOM或截止瞬间kill |

两个cell分别为tag2/permutation4680/local trace375，以及tag1/permutation0/local trace75。该行只覆盖原误差能量约0.00627%/0.00664%，top10也仅约0.04693%/0.04287%；它是机制探针，不是全域精度代理。旧4766937上的改善和本行将来的改善都不能自动准入200q。[R1][R2]

监督补审父175.031547463 s、全域比较父39.381449460051954 s、metadata父111.71154267387465 s及attempt03/04父47.917511329986155/49.320757986977696 s分别保留。账本快照20085.307234 s已包含准备、等待和这些service，不能再相加；快照之后的提交费用不冒充已计量。RSS/cgroup/PSS/宿主swap按原口径，不由小型诊断峰值推断完整场容量。[R1][R4]

## 2. 运行前必须关闭的窄接线问题

### 2.1 新consumer不能再被强制绑定到旧metadata窗口

冻结源码 `_run_v11_selected_trace_star_candidate_replay` 有两项明确检查：

```python
fixed_window.sha256 == TASK41_P0_V11_METADATA_WINDOW_SHA256
fixed_window.sha256 == old_window.sha256
```

前者在函数入口，后者在metadata身份联合判断内。这使一个合法的新窗口也必然被拒绝。上一轮把账本路径与window JSON路径混比的错误已修，**但该修复没有解决跨窗口消费**；不能直接把attempt04命令换个时间再启动。[C1]

最小处理：保持旧metadata的source/contract/window/ledger/receipt/全部数组hash和coverage完全不变；新consumer单独绑定获准窗口、当前source和输出目录，并明确引用这些旧producer。旧window只作历史证据验证，不检查其“现在仍可运行”，不追加旧账、不把旧source换成当前source。当前数值准入只读取新consumer的时钟/资源合同。

在现有contract/prepare/service/worker允许的接续范围内传递这一个显式消费绑定；不要全局取消window检查，不新建V12求解器或一整套版本框架。检查直接调用者是否还硬要求旧window或旧consumer source，统一边界，一次改完。至少用一个未来有效新window加冻结旧metadata的真实路由fixture验证能走到局部构建回调；坏producer hash、错误账本path、错误cell覆盖仍必须拒绝。昂贵kernel可替身化，身份与路由不能全部mock。

### 2.2 保持现有数值顺序；当前范围无需重写核心

已核对的局部路径正确保留了：完整S@t、T@bi、J@z后选行；消费 `project_internal_rhs_same_lu` 实际返回的correction，并独立核对完整−J@z；global RHS先写入，再按360、446累加；作用侧最后加入Bα一次；全域native trace只减一次；残差缩减也走同LU而非用旧T*r替代。[C2][C3]

当前目标每cell只有一条系数为1的贡献，因此稀疏Eᴴ投影与逐原行散射在此处一致。保留这个显式覆盖条件；不要把该实现宣称为任意多项MPC行的次序证明，也不为本任务扩写通用散射框架。

补充几项廉价且直接的绑定：两列j0/j3标签各恰好一次；选中active trace与known一致；读取的storage/native action/residual来自同一保存状态；局部bi仍等于原volume内部RHS。evaluator.prepare之后，除实现名外，实际cache/integration identity也与V9 compact比较；actual坐标、I/T分区、方向、材料、FFCx C hash保持原值。不能仅凭同名evaluator或相同cell号声称旧矩阵逐位重现。

### 2.3 不要让“审核完成”和“恒等式诊断”共用恒定失败标签

当前代码把每条 `equation_1_status` 无条件写成 `LOCAL_IDENTITY_UNBOUND`，最终classification又检查这个值；因此即使以后y/g都逐位重现，汇总仍必然为UNBOUND。这是尚未执行路径的状态表达问题，不是原科学误差根因。[C3]

保持保守性，但拆开记录：`replay_completed`、数据完整、y/g各自重放绑定、恒等式实测余差、全域scientific资格。恒等式余差可以是DIAGNOSTIC_ONLY，不要求其人为归零；不得把“在gamma估计内”直接改成科学PASS。保存y/g分别逐位重现才写精确重现；有差则保存差及相对原d的大小，保留未绑定边界。报告完成本身不应被恒定字符串误报为未运行，也不自动启动新一轮checker开发。

## 3. 唯一连续数值包：完成两cell，不再扩张范围

### 3.1 原样复用的入口

工作站根仍为 `/home/fenics/Projects/laptop_share`。旧metadata路径在此根下：

```text
results/task41extra_phi90_p50x50_g17x20/task41_p0_saved_diagnostics_6h/
bc646b17157eed567e2c5391df79e4eda681ab4028f9e86901e8c7fcfd9222b4/
selected_incident_replay/attempt02/task41_p0_v8_selected_trace_star_metadata.json
```

以上换行仅为排版，实际是连续路径。metadata SHA256为 `332baa3a5253a8322b56615c7fe087e401f909c3c889fa048fccc3f9f2b9fcd3`；相邻 `attempt02.service/task41_p0_service_receipt.json` 的SHA256为 `ccf9c796ed38d21180e5336d59b8610a62fb869fc271dc3703a87cedb986eb4c`。producer source=`967ad08d7da75ff8fa4e49bd63ed9abe53469d46`，producer contract SHA=`af27a07502f72f5d3d1effecf98bda21f09e95cca230278e05ed1a63eeaf8931`。[R3]

继续使用旧donor、active/slave与两cell完整E映射、V9 compact和两份完整y9/g9、V11全域比较结果、原FFCx C source与actual-qmetric evaluator。不重新做全域差异统计或incident搜索；读回实际消费的文件hash不等于重跑旧资格。新consumer不得通过执行旧补审/比较“重新取得PASS”。

### 3.2 获准后第一个数值目标就是candidate360/446

复用现有selected-candidate service和 `_v8_rebuild_selected_cell_role_artifacts(..., candidate_only=True)`。只生成两个缺失的candidate原始/定向张量、同源LU/pivots/R/T/S，并逐cell保存、回读hash。J/K/G/L由同一oriented张量及真实I/T切片得到，不从−TK反推J。[C2][C4]

既有实现为编译原form/evaluator而建立必要mesh/space可以保留；这不是允许重新扫描完整incident或构造全域凝聚owner。禁止调用完整28,000键builder、旧八键数值prefix、carrier生成/全模式作用、A1/A2、200q或全局factor。不默认补FFCx reference；本轮首先要重现candidate自己的已保存输出。

如果第一个cell已持久化而第二个或checker出错，接续时严格读取完成的cell，不再积分/分解它。复用现有artifact索引加每cell完成标记和读取分支即可，不开发通用缓存平台。旧进程的LU已释放；仅这两份确缺局部数据允许新建，来源标记 `RECONSTRUCTED_SELECTED_CELL`。

### 3.3 先重现y9和g9各自，再解释差异

对原两列，按实际顺序分别重放完整局部S作用和same-LU RHS缩减，绑定保存的y9、g9行值。先只做两cell×两列的bi求解，j0/j3共用该bi结果；随后每状态求一次ri的同LU作用用于诊断。R/T构造与strict-LU检查所需多RHS求解另外计费，不混入这12个局部诊断GETRS的计数预期。

不能只匹配d；两侧错误抵消也可能让d看似正确。同一新局部矩阵上的stored_T输出仅作对照，不因它更小就回退生产默认或宣称更接近真实解。

对每cell、原donor状态定义：

```math
z_b=\operatorname{solve}_{LU}(K,b_i),\quad
r_i=b_i-n_i,\quad z_r=\operatorname{solve}_{LU}(K,r_i),\quad
w=Rt+z_b-z_r-u_i.
```

保持已审V11两条恒等式，实际浮点余差另列：

```math
\begin{aligned}
C_S&=S-L-JR,\quad E_R=KR+G,\quad
\delta_i=Ku_i+Gt-n_i,\quad \delta_t=Ju_i+Lt-n_t,\\
d_{LU}+\mathcal R_{LU}(r)&=\delta_t+C_St+Jw,\\
Kw&=E_Rt-\delta_i-(b_i-Kz_b)+(r_i-Kz_r).
\end{aligned}
```

局部trace项按Eᴴ组装，全局n_t只扣一次。这里r_t=f_t−n_t−Bα，$\mathcal R_{LU}(r)$使用同LU返回的−Jz_r；不再混用旧T*r。原代码的符号在这一约定下正确，本轮不另改恒等式。每个状态的原生作用是其独立保存输入，不用候选制造native RHS。

必要输出是逐cell有符号局部项、两列y/g各自偏差、四组恒等式左右及余差、原分母下的量级。保留 `Tb_i+Jz_b=(J+TK)z_b+T(b_i−Kz_b)` 作为对照。宽算术只在保存的两cell块上解释求值敏感性；complex128生产答案、原输入/积分/门限和最多三次恢复修正规则全部不变。本包不重跑恢复见证，也不增加修正次数。

### 3.4 收口只读复算，不重新生成

补算完成后，在同一获准包内复用现有保存checker的局部代数能力，读取新两cell文件、pivot可写副本、映射及原向量切片，独立复算y/g、残差缩减和有符号项。不得只检查producer的status，也不得调用数值构建器来“审核”；无新factor、FE、carrier或全域作用。若复用现有函数需要窄适配这两个cell，采用参数和既有artifact格式，不复制整套runner。

输出 `audit_completed` 与 `scientific_qualified=false` 分开。supervisor原字段not_applicable不等于已完成独立数值复核；对本次新局部产品保留真实审核入口、source、原始输入hash、退出和清场证据。不要重启已经完成的V9失败补审服务。

## 4. 判定和继续条件

| 观察 | 本包动作 |
|---|---|
| 局部y9或g9不能独立重现 | 保留各自实虚差及规模，检查重建块/状态/求值身份；标未绑定，不对旧全域故障下根因结论 |
| 能重现且发现确定的状态/索引/漏项错误 | 最小修对应生产函数，用本包已保存块做局部修复前后复核；不用保存差向量补答案，不重新积分无关对象 |
| 能重现但误差由多项数值贡献混合 | 给出每项有符号量、闭合余差和已排除项；不预判“只是舍入”，不自动尝试第二算法 |
| 只在局部改善或诊断闭合 | 仍不准入200q、FGMRES或新全域实验；一行只覆盖约0.0063%/0.0066%误差能量 |
| 普通接口/记录错误 | 同范围定向修复并重读现成产品，不回到补审/全域比较/metadata阶段，不因一个bug再次停整轮 |
| 真实身份、数值非有限、资源、磁盘或截止失败 | 保存已完成cell和首个真实错误，停止受影响步骤；不降低1020秒准入或刷新T0 |

本轮完成标准是两cell可复算证据和明确原因边界，不是测试数量、metadata PASS或“接线已完成”。若尚不足以选择一个生产修复，给出准确缺失的操作/数据及为何必要；不能再交笼统“继续诊断”，也不能编造根因。

## 5. 时间与执行组织：准备完成后，一次授权直达未完成阶段

旧V11窗T0=2026-10-23T05:21:04.242015987Z，数值截止11:01:04.242015987Z、总截止11:21:04.242015987Z（新加坡19:21:04）。本次20:19:03新加坡时钟快照已晚于总截止。旧窗口、账本和不准入事实不改。

**提议一个新的6小时窄续作窗：总21600秒、数值20400秒、收口1200秒，PENDING_USER_APPROVAL。**复用现有6小时合同机制，使用新的唯一实例、T0及consumer输出，范围仅上述两cell重放/只读复核和同范围普通修复。不是复用旧window文件覆盖其T0，也不是再次授权V11所有已完成阶段。用户一次明确批准后连续执行，不逐cell停审；本报告自身不构成批准。

先在未启动正式科学计算时关闭§2窄修、相关fixture及真实启动参数验证，冻结源码、生成实际service命令和输出预算，然后建立获准窗口。T0不得晚于本包第一项必要运行准备；P0代码准备另计工程账，不冒充零成本或删除最终cold所需准备。窗口内修错仍计费，不能通过重新冻结source延长时间。

启动的第一项科学任务就是本地数值重放，不把新窗再消耗在已完成补审/全域统计。保留900秒工作估计与120秒终止预留作为当前准入依据；它不是实测完成时间承诺，也不是单独的900秒强杀。若准备后实际余额不满足原规则，保存计划，不降低预留取巧。记录FE/form/evaluator准备、每cell张量/消元、bi/ri求解、J乘法、持久化和审核的嵌套阶段，避免再次将工程等待当kernel成本。

主机/项目/目录沿用 `fenics-ws:/home/fenics/Projects/laptop_share`，Codex项目不变。task cap=1649267441664 B、host reserve=68719476736 B、task reserve0、原complex128/int32、MPI1/math1、task tree/cgroup swap0；host/ancestor/磁盘实际更紧约束继续生效。保持512MiB新证据上限、16GiB累计上限及2GiB磁盘底线，沿当前128MiB预计证据和6GiB工作区做实时准入，不将派生载荷或前缀RSS当全域容量。无更改MUMPS、PC或物理模型授权。

只补三类相关回归：跨窗口历史producer/新consumer及错误身份拒绝；真实两cell累加/返回量/状态绑定；局部产品先保存与只读复核/异常接续。现有通过测试引用，不默认全仓pytest、不重装Ruff。至少一个小型集成测试贯通实际selected service参数到局部构建入口，不能只测路径比较helper。

主控集中提交：先必要窄修/测试，后真实两cell证据及 `response_v12.md`；更新原summary/run_index和两级账。只推当前执行分支，不amend、强推、删除负结果或merge master。

## 6. 给Codex的接续文本

```text
读取同分支review_report_v12.md；结果base=709f19209a9321dc1073ee7408de145df09e665b，
科学base=f1697498699d9b4c2c4c4919b97e4a1e2bba22f5。
V11补审、全域y/g比较和87567 metadata已接受，不重跑。
变化发生在g的trace侧；不是已证明GETRS/J/某个舍入环节单独导致。

本轮只完成active87567/original250113的cells360、446 candidate重放。
先窄修现有入口中current window必须等于旧metadata window的两处条件及
直接调用者：旧producer source/contract/window/ledger/hash/coverage原样验证，
新consumer绑定新批准窗口和输出。禁止取消身份门、覆盖旧window或刷新旧T0。
保留账本path修复，做一个跨窗真实路由小fixture，不只测helper。

原局部核心沿用：完整S/T/J向量乘法、同LU实际返回correction、原MPC投影，
b_t先写一次、按360/446累加、作用侧Balpha一次、全域native trace扣一次。
本行每cell一条系数1贡献，显式核对；known与j0/j3的trace/RHS/native状态配对。
evaluator实际cache/integration identity与V9核对，不能只验名字。
把恒定LOCAL_IDENTITY_UNBOUND与replay是否完成分开，保留实测余差；
不以gamma估计内代替科学PASS，不改门或分母。

新窗口批准后，第一项科学工作就是复用attempt02 metadata及donor，
只生成360/446缺失candidate raw/oriented/LU/R/T/S，逐cell持久化。
既有form/evaluator必需mesh/space准备可用，但不重扫incident、不建全域owner，
不跑旧八键prefix、FFCx参考、carrier、模式遍历、A1/A2或200q。
已完成cell遇后续bug只读回，不再积分/分解，不新建缓存平台。

分别重放保存y9和g9，不只匹配差d；再按V11同LU残差恒等式计算四组有符号项。
bi每cell/列只解一次，j0/j3共享；ri各状态另解。旧T*r不能代替同LU残差缩减。
读取新数组做独立局部复核，不能只相信status，也不能为checker重建数值。
未绑定如实报告；有确定接口错误可同包定向修复并复核。
局部改善不解锁全域/200q/FGMRES，不试第二数值方案、不加精化次数。

旧V11窗已结束。先完成窄准备、source冻结和真实命令核验；
新21600/20400/1200秒续作窗待用户一次明确批准。
沿现有6h合同机制创建新实例，不复制V12框架；900+120秒准入不降低。
主机/cap/reserve/ABI/线程/swap0及512MiB新证据、16GiB累计边界不变。
准备/修错/等待按真实范围计账，不刷新同窗时钟。

不重跑失败补审、全域比较、metadata、旧恢复或28000键。
只跑直接受影响的小回归；主控集中提交response_v12、两cell路径/hash、
局部重放/独立复核/费用与原因边界到本分支，不合并master。
全域action、完整场、最终精度及2TB/48h均未通过，不改写旧负结果。
```

## 固定来源

[R1]: https://github.com/Rookie1234567/MyFEniCS/blob/709f19209a9321dc1073ee7408de145df09e665b/docs/task41extra_phi90_p50x50_g17x20/response_v11.md
[R2]: https://github.com/Rookie1234567/MyFEniCS/blob/709f19209a9321dc1073ee7408de145df09e665b/docs/task41extra_phi90_p50x50_g17x20/outcomes/b0_v11_saved_diagnostics_20261023.json
[R3]: https://github.com/Rookie1234567/MyFEniCS/blob/709f19209a9321dc1073ee7408de145df09e665b/docs/task41extra_phi90_p50x50_g17x20/outcomes/v11_closeout/evidence_index.json
[R4]: https://github.com/Rookie1234567/MyFEniCS/blob/709f19209a9321dc1073ee7408de145df09e665b/docs/task41extra_phi90_p50x50_g17x20/outcomes/run_index.json
[C1]: https://github.com/Rookie1234567/MyFEniCS/blob/709f19209a9321dc1073ee7408de145df09e665b/src/runners/task41_p0_v4_volume_only_audit.py#L3520-L3660
[C2]: https://github.com/Rookie1234567/MyFEniCS/blob/709f19209a9321dc1073ee7408de145df09e665b/src/runners/task41_p0_v4_volume_only_audit.py#L3890-L4100
[C3]: https://github.com/Rookie1234567/MyFEniCS/blob/709f19209a9321dc1073ee7408de145df09e665b/src/runners/task41_p0_v4_volume_only_audit.py#L4100-L4455
[C4]: https://github.com/Rookie1234567/MyFEniCS/blob/709f19209a9321dc1073ee7408de145df09e665b/src/runners/task41_p0_v4_volume_only_audit.py#L1584-L1712
