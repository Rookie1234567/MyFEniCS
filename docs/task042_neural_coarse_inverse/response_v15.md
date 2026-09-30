# Response V15：局部与组合配对完成，多项式组合更好，仍未通过有限元门限

按[Review V12](review_report_v12.md)实际完成L0、LOCAL-POLY/NN、UNION-POLY/NN和独立L3。局部容量**1544**、组合**3098**，4个候选decoder与2个制造见证数值合格；独立8状态严格通过**0个**。UNION-POLY有真实场改善，NN同容量更差；没有hidden训练或独立神经增量，原0.7nm／48小时目标未合格。

把单胞的有限元边／面系数按几何位置分成八组，让各区独立组合空间函数。函数先经过完整边／面积分、坐标和方向变换，才变成合法的Nédélec有限元未知量；所有区域仍由同一个原Maxwell方程耦合。两库分别使用固定随机神经隐藏特征与确定多项式，并按每组实际秩匹配容量。每组方向正交化后直接输出trace，避免用巨大原始输出系数相消。这里trace是单元共享的电场积分系数，40个port是上下边界波模幅值；内部电场由原局部方程作包含非零特解的恢复。

本批hidden固定，网络只计算局部坐标的64个tanh函数；加常数后形成65个标量特征，每个配三个物理向量方向。最终组合系数由原方程薄最小二乘求得，完整40端口由原40×40凝聚Hhat闭合。Hhat不同于未凝聚Hp。两路线都有相同稳定解码及线性代数，不存在hidden训练增量。

| Git／provenance／冻结模型 | 实际身份 |
|---|---|
| 分支/工作树/upstream | task42_neural_coarse_inverse；NN-Lab canonical linked worktree；origin/task42_neural_coarse_inverse；origin git@github-myfenics:Rookie1234567/MyFEniCS.git；common /home/fenics/Projects/Maxwell3D-Lab/task-repository.git。由干净V14 HEAD安全FF至c0a759c29c08cc377a3fde3b81c5f4c34c24710a，不回退、不操作其他worktree |
| base/真实source | base ccd357885f7f9be84efe3be07868cc94f13d93fc；六run均 **db0e68e519767554412c960af14b3c185012f9de**；checker 8d6df6926fc6f5c1afc27491dc06255791fcc044。最终文档HEAD另在推送报告，不冒充数值source |
| 原物理/材料 | 0.7nm、384hex/p3/q15/batch8、完整40端口，full34050/trace18144/内部13824/slave2082；canonical USER V1材料/背景/RHS/hash保持，Si n=.999885140474+4.32477054e-6i、epsilon=n*n |
| L0/容量/原作用 | 8组完整实体无丢行或重复，MPC通过，独立完整FE矩差约2e-15；共同秩195×6+187×2，未凑满1560。Hhat cond13284、GELSD/cond1e-12；原3列+2组合、实际/thin、驻点、port与齐次恢复均过原Gate |

| 相同物理模型；measured无量纲 | 实际复容量 | 原Phi | Schur/native；限1e-6 | 散射E/curl；限1e-4 | 资格 |
|---|---:|---:|---|---|---|
| G0 | 1560 | 0.318179987294 | 0.797721740／0.309359507 | 0.734256828／0.734361605 | FAIL |
| LOCAL-POLY | 1544 | 0.339574133266 | 0.824104524／0.319590851 | 0.578751074／0.578743743 | FAIL |
| LOCAL-NN | 1544 | 0.339239788767 | 0.823698718／0.319433478 | 0.628221107／0.628213879 | FAIL |
| UNION-POLY | 3098 | 0.134013809183 | 0.517713838／0.200771384 | 0.283235368／0.283293409 | FAIL |
| UNION-NN | 3098 | 0.168191759580 | 0.579985792／0.224920683 | 0.766070574／0.766240878 | FAIL |

两条局部普通负结果后按准入继续L2；G0取V14 ORIGIN Q，补空间raw秩POLY1538/NN1544，共同q1538，完整保留G0、重建差0，各自独立求原RHS，无参考或warm start。组合POLY的rho下降35.1009%、散射E下降61.4256%，仍未达rho减半研究门限；NN组合的散射误差还劣于G0。组合改善包含维数增加，不能归为神经训练。

全部求解/决策/hash冻结后，一次FE审核历史2+候选4+表示投影2。REF7本次独立native **1.437444866e-12**通过且原非零残差保留，未新LU。两库offline投影trace误差约0.00125、散射E約0.00113/curl约0.0035，比方程LS场接近得多，但其原Schur仍0.91/0.96；不能称解或全部NN能力下界。遗漏高响应方向、表示不足和欧氏残差衡量取舍仍可能并存，唯一根因INCONCLUSIVE，参考未回传求解。

最好的UNION-POLY total E／scaled-curl（亦对应H）误差0.0296391/0.0296458，selected复E/H .0258167/.0331777，40复通道.0118838，能量闭合.0308740，均FAIL；port/recovery/identity与slave-zero通过不能替代整方程。R_total/T_total/A_balance/A_volume=.107762913/.856177879/.036059208/.005185180，全部未资格化诊断，无official R/T/A。[完整方法与结果](outcomes/local_trace_representation_v15.md)、[全部原场/方程CSV](outcomes/records/local_candidate_comparison_v15.csv)、[40复通道](outcomes/records/channel_observables_v15.csv)、[offline表示投影](outcomes/records/representation_projection_diagnostic_v15.json)。

六stage监督wall **2106.167431s**，完整launchwall2114.586302s，最大采样整树 **4175888384B=3.889GiB**、ownswap0/VRAM0，全部清场；S/SH9345、A列9284、LS/RHS6、localSVD16/complementSVD2、audit13/field8。联合POLYstage包括两库共同设置351.63s，各方法另记自己的设置成本，不能按stagewall误称NN加速。decoder变小，A/QR/LS workspace仍实测计入，未构造global p4因子、全局Schur、正规方程、ILU/Riesz或fallback；独立native审核装配如实计费。新artifact1.020GB，旧负结果未删。[资源与生命周期](outcomes/records/resource_costs_v15.json)、[真实source run index](outcomes/records/run_index_v15.json)。

受控共享CPU每stage实时选核，MPI1/数学Torch1/Loader0、ownlock/cache、nice10/I/O idle，规划<8GiB、warn12/hard16GiB、ownswap0；无cgroup委派，实际为0.5s采样整树监督。未见持续压力stop，可比邻吞吐unknown，性能INCONCLUSIVE/shared-workstation，未修改邻任务，不能宣称零干扰。新窗口start08:44:30UTC、heavy12:29:30/总12:44:30不刷新；V6起formal下界16776.579534s，旧aux unknown保持。

最终33小回归、compileall、6入口验证和独立raw checker通过；正式修复/重放0。文档合同及模型总账5项小测试也通过，历史正文保持。额外preflight误用WSL marker、shell未set-e的偏差如实保存，既有和重核native complex128/int64/MPI1有效，后续set-e，不重跑正确L0。Ruff unavailable，无CI/full pytest/MPI2/4声明。[测试](outcomes/test_summary.md)、[变更分组](outcomes/changed_files.md)。Review V12服务端4表/3公式结构PASS，浏览器字形未观察；结果推送后检查另记[publication](outcomes/records/publication_checks_v15.json)。

唯一下一建议（本批未实施）：保持 LOCAL-POLY 的1544维空间及相同物理RHS，预登记一次由原FE测试函数的 H(curl) 能量范数确定的残差行尺度对照；尺度只由网格／算子决定，禁止用REF7选权重，最终仍按原未缩放残差和全部场／功率门限审核。这检验当前系数欧氏残差的衡量方式是否造成场误差取舍，不保证补足遗漏方向；需要下一份review授权，不自动执行或扫描尺度。

旧task/review/response/raw与seed420620保持；不新增p4参考、最大模型、GPU、训练或merge。全部授权路径完成，推送本分支后清场等待review。
