# Review V16：接受冻结方向归因，暂停 FEINN 数值探索并完成一次交接

## 0. 本轮裁决与精确身份

**接受 Response V16：Review V15 的检查器修复、原记录复验和两条冻结方向归因已经完成。现有证据不足以让 FEINN 继续承担主求解器，也不足以批准生产初值或神经修正器。下一轮只授权一次轻量交接和研究工具依赖清单整理，不分配新训练、优化或 PDE。** 这是有证据的研究收口，不是所有神经表示不可能成功的证明。

最终目标仍是**原尺寸50×25×140 nm、Si线宽17 nm/高120 nm、λ=0.7 nm的完整三维有限元解**，保留非可分三维缺口、内部自由度、双Floquet和完整端口能力。整机物理内存上限为**十进制2,000,000,000,000 B**、swap=0；准备、冷JIT、装配、辅助求解、训练、完整恢复、独立验算和输出的必要流程合计≤**172,800 s**。较长波长、缩小几何和小型线性诊断均不能替代该目标。

| 冻结项 | 本轮核对结果 |
| --- | --- |
| 唯一执行分支 / 审阅输入HEAD | `task42extra_feinn_5nm` / `89d24fa253aa6d9c8109e1d8b1983d964388e826`；远端精确ref与本地相同，工作树干净，ahead/behind=0/0 |
| 上轮review发布 / 本轮增量 | `788ac4c174263321a8fff8f86d856a4e9ebe8075`；2个新提交、22个文件；checker、保存方向代数及测试改变，训练和FE数值核未改变 |
| V16检查器实际源码 | `a14dd6187336c866f0a327760f10c4ece0140a8d`；文档HEAD不能冒充运行源码 |
| V15数组分析 / 原C1数组源码 | `99f2968be8d715a6f2e6985f5b032c53ca505950` / `bc4c2026f8a9510c90424d24f1808a288413bba4` |
| 冻结base / canonical / worktree | `fbac3d8777fcfd897d93b898cb9f460f79ddd6ff` / `/home/fenics/Projects/Maxwell3D-Lab/task-repository.git` / `/home/fenics/Projects/NN-Lab-V2`，已登记工作树 |
| 主线最新远端 | `task40extra_0p7nm_engineering` / `b8bd7c2f23726142161b58a7d7ff52275ea677ba`，已有Response V5；不再停留于“仅已分配Gx784” |
| dot最新远端 | `task40extra_dot_parallel_cloud` / `eb5b0ecc1afe593f626b44a6038f7f26651b3317`，新C1入口尚无新FE资格结果 |
| 明确排除的分支 | `task42_neural_coarse_inverse` / `b9e2d587cec6a2418573faa4e3c87721194914eb`；`task42extra_NN-V3-learned-iteration` / `1f01ae46bbe21f17200350a46513ef5f33e5cf6a`；只核对ref，不取作本支数值证据、不修改 |

依据为[任务书](task.md)、[Review V15](review_report_v15.md)、[Response V16](response_v16.md)、[README](README.md)、[完整历史summary](outcomes/summary.md)、[V16专题](outcomes/checker_integrity_v16.md)和[运行索引](outcomes/records/run_index_v16.json)。V1–V15任务、review/response及完整训练/FE接口的既有审阅继续有效；本轮核对增量并复用未变源码及hash资格，不将旧材料当成新结果。训练路径的完整矩插值、原方程/端口消元、Riesz辅助因子、相位表示、GN、缓存与参数度量均保留原限定。

裁决为 **ACCEPTED_WITH_SCOPE_LIMITS / FEINN_MAIN_SOLVER_ON_HOLD / NO_VERIFIED_NN_INCREMENT**。没有production numerical/core晋级，没有merge approval；本review只写入FEINN执行分支。

## 1. V16验收：记录完整不等于求解合格

检查器的作用是独立读回证据，避免缺数据、错标签或人工结论被当成实验成功。修复只改变证据验收边界和已有方向的解释，没有生成新的网络场，也没有改变旧优化结果。

| Review V15要求 | V16证据与本轮核验 | 裁决及边界 |
| --- | --- | --- |
| P0-A 配置、四点与冻结证据 | 原8个唯一配置、32个zero/residual/field/common点、4个候选和真实ledger一致；缺失/重复/额外key、错用途、错账本按影响拒绝或UNKNOWN | 接受；合法partial不提升为完整通过；文件hash还须结合源码白名单/执行顺序测试解释无标签资格 |
| P0-B 独立分层判定 | F/R/native及小证书从原数组复算；覆盖COMPLETE、数值有效PASS、阈值6有限排除/2参考oracle可行、界宽4 UNKNOWN/4 PASS、无标签准入NOT_ADMITTED | 接受；M3600的界宽UNKNOWN保留，不能被“COMPLETE_RECORDS_VERIFIED”覆盖 |
| P1-C 两条冻结方向归因 | M3600与Mfinal的原残差一阶项均为正；端点最大重构缺陷5.56e-16≤1e-10 | 接受DIRECTION_NATIVE_CONFLICT；不是缩步即可修复的线性过冲 |
| P0-D 干净源码复验一次 | a14dd618上仅重验原result一次；SHA256仍为ea99221df016b6750be227491dd6160c42582c31310df97d940ef16e19eada2c；原producer/优化/FE/网络前向0 | 接受；旧数值来源不变，不再为本review重复完整checker |
| 测试、失败与费用 | 最终受影响75项通过；相关143项在仅增加pure/clean/source guard之前通过，未变代数按hash复用；Ruff/compileall通过；最初8失败/67通过和文档缺记录失败均保留 | 接受限定范围；本地测试，不声称全仓、MPI、FE或CI通过；两次局部意外修复已记录 |
| 文档交付 | V16新页面本地结构/链接通过，但当时资源第二次拒绝后未启动浏览器；不是实际渲染PASS | 保留旧NOT_RUN；本review的实际补验结果另存审阅收据，后续通过不得追改旧记录 |

本轮审阅在pure环境独立核对**34个源码/输入/候选/账本/测试与监督文件hash**，重现上轮5类错误输入的拒绝或冻结资格UNKNOWN，并直接从原NPZ做两态三范数内积复算。未调用producer、完整checker或新优化。审阅worker为**2.070735534 s、同时进程树RSS峰76,230,656 B、自身swap0、后代清场**；这是轻量审阅成本，不是求解时间。详细路径、脚本、hash、渲染及发布成本见[审阅收据](outcomes/records/review_v16_evidence_audit.json)。

V16唯一原记录checker为4.950958552 s、树峰194,895,872 B。其完整批次在06:58:50 UTC快照为1290 s，另留600 s发布额度，保守1890 s；不能把约5秒worker当完整流程。历史项目累计是部分实测与保守记账，缺失尾段仍未知，不能当目标单次48小时验证或剩余运行余额。本次审阅费用也单列，不嵌套重复相加。

## 2. 已试、已否定及仍未验证的内容

下表沿用同M5身份：5 nm、10×7.5×10 nm的Si/air三维缺口、384 hex、Nédélec p3/q15、31968独立复FE、2082周期slave、40有序端口、8966实FP64参数；掠角1°、φ0°、s偏振，n=0.99396854453+0.00435380777i、ε=n²、μ=1、exp(-iωt)。native是代回原方程的不平衡除以固定载荷范数；散射E/curl误差是相对同p3准确参考的场距离。它们均越小越好，含义不同。

| 历史 / 必须保留的实际结果 | 已排除的下一步 | 仍未证明什么 |
| --- | --- | --- |
| V1–V2 EUC/DUAL/FREE及对角变量尺度；native约0.928/1.10/0.597，缩放FREE仍约0.608 | 不重复初始三路线或同类对角缩放 | 不能把失败单归于网络；测试范数和优化条件仍有影响 |
| V3–V6监督拟合、冻结特征确定性读出；监督G误差约1.387%/1.159%，195复特征native最小约0.57058 | 不把读出最小二乘或监督改善算NN无标签解；不重训同监督基线 | 预算内拟合不是数学表达上界，完整网络全局表达仍UNKNOWN |
| V7–V10相位、p4/p5、GN和缓存；phasefit E=0.00955792521、curl=0.0100342088、native=0.531472182 | 不继续原GN、单纯延长训练、重复加阶；缓存1.46–1.57倍单列工程等价收益 | p敏感性是真实离散限制，但不解释同p3原代数方程未解准 |
| V11一次八组参数度量设计、I/M两路；不是八次独立训练。M3600→Mfinal：native 0.885852183253→0.846541904928；E 0.093300276471→0.122944519716；curl 0.093541515196→0.123039105854；loss 0.094314671576→0.087206078410 | 中间较好态和最终退化均保留；不事后按参考挑终态，不扫层尺度/阻尼/权重/seed/时长 | loss和native下降都不足以保证场变好；六个后续接受步的退化不能被较好截图掩盖 |
| V12–V13保存向量、导数/MPC已测接口；同总场背景换元使p3参考在p4的残差3.55236→5.20557 | 不重复完整矩、Floquet和背景修正；没有证据把当前失效优先归为边界漏施加 | 只排除已测接口，不证明任意几何/端口/连续稳定性；新E/curl交叉及邻层积分仍NOT_RUN_RESOURCE_WINDOW |
| V15–V16固定PDE8/ALL16局部球；两态PDE8无标签不准入，终态ALL16参考oracle可行；两条PDE8方向从起点增加native | 不再投影/调半径/改余量来凑通过，不把参考方向收益说成NN增量 | 限定8/16个已保存方向；不是8966参数全切空间或非线性全局结论 |
| D0必要前缀≥15758.7401 s，对完整传统基线672.4629 s被成本否决；D1 NOT_RUN_COST_VETO | 不启动传统完成器掩盖费用，不删训练/Gram前缀、换成warm-cache成本 | D1未运行不是数值失败；目前无可部署初值证据 |
| 原尺寸0.7 nm、全成本、部分旧optimizer/RNG | 不把缺项补造成通过，不重演丢失历史 | 目标仍NOT_RUN/NOT_QUALIFIED；旧状态缺失仍NOT_RETAINED |

当前残差约0.85而门限1e-6，散射场误差约9%–12%而门限1e-4，差距远超过数值边缘。有效解继续要求完整native/增广/独立FE残差≤1e-6、MPC≤1e-10、规定total/scattered E/H/curl及全部复通道≤1e-4、功率/能量≤1e-5、逐级功率≤1e-6和原求积门；真正NN增量还需同严格精度、同完整必要成本下时间或RSS至少改善20%，另一项合规。

## 3. 瓶颈判断：局部目标不一致已经实证，全局表达上限仍未知

Riesz对偶范数给不同的方程残差方向不同权重，目的是让弱残差具有明确的有限元意义；它需要额外Gram因子和求解。对于当前开放、损耗的Maxwell离散，减小这个量不会自动以足够的常数控制场误差，也不会自动减小原方程的欧氏残差。新证据支持这种**度量与更新方向之间的局部分歧**，没有测出完整空间的稳定性常数。

取已冻结参数方向α，在已有线性响应中令δr=Yα。N相对于当前残差能量归一，正式native仍除原norm(f)=0.29104200262261154，不更换分母：

```math
N(s)=\frac{\|r+s\delta r\|_2^2}{\|r\|_2^2}
=1+b_Ns+c_Ns^2,\qquad
b_N=\frac{2\,\mathrm{Re}(r^*\delta r)}{\|r\|_2^2},\qquad
c_N=\frac{\|\delta r\|_2^2}{\|r\|_2^2}.
```

| 保存态 / 同PDE8主rcond=1e-10 | b_N / c_N | s=1的F / R / N | native起点→已保存线性步 |
| --- | --- | --- | --- |
| M3600 | +0.00519171721558 / 0.000417622223940 | 0.996151144653 / 0.999782594069 / 1.005609339440 | 0.885852183253→0.888333231652 |
| Mfinal | +0.00198117264606 / 0.000341886406808 | 0.997525889151 / 0.999588352612 / 1.002323059053 | 0.846541904928→0.847524617952 |

F为相对当前G场误差能量，R为相对当前G对偶残差能量，起点均为1。b_N明显大于约2.32e-15/2.10e-15的操作舍入余量，c_N为正，因此**沿这两条线性方向，任何正s都会增加N**。这排除了“同一方向只需缩短正步长”这一解释；没有计算新步，没有推断远处非线性网络轨迹，也未排除其他方向。

| 竞争解释 | 证据权重 / 本轮判断 | 是否足以安排新训练 |
| --- | --- | --- |
| 网络表达能力不够 | 监督与相位改善说明表示会影响拟合，但既有拟合未到严格门；预算/优化未分离，不能证明表达上限 | 否；“上限未知”本身不是扩宽/多载波/换网的准入证据 |
| 离散弱残差、试验范数与场目标不一致 | M3600退化段、两态有限方向及V16正b_N直接支持；R下降不等于native或场同步改善 | 当前最强的局部解释；不等于已验证新范数或新测试空间能修复 |
| 边界、Floquet、插值或背景错误 | 现有完整矩/非零相位/原算子与导数接口已过；背景转换未消除问题 | 当前优先级低；需新的具体反例才重开相应接口，不泛化排除所有边界问题 |
| 损失权重、参数尺度或阻尼 | 八组参数度量已有试验，Riesz能量和native实际分歧明确；没有验证某个新权重 | 不扫描；不能用较好loss替换原Gate |
| 优化算法或单步过大 | 原GN/缓存续算没有合格解；V16排除两条冻结线性方向的正向缩步修复 | 不重复优化器微调；全参数/非线性未证明，不构成自动续算理由 |

有监督拟合收益、无标签PDE能力、确定性方向组合收益、真正NN增量四者继续分开。ALL16用了参考场方向，PDE8虽无标签构造也只是网络局部导数的确定性组合；都没有同精度、同成本非NN对照的神经收益资格。缓存/组装复用只记工程贡献。

## 4. 两条并行线的最新证据与分工

主线以提交固定的[Response V5](https://github.com/Rookie1234567/MyFEniCS/blob/b8bd7c2f23726142161b58a7d7ff52275ea677ba/docs/task40extra_0p7nm_engineering/response_v5.md)、[closeout](https://github.com/Rookie1234567/MyFEniCS/blob/b8bd7c2f23726142161b58a7d7ff52275ea677ba/docs/task40extra_0p7nm_engineering/outcomes/records/review_v5_execution_closeout_v1.json)及[Review V5](https://github.com/Rookie1234567/MyFEniCS/blob/b8bd7c2f23726142161b58a7d7ff52275ea677ba/docs/task40extra_0p7nm_engineering/review_report_v5.md)为准。dot以[新C1候选](https://github.com/Rookie1234567/MyFEniCS/blob/eb5b0ecc1afe593f626b44a6038f7f26651b3317/docs/task40extra_dot_parallel_cloud/outcomes/fresh_c1_candidate_v1_zh.md)和此前[Response V15](https://github.com/Rookie1234567/MyFEniCS/blob/eb5b0ecc1afe593f626b44a6038f7f26651b3317/docs/task40extra_dot_parallel_cloud/response_v15.md)区分新环境待验与旧环境成功。

| 线别 / 最新证据 | 不能移植为FEINN结论的差异 | 下一责任 |
| --- | --- | --- |
| 主线Gx784正式尝试在FE前退出：旧worker要求observe_only，与新enforce-time策略冲突；3.939483342 s流程、133,492,736 B树峰、swap0，无场/残差/RTA。源码修复已测，唯一bug replay额度已用 | 这是工程失败，不是数值不收敛；更不能用小失败RSS估计setup/KSP/恢复。旧Gx→F5 E/curl约1.376e-6/8.788e-7与Gz→F5约2.612%/2.750%仍为既有缩放证据 | 主线审阅决定是否再授权同一Gx784；FEINN不修改其worker、不另起同模型 |
| 主线已生成原尺寸AUTO 32060 ordered modes及digest；derived候选272×4×14=15232 cells、p6独立9948672、retained3126332；一个dense H=16,445,497,600 B、74条外层向量=3,701,577,088 B | 这些是库存/对象payload，不是同时RSS或准确网格资格；全q fill、JIT、C/D、恢复和完整耗时仍unknown。不能把unknown计0或把32060端口当完整内域通过 | 原尺寸成本与传统求解器容量仍由主线/dot做；FEINN不重复AUTO或存储实验 |
| dot旧Y：p4、120cell、六q/三twist、manual532，原三维残差约1e-11并完成保存checker；新C1候选79项pure合同及imports通过，实际FE/JIT/p6/p4链与持久raw仍待资格 | φ5°而主线φ0°；Y缺口沿y平移，不能作为X/XZ同场收敛点；旧532、旧ABI结果不等于新C1或目标AUTO32060 | dot按其持久保存及C1a/b/c→C2条件执行，FEINN不接管 |

跨线比较前必须同时核对：几何尺寸/缺口坐标、Si材料和频率、波长与光学尺寸、Nédélec阶次及试探/测试空间、网格与求积、Floquet相位/入射/背景、完整端口keys/归一化、total/scattered E及H单位/curl尺度、误差分母/近零规则、参考身份和完整成本口径。M5的5 nm材料、40端口和同p3代数目标，与主线7/135缩放的0.7 nm、p6/准确p4、340模式，以及dot的p4/φ5/532都不可直接排名。主线1%离散对照门也不能替换FEINN原1e-4同离散场门。这里更新分工，不裁定其他分支通过、不授权跨支修改。

## 5. 下一轮执行批次：一次交接，条件明确，完成即停

输入是本review发布提交及其祖先**89d24fa253aa6d9c8109e1d8b1983d964388e826**；数值入口仍为[run_index_v16](outcomes/records/run_index_v16.json)、旧result SHA256 `ea99221df016b6750be227491dd6160c42582c31310df97d940ef16e19eada2c`、旧C1向量 SHA256 `22c5200d6744cb3e0e4e360dae597fcb3f26b96bf80d478b2fff7d050ccd2263`及全部四候选的完整hash。安全同步同分支；若远端已有同任务新response，先读增量，不退回旧HEAD。所有下列工作都不需要FE/ML环境、不启动训练。

### P0-A：一次完成暂停交接与最新状态同步

诊断问题已得到当前可支持的结论，下一步要防止接续方把历史“下一步建议”重新当作待执行任务。更新现有README和summary顶部当前导航，指向本review，明确**数值探索暂停、无主求解器/初值资格、D1未运行**。保留所有历史正文，不删除V14曾暂停及V15–V16受控重开记录；不批量重写旧任务书、review或response。

在同一份`response_v17.md`用一张表回应P0-A/P0-B和条件P1，列精确HEAD/base/tracking/worktree、已复用证据、未验证项、完整本批时间及停止原因。主线状态同步为Gx784工程失败/AUTO库存已生成、dot新C1仍待验；只更新本任务当前导航，不改其他分支任务材料。**不再生成一套空run_index、假数值result或新的“零次训练实验”。** 本review补验成功且页面字节未变的渲染可直接按hash引用；旧V16 NOT_RUN原样保留。

### P0-B：把“可复用诊断工具”限定到准确依赖与非求解用途

当前[依赖组manifest](outcomes/records/selective_merge_manifest_v16.json)是本轮增量清单，含“existing numerical kernel”等描述，尚不能作为从master独立抽取文件的闭包。用**静态import/调用检查**补齐研究诊断入口的准确依赖路径、已有测试/源码/数据入口和建议顺序；写在本次response及一个本轮manifest中，不覆盖旧manifest，不实际迁移或合并。

至少核对`benchmarks/run_feinn_common_descent.py`、`benchmarks/check_feinn_common_descent.py`、`src/runners/feinn_common_descent_arrays.py`、`src/solvers/feinn_common_descent.py`、`src/solvers/feinn_diagnostic_algebra.py`和现有测试之间的依赖。说明runner同时含producer入口；**可读取保存数据的checker资格不等于授权运行producer或抽取整个研究优化模块**。本轮不为此重构代码、不创建第二套checker、不跑优化、不安装依赖。没有真实接收方时记`RESEARCH_ONLY_NOT_SELECTED_FOR_TRANSFER`，不以“可复用”宣传已经部署。

验收是六类依赖组完整：production numerical/core为空；runner/watchdog未改复用；checker/benchmark的依赖可定位；compact evidence/docs保留全部正负边界；训练/方向诊断为research-only；raw/venv/cache为do-not-merge。需要代码资格的地方指向已有75/143项的准确范围，不宣称新的fresh PDE。若抽取无法脱离研究运行环境，如实列出，不开展搬迁工程。

### P1：只有出现具体接收需求，才提交辅助角色准入建议

目前唯一已验证辅助角色是**研究失效诊断**：读保存的场/残差方向，区分度量冲突、参考暴露和证据缺失。它没有神经网络增益，不是生产误差估计器或解修正器。当前没有主线请求接入此工具的证据，因此默认`NOT_REQUESTED_NO_RUN`，不能为了完成任务自行创造消费者。

若主控提供确切接收接口与保存数组合同，P1只做静态可比性表和一个有界验收设计：明确原A/f/G或替代范数、场与残差单位、MPC/端口、alpha来源/标签权限、baseline、全成本。拟议对照须包含已知正向冲突、已知线性过冲、阈值/缺证据UNKNOWN及禁止读取参考标签的测试；这些小fixture在V16已具备时直接复用，不再跑同类测试。**实际接入、任何新数值见证和训练都仍需后续review的具体授权。** 若接口不相容，结论为NOT_COMPARABLE并停止此项，不复制主线场积分、传统solver或存储验证。

| 优先级 / 分配 | 时间硬限，含相关IO | 验收 / 失败后有限处理 |
| --- | --- | --- |
| P0-A 当前导航、停止交接和状态同步 | 900 s | 一份response、当前状态无冲突；缺链接只查已有索引一次，找不到列UNKNOWN，不重造历史 |
| P0-B 静态依赖闭包 | 900 s | 六类清单和准确文件/测试/用途；依赖不明写研究限制，不为凑portable重构 |
| P1 有具体需求时的静态准入设计 | 300 s；未触发为0 | 输入/对照/指标可审阅；缺需求直接NOT_REQUESTED，不等人、不启动后台监测 |
| 文档检查、必要渲染、提交推送及局部修复预留 | 1500 s | 本地结构/链接/JSON、最终git diff检查；实际渲染以本review收据的未变字节复用或只查新增页面 |
| **完整批次总上限** | **3600 s** | 准备、阅读、等待、失败、浏览器、保存和发布全计；额度不用完也结束 |

沿用`source scripts/activate_task42extra.sh pure`、CPU-only、1空闲物理核且SMT同胞空闲、数学线程1、整树2 GiB hard/1.75 GiB warn、自身swap/OOC0；系统余量max(128 GiB,effective total的10%)、邻任务增长至少384 GiB、磁盘自由≥50 GiB、artifacts总额≤20 GiB。复用监督器，不借16 GiB FE配额、不安装环境、不改其他任务进程/锁。

明确的链接、schema、局部脚本问题最多两次有依据的修补和定向重验；不因一个小错误停止全部独立交接，也不因此重跑75/143套件、旧FE、全部hash或历史页面。资源拒绝先完成静态部分；仅在有实测新空闲窗口且剩余预算足够时允许一次重新准入，之后记未验项并交付，不循环等资源。到硬限或监督失效，保存并清除自身进程树。**完成本批即暂停；不得为新的归档轮次、余下预算或“仍有未知”自动追加V18实验。**

## 6. 后续重启条件与主控优先级

重启神经数值路线必须同时提供：新的具体无标签干预；与已否定缩放/GN/缓存/缩步/背景不同的机制；已有保存数据中能区分竞争解释的正证据；同精度、同完整成本的非NN对照；固定候选数、原严格Gate、资源预算和失败停止出口。若用参考标签训练，必须另标监督辅助研究，不能改名PDE-only。若必要成本前缀已不可能满足所宣称的20%净收益，先否决，不运行完成器。

若这些条件不满足，FEINN继续暂停；辅助初值、预条件器、误差估计器或压缩器都不能仅凭名称获得新预算。历史方法全局表达能力未知，也不构成无限试参的理由。后续独立架构如有新证据，仍应由其所属分支审阅，不能把NN-V3的结果并入FEINN功劳。

对项目主控的下一轮计算优先级建议是：**先在主线自己的review闭环中解决已修复Gx784的再次准入，取得缺失的x网格精度证据；dot继续自身有持久证据前提的C1资格；FEINN执行上述轻量交接后释放数值预算。** 主线的额外正式尝试已超旧一次重放额度，本报告不代替其新授权；不因工程失败降低残差/物理门或扩大网格扫描。

## 7. 可直接转交项目主控Codex

> 在已登记worktree /home/fenics/Projects/NN-Lab-V2 的精确分支 task42extra_feinn_5nm 安全同步含 review_report_v16.md 的提交；审阅输入89d24fa253aa6d9c8109e1d8b1983d964388e826、base fbac3d8777fcfd897d93b898cb9f460f79ddd6ff。V16 checker/两方向归因已验收；保持 FEINN_MAIN_SOLVER_ON_HOLD、NO_VERIFIED_NN_INCREMENT、D0成本否决/D1未运行。只执行本review P0-A一次暂停交接和P0-B静态依赖清单，交response_v17；P1仅有确切接收需求时提交静态准入设计，默认NOT_REQUESTED_NO_RUN。不得启动新训练、producer、优化、FE/网络前向、传统完成器、全量历史复验或跨支代码迁移。旧99f2968数组分析与a14dd618检查器来源分开，原8配置/32点/4候选hash、M3600界宽UNKNOWN、较好中期与退化终态、所有失败/未运行保留；复用本review收据及未变源码测试。主线最新b8bd7c2f23726142161b58a7d7ff52275ea677ba是Gx784在FE前工程失败和AUTO32060库存，不是新精度解；dot eb5b0ecc1afe593f626b44a6038f7f26651b3317的新C1仍待实际资格。本支不改主线/dot/coarse_inverse/NN-V3，不重复solver或storage。完整批次≤3600s，pure/单空闲物理核/线程1/整树2GiB/自身swap0及原系统邻任务余量，最多两次局部修补和一次有实测新窗口的资源重新准入。原尺寸0.7nm完整三维、十进制2TB整机/172800s及原精度/20%净收益门不变。提交推送同一分支并给完整HEAD/base/tracking、工作树、证据和费用，完成后暂停，不合并master、不自动追加实验；主线再次运行Gx784须走其自己的新review授权。
