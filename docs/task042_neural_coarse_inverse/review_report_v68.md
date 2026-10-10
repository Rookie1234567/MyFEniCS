# Review V68：装配时形成四面体Schur，推进无全局K计算与接口作用

## 0. 裁决与唯一身份

**V69按pass_with_qualifications接受：C5严格复现原L5，M5取得p5的828→1188有限模式增量通过。空间准确性仍未闭合；不授同精度冷启动加速、原尺寸2TB/48h或NN收益。** 本轮不重做这些实验，批准 **V70_ASSEMBLY_TIME_TETRA_AND_TRACE_ACTION**：在相同L5空间中，直接从真实单元核形成缩减系统，不先装配、读取或恢复旧全局K；完成一份完整物理解，并验证不依赖全局Schur矩阵的接口向量作用。

要消除的blocker是当前“先形成大体矩阵，再形成缩减矩阵”的重复存储与准备，以及接口作用仍只能通过全局CSR实现。局部消元数学已经通过，不再为其另开研究。新装配不会改善旧空间误差，也不会自动解决全局LU；其价值必须由正确性、实际构建成本和后续可消费接口证明。

```text
repository             = Rookie1234567/MyFEniCS
execution_branch       = task42_neural_coarse_inverse
canonical_worktree     = /home/fenics/Projects/NN-Lab
review_date            = 2026-10-10 Asia/Singapore
reviewed_HEAD          = c776edf07417aa8238310c8e8fc065bd2560070f
latest_commit_UTC      = 2026-10-10T10:13:03Z
latest_commit_local    = 2026-10-10 18:13:03 +08:00
latest_response        = response_v69.md
previous_review        = review_report_v67.md
previous_review_commit = 0f7d19e692b49ff06557d95891a843a3803fcdd5
previous_review_blob   = d2a28a8ad0d1797fcdc06cb1a654cf4f4c010bf7
original_base          = ccd357885f7f9be84efe3be07868cc94f13d93fc
campaign               = V70_ASSEMBLY_TIME_TETRA_AND_TRACE_ACTION
required_response      = response_v70.md
ordinary_default       = UNCHANGED
NN_training_PC         = NOT_AUTHORIZED
merge                  = NOT_APPROVED
```

上版合同以已由用户选择并在V69实际执行的远端0f7d19e6为准，不重新导入此前不同正文附件。本报告只新建V68，不覆盖旧review、response、失败或身份记录。

最终目标保持：真空0.7nm，原50×25nm周期及z=-10..130nm，单胞内任意非可分三维材料/几何，complex128 Nédélec H(curl)、双Floquet和Fourier-DtN，完整复E/H、衍射、R/T/A及独立体吸收；必要构建至验收≤172800s。约2e12B是整机物理内存，须保留系统余量。本批s=7/135有限参照不是原尺寸资格。

## 1. 实际审阅与最新结果

已读取冻结HEAD的根AGENTS、docs规则、仓库原则、原task身份、现行完整review、最新response/summary、12次提交差异、实际消元/装配/求解源码及非重叠费用；任务目录未找到新的独立supplement或同名V68。核对相邻NN和工程分支最新入口。审阅端未运行工作站PDE、未重新计算大场数组；下表measured均指仓库提交的记录。

证据：[Response V69](response_v69.md)、[summary](outcomes/summary.md)、[最终费用](outcomes/records/resource_costs_final_v69.json)、[完整比较](outcomes/records/paired_results_v69.json)、[准备包](outcomes/records/exact_condensed_checkpoint_v69.json)、[保存场诊断](outcomes/records/saved_field_diagnosis_v69.json)、[原式与物理](outcomes/records/complete_physics_v69.json)。

| recorded measured | 结果 | 裁决边界 |
|---|---:|---|
| C5完整FE / retained含828模式 | 1943745 / 1177293 | 内部767280全部恢复，不是混阶或删方向 |
| C5 stored nnz / sampled峰 | 266599917 / 110.779579163GiB | 原L5为464436991 / 129.562198639GiB；不同运行采样，不授严格资源比 |
| C5/L5散射E/H | 5.02140388e-11 / 5.02105969e-11 | 同离散严格再现PASS |
| C5独立true / port | 3.35623708425e-10 / 9.80666095409e-16 | formal1e-6通过，direct1e-10失败单列 |
| C5 prepared-start部署链 | 7559.58426938s | 原L5为5955.67641464s；观察到更慢，不称加速 |
| M5 p5/1188，独立true / sampled峰 | 3.3558970894e-10 / 113.257854462GiB | formal通过，direct子门未过 |
| L5/M5散射E/H、240点、复通道 | 4.65172746e-7 / 8.58749886e-7；1.77136396e-6；4.77153202e-7 | 两端固定分母的有限模式增量PASS |
| 历史P6/L5散射E/H、240点 | 1.14449343e-4 / 1.23013215e-4；9.56041627e-4 | 仍超过原1e-4门；凝聚和模式通过不覆盖 |
| C5/M5 R/T/A_volume | 约0.0762185592 / 0.9056651611 / 0.0181162796 | 能量约4.2e-12，不作为全场精度替代 |

C5相对原L5的行数、stored nnz、采样峰变化分别约-39.46%、-42.60%、-14.50%，成功prepared-start记录约+26.93%时间；均为据记录计算的比较，不是配平fresh性能证书。C5的numeric为4320.66493785s，完整体积分输出1694.17980063s，分别约占其7559.58s部署链的57.15%和22.41%。成功凝聚形成及保存402.621184918s，不能与其父计时重复相加。原体K准备12095.1191837s和两次未完成准备3167.24882335/671.32188583s仍收费。

240点确为实际网格顶点；8方向辅助评价和约77.8%差平方在材料邻域两层之外的结果保留。不能据此删除旧点、改分母、只报远场或宣称空间误差已解决；也不再原样重复区域诊断。p5模式增量已小，不再追加模式库存。

## 2. 本轮范围：一份完整解，加一份全局S无关的作用资格

| 阶段 | 实际工作 | 必须产出 |
|---|---|---|
| Q | 新单元核、DG0材料、方向、MPC和非互伴消元的最小资格 | 至多8个预登记真实cell的原作用配对；不新解旧PDE |
| BUILD | 从单元核直接累加全部p5接口及828模式的S和rhs | 新S、局部响应/恢复packet、完整身份；生产full-K读取/构造均0 |
| ACTION | 独立进程只用新局部packet与边界，完成2个接口作用 | 与BUILD保存的2个S作用向量配对；该进程global-K/S读取及factor均0 |
| SOLVE | 用新S完成一次物理零初值有限直接解并恢复原L5全场 | 完整原方程、六场、240点、828模式、体吸收、必要费用 |
| VERIFY | 冻结后与保存C5严格同离散比较，结算全部阶段 | 准确性/资源/作用能力分开裁决；唯一下一pilot |

只做同一25576tet/p5/828问题，不改变空间/材料/几何；不重跑L5、C5、M5或P6控制，不重做15表、旧q资格、慢oracle、240点诊断、模式或载波扫描。本批仍可物化最终S供有限LU，但不得称整个求解器matrix-free。ACTION通过只授串行、局部数据驱动、无全局S的作用资格，不授新PC、迭代收敛或分布式生产资格。

## 3. 窄实现路径及已查明的风险

### 3.1 正确复用，不能把旧hex入口改个单元名

[原体形式](../../src/solvers/independent_tetra_reference.py)使用DG0函数epsilon及完整Ckappa，生产体求积q13。[旧assembly-time模块](../../src/solvers/hcurl_assembly_time_condensation.py)限制轴对齐hex；其_tabulate_cell_tensor向系数和常量参数传NULL，不能直接用于当前DG0形式，_canonical_axis_aligned_coordinates也不能用于tetra。

复用可通用的_orient_cell_tensor、局部约束/预分配思想和V69恢复协议；新增显式opt-in tetra单元provider，使用真实4×3坐标、单元方向及实际材料。分离“构造UFL form”和“全局assemble_matrix”，生产provider只编译/调用单元核，不调用原完整K装配器。

首选按实际Form的积分域/系数偏移打包DG0和constants，通过当前已资格ABI调用tabulate_tensor_complex128；积分条目、cell、系数行须精确对应。不得以空指针、第一cell材料或旧tag顺序替代。参考[DOLFINx 0.10局部凝聚示例](https://docs.fenicsproject.org/dolfinx/v0.10.0/python/demos/demo_static-condensation.html)和[pack_coefficients/pack_constants](https://docs.fenicsproject.org/dolfinx/v0.10.0/python/_modules/dolfinx/fem/assemble.html)，示例是接口依据而非本Maxwell资格。

若运行时系数桥接成为障碍，允许等价后备：对本批每个实际常材料值编译相同Ckappa弱式的常量核，按真实cell tag调用；这是DG0常材料的等价实现，不推广到单元内变系数。两种实现均须与独立Basix作用配对。用现有CFFI/可用JIT栈，不升级ABI或安装新的系统依赖，不另造通用编译器。

方向变换遵守当前DOLFINx的局部基约定；复数MPC使用共轭拉回。几何用真实仿射J而非包围盒宽度。缓存只能按精确核输入、材料、p、kappa、求积和方向身份；不得round合类。仅在证明确切适用并完成真实配对后可利用平移不变性，源项/相位边界不得沿用体核平移缓存。不能拿全局K的cell×cell子矩阵当作未装配的完整单元矩阵，因为共享trace块含邻单元贡献。

### 3.2 一次累加的完整数学

令E_e把独立全局trace映射到单元局部trace；K_e已经施加正确DOF方向，分为i/t，i为本单元30个内部，t为110个边/面。C_i,e和D_i,e从该单元唯一内部的实际边界支撑取得。C_t、D_t、H和全局f_t只插入一次，不在每个cell重复。

```math
S_{tt}=\sum_e E_e^*\left(K_{tt,e}-K_{ti,e}K_{ii,e}^{-1}K_{it,e}\right)E_e,
\qquad \widetilde C=C_t-\sum_e E_e^*K_{ti,e}K_{ii,e}^{-1}C_{i,e}.
```

```math
\widetilde D=D_t-\sum_e D_{i,e}K_{ii,e}^{-1}K_{it,e}E_e,
\qquad \widetilde H=H+\sum_e D_{i,e}K_{ii,e}^{-1}C_{i,e}.
```

```math
S=\begin{bmatrix}S_{tt}&\widetilde C\\-\widetilde D&\widetilde H\end{bmatrix},
\quad b_S=\begin{bmatrix}f_t-\sum_e E_e^*K_{ti,e}K_{ii,e}^{-1}f_{i,e}\\g+\sum_e D_{i,e}K_{ii,e}^{-1}f_{i,e}\end{bmatrix},
\quad u_{i,e}=K_{ii,e}^{-1}(f_{i,e}-K_{it,e}E_eu_t-C_{i,e}a).
```

Kti不能由Kit共轭猜造，C/D不假设互伴；所有实际非零内部端口项保留，不能以理论零为由drop。f_i和g非零由小型回归覆盖；当前真实边界RHS沿原定义，不重新制造。内部DOF必须唯一owned且在P中为单位映射，trace经P只作用一次。原p5空间一个方向也不删。

全球图由真实cell trace闭包和port支撑得到，复用已有稀疏构造而非新写通用CSR框架；不使用旧full-A图的多份副本。直接ADD_VALUES贯穿或在INSERT/ADD切换时用FLUSH，只有最终完整结构使用FINAL；V69修复已经通过，不重复踩预留槽压缩问题，见[PETSc装配语义](https://petsc.org/release/manualpages/Mat/MatAssemblyBegin/)。不得为获得更少nnz删除数值小项；存储的显式零和实际非零分列。

按单元/精确类流式形成局部30阶LU及恢复数据；不保存全体140×140 raw数组到RAM，不形成全球内部逆。默认局部chunk≤64cell，端口列块≤32；exact cache≤4GiB、额外临时workspace≤2GiB，均计入role总内存。新packet可保存局部Schur或其生成因子，但须列payload、共享数和缓存未命中；原K、旧S或旧恢复packet不能成为生产数据源。

### 3.3 必须在旧runner的full-K构造之前分流

[independent_tetra_study.solve](../../src/solvers/independent_tetra_study.py)现在先解包K，再sparse.bmat构造A，随后才调用system_adapter。仅更换system_adapter不能实现无全局K。

增加早分流的显式retained_provider或等价strategy，复用同一求解/恢复/保存/后处理尾部。新provider提供S、full_rhs、完整FE维数、边界、form身份和恢复服务；完整FE维数从P取得，不从S.shape猜。旧full路径和普通默认不变，不复制整个runner。production计数必须证明full_body_assemble_matrix=0、old_full_K_reads=0、full_A_materializations=0、old_condensed_packet_reads=0。mesh/P、完整向量、边界本身仍有O(N)成本，不能谎称全部空间存储消失。

## 4. 最小资格、完整运行与精度门

Q只做：一个复数非Hermitian、fi/g/Ci/Di均非零的小块消元；至多8个事前按材料/方向/几何选定的真实tet，用新核随机向量作用与独立Basix q15积分比较≤1e-10；完整分区/MPC复对偶/材料哈希核对。至少覆盖air、Si及周期相邻cell，NOTCH只按真实标签。旧数学同字节资格直接复用；不跑全库pytest、旧FLAT或24cell整套。若因几何矩阵近退化导致真实局部块不可信，不shift或伪逆，先定位；不得静默改变分区，旧≤128cell异常保留机制只有其完整资格已复用时才可用并明确行数。

BUILD从物理输入新构造同q47/q63边界各一次，生产p5体核q13，形成新S及任意RHS恢复packet；保存原子COMMIT和成员hash。允许一个单独compare-only消费者读取V69的S，先保存两个固定复向量作用参考，再释放；该读取不得发生在新生产构建或影响缓存、RHS、分区、初值。旧完整K不必读取。

新S与V69 S在对齐i/t/port身份后的2个固定向量作用差≤1e-10，FE/port分块的原运算尺度也检查，不能让大倏逝坐标掩盖FE差。用一个非零内部/端口RHS恢复完整向量，验证原PUBLIC_BASIX(q15体、q63边界)的残差与提升后的凝聚残差一致≤1e-10。原独立核不读取新单元raw或新S来自证。此项通过后立即进入完整求解，不在微基准/代码commit处停等review。

ACTION在独立进程中只读新局部packet和新边界，按同一消元式逐cell gather/apply/scatter-add。禁止读取任何全球K或S，禁止在内部隐藏sparse.bmat或创建全球FE矩阵；可存局部小矩阵、LU及稀疏边界。计算上述两个z的S作用，与保存参考比≤1e-10，记录冷读/第二作用时间、字节、缓存及全部实际调用。ACTION新增2次作用，不另做迭代/谱扫描；接口接线失败只隔离ACTION，BUILD原式已可信时SOLVE仍继续。该核用来交付下一步trace迭代的原算子，不冒称本批已经有可扩展PC。

SOLVE使用新S、原MUMPS和端口等价坐标，物理零初值，最多两次既有精化；不扫ordering/shift/BLR/OOC/ILU。完成既有精化和retained true residual后，先保存retained解、full RHS及最小恢复packet，销毁因子、无用矩阵和旧拥有者并确认RSS下降，再完整恢复1943745个FE及828端口、进行独立原方程审核和输出。未完成恢复不得称全场返回，formal资格只由完整原式裁决；不得因后处理失败再建factor。

| Gate | 原限值/含义 |
|---|---|
| 新完整true/native/augmented/port | 各≤1e-6；独立direct1e-10单列，不用生产残差覆盖 |
| MPC、内部恢复、切向E/操作恒等式 | ≤1e-10，复用原验收定义 |
| 新解/C5同离散六场、原240点、物理参考面复通道 | ≤1e-6；R/T/A/A_volume差≤1e-8；逐mode功率差≤1e-9 |
| 每份完整场的独立能量闭合 | ≤1e-5；体吸收不由1-R-T代替 |
| 历史空间与模式标准 | 六场/240点/复通道1e-4、功率1e-6、能量1e-5不改 |

同基/几何/DOF一致才沿V69先减系数、再评价差场，避免近等大场抵消；独立差场q配对原2e-6门保持。raw倏逝辅助坐标和物理参考面复振幅分列，不校幅相、不改floor、不删点。新解严格复现只授同离散资格，旧P6/L5的全域和240点FAIL必须仍保留。

## 5. 成本、资源和持续执行

本批一个计划global numeric/完整求解；第二次仅用于已定位并修复、且没有合法返回的故障。不得用旧full-K求解作为“后备”重复一份已知解。内核桥受阻优先第3.1节等价常材料后备；稀疏接线受阻使用当前已资格插入方式，不开发新框架。BUILD已完成但solve资源不准入时，仍完成ACTION及有效构建交付；准确标NOT_RUN而非全场PASS。

新12h总研发窗、科学有载≤10h、最后1h收尾；实现/读库/失败/修复/等待/IO均计费。实现目标2h，资格与引用核对不超过必要范围；每次numeric前按最新实测factor约4321s建立有不确定性余量的forecast，再留至少3600s验收/输出和总收尾。不是把SOLVE仅按三角求解98s预算。旧窗口不刷新，第二次尝试和补消费共用本批剩余。

默认无factor资格/消费64/80/96GiB，BUILD/SOLVE上限仍256/320/384GiB，分别为规划/警戒/采样停止；retained行≤1300000，完整场载体不得误套该行门。不是占用预测或目标准入票。numeric必须live树RSS+2×可靠symbolic decimalMB+2GiB≤256GiB，负编码fill保持unknown，不能由旧S相同行数免检。数学/ABI保持complex128/int64、MPI1、CPU/math1、GPU/Loader0、ownswap/OOC0；原PSI/cgroup/宿主/384GiB邻增长/空闲物理核避忙SMT与heavy锁条件不放宽。一个自身heavy actor和一个global factor，不改邻任务或系统策略。

新ignored≤40GiB、Task去重≤600GiB、free≥50GiB并留512MiB证据余量，前置核算atomic双份、局部packet和完整输出；不复制旧K/S、删除负结果或压缩掉必需场。预算先算实际对象和别名，再分配。临时full-sized向量不等于full-K，但必须入账。

完整成本从新case第一次必要数值构建到全部原式、恢复、六场/240点/模式/体吸收、IO及清场；编译/核调用/局部LU/图/累加/封存/边界/因子/输出分项且不重复父子计时。OS/JIT状态如实记录。重启prepared-start另列，不冒称fresh；历史K→S路线的必要父PREPARE和失败继续收费，不能拿本轮完整成本与旧“已准备好K”的5955s直接授加速比。

原核计算和局部LU仍需完成，不能承诺跳过global K就自动省掉全部12095s。若新方案只减少生产对象而总时间/RSS未改善，明确判无已验证速度收益；但可接受合法的无full-K路径和ACTION接口。成功不预设20%或倍数，不以没有预先速度证书阻止唯一完整实验。

## 6. 普通bug、证据和分支边界

普通API、dtype、coefficients、方向、schema、writer错误同轮最小修复并做受影响回归；不按bug数量停工。同根因两次无效后换已授权等价实现或隔离该组件，不第三次盲跑。累计故障修复含重放≤2h并服从总窗。原式/ABI/身份/监督真不可信先隔离依赖；科学差异不是bug，不改物理、精度或参考来救成功。

新局部packet/累加进度按批落盘，确认数学身份没变才续用；防止重复累加必须有已提交范围/原子manifest。返回完整向量立即保存，JSON、后处理或文档错误只补消费，不重factor。V69的FLUSH修复、同基差场和持久停止事件直接复用，不为历史未知发信者再开取证。复用有限精确hash，不扫描所有历史数组或重建全仓索引；新增数学targeted tests、相关Ruff/compile、dat validate及一次紧凑文档检查即可。视觉不可取得如实NOT_VERIFIED，不重跑PDE。

已核对相邻路线：task42extra_feinn_5nm@4ed149dd709419f00bad01e6e5dea7079fa61d81最新V40为FTT容量判别；V39映射成本改善但M5完整门仍FAIL，没有神经生产收益。task40extra_0p7nm_engineering@32a7293233985083ae5024b275b39fbdc7c56ab2最新V22为原尺寸模式support/action前缀与有限B/D packet；尚无全目标FE/MPC/KSP/场。dot@15713d3e09b63f65511c7b7f61fa043fdb23dca5只读，不复刻其原尺寸边界研究。NN-V3 ref未变化不等于本机无工作。本报告不授权邻分支集成、训练、PC或通知。

## 7. 入口、提交与必须交付

所有新数值核心进src，原runner只加显式strategy/provider，不复制大型task专用求解器。先实现与定点测试、提交clean数学source，再validate/run；修复另提交，不amend。阶段使用本分支标准one-run入口，以下尚待Codex实际创建：

```bash
python scripts/run_case.py input/task042_neural_coarse_inverse/v70_cell_kernel_preflight.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v70_assembly_time_p5_prepare.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v70_trace_action_no_global_s.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v70_assembly_time_p5_solve.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v70_compare_verify_cost.dat
```

Q/BUILD/ACTION/VERIFY不暗藏global numeric。ACTION失败不自动取消已独立资格的SOLVE；完整数学Gate失败则不可继续依赖求解。每个dat绑定input_original、resolved、manifest、input/physical/source哈希、实际环境/MPI/资源和artifact身份，不伪造旧prepared母项以通过schema。

一次交付response_v70.md、outcomes/assembly_time_tetra_trace_action_v70.md及紧凑records：新局部核和系数语义、完整无K构建、S/恢复packet、ACTION配对及无S证明、完整解/C5再现、实际nnz/fill/峰/gap/全部费用、失败/修复与唯一下一pilot。更新retained_operator_contract_v70.json，明确apply_trace、condense_rhs、recover、原/缩减空间及未实现的distributed/PC能力。

主线推进条件：如果无K构建、完整再现与ACTION均通过，下一最小工作应转到这一准确离散系统的有界trace迭代/分布式数据验证，不再无依据扩大全局direct；需要新的明确PC方案和预算，不能自动启动。若ACTION瓶颈或构建成本不合格，报告实测的具体耗时/字节项，禁止用旧行数收益掩盖。连续精度缺口独立保留，不能由同离散工程资格覆盖。

旧task/review/response/raw不改，summary/README/两总账追加清楚入口。只推送git push origin HEAD:refs/heads/task42_neural_coarse_inverse；核对实际remote完整SHA、upstream/clean、closed/active null、后代清场和锁释放后交付用户暂停。不merge、不改master/邻支、不自动开新窗口。
