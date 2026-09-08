# Task39extra：D5最新收口——原A4数值Gate拒绝，7次PC诊断完成

| 项目 | 最新结果与适用边界 |
|---|---|
| 来源与模型 | clean source `bf8e0c1d16c9c86677e866cdf29fd5491f076e32`；原始13.5nm、1°、s、Full3D p6/h10、MPI1/线程1、80 DtN modes；无参考D1/D3诊断 |
| 数据/作用 | 3份历史快照原A6残差复现，最大绝对差2.77556e-16；native独立系数逐位匹配，分项和与A作用一致 |
| 调用计数 | 8 started / 7 completed；第8次JOINT448→LIGHT未完成，不能记为完整PC；已知误差/投影/互补/D4均not_run |
| 终止 | 原A4残差1.0086968840613509e-10>1e-10（超限0.8696884%）；worker DIAGNOSTICS_FAILED，watchdog/launch WORKER_FAILED，outer exit2 |
| 资源/清场 | 同期树RSS峰3777171456 B<实际cap8367992832 B；reserve4294967296 B、最低available9252577280 B；3324样本无违规，swap0；父进程及19后代清场 |
| 时间 | watchdog mono866.072315784 / BOOTTIME866.072315245 / UTC945.518512242 s；逐段保守收费945.519546580 s，outer含pre/post952.495114811 s |
| 规模 | p6存储173802/独立164592行、252cells；p4存储53084/独立48960、增广53164行、allocated NNZ24730144、factor NNZ53417584 |
| 物理输出与比较 | 无新R/T/A、A_volume、R00_s/p/total、衍射级、复E/H或full solve资格；无p/h/M/MPI/Hybrid扫描、非可分或短波资格 |
| 后续范围 | 数学根因仍未完成；唯一优先是补存同一失败p4输入，核对增广系统与原A4残差差别/可靠性，再补缺失表示与响应诊断；本轮不重跑或精化 |

本次完成的是部分数学诊断及数值拒绝的证据闭环，不是原始完整问题算通。三份原A6身份/残差复现及七份同输入PC响应已经测量；共享p4参考在第8次输入上的原1e-10门槛未闭合，主任务裁决不追加refinement、重跑或D4。

复核六个数值核心文件与旧F3源码逐字节一致，归一化、原P^H限制、独立向量存储、zero-slave与分母路径未发现可唯一定位的工程错误。分母1.1561769354407092、差向量范数1.166232072202645e-10的比值确为失败残差；但失败p4 RHS/解/残差向量未保存，不能声称独立重算了该A4作用或排除全部潜在数值问题。0.8696884%越限既不能改PASS，也不是历史约0.1外层停滞的因果证明。

用户明确授权工程修复后，bf8e0c1保留strict默认，仅诊断opt-in逐段保守收费，不因单独UTC偏移永久中止；数值/资源Gate未变。24b3dbb的TIMEBASE原记录、bf8e0c1的MPI预检子进程启动失败、fresh attempt2分别保留。当前完整terminal为worker DIAGNOSTICS_FAILED、watchdog/launch WORKER_FAILED、outer exit2，清场完成；本机8.367GB安全cap下通过资源检查不代表2GB资格。

唯一优先后续是先补存同一失败p4输入，比较增强系统与原A4残差及映射/可靠性，再补已知误差、表示/粗响应与互补缺口；当前不提出新PC、不宣称病态或舍入唯一根因。D2安全预审的REFERENCE_UNAVAILABLE_ON_16GB不等于16GB普遍不可能。

已有19 focused tests（5.50 s）、ABI、编译通过；最终只作一批文档/JSON/hash/链接/表格检查，未新增pytest或PDE。原四小时账本不重置，所有失败/测试/准备计费；审计时总账9865.346017767 s，历史余额4534.653982233 s不授权新运行，之后文档工作继续计时。最终静态报告位于`benchmarks/artifacts/task39extra/v3_d5_numerical_closeout/static_checks.json`。

原Task base `2dc2e7305f10dc391a13970c6f0f0340cb87b6ee`；本次正式源码/文档提交parent `bf8e0c1d16c9c86677e866cdf29fd5491f076e32`。本轮只提交指定8个文档/索引；新完整文档HEAD与工作树状态在交付消息报告，主任务负责审阅推送，不merge master。

证据：[中心报告](outcomes/nonconvergence_diagnosis_v3.md)、[中心JSON](outcomes/records/nonconvergence_diagnosis_v3.json)、[summary](outcomes/summary.md)、[run index](outcomes/records/run_index.json)、[test summary](outcomes/test_summary.md)、[development_progress](../development_progress.md)、[development_model_registry](../development_model_registry.md)。中心报告列出了7次rho与成本、3份identity/相消、原因矩阵和selective merge依赖组；所有raw及失败证据均保留。

## 历史Response V4首次D5收口（只代表当时状态）

# Response V4：D5证据闭环，数学诊断未完成

| 交付身份 | 结果 |
|---|---|
| 执行分支 | task39extra；原Task base `2dc2e7305f10dc391a13970c6f0f0340cb87b6ee` |
| 正式clean源码 | `24b3dbb67540a4cc2ec3e70ba381ab8a3e41d650`；Review V3 parent `97e82eeb08b6c2faef6457356cdc643832a75eb8` |
| 唯一正式启动 | D1/D3无参考诊断，原始13.5nm/1°/p6h10/MPI1/80modes；没有续跑R3/F3 |
| 停止/清场 | TIMEBASE_INCONSISTENCY；parent exit1、leader−9；watchdog摘要为权威，初始launch未改、worker终态缺失；parent及六个已观测后代均清场 |
| 实际进度 | setup完成p1 numeric，最后s6_transfer_cycles_started；fresh原A身份、canonical资格及残差未重算；完整PC0/互补0/投影0，D4 not_run |
| 资源 | 同期树RSS峰639950848 B，cap8417038336 B；reserve4GiB，最低effective available12219453440 B；swap0、245样本资源违规0 |
| 参考路径 | D2仅安全预审，缺完整MPI1峰值上界，未启动direct；不证明16GB普遍不可能 |
| 数学与物理 | 表示空间、粗响应、互补与restart原因仍UNRESOLVED；没有新的official输出或full solve资格 |

用相同输入检查三种PC，原本能把“误差无法由p4表达”和“虽能表达但修正不准”区分开。本次尚未取得这些数据，D5交付的是可审计停止与有限原因矩阵，不是诊断完成或新PC推荐。

首次Gate区间monotonic61.410906241 / BOOTTIME61.410906659 / UTC67.359115896 s，差5.948209655>5 s。245样本中的244相邻区间显示两次UTC相对跳变3.028049929与2.920159649 s，其余242段一致到约2.35微秒。未找到Python混减/单位接线错误；系统原因未定。保存的16:17:08 CST采样为NTP=yes、NTPSynchronized=no；历史TSC/Hyper-V记录不能归因本次跳变。没有进一步环境调查或系统修改。

批次14400 s上限并未触发：启动前保守计4936 s，termination audit外部累计5190.29133 s；时钟差异限制精确wall解释。余额不授权重试。代码冻结在上述SHA；本次只更新指定八份文档/索引，原review、旧response、旧负结果和raw不变。提交后完整文档HEAD及工作树状态由交付消息报告，避免把未知未来SHA写入自身提交。

历史p4精确逆残差≤1e-10仍未让fine残差低于1e-6，局部联合收益也没有一致改善旧完整曲线；这反驳了简单充分性假设，不能证明p4色散/共振、所有多层法无效或restart唯一致因。唯一后续优先是时间资格后补齐冻结同输入最小诊断证据，本轮不执行，不扩展方法搜索。

本轮既有微型批次6/7/8/8 passed，窄修1/2 passed，编译与ABI检查通过；D5仅JSON/链接/hash/文档检查，报告在`benchmarks/artifacts/task39extra/v3_d5_closeout/static_checks.json`。不重复pytest/正式运行、不声称CI或原尺寸数学通过。

证据入口：[中心报告](outcomes/nonconvergence_diagnosis_v3.md)、[紧凑JSON](outcomes/records/nonconvergence_diagnosis_v3.json)、[summary](outcomes/summary.md)、[run index](outcomes/records/run_index.json)、[test summary](outcomes/test_summary.md)。中心报告已给出production/core、runner/watchdog、checker、docs、research-only与do-not-merge依赖组及资格限制。两本项目总账为[development_progress](../development_progress.md)与[development_model_registry](../development_model_registry.md)。

本轮提交后由主任务审阅并推送；不合并master，等待review。
