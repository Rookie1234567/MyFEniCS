# V30：轻量入口与审核误报已修复并完成原样验收

**本轮达到 `LIGHT_ENTRY_AND_SYNTHETIC_CHECKER_QUALIFIED`。** 真正的编译检查通过后，以同一个clean实现、唯一一次合格准入完成7项最小回归和162项完整scope（原155项＋新增7项）。完整入口返回0，冻结CPU重算、固定三种小矩阵和成本模块均已执行。该资格只属于轻量入口与合成审核，不是新的有限元解、真实回流方向或神经收益。

审核器负责核对保存的向量、来源和计数是否一致。此前缺输出目录使正确记录无法写出，32个负例又把任意文件错误误认为审核成功。本轮让collector创建输出目录，每个变异测试先确认完整正控制通过，再检查准确的错误类型与消息；专门的IO反例确认FileNotFoundError不能让数据变异测试假通过。数值方程与门限未改。

| 身份／工作包 | measured结果及边界 |
|---|---|
| canonical worktree／branch／upstream | `/home/fenics/Projects/NN-Lab`；`task42_neural_coarse_inverse`；`origin/task42_neural_coarse_inverse` |
| origin／common | `git@github-myfenics:Rookie1234567/MyFEniCS.git`；`/home/fenics/Projects/Maxwell3D-Lab/task-repository.git` |
| Review V27／base | 安全fetch并确认包含`0a0f03390247ef37b12a04cadc61d091320203c0`；冻结base `ccd357885f7f9be84efe3be07868cc94f13d93fc` |
| actual implementation／worker source | `1a18f520dae3ecd702a1369b0d9241ec3e81802a`；运行前clean，22文件hash对回该提交；最终文档HEAD另外报告 |
| A：入口／输出／负例 | `snapshot_label`与`snapshot`文件引用拆分；collector负责新目录，原子writer语义不变；32种变异均触达指定语义Gate，无泛化OSError兜底 |
| B：编译与整体入口 | 准入前22文件`compile(...,'exec')`通过，无模块执行；worker最小7 passed，完整162 passed，入口PASSED／exit0；没有CI／full-repo／FE-MPI声明 |
| CPU缓存重算 | 原V28两冻结快照，从ticks/start与原排除规则重算为`[11,22,26]`／`[]`，逐核JSON／CSV已保存；不是当前CPU预约 |
| 三小矩阵 | n8非Hermitian最大操作归一误差`8.129925522e-17`；n2反例`1.905282407e-16`，均≤1e-12；零局部块显式拒绝 |
| C：成本链 | 原样模块生成hash-bound V24–V28账；不重复累计nested timer，合格完整N=1时间／同时峰仍unknown |

小矩阵检查的是“先解局部J、再处理外域残差、最后回到J补偿”的传统块代数。固定2×2反例中旧回流忽略外域输入，新全空间补项返回`[-2,1]`，原残差成为`[0,6]`，范数放大6倍。代数成立和可逆均不保证迭代收敛；三fixture通过不授予真实预条件器或神经资格。

| shared-workstation费用／资源 | 单位、分母与范围 |
|---|---|
| 不刷新窗口 | 首次工作`2026-10-03T06:39:09.630103Z`；light-stop07:24:09.630103Z，deadline07:39:09.630103Z；队列06:46:31.384243Z提前closed |
| 唯一准入 | 06:45:30.691948–06:45:31.968632Z；CPU21，候选21／37；CPU/SMT、MEMORY、DISK、PSI通过，cgroup/GPU仅只读观察 |
| 有载／累计 | V30监督18.785166597 s≤120 s；V27起21.163846770＋18.785166597＝39.949013367 s≤600 s；V29仍0 s；审阅费用单列 |
| worker／测试成本 | entry14.790799552 s；pytest最小1.26 s、完整10.86 s，含启动的外层2.486083292／12.198941457 s；均嵌在监督wall内，不相加重复收费 |
| simultaneous process-tree | RSS峰195,633,152 B，自身swap峰0；监督parent＋全部后代，0.5 s请求采样、27样本；warn1GiB／hard2GiB有效，未宣称kernel cgroup限制 |
| 环境 | 独立pure `.venv`，NumPy1.26.4／SciPy1.11.4；MPI1/math1，CPU21；三个BLAS getter均1；无FE/JIT/Torch/GPU/OOC，缓存位于V30 |
| 实际数值库存 | 真实actor／S／SH／reader／local solve／LU／gecon／QR-SVD／FE／迭代／训练全0；fixture中的36作用／35端口／7reader只是合成证书 |
| 历史与资格 | formal研发下界77,161.557139 s、旧辅助及完整暖链unknown不清零；V24完整0/5、V23 0/6不改；原尺寸／2TB／48h NOT_QUALIFIED，NN20% NOT_DEMONSTRATED |

没有检测到watchdog资源／健康停止，所有后代已清空；这不证明绝对零干扰。监督wall包含测试、缓存分析及原始写出，准入启动和实现／读取／交付计入总elapsed，完整launcher独立峰／exclusive费用unknown。新增存储与实测总elapsed见[存储记录](outcomes/records/storage_v30.json)和最终终端回执，不用数组体积冒充RSS。

[详细结果](outcomes/light_entry_acceptance_v30.md)、[合成checker资格](outcomes/records/checker_acceptance_v30.json)、[完整入口](outcomes/records/entry_result_v30.json)、[编译](outcomes/records/compilation_v30.json)、[run index／raw](outcomes/records/run_index_v30.json)、[费用](outcomes/records/resource_costs_v30.json)。V29的NOT_RUN、Review V27审阅阶段的147/8及隔离修补结果分别保留，没有倒填。

神经20%仍须在相同完整正确性下，相对最佳合格非神经N=1路线，使完整耗时或同时峰至少下降20%，另一项合规。仅替代V26共0.008964091 s薄LS，最多覆盖该诊断actor约0.026949%，不是完整成功单解份额；因子、原作用、审核、IO和学习新增成本仍须完整计入。

**唯一下一建议：由新review判断是否授权一次原两冷态、V26九方向基线的真实回流诊断。** 仍缺真实因子原作用／完整消费资格、可审计资源准入、独立监督和完整冷／驻留成本；本轮没有授权或执行它。不续旧closed窗口，不改dot、其他分支或master，无subagents／重置卡／merge。提交推送后停止等待审阅。精确GitHub review页Cache miss，视觉`NOT_VERIFIED`；本地结构检查另列。
