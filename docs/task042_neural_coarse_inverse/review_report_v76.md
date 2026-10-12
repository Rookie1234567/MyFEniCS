# Review V76：关闭无收益重型PC，补齐一次未被提前重启的廉价求解证据

## 0. 裁决与责任

**V77执行完成、数值失败。原残差0.917996，明显劣于Jacobi32步的0.388827，局部矩阵和39个因子通过并不是求解收益。不批准阻抗系数、粗空间、RAS组合、harmonic、SMR或restart扫描。** 此前ChatGPT先后把局部数学正确性当作值得开展完整试验的主要理由，却没有先检验一阶阻抗对本题掠入射的适用性，也没有给表现最好的廉价基线一次完整且未被人为切断的搜索周期，投入顺序不合理。

批准 **V78_UNINTERRUPTED_JACOBI_AND_STOP_LOSS**：只读复用已有原算子与Jacobi对角，执行一次连续的restart128求解；这不是新预条件器，不承诺成功。正常没有新矩阵、局部/粗numeric或新FE装配。第一完整周期无足够效果就结束，本分支停止自行逐版试PC，不自动立下一方案。

本轮要消除的具体blocker是：复杂PC已被实测否决，但廉价基线被人为32步截断并新建KSP续算，尚不能判断一个实际128维搜索周期的效果。不得把本项说成解决了全部波长鲁棒性或原尺寸容量。

```text
repository = Rookie1234567/MyFEniCS
branch = task42_neural_coarse_inverse
worktree = /home/fenics/Projects/NN-Lab
original_base_SHA = ccd357885f7f9be84efe3be07868cc94f13d93fc
reviewed_HEAD = 138df5d715334de41df0889c19181d409a7db992
reviewed_commit_time = 2026-10-12T07:47:23Z / 2026-10-12 15:47:23 +08:00
previous_review = review_report_v75.md @ fc02a8612f1aa31b2c52366cc645acee6b5f8daf
reviewed_response = response_v77.md
campaign = V78_UNINTERRUPTED_JACOBI_AND_STOP_LOSS
required_response = response_v78.md
ordinary_default = UNCHANGED
NN_training / merge = NOT_AUTHORIZED / NOT_APPROVED
```

最终目标仍为原50×25nm周期、z=-10..130nm、0.7nm、任意非可分三维材料/几何、complex128 Nedelec H(curl)、双Floquet/Fourier-DtN，整机约2TB保留系统余量，必要构建至完整验收≤172800s、ownswap/OOC=0。当前s=7/135缩尺模型不等于该目标。本报告明确覆盖V75“不再运行Jacobi”及V74的32/64步效果门，仅限以下一次未重启周期；历史失败与旧预算不改。

## 1. 最新证据与解释边界

实际读取最新ref、V77完整回应、4个增量提交、阻抗面核/子域装配、controlled runner、原规则和task、任务树与最新入口；前一报告下载副本的完整正文对应远程blob。任务树未发现独立supplement；未逐行重审全部历史或声称SSH访问了工作站。主要依据：[V77](response_v77.md)、[V76](response_v76.md)、[最新原式](outcomes/records/mathematical_qualification_v77.json)、[V77曲线](outcomes/records/residual_history_v77.json)。

| 同25576tet/p5/828；measured | 新Arnoldi步 | 原true | 接口true | KSP含检查秒 / wrapper秒 |
|---|---:|---:|---:|---|
| Jacobi历史零起点 | 32 | 0.388826586390 | 0.379105019552 | 174.050 / 526.966 |
| Jacobi历史续算 | 累计64，但中间新建KSP | 0.341713600189 | 0.339415221770 | 两wrapper合计1073.141 |
| V77阻抗+粗层 | 32 | 0.917996117703 | 0.919289591408 | 521.867 / 1272.633 |

V77的38块局部方程、出射符号、独立面积分、39因子和原式身份检查通过；无普通错误造成科学重放。37.080410GiB采样峰属于失败尝试。新局部CSR共368317250项，科学执行链2580.145s，最终增量费用下界2908.906s；不能把它们称为合格解的低内存/加速成绩。原true/native/augmented/port均未过1e-6，昂贵坏场物理输出按政策NOT_RUN，保存系数可继续消费。

**已证结论是这份固定PC无效，不是所有Maxwell DD无效，也未定位唯一根因。** 真实原算子、Jacobi、独立审核与checkpoint可复用；旧PC包保留证据但不再创建其因子。

## 2. 前次决策遗漏的物理适用性：符号正确不等于吸收有效

[physical_impedance_patch.py](../../src/solvers/physical_impedance_patch.py)的outward_symbol使用波矢k0*n，检验的是法向出射；impedance返回固定-i*k0*sqrt(epsilon/mu)。这检验了所定义公式的符号，**没有检验实际掠入射和全部误差波的传输能力**。

考虑均匀空气中的平面TE波与平坦阻抗面。这只是解析诊断，不是当前不规则38块的实测反射。令mu=|k dot n|/k0，一阶法向匹配边界的反射幅值满足：

```math
|R|=\left|\frac{1-\mu}{1+\mu}\right|,\qquad
\mu_z=\sin(1^\circ),\quad
\mu_y=\cos(1^\circ)\sin(5^\circ),\quad
\mu_x=\cos(1^\circ)\cos(5^\circ).
```

| 理想化面方向；derived，非实际patch测量 | mu | 幅值反射 | 功率反射 |
|---|---:|---:|---:|
| x法向 | 0.996043 | 0.001982 | 0.000003930 |
| y法向 | 0.087142 | 0.839685 | 0.705071 |
| z法向 | 0.017452 | 0.965694 | 0.932565 |

这些数不能与0.918残差等同。它们足以否决“只要采用-i*k0*n就能很好传递本题所有方向波动”的前提。实际切口斜面、材料、复波数、误差频谱和粗空间会共同影响收敛，尚无完整因果分解。今后任何新传输机制须先给出传播/掠射/消逝分量上的符号与近似范围，不能只用法向符号测试和方法名称立项。[T1]

本轮不据此立即换二阶Robin、PML、另一套局部DtN或再建波动粗空间；方向适配检查是今后投入条件，不是本轮另一项大型开发。

## 3. 为什么保留一次Jacobi，而不是再次提高restart

[controlled_trace_study.py](../../src/solvers/controlled_trace_study.py)对BJ设置max_it=32，PROMOTED只读取scaled_retained并调用新的run_retained_fgmres；原Arnoldi基没有传递。**旧的32+32并不等于同一个KSP中连续64步，更不等于完成了restart128的一个周期。** GMRES的搜索空间与重启语义见[T2]。旧R128失败属于另一个PC，不能代替Jacobi的结论。

本轮restart仍128，与V76所配置值相同；只取消人为在32步结束实例的调度。全部32/64/96步检查留在同一KSP内，不丢弃搜索方向。这个区别有源码证据，但不证明连续周期必然收敛。

这里不加载38个局部块、Z0/E0、harmonic或阻抗包；不建立任何新numeric。已有packet里的原cell内部LU仍用于作用/恢复，因此不称factor-free，也不把父准备成本写零。

## 4. 冻结问题、唯一执行及最小接线

保持完整FE1943745、retained1177293、25576tet/p5/1000个NOTCH tet、全部828模式、原载波(8.94046081729244,0.7821889682108057,0)、1度掠角/5度方位/s、Si n=0.999885140474+4.32477054e-6i及全部原材料与RHS。无改p/h/M、物理损耗、参考面、边界和尺度。

```text
mesh_sha256 = c470274ab6c64cee0b8eef09dbcdadadfac4c6ca229d7fc2b6e608ded62f540c
physical_sha256 = df26b8cf28e1115bdb2eb9ac9b79e698596133305310d26c1d664f94e2c5be44
packet_sha256 = 9bef5add6398999c70c21c7f26a86833fc1eb46f98598c8503aa3c41743728da
```

PRECHECK只读V76已资格化complex_diagonal和原packet，核对左右尺度/原RHS/算子身份及零对角计数，不重生成对角，不重跑3次作用和历史单位向量资格。文件缺损可由原正确trace_diagonal只重建该小资产，记录费用，不重建FE/粗矩阵。数学未变时复用资格收据；不删除hash保护。

主角色J128_CONTINUOUS：RIGHT FGMRES、restart128、max_it256、原正交化/norm/坐标、retained零初值、原复Jacobi右作用。只用当前物理RHS；不得读取正确参考场或旧失败向量初始化。不要把role命名BJ后继续触发旧max_it32，不走PROMOTED，不通过scope字符串静默落回旧窗口。

给已有controlled runner和FGMRES传入显式iteration_policy：max_it、评估时点和本轮effect_check；旧入口默认不变。**不复制大型runner，不改变原算子或PC数学来实现本轮。** 最多一组pure-array/小复数KSP接线回归，证明第32/64次回调不会销毁KSP，并检查新角色计时/计数沿一份scope；不以真实PDE作调度测试。

## 5. 继续门、验收和失败后的确定处理

令rho=max(独立原true,scaled retained true)。原式、端口和恢复仍由原q15 PUBLIC_BASIX及q63边界审核，不改分母，不把KSP报告残差当原残差。

| 时点 | 动作 |
|---|---|
| 0/32/64/96 | 保存原true、接口true、port、迭代累计成本；只观察，不套用旧0.30/0.10阶段门；安全、nonfinite或真实身份失败例外 |
| 第128步 | 完成第一次真实搜索周期。rho>0.10则EFFECTIVENESS_FAIL并冻结，不开始第二周期；rho<=0.10才继续同一KSP，最多256步 |
| 达到原联合门 | 冻结合格候选，退出并进行完整验收，不为了表格继续凑步 |
| 256步或累计KSP含检查3600s | 保存终态，未过门为有限失败，不自动512步、改restart、回收子空间或另一PC |

0.10是一次完整周期后的投入门，不是数学不可能性判定；放宽的是研究观察窗口，不是最终正确性。第一次128周期内原残差未必单调，持续用原式判断，禁止以较小接口残差覆盖原残差。

最终沿原门：retained<=1e-11；独立true/native/augmented/port各<=1e-6；MPC/恢复/Schur-original<=1e-10；独立direct1e-10单列。联合通过后才读V70并验证六场/原240点/复通道<=1e-6，R/T/A/A_volume差<=1e-8，逐mode差<=1e-9，能量<=1e-5。保留原同一分子两固定分母，不校幅相、不删点/模式。

未达联合门的候选保存完整retained、全FE恢复系数、原式向量与身份；原true>1e-2不做昂贵六场积分、图表或衍射评分，official=False。达到1e-2但尚未合格不自动授全部诊断输出，优先交原式/成本；正确场不因writer错误丢失。

**本轮后不再以“换一种PC看看”自动立项。** J128也失败则关闭本分支当前固定小粗空间/局部逆机制试错，只保留正确原作用和已有直接参照供明确消费者使用。该决定不是放弃通用Full3D目标；新的传播/粗空间方案须先有同物理方向与误差尺度依据、已有同题成本对照及明确消费者，不能继续靠每轮修正名称取得重型预算。

## 6. 资源与故障恢复：低成本上限，不再扩大准备

新总研发窗4h，全部实现、读取、失败、修复、KSP、输出和文档均计费；累计KSP含检查<=3600s，全域作用<=400，最后1800s收口。启动主solve前保留完整KSP配额及4500s可能成功的物理验收，不把输出时间隐藏。没有新的独立局部分解阶段。

整树规划64GiB、警戒80GiB、采样停止96GiB；不借用旧96/112/128或256GiB许可。FGMRES128两主向量库257条约4.509GiB只是derived载荷，需加mesh/MPC、原局部包/热缓存、复Jacobi向量、原式工作区和恢复，实际RSS准入。全局K/S读取/形成/new fine LU为0，new local/coarse numeric为0。父packet内部LU和前缀成本单列。

沿原qualified native activation、complex128/int64、MPI1/math1/CPU1/GPU0、ownswap/OOC0、宿主/cgroup/PSI/邻增长/CPU-SMT/heavy锁，不改邻任务、系统配置或ABI。新ignored<=8GiB、free>=50GiB，完整向量和原子写出空间先核对，旧结果不删除。

正常一次KSP.solve。普通元数据/路径/writer错误同窗修复并继续，避免抛异常销毁健康KSP；已返回解只补消费。数学/调用异常导致KSP确实失效时，可在同一累计预算内一次修复续算，但必须标记Krylov基丢失，不能再称完整未重启对照；无合法原式不得续用该候选。总新增Arnoldi步<=256、KSP时间/作用计数不清零；失败不授权第二种方法。普通修复总<=45min，不能按bug个数立即停，也不能无限重播。

不full pytest/CI、全仓索引、历史hash扫描、旧FLAT/PC/39因子或已完成物理对照重跑。只测试显式policy、资产复用、同KSP检查点及失败出口。数学核心与通用策略进src，benchmark仅薄调用。

## 7. 正式入口、交付与通向目标的判断

```bash
python scripts/run_case.py input/task042_neural_coarse_inverse/v78_jacobi_reuse_preflight.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v78_jacobi_uninterrupted.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v78_verify_cost.dat
```

以上入口尚待实现；必须targeted回归、commit clean、真实dat validate后运行。PRECHECK/VERIFY不能暗藏KSP或numeric。C1仅显式policy/复用/必要测试，C2结果及紧凑记录，C3回应与两总账短增量；不为了固定提交数拆分无意义变更。

交response_v78.md、outcomes/uninterrupted_jacobi_v78.md及紧凑原残差/配置/资源/source记录。回答：是否真的完成一个不中断周期、原残差是否下降、是否获得合格同离散场、总费用多少。前32步与旧BJ仅作可重复性观察，不以浮点轨迹逐位相同作数学门。原量、旧失败和所有未测项保留，不生成几十份重复清单。

目标路线分清两个资格：廉价基线合格只证明固定缩尺离散系统可解，历史P6/L5空间FAIL、原尺寸传播通道库存、MPI复制/所有权和完整48h成本不随之通过。若本次成功，下一个有价值的阶段是消费已证明有效的求解方式，测packet-only冷前缀和一个中间尺度，而非自动运行原尺寸。若失败，停止Task42重复昂贵PC准备；工程线自己的原尺寸reference-q工作和邻NN线保持独立，不在本次给它们新授权或推测其最新通过状态。

只推送origin HEAD:refs/heads/task42_neural_coarse_inverse。核对完整remote SHA/upstream/clean、closed/active null、后代清场与自有锁释放后交付；不merge、不改master/邻worktree，不自动V79。

## 8. 来源与审阅边界

[T1] COMSOL官方[一阶散射边界的适用范围](https://doc.comsol.com/6.3/doc/com.comsol.help.woptics/woptics_ug_optics.6.72.html)及[掠入射反射说明](https://www.comsol.com/blogs/using-perfectly-matched-layers-and-scattering-boundary-conditions-for-wave-electromagnetics-problems)。用于核对物理近似，不运行COMSOL、不将其示例当本项目实测。

[T2] PETSc官方[KSPGMRESSetRestart](https://petsc.org/release/manualpages/KSP/KSPGMRESSetRestart/)。只援引搜索基和重启的算法语义，不升级工作站软件；增大搜索空间并不保证本题收敛。

审阅端复算了上述空气平面波反射与向量库存，读取了当前源码和远程结果；没有执行工作站PDE、实时资源审计或新的Jacobi收敛试验。新方法收益未测，不给保证。报告使用fenced math；渲染不可取得时如实记NOT_VERIFIED，不能因此重跑PDE。
