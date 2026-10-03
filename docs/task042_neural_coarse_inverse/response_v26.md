# Task042 V26：固定5／7联合方向诊断收口

**V26已完成，数值资格通过，预登记决策为 `FIXED_JOINT_DIRECTION_INSUFFICIENT`。** 两终态g均≥0.95，未达到两者g≤0.75的继续研究信号。关闭本固定5／7联合方向提案，不新启动迭代、另一块对或训练。它产生了可分辨的新方向，但不能显著消除旧八方向留下的残差；不是新的有限元解，也不否定所有接口／神经方法。

把两个相邻局部块一起解，是让一次局部解考虑它们之间的双向耦合。本批把这个新向量的原方程响应，加入已有八个向量的响应集合，只检查多出的方向是否有用。代价是一套更大的稠密矩阵／LU、一次只读重载与有界原作用；不把诊断向量作为部署PC或求解终态。

eta8／eta9是修正后原trace残差范数除以各自当前残差范数；g比较加入新方向前后剩余残差，分母不是物理b或参考场。范数下降与平方范数消除分别列出，均为measured／derived offline diagnostic。

| 固定已消费冷终态 | eta8 | eta9 | g=eta9/eta8 | 相对e8范数下降 | 相对e8平方范数消除 | rank |
|---|---:|---:|---:|---:|---:|---:|
| V24-LZ-CYCLE4 | 0.983236989810 | 0.966205505618 | 0.982678149451 | 1.732185% | 3.434365% | 9 |
| V24-LCZ-CYCLE4 | 0.989924628585 | 0.981968429990 | 0.991962823870 | 0.803718% | 1.600976% | 9 |


两个状态不是fresh终测，均为V24已消费冷末态。旧V25数值和原始记录不改；本批没有调用REF7、teacher、NN权重、旧p1 T/U/R、D_L或Krylov库存。

## 身份与执行

| 身份／范围 | 现场核验与证据 |
|---|---|
| branch／upstream／worktree | `task42_neural_coarse_inverse`／`origin/task42_neural_coarse_inverse`／`/home/fenics/Projects/NN-Lab` |
| canonical common Git／origin | `/home/fenics/Projects/Maxwell3D-Lab/task-repository.git`／`git@github-myfenics:Rookie1234567/MyFEniCS.git`；开始clean、无本Task actor、安全fetch/ff后含 `867ab17c496b2e5dc57766da749eb1f6b42036a1` |
| base／实际run source | `ccd357885f7f9be84efe3be07868cc94f13d93fc`／`652cb206cd1ebeb1c4182ac2300c1dc23c57b48f`；clean实现提交后运行，文档／checker的后继HEAD不冒充source |
| 原物理／离散 | 0.7nm，1.4×1.05×1.4nm三维缺口micro，384hex/p3/h0.175nm/q15；双Floquet、完整40端口；18144 trace／40 port／18184完整z |
| physical／packet | `2b532f91550316b16a304f3be9ae78605816b5a2aba556f548b5bd794f82e6de`／`9196edb807b534217d0c0eb78882125341342784a48ef20ebe2d9421fe636454` |
| 材料 | canonical `SI_OPTICAL_CONSTANTS_USER_20260929_V1`；Si n=0.999885140474+i0.00000432477054，epsilon=n²；source标签0.699999988→nominal0.7唯一alias，不改材料/背景 |
| 固定J | 零基5／7，2220+1668=3888行；canonical升序完整实体并集，hash `893f5a0b49a6d5e27c8fcef34482fed35bd783064d4504d0ed9dbf9dc9ec6029` |
| one-run | `python scripts/run_case.py input/task042_neural_coarse_inverse/v26_joint_block_diagnostic.dat`；仅一个正式离线actor，两份固定残差，非PDE求解器扫描 |

完整输入／mode／材料／map／父状态与成员hash见[input inventory](outcomes/records/input_inventory_v26.json)。[run index](outcomes/records/run_index_v26.json)绑定original dat、resolved、manifest、原始结果、时间线／日志与ledger；[source inventory](outcomes/records/source_inventory_v26.json)区分开始HEAD、运行source与后继证据来源。旧V24/V25目录只读，dot/master及其他worktree不改，未使用重置卡。

## collector与数值资格

§3最小修复要求恰好三个唯一固定name，逐名绑定plan/parent/state path、容器及成员hash，明确选取LZ4/LCZ4；空、缺、重复、错label/交换内容、坏gates、非有限、缺rank/重组拒绝。decision()同样保护命名边界。真实V25三组缓存重算仍EIGHT_DIRECTIONS_WEAK，旧数据不重跑、不重写。新两样本checker也核对固定库存并从向量重算。[库存核验](outcomes/records/fixed_inventory_checker_v26.json)。

| 数值Gate；同一原算子独立见证 | measured值／要求 |
|---|---|
| 3888行主块装配 | 全384 cell均遍历，96 cell有J贡献；完整Schur／Floquet／MPC共享贡献合并及40维Hhat消元，F不假定Cᴴ；A5/A7原对角块配对通过 |
| 唯一LU | complex128 LAPACK partial pivot，无shift/drop/精化/fallback；`JOINT_5_7_DENSE_LU_PRESENT`，非factor-free；无global fine K/A/CSR及global p4 LU |
| gecon | info=0，rcond1=9.86264412868e-06≥1e-12；一次尝试，内部pass未知，保守上界22另计 |
| seeds422601/422602原正／共轭作用 | 最大operation差1.594e-16≤1e-10；真实正向及共轭转置分别计费，非互伴端口未被改写 |
| 随机solve／复线性／零 | 最大相对solve残差3.113e-13≤1e-8，operation≤2.094e-18≤1e-12；复线性1.657e-13≤1e-10，重复差0，零RHS精确零 |
| 只读重载 | 新A/LU/pivot容器及数组hash通过，一次reader、不refactor；pivot私有可写15552B；同进程重载，不冒称独立进程运行 |
| 两状态身份 | 18144/40/18184拼接正确；保存r与原b-Sz、40port重闭合核验通过；最大trace差/b5.999e-17，方向不含内部特解 |
| QR／rank／驻点 | 各一次9列nonpivoting QR+小GELSD，cond1e-12，rank9；最大驻点6.024e-17≤1e-8；数值满秩不称精确最优或完整物理资格 |
| 原独立重组 | 每状态新一次A(Q_local*c+gamma*qJ)；差/b≤1.641e-16≤1e-11，差/r≤7.151e-16；operation≤2.090e-21≤1e-10另报，不仅依赖保守尺度 |
| 独立缓存checker | 从hash-bound实际向量重算eta/g、正交创新、驻点与相干度；不增加原作用、QR/SVD或factor读取；不只信status/gates |

[联合资格](outcomes/records/joint_numerical_gates_v26.json)、[两状态系数／Gate／数组](outcomes/records/extra_direction_gates_v26.json)、[独立缓存重算](outcomes/records/cached_array_checker_v26.json)保留全部值，未四舍五入过Gate。

## 局部与全域的区别

新方向h是从vJ扣除旧八响应已经包含的部分。h/vJ约0.77，远高于64eps原运算尺度界及1e-12相对界，确实增加方向；但它与旧剩余残差e8的复相干度仅0.1853／0.1265，因此能额外消除的平方范数仅3.4344%／1.6010%。这定位为**新响应不够对准剩余残差**，不是重复方向或线性头没求好。

| 状态 | 新方向h/vJ范数 | 与e8复相干度 | J内e8→e9范数 | J外e8→e9范数 | qJ响应在J外范数比 | 旧q5+q7响应在J外范数比 |
|---|---:|---:|---|---|---:|---:|
| V24-LZ-CYCLE4 | 0.768351096 | 0.185320411 | 0.003405752361 → 0.002856574893 | 0.005671246941 → 0.005839453512 | 0.827448040 | 0.639896355 |
| V24-LCZ-CYCLE4 | 0.769292384 | 0.126529665 | 0.01428603752 → 0.01299844595 | 0.02246321287 → 0.02298654608 | 0.875014934 | 0.648236637 |


J内剩余残差下降，J外反而上升；同支撑旧q5+q7与qJ已由新原作用配对，方向差／响应差明显，不能归结为仅扩大支撑。新响应的J外范数比0.8274／0.8750，高于旧控制0.6399／0.6482。A57/A75的Frobenius范数均约3593.0401，但非互伴差范数642.3616、按两项和归一约0.0893897；不据范数相同推断互伴。仅考虑联合内部耦合可改善局部，却没有处理全域返回作用的证据。以上不是场误差、唯一根因或对所有NN的否定。

## 资源、费用与边界

| 全部shared-workstation；峰与嵌套计时分开 | measured／derived口径 |
|---|---|
| actor监督wall／含launch wall | 33.262622487／34.694649234 s；含hash/读取/资格/保存 |
| 装配／LU／gecon | 1.592389774／3.324998309／0.537647051 s，嵌套于actor |
| 只读factor hash/reload／9次联合solve | 5.835275504／0.967400231 s，嵌套，不能再累加到actor |
| 两状态诊断／其中薄代数 | 0.554751218／0.775724874 s；薄代数合0.008964091 s，仍嵌套 |
| 原S／SH、联合LU与pass | 14／2，总16≤64；联合solve9≤16，显式L/U pass18≤32，gecon未知保守22，总上界40≤54 |
| factor reader／9列分解流程 | 1≤2／2≤2；旧八LU读取及旧方向原8探测均0 |
| 40端口LU／LAPACK solve | 1／16调用≤128；其中一个矩阵RHS有3888列，全部调用合3903 RHS列，不能称16次单向量解；维度和时间明列 |
| A_J+LU数组载荷／同时规划 | 483,729,408 B／4,621,269,504 B（约4.30GiB，derived非RSS）；pivot、oldA5/A7、packet/hash/LAPACK及薄阵另计 |
| 整树同时采样峰／ownswap／VRAM/OOC | 1,625,231,360 B（1.513615GiB）／0／0；无Torch/GPU；0.5s采样，不冒充连续kernel硬限额 |
| 初步CPU／正式CPU | 先probe CPU0，launch现场重选CPU16（socket0/core20/sibling16）；以实际命令／baseline为准，MPI1、实际BLAS1、Loader0、自身nice10/I/O idle |
| 有监督辅助wall | 23.338665920 s；数值加辅助56.601288407 s≤900；最终以成本/交付回执观察为准，各stage不清零 |
| 新artifact／含TMP等先期输出 | 486,889,685 B／500,265,882 B；最终库存另核，均受768MiB；全Task artifacts约18.025GB≤20GiB |
| 系统与存储 | 启动MemAvailable1,830,200,459,264B，系统reserve216,310,038,528B＋邻增长137,438,953,472B；磁盘余量约3.391TB≥50GiB；cgroup无delegation、PSI full avg10=0 |

UTC start为2026-10-03T00:39:41Z，heavy-stop02:24:41Z、总deadline02:39:41Z；monotonic起点是首次UTC与随后配对读数的保守对齐，不冒称同时采样。未刷新窗口，求解队列01:00:28Z写minimum result/cost/response后closed，后代已清场；仅继续低负载证据收尾。新stage/提交/交付前重读实际钟，最终时刻见回执。

原自有锁、整树RSS warn12/hard16GiB sampled停止、ownswap0、PSI/系统reserve/邻增长余量保持；无可写delegated cgroup，不伪称内核连续硬限额。正式准入在主机视图进行；辅助小测试的沙箱PID视图不冒充全邻任务扫描。没有资源停止／重入，邻任务未操作；缺少可比邻阶段指标，因果影响INCONCLUSIVE，不能宣称绝对零干扰或无争用加速。

formal研发下界从77,128.294516增至77,161.557139 s，仅增加本actor；历史辅助及每个暖解完整lineage费用unknown保留，不是一个成功解的耗时。理想替换旧5/7的A+LU净增236,989,440B、稠密LU立方比约3.77，仅为derived存储／复杂度，不代替本诊断实际新增483,729,408B及设置/全程计时。[完整费用](outcomes/records/resource_costs_v26.json)不重复累计嵌套计时。

本批没有新原方程/native/FE恢复/E/H/curl/复通道/RTA场资格，不生成official结果；V24仍0/5，V23仍0/6，旧负结果不改写。无合格非神经与神经完整N=1成本配对，NN20%仍NOT_DEMONSTRATED；不以传统LU/QR/固定特征归功于训练。原尺寸非可分三维解、离散精度、2e12B（与TiB分开）/48h完整端到端、fresh池均NOT_QUALIFIED/NOT_RUN，不自动最大模型或新p4参考。

两项辅助准备修复D01/D02均无正式actor或原作用重放：错误辅助window文件名改为本批固定window；缺失threadpoolctl改用既有ctypes BLAS getter，不安装环境。另有未提交预登记额外SHA清理、裸Python探针失败、收尾JSON脚本草稿语法纠正，全部原状／成本口径在[失败记录](outcomes/records/failures_and_not_run_v26.json)单列；数值修复/重放0，未通过新分解重试救场。未知单项费用保持unknown并已进入总elapsed。

正式源码前94 focused通过（3.89s），包含§3固定三样本19项库存／命名边界回归以及复数主块/贡献/非互伴40port/正反作用/秩亏零向量/只读pivot/容量/预算/默认/新dat注册等；早期86为其中子集，不相加。冻结后缓存checker14项（0.78s）通过，108为两个不重叠测试scope；actor source不因后继checker/文档变化重新计算。另外12项仓库治理/模型总账文档回归通过（0.07s），不与上述scope混淆。compileall及clean源码dat validate通过；Ruff未安装NOT_RUN，full pytest/MPI2/4/CI/PDE/训练按范围未运行，不声称CI。

GitHub精确review页Cache miss，无视觉证据，NOT_VERIFIED；本地fenced math/表格列数/链接另检，不擅改review。全部授权路径完成已closed，只提交本执行分支；运行source与文档HEAD分开，发布/清场回执绑定最终Git观察。完成推送即等待review，不merge、不启动下一提案。

## 唯一下一建议

仅建议下一review审查一个**跨界回流方向**的有界资格诊断，不实施。联合局部解把误差推到J外；提案先用外域已有六块解处理这一泄漏，再回到J补偿反作用，改变通信顺序而不扩大联合块：

```math
J(r)=E_J^H A_J^{-1}E_Jr,\qquad
L_O(r)=\sum_{b\in\{0,1,2,3,4,6\}}E_b^H A_b^{-1}E_br,
```

```math
w=L_O(A\,J(r)),\qquad
B_{\rm return}(r)=J(r)-w+J(A\,w).
```

这与仅用原J主子块的方向不同，仍是固定线性作用、无训练或参考。提案每残差2次原A、2次已有联合solve、6次旧外域solve；只读复用既有因子，不新增LU，外域factor逐块流式加载。最大旧外域单LU的derived数组载荷16×2913²=135,769,104B，另计读盘/hash及原packet与J因子；完整峰先另审≤8GiB，端到端成本unknown。可证伪条件仍是同两个冷残差、同旧八方向基线，新增方向可分辨且两者g≤0.75；否则关闭，不追加迭代/训练/块对。需要新review批准读取、计数和数据边界，**本批未运行该提案**。
