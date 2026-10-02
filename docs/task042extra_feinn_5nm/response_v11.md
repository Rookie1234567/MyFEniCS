# Response V11：固定参数度量诊断和唯一短对照

A/B及唯一一对C已执行，实际终态已冻结并独立复验。分组度量接口通过，研究分类为`NO_USEFUL_METRIC_GAIN`；严格求解资格按原方程、场及功率分别判定。缓存加速资格保留，不能当作求解收敛。本批无监督D、无新增参考求解。

本轮比较网络权重/偏置的步长尺度。原阻尼对各参数施加同一种步长限制；固定八组度量按方向曲率改变限制，但仍求同一Maxwell方程、使用同一Riesz对偶目标。额外代价是26次公共曲率诊断、资格检查，以及每条独立Gram准备。原残差1表示误差仍相当于原载荷；散射场相对误差0.36表示误差约为参考散射场范数的36%。curl描述场的空间旋转并对应磁场H，E_G综合电场与curl；各指标越低越好，但必须同时通过门限。

| 身份 | 准确值 |
| --- | --- |
| branch / tracking | task42extra_feinn_5nm / refs/remotes/origin/task42extra_feinn_5nm |
| Review V10发布 / 审阅基线 | 13ca73756a4c74bd24ad5241d97a810bfcce6971 / c35fb5714e81736a5fe5e4f90159f4dacaf4b2a9 |
| 原base | fbac3d8777fcfd897d93b898cb9f460f79ddd6ff |
| canonical / linked worktree | /home/fenics/Projects/Maxwell3D-Lab/task-repository.git / /home/fenics/Projects/NN-Lab-V2 |
| 执行环境 | 工作站原生Linux；独立qualified FE/ML activation |
| C actual source | 0f7ad43cb3e6a6f11e2b3f8b884a9d47f0f70524 |
| 最终文档HEAD | 交付回复另核报；不冒充运行source |
| production / merge | false / NOT_APPROVED |

## 实际结果与精度边界

| 路线，相对原V1同p3参考 | native | augmented | 散射E L2 | 散射curl/H | E_G | 能量闭合 |
| --- | --- | --- | --- | --- | --- | --- |
| V10-PHASE-CACHED-GN-CONTINUE | 0.978821198632 | 0.978821198632 | 0.362017880269 | 0.362633734179 | 0.36261857554 | 0.0927477482932 |
| V11-PHASE-IDENTITY-METRIC-CONTROL | 0.984363547288 | 0.984363547288 | 0.15960198092 | 0.160305545482 | 0.160288250677 | 0.0293262887055 |
| V11-PHASE-BLOCK-METRIC | 0.846541904928 | 0.846541904928 | 0.122944519716 | 0.123039105854 | 0.123036776653 | 0.0492282322929 |

| 路线，功率均diagnostic | R | T | A_balance | A_volume | R00_s | R00_p | R00_total |
| --- | --- | --- | --- | --- | --- | --- | --- |
| V10-PHASE-CACHED-GN-CONTINUE | 0.794315997762 | 0.0513415797058 | 0.154342422532 | 0.247090170825 | 0.794296464658 | 4.64479356959e-07 | 0.794296929137 |
| V11-PHASE-IDENTITY-METRIC-CONTROL | 0.798616960425 | 0.0385522797318 | 0.162830759843 | 0.192157048548 | 0.798574485565 | 6.36199208866e-07 | 0.798575121764 |
| V11-PHASE-BLOCK-METRIC | 0.795461317421 | 0.0250470810956 | 0.179491601483 | 0.13026336919 | 0.795391017878 | 1.98764166035e-06 | 0.79539300552 |

| 路线 | 新增接受 | K | JVP | VJP | 真实试探 | 拒绝 | 完整新增s | 树峰GiB | 停止原因 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| V11-PHASE-IDENTITY-METRIC-CONTROL | 24 | 930 | 930 | 954 | 34 | 10 | 5225.489258 | 2.83142471313 | GRADIENT_START_SAVE_RESERVE |
| V11-PHASE-BLOCK-METRIC | 20 | 991 | 991 | 1012 | 31 | 11 | 5219.37018731 | 2.39972305298 | BUDGET_FRONTIER_CG_RESERVE |

两条从完全相同的无标签phase75参数/buffers/mu0/h0/GN/RNG分叉，不重做Adam、不使用旧D/监督权重或p4/p5标签，不使用best/last_trial。全部8966实参数和31968独立复FE/40端口保留；两条共同关闭PC后备，唯一组间差异为固定M。每接受步先fsync原子持久化匹配状态，再公布committed审核。

严格native/augmented/原total≤1e-6、场/复通道≤1e-4、功率/能量≤1e-5、逐级功率≤1e-6、MPC≤1e-10、q15/q30≤1e-8不变。研究信号还要求M的native/augmented都≤0.1倍起点且≤0.5倍control，散射L2/curl均≤0.1且优于control。只降loss、加快CG或局部几个百分点不满足。所有未通过原方程Gate的功率均diagnostic，不能作official结果。

## 诊断、资格与有据修复

固定度量的收益有具体边界：共同新增20步时，散射E/curl误差由控制的0.244415/0.245047降到0.122945/0.123039；但度量终态native只比起点降低约13.5%，不是研究信号要求的90%。固定60分钟实际态的散射误差约0.0933，随后终态回到0.122945；它是预定对照点，不能拿它替换实际终态或作为下一轮best初值。最终控制场误差为0.159602，能量闭合0.0293263；度量场误差0.122945，能量闭合0.0492282。场更接近参考，并不保证功率或原方程同时更准确。

真实参数重建相对差为0，q15/q30漂移约1.6e-15；这是插值/回写通过。共享代码中的 `numerical_reconstruction_pass=false` 表示完整方程、场与功率联合检查未过，不能解释为参数重建失败。独立原total残差为控制0.466295、度量0.401008，均高于1e-6。

A的八组曲率跨度为2226255.7581，Riesz/欧氏梯度余弦为0.0551021932917；M试探支持一次短对照，A不提交更新。三随机方向/组只是局部估计，不是完整条件数或精确逐参数对角。B链式g/K及S=I短proposal相对配对均为0。方向0的过大步长截断及过小步长舍入问题先保留失败，再以已测稳定区间中的h=3e-7见证补齐；原h=1e-7与新见证均≤1e-5，没有改M、loss、优化器或门限。

独立ML用冻结PT/NPZ重建q15/q30；独立FE compare-only才读取V1参考，没有新MUMPS或Gram因子。完整六点复E/H、四类40级复通道及分母/近零尺度、逐级功率、材料/界面区域和G与L2/curl范数配对见[完整诊断](outcomes/parameter_metric_v11.md)及[字段记录](outcomes/records/metric_field_diagnostics_v11.json)。真实轨迹留ignored并绑定hash，不向Git重复复制内层日志。

## 资源、局限与下一步

| 子包 | 新增实测/保守辅助s | 限额s |
| --- | --- | --- |
| A | 507.535971825 | 1800 |
| B | 2829.01236233 | 5400 |
| C | 10444.8594453 | 10800 |
| E | 1814.37630415 | 3600 |

旧累计137403.03555569s完整保留；本页资源快照新增15595.784083609s，累计152998.8196393s，后续浏览器/尾段继续计入最终资源账。历史phase75前缀15758.74009511806s各归属一次逻辑路线，在全项目账不再收费。失败FD、fresh G、拒绝、早停CG、保存和审核全部计费。

每次新数值启动均通过至少60s原PSI稳定窗；CPU-only/MPI1/数学Torch线程1，现场空闲物理核，数值warn12/hard16GiB、factor规划12GiB、detached缓存≤2GiB、轻tests/浏览器≤2GiB，自身swap/OOC0。系统余量max(128GiB,10%有效总量)加384GiB邻增长与自身预算，未修改其他项目。树采样约0.5s，不冒称连续内核限额；tmux管理快照单列。

控制路线使用现场选定CPU12，度量路线使用CPU0；这是共享工作站对照，不能称隔离性能或只归因于算法的同成本优势。两条均没有本批PSI停止或故障恢复。FE第一次验收在worker启动前被“无可审计空闲物理核”拦住；一次有界复核后独立attempt2通过原Gate并完成。两个轻量聚合启动也被拦住，随后原选择算法的只读trace保留了真实准入输入；未降低忙碌阈值、预留或watchdog保护。CPU窗口拒绝与旧两次memory PSI停止分别记账，不写OOM或数值失败。

本轮有界对照不证明FEINN普遍无效，也未证明参数尺度是唯一根因。唯一后续建议：先设计有界的测试空间/弱残差与场误差相关性诊断，保持开放Maxwell物理及完整矩验算，待review冻结数学后再实现；当前不切换loss、不训练第三条、不追加原样GN或监督拟合。p5已有参考保持REFERENCE_ONLY，curl/H、h及端口截断仍未全面资格化；目标尺寸5nm/0.7nm未启动。

[修复记录](outcomes/records/repair_log_v11.json)、[source/hash索引](outcomes/records/run_index_v11.json)、[定向测试](outcomes/test_summary.md)、[文件边界](outcomes/changed_files.md)、[实际GitHub渲染](outcomes/records/render_check_v11.json)。浏览器视觉与本地Markdown解析分别记录；GitHub服务失败不写视觉PASS。只推本执行分支，最终HEAD、ahead/behind、clean和清场在交付回复核报，随后等待review。
