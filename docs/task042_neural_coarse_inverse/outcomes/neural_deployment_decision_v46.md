# Task042 V46：统一冷成本、拒绝部分引擎，关闭当前神经候选

本轮把“谁更便宜”改成可执行的同一账本：先确认全部8项都正确，再比较从冷启动到审核结束的一次完整计算；缺费用就拒绝排序。它修复未来复用时的选择错误，没有新增有限元或神经试验。原尺寸0.7nm完整三维前向解仍未完成；2TB/48h和NN20仍未资格。

| Review V43工作包 | 实际结果 | 边界／证据 |
|---|---|---|
| 5.1统一冷N=1费用 | 已接入实际FullMomentStudy.timing；五路线0/8→NO_ALL_EIGHT_CORRECT_ROUTE | [费用合同](records/cold_n1_cost_contract_v46.json)，不把已知下界叫完整时间 |
| 5.2引擎消费 | NO_MATCHED_QUALIFIED_ENGINE；真实q0合同在消费前拒绝 | [逐层身份](records/engine_matching_v46.json)，没有调用模型或solver |
| 5.3收益与关键路径 | 目标C/U/V/H与同时峰unknown，当前NN f=0，依赖关闭 | [必要条件](records/benefit_necessary_conditions_v46.json)／[责任表](records/critical_path_v46.json) |
| 5.4历史补档／配置 | 新记录补最终355B stdout；说明旧live limits变化，旧证据不改 | [最终日志](records/final_stdout_correction_v46.json)／[manifest](records/selective_merge_manifest_v46.json) |

## 1. 原问题、历史资格与真实源码

目标是50×25nm周期、z=−10..130nm、17×25×120nm Si光栅、λ=0.7nm，保留非可分三维能力与全部32060端口。材料来自canonical用户表，不重新插值或联网替换。新代码只消费冻结标量及hash，不创建目标530856hex/p6网格、105298704 trace或344183904独立系数向量。

V46标量实现source为`4c40128d100860e24a5f50e220361c26bd1180b9`；V45真正数值source仍`53b7a109160e52caf6a712b1d4059b6adbb049ce`，最终文档HEAD不代替它。base仍`ccd357885f7f9be84efe3be07868cc94f13d93fc`。canonical linked worktree、唯一分支、共享common Git和无本任务actor均实查，未改origin配置或其他worktree。

| 冻结有限代数路线 | 原ρ，限1e-6 | 全部系数η，限1e-4 | 完整资格／解释 |
|---|---|---|---|
| R0 | 2.505960139e-8..3.847077003e-8 | 3.661522394e-4..5.538544985e-4 | 0/8；η超限，不能当合格传统基线 |
| CL44 | 2.581975482e-8..3.788533990e-8 | 3.508615011e-4..5.405081646e-4 | 0/8；旧复线性，费用继承独立记 |
| LIN-H | 2.615473870e-8..3.861573114e-8 | 3.484809644e-4..5.296573543e-4 | 0/8；同信息实线性，不是NN收益 |
| NN-L / NN-H | 与R0完全相同 | 与R0完全相同 | 各0/8；验证选step0，16保存状态零修正 |

这是64hex/p6/q15无完整DtN的制造RHS代数试验，已实际训练3×128，不是not_run；其误差为门限3.48至5.54倍。V42内部恢复7.59146691736e-10及1.01044851177e-10大于1e-10保持FAIL。V46没有重算残差/场或把历史失败改为成功；h/p/mode、完整E/H/curl、复通道/逐级功率、R/T/A/A_volume和能量仍按原门，未给原尺寸资格。

## 2. 同一费用函数与实际消费拒绝

冷N=1表示一次新问题从数据、准备、训练、加载、共同前段、推理、后清理、审核/IO到失败重放的全生命周期；不是只计最后几秒迭代。九类字段有秒单位、阶段、source/证据hash、消费对象和measured/derived/unknown。多臂研究总费另记，不把另一臂训练硬加到单候选。

| 路线 | 旧混口径score，s，仅静态反例 | 统一发布情景已知下界，s | 完整冷N=1 |
|---|---|---|---|
| R0 | 32.2991978049 | 124.68974193860777 | unknown，0/8不准入 |
| CL44 | 616.6864592782 | 619.2285887566395 | unknown，0/8不准入 |
| LIN-H | 242.6734232934 | 701.5235948761692 | unknown，0/8不准入 |
| NN-L | 不用于选择 | 696.17785803476 | unknown，选零校正 |
| NN-H | 不用于选择 | 702.623143412522 | unknown，选零校正 |

CL44仅继承493.7489533459302s已消费旧准备/训练；旧在线、加载和审核不再叠加。LIN-H包含新数据/准备/加载/审核。共同前段、推理和剩余清理由冻结8项标量分账，不重复计嵌套CSR加载。失败分配的已知情景下界为0，但完整历史失败归属明确unknown，绝不把失败免费。旧FE/CSR冷准备、人工、未监督Git/IO、新RHS加载与完整物理审核均保留unknown。

若合成CL44/LIN-H都正确且完整费用已给定，旧代码会选LIN-H，新真实消费选CL44；这是软件反例，不是本轮实际选择或求解通过。共同未知只有严格同源、同对象、同寿命、单次消费证据才可为有限排序抵消，百分比的完整分母始终不消。不同unknown→COST_ORDER_UNRESOLVED；有序下界不授最佳完整路线或NN20。真实五路线全0/8，所以没有执行条件独立性能计算。

## 3. 一次dot快照及逐层消费合同

仅只读一次远端dot发布`7f03a48d2962dd3ea967a07368b36acb4aae7f57`，实际source`39c5052476d48eb5d53870d80418e21c969980d8`分开。只读compact/发布文字，未下载Library、解压矩阵或读取因子、未运行dot代码、未改其ref。相对Review V43快照没有新增完整引擎证据。

| 身份层 | 本轮明确缺口 | 责任与停止边界 |
|---|---|---|
| 物理 | dot为7/135缩尺/80cell/phi5，λ相同不能证明几何、材料、k_parallel、偏振和外边界一致 | dot发布完整同物理引擎，Task042检查 |
| 离散 | q0有1884商行/4320内部；完整p6 canonical/native、方向/对偶/MPC/owner及版本hash缺失 | unknown不能用adapter兼容标记补齐 |
| 完整问题 | 228 selected modes/509贡献；532端口manifest并非all532资格；PDE_solved=false | 不等于Task042完整32060端口A/AH/DtN/非零恢复 |
| 正确性 | q0 CSR Fro约7.6099e-16、max约9.8955e-16是组件证据；完整solve/场/功率false | 不能授完整参考逆或2TB/48h |
| 工程/费用 | ignored本地文件及Library索引不等于可部署payload；完整ABI/MPI/冷热寿命/冷费用/同时峰unknown | 不请求它重跑，不在本分支复制solver |
| 神经接口 | 本轮冻结输入输出顺序及残差/伴随/审核要求；选中NN-L/H恒零 | ZERO_CORRECTION_NO_DEPLOYMENT_BENEFIT，不换step128 |

合同逐字段比对源/证据和完整库存，unknown对unknown也失败，compatible=true不能覆盖。真实q0在实际消费入口拒绝，未调用consumer；合成完整合同仅调用标量fixture，证明软件PASS，不授真实求解资格。

## 4. 20%必要条件与唯一原尺寸关键路径

网络要省下足够多的传统计算，才能抵消数据、训练、推理和新增审核。设共同不可省C、其他不可省U、可改变部分V和新增成本H，能省比例f≤1：

```math
T_B=C+U+V,\qquad T_N=C+U+(1-f)V+H,\qquad fV-H\ge0.2T_B.
```

因此必要`V>=0.2*T_B+H`。本轮C/U/V/H全部来自缺完整目标引擎的unknown，不能用微型乘尺寸填成实测；选中零decoder的f=0，净节省`-H<=0`。这关闭冻结模型，不否定所有NN。内存用同时存活对象，必要`M_N<=0.8*M_B`且完整时间≤48h；保存文件变小不是解算峰变小。一份目标复向量5506942464B只是容量derived，未分配，完整基线峰及backend/训练/反向/通信未知。

| 关键步骤 | 已有证据 | 缺口／责任 | 重新准入条件 |
|---|---|---|---|
| 1完整传统引擎 | Task042有限原作用审核；dot q0组件 | dot：完整同物理及可恢复包；Task042：核身份/接口 | 新实质完整证据，不是新文档SHA |
| 2完整正确性与冷成本 | 原标量/费用资产可复用 | 引擎发布者完整场/全通道/功率及冷N=1实测；Task042独立审核 | 所有原门和完整成本，unknown不填0 |
| 3一个不同学习对象 | 固定A全矩分层已关闭 | Task042：先识别昂贵难误差V、标签来源/原方程审核和非神经控制 | 有可核算20%必要机会才另立正式合同；本轮不指定新网络 |
| 4独立收益及原尺寸 | 已消费heldout不可再当fresh | Task042：未见物理输入上非零有效修正、同正确性全成本 | h/p/mode/全端口和NN20均过，再申请原尺寸 |

最终状态DEPENDENCY_CLOSED_NO_MATCHED_QUALIFIED_ENGINE。不再安排纯FE演示、边界测速或同A微调，不轮询等待dot。唯一下一建议：只在外部新增完整同物理引擎/成本证据，或独立新学习对象与可核算20%机会改变实际准入时，提交新的正式研究合同；否则保持数值依赖关闭。

## 5. 最终日志、配置、测试与完整费用

V45最终stdout355B现在以新版本补档，SHA256 `08548d517d163aa0c5470fb96fbf7ec07aeb2652070759f3a3fd119ed3467b99`；旧空归档与旧index不修改。生产者已退出才归档，最终父控制台不归档并说明范围，避免自归档递归。

V45曾把历史namespace v43 live health从20改24GiB、v42从20改64GiB，旧全局storage本已24/64；“old defaults unchanged”过宽，新manifest准确说明。旧ledger永久closed。V46只新增64MiB/Task24GiB/free50GiB配置；256MiB交付预留属于Task/free余量，不能加到仅64MiB的新输出配额导致永远拒绝。live watchdog读同一冻结profile，错误20GiBprofile在fixture被拒绝。

最终26项纯费用/身份/配置测试中一个ML导入专用项在pure跳过、隔离ML单独通过；没有创建模型。Ruff/compile通过，15文档合同另见[测试](records/tests_v46.json)。一次初始Ruff普通错误保留，局部修复后复验；没有数值失败重放。GitHub精确Review页面Cache miss，视觉NOT_VERIFIED，本地表格/公式结构不称网页/CI通过。

从2026-10-04 18:31:49.844698068 UTC与同boot monotonic冻结24h，末1h交付；有载900s含probe60s和末60s清场。仅CPU/math1，实际MPI启动0，GPU/ownswap0；辅助整树hard2GiB，原PSI、系统/邻任务增长余量和空闲CPU/SMT准入不放宽。共享工作站采样峰/实际间隔、所有失败及probe分别结算于[资源费用](records/resource_costs_v46.json)／[采样](records/resource_samples_audit_v46.json)；采样不冒充连续cgroup峰，不承诺绝对零干扰。少量人工/未监督Git/IO未知，历史88389.24759937632s下界继续加本轮已知费用，不清零。

本轮A/AH/B、模型前后向/训练、求解、mesh/JIT/LU/QR/目标分配全部0，新因子0；旧因子/QR历史费用未抹掉。无目标新残差或official R/T/A。交付后closed、清场、释放锁、提交推送唯一分支，核实clean/upstream0/0和实时remote，再经原队列交回审阅；无merge/其他分支/subagents/重置卡。

费用守卫后续实现source `109ad48d4625c1158cd70ce8d30605f2127de150`；唯一标量决策仍绑定4c40128d，没有重跑。可实测launcher开销在live账本收费并与probe去重，最终26项纯回归的ML专用1项在pure跳过、此前隔离单独通过。

最终结算摘要（shared-workstation；完整原尺寸费用仍unknown）：

| 本轮测量／费用 | 数值及口径 |
|---|---|
| 已知有载下界／收费上界 | 85.530298s／<87s（900s上限，末1s结算预留包含） |
| probe／非嵌套launcher | 19.409109s／17.812535s，不重复监督时间 |
| 同时树采样峰／ownswap／GPU | 307077120B（292.852MiB）／0／0；非连续cgroup峰 |
| 实际最大采样间隔 | 0.956220958s；配置0.5s不冒充每次实际间隔 |
| 历史有载已知下界 | 88474.777898s；旧冷费用、人工及未监督Git/IO仍unknown |
| 本轮tmp/artifact／Task artifact／free | 19631628B／23210683811B／3349819416576B，另有新docs小档，64MiB/24GiB/free50GiB内 |
| 数值／模型／MPI启动 | 全0；无新残差、official场功率或神经收益 |

最终历史保护元数据把新增快照误作旧修改的断言已保留并修复，仅补分类/索引，未重开closed窗口或重跑任何actor；[错误及修复](records/software_failures_v46.json)。
