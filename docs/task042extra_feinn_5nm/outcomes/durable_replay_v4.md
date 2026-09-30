# Task42extra V4：保全阶段边界的监督场拟合

| 范围 / 证据性质 | 结论 |
| --- | --- |
| R0自身小问题与M5资格 / measured | 保存、加载、真实线搜索异常、原子写入中断、模拟启动端断开和监督死亡清场通过；M5仅2次loss/gradient，Adam500→fresh L-BFGS资格通过 |
| R1 / measured | 唯一正式重放，2129完整闭包、93完整外层step；WALL_BUDGET回滚并冻结2122闭包处参数及匹配optimizer |
| R2 / measured | 完整参数→c相对差0；q30/q15差8.5141e-13；独立FE compare-only完成，新参考solve为0 |
| 表示 / derived | 三项误差0.0138717/0.0132512/0.0138870均高于部分门限0.01，`REPRESENTATION_OR_FIT_OPTIMIZATION_UNRESOLVED` |
| 严格物理 / derived | native/augmented1.60884、场/通道超1e-4、功率/能量超限；不能成为official解 |
| 执行预算偏差 / measured | 总wall小于3h，C1遗漏导入导致≥120s保存留白未满足；C2已最小修正及测试，未第二次正式运行 |

这次研究回答的是“能否取得并复验完整的已知场拟合终态”。网络读取V1准确散射系数作为标签，调参数让自身完整有限元场接近它。收益是把表示诊断从丢失参数的日志，推进到可逐项复验的固定终态；代价是约三小时重复后段、存盘和独立审核。它没有独立从方程求解，不能用作原路线或目标模型的训练初值。[Response V4](../response_v4.md)、[机器Gate](records/gate_decisions_v4.json)、[同口径CSV](records/representation_comparison_v4.csv)是本页的证据入口。

## 固定物理、目标和源身份

M5仍是真空波长5nm、Si/air三维空气缺口，h1.25nm、384hex、p3/q15、双Floquet和原完整Fourier-DtN；native34050、slave2082、独立复FE31968，其中边3744、面14400、内部13824，端口40。网络3→64→64→64→6 tanh、FP64、8966实参数、seed421001初始化血缘不变，输入中心/半宽归一化与全部矩均原样。网络输出为散射E；已知layered背景只在原仿射换元和total后处理使用。

目标把电场误差及其旋度误差放进同一个正定内积G，避免把不同FE系数的数值大小直接当同尺度误差。G已经施加原MPC，ell=5nm；它不是Maxwell矩阵。

```math
e=c(\theta)-c_{\rm ref},\qquad
d_{\rm ref}=c_{\rm ref}^*Gc_{\rm ref},\qquad
J_{\rm fit}=\frac{e^*Ge}{2d_{\rm ref}},\qquad
g_c=\frac{Ge}{d_{\rm ref}},\qquad E_G=\sqrt{2J_{\rm fit}}.
```

每个fit闭包只做完整矩的网络前向、G matvec和完整矩VJP，把系数梯度回传至全部网络参数。它不调用A/Aᴴ、Gsolve、Gram factor或Maxwell逆。23次原方程审核另计，没有把审核成本隐藏在“闭包没有A”的陈述中。

| 冻结文件 / source | SHA256或完整SHA |
| --- | --- |
| Adam500 NPZ | `4e818a16b876ffd0776e74438654ca7de5632b1e17269a38e87749b5b3ad6a97` |
| 原native packet | `2dbd60267758c2c53ea62a722ee0b07fad16f3cfae3f772bb0ba4830f4e28215` |
| MPC后全局稀疏G | `2c984449248c02f01f4a41a681d00015bbe779add0ef30f0141d9eccf75b01c9` |
| q15完整矩 | `0260c986bc7a71d6b8d6b0b695df4ca730d24654f5ad0705313a45205c28b69e` |
| V1准确散射master标签 | `0c3c0574a8c1eddcadfb56268e00c08e55d5cb15d44c0c76e873fcea0c467ff7` |
| 材料表 | `55aa34e55c5e3cc35f6849eddbd3bcc72d3b694d32bc4885299ef373acd676a2` |
| R0 / R1 source | `538c6320679d9a3ce3efe5e6d6ebef062963f601` |
| R2 source | `c8a057a46645542aaa17a38b78e64c6add80cb68` |
| final参数/c NPZ | `e33a2c9eafb50639a36555e159895d62617feda7e4831238a7868887700f9363` |
| final完整优化检查点 | `e09b94364837bdb72714f7c229d19993836072dd035c85249bfc19376a44a790` |

master顺序、背景、mesh/tags/modes、qualified buffers与参数顺序另外绑定在 [run index](records/run_index_v4.json)、原始manifest和 [checkpoint index](records/checkpoint_index_v4.json)。V1同p3准确参考是best available discrete reference，不是连续极限；本轮不重新建立参考MUMPS symbolic/numeric/solve、全局Maxwell CSR或因子。

## 为什么这次边界可以重放

旧V3只留下zero和Adam500参数，未保留其Adam动量或L-BFGS历史。第817次只有scalar log，第825次也是已观察下界；两者都不能作为恢复点。旧源码的保存顺序却能证明Adam500文件在fresh L-BFGS创建之前写入。因此仅这个切换边界可加载参数并创建原配置的空历史L-BFGS，完全不再调用Adam。

R0复用了已资格化的native/G/矩/环境证据，比较了相同未更新Adam500模型上的克隆FitMetric与原目标、梯度；配对相对差全部0、E_G=0.20082113406866917、native=14.263463207213235。原NPZ未存buffers；从冻结几何和不变构造器确定性重建center/half_width，再通过完整c及梯度校验，才保存资格化边界。并未补造旧buffer字节或旧optimizer。小问题测试才承担完整state保存/加载后的短程等价验证，真实M5没有为了补历史继续训练。

## 保全协议及故障实测

launcher、subreaper watchdog和worker在一个任务独立tmux会话中运行。独占任务数值锁、保存PID/start_ticks/session/process group、输出文件和cgroup身份；worker没有离开监督树。父进程死亡保护避免持续无监督负载。tmux服务管理内存在数值树外单列，未把服务缓存算成worker树峰，也不声称可以逃过平台回收策略。

外层step正常返回后先生成完整state快照，计算真实theta_after−theta_before，再同步写临时文件→flush/fsync→原子替换→目录fsync→原子指针。随后才发布committed行并继续下一step。闭包异常恢复完整模型、梯度、buffers、optimizer及RNG。试探参数与c单独保存为not_committed，不参与物理终态审核。最后两代和阶段/审核/最终固定点保留；非固定中间代删除只发生在新指针已经完整发布后。

| 自身小问题 / measured | 实际检查 | 结果与限制 |
| --- | --- | --- |
| 保存/加载等价 | 复数loss、模型＋optimizer＋梯度/RNG，后续步骤相对/绝对1e-12规则 | 通过；不是任意外部checkpoint可恢复的授权 |
| Adam→fresh L-BFGS | 连续切换与参数保存后重建fresh optimizer比较 | 通过；不能恢复丢失的817历史 |
| 原子写入中断 | 自身子进程临时文件fsync后、replace前SIGKILL | 上一代hash可读；未承诺所有磁盘硬件故障模式 |
| 实际strong-Wolfe异常 | 非零试探时RuntimeError/预算异常 | 参数和匹配optimizer回滚；费用保留 |
| 启动端退出/关闭管道 | 短启动端退出，完整受监督dummy由任务tmux承载 | 正常完成；只是模拟断开，未覆盖全部客户端/cgroup回收路径 |
| 明确停止 / 监督失效 | USER_CONTROLLED_STOP、MONITORING_FAILED、监督SIGKILL | 自身worker清场、checkpoint可读；监督SIGKILL无summary，不伪造finally |

原9项定向tests与四类进程案例的hash在 [durability checks](records/durability_checks_v4.json)。计时与标签修正后11项通过，原子写入、事务及接口不做full pytest重验。实际正式段每个完整外层step都有完整检查点登记，最终PT与上一完整边界的模型/optimizer/梯度/RNG逐项一致；参数到冻结NPZ和独立q15系数一致。SIGKILL保证仅指已成功落盘的上一完整边界，不保证final文件或summary一定执行。

## 工作量、接受更新与停止预算

闭包是一次完整目标和梯度计算，L-BFGS可为一个外层step调用多次闭包选择步长；没有按数据epoch计时。原配置lr1/history20/strong-Wolfe/max_iter20/max_eval25/tolerance_grad1e-7/tolerance_change1e-9未改。

| 工作量 / measured | 数值 | 分类 |
| --- | ---: | --- |
| inherited_committed_Adam_updates / 新Adam | 500 / 0 | 特定阶段锚点，非从零重训 |
| new_complete_fit_closures | 2129 | 新段≤3500，含未提交试探 |
| logical_path_closures | 2629 | 500＋新段评价数，非提交计数 |
| committed_complete_fit_closures | 2122 | 最后完整外层边界；final复制此参数/optimizer |
| 完整外层step / 内层迭代 | 93 / 1859 | 94th外层尝试预算回滚 |
| native审核 | 23 | 锚点、跨100闭包审核和final，≤40 |
| 旧观察＋新增拟合闭包下界 | 2954 | 旧≥825＋新2129；不删除旧500之后重复成本 |

接受更新在step返回后测量，最近完整step的norm为0.01503083458，相对增量0.001474149259；final本身没有新的接受更新。[审核历史CSV](records/durable_audits_v4.csv)记录checkpoint/计数/E_G/native一一对应。scalar loss总体下降而native并不单调，不能只挑loss下降行当物理改善。

正常预算收口保存终态，stop_reason=WALL_BUDGET，failure=null。C1的内部120s预留从run_replay入口算起，漏计import/prelaunch，实际预算留白不符合review。总launcher→summary10690.4132748s、监督10688.7017356s、routine10683.1157621s三种口径分列；结束后的余量是109.5867252/111.2982644s，不用它们伪造收口前留白。原计划外部预算请求在内部已经结束后未执行，没有发SIGTERM、没有重启。C2把时钟起点移至launcher并留150s，计时测试通过，但此修正没有新的正式运行资格证据。

## 完整场、原方程与功率

所有相对差都使用各自原参考范数；既不拟合整体复相位，也不临时改近零分母。G误差同时保存分子/分母，区域误差保存原集合ID/hash、绝对误差和参考分母。total和scattered的差场相同，参考范数不同，因此total数字更小不是散射更准确。

| 完整FE场 / measured | V4 final | 严格门限 |
| --- | ---: | --- |
| G场误差 | 0.0138716912975 | 表示三项≤0.001正 / ≤0.01部分，均不满足 |
| scattered E L2 / scaled-curl | 0.0132512476647 / 0.0138870027008 | 各≤1e-4 |
| total E L2 / scaled-curl | 0.00908709789134 / 0.00949580596642 | 各≤1e-4 |
| 六点total E / H_code | 0.00975197801709 / 0.00716738817286 | 总向量及逐点各≤1e-4 |
| 六点scattered E / H_code | 0.0144133908755 / 0.0106715966193 | 各≤1e-4 |
| native / augmented | 1.60884472011 / 1.60884472011 | 各≤1e-6 |
| total增广 / 独立DOLFINx total原方程 | 0.762112577426 / 0.762112577426 | 各≤1e-6 |
| port绝对 / full-RHS相对 / operation相对 | 9.15689e-16 / 3.14624e-15 / 2.67438e-17 | 两相对量≤1e-6，通过 |
| slave存储 / 参数→c / q30→q15 | 0 / 0 / 8.51407e-13 | 通过原存储与≤1e-12/≤1e-8身份/求积要求 |

H_code由原curl E/(i k0 μ_r)给出，μ_r=1，所以完整H的相对L2误差等于相应curl相对误差；六点仍独立存完整复H_code。这里物理scaled-curl用1/k0归一化，G用ell=5nm，不能把这两个范数混用。原场/通道误差以及各点的absolute/denominator/relative全部见 [Gate JSON](records/gate_decisions_v4.json)。

| 原40级有序复向量 / measured | 绝对差 | 实际参考分母 | 相对差 |
| --- | ---: | ---: | ---: |
| 原total端口系数 | 0.00935354178038 | 0.438234233940 | 0.0213437040194 |
| 真出射复幅 | 0.00935354178038 | 0.913080171052 | 0.0102439436064 |
| 真出射幅移至原边界位置 | 0.00894739848958 | 0.909518121497 | 0.00983751535907 |
| scattered端口系数 | 0.00935354178038 | 0.246835952279 | 0.0378937577530 |

原total系数包含原双向端口变量；真出射按冻结入射投影去除入射，boundary出射再按原边界相位换位置；散射用原背景仿射变量。各自40维复向量和功率在Gate里完整保留，原mode inventory/hash绑定顺序；总、出射、散射不能共用一个分母或表头。四项均未通过1e-4。

| 功率 / measured、无量纲 | 同p3参考 | V4 final diagnostic | 绝对差 / 限值 |
| --- | ---: | ---: | --- |
| R_total | 0.812426499057 | 0.813057790084 | 0.000631291027 / 1e-5 |
| T_total | 0.0324623960953 | 0.0327381741782 | 0.000275778083 / 1e-5 |
| A_balance | 0.155111104848 | 0.154204035738 | 0.000907069110 / 1e-5 |
| A_volume | 0.155111104847 | 0.155388025694 | 0.000276920847 / 1e-5 |
| R00_s / R00_p / R00_total | 0.812256818464 / 1.25634e-26 / 0.812256818464 | 0.812608163311 / 5.02696e-5 / 0.812658432870 | 分极化保留 |
| abs(R+T+A_volume−1) | 约2.98e-13 | 0.00118398995593 | ≤1e-5，失败 |
| 最大逐通道功率绝对差 | reference | 0.000351344847336 | ≤1e-6，失败 |

A_balance=1−R−T，由定义闭合，不能作为独立能量通过；体吸收独立积分A_volume与它相差0.00118398995593。同p3准确参考自身原残差/能量资格通过，不能替代候选资格。

| 原区域集合 / measured | cell数 | scattered E L2相对差 | scaled-curl相对差 |
| --- | ---: | ---: | ---: |
| air | 200 | 0.0132173167568 | 0.0140329902131 |
| substrate | 48 | 0.0196670357518 | 0.0238319857685 |
| grating | 136 | 0.0120628054042 | 0.0114107482194 |
| interface-near | 264 | 0.0139673775797 | 0.0140481219144 |

interface-near与三个材料集合重叠，不能将四行误差相加。substrate的相对误差更大仅是本终态观测，不单独证明材料界面是唯一根因。

## 资源全账及结论边界

| 本轮阶段 / measured | 监督wall / s | launcher→summary计费 / s | 同时整树RSS峰 / B |
| --- | ---: | ---: | ---: |
| R0 M5边界 | 15.8439320 | 22.0154352 | 533176320 |
| R1唯一后段 | 10688.7017356 | 10690.4132748 | 764751872 |
| R2 ML完整矩q15/q30 | 17.5169616 | 19.3154006 | 523923456 |
| R2 FE独立compare-only | 18.1646247 | 20.0003183 | 584249344 |

本页冻结数值时资源快照10934.6917s，含aux及120s直接/最终保守计费；后续checker、文档/浏览器和尾段在 [最终资源账](records/resource_costs_v4.json)继续追加。旧累计33070.52670758043s及失联3284s保留，不用新重放删除旧费用。各阶段取supervised与derived launcher wall的较大者，G/VJP/存盘等嵌套timer不重复加到父wall。数值树峰0.71223GiB，自身swap全采样0；所有资源性能标shared-workstation。

G的31968行、7336179 NNZ、CSR payload146851456B沿用；本轮factor/solve0，2154次G matvec95.4165s、存盘3.8402s、保留checkpoint payload88078236B，全部包含于R1监督时间/RSS。网络前向、moment map、VJP计时分别4569.931/1132.652/4799.563s；它们是内部计时，不同于研究总账。历史`RESEARCH_ONLY_GLOBAL_RIESZ_FACTOR`setup/solve费仍在V1–V3账，不能把整个研究说成没有辅助全局因子。

CPU12在各次准入现场选择；原生Linux、CPU-only、MPI1、数学及Torch线程1、DataLoader0。numeric warn12/hard16GiB、轻测试/浏览器≤2GiB、自己的swap0；无cgroup委派，约0.5s同时进程树RSS采样，不称连续内核限额。保留system reserve=max(128GiB,10%)、至少384GiB邻任务增长和自身预算；磁盘与artifact Gate通过。tmux服务在数值树外的样本RSS/VmHWM4702208B、swap0仅说明该次观测，不是全过程上界。未调整邻任务或全机配置，不能证明完全零干扰。

`reference_used_for_training=true`、`pde_only_solve=false`、`production_initialization_allowed=false`、`pde_only_solver_qualified=false`、`official_candidate_results=false`在manifest/checkpoint/results一致。checkpoint保全、完整插值身份和求积漂移已取得实证；固定表示与有限预算优化仍混在一起，严格物理解未取得，神经增量未证明。旧V1/V2结果、旧V3中断、p4实际not_run和目标尺寸5nm/0.7nm not_run不改。

下一步仅建议review这个完整终态和保存留白偏差，另审一项能够区分表示与优化的最小诊断；不自动改网络、优化器、PC、求积或扩模型。新review及必要V4页的实际GitHub渲染以 [独立记录](records/render_check_v4.json)为准。选择性合并依赖组及禁止生产默认见 [changed_files](changed_files.md)；本分支不merge，提交推送后停止等待review。
