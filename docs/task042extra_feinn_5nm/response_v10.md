# Response V10：等价导数加速通过，完整GN与条件表示诊断已执行

本轮A–E授权矩阵已执行。完整导数复用与包含建立/释放的加速通过；两条C仍未求准原p3。plain正常预算冻结，phase因两次系统压力停止后保全最后完整状态，停止原因与保存状态的精度分开报告。条件D已独立完成；全部候选功率仅为diagnostic。

| 身份 | 准确值 |
|---|---|
| branch / 显式tracking | task42extra_feinn_5nm / refs/remotes/origin/task42extra_feinn_5nm |
| Review V9发布 / 审阅基线 | 47317bb648d5e2237657f8b6c75c239ab5bf55c5 / 0277bddd50c910fb3b04fa276191872776728942 |
| 原冻结base | fbac3d8777fcfd897d93b898cb9f460f79ddd6ff |
| canonical common Git | /home/fenics/Projects/Maxwell3D-Lab/task-repository.git |
| linked worktree / 环境 | /home/fenics/Projects/NN-Lab-V2；工作站原生Linux；独立qualified FE/ML activation |
| 数值source / 文档HEAD | 043资格、902性能、acdd plain/phase首段、5cda phase恢复、ca0c资源导出与C/D独立审核；完整SHA见run index；最终交付HEAD另在回复报告 |
| production / master merge | false / NOT_APPROVED |

## 实际结果与方法边界

缓存保留同一参数处的隐藏激活，使完整参数方向导数少做重复前向。代价约1.10GiB缓存和建立/释放；保持原网络、完整边/面/内部矩、原A/f/G、q15、loss与GN接受规则。它是工程加速，不是新预条件器或条件数改善证据。一次outer包括内层K和真实trial，不是epoch；本轮不重做Adam，也不从best/last_trial回放。

下表的原残差表示计算场还差多少才能满足原方程，1表示差值仍相当于完整载荷；场相对误差0.36表示误差约为准确参考散射场范数的36%。散射场是相对于已知背景的变化，总场等于背景加散射场；curl衡量场的空间旋转变化并对应磁场H。E_G同时度量电场幅值和curl误差，不能用背景占主导的总场误差替代散射误差。

| 固定V9终态 | 旧总工作中位数s | 缓存总工作中位数s | 含建立/释放加速 | 完整proposal成本Gate | 准入 |
| --- | --- | --- | --- | --- | --- |
| plain_gn | 137.98991387 | 94.42319538 | 1.4613984765 | true | true |
| phase_gn | 136.49640561 | 88.444040504 | 1.543308117 | true | true |
| plain_fit_gn | 123.85393964 | 80.953429926 | 1.529940606 | true | true |
| phase_fit_gn | 129.83995715 | 82.604037084 | 1.5718354905 | true | true |

| 路线，相对原p3参考 | native | augmented | 散射E L2 | 散射curl/H | E_G | 独立能量闭合 | 分类 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| V10-PLAIN-CACHED-GN-CONTINUE | 1.0154347975 | 1.0154347975 | 0.99888849996 | 0.99890594486 | 0.99890551512 | 0.41593547468 | PDE_OPTIMIZATION_NEGATIVE |
| V10-PHASE-CACHED-GN-CONTINUE | 0.97882119863 | 0.97882119863 | 0.36201788027 | 0.36263373418 | 0.36261857554 | 0.092747748293 | PDE_OPTIMIZATION_NEGATIVE |
| V9-PLAIN-DAMPED-GN | 1.0285051156 | 1.0285051156 | 0.9989232163 | 0.9989423061 | 0.99894183584 | 0.4157492147 | PDE_OPTIMIZATION_NEGATIVE |
| V9-PHASE-DAMPED-GN | 1.0187461988 | 1.0187461988 | 0.43715907484 | 0.43778332738 | 0.43776795997 | 0.12094192809 | PDE_OPTIMIZATION_NEGATIVE |
| V10-PLAIN-CACHED-FIT-GN-CONTINUE | 6.9238228453 | 6.9238228453 | 0.035964629101 | 0.048041839362 | 0.047781012309 | 0.0074739007987 | REPRESENTATION_OR_FIT_OPTIMIZATION_UNRESOLVED |
| V10-PHASE-CACHED-FIT-GN-CONTINUE | 0.53147218171 | 0.53147218171 | 0.0095579252068 | 0.010034208799 | 0.010022747742 | 9.4658158489e-05 | REPRESENTATION_OR_FIT_OPTIMIZATION_UNRESOLVED |
| V9-PLAIN-FIT-GN-DIAGNOSTIC | 11.001030573 | 11.001030573 | 0.068217087643 | 0.1000521103 | 0.09939045116 | 0.014917309507 | REPRESENTATION_OR_FIT_OPTIMIZATION_UNRESOLVED |
| V9-PHASE-FIT-GN-DIAGNOSTIC | 0.8082166866 | 0.8082166866 | 0.014403534682 | 0.013024032447 | 0.013059766413 | 0.0028868109962 | REPRESENTATION_OR_FIT_OPTIMIZATION_UNRESOLVED |

两条C未取得同p3严格资格或联合10倍研究信号；phase的部分场改善花费额外时间且受系统压力中断，不能称同成本算法优势。C plain新增14完整接受、phase新增21，均保留全部8966实参数和31968独立复FE及40端口。条件D plain/phase新增10/7接受，监督G/L2/curl分别为0.04778101231/0.03596462910/0.04804183936和0.01002274774/0.00955792521/0.01003420880：phase G/curl仍高于1%门限，不能舍入判部分表示通过，也不能证明网络不可表达。神经增量仍NOT_QUALIFIED。完整功率、通道、区域、CG真残差、pred/ared/eta和未提交工作见[续算结果](outcomes/cached_gn_v10.md)、[对照](outcomes/records/comparison_v10.json)、[内层聚合](outcomes/records/inner_summary_v10.json)和[外层CSV](outcomes/records/accepted_steps_v10.csv)。

## 自主修复、保全和独立验算

保留两个未通过完整proposal的导数版本，定位原Torch AD线性层bias-first和相位左右乘的浮点累加顺序后，充分预算下两个C方向/pred/ared逐位一致。初始保存重复metadata字段在尚无新GN工作时修复，失败157.159796420s保留；没有刷新路线额度。

phase首次PSI停止后只恢复自身完整V10 PT/GN/RNG，继承已耗时间、24个未提交K和1梯度，并预留未完成作用额度；第二次PSI停止后不再训练。保存第75完整边界的PT SHA256 cf6919a8ee86e32ad7f0f4b0d4ef8411061b149c564dd289237334f90b7d9e86完全不改；独立导出NPZ并核对完整c逐位一致，原参数source5cda与export sourceca0c分开。第二次停止前又有21K+1梯度未提交，费用保留。系统压力来源未确定，自身swap0；不写OOM、正常预算停滞或网络数学不可表示。

两类实际终态冻结后独立ML q15/q30重建、FE compare-only只读原p3参考，无新MUMPS symbolic/numeric/solve。C始终reference/features=false、PDE-only=true；D始终reference/features=true、PDE-only/official/production=false，权重/标签不反馈C、Task042或0.7nm。严格物理、监督表示、GN研究与缓存性能由原字段分别重算。

完整failure→hypothesis→change→test→retry见[repair log](outcomes/records/repair_log_v10.json)，source/输入/所有attempt见[run index](outcomes/records/run_index_v10.json)。定向tests、Ruff/compile、FE Torch隔离和文档检查见[test summary](outcomes/test_summary.md)；未full pytest、未安装、未声明CI。

## 资源、剩余边界与下一步

本页数据冻结时新增全账37417.194589828s，旧账99864.4864455976s和失联3284s及所有重放费用完整保留，累计137281.681035426s。后续浏览器与最终检查继续追加[完整资源账](outcomes/records/resource_costs_v10.json)，不把本页快照冒充最终闭账。

| 子包 | 完整新增实测/保守尾段秒 | 预登记限额秒 |
| --- | --- | --- |
| A | 16.1195113 | 150 |
| B | 16589.349215 | 17050 |
| C | 13551.506396 | 17200 |
| D | 6765.5812557 | 7200 |
| E | 494.63821207 | 1600 |

工程资格耗时较长，运行前已登记预算转移为A150/B17050/C17200/D7200/E1600，总额43200s，E始终预留至少1200s。C公平新增上限各8600s，全部失败/恢复墙钟都从该路线扣除；D各3600s。历史前缀只在逻辑路径归属一次，不在全项目账重收费。未用C额度未变成第三次phase启动。

全过程CPU-only/MPI1/数学及Torch线程1，现场选择空闲物理核，数值warn12/hard16GiB，factor规划12GiB，新增detached缓存≤2GiB，轻检查/浏览器≤2GiB，自身swap/OOC0。启动保留max(128GiB,10%有效总量)系统余量、384GiB邻增长及自身预算。约0.5s树采样不冒称连续内核限额；tmux管理快照另列，未修改其他项目或共享环境。

本轮结束“只靠等价加速再加时间继续原GN”的尝试。唯一下一轮建议是一次有界、无标签的参数尺度与阻尼诊断：在冻结phase C状态记录同一K的方向曲率、mu所占比例及逐层更新尺度，并配对预测/真实下降。依据是C plain内层CG中位68步、真线性残差中位0.00955，phase中位28步/0.00834，但最终原方程仍近1，接受步也可能增加native；内层解得较准不能保证真正的场改善。建议未来授权上限20分钟、32次K和4次真实目标试探，保留120秒保存窗口；本批只写设计、不执行，不新增loss/PC/训练或改参数尺度，不声称已证明条件数是唯一根因。完整矩、原A/f/G和严格物理验收仍是基准。目标尺寸5nm/0.7nm、p6、h和端口扩展不启动。

新review及关键新页的实际GitHub DOM/截图抽查见[渲染记录](outcomes/records/render_check_v10.json)，结构解析不替代浏览器视觉。只推本执行分支，最终准确HEAD、tracking/ahead-behind、clean和自有进程/锁清场在交付回复核报；不amend/强推/merge，停止等待review。

实际Review V9的6张表、2处公式已取得DOM，标题/准入表/两处公式截图目视正常。访问已发布Response V10时GitHub返回“Unicorn”服务错误页，截图和费用保留；新页整体视觉验收为RENDERED_VIEW_BLOCKED，其余两页未取得正文，不宣称通过。
