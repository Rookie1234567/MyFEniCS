# Review V38：把 FTT 的结构优势落实到计算，完成原定优化流程而非原样续跑

## 0. 裁决、目标与授权身份

**接受 V38 已实际训练和完成独立验收的负结果；M5、NN 资源收益及原尺寸 0.7 nm 均未通过。V38 的 FTTNN/Cheb 无标签路线只完成 46/68 次 Adam，隔离拟合只完成 40/33 次 Adam，四条均未进入 L-BFGS。现有证据支持“这份慢实现没有在预算内求解成功”，不支持“秩 8 表示的最佳精度已被测清”。本轮仅批准同一 FTT 模型、同一原方程的等价计算重构，并在正确性与完整成本准入通过后，从已保存的完整状态完成原定优化流程。不得原样再给逐点慢实现追加时间。**

要消除的 blocker：小型神经表示虽然取消了全局波列库，却仍在大量三维积分点反复评价相同的一维核、构建反传图；有效更新极少。此次直接利用网络连乘结构，减少核评价与反传重复工作，检验该表示在实际可承受的完整优化量下能否满足原方程。加速只解决执行成本，不预设改善条件数、表达能力或最终收敛。

```text
repository              = Rookie1234567/MyFEniCS
branch                  = task42extra_feinn_5nm
canonical_worktree      = /home/fenics/Projects/NN-Lab-V2
original_base_SHA       = fbac3d8777fcfd897d93b898cb9f460f79ddd6ff
reviewed_result_HEAD    = 8136afcd8a5229974556038428b28833eafb9c91
result_commit_time      = 2026-10-10T03:45:44Z / 2026-10-10 11:45:44 +08:00
review_date             = 2026-10-10 Asia/Singapore
previous_review         = review_report_v37.md
reviewed_response       = response_v38.md
campaign                = V39_STRUCTURE_AWARE_FTT_COMPLETION
required_response       = response_v39.md
new_total_window_s      = 43200
ordinary_default        = UNCHANGED
production_merge        = NOT_APPROVED
```

最终目标保持：真空 0.7 nm、周期单胞内任意非可分三维材料/几何、complex128 Nédélec H(curl)、x/y 双 Floquet、z Fourier-DtN、完整复 E/H、衍射和体吸收；十进制 2e12 B 为整机物理内存并须留余量，ownswap/OOC=0，单场必要准备至完整验收不超过 172800 s。原 50×25×140 nm 目标未资格化。本批 12 h 是研发上限，不是目标 48 h 成绩。

本报告明确覆盖 V38 回执的自动续跑关闭状态，**只允许下述等价内核和有条件的有限续算**；不复活旧稠密波库，不改秩/网络/材料/loss/优化器配置。本支仍只做神经研究，不开展 W0/W1、全口面、模式恢复、传统 PC、存储系统或主线接入，不修改或安排 Task42、主线、dot、master 或其他工作树。原 FE 算子与独立参考仅为神经求解提供原问题及验收。

## 1. 已审阅证据与当前数值结论

读取了最新 branch、Response V38、summary、实际训练/费用记录、FTT 表示/完整矩/优化器源码，核对 Review V37 后 6 次提交。根规则与仓库原则实际回读；原 task/目录规则的未变 blob 与此前完整原文衔接，目录未发现新的独立 supplement 或 Review V38。前版完整 review 从本会话挂载原件读取。审阅端没有 SSH、工作站训练、原始 M5 大数组复算；下表 measured 为执行端记录，非审阅端新测量。

| 同 M5/5nm/384hex/p3/N31968/40端口；measured | 无标签 FTTNN | 无标签 Cheb-TT | 隔离 FTTNN 拟合 | 隔离 Cheb 拟合 |
|---|---:|---:|---:|---:|
| 完整调用 / Adam / L-BFGS 外层步 | 46/46/0 | 68/68/0 | 40/40/0 | 33/33/0 |
| native 与 augmented | 0.998818668222 | 3.39713275365 | 23.9624301842 | 69.6724500532 |
| 散射 E 相对 L2 误差 | 0.999950913962 | 0.999993299439 | 0.985963520891 | 0.888063299314 |
| 散射 H/curl 相对误差 | 0.999951999695 | 1.00007590129 | 0.992520786960 | 0.925828410091 |
| G 场相对误差 | 0.999951972949 | 1.000073866530 | 0.992359773046 | 0.924916613637 |
| 独立体吸收能量闭合 | 0.414094976032 | 0.414078472276 | 0.423985832277 | 0.377357112773 |
| actual / producer 联合门 | FAIL/FAIL | FAIL/FAIL | FAIL/FAIL | FAIL/FAIL |
| 正式 attempt 秒 | 3502.51148525 | 3385.22676557 | 1631.03693267 | 1635.24322962 |
| 同时树 RSS 采样峰/B | 463720448 | 463044608 | 612298752 | 608882688 |

依据：[Response V38](response_v38.md)、[summary](outcomes/summary.md)、[训练及恢复状态](outcomes/records/training_and_fit_v38.json)、[完整原数值](outcomes/records/full_numerical_gates_v38.json)、[资源](outcomes/records/resource_costs_v38.json)、[修复](outcomes/records/repair_log_v38.json)。FTTNN native source=5f192b5c1e871536469174cbc009f0bc4689941a，Cheb native source=26e71e886a42bf5ba65dcb99c7f2162d5d80569e，拟合/最终核验 source=a319b9b0cc09a04989111cb4494380d9912d0a5e。发布 HEAD 不是数值 source。

完整模型重建、q30/q60 系数及原作用、FE 积分与 MPC/端口恢复已通过；梯度和参数真实更新有证据。四条路线失败不是缺少最终场。实际 M5 的 y-Floquet=1；两非单位缝是额外合成见证，不改写实际入射身份。FTTNN 首轮 raw CALL_LIMIT 与实际时间停止不符、软截止越界下界 25.6411715581 s 等历史偏差保留；后续修复不能追认旧时间协议通过。

## 2. 从实测成本定位问题，而不是再猜网络参数

FTTNN native worker=3435.215706937015 s，互斥叶计时中：核评价 1099.844959 s、连乘 495.138754 s、点包装/AD 反传 1659.497970 s，三项合计约 94.7%；A/A* 合计约 8.831007 s。完整 closure 中位数 61.609259 s，最大 147.016121 s。数据由上节训练记录提供；不得把这些百分比外推到目标网格或其他路线。

[ftt_field.py](../../src/solvers/ftt_field.py)对每个三维点重新调用三个一维 core；[ftt_moments.py](../../src/solvers/ftt_moments.py)逐 cell、逐 512 点重复 forward/backward。[ftt_optimization.py](../../src/solvers/ftt_optimization.py)保存每个更新后的新状态还需重新计算 c：FTTNN 46 次 closure 对应 95 次完整 forward。更新后的 c 不能用更新前的 c 冒充；真正应降低的是完整映射的成本，而不是取消必要的保存或复核。

因此本轮不加 GPU、不放宽内存、不缩小积分规则，也不立刻更换优化器。先利用 **同一个网络已经具备的一维连乘结构**。论文 [FTTNN v1](https://arxiv.org/html/2510.13386v1) §2.1–2.2 支持核函数连乘及分离积分的基本机制；其整个 PDE loss 的快速积分还要求系数/源项的张量表示。本轮只重排网络到 FE 矩的计算，原非可分材料和原 A/f/DtN 不作张量近似，不能声称直接继承论文的全部复杂度结论。

## 3. A：等价的一维核评价、余切聚合与张量矩收缩

### 3.1 必做基线：重复坐标只算一次核，连乘导数显式聚合

一个标量物理分量的点值写为 X(x)Y(y)Z(z)，三核分别为行向量、矩阵、列向量。对实际访问坐标建立各轴唯一坐标索引；只合并严格相同的坐标或有已验证代数身份的节点，不能按几何容差合并不同采样点。表按 cell 或最多 8-cell block 有界生成，禁止全网格点图或 N×r² 库。

在参数不变的一个计算基点，按唯一轴坐标评价各 core，获得 detached 数值表。沿原稀疏 interpolation、Piola、orientation 和 owner 得到完整 c。VJP 先用原线性矩映射的共轭转置得到每个点的余切 g，然后按下式累计核余切，重复节点必须 scatter-add，不能覆盖：

```math
\delta L=\mathrm{Re}\{\overline g\,\delta(XYZ)\},\qquad
G_X=g\,(YZ)^*,\quad G_Y=g\,X^*Z^*,\quad G_Z=g\,(XY)^*.
```

G_X/G_Y/G_Z 是对应核的余切，星号表示共轭转置，必须按实际数组维度核验。核余切聚合以后，只对各轴唯一节点的 core 做小批反传：Re(vdot(core_dual,core_value))。不在每个三维点建立重复 MLP 图。完整 c 的余切仍为 A*(Ac-f)/(f*f)，不改变训练目标。

缓存分为固定几何/插值表与参数相关核表。后者绑定 model_kind、完整参数版本、坐标/buffers、用途和 dtype；接受更新、trial、恢复不可串用。仅同一个参数状态才可复用；不得把旧核值带入新梯度。规范缩放/权重/参数顺序均不变。

### 3.2 优先加速：把 tensor-product 矩先收缩为一维矩

对 M5 的仿射六面体，先现场核对映射是否沿坐标轴或仅轴置换，节点和矩是否具有对应张量结构。不能因为叫 hex 就假设任意扭曲单元满足此条件。对不满足者回退到 §3.1 或旧逐点可靠实现，不改变网格。

对原参考矩的一项，若其离散权重由既有一维求积/测试多项式定义给出 wx_i wy_j wz_k，则有限和可准确重排为：

```math
\sum_{i,j,k}w^x_iw^y_jw^z_k X_iY_jZ_k
=\left(\sum_i w^x_iX_i\right)
 \left(\sum_j w^y_jY_j\right)
 \left(\sum_k w^z_kZ_k\right).
```

一个矩是多项之和时逐项相加；边/面的固定坐标是点评价因子，不是删掉该轴。先完整计算参考三分量矩，再施加原 Piola 分量混合、方向变换和唯一 owner。原点重复、entity 编号和周期相位必须精确衔接。1D 矩的 VJP 用同一复连乘链，累计到轴核，不恢复全三维 AD 图。

分解来自原 quadrature/多项式定义，不是参考场、材料或网络输出的低秩拟合。**禁止用 SVD 截断、丢微小非零 interpolation 条目、降低 q 或替换积分点来换速度。** 某行不能建立代数分解时，保留该行原稀疏求和和 §3.1；不能以整份 tensor 化不成功为由结束全部工作。所有行/三个分量的分解、原矩作用、完整系数和导数必须配对。四舍五入归一化只作为等价重排的误差检查，不用于悄悄改离散。

这项优化利用积分单元和神经函数的结构，不要求材料沿 x/y/z 可分；材料始终在原 A 的完整局部张量中。不过不承诺它对任意非结构网格有同样加速，也不承诺秩 8 足够表示任意三维解。

### 3.3 真实资格和性能准入必须一次完成

保留旧 StreamingMomentMap 为独立数值对照，不直接覆盖原默认。新增小型 opt-in mapping_kind 和通用模型适配，不复制整套 runner/watchdog。等价重排允许改变浮点累加顺序，不宣称逐位轨迹一致。

| Gate | 必须验证 |
|---|---|
| 小型代数 | 复矩阵连乘、重复轴节点余切累加、非交换顺序、错误共轭负控；直接三维有限和与一维收缩前向/梯度≤1e-12 |
| 原矩与几何 | 所有 edge/face/interior 行、轴置换/方向、非均匀盒；不能支持的几何确实回退；原 interpolation 与新分解相对差≤1e-12，完整 c/loss/VJP≤1e-10 |
| 完整梯度 | 两模型真实非零态至少3个方向，中心差分稳定区≤1e-5；实伴随≤1e-10；batch1/8及点批128/512对照 |
| 状态等价 | 各 V38 native 终态旧/新 c、原 residual、梯度、一完整 Adam 更新≤1e-10；克隆 L-BFGS 起始态至少一完整外层步的作用/真目标配对，trial不污染缓存 |
| 边界及求积 | 实际 M5 原相位及合成双非单位缝/角点；q30/q60完整 c 与原作用≤1e-8；先原非零态，最终还要复核 |
| 资源/事务 | 无 N×P、N×r²、旧U/Q或全网格AD图；参数版本失效、异常回滚、匹配optimizer/RNG、原子保存、过期deadline继承负控 |

静态坐标/插值元数据与动态 core/cache/AD 新增规划合计≤1GiB、全数值树仍warn12/hard16GiB；不要为了省几百MB把正确批量强行切回极慢循环。每个比较量报告分子/实际分母，近零用原非零自然尺度并另报绝对差，不用epsilon掩盖。

在两个 V38 native 已提交状态上各做旧/新 **完整梯度+一次更新后c/r+保存** 交替短测；旧实现每模型最多3个完整测量，第一轮初始化/setup另列，测试副本不成为正式起点。新实现另测3次连续完整工作，记录 setup、去重节点、core评价、收缩、矩、A/A*、反传、保存及同时峰。选择主路径/逐点回退只能根据等价性、资源和耗时，不能读取参考场选择有利算法。

长续算准入除了所有正确性门，还要求保守成本预估足以在本轮每路线7200s内完成原累计1000次预算：

```math
T_{\rm setup}+1.5(1000-n_{\rm inherited})t_{\rm step}^{\max}+600\le7200\ \text{s}.
```

t_step 取上述新完整工作实测最大值，不能只取热core时间；LBFGS一次调用未必更新一次，用每调用都付一次保存成本是规划保守值。此估计不是保证全部线搜索时长。正确但仍慢，继续在本节范围内修复至 A 预算；仍不满足则记录 FTT_EXECUTION_COST_GATE_FAILED，不原样再跑两小时慢Adam，不因此否定所有FTTNN。另一独立合格路线及文档照常完成。

## 4. B：复用真实完整终态，补完原定 Adam→L-BFGS

只取 V38 各自最终无标签 checkpoint，路径从原 run/checkpoint index 获取，不猜磁盘绝对路径。已知文件 SHA256：

| 模型 | 完整状态 | SHA256 |
|---|---|---|
| FTTNN native | committed_000047.pt，Adam46 | c3927e1f6b8debc5f24c487707f7fae3588d59061bb223857278566fee92c870 |
| Cheb native | committed_000069.pt，Adam68 | 91d11667280bb6fe838bd0f2df772faa70c3a38fb5685b0ff331f31f7d6d0029 |

核对 model/buffers/参数顺序、Adam动量/step/RNG、实际c/r、用途/native/moments hash。原native SHA256=2dbd60267758c2c53ea62a722ee0b07fad16f3cfae3f772bb0ba4830f4e28215，q30 moments SHA256=22715fac468c4e364c3947e99672117f0f855dfe424914f9fce16be090a693f5。只查本任务声明副本；真缺失不可用拟合权重或旧best代替，不自动从零重放已花费用。

新路线为 FTTNN_R8_FACTORED_MAP_CONTINUE 和 CHEB_TT_R8_FACTORED_MAP_CONTINUE。保持原 M5/5nm/h1.25nm/384hex/p3/N31968/40端口、材料/背景/A/f/完整矩、r8、9072/9120参数、sin/Cheb、q30、原native欧氏loss不变。没有新秩、载波、规范重标度、loss权重、Gram逆、Maxwell逆、全FEKrylov完成器或监督warm start。

保持原 Adam lr1e-3，**累计到500次更新**后释放Adam并建立原配置 fresh L-BFGS：lr1/history20/strong-Wolfe/max_iter20/max_eval25/tolerance_grad1e-7/tolerance_change1e-9。新旧完整调用累计最多1000；失败调用仍计入各自实际尝试量，不能反复reset额度。每条新增硬7200s含导入/setup/失败/审核/保存，不宣称仍在V38原1h冷预算内。继续FTT最多954、Cheb最多932次名义剩余调用，实际故障消耗只会减少余额。

原run_training目前强制zero初态且新建Adam；以显式resume opt-in接入完整状态，不绕过身份检查。旧deadline已耗尽，不可作为新绝对时钟，也不可把旧remaining改成新余额；记录新窗口、历史费用和parent checkpoint，分别列继承/新增/累计计数。代码签名/来源变更以当前实现commit绑定，旧SHA保留。

每完整外层step返回后保存新参数对应的c/r与匹配optimizer/RNG，不能用上次closure的旧c省计算。相同参数hash下已生成c可复用；否则必须新算。每25个累计完整调用后的下一committed边界核验原方程，严格三残差到1e-8即冻结做联合验收。实际不更新/非有限/安全/调用或时间上限触发时保存并完成验收；不为了进入L-BFGS缩短Adam500。若再次因性能未完成计划，明确报告执行未完成，不把它称为秩8最优精度。

原方程通过但完整场未过，只允许在原累计额度内按原r继续至1e-10；参考仅返回预登记标量继续信号，不回传向量。两个候选串行且互不warm-start，一条数值失败不取消另一条。无标签标记保持，研究benchmark已经见过不得称盲测。

## 5. C/D/E：一次收齐诊断、物理门和下一档条件

### 5.1 联合验收

独立重建必须至少用未修改的 V38 逐点 FTTField/StreamingMomentMap 路径生成 q30/q60 的实际模型场，不能只让新tensor映射自检；producer另行评分。FE进程不import Torch，ML不载FE ABI，保存数组pure监督沿已合格父进程。不重求已有V1同p3参考，SHA256=0c3c0574a8c1eddcadfb56268e00c08e55d5cb15d44c0c76e873fcea0c467ff7。

| 联合Gate，全部保持原分子/分母 | 限值 |
|---|---:|
| native/augmented/独立total原方程 | 各1e-6 |
| total/scattered E/H/curl、六点复场、四类完整复通道向量 | 各1e-4 |
| R/T/A/A_volume绝对差、吸收一致性、独立能量闭合 | 1e-5 |
| 逐衍射级功率绝对差 | 1e-6 |
| 实际模型重建、MPC、端口恢复 | 1e-10 |
| 网络q30/q60系数和原作用、FE q15/q30积分 | 1e-8 |

接口PASS、时间PASS、训练实际更新、研究信号、联合解PASS和成本收益分别判定。功率在原残差未通过时只作diagnostic。两路线都失败时不授NN增量。

### 5.2 同批条件拟合，不重复其前缀

FTT无标签未联合通过且新映射合格时，自动从 V38 各自最终隔离fit的完整Adam状态继续；按原index冻结hash，FTT继承40步、Cheb继承33步，不误用C或native。共同模型和G拟合目标不变，只G乘法不逐步A/A*/Gsolve。累计Adam100后fresh同配置LBFGS，完整调用累计≤500、各新增≤1800s；性能估计同§3.3但改为500/1800与300s预留。不再从零重做fit前缀。

永久 reference_used_for_training=true、features_reference_exposed=true、pde_only_solve=false、production_initialization_allowed=false、pde_only_solver_qualified=false、official_candidate_results=false。拟合权重/向量不得反馈native或0.7nm。最终通过独立原场验收；有限拟合不叫全局最优oracle，更不用于证明所有r8模型不可能。

### 5.3 条件0.7nm与止损

仅无标签FTT的M5联合PASS、资源合格且总窗仍有≥7200s含终验时，允许原V37定义的长度×0.14、统一正式0.7nm材料的非可分缩小pilot。重新绑定材料/几何/背景/模式/算子/参考，不硬套40端口；r8原零初态，同优化配置≤1000调用/3600s。原模型从头准备及一次小型独立参考纳入7200s；只复用现有合格流程，不另开Full3D工程。C与D互斥；未准入不预注册空stage。

这种缩放近似保持几何/波长比，不检验原尺寸高频规模难点，不可据此宣称任意三维目标已解决。M5本身也只是同p3离散资格，不是连续精度。

若完成上述有效优化量后仍无联合PASS且未达原预登记研究信号(native/augmented≤1e-3、散射E/H/curl≤1e-3)，关闭此r8/native-EUC+固定优化流程，不自动再排rank、seed、loss或旧GN扫描。若软件/预算不足以完成，保留精确原因，不把实现未完成与科学失败混淆；没有依据不得续写“下一轮一定能成”。

## 6. 资源、连续修复和完整成本

新连续总窗43200s：A实现/资格软10800s；B两native各硬7200s；条件C各1800s或D合计7200s；独立终验/发布软5400s，最后至少1800s。剩余为同窗修复余量；允许登记转移软额度，不放大候选硬上限，不开第二个窗。正常bug不设次数交棒卡：定位→最小修改→定向测试→完整健康边界继续，失败费用、源码及旧日志永久保留。不要因writer、用途schema、角色或网页错误重算健康producer；不能以数值停滞作bug重启。

CPU-only/MPI1/math及Torch1，一个现场合格物理核；数值树warn12/hard16GiB、含临时规划≤12GiB、新增缓存/AD≤1GiB；轻任务≤2GiB、ownswap/OOC0。原PSI60s、系统max(128GiB,有效总量10%)及至少384GiB邻增长不放宽；成功准入计墙钟，真实拒绝后的额外前台等待/重采样≤900s，不后台无限等待。保留启动磁盘余量、全链durable launcher/watchdog/worker及身份匹配清场。

训练软截止以前150s收口、至少120s保存。V38最长单closure可能147s，不能靠finally赌成功；用本轮实际完整closure及保存成本加裕量预判。长操作不安全就不启动下一次，先保存当前完整状态。短fixture覆盖导入延迟、两种时间出口和超长线搜索的回滚。raw reason必须反映实际触发，不复用CALL_LIMIT默认掩盖时间停止。软窗口、硬总时限及采样覆盖分别记录，不追认旧失败。

成本分账：V38两native/fit前缀是本次续算的必要继承，项目历史不重复收费，但从零求该场的路线归属不能删除；旧10186s稠密波库不是FTT依赖，仍只保留研发历史。实际native/moments准备、索引计划、core/cache、训练、保存、独立重建/检查全部计费。完整冷N=1缺项继续UNKNOWN。新核心比旧逐点快，不等于同精度胜过传统FE；同精度全流程时间或同时峰改善≥20%才授资源收益。

原A局部张量、完整c/r/余切、CL展开、端口和后处理仍在。本轮只优化神经场映射，不谎称全部matrix-free存储/分布式已完成；2TB不会补救未知的秩需求或优化不收敛。没有合格FTT解以前，不能让本支承担原尺寸48h交付承诺。

## 7. Git、入口与证据交付

先确认branch/HEAD/worktree/锁/活跃run；合法作业未退出不改HEAD不盲kill。只精确fetch/ff-only本分支，不新clone、不reset/stash覆盖不明工作、不改共享配置，不merge其他分支。当前任务新review优先于旧自动暂停说明。数值核进入src，最小opt-in复用现有ftt_campaign/worker和验证，先targeted测试与clean实现commit再运行。不full pytest、不重装、不反复全仓hash或重渲染历史。

在 input/task042extra_feinn_5nm 下实现并validate后，依赖串行：

```text
v39_ftt_factored_checks.dat
v39_ftt_factored_benchmark.dat
v39_fttnn_native_continue.dat
v39_chebtt_native_continue.dat
v39_ftt_independent_compare.dat
v39_fttnn_fit_continue.dat       # 条件C
v39_chebtt_fit_continue.dat      # 条件C
v39_ftt_fit_compare.dat          # 条件C
```

长阶段用既有包装：

```bash
python scripts/launch_task42extra_durable.py input/task042extra_feinn_5nm/<one-run>.dat
```

包装选正确FE/ML/pure activation并调用scripts/run_case.py，每项确认收尾再下一项。D只有真实准入后才建立明确输入。正式run绑定input_original.dat、resolved_config.json、run_manifest.json、input/physical/source SHA、run_summary.json、环境/MPI/线程/资源与artifact hash。

交 response_v39.md、outcomes/ftt_structure_aware_v39.md，以及compact原状态、节点/矩分解、复导数、旧新等价及完整性能、恢复、真实Adam/LBFGS计数、全部物理Gate、成本、修复、run/provenance记录；独立checker从原字段重算。状态区分FTT_MAP_EQUIVALENCE_PASS、FTT_EXECUTION_COST_GATE_PASS/FAILED、OPTIMIZATION_SCHEDULE_COMPLETED/INCOMPLETE、M5_JOINT_GATE、NN_RESOURCE_GAIN和FULL_TARGET。大轨迹/节点表留ignored，不复制多份大JSON。

README/summary保留历史并更新本支当前状态，同步progress、模型总账、tests/changed_files。不得只交“内核实现了”或“还需下一轮授权”：资格/性能通过后即在同批完成B、条件C或D及终验。明确硬安全、数据、容量、总预算或科学否决出口才收口；不保证PASS，不改变门限。只推本分支，不amend/强推/merge，不向其他任务派活。

审阅端已做小型复数重复节点VJP及有限和重排/梯度检查，误差在1e-15量级以内；这不是Basix/M5实测或性能证明。本地Markdown与远端blob另行核对，GitHub完整视觉未验证，执行端有限补查新关键页；网页错误不阻止数值或触发健康计算重跑。最终一次回报完整HEAD、显式tracking/ahead-behind、clean、自身清场以及每项真实数值结论。
