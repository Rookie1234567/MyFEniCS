# Review V27：结束旧 hash 恢复循环，交付独立核验的全模式 W1 边界包

## 0. 决定、快照与本轮实际交付

**接受 Response V27 的工程修复、实际生成、保存复核和正确拒绝；不接受原清单已恢复，也不授予 W1 或完整前向求解资格。下一批不继续原样追逐缺失旧文件的 hash。明确新增一条有独立科学验收的新输入身份路径：优先复用 V27 已保存候选，核验全部物理模式字段，再完成原尺寸两代表面的全 32,060 模式作用、独立重开与可消费交付。原件路径保持严格，新路径不得冒充原件。**

本轮针对两个 blocker：旧原始输入不可得使接收链无法进入数值验证；全模式边界作用尚未在本接收端得到独立资格。它是确定性 Full3D 边界组件工作，不是恢复 FEINN 长训练。成功必须包含真实数值数组、原门判断及独立消费者，不以测试数、receipt 数或新增文件数代替。

```text
repository              = Rookie1234567/MyFEniCS
execution_branch        = task42extra_feinn_5nm
canonical_worktree      = /home/fenics/Projects/NN-Lab-V2
review_date             = 2026-10-05
reviewed_HEAD           = 533768469e1a28789d16eef9fcac9e763ca28c5b
latest_commit           = Seal V27 published view and complete retained cost receipts
latest_commit_UTC       = 2026-10-05T02:18:07Z
original_base_SHA       = fbac3d8777fcfd897d93b898cb9f460f79ddd6ff
previous_review_seal    = a9afaa9112d7395f7b8991602906606237db87c3
response_reviewed       = response_v27.md
V27_generation_source   = 904131e19396c4b6896d42056df2e27387908c1f
frozen_math_source      = c354afa449fb80cfb5012e7d2ff66a3e3e64e088
main_readonly_snapshot  = d15554af7da49040565dab015dc09a16c1b18dde
next_batch              = V28_VERSIONED_INPUT_AND_FULL_MODE_BOUNDARY
response_required       = response_v28.md
new_continuous_window_s = 28800
production_or_merge     = NOT_APPROVED
```

最终目标保持：原 50×25×140 nm 单胞、Si 线宽17 nm/高120 nm、真空波长0.7 nm、完整非可分三维 FE 能力，整机十进制2,000,000,000,000 B、自身swap/OOC0、完整冷流程≤172800s。完整显式残差≤1e-6；同离散总/散射E、H、scaled-curl、样点和复通道≤1e-4；功率/能量≤1e-5、逐级功率≤1e-6。**本批不运行该原尺寸全局求解，不以代表面通过替代它。**

维持 `FEINN_MAIN_SOLVER_ON_HOLD / NO_VERIFIED_NN_INCREMENT / FULL_TARGET_NOT_QUALIFIED`。用户要求实质进展和自主修复，故本报告显式覆盖 Review V25–V26 的“必须重现旧字节才有任何数值出口”、只允许唯一R生成候选及固定整面q60无数值修复出口的限制；仅在下述新版本路径和有限分面修复中覆盖。旧task/review/raw/失败/成本、旧原件接收规则和其他分支权限全部不改。

本审阅实际读取远端 V27、当前 summary/README 的近期历史、Review V26、输入复现记录、接收/生成/模式与作用源码；核对最新三次提交相对于V26 seal的改动，并只读主线最新Review V10。旧规则/task的未改blob与此前已读全文对应。本地没有工作站原36MB清单、场或大数组，也未执行SSH数值复测；measured均来自已发布证据，以下工作均为not_run。不能把审阅端的源文阅读当成现场数组或浏览器视觉验证。

## 1. 近期进展：哪些应保留，哪些循环应结束

| 时段 / 已发布证据 | 实质结果 | 当前结论 |
|---|---|---|
| V11–V18：尺度、残差与场误差研究 | 中期M3600散射E/curl约0.0933003/0.0935415，Mfinal约0.122945/0.123039；原残差却从约0.885852降至0.846542。后续小步有原对偶不增门失败 | 不能只按loss/native下降判断场正确；没有经验证的NN净收益，不恢复同类扫参 |
| V20–V23：确定性波动积分 | V23代表面p4/p6原分母门通过；解析相对q60冷成本仅改善约0.232%，不是20%收益 | 复用已有q60与独立解析参照，不重复开发同一个积分加速器；不是全32,060模式资格 |
| V24：W0接收 | 80-cell/p6/532端口制造态及完整内部恢复，955项保存数值检查、1619原件读回通过，带流程限定 | 可复用组件；不是完整散射PDE、原尺寸或跨机持久性证书 |
| V25–V26：接入和准入修复 | 输入/消费者绑定、封存逻辑已建设，但实际生成和全模式数值未完成 | 工程工作必要，却不能长期作为最终产出 |
| V27：真实生成 | 生成一次、监督正常退出；36,263,033B，旧要求36,244,923B，相差18,110B；key和物理身份符合，整体hash不符 | 正确判`BITWISE_REPRODUCTION_FAILED`；B0/B1未运行，q60准确性未知，不是OOM/FE失败 |

依据：[Response V27](response_v27.md)、[当前及历史summary](outcomes/summary.md)、[输入原字段](outcomes/records/input_reproduction_v27.json)、[W0回执](response_v24.md)、[局部积分回执](response_v23.md)。

18,110B是文件长度差，不是物理误差、误差百分比或“仅末位差”的证据。旧正文不可读，就不能进行逐字段数值差，更不能归因于ABI/序列化/材料中的任何唯一因素。另一方面，未知旧字节也不应永久阻止对一个明确新来源的数值输入进行独立验证。

主线当前只读快照的 [Review V10](https://github.com/Rookie1234567/MyFEniCS/blob/d15554af7da49040565dab015dc09a16c1b18dde/docs/task40extra_0p7nm_engineering/review_report_v10.md) 已授权小模型完整p6参考逆、真实缺口和工程锚点；这不是它们已完成的新结果。本支不重复主线p6参考逆、四个局部LU/恢复或dot后端工作。**本支的增量是接收端独立的模式输入资格、边界作用和真实消费者包；主线负责把合格组件组成求解器。**

## 2. 一个工作包，两种身份；不再要求“找不到原件就结束整批”

```text
P0：冻结路径/旧证据/新schema，最小接线与正负测试
  ├─ 历史原件可得：保持旧字节门，读回并记录真实来源
  └─ 历史原件不可得：V27候选→新版本身份→独立全模式科学核验
共同科学输入合格 → P1/B0原生方向与MPC
                 → P2/B1 q60全模式；必要时唯一确定性分面补救
                 → P3独立保存checker/重定位消费者/主线交付
```

逻辑独立不等于并行占用资源。各数值阶段串行；P0通过、得到新文件、代码提交或一个常见bug修复后都不是交棒点。应继续到真实数值验收和交付，或明确的安全/科学失败分流。

### 2.1 历史恢复只做有限查找，不做环境试错

最多15分钟，只检查已经声明的本任务index、sealed副本、显式可访问的主线交付位置。主线远程Git文本不等于本机原数组；没有实际权限不索要凭据、不扫描别的工作树。如果旧manifest和配套来源确实到位，保持原完整hash检验并保存接收收据；同一原问题的合格新raw可优先独立消费，避免重跑正确producer。

旧原件未到位时一次记录 `HISTORICAL_BYTES_UNAVAILABLE`，立即进入新身份路径，不再重复搜索18个旧目录、轮询等待传输或重建AUTO追hash。历史原件以后到位，可单独比较；本批不依赖未来到位。

### 2.2 新身份路径是显式授权，不是放松旧校验

冻结以下已存在候选供重新资格化，优先原样复制到本批独立目录，不重新生成：

| 对象 | 必须绑定的值 |
|---|---|
| V27实际候选 | `7dd07d7145c70759f53465b6ec11237a89effdf7d68a0df6423768858639c56e`；36,263,033B |
| 旧原件身份，仅保留 | `52d7ec801de65d11b15aa1b6daff8d2ad43e1f51902dfd91d06597e49715490d`；36,244,923B |
| 有序32060-key | `03c1965cc13d89b256ea61212a5baba9aa97ef7ec20d356b0a04f9d233e95dec` |
| 冻结物理身份 | `a855565b82c1d88e84352dd355aec3531464261e5ab0df3e45de17e1879eaf1f` |
| V27 inventory组合hash | `daa1f7dd1092ebe148ce173219559c6e60105800e374570bfdf872408a38952c`；不是旧39b457c3… |
| 新instance命名 | `W1_0P7_FULL_32060_NATIVE_V27_REQUALIFIED_V28` |

新来源标 `independently_validated_v28`，至少绑定：schema版本、instance_id、实际manifest bytes/hash、key/physics hash、完整resolved config、源dat/Git闭包/ABI、独立验证程序与原数组/阈值收据。`historical_bitwise_reproduction=false`，`equivalent_to_historical_numeric_manifest=UNKNOWN`，`historical_ledger_recovered=false`。新receipt是新来源，不伪造两份旧ledger之一。

**保持schema1原常量和严格行为；新增显式schema2/新来源分派，默认仍拒绝不匹配。** 禁止删掉`validate_originals`中的hash判断、增加通用`ignore_hash`、把新hash写入旧常量，或利用fixture参数覆盖假装旧生产规则通过。worker、checker、prerequisite和导出消费者必须接收同一个类型化科学binding，禁止各自回退默认旧路径。

若V27原文件本机丢失，先从其封存副本恢复；确实不能恢复时，本报告允许一次**新身份的**模式元数据生成，从固定数学源和物理配置出发，完整记录实际新hash。若发现可证明的生成/序列化实现错误，允许最多两份有根因、修复及独立测试的后继候选，均保留旧文件并在下游数值前重新冻结身份；不扫描ABI/库版本/舍入方式。健康候选不为封存或checker错误重新生成。

## 3. P0/P1：新清单必须独立验证的科学内容

### 3.1 冻结物理而非仅检查自报hash

波长0.7nm；period50/25nm；z=-10/130nm；Si线宽17、高120、原缺口坐标；掠角1度、方位0、s、复幅1；上空气，下Si `0.9998851703688496+4.3236152269189515e-6i`；mu_r=1；exp(-iωt)约定。原`auto_propagating`选择及Rayleigh规则不改，不扩大或裁减mode集合。完整物理payload按V27记录和冻结源dat逐字段核对，包括其既有浮点几何字符串，不以手写近似数重新定义历史物理hash。

当前生成源码 `fullspace_dtn_action` 和 `modes_3d` 提供规范公式；**独立checker不能再调用同一个`build_dynamic_mode_inventory/_mode_identity`生成一遍后自比**。用不同的标量计算路径或已资格化独立核，从配置重算每个模式的物理字段；共同输入和数值假设写明。格式重开、自洽恒等式和独立重算分列，不把三者混成一个PASS。

| 全量检查 | 要求 |
|---|---|
| 结构/覆盖 | schema/profile、mode_index与行顺序、唯一key、top/bottom×s/p各8015；全部32060，无遗漏/重复/重排；独立枚举选择范围核对，不靠manifest自报 |
| k与分支 | alpha/gamma由Bloch及晶格重算；beta色散/出射平方根分支、vertical_sign、完整k；近截止分类、容差和有损传播判据按冻结政策 |
| 极化/磁场/牵引 | 冻结s/p规范和归一化，k点乘E、E切向范数；h_code=k×E/(k0 mu_r)，牵引按原curl/法向/符号；不能只核对散度而忽略整体极化符号 |
| 端口H/功率 | 整周期面积、实际参考面、衰减因子及切向范数重算H；H是端口投影分母，不是磁场h_code；单位幅值Poynting功率及传播标记分别核对 |
| 物理源/坐标 | 真实top(0,0,s)入射、下Si背景、中心坐标→ledger平移(25,12.5,0)nm；公式变换不拟合整体相位、不重复Floquet相位 |

例如波矢应满足：

```math
\alpha_m=k_x+\frac{2\pi m}{L_x},\qquad
\gamma_n=k_y+\frac{2\pi n}{L_y},\qquad
\beta^2=(n_{\rm ext}k_0)^2-\alpha_m^2-\gamma_n^2.
```

对本冻结约定，H还须独立符合原参考面定义：

```math
H_i=L_xL_y\,\lVert e_{t,i}\rVert_2^2\,
\left|\exp(i k_{z,i}z_{\rm side})\right|^2.
```

按原运算尺度/原相对分母门≤1e-10检查数值字段；逐字段保存分子、分母、最大key、全部失败key。H正性、元数据及key是硬门，不以概率抽样代替。精确零/近零沿既有明确绝对规则，不能增加max(1,...)掩盖误差。对临近分类阈值、最大频率、实际n=0、最小H及所有FP64歧义项，用固定80/110位独立核复核；不为全32,060模式逐列重做昂贵积分。分类在高精度中确实不稳定时报告，不删该模式。

新schema的负控至少包括：内容被改且hash同步更新；缺/重排mode；beta符号、极化符号、H整体缩放、错误参考面、牵引共轭/符号、错误材料；跨instance混用worker/checker；旧schema仍拒绝新候选。证书必须由保存字段重算，不能靠`status=PASS`。

### 3.2 工程接线一次做完整

复用V27已修好的pin前范围、当前样本选核、Git blob与磁盘artifact区分、marker-last事务。把schema2的加载、科学身份、封存、失败保存、真实消费者一起接通。正确候选经过科学核验、成功监督与清场、fsync/reopen、seal、独立消费者后，才发布本实例的可用标记。

测试走实际 writer→seal→重开→consumer，不仅测试一个返回字典；中断不得留下正式PASS标记。旧92项A/39项增量根据依赖判断复用，仅重验受影响项，不为review版本变化全部重跑。初始开发阶段常见路径、import、JSON、数据类型和dat分派问题在同批修好，不把每次编辑当成一次数值重放许可。

## 4. P2：真实原生控制及全部32,060模式边界资格

### 4.1 与新身份一起冻结的数值范围

原90/46/46/90分段、原(top,100,1)/(bottom,100,1)两代表面、实际两种面宽、p4/p6全部原局部列、全部模式及其原H/两切向分量保持。先B0：真实Basix方向、两条非单位Floquet缝及角点展开；这不是体网格全场求解。

B1首先使用已有可靠实现的q60，不重跑q30制造负结果。所有去重切向频率、ell=0..6及原≤56rad覆盖按实际清单核对，复用已绑定的Decimal80/110表，仅补缺少的频率。显式检查实际n=0及对应k_y；不要在方位非零的控制中把n=0错当k_y=0。

独立矩参考可沿用既有解析核，其公式与[NIST DLMF 10.54.2](https://dlmf.nist.gov/10.54.E2)一致：

```math
\int_0^1 P_\ell(2r-1)e^{i\kappa(x_0+Lr)}\,dr
=e^{i\kappa(x_0+L/2)}i^\ell j_\ell(\kappa L/2).
```

这是dr积分，物理Jacobian由原面/Piola处理，不能重复乘L。零频率取解析极限。此独立核与q60必须保留实现独立性；不把同一个系数表通过两层wrapper称作独立检查。

### 4.2 验收不是只看投影某个分量

必须保存并核对B、D、端口H、两切向分量、回散布后的完整作用、实复伴随、坐标桥和真实入射边界RHS。输入包含原冻结复见证、另一个预登记seed=4212801的通用复trace/dual/port见证，以及真实物理入射；不得从输出误差选择有利向量。不假设D=B的共轭转置，不裁掉微小非零内部迹，不丢倏逝/近零通道。

| 门 | 本批要求与范围 |
|---|---|
| 一维矩 | 原绝对门≤1e-12，覆盖全部实际去重频率/次数 |
| 局部B/D/H、相位/入射源、方向/MPC | 原分母/运算尺度门≤1e-10，所有受测列/模式和两侧 |
| 完整作用/伴随/通道输出 | 原门≤1e-10；逐key与完整向量均报告，不能只给平均值 |
| 读取/来源 | 实际数组、源/输入hash、形状、覆盖和独立重开必须一致；混合身份、partial、未清场不得准入 |
| 结论 | 仅`W1_REPRESENTATIVE_FACETS_FULL_MODE_EMPIRICAL_PASS`，不是全域所有向量误差界、R/T/A或目标解资格 |

**分母语义不放宽。** 旧原件路径及既有旧q60数组使用其原已冻结分母。新instance没有原件数组时，在评分之前单独冻结新独立reference及同一定义的norm/近零规则，所有新候选共用它；新数值分母不能假称为旧文件的分母值。两种身份的结果分表，禁止借更大的新分母改善旧结果。原定义不明确的量先用已有代码/任务确定并写入design，不用一个PASS标签代替定义。

参考可靠性以独立解析矩与不同实现的直接积分交叉验证到本次测试范围；不要求先证明整个浮点流水线的普适严格误差界才运行有限组件。此为新报告授权的经验资格，旧证明UNKNOWN保持，最终精度门不降低。

### 4.3 q60若真失败，允许一种有依据的数值补救

保存原q60全部失败key/分子/分母；先定位是元数据、坐标/共轭/布局、参考实现还是积分分辨率。明确代码错误可最小修复后重验受影响部分，不改阈值。

若独立证据确为高振荡积分分辨率问题，本报告授权唯一后备 `q60_phase_subdivision_v28`：保持原FE面、基函数、物理模式和q60规则，只把积分区间内部按相位跨度确定性分段。每轴采用不超过4π的目标相位跨度，分段数取满足该目标的最小2的幂；实测参数与分段数在运算前写出。不是h细化，不减少波长或模式。对复频率同时检查指数尺度，不能忽略虚部。遇超出已审频率范围或难以稳定表示的指数尺度，报告而不静默改变物理。

保持原基函数在每个子区间的准确坐标变换、Jacobian和相位；流式一维可分矩/小批积分，不建大张量网格。固定整面q60与分面q60使用不同integration_profile和source标记，旧q60失败不回写通过。后备也须独立全模式复验及全部negative controls；最多两轮有新证据的数值修复，不做q80/q100/多阶数扫描。若独立参照自身有bug，先用解析零频率/不同直接积分确认并修复，不能让producer与checker共享同一错误。

任一数学改动使哪些旧chunk失效必须明确；不依赖变更的已合格chunk可复用，受影响块必须重算。文件封存/checker bug不应重新运行健康producer。积分方案仍失败则交付完整数值负结果和明确下界/未知项，不能恢复NN来掩盖。

## 5. P3：真实消费者与主线衔接，而非再交一页“已实现”

数值worker按至多64模式一批保存原数组、key范围、输入/数学/接收source/hash和integration_profile；允许从最后完整chunk恢复，不能从partial行推断完成。禁止32060²密集矩阵、全目标FE组装/因子或新增Gram。大数组留ignored，Git只存compact摘要和索引。

独立checker只读保存数组重算所有分子/原定义分母、mode和列覆盖、H/RHS/作用/伴随以及状态；不重新调用生成器或重复正确的积分producer。抽样不能代替32,060项完整输出。错误符号/H/丢key/更新hash的坏内容必须被拒绝。

形成一个**相对路径、显式新instance的可搬运包**：模式manifest、resolved config、来源/科学证书、必要频率参照、B/D/H及作用见证chunks、独立消费者、依赖清单和复现命令。依赖和raw先完整，再发布最终ready标记。包必须在本任务另一个干净目录中，由独立进程实际打开并完成同一数值检查；路径仅指旧工作站绝对目录、缺原数组、mixed-instance或未清场producer均拒绝。这是本机重定位读回，不冒充跨机/断电测试。

主线只读接收状态标 `READY_FOR_MAIN_OPT_IN_NOT_INGESTED`，直到主线自己按其review实际消费。若新manifest与主线旧manifest不同，**主线不能只替换一份H或manifest继续使用旧B/D/端口factor/旧结果身份**；必须全套一致，或自行通过明确版本桥重新资格化。此处不授权修改主线、dot、其他worktree或其review。

主线Review V10已经承担p6完整参考逆、真实缺口及四个局部恢复；本包不复制B2/W2或新PC。若主线在本批开始时已交来同科学身份/同面/p/列/profile的完整raw，优先独立消费，节省producer计算；仅有近似描述或旧hash摘要不算已接收。没有外部raw也继续本包，不再次以外部传输作为唯一出口。

## 6. 自主修复、资源和停止规则

**新增一个28800s（8h）的连续执行窗**，自本轮第一次实际准备开始，不重开V27旧窗、不叠加旧未用额度。建议P0接线/验证≤7200s，清单科学核验≤3600s，B0/B1/有界补救≤10800s，独立读回/交付≤7200s；这些是同一总窗下的调度分配，不相加扩大。开始任何重阶段前为后续独立验收保留至少3600s；阶段间可在原总额内登记转移，不给正确producer重复预算。

初始开发/lint/路径/schema错误在P0窗口内直接修；冻结后每个可定位工程根因最多3轮 `failure→hypothesis→change→test→retry`，不是每次修改都要再等review。只重跑失效阶段/块，失败原记录和已耗时间保留。单个科学门失败按§4.3推进或关闭其依赖，不取消其他不依赖它的交付。

| 项目 | 不放宽的执行边界 |
|---|---|
| CPU/ABI | 工作站原生Linux，CPU-only，MPI1，数学线程1；complex128/同ABI，FE不顶层导入Torch，不升级共享环境 |
| 资源 | 一个当前合格物理核；纯/模式/控制/checker2GiB（warn1.75），实际局部边界16GiB（warn12），自身swap/OOC0；不改邻任务 |
| 系统余量 | max(128GiB,有效总量10%)系统＋至少384GiB邻增长＋本任务预算；原PSI阈值与60s稳定观察保留 |
| 准入 | pin前允许范围与当前cpuset交集，原SMT/忙率/邻线程排除不变；可使用当前新样本中的其他合格核，不能沿CPU编号盲试 |
| 有限等待 | 本批R/B最多24份实际样本（内/外层均计），前台资源等待累计≤900s；系统压力后至多2次有新合格窗口的恢复，费用不清零；不后台轮询或无限等待 |
| 持久/时钟 | 完整launcher/watchdog/身份匹配终端树、低优先级；150s收口、至少120s保存；monotonic/UTC按原容差检查，不回写时钟 |
| 磁盘/数据 | 启动空闲≥50GiB，新artifacts≤16GiB；采用现有chunk/NPZ/索引，不重复开发dot存储框架 |

这不是允许对繁忙主机强行运行。真正无资源、权限、ABI、监督或自身换页时安全停止受影响工作，保存理由并做仍可完成的轻任务；不要为“实质进展”绕过保护。也不能把一个JSON bug或Git网页服务错误等同数学失败而结束所有阶段。

新预算覆盖代码、测试、失败、参考、等待、数值、存盘/释放、独立审核和发布尾段。已保存父时钟与嵌套时间不双加；旧A2361.839628s、V25 2846.101466s、V26交付2590.730724s、V27全部费用、失联3284s及旧未知尾段永久保留。项目精确累计原为UNKNOWN，不凭旧的部分账凑出新的精确累计；新窗尽力完整记录并单列未测allowance。

## 7. 文件、提交与一次性交付

数值/输入验证进入合适src/io、src/solvers或现有通用runner；benchmark只编排/聚合，不复制多套数值算法。所有改动显式opt-in，old schema/default不变。先读更深AGENTS；只在本分支修改，正确数学snapshot/源文件通过Git blob核对，不修改原提交。源码冻结后再正式运行，文档HEAD不是run source。

建议一次依赖序列（新增stage先实现和资格化）：

```text
input/task042extra_feinn_5nm/v28_input_contract_checks.dat
input/task042extra_feinn_5nm/v28_manifest_qualify.dat
input/task042extra_feinn_5nm/v28_native_control.dat
input/task042extra_feinn_5nm/v28_boundary_full_modes.dat
input/task042extra_feinn_5nm/v28_boundary_check.dat
input/task042extra_feinn_5nm/v28_bundle_consume.dat
```

使用现有独立activation和 `python scripts/launch_task42extra_durable.py <one-run.dat>`，由wrapper选择环境并调用 `scripts/run_case.py`。每个dat只定义一次明确阶段/候选，后备分面profile用独立dat/attempt并继承总预算。不把未实现stage名称直接投入旧入口；不要在未切换FE/ML/pure环境的裸shell里连续运行。

建议提交顺序：C1版本身份/负控/端到端writer消费者；C2独立物理核和新增资格；C3全模式运行与必要修复；C4独立消费/证据/Response。修复另commit，不amend/强推；本任务运行活跃时不为文档随意改变运行源码。不得merge master或其他研究分支。

最终新增 `response_v28.md`、`outcomes/versioned_manifest_and_boundary_v28.md`、`outcomes/main_handoff_v28.md`，以及compact记录：

```text
records/design_v28.json
records/input_identity_v28.json
records/mode_validation_v28.json + 逐字段失败CSV
records/boundary_metrics_v28.csv
records/independent_checker_v28.json
records/consumer_receipt_v28.json
records/repair_log_v28.json
records/run_index_v28.json
records/resource_costs_v28.json
records/gate_decisions_v28.json
records/selective_merge_manifest_v28.json
```

summary首页给当前结果和下一步，不删除任何历史；同步本分支development_progress、development_model_registry、test_summary和changed_files。单JSON建议≤200KiB，完整32,060数据/复杂历史留ignored且hash绑定；不为满足体积建议丢失败key与可重算来源。

新review/关键新页做有限实际GitHub视觉核验；服务错误如实标 `RENDERED_VIEW_BLOCKED`，保留结构检查与实际数值进展，不重渲染全部历史、不让网页错误阻断B1。只推：

```bash
git push origin HEAD:refs/heads/task42extra_feinn_5nm
```

## 8. 本轮结束时必须回答的问题

**新输入是否在保持原物理与模式集合下独立通过？全32,060模式的两代表面B/D/H、完整作用/伴随和真实边界RHS是否通过原门？另一个干净目录里的消费者是否实际读到了同一数值包？** 这三项是本轮的实质验收。

新路径通过不代表旧manifest数值等价；旧bitwise失败保持。新输入/组件通过不代表原尺寸完整三维E/H/R/T/A通过，也不代表NN有净收益。成功应分别写 `VERSIONED_MODE_INPUT_QUALIFIED`、`W1_REPRESENTATIVE_FACETS_FULL_MODE_EMPIRICAL_PASS`、`LOCAL_RELOCATED_CONSUMER_PASS`；未合格分别说明INPUT_PHYSICS_FAILED、BOUNDARY_NUMERICAL_FAILED、REFERENCE_UNRESOLVED、ENGINEERING_BLOCKED或RESOURCE_CONTROLLED_STOP及实测分子/分母/成本。

**若结束时仍只有“更多fixture通过、又一份receipt”，却没有实际模式科学核验或全量数值尝试，除真实资源/权限/输入科学失败外，不算本包完成。** 反之，完整真实数值负结果是有效交付，不能为通过而修改门槛。授权工作完成或达到明确停止条件后一次性交付并等待review，不自行恢复NN、扩大网格/波长范围或运行原尺寸全局solve。
