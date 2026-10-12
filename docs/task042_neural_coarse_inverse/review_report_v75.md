# Review V75：关闭组合微调，只检验真实子域阻抗传输能否超过Jacobi

## 0. 裁决与本轮唯一任务

**V76取得了有用的否决证据，但没有可用物理解或同精度性能收益。Jacobi在32步将原残差降至0.388827，续至64步为0.341714；昂贵三方向SMR在64步为0.360077。关闭原主子块RAS上的固定和、平衡、harmonic粗基及SMR组合微调。本轮不补这些尾部，不新建粗空间。仅批准一个真正改变局部问题的候选：在原38个重叠单元区域内重建Maxwell局部矩阵，并在区域边界施加固定物理阻抗，以原精确全域方程检验其效果。**

本轮消除的blocker是：当前预条件器的局部逆只是全域接口体矩阵的主子块，没有实际子域出射边界；此前改变粗基和修正权重，始终没有检验这一局部传播机制。**边界反射是可检验假设，不是已证明的唯一根因；第一阶阻抗也不是精确DtN，不能保证本题收敛。** 本批以早期原残差和完整成本决定继续，不用方法名称、局部LU成功或较低RSS作为成功。

```text
repository             = Rookie1234567/MyFEniCS
execution_branch       = task42_neural_coarse_inverse
canonical_worktree     = /home/fenics/Projects/NN-Lab
original_base_SHA      = ccd357885f7f9be84efe3be07868cc94f13d93fc
reviewed_result_HEAD   = 7af6cec9ae28634dd60e9af989018db513e19443
result_time_UTC        = 2026-10-12T05:17:36Z
result_time_local      = 2026-10-12 13:17:36 +08:00
previous_review        = review_report_v74.md
previous_review_commit = 3f40d40f55c798f55d07c413a6492241db59a6ad
reviewed_response      = response_v76.md
campaign               = V77_PHYSICAL_IMPEDANCE_PATCH_PILOT
required_response      = response_v77.md
ordinary_default       = UNCHANGED
NN_training            = NOT_AUTHORIZED
merge                  = NOT_APPROVED
```

最终目标不变：原50×25nm周期、z=-10..130nm、真空0.7nm、任意非可分三维材料/几何、complex128 Nedelec H(curl)、双Floquet/Fourier-DtN、完整复E/H及物理输出；整机十进制2e12B留系统余量、ownswap/OOC=0，必要构建到验收≤172800s。当前s=7/135、MPI1有限试验不是原尺寸资格。本报告仅覆盖旧合同禁止本批开发阻抗PC的阶段限制；不改变细层物理、历史精度FAIL或安全门。

## 1. 已审证据与成本判断

本次读取最新ref/commit、V76完整response及残差记录、summary当前段、上次review后的5提交变更、局部矩阵形成、controlled runner和原FGMRES接线，以及既有阻抗模块。完整阅读本会话挂载的V74报告；根规则回读，未变task/仓库原则/docs规则与此前已读全文衔接。增量未添加补充任务书或V75 review。没有声称逐行重审全仓、SSH检查实时工作站或在审阅端复算大场/PDE。

证据：[R1](response_v76.md)、[R2](outcomes/records/residual_history_v76.json)、[R3](outcomes/summary.md)、[R4](../../src/solvers/bounded_trace_pc.py)、[R5](../../src/solvers/controlled_trace_study.py)、[R6](../../src/solvers/physical_retained_fgmres.py)。表中measured指执行机记录，非审阅端测量。

| 同题同尺度；原残差优先 | 步数 | 原true | scaled retained true | recorded wrapper秒 |
|---|---:|---:|---:|---:|
| 无PC B0 | 32 | 1.93460766967 | 0.376872295207 | 520.729 |
| 复Jacobi BJ | 32 | 0.388826586390 | 0.379105019552 | 526.966 |
| Jacobi续算 | 累计64 | 0.341713600189 | 0.339415221770 | 另546.174 |
| 三方向SMR | 64 | 0.360076582954 | 0.147596138687 | 2401.451 |

Jacobi的64步由32步checkpoint启动新KSP，旧Arnoldi基未保留，不是连续64步公平计时。不能据这两点证明Jacobi已渐近停滞；但它没有达到本项目64步0.1投入门，不批准无界续跑。SMR的scaled residual较小，原true却更差；不改变尺度或改验收分母以救结果。

SMR首次作用的最小残差保护实际成立，首次scaled残差约0.419787；这关闭了“固定求和丢掉有效方向”的有限实现疑问，却没有产生强逆。SMR64成本高于Jacobi累计64且原残差更差，因此没有继续同组合的依据。V76新KSP4次/160步，SMR才创建39个numeric；采样峰41.453972GiB、ownswap0均属于失败尝试，不授低内存有效解资格。

最新结算的不重叠命令下界5442.469387s、研究总窗8191.785677s分别报告，不相加；不采用较早5249s快照。完整系数与独立原式已保存，昂贵坏场体积分按原政策未运行，这个止损成果保留。没有因为writer重跑PDE；主要问题已不是普通bug。

## 2. 为什么此次必须改变局部矩阵，而非再调组合

当前local_principal显式遍历所有细单元，包括halo以外的单元，只按选中全局行取主子块。它正确实现的是代数限制，并没有实现实际子域上的出射弱边界。新方案不得写成“在旧CSR上加一个对角或表面项”就称ORAS；这样保留了域外单元贡献，不是本文定义的问题。[R4]

ORAS方法族使用物理子域方程加阻抗边界作为局部逆；其目的在于让波动修正能够通过人工切口，而不是仅采用零外部系数的限制。[T1] 但本批仍用原二值core写回、固定p2粗空间，不等同于文献中所有加权/谱粗空间版本，不引用波数无关收敛结论。[T2]

仓库已有fullspace_slab_interface.py和fullspace_second_order_impedance.py，包含切向面弱作用及-i*k0*n系数。它们针对水平两slab等旧问题，不能直接用于当前任意三角面，也不能用旧通过标签代替新资格。复用其已知符号/数学约定与通用几何工具，不复跑旧两slab任务，不引入FreeFEM或另一套FE软件。

## 3. 冻结细层、几何分区和唯一PC

细层、物理RHS、原左/右尺度、q47生产边界及q63独立边界完全不变。生产继续只读V70精确local_packet；不得读取/形成global fine K/S或fine LU。保留全部1,943,745个FE未知量、1,176,465个retained FE和828端口。V70正确场只能在候选冻结后用于最终评分，不进入初值、PC或选区。

```text
mesh_sha256     = c470274ab6c64cee0b8eef09dbcdadadfac4c6ca229d7fc2b6e608ded62f540c
material_sha256 = 55aa34e55c5e3cc35f6849eddbd3bcc72d3b694d32bc4885299ef373acd676a2
physical_sha256 = df26b8cf28e1115bdb2eb9ac9b79e698596133305310d26c1d664f94e2c5be44
packet_sha256   = 9bef5add6398999c70c21c7f26a86833fc1eb46f98598c8503aa3c41743728da
Z0_sha256       = 536758160a20d38c5fc87781a192fd853d6f387164774181c12595d0daa3880e
```

25576tet、p5、1000个NOTCH tet，kappa=(8.94046081729244,0.7821889682108057,0)，grazing1度/azimuth5度/s。Si n=0.999885140474+4.32477054e-6i、epsilon=n*n、mu=1；空气沿原descriptor。未知数、波长、材料、参考面、模式键和输出规则不变。

复用V71保存的38个core/halo_cells/ids，不重新划分、不加重叠、不增加块。每块行数沿80000硬门；core写回唯一owner保持。读取halo_cells而非凭包围盒重建区域。复用原Z0/E0（6240+828=7068，硬上限8192）和原Galerkin资格；不使用harmonic基，不重建粗Galerkin。

唯一候选为固定coarse-first：

```math
C_0=Z_0E_0^{-1}Z_0^H,
\qquad B_{\rm imp}=\sum_j R_{j,\rm core}^{T}B_j^{-1}R_j,
\qquad M^{-1}r=C_0r+B_{\rm imp}(r-\widehat A C_0r).
```

这里R_core表示解出局部向量后只累加原core行，端口不在局部FE矩阵中；原粗修正与精确外层作用仍处理全部828端口。只改变B_j的定义，不加SMR权重、不加balanced末尾反馈，不改正交化、norm、restart或残差权重。固定低维粗空间仍可能不足，这是风险而非隐藏假设。

## 4. 子域上的具体数学，防止“假阻抗”

令Omega_j为保存halo_cells的单元并集，在x/y周期商空间上识别相邻面。两侧单元均属于Omega_j的面是内部面；只有一侧属于的面是人工外面。物理z外边界另标。材料界面两侧都在域内时不加吸收。周期配对先处理，再判断人工边界，不能把每个x/y周期接缝都当成吸收面。

本批局部PC在人工外面及其接触的物理z外面统一使用一阶局部阻抗近似；这是PC边界，不是替换真实模型的Fourier-DtN。全域A/RHS和最终q63审核仍保持原完整828模式。

```math
C_\kappa u=\nabla\times u+i\kappa\times u,
\qquad u_t=(I-nn^T)u,
\qquad \zeta_f=\sqrt{\epsilon_{r,f}/\mu_{r,f}},
```

```math
a_j(u,v)=\sum_{K\subset\Omega_j}\int_K
\mu_r^{-1}C_\kappa u\cdot\overline{C_\kappa v}
-k_0^2\epsilon_r u\cdot\overline v\,dx
-i k_0\sum_{f\subset\partial\Omega_j}\int_f
\zeta_f u_t\cdot\overline{v_t}\,ds.
```

zeta取域内相邻单元材料的被动分支，当前mu=1所以等于相应n。时间约定与现有-i*k0*n核一致，先用外传法向平面波检查Green边界符号；不扫描正负号、倍数或复shift。Pt使用每个真实三角面的单位法向，不固定成Ex/Ey；真实3x3仿射J、Piola、方向变换、实体闭包、面积权重及MPC共轭拉回各一次。实kappa使相位在切向质量内积中抵消，不省略体内Ckappa项。

在精确切向迹中，cell内部bubble的迹为零，故可沿原内部LU先消元：

```math
B_j=\sum_{K\subset\Omega_j}E_{Kj}^{H}S_K E_{Kj}
-i k_0\sum_{f\subset\partial\Omega_j}E_{fj}^{H}M_{t,f}^{\zeta}E_{fj}.
```

**第一项只能累加halo_cells中的单元，不能调用原local_principal后加面项。** 面质量以真实迹矩定义，不是trace系数对角阻尼。理论结构零通过实体支撑与实际trace见证确认；不得按幅值删项来满足图/内存门。若实际basis接口产生不能忽略的内部边界项，则对受影响边界cell的完整raw加入所有Robin项后再局部消元，有限定点回归后继续；不能漏项，也不修改原全域packet。原cell raw可从已保存局部块关系复原或调用已有正确单元核，只重建受影响cell，禁止重装全域K。

新local矩阵是PC代理，不是原全域方程的精确主子块；因此不要求它等于旧patch CSR。必须保存这种数学身份差异，旧CSR不能冒充新对象缓存。对角、边面及非互伴体耦合保持完整；没有证据预报新factor一定更小、更快。

## 5. 执行顺序：必要资格后直接进入实际残差试验

PREFLIGHT：核对旧资产、边界分类和固定PC配置。只补非Hermitian块消元、任意朝向面Gram/出射符号、周期面的内部/人工分类、未来版本计数和效果门接线。选择最大原patch与含材料界面的最小ID patch（重复则下一ID）作两份实际局部作用验证：给固定向量，利用原局部恢复后由PUBLIC_BASIX独立体作用加直接面求积，核对局部矩阵作用≤1e-10。q13/q15面求积配对；不把旧水平slab测试当成新三角面资格。

PREPARE：上述两块属于正式38块，合格后直接保存留用，不销毁重做。其余块逐块形成、原子保存、symbolic并收费；数学不变的中断只补缺块。E0只读复用但其本进程numeric仍重新计费。不得在PREPARE装载完整正确场或执行隐藏的全域求解。

ITERATE：复用controlled_trace_study的效果门、physical_retained_fgmres和原恢复/输出；新增显式pc_factory/strategy与数据接口，不复制大型runner，也不把新role送入旧SMR/harmonic字符串分支。一个正式RIGHT FGMRES，restart128/max256、retained零初值；初始内部特解照原方程恢复。初次末态与每个效果点用独立原方程判定。

无需重跑B0/BJ或再做64步Jacobi：现有32步是独立零初值对照，足以作本轮准入标杆。历史64步续算语义保留，不授严格配平性能比。正常主路线不得拆成每32步新KSP，以免无意丢失Arnoldi方向。当前effect_check已可在一个KSP内判定，不用再次开发调度系统。[R5/R6]

## 6. 成本门与最终验收

令rho=max(独立未凝聚原true, scaled retained true)，均用原RHS分母。固定原方程norm不变，不能只优化较小的scaled residual。

| 实际累计步 | 继续投入的门 | 不满足时 |
|---|---|---|
| 32 | rho<=0.30 | 保存并停止；必须明显超过已测Jacobi32的0.388827 |
| 64 | rho<=0.10 | 停止该固定候选，不补尾部 |
| 128 | rho<=1e-3 | 同上 |
| 至多256 | 原最终联合门 | 无自动扩容、改阻抗或加步 |

上述是本项目成本决策阈值，不是数学不可能性结论。记录达到同一原残差的时间与作用数；新PC的全部局部组装、面积分及factor必须计入，不能只报KSP部分。若门不满足，即使局部方程全通过也判EFFECTIVENESS_FAIL。

正式成功：retained true<=1e-11，独立原true/native/augmented/port各<=1e-6，MPC/恢复/Schur-original<=1e-10，direct1e-10子目标单列。联合通过才读取V70作严格同离散评分：六场/原240点/物理复通道<=1e-6，R/T/A/A_volume差<=1e-8，逐mode功率差<=1e-9，独立能量<=1e-5。同一分子两固定分母，不校幅相、不投影、不删点/模式。

失败原残差>1e-2时只保存完整retained/尺度/RHS/source、完整恢复系数和独立原式向量，不支付昂贵六场积分、衍射评分和图表；official=False，NOT_RUN_BY_FAIL_FAST_POLICY。<=1e-2但未通过时，预算足最多补一份诊断，不能称可用物理解。合法候选返回后释放KSP/39因子/无用矩阵、记录RSS下降，再输出；writer/JSON错误只补消费。

历史P6/L5空间增量E/H约1.14e-4/1.23e-4、240点约9.56e-4仍FAIL。严格再现只授同离散求解资格，不授连续精度、原尺寸或2TB48h。

## 7. 资源、停止与普通bug的继续边界

新总窗6h，从第一项实际工作计时；新数学接线/局部准备目标2h但不是独立硬断点，统一按总余量与实测forecast分配。允许KSP累计至多2h、全批fine action至多800（含PC内部与独立作用），所有层显式传入，不能遗留600门。新numeric前保留实际factor上界、首个效果段及4500s可能成功的完整验收余量；最后1800s收口。没有效果不消耗剩余时间再开一个方案。

默认64/80/96GiB；PREPARE/ITERATE最高96/112/128GiB，因子双倍symbolic总门80GiB。新B_j必须重新symbolic，不继承旧主子块的74.8GiB估计。逐factor要求live RSS+尚未分解因子双倍估计+future<=96GiB，future>=12GiB且逐项覆盖257条主Krylov库、原式/恢复与工作区。只读当前CSR，释放输入后持有其因子，不同时加载38个CSR。旧E0之外不得增加global coarse factor或fine factor。

各patch<=80000行，patch_count=38、coarse_rows=7068；实际数学不符先记录原因，不通过重分区或裁剪绕门。局部新facet缓存总<=2GiB，临时workspace<=2GiB，计入总预算。新ignored<=24GiB，Task总<=696GiB、free>=50GiB；旧结果不删除，解与原子写出空间事前核算。

原qualified activation、complex128/int64、MPI1/math1/CPU1/GPU0、ownswap/OOC0、PSI/cgroup/宿主/384GiB邻增长/物理核-SMT/heavy锁保护保持。工作站新角色的实际ABI须现场核对，不照搬工程分支int32/runtime或其拟议资源许可。共享硬件繁忙不操作邻任务。

正常一个KSP.solve；确诊实现错误且无合法终态，可一次本批retained续算，累计步数/作用/时钟不重置。正常门停止或科学停滞不能借此重开。普通API/shape/路径/collector错误同窗最小修复，修复累计<=1h；同根因两次无效换等价正确实现或隔离，不盲重播长前缀。纯面核可回退原正确逐facet积分，不要求为了批乘优化重新准备整批。真实原式、材料、ABI、身份或监督不可信仍先停止依赖工作。

不full pytest/CI、不全仓或历史hash扫描、不重跑FLAT/Q0/15表/慢oracle/旧PC。新core数学进src/solvers；benchmark只作薄调用/消费。一次紧凑文档检查，两总账各追加一个有结论的短条目。

## 8. 正式入口、commit与分支分工

待创建入口，必须实现、targeted回归、commit clean、dat validate后才运行：

```bash
python scripts/run_case.py input/task042_neural_coarse_inverse/v77_impedance_patch_preflight.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v77_impedance_patch_prepare.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v77_impedance_trace_solve.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v77_verify_cost.dat
```

PRECHECK/VERIFY不得暗藏numeric或PDE；PREPARE仅形成局部/粗symbolic，正式39个numeric在唯一ITERATE进程中建立，不为了预检建立再销毁全部因子。局部正确性用作用验证，不需要提前重复factor。

commit计划：C1局部体/面形成及显式strategy、效果门与最小回归；C2同题实际执行与紧凑记录；C3response、summary与两总账。活跃计算期间不改其tracked source/HEAD。仅push origin HEAD:refs/heads/task42_neural_coarse_inverse，不merge、不改master/邻支、不自动V78。

交付response_v77.md、outcomes/physical_impedance_patch_v77.md及紧凑records：区域/边界数学身份、域外贡献确实不进入局部B_j、q13/q15与原式作用、38个新CSR/factor成本、每步/效果门/原残差、保存终态、实际峰/gap/swap、是否达到完整场与唯一下一决策。原factor输入对照证明不是旧主子块简单加质量项，不为证明而重读所有旧大CSR。不能只交测试通过数。

工程线截至5bb1040ac0e18041cf4f0d055e02ab7070d18453的V29：已完成strict factor-only接线，但目标service/factor未启动，仍等待其资源/依赖/runtime授权。其q0规则参考逆属于独立原尺寸路线，本轮不复制或授权其操作。NN分支task42extra_feinn_5nm回读HEAD5a48c802486875ac628e6e710b5caf240769248b，本次不重审其训练结果、不派任务。dot同样只读隔离。[R7]

若本候选在原残差门失败，关闭这一具体固定阻抗配置，不扩成阻抗系数、粗阶数或restart扫描；不宣布所有DD/NN不可行。后续需要独立的新证据才能投资新的波动粗空间或传播机制。若完整通过，先报告包括新局部准备的单场成本，再做packet-only冷构建和一个中间尺度/MPI试验的容量提案；本批不运行原尺寸。不把6h研究窗口、低RSS或局部absorbing边界名称当作2TB48h成功。

## 9. 依据与审阅边界

[T1] [FreeFEM官方DD说明，RAS/ORAS定义](https://doc.freefem.org/documentation/ffddm/introduction-to-the-domain-decomposition-method.html)：局部主子块与物理子域阻抗矩阵的区别。本批不安装FreeFEM，也不将其示例成功外推本题。

[T2] Bonazzoli等，[高频Maxwell吸收问题的DD预条件原始论文](https://arxiv.org/abs/1711.03789)：局部/粗空间和参数条件不可省略；本批弱损耗Floquet/DtN不直接继承其理论保证。

[R7] [工程V29回应](https://github.com/Rookie1234567/MyFEniCS/blob/5bb1040ac0e18041cf4f0d055e02ab7070d18453/docs/task40extra_0p7nm_engineering/response_v29.md)按邻分支不可变SHA引用，不要求本分支存在同名文件。既有阻抗代码：[水平界面](../../src/solvers/fullspace_slab_interface.py)、[二阶Taylor历史核](../../src/solvers/fullspace_second_order_impedance.py)。

审阅端只核对远程代码/记录、局部复数消元恒等式、文档和字节身份，没有运行真实新PC、PDE或收敛实验。GitHub视觉无法取得时记NOT_VERIFIED，不为渲染或历史计时补齐重跑PDE。
