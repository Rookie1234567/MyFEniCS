# Response V35：冷启动在线负结果，关闭固定七／八块追加路线

收到用户授权交接`review-execution-handoff-20261004-v32`后，在canonical工作树安全取得[Review V32](review_report_v32.md)，完成任意输入七区预条件器、真实reader与算子资格、一次从零trace开始的GMRES256及独立缓存审核。**首周期原Schur残差0.20524886351900365，大于继续门0.01，判定`ONLINE_BLOCK_PC_PROGRESS_INSUFFICIENT`。第二周期及条件FE验收未运行。** 普通fixture问题同轮修复后继续，没有以软件完成代替真实执行。

本方法先在联合区域J=[5,7]内解局部方程，再处理六个外域块的残差，最后消除返回J的作用。希望用局部存储提供全域修正方向；GMRES在这些方向中选择使原方程残差下降的组合。每个非零PC输入需要两次J解、六次外块解和两次原作用，外层还需原作用。它是传统固定块方法，本轮没有神经训练。

| 身份／范围 | 实际记录 |
|---|---|
| branch／canonical worktree／upstream | `task42_neural_coarse_inverse`／`/home/fenics/Projects/NN-Lab`／`origin/task42_neural_coarse_inverse` |
| base／实际取得review | `ccd357885f7f9be84efe3be07868cc94f13d93fc`／`e1926a9cb42329276da4a26f4304f71cbbf97198` |
| 正式数值source | `af0d3d3e7d2b05ab915902bbb66b6ddbd7ed912e`；启动前clean，最后文档HEAD不替代它 |
| 独立缓存checker source | `6e17883a672d6166472bb80c27999afc46d4a059`；最后计数元数据修复、静态／接线复验另列[source inventory](outcomes/records/source_inventory_v35.json) |
| 完整物理身份 | 原0.7nm／384hex／Nédélec p3／q15／三维缺口／双Floquet，18144trace＋完整40port；[run index](outcomes/records/run_index_v35.json) |
| 材料 | canonical用户Si表，source标签`0.699999988`明确alias到nominal`0.7`；n=[0.999885140474,4.32477054e-6]，epsilon=n²，不插值 |
| 新入口 | `python scripts/run_case.py input/task042_neural_coarse_inverse/v35_online_cold.dat`；条件`v35_verify.dat`已实现但NOT_RUN |
| reader／禁读边界 | V26 J及V24外块0/1/2/3/4/6只读；未读原5/7单独LU、warm、V25响应、V26/V32校正、REF7、神经权重或旧Q/U/R |

## 资格、实际返回与停止

七个reader逐一核对几何、容器／成员hash与两种子原主块／伴随／solve见证。复线性、重复性、全零输入及J消除检查通过；class64仅复用相同数学作用，旧ActionPacket/recover/uncondensed/audit仍为独立oracle。完整b归一化新旧作用最大差1.46416e-13≤1e-11，operation最大差1.18089e-16≤1e-10；PC复线性误差7.42378e-14、J平衡最大3.39863e-13≤1e-10。

| 首周期measured指标 | 实际值 | 原门限／决定 |
|---|---:|---|
| Schur：保存的完整b−S*z／原完整b | 0.20524886351900365 | 资格≤1e-6；第二周期进展≤1e-2，两者均失败 |
| 原native／未凝聚augmented | 0.07959628543991103／0.07959628543991103 | ≤1e-6，失败 |
| original total augmented | 0.027619862207395922 | ≤1e-6，失败；不替代Schur |
| port／完整b；port operation | 1.3018827520752422e-16；7.037334124260932e-17 | ≤1e-6，通过，但不授予完整解资格 |
| 内部恢复；原恒等式operation | 3.844299504353224e-13；4.299640328602692e-13 | ≤1e-10，通过 |
| slave storage | 0 | 精确0，通过 |
| 返回边界 | Arnoldi256／GMRES info1／一周期 | info1是固定周期用尽，不是bug；完整y/By/trace/port/z/残差已原子保存 |
| total/scattered E/H、curl、selected field、40复通道误差、R/T/A/A_volume、逐通道功率和能量 | NOT_RUN | 原方程失败，不准入独立FE；没有新official R/T/A |

[独立checker](outcomes/records/online_checker_v35.json)从保存数组重算残差、右变量映射及消费，不信status自证。单次原审核包含一次实际内部恢复；cold端口按原rhs闭合，本例测得其范数0，不是人为把所有端口置零。内部非零特解仍保留，非零端口接线由小型复数见证覆盖。

## 成本、资源与失败保留

| 实测／口径 | 数值／证据 |
|---|---|
| 唯一actor监督wall | 188.16208866692614s，shared-workstation；完整launcher191.15673444897402s包含actor，不能相加 |
| 求解周期／PC | 155.22630215494428s／129.56581060239114s，均为嵌套计时，不加到actor上 |
| 七reader读取/hash；全部局部solve | 约14.69s／56.797606099s，reader和solve分项可重算，见[成本账](outcomes/records/resource_costs_v35.json) |
| 同时整树采样峰／ownswap | 2,108,018,688B／0，0.5s监督含launcher、worker及后代；无可写cgroup，不称内核连续限额 |
| 规划及对象体积 | 同时规划5,371,055,616B≤8GiB；七套A/LU净1,591,420,032B＋pivot72,576B；不是RSS |
| 实际完整消费 | S/SH834=旧45＋fast789；PC264含零短路2；reader7、Jsolve526、外解1584、三角pass4220；40port factor2／solve与RHS822；原audit1 |
| 新大LU／gecon／全局image QR／NN／GPU | 全0；存在七套只读dense p3局部LU，不能称factor-free |
| 历史与本轮 | 本轮监督／探针261.5397493925411s=actor188.16208866692614＋aux56.7378578648204＋probe16.63980286079459；旧212.19044355582446s campaign保持closed，Review已测辅助3.666822421s另列；完整历史N=1仍unknown，[完整费用](outcomes/records/resource_costs_v35.json) |
| 现场共享 | 运行时fresh选CPU0，MPI1/math1，实际BLAS getter1，nice10/idleIO；没有观测到持续PSI压力，未操作邻任务；无可比吞吐证据，影响及无争用性能INCONCLUSIVE |

首次前测24pass/1fail是合成fixture在结算前调用VERIFY，修后25pass；独立缓存阶段26pass。结项静态检查后一次导出接线复验34pass/7fail：共享runner通过模块属性读取FAMILY，误删后失败；恢复显式公共导出后，只重跑受影响7项，全部通过。未受影响34项含15个文档合同测试；相关编译23文件、Ruff新V35模块通过，最后存档接线在真实packaging和单文件Ruff上另验证。原失败不覆盖，跨source测试不合并伪称最新source全量资格，见[tests](outcomes/records/tests_v35.json)。两次容量预留拒绝均发生在真实actor／reader／作用前，同门限无损归档后继续，真实轨迹只有一次。bytecode、失败fixture及资源jsonl均逐名hash无损归档，不删除旧真实数组或closed证据。[原始索引](outcomes/records/raw_evidence_index_v35.json)包含所有失败与归档入口。

原公共adapter曾把旧oracle的45次作用写成总数、把恢复写为0、沿用较早formal费用下界。原始af0记录保留；新记录按旧＋fast计834、原audit恢复1，并保留Review V32确认的77161.55713859801s历史下界。最小opt-in元数据hook及真实接线测试修复将来输出，不重跑已冻结数值。

## 全局困难、原尺寸与神经收益

最终保存残差平方的99.1900179%在六个外域块，J只有0.8099821%；八区平方和与全域一致到5.65e-16。最大分量在块1与3，合计53.7432330%。这是canonical残差系数分区，不是材料场能量。局部解与端口闭合可信，残余外域耦合仍占主导；不能据此宣布唯一物理病因或Maxwell本身奇异。

原尺寸50×25nm、z=−10..130nm的体积是micro约85034倍，不能当DoF倍数。固定七块的dense存储/solve随块行数f近似f²、构建f³；原样放大不是可扩展设计。目标mesh/p/积分、准确几何细节、完整通道、N=1及全局耦合成本仍unknown。[规模桥接](outcomes/original_scale_bridge_v35.md)及[机器记录](outcomes/records/original_scale_bridge_v35.json)明确已知值、假设和缺项，未把40通道或micro费用外推为2TB/48h资格。

没有合格完整非神经N=1分母，也没有训练／推理配对，**神经20%仍NOT_DEMONSTRATED、原尺寸仍NOT_QUALIFIED**。固定旧列空间的系数训练不能超越该空间精确LS；局部逆压缩即使省存储，也不会自动补全外域全局传播。必要成本式及同时峰生命周期见[规模桥接](outcomes/original_scale_bridge_v35.md)，未知C不填0。

唯一下一建议：在匹配原行序、复Floquet相位、40端口消元及恢复审核的接口下，先审查真正外域Schur耦合的周期／层次全局逆与容量证据。**本批不实现该替代求解器，不再投入固定七／八块的追加方向或周期。** dot仅只读远端ref，最新SHA的内容未取，不能用其不同模型当本micro资格或等待它替代交付。

已同步[summary](outcomes/summary.md)、[tests](outcomes/test_summary.md)、[changed files](outcomes/changed_files.md)、[项目进展](../development_progress.md)及[模型总账](../development_model_registry.md)。历史task/review/response/raw保留；GitHub视觉无取得证据时为NOT_VERIFIED，本地结构检查另列，不称CI。仅推送本执行分支，完成清场后通过既有会话队列通知审阅窗口，停止等待review；不merge、不启动更大模型。
