# Review V77：停止盲试PC，以保存的正确解建立剩余误差证据

## 0. 正式裁决

**接受V78为可信的有限负结果，不接受有效求解、同精度性能收益或目标资格。兑现V76的止损决定：不追加Jacobi周期，不更换restart，不重建RAS、阻抗、harmonic、SMR或另一套未经误差证据支持的PC。** 最新连续128步原残差0.284024612789，比旧32+32好，但仍远高于1e-6。局部数学正确、单次作用快和低RSS都不能替代正确完整场。

此前评审连续从“一个实现成立”推到“值得投入一次大型求解”，而没有先把失败迭代的真实场误差与已有正确离散解比较。这是决策证据不足，不应继续让Codex通过更多重型尝试承担代价。本轮不以换方法名称回应进度压力。

本报告只授权 **V79_KNOWN_ERROR_BUDGET_AND_HANDOFF**：一个有界的保存数据消费者，量化Jacobi剩余错误、原算子各项的抵消与误差的空间分布，并导出可复用的同离散挑战数据。**不授权新的PDE求解、PC调参、训练、粗空间构建、全局矩阵或任何新numeric factor。** 这是求解机制选择前的诊断，不包装为生产路线突破；若仍不能识别可检验机制，就报告证据不足，停止申请新重型预算。

```text
repository = Rookie1234567/MyFEniCS
branch = task42_neural_coarse_inverse
worktree = /home/fenics/Projects/NN-Lab
original_base_SHA = ccd357885f7f9be84efe3be07868cc94f13d93fc
reviewed_HEAD = 01b288d2c0ea47ff6f974d7ff453076ae4bbf9ee
reviewed_commit_time = 2026-10-12T09:24:31Z / 2026-10-12 17:24:31 +08:00
reviewed_response = response_v78.md
previous_review = review_report_v76.md @ c126e154a7196cf427b4511a9e2e596fa5580993
scientific_source_V78 = a08d40f9845f481fa79abf6f8d7a48c99b956bcd
campaign = V79_KNOWN_ERROR_BUDGET_AND_HANDOFF
required_response = response_v79.md
new_KSP_solve / new_numeric / NN_training = 0 / 0 / 0
merge / ordinary_defaults = NOT_APPROVED / UNCHANGED
```

目标仍是原50×25nm周期单胞、z=-10..130nm、0.7nm、任意非可分三维、complex128 Nedelec H(curl)、双Floquet/Fourier-DtN，约2TB整机物理内存保留系统余量，必要构建、求解、恢复、输出、验收不超过172800秒。当前s=7/135缩尺问题不是目标规模。V79仅覆盖旧“失败场不作昂贵输出”的一小部分：允许一次必要的真实误差积分，不开放坏场RTA、全衍射评分和图表。

## 1. V78审阅事实

依据：[response_v78](response_v78.md)、[真实配置与逐点记录](outcomes/records/results_v78.json)、[费用](outcomes/records/resource_costs_v78.json)、[证据索引](outcomes/records/evidence_index_v78.json)。

| 同25576tet/p5/828，measured | 独立原true | scaled retained true | port |
|---|---:|---:|---:|
| 32步，同一个KSP | 0.388826586390 | 0.379105019552 | 0.0525401882174 |
| 64步，同一个KSP | 0.316494040594 | 0.315852440263 | 0.0188602430720 |
| 96步，同一个KSP | 0.295572340788 | 0.295216222243 | 0.0143500399313 |
| 128步，同一个KSP | 0.284024612789 | 0.283620383707 | 0.0138676292829 |

create/solve/destroy各1，未丢Arnoldi基；128步投入门0.1失败，第二周期未运行。原式/接口正式门仍1e-6/1e-11，不以研究门覆盖。真实残差继续下降但边际改善变小，不能称完全不动，也不能据此保证更长迭代收敛。

KSP含检查534.859523秒，完整失败wrapper875.795297秒，PRECHECK+主对照+独立VERIFY为1182.803294秒；父子区间不相加。采样整树峰11.674725GiB，实际最大gap1.224841401秒；连续峰unknown，ownswap/OOC为0。140次全域作用，新矩阵/numeric为0，但父packet内部LU存在。最终历史已知费用下界400183.831621秒属于多轮研究累计，不是单场耗时或48小时不可能性证明。

新进程原式向量与producer差0；完整FE、port、RHS、尺度、MPC、网格和源码均已保存。六场积分和功率按失败政策未运行，不能据低残差或低内存给出有效物理解。

## 2. 已能从源码排除的解释：原true不是仅端口不一致

[complete_residual_metrics](../../src/solvers/independent_tetra_reference.py)使用完整未凝聚方程的闭合FE残差。按原符号：

```math
\mathcal A\binom{u}{a}=\begin{pmatrix}K&C\\-D&H\end{pmatrix}\binom{u}{a}=\binom{f}{g},\qquad
r_E=f-Ku-Ca,\quad r_p=g+Du-Ha.
```

```math
q=r_E-CH^{-1}r_p=(f-CH^{-1}g)-(K+CH^{-1}D)u.
```

因此q与当前辅助端口系数a无关；本题g=0。代码的true是q对原FE RHS分母的相对范数。**0.284是原闭合物理FE方程的不平衡，不能只归罪于端口变量尚未闭合或KSP打印了错误的范数。** 此式是源码代数解释，不批准端口消元作为新的求解试验。H逆仍按原元素/模式实现，不正则化或删模式。

残差也不是场误差。PETSc官方[KSPSetNormType](https://petsc.org/release/manualpages/KSP/KSPSetNormType/)明确区分方程残差与解误差。只有已知同离散参考时，才能直接量出后者；无需据残差猜其大小或类型。

本题虽有原参考，但它不是连续真解。V70独立原true约3.3562e-10，direct1e-10子门未过；历史P6/L5空间增量FAIL均保留。0.7nm材料、相位、几何和模式身份固定，不跨p/h拿两个不同空间相减冒充代数误差。

## 3. 唯一获准消费者：真正的同离散错误，而非又一组PC见证

### A. 一次读取、明确身份

只读V70正确离散场与V78第128步终态；第32步仅在其完整系数已保存且可直接读取时加入，不能重跑或重建轨迹。按各自已提交的source/array索引定位真实路径，不遍历全盘、不猜包名、不复制全量artifact。

```text
mesh_sha256 = c470274ab6c64cee0b8eef09dbcdadadfac4c6ca229d7fc2b6e608ded62f540c
physical_sha256 = df26b8cf28e1115bdb2eb9ac9b79e698596133305310d26c1d664f94e2c5be44
packet_sha256 = 9bef5add6398999c70c21c7f26a86833fc1eb46f98598c8503aa3c41743728da
full_FE / port / retained_rows = 1943745 / 828 / 1177293
carrier = (8.94046081729244, 0.7821889682108057, 0)
```

核对真实数组、native basis、DOF排列、P、模式键、参考面、材料、入射、RHS和左右尺度；origin-extrapolated倏逝幅度可能极大，不能把辅助端口系数欧氏范数当物理场误差。优先直接相减保存的完整独立FE系数，随后用P恢复native。若必须从retained差恢复，使用零RHS的齐次恢复；不能再加一次内部特解。保留参考非零残差，不把它设0。

[V70参考](response_v70.md)及其[独立科学记录](outcomes/records/scientific_checks_v70.json)是同离散权威，不重新factor；不得以旧full-K或S的存在为理由读取这些大矩阵。只有本次诊断进程可以访问正确解；之后任何候选若使用了本诊断选型，必须标记该参考已被消费，不再称blind/held-out。

### B. 一次明确的误差闭合与场误差积分

令e=u_ref-u_J，采用同一个q63物理边界与q15 PUBLIC_BASIX体作用：

```math
\bar A=K+CH^{-1}D,\qquad \bar A e=q_J-q_{ref}.
```

复用[actual_error_diagnostics.py](../../src/solvers/actual_error_diagnostics.py)的误差恒等式和[physical_error_diagnostics.py](../../src/solvers/physical_error_diagnostics.py)的复制/范数约定；这是既有诊断组件，不是新算法。按原运算尺度验差<=1e-10；不同producer边界或原残差定义必须先对齐，不将不同向量静默比较。保存q、e及完整身份即可，不重复生成所有历史原式。

复用[tetra_polynomial_difference.py](../../src/solvers/tetra_polynomial_difference.py)的same_native_difference和numerator，**只调用差分分子消费者，不调用完整comparison**。后者要求失败场不存在的output.integrals/port_metrics并会触发无关评分。读取V70已有q23/q31物理范数作固定分母，不给失败场重算分母。相同实载波下，total/scattered差分分子相同；原背景、物理单位和near-zero floor保持。

积分q沿已有`2*embedded_superdegree+3`证书，p5正常为13，现场核对；对角/系数欧氏量不冒充E/H L2。先完成128步误差的E、H、完整相位curl及逐cell非负平方积分，32步是同遍历批处理的可选第二列。只产生误差标量和轻量cell数组，不输出六场网格文件、原240点侧选择、全衍射表或RTA。

必须给出：相对V70总场与散射场的两套固定分母误差，误差范数与原残差是否同步改善，材料/预先固定四个等体积z区间的体积分分账。每个cell仅计一次，分账和整体一致<=1e-10；区域不按结果重新选，体积与误差平方占比分列。该分账描述的是当前迭代错误，不是V69的P6/L5离散差异，不能混用。

### C. 对完整FE错误拆原方程，不另凝聚curl与mass

只对128步误差作一次额外的机制分账：

```math
v_c=K_{curl,\kappa}e,\qquad v_m=-k_0^2M_\epsilon e,\qquad v_b=CH^{-1}De,\qquad
v_c+v_m+v_b=\bar A e.
```

在[tetra_coefficient_action.py](../../src/solvers/tetra_coefficient_action.py)已验证的参考积分上提供显式diagnostic回调，复用同一批基函数、真实Piola、方向、P共轭拉回和材料。允许拆现有积分项，不改production apply默认值。**不分别静态凝聚三个物理项再相加**；这里只对已经恢复完整的e作未凝聚作用。边界采用全部828模式，不用第一阶阻抗替代。

保存三项dual范数、3×3复Gram交叉项、和向量及其与q_J-q_ref的闭合误差；标注这些dual范数依赖基/尺度，不能当物理能量。另由同一场积分报告：

```math
\chi=\frac{\|\nabla\times \delta E\|_{L^2}}{k_0\|\delta E\|_{L^2}},\qquad
\gamma=\frac{\|v_c\|+\|v_m\|+\|v_b\|}{\|v_c+v_m+v_b\|}.
```

chi描述该已测错误的curl尺度，gamma描述这一个向量上的项抵消。二者都不是条件数、谱半径或共振证明；小chi不自动证明错误属于梯度空间，大gamma不自动证明某个sweep/吸收PC有效。零分母按绝对量报告，不能伪造有限比值。

## 4. 下一方法的准入：不再由方法名决定

交付只需回答以下问题，不能把它扩成全谱、所有旧PC重放或新特征库：

| 问题 | 必须带回的证据 | 不允许的结论跳跃 |
|---|---|---|
| 残差下降是否真正修好了场？ | 128步真实E/H/curl错误，条件32步比较 | 0.284不等于28.4%的电场误差 |
| 未消除错误体现何种尺度？ | chi、三个原作用分量、交叉项、空间分账 | 不凭单一比值宣布唯一根因 |
| 何种新机制值得投入？ | 一条可证伪假设、对应测量、与旧失败的实质差异、N=1成本表 | 没有证据就不指定新PC、不申领重型预算 |

若结果仍不足以区分表示、传播与尺度问题，结论写`INSUFFICIENT_CAUSAL_EVIDENCE`，保留正确算子和离散参考，不自动下一批。若识别出一个更具体的候选，也只写准入卡，不在本批搭建和运行。新候选将来必须以原RHS和新的独立误差方向验证，全部准备计费，优于廉价基线且通过原式/场门；不能把已知正确误差直接塞进PC后宣布成功。

本次“真误差消费者”不是新的Full3D求解能力。其价值是把下一次重型决策从猜测改成同题数据；没有这个变化就不要继续计算。当前PC试错路线继续关闭，不因为写出了一个诊断PASS而重开。

## 5. 对2TB/48小时主线与邻分支的约束

准确性、同离散求解、全流程容量分别验收。V70等正确直接参考可服务求解器验证；现有空间精度未闭合，不能作为目标准确网格。复用父packet只能叫prepared-start，packet-only冷构建份额未知，不能填0。

本轮已只读核对工程分支`task40extra_0p7nm_engineering`，HEAD为`d7ffbfea952bc160742b18739369f2e3f656ee8e`，最新review已授权saved-first V31；其[response_v30](https://github.com/Rookie1234567/MyFEniCS/blob/d7ffbfea952bc160742b18739369f2e3f656ee8e/docs/task40extra_0p7nm_engineering/response_v30.md)记录旧q0参考残差约2e-14，但本轮目标Ny8未取得FE/MPC完成的持久收据，q0–q7新资格0/8，完整PDE未完成。不能再把它说成已有目标解，也不在Task42重建它的reference-q/CSR、启动服务或改变其授权。

Task42仅导出同离散消费者契约：精确模型/数组/原作用入口、正确参考与失败候选、资格/费用/已知不足、明确不可跨网格直接替换。不能把tetra场或PC直接接入工程线hex系统；不得整体merge、擅自发消息给邻执行器或恢复NN训练。Task42extra的网络路线继续保持独立，本报告不对其未核对的新进度下结论。

最终架构仍须从无界全局直接因子、显式大耦合和MPI复制转向分布式matrix-free Full3D iterative、有界局部/粗问题与流式DtN；Hybrid仅作为可利用结构的加速器。本轮不声称这些能力已实现。停止一个无收益候选不是放弃0.7nm目标，但继续失败候选也不算推进目标。

## 6. 实施、资源、修复及交付

**单一总研发窗2小时，包含读取、实现、失败、计算和文档；数值/数组有载最多45分钟，最后20分钟收口。全域体作用按列计最多8次，新KSP/new numeric/new global K/S均0。** 只准一个p5/q13差分遍历，可批两列；不重复q23/q31大积分。64/80/96GiB整树规划/警戒/采样停止不提高；新增ignored<=2GiB，free>=50GiB，全部旧数组只读。

先核对branch/HEAD/upstream/worktree、原native ABI和complex128/int64、MPI1/math1/GPU0、ownswap/OOC0、宿主/cgroup/PSI/邻任务/CPU-SMT与machine heavy锁。这里会读取百万规模向量及执行FE作用，**不是可以忽略heavy锁的轻量文档任务**。现场有冲突则完成纯文档部分，不能干扰邻计算。

用已有消费者和数值小核，不新增通用调度框架或复制大型runner。主误差积分、项分解、决策导出为可独立保存的结果；32步资产缺项只取消32步，分解适配失败不丢弃已合格的场误差。普通路径、dtype、writer问题同窗定点修复、继续健康块，不按bug个数停止；已有差分/积分块不重算。未知来源或数学不一致必须隔离，不关闭身份检查。总修复<=30分钟并受总窗约束，不要求修好后再开新窗口。

若尚需实现，先做一次合成复数闭合/新回调测试、相关compile/Ruff和两dat validate，commit clean后运行；不重跑旧PDE、full pytest/CI、39因子、全仓索引或历史全盘hash。正常两次提交：必要小接线；结果与回应。只增加少量直达证据，不再生成几十份内容重复的清单。

```bash
python scripts/run_case.py input/task042_neural_coarse_inverse/v79_known_error_budget.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v79_decision_export.dat
```

每dat是一项明确的保存场诊断或纯保存消费；入口尚待实现，不假称已经可执行。第二入口不暗藏FE重算或新求解，费用累计不清零。最低交付：`response_v79.md`、`outcomes/known_error_budget_v79.md`、`outcomes/records/known_error_budget_v79.json`、`outcomes/records/reference_consumer_contract_v79.json`；源/时钟/资源/数组hash在原run provenance中绑定。summary、两总账只短追加，不改历史。

提交仅到本分支：`git push origin HEAD:refs/heads/task42_neural_coarse_inverse`。核对remote完整SHA、upstream、clean、closed/active null、后代清场与锁释放后暂停；不merge、不自动V80。实现错误并不授权启动新的求解器。

## 7. 审阅范围与未完成项

本次实际读取远端ref/提交、V78完整回应及结果、当前任务和规则、任务树（未发现独立supplement）、当前summary入口、上轮完整review副本和远程blob、相关数值消费者与工程线V30；未逐行审阅全库所有代码或SSH运行工作站。报告中的新误差分账尚未运行，因果解释保持待测。

本次仅提交本review。Markdown结构、公式fence和文件身份需机械核验；GitHub渲染若不可取，应记NOT_VERIFIED，不得因此重复科学计算。没有在审阅端生成新的Maxwell解，未承诺下轮一定收敛或达到原尺寸目标。
