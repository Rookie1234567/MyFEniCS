# Task40extra Review V29：接受完整 q0 CSR，以明确资源合同进入首次单 q 分解

## 0. 审阅结论与本轮决定

**接受 V28 的完整 regular-reference q0 CSR/native 资格。下一项主工作是消费现成矩阵，完成第一次单 q 精确分解及两次非零 RHS 求解，取得真实分解、重复求解和内存数据。无需重跑 producer、FE/MPC/native、routes、pattern、fill 或已经通过的四次 native 回读。**

CSR 是稀疏矩阵的行指针、列号和复数值三组数组；V28 已经把三组都完整保存并通过对照。factor 是把这个矩阵分解成以后可反复用来解方程的因子。矩阵资格与 factor 资格是两个阶段：前者已完成，后者还没有开始。[R1]、[R2]

| 决策项 | 本次决定 |
|---|---|
| 审阅日期 | 2026-10-12，Asia/Singapore |
| 仓库 / 唯一分支 | Rookie1234567/MyFEniCS / task40extra_0p7nm_engineering |
| 冻结正式交付 HEAD | b76ef700ad5f5d113f3be2115b128e5109454a44；已实际回读分支确认 |
| 正式源码 | c6624391d8f96e257d1efa914cb38821e2a87eb9 |
| V27 结果基线 / 前一 review | 4e04f2fe2b3ea22e67cbd93ee1ffebfd66b50a79 / b52c8d47a9db7f4e9d7f6d134a7f307b8728a4ab |
| 提交范围 | V27 基线以后5个提交、19个文件，含2个 Review V28 文档提交、2个实现提交、1个正式证据提交；最终源码后只改文档/证据 |
| 正式判断 | pass_with_qualifications：q0 CSR/native 接受；单 q inverse、全 q、target PDE、精度与2TB/48h仍未通过 |
| 下一唯一 heavy | 已资格 q0 的 conversion → symbolic → numeric → fresh probe → 第二非零 RHS → evict |
| 资源决定 | 提出指定大内存主机上固定512GiB任务cap、64GiB宿主余量的具体方案；**尚待用户批准与实际主机/目录绑定** |
| 立即可做 | 同一现有本机目录中的只读核验、依赖清单、严格factor-only接线和定向软件验证准备 |
| 本次 Chat 工作 | 远端源码与证据审阅、哈希/算术核对和本报告；没有启动项目测试、FE/PDE、SSH、服务或数据迁移 |

本次以 GitHub 连接器冻结读取了数值内核、续作入口、记录与规则。已核验的30份文件 Git blob 匹配，run index 的10份 tracked 文档/记录 SHA-256 匹配；范围覆盖数值内核、后端/profile/activation、续作与资源接线。大数组仍在执行端 ignored artifacts，本 Chat 没有访问其完整字节或重新计算向量；接受资格依据是源码、冻结 compact、正式实读 hash checker、已保存输出及主控独立审计的一致证据链。[R2]、[R4]

**资源批准是下一次 heavy 的唯一外部前置。** 用户本轮明确要求“不自动迁移、不擅自提高cap”；Task40 AGENTS 仍限定本机路径并禁止SSH/工作站切换。因此本报告提交不等于已经获得工作站或512GiB授权。先完成本报告规定的可审阅准备包，最后一次明确批准主机、目录、资源、必要文件转移与固定窗口；批准后按包连续推进，不逐阶段再申请相同权限。[R16]

## 1. V28 成果及资格范围

### 1.1 已完成的实际对象

| 指标 | 数值 / 状态 | 数据身份及解释 |
|---|---:|---|
| 实际模型 | regular reference，去除notch/void，272×2×14=7,616 cells，p6，λ=0.7nm | recorded；单 q0，不是完整非分离target解 |
| q0 rows | 777,644 | recorded；773,568 trace＋4,076 q0 port aliases |
| CSR shape | 777,644×777,644 | recorded |
| structural slots | 577,061,168 | recorded；排序且唯一的完整行列结构 |
| numeric nonzero | 560,366,994 | measured / recorded |
| exact-zero slots | 16,694,174 | measured / recorded；仍保留在原结构中 |
| 类型 / 有效载荷 | complex128/int32；11,544,333,940 B | recorded及算术核验；文件header另计 |
| FE/MPC/native/producer/routes/pattern重建 | 全部0 | recorded；V27 pattern直接继承 |
| 成功完成工作 | Hhat 1、volume 7,616、surface 15,864，共23,481 | recorded；全部完成 |
| 新完整CSR作用 | 4次 | recorded；主控独立审计没有新增CSR作用 |
| q0矩阵资格 / 全q inverse | q0 CSR/native已接受；inverse仍0/8 | 当前阶段范围，不混为同一个计数 |

generic contribution count为23,480，另有一次独立Hhat，所以总完成数23,481没有漏项。COMPLETE manifest创建source52b435d2与实际numeric/qualification sourcec6624391分列；这属于保留创建及后续执行身份，不是混用源码。旧V27 manifest与原失败、费用均保留。[R1]、[R2]

原尺寸parent仍是50×25×140nm、272×8×14=30,464cells、真实非分离Si/air。Nx272/Ny8/Nz14/p6是工程pilot配置，尚未自动获得最终精度资格。本轮q0参考矩阵不能替代真实target KSP/PDE、full A6、场/衍射/R/T/A或精度验证。[R2]、[R17]

### 1.2 数值对照可以关闭本阶段

| 完整CSR/native比较 | 相对误差 | 门限 |
|---|---:|---:|
| x1 total | 1.9116580127740397e-14 | 1e-11 |
| x2 total | 1.9044249363689425e-14 | 1e-11 |
| volume | 1.9115170598605398e-14 | 1e-11 |
| −D | 4.0018002857899965e-15 | 1e-11 |
| C | 1.0992641636347272e-15 | 1e-11 |
| Hhat | 1.0985392495312836e-16 | 1e-11 |
| trace＋port重组 | 2.8011401775529595e-16 | 1e-11 |
| 四个native off-block | 全部0 | 1e-11 |
| 主控独立保存输出重算最大值 | 1.9116580127738185e-14 | 1e-11 |

源码对两组完整输入及trace-only、port-only输入做四次真实CSR作用，检查分量、off-block及重组，并在分解前原子保存输出、资格和operation；随后释放adapter/maps。CSR opener实际校验三数组文件hash、类型、shape、canonical/sorted与共享保存数组，正式partial checker也实读三数组，21/21通过。[R2]、[R6]、[R7]

新的稀疏投影保持L^H V R：右侧的普通转置、左q映射共轭、−D负号及H按实际保存映射的加权投影均有源码和完整数值对照支持。修复后的completion回调发生在投影/scatter成功后。未发现需要撤销q0资格的数值问题。[R6]、[R7]、[R15]、[R19]

正式partial checker通过不等于full_pass；后者仍false。最后progress保留READBACK_IN_PROGRESS与过期surface ETA，但readback_completed及最终COMPLETE/PASS/RESOURCE_CONTROLLED_STOP_AFTER_Q0_CSR一致。把进度终态写清可随V29修补，不追改原progress，也不为该显示问题重跑。[R1]、[R2]

### 1.3 本轮必须保留的不可变入口

| 文件 | SHA-256 |
|---|---|
| V28 COMPLETE manifest | ca3c8de9093fd1cfe9e17c8eb557cd2f96920a3ee110549f007e70835d4a2290 |
| native PASS receipt | 63babb2943b7e0f613a2c531afd09f931c4ee5504a345748c52f6ef38b0e9c81 |
| CSR data.npy | 457b946f8e08557d82df38683a884d25ff58413f17ad1bb7f7e04a7296698c27 |
| CSR indices.npy | 9279c5dbfb8921c61dc229ea6a99d30bb76f8b31d005076796d4504a1e7d0d6e |
| CSR indptr.npy | 6d24828a2cd820601fedf92c5b6575fc2dd95a905c2533677f3a3367648a7819 |
| 四个保存输出NPZ | 304f3029e147ba0d4054efdf484757581a88b71a0ae60f6bea7235003eeac9ac |
| 主控独立审计 | 577dc063324a083cd285cceddb7cc60b1a4516cffb0149e3eb94af9e132a2469 |
| 原V27 manifest | 1ea707f3c201359c390b620a5122d0102f5b34bd74873b5f00e3a40b673b94de |
| 科学输入DAT | 134ea5f08d5d5dbc366870f451ba0de0df5893c5cd73d227dac77f8a11aa2c0b |

完整路径以operator和handoff为准。大数组无需进入Git；新factor输出写新attempt目录，不写入旧manifest或旧证据目录中的已完成科学文件。[R2]、[R5]

## 2. 时间与资源：接受已测值，明确仍缺什么

### 2.1 V28 的完成速度是真实成果，但不制造不可比的加速倍数

| 范围 | 秒 | 解释 |
|---|---:|---|
| data清零＋初始flush | 52.559229 | fill父段之前 |
| numeric parent | 734.323900，约12.239min | 已包含生成、投影、scatter、回调 |
| data hash | 50.957251 | 填值后独立区间 |
| readback parent | 286.435002，约4.774min | 包含4次完整CSR作用 |
| 已记录service父链monotonic | 1,316.226225，约21.937min | 含已记录activation/ABI/run_case/checker/间隙 |
| 同一已记录父链保守计费 | 1,464.152690，约24.403min | 各不重叠区间按保守时钟归并 |
| V27 pattern历史成本 | 2,106.866994 | 本轮重建0；保留原历史成本 |

generation203.372s、projection278.819s、scatter136.587s及gate145.112s存在父/子与交叉口径，不能全部相加；watchdog也不能再加到run_case/service父段。V27未完成fill，没有同范围完成时间，不能用其worker总时间除734s宣称一个严格加速倍数。[R1]、[R3]

**源码确认的计时缺口应在V29顺手补齐：** service在第一条user_service_parent_before_activation之前已经完成selector/input/window/donor绑定，可能包含大文件hash。因此1,316.226/1,464.153s是“已记录父链”，未覆盖所有入口准备，更不能把遗漏仅理解成systemd几毫秒的首尾。未记录部分保持UNKNOWN，不通过相减补写原记录，不重跑V28。V29从真实service/wrapper入口开始父计时，把此前输入与donor核验纳入或明确单列（源码run_service7251–7260、7338–7340及selector1951）。[R8]

### 2.2 本次没有进行分解；当前guest物理内存确实不足

| 指标 | 字节数 | 口径 |
|---|---:|---|
| simultaneous process-tree RSS peak | 12,497,358,848 | measured |
| dedicated cgroup peak | 13,044,125,696 | measured |
| 当前任务cap | 17,179,869,184 | 16GiB |
| 当前WSL guest可见MemTotal/effective_total | 14,654,988,288 | 约13.6485GiB；不能称Windows宿主装机容量 |
| 源CSR B | 11,544,333,940 | derived/recorded |
| 源CSR＋显式转换副本2B | 23,088,667,880 | derived |
| 当前conversion前新增对象请求 | 69,340,657,464 | derived；2B＋4B symbolic guard＋六向量 |
| 当前完整分解入口envelope | 80,884,991,404 | derived；7B＋六向量 |
| host可新增 / 缺口 | 4,873,007,104 / 64,467,650,360 | 同一host gate |
| cgroup当前＋新增 / 扣reserve额度 | 81,647,519,544 / 17,045,651,456 | 同一cgroup gate |
| cgroup缺口 | 64,601,868,088 | 不与host缺口相加 |
| factor symbolic/numeric/probe/RHS | NOT_RUN | 在PETSc conversion之前被拒绝 |

总envelope与cgroup请求之和不同，是后者的实测current包含其他owner；不是相互矛盾的预测。释放adapter/maps后RSS低，不代表完整CSR文件页不占内存；cgroup中file页仍收费。[R2]、[R3]、[R11]

task tree/cgroup swap=0；宿主原有swap非零，WSL-global本次60页swap-in、无新增swap-out，活动归因UNKNOWN。保留这个范围，不写整机零swap；下一轮也不通过修改宿主全局swap来美化结果。[R3]

**只提高当前16GiB cap无法使这个14.65GB guest容纳现有路径。** 需要有足够物理可用内存的实际执行环境。精确零占2.892964%，即使只按结构槽压缩，直接CSR节省也仅333,883,480 B，无法解决当前几十GB新增需求；删零还会改变结构hash与symbolic graph。本轮先分解已经合格的原矩阵，不把压缩作为前置。其对factor填充的影响尚无实测。[R2]、[R11]

## 3. 下一轮执行环境与资源授权提案

### 3.1 推荐一次明确的资源包

建议在**用户现有约2TB物理内存的Linux工作站，或用户明确指定的等效大内存主机**上，给第一次q0分解设置以下合同。具体SSH别名/主机身份、canonical目录、runtime位置必须由实际授权填实；本报告不编造主机名，不执行SSH或迁移。

| 合同字段 | 建议值 | 状态与理由 |
|---|---|---|
| execution_host / host identity | 用户指定的实际主机；记录hostname/boot/资源快照 | 待明确 |
| execution_root | 优先保留/home/shenjh/Projects/MyFEniCSx_task40extra_0p7nm_engineering；不兼容时使用明确批准的新根路径 | 待绑定；目录存在性和canonical身份必须核验 |
| task hard cap | **512GiB = 549,755,813,888 B** | 拟议新授权；不是当前许可或预分配 |
| host reserve | **64GiB = 68,719,476,736 B** | 拟议新政策；与任务cap分开 |
| 运行范围 | 一个已资格regular-reference q0 factor生命周期 | 不自动扩展到all-q或target PDE |
| 数值/并行 | complex128/int32、MPI1、数学线程1、既有exact MUMPS参数 | 保持 |
| 任务内存机制 | 专用cgroup、MemorySwapMax=0、独立watchdog、实时host及ancestor cgroup准入 | 必须可验证 |
| 允许的数据动作 | 仅经批准的本包依赖复制/只读消费；保留源文件 | 待批准源/目标 |
| 运行环境 | 目标Task40独立资格化环境；记录真实runtime/ABI/JIT路径 | 不改其他项目的运行环境 |
| 新heavy窗口 | 总21,600s；数值20,400s；收口1,200s | 授权落定后冻结唯一T0 |

512GiB约为十进制2TB的27.49%。选择这个上限，是为了给尚未知的symbolic/numeric填充留出空间，减少先申请128GiB、刚取得INFOG又回到申请额度的循环；**不是证明q0一定需要512GiB，也不是保证它一定能完成。** cap只允许达到该上限，程序仍按真实对象申请内存。其他任务已占内存由MemAvailable/ancestor cgroup反映，host reserve另保留一次。主控在约定资源时段确认可用量，不能停止他人作业来取得通过。

symbolic之后仍要按实际INFOG(16/17)、current owners、任务上限和host余量做numeric准入。超出固定授权时保存真实估计、缺口及已完成阶段并释放，不偷偷升cap、开OOC/BLR或改排序/主元。80.885GB不是永久数学下界，也不是numeric factor的预测上限。[R11]

### 3.2 授权前后分开执行，避免空等或越权

**授权前可以完成：** 本机只读核验、实际loader依赖清单、V29严格factor-only及执行合同接线、必要轻量fixture、源变更审阅、待批准的资源与路径方案。不得启动旧C命令试探，不动工作站或cap。

**批准必须一次覆盖：** 实际目标主机、Task40专用canonical目录/必要独立环境、所需现成文件的源和目标、512GiB任务cap与64GiBhost reserve、MPI/ABI与单heavy范围、6h固定窗口。本包批准后，若主控已有用户指定工作站的SSH别名和路径，可只读确认后登记；有歧义才问一次具体字段，不能从其他任务任意选主机。

**批准后立即连续执行：** 从本执行包第一项迁移/目标环境准备操作开始冻结T0，登记T0+20,400s数值cutoff与T0+21,600s总deadline。包含必要环境确认、文件转移/导入/hash、构建接线后的检查、factor和checker；普通bug修复不刷新T0。授权前本地准备成本另外真实保留，并在最终单场必要成本分析中按实际用途归账，不能作为“免费预热”。本Chat审阅时间不是计算服务时间。

旧V28 nominal deadline在用户发消息时尚未到，但该批次已经正式收口；不能称它“已过期”，也不能借未到的旧时间继续资源拒绝后的工作。旧window和账本不可变，新包不恢复旧attempt。[R1]、[R5]、[R16]

## 4. 接续代码只补四处，复用现有数值内核

### 4.1 严格factor-only，资格不匹配不回退计算

现有stage2003–2163已经有在adapter创建之前早返回的factor-only分支；它打开完整CSR，保留旧资格source/window，直接调用已有q0 lifecycle。现有资格loader378–468允许新执行window与旧资格window不同；已有fixture101–181覆盖跨窗口复用。这些代码应该保留。[R7]、[R15]

V29新增**明确、被合同hash绑定的“必须COMPLETE＋匹配PASS”策略**；这是待实现的窄策略，不是声称当前已有某个新flag。要求：

1. 两项满足就直接factor-only，标记fill/readback skipped。
2. 不匹配就列出字段、路径或文件hash差异，在adapter、fill、native回读前停止。
3. 修复本次定位/合同接线后继续，不删除旧PASS，不借AUTO默默退回readback。
4. source/window仅作新的execution identity；旧CSR/qualification/producer身份原样继承。
5. 科学DAT字节保持不变。loader核对原input SHA，不能通过改DAT资源字段抬cap，然后重署旧资格。

只有实际科学数组或ABI发生改变才重新审查受影响资格；仅launcher/计时/路径读取接线改变，不撤销既有矩阵native资格。

### 4.2 新资源合同必须贯穿launcher、worker、watchdog和checker

| 已确认的旧绑定 | 位置 | V29最小处理 |
|---|---|---|
| 任意Task40 campaign都设MemoryMax=16G | run_case_in_user_service.sh26–29 | 仅登记的V29合同读取批准的cap；旧分支默认不变 |
| 固定local_w0_wsl runtime/ABI与local_w9_wsl JIT | 同脚本35 | 接收本次已资格的实际路径，不复制旧boot/platform资格 |
| 固定target profile16GiB | physical_intermediate_profile.py337–349 | 执行层受批准的资源合同覆盖；科学DAT及旧profile默认不变 |
| service/campaign只识别旧window与hash | service494–528、1933–1965；campaign相应注册/校验 | 登记独立V29window/selector/authority，不修改V28 |
| checker/watchdog仍从旧profile取cap并验证V28 | service2328及6106–6259相关分支 | 同步消费同一执行合同，保存实际读回值 |

不全局搜索替换16→512，不绕开资源门。task cap、host reserve、当前可用量、路径/ABI、window与policy hash要在各层一致；任何一层仍拿旧16GiB值都应在轻量检查时指出，不能等矩阵打开后再发现。[R8]、[R9]、[R10]、[R14]

科学ABI维持complex128/int32、MPI1和原库栈/构建合同。新主机单独生成imports-only ABI/environment收据，记录新host/boot与库路径；不把旧WSL boot ID伪装成新主机的验证结果，不切换int64、实数PETSc或多线程。缺少同ABI环境时，先在已批准的Task40独立范围解决；不得热改其他项目环境。

### 4.3 文件路径与依赖包必须先做实，不能只复制三数组

当前service还会核验producer六个payload、replay/native记录及V26 row witness，包括约11.23GB的历史surface stream。它们被读取核验不等于重新计算producer/native，但**只复制CSR＋PASS不足以原样执行现有CLI**。从实际loader读取集合生成一次依赖清单，列原路径、目标路径、bytes、内容SHA、所属凭据、用途与是否已有文件；不要复制所有历史artifacts，也不重新生成routes/pattern（源码1568–1824）。[R8]

最快可行方案是在获准目标环境保持相同canonical绝对根和相对artifact树。若目标只能使用不同根路径，则只为本包加入显式old-root→approved-new-root解析：

- 旧manifest、qualification、donor及其中路径字符串保持原字节/hash；
- 新消费/导入sidecar记录旧内容身份与本次实际位置；
- 校验映射后containment、大小和完整内容hash；
- 同步用于CSR opener、qualification loader、donor verifier与checker；
- donor identity hash仍绑定原始科学身份，不用新绝对路径字典冒充原donor；
- 不用sed重写旧JSON，不任意放宽允许目录或关闭hash；
- 身份不匹配按严格factor-only报差异，不回退昂贵计算。

这是有限的定位接线，不开发通用迁移平台。若维持旧完整donor验证链最省实现，直接带齐必要依赖即可；不为省约一个历史stream的传输而先重做信任/资格框架（saved_q0源码1450–1509；stage源码378–468）。[R6]、[R7]、[R8]

同一次导入/打开允许完整实读一次所需文件hash。后续步骤复用由当前消费者持有的已验证状态，不每阶段重复全文件hash；原生命周期要求的CSR内容不变检查仍保留并计时，不能为提速删除科学验收。

### 4.4 在同一次factor运行中把成本测清

现有q0 lifecycle80–519可以保留，但它只记录阶段累计elapsed和整个函数时间，没有单独的conversion/symbolic/numeric/MatSolve计时。V19全q类已有cache_miss_parent_seconds，不等于这个单q函数已经实测过同一指标。[R11]

V29在现有函数与入口添加以下父/子计时，直接随第一次完整factor采集：

| 计时 | 定义与避免误算的规则 |
|---|---|
| 完整service父成本 | 从真实入口准备到必要checker结束；包含本次启动前的selector/donor/文件核验 |
| 初次导入/身份核验 | 文件读取、三数组hash、资格与donor核验；不是将来每次PC必然重复的成本 |
| conversion parent / native call | NumPy转换副本、PETSc创建/assemble、释放与相关证据；原生调用另列 |
| symbolic parent / native symbolic | 构造factor、参数读回、symbolic、INFOG、准入证据 |
| numeric parent / native numeric | numeric调用、INFOG及阶段收据 |
| fresh资格parent | 第一非零测试RHS生成、实际MatSolve、完整true residual、保存/回读及资格；raw solve另列 |
| 第二RHS parent / raw repeated solve | 第二组非零测试RHS完整验证父段，solve_repeated原生时间单列 |
| evict/cleanup | 因子、PETSc矩阵、向量销毁，对象清单及前后资源 |
| F_q | 本次cache-miss所需准备至fresh factor资格完成的父成本；注明是否含初次文件导入 |
| S_q | 同一已驻留factor的一次重复求解成本；测试RHS构造/持久化另列，不能称完整target PC成本 |

现有两组RHS由不同种子的非零x生成b=A_q x，是分解校验用的非零测试RHS；第二次通过solve_repeated使用同一factor。它能测真实重复线性求解成本，尚不是完整target PC一次业务调用。两者都保留完整CSR true residual≤1e-10及向量证据；不要把制造RHS与保存见证的全部父时间当成每次正式业务RHS必需的费用（源码318–435）。[R11]

父段和子段不重复相加，缺失值写UNKNOWN；不从两个大checkpoint差值冒充纯MatSolve时间。每30–60s保存轻量heartbeat，stage开始/完成立即原子写收据；native长调用期间靠独立watchdog记录存活与资源，不因短期无日志就重启。

## 5. 单 q 分解的连续执行与验收

### 5.1 维持已有exact MUMPS路径和参数

直接复用open_saved_q0_csr_from_manifest与run_task40_v26_selected_q0_factor_lifecycle。exact factory仍设置ICNTL(35)=0、(10)=0、(2)=0、(3)=6、(4)=2；禁止扫描排序、主元、BLR、OOC或数学线程。可用已有symbolic_memory_settings只读记录7/10/14/18/22/23以及实际库身份。[R11]、[R12]、[R13]

当前q0生命周期没有调用set_memory_limit_mb/ICNTL(23)，没有找到隐藏的80GB MUMPS硬上限。512GiB是任务资源cap，**不得自动转写为ICNTL(23)**。symbolic后的numeric准入继续使用实际INFOG(16/17)与实时共驻账；保留原单位解码规则和raw INFOG。[R11]、[R12]、[R13]

### 5.2 必须完成到明确出口

| 顺序 | 本轮工作 | 成功或停止时必须保存 |
|---|---|---|
| A | 新执行合同、ABI、文件身份、严格factor-only准入 | 真实主机/目录/资源/window、旧资格及新执行身份 |
| B | 打开现成CSR，PETSc conversion | 额外副本/所有权、时间、RSS/cgroup和释放 |
| C | symbolic | 参数读回、INFOG(16/17)、symbolic时间/峰值、numeric实际需求 |
| D | numeric | 实际INFOG，allocated/used/entries各自原字段及单位、numeric时间/峰值 |
| E | fresh true-residual probe | 完整残差≤1e-10、实际solve计时、输入/RHS/解/残差及hash |
| F | 第二非零RHS，同一factor | 完整残差≤1e-10、重复solve时间、未额外factor的计数 |
| G | evict与checker | 原CSR不变、对象清理、task swap0、后代为空、最终分类 |
| H | 同窗成本/容量整理 | q0实测F_q/S_q、常驻与瞬时峰值、2TB/48h约束和下一项全q计划 |

symbolic通过不能作为正常提前停审点；numeric或probe通过也应在资源/时间允许时继续到第二RHS、释放和checker。普通接线、路径、序列化或变量错误在同窗最小修复、保留失败、新source冻结后接续；不得重跑已接受CSR环节。

真实数值失败保持原阈值，保存RHS/solution/residual及INFOG，先判断是哪一阶段；不把普通bug包装成数值方法失败，不靠更换MUMPS参数、粗化模型或删通道“修复”。真实资源不足保存新的symbolic/numeric证据和具体缺口，释放后结束受影响heavy；不在同条件重复启动。每次heavy结束/停止必须确认完整进程树清场，不能同时留下两个factor作业。

### 5.3 定向软件验证做到必要即可

只覆盖本轮改动：

- COMPLETE＋匹配旧PASS跨新window/source直接factor-only；
- 不匹配时在adapter/fill/readback前停止；
- 新资源合同在launcher/worker/watchdog/checker一致，未授权或cap不符拒绝；
- 绝对路径保持或受限映射后，旧凭据hash不变、内容变化拒绝；
- 计时父/子关系与失败时checkpoint/cleanup保存；
- 保留既有exact controls及两组非零RHS/solve_repeated路径。

沿实际资格化环境运行最小相关fixture和imports-only ABI检查，不重复初始77项整组、整仓pytest、MPI2/4或新小PDE来推迟q0 factor。最终以真实factor运行加保存向量checker验证，不以mock测试通过替代。源码修改后先停旧heavy、冻结clean source，再启动新attempt。

## 6. q0 数据怎样帮助2TB/48h，而不形成新的小模型循环？

### 6.1 测量最终要用于“保留多少个因子、重建多少次”

当前ONE_Q_REFACTOR_V19保留全q CSR但只有一个live factor；cache miss可能重复conversion、symbolic、numeric、probe与检查。降低外层迭代次数不等于总时间降低。已有ALL_Q_RESIDENT可作为全q因子同时保留的路线，但是否装得下只能由完整共驻账决定。[R11]

**不能把1个槽简单改成2/4/6个普通LRU槽就宣称一定减少分解。** 如果PC固定按q0→…→q7循环，小于8槽的纯LRU可能每轮仍全部miss。后续有各q真实成本后：

1. 全8q因子加target/Krylov/恢复/输出共驻安全时，优先复用ALL_Q_RESIDENT。
2. 无法全驻留时，固定保留若干重建代价高的相同精确因子，并为其余q保留一个流转工作槽；按实测F_q与驻留bytes选择。
3. 资源账必须含固定因子集合以及剩余q的最大瞬时构建工作集，不只计算平均factor大小×槽数。

这属于同一精确预条件器的驻留策略。V29先取q0数据并形成表格，不提前开发缓存框架，不用q0乘8冒充其他q实测。其余q的alias、复twist、真实factor填充与target外围成本继续保留UNKNOWN。

### 6.2 两个总约束必须同时成立

内存预算按同一时刻全部对象与系统余量核算：

```math
\begin{aligned}
M_{\mathrm{host}}(t)={}&M_{\mathrm{system}}(t)
+M_{\mathrm{target/reference\ other}}(t)
+M_{\mathrm{all\ CSR}}(t)\\
&+M_{\mathrm{resident\ factor/PETSc}}(t)
+M_{\mathrm{build\ scratch}}(t)
+M_{\mathrm{Krylov/recovery/output}}(t)\\
\le{}&2{,}000{,}000{,}000{,}000\ \mathrm{B}.
\end{aligned}
```

system项包括实际系统/其他任务及保留余量；target/reference other项包括未在其他项计入的FE对象、q映射、Schur模板、transform/inverse bank和恢复所需静态数据；resident factor/PETSc项包括每个live factor、仍与之共存的PETSc输入矩阵及附属owner，不能把转换副本当成早已释放的scratch。Krylov/recovery/output项计入相应向量、临时工作区和输出。所有共享backing按实际所有权只计一次。[R11]

首个q0试验的512GiB cap不等于实测factor驻留量，不能乘8作为全q预测。单阶段或不同q历史峰值也不能直接相加成并存峰值。

单场时间必须包含必要首次构建和实际重建次数：

```math
\begin{aligned}
T_{\mathrm{field}}={}&T_{\mathrm{necessary\ initial\ preparation/build}}
+\sum_q N_{\mathrm{rebuild},q}F_q
+\sum_q N_{\mathrm{rhs},q}S_q\\
&+T_{\mathrm{PC\ other/target/Krylov}}
+T_{\mathrm{recovery/output/checker}}
\le172{,}800\ \mathrm{s}.
\end{aligned}
```

说明哪些准备/身份核验仅首次发生，哪些每次cache miss仍发生；F_q已经包含的fresh probe不再加，S_q中的纯重复solve与测试保存成本分列。V28窗口不重复支付旧pattern是正确的，但最终48h验收必须明确cold/warm起点与必要producer/pattern/CSR/JIT是否归账，不能靠把必需预计算移到“历史”中消失。[R3]、[R11]、[R17]、[R18]

### 6.3 离大模型的下一步已经明确

| 阶段 | 当前状态 / 出口 | 之后做什么 |
|---|---|---|
| q0完整矩阵/native | 本review接受 | 不再作为下一轮重复主任务 |
| q0精确factor | V29获准后唯一heavy | 得到真实分解、solve及内存信息 |
| 其余q＋因子驻留选择 | 根据q0证据规划并继续资格化 | 原尺寸参考PC与真实target接线 |
| 原尺寸非分离pilot | 完整求解、full A6、恢复/输出/物理检查 | 量化误差与全链成本 |
| 最终资格 | 精度合格、整机≤2TB、task swap0、必要全过程≤48h | 才能宣布目标达成 |

最终A6和物理输出是在完整target求解后验收，不能循环要求它们在首次pilot开始前已通过。若单q实测已经显示时间/内存不支持现行驻留方案，应据实调整同一因子的生命周期或给出明确不可行范围；不返回无限缩尺、小面板或另造新PC。

## 7. V29交付合同

response_v29先回答：**是否开始并完成实际factor；symbolic/numeric/raw MatSolve/F_q/S_q分别多少；常驻和瞬时峰值多少；两组完整残差多少；如何据此推进全q及原尺寸。** 随后再写bug、测试和文档。

本轮由主控集中提交/push同一分支；执行者不提交，不改master，不新开其他项目/聊天或执行subagent。目标Task40工作树/独立环境若需要创建，只在用户明确批准的目标目录范围实施。Chat仅提交本review；旧数据和数值源码不由Chat改写。[R16]

应交付：

- response_v29.md及operator/resource compact，分别写实测、派生、UNKNOWN、NOT_RUN。
- 新执行资源授权记录、固定window、runtime/ABI、路径映射/依赖清单、actual source/input/旧CSR/PASS身份。
- **由实际实现的prepare产生并经过轻量验证的唯一factor-only命令**，保存shell文本、参数、环境、policy/window hash和attempt目录；不能只改旧handoff C中的日期。
- conversion/symbolic/numeric/probe/第二RHS/evict逐阶段证据、raw INFOG、原始向量与独立checker。
- 完整service父时间、各阶段父/子时间、task/host swap范围、simultaneous tree/cgroup与文件页、清场证据。
- run index、summary/test_summary、两级模型/进度总账，及下一全q/2TB驻留/48h决策。

若尚未获得资源授权，先完成本地准备并交出具体待批准合同，不进行第二次16GiB factor拒绝；不得把“准备就绪”写成factor完成。获准后直接消费本次准备，不另开一轮review才能开始。

## 附录 A：现在即可交给Codex执行的只读起点

以下命令是已有工具，只核验本机小元数据并列出数组，不启动service，不重算CSR。HEAD核对本次已发布Review V29的实际提交；科学数据继续绑定c662和原input。命令在指定Task40 workdir、/bin/bash、login:false执行，任何一项失败都先读清错误，后续不得无条件继续。

```bash
set -euo pipefail
cd /home/shenjh/Projects/MyFEniCSx_task40extra_0p7nm_engineering

git branch --show-current
git rev-parse HEAD
git status --porcelain

TASK40_CSR_DIR=results/task40extra_nonseparable_0p7nm/task40extra_0p7nm_target_original_ny8_operator_probe_v22__full3d_iterative__mpi1__Mna/20261011T153931.649307Z/v27_q0_csr
TASK40_V28_RUN=results/task40extra_nonseparable_0p7nm/task40extra_0p7nm_target_original_ny8_operator_probe_v22__full3d_iterative__mpi1__Mna/20261012T002559.817050Z

sha256sum \
  "$TASK40_CSR_DIR/task40_v27_q0_csr_manifest.json" \
  "$TASK40_CSR_DIR/task40_v28_q0_csr_continuation_manifest.json" \
  "$TASK40_V28_RUN/v28_q0_native_qualification.json"

jq -e '.status == "COMPLETE_CSR" and .native_qualification.status == "PASS_COMPLETE_Q0_CSR_NATIVE_READBACK"' \
  "$TASK40_CSR_DIR/task40_v28_q0_csr_continuation_manifest.json"

jq -r '.csr_artifacts | to_entries[] | [.key, .value.path, .value.bytes, .value.sha256] | @tsv' \
  "$TASK40_CSR_DIR/task40_v28_q0_csr_continuation_manifest.json"
```

sha256sum输出应与§1.3三个对应小文件hash一致；jq状态guard只证明起点，正式loader还须验证完整资格和文件内容。旧C命令没有在本报告中伪装成新命令；V29 heavy command待资源批准和窄接线实现后由prepare产出。

## 附录 B：拟议资源合同与最后一次批准内容

以下是**待批准提案**，不是已生效运行配置，也不是当前CLI已支持的JSON schema。具体host/root/runtime与许可凭据未落实时不得启动。

```json
{
  "proposal": "Task40extra Review V29 first qualified q0 factor",
  "authorization_status": "PENDING_USER_AUTHORIZATION",
  "repository": "Rookie1234567/MyFEniCS",
  "branch": "task40extra_0p7nm_engineering",
  "execution_host": null,
  "execution_root": null,
  "runtime_prefix": null,
  "allowed_operation": "existing_complete_qualified_q0_factor_only",
  "proposed_task_memory_max_bytes": 549755813888,
  "proposed_host_reserve_bytes": 68719476736,
  "task_memory_swap_max_bytes": 0,
  "mpi_ranks": 1,
  "math_threads": 1,
  "scalar_type": "complex128",
  "index_type": "int32",
  "mumps_controls": "preserve existing exact backend",
  "artifact_transfer": "pending explicit source/destination approval",
  "t0_utc": null,
  "total_window_seconds": 21600,
  "numeric_cutoff_after_t0_seconds": 20400,
  "closeout_reserve_seconds": 1200,
  "auto_cap_increase": false,
  "all_q_heavy": false,
  "target_pde": false,
  "master_merge": false
}
```

需要用户最后确认的内容可集中为：

“批准Task40 V29在我指定的现有约2TB Linux工作站进行一次现成q0分解；任务固定上限512GiB、宿主留64GiB、任务swap0、MPI1/数学线程1、原ABI和MUMPS参数、固定6h窗口。允许主控核实指定SSH主机和Task40专用canonical目录，在该范围准备同ABI独立环境并复制本包所需现成文件；源文件、其他项目和master不动。不自动提高上述cap，也不扩展到全q或target PDE。实际主机/SSH别名、目录及数据目标在启动前登记。”

这项确认来自用户本轮的明确边界及Task40 AGENTS，不是普通bug导致停审。若用户只批准其他数值/环境，按实际许可登记，不把本建议512GiB当成默认已许可。

## 附录 C：可直接交给Codex的完整执行文本

```text
继续 Task40extra，完整阅读同一分支 task40extra_0p7nm_engineering 的 Review V29。审阅正式结果HEAD为b76ef700ad5f5d113f3be2115b128e5109454a44，V28科学source为c6624391d8f96e257d1efa914cb38821e2a87eb9。先拉取并核对实际Review V29提交，不把旧结果HEAD当新执行HEAD。

V28的regular-reference q0完整CSR/native资格已经接受：777644²、577061168结构槽、complex128/int32、11544333940 B，四次native最大约1.911658e-14。保留旧manifest、三数组、native PASS、保存输出与donor原字节/hash，不重跑producer、FE/MPC/native、routes、pattern、fill或四次native回读。当前只有q0矩阵资格；factor/all-q inverse/真实非分离target PDE/最终精度/2TB与48h仍未通过。

本轮唯一heavy是已有矩阵的conversion→symbolic→numeric→fresh true-residual probe→第二非零RHS→evict及checker。普通bug同窗定向修复并继续，不逐阶段停审。

一、先完成本地准备，资源批准最后落实。
在现有/home/shenjh/Projects/MyFEniCSx_task40extra_0p7nm_engineering内按Review附录A核验分支、HEAD、工作树与三个小凭据hash，列出三数组。生成当前loader实际依赖清单，含原路径/目标路径/bytes/hash/用途/已有与待复制状态。现有service还核验约11.23GB历史surface stream等producer/replay/native/witness，不能只带三数组和PASS便声称旧CLI可运行。只读核验不等于重跑producer/native。
准备严格factor-only、执行合同与计时的窄接线和必要fixture。未获准前不SSH、不迁移、不启动旧C命令、不提高cap。

二、把资源提案交主控一次落实。
建议在用户指定的约2TB Linux工作站，固定task cap512GiB=549755813888 B，host reserve64GiB=68719476736 B，专用cgroup/MemorySwapMax0，MPI1/数学线程1，原complex128/int32 ABI与exact MUMPS参数。此为待用户批准提案，不是既有授权；主机/SSH别名、canonical根目录、runtime/ABI/JIT、文件源和目标必须实填。批准已覆盖的后续动作不重复请示。
当前WSL guest可见物理总量只有14654988288 B，原16GiB条件不得再试。512GiB是固定上限，不预分配、不保证成功、不自动变成ICNTL23；symbolic后仍按INFOG和实时host/ancestor cgroup准入。不足就保存新INFOG/峰值/缺口并释放，不能偷升cap或改OOC/BLR/排序/主元。

三、保留科学身份，只改新执行合同。
科学DAT SHA134ea5f08d5d5dbc366870f451ba0de0df5893c5cd73d227dac77f8a11aa2c0b保持不变。新host/cap/window/source放独立执行合同，不改DAT资源字段后重署旧PASS。
COMPLETE manifest SHA ca3c8de9093fd1cfe9e17c8eb557cd2f96920a3ee110549f007e70835d4a2290，native PASS SHA63babb2943b7e0f613a2c531afd09f931c4ee5504a345748c52f6ef38b0e9c81，旧资格source/window原样保留。现有loader允许跨window复用，不因新review/source重新做native。
优先在获准环境保持原canonical绝对路径。只能异根时，用本包有限old-root→approved-new-root解析及sidecar，保留旧JSON字节和donor身份，核验映射后containment/完整hash；同时接入opener、qualification loader、donor verifier和checker。不要sed旧manifest/receipt，也不写通用迁移平台。

四、复用现有factor-only快路径，禁止AUTO回退。
stage_runner已有adapter之前早返回的factor-only分支，复用它和open_saved_q0_csr_from_manifest、run_task40_v26_selected_q0_factor_lifecycle。V29明确要求COMPLETE＋匹配PASS；不匹配在adapter/fill/readback前报具体字段或路径差异，不自动回退。修复本次定位/合同后直接继续。
旧handoff C仍绑定V28窗口、MemoryMax16G及WSL runtime，不是新环境命令。窄登记V29 window/resource/selector，批准的同一cap/host reserve必须贯穿shell launcher、worker livegate、独立watchdog和checker；不全局替换16→512、不改其他默认。imports-only确认目标实际ABI/库栈，记录新host/boot，不借旧WSL收据冒充新环境。
由实际prepare生成唯一可复制factor-only命令及合同hash，并用轻量fixture验证参数/路由。不要写一个源码尚不支持的--v29-*或--memory-cap选项并称可执行。

五、一次运行把factor成本测清。
完整service计时从真正入口开始，包含selector/donor/hash准备。V28已有1316.226/1464.153s父链未覆盖第一事件前全部准备，保留历史UNKNOWN，不重跑V28。
在现有q0 lifecycle添加conversion、symbolic、numeric、fresh MatSolve、repeated MatSolve原生子计时及对应完整父段；记录输入加载/hash、资格保存、第二RHS测试构造/持久化、evict、checker。F_q记录从cache miss必要准备到fresh资格保存的父成本，并声明是否含初次文件导入；S_q另列同factor重复solve和测试RHS完整父成本。父子不重复相加，不把整个lifecycle elapsed当F_q。
保留原ICNTL35=0、10=0、2=0、3=6、4=2，其他参数不扫描；可只读记录symbolic_memory_settings及raw INFOG。已有两个不同种子的非零测试RHS都用完整CSR true residual≤1e-10；第二次使用solve_repeated且不重新factor。保存input/RHS/solution/residual及hash、solve/factor计数、每阶段INFOG/时间/峰值，完成阶段立即原子写回。
独立watchdog持续记录tree/cgroup/anon/file/dirty与task swap、host基线和活动范围；native长调用不因无短期日志重启。结束必须evict、源CSR不变、对象清理、task swap0、后代为空，checker独立核验保存向量。

六、固定窗口及连续推进。
授权前本地准备成本真实另列，不启动heavy窗口。批准后从本包第一项迁移/目标环境准备开始冻结新T0，总21600s，数值cutoff=T0+20400s，收口1200s；bug修复不刷新T0。旧V28已正式收口，旧window/账本/失败不改写，不能借其nominal截止尚未到恢复旧批次。
单heavy、保持已授权主机/目录/ABI，不新建聊天或执行subagent，不改其他项目或master。主控集中冻结/提交/push；执行者不commit/push。定向软件检查只覆盖本轮接线、跨窗/路径/资格拒绝、资源一致性、计时与cleanup，不重跑整仓/旧77项整组/MPI2/4/新小PDE。

七、q0完成后同窗给出面向2TB/48h的决策。
立即报告实测F_q、raw repeated solve、测试RHS父成本、真实factor常驻与瞬时峰值；不能拿q0乘8称整场实测。列出其余q、target/Krylov/恢复/输出尚未知的成本。全共驻账明确包含各live factor对应仍保留的PETSc输入矩阵、源CSR、target与reference的FE/映射/模板/inverse bank，以及构建和Krylov/恢复/输出工作区；实际共享backing只计一次，不能只用INFOG factor内存代替整机账。
如果全q实测并存账允许，后续优先复用已有ALL_Q_RESIDENT；否则评估固定保留高重建代价因子＋一个流转槽。固定8q循环下小于8槽的普通LRU可能每轮全miss，不按槽数线性推断提速。本轮不先开发新缓存或新PC。
最终48h账包含该场必要初始producer/pattern/CSR/JIT/构建和实际重建/RHS次数、target/Krylov、恢复/输出/checker，初次准备与每次cache miss分开，不能把必需预计算藏到历史里。
交response_v29、operator/resource compact、资源授权/window/ABI/依赖映射与真实启动命令、分阶段raw证据和checker、run index、summary/test_summary、两级模型/进度总账。先回答factor完成没有、分解/RHS花多久、峰值多少、残差多少、下一步怎样进入其余q和原尺寸，再写bug和测试。资源尚未批准则交完整准备包和待批准字段，不制造第二次同16GiB拒绝。
```

## 附录 D：冻结来源

所有链接固定在本次正式交付HEAD。源码行号仅指该冻结版本；本报告中的新策略、资源数值与V29合同均明确标为任务要求或待批准提案。

[R1]: https://github.com/Rookie1234567/MyFEniCS/blob/b76ef700ad5f5d113f3be2115b128e5109454a44/docs/task40extra_0p7nm_engineering/response_v28.md
[R2]: https://github.com/Rookie1234567/MyFEniCS/blob/b76ef700ad5f5d113f3be2115b128e5109454a44/docs/task40extra_0p7nm_engineering/outcomes/records/target_operator_probe_v28.json
[R3]: https://github.com/Rookie1234567/MyFEniCS/blob/b76ef700ad5f5d113f3be2115b128e5109454a44/docs/task40extra_0p7nm_engineering/outcomes/records/time_resource_accounting_v28.json
[R4]: https://github.com/Rookie1234567/MyFEniCS/blob/b76ef700ad5f5d113f3be2115b128e5109454a44/docs/task40extra_0p7nm_engineering/outcomes/records/run_index.json
[R5]: https://github.com/Rookie1234567/MyFEniCS/blob/b76ef700ad5f5d113f3be2115b128e5109454a44/docs/task40extra_0p7nm_engineering/outcomes/target_stage_handoff_v28.md
[R6]: https://github.com/Rookie1234567/MyFEniCS/blob/b76ef700ad5f5d113f3be2115b128e5109454a44/src/solvers/task40_v27_saved_q0.py
[R7]: https://github.com/Rookie1234567/MyFEniCS/blob/b76ef700ad5f5d113f3be2115b128e5109454a44/src/runners/task40_v20_stage_runner.py
[R8]: https://github.com/Rookie1234567/MyFEniCS/blob/b76ef700ad5f5d113f3be2115b128e5109454a44/scripts/task40_v20_service_workflow.py
[R9]: https://github.com/Rookie1234567/MyFEniCS/blob/b76ef700ad5f5d113f3be2115b128e5109454a44/scripts/run_case_in_user_service.sh
[R10]: https://github.com/Rookie1234567/MyFEniCS/blob/b76ef700ad5f5d113f3be2115b128e5109454a44/src/runners/task40_v10_campaign.py
[R11]: https://github.com/Rookie1234567/MyFEniCS/blob/b76ef700ad5f5d113f3be2115b128e5109454a44/src/solvers/task40_v10_p6_mumps.py
[R12]: https://github.com/Rookie1234567/MyFEniCS/blob/b76ef700ad5f5d113f3be2115b128e5109454a44/src/solvers/fullspace_v17_p3_oracle.py
[R13]: https://github.com/Rookie1234567/MyFEniCS/blob/b76ef700ad5f5d113f3be2115b128e5109454a44/src/runners/physical_p4_cell_condensed_v18.py
[R14]: https://github.com/Rookie1234567/MyFEniCS/blob/b76ef700ad5f5d113f3be2115b128e5109454a44/src/io/physical_intermediate_profile.py
[R15]: https://github.com/Rookie1234567/MyFEniCS/blob/b76ef700ad5f5d113f3be2115b128e5109454a44/src/test/test_task40_v28_q0_continuation.py
[R16]: https://github.com/Rookie1234567/MyFEniCS/blob/b76ef700ad5f5d113f3be2115b128e5109454a44/docs/task40extra_0p7nm_engineering/AGENTS.md
[R17]: https://github.com/Rookie1234567/MyFEniCS/blob/b76ef700ad5f5d113f3be2115b128e5109454a44/docs/task40extra_0p7nm_engineering/task.md
[R18]: https://github.com/Rookie1234567/MyFEniCS/blob/b76ef700ad5f5d113f3be2115b128e5109454a44/docs/task40extra_0p7nm_engineering/review_report_v28.md
[R19]: https://github.com/Rookie1234567/MyFEniCS/blob/b76ef700ad5f5d113f3be2115b128e5109454a44/src/solvers/task40_v10_p6_yorbit.py
