# Response V23：实际拒绝不合格求解，完成可消费面积分组件

Review V22的P0–P3已完成。两种局部积分都满足本轮精度门，但解析组件没有20%的完整成本优势，**推荐接收方已有的q60，结束追加解析优化**。这次交付修复实际准入漏洞，并给出已运行的可选接口；没有新的场或神经收益。

| 本轮实物 / measured | 结果 | 证据与边界 |
| --- | --- | --- |
| P0真实调用链 | E3/E4保存算术可读；oracle、实际物理投影及仿射标量资格不全，campaign/direct两入口均拒绝 | [派生角色](outcomes/records/strict_admission_v23.json)；UNKNOWN/缺文件/错caller identity/schema不能进入factor，即使全门通过，本批也禁止solve |
| P1实际接收方 | 冻结 `FacetPolynomial` 的300/882列p4/p6面系数；非恒等方向、独立点值重构及80/110位积分交叉通过 | [局部资格](outcomes/records/facet_qualification_v23.json)、[可运行接入包](../../benchmarks/cases/portable_interval_facet/README.md)；没有复制owner、MPC布局、W1或体积求解器 |
| P2解析 / q60矩 | 最大自然区间绝对差3.55445e-16 / 9.08281e-14，均≤1e-12 | [逐case原分母864行](outcomes/records/local_case_errors_v23.csv)；完整1213频率及Decimal字符串留hash-bound ignored数组 |
| P2逐case/方向原分母 | 最坏相对差1.65720e-13 / 1.97675e-11，均≤1e-10 | [独立checker](outcomes/records/independent_checker_v23.json)；上下s/p、非零载荷、三条复方向、B/D/H及共轭伴随；不代替旧敏感向量投影门 |
| 完整冷成本 | 解析64.46515s、175190016B；q60 64.61506s、114491392B | [完整冷对照](outcomes/records/local_cold_comparison_v23.json)；含导入、首次系数、积分、适配、写出、checker和规定稳定窗口；单次共享机观测 |
| 增益出口 | 完整时间仅改善0.2320%；RSS反而增加53.0159%，没有≥20%局部净收益 | **RECOMMEND_EXISTING_QUALIFIED_Q60_CLOSE_ANALYTIC_OPTIMIZATION**；更小矩误差不构成目标完整解或NN收益 |
| P3保存与成本 | 实际数组独立重算、失败/UNKNOWN、六类依赖、接口和自身导航已交付 | [运行/source](outcomes/records/run_index_v23.json)、[资源](outcomes/records/resource_costs_v23.json)、[修复](outcomes/records/repair_log_v23.json)、[依赖组](outcomes/records/selective_merge_manifest_v23.json) |

接口解决的是宽面片上波动积分不够准的问题：保留面上的有限元多项式、几何面积和物理方向，直接计算其与传播相位的积分，替换接收方两次一维求积。付出的代价是Bessel依赖、身份核验和适配成本；本次可靠q60已够准，解析方案未带来所需成本收益。详细数学、分母和固定范围见[单个专题](outcomes/portable_facet_component_v23.md)。

实际source：P0成功提交 `765aeafc615ebfb0c842bd2fdad195a696271a71`；P1及两条冷生命周期 `b5034e5ffab657146024ac429fe410f005049d3d`；最终保存数组checker `7a7c6b5a3a0c65a93e362644b50ad84ae0d20f2c`。输入Review seal为 `e1635d7f2c461a5e1a019bd38f84412968930be5`，冻结base为 `fbac3d8777fcfd897d93b898cb9f460f79ddd6ff`。交付文档HEAD另在最终通知报告，不替代运行源码。

47项最终定向测试、Ruff/compileall和实际入口fixture通过；没有full pytest、CI或环境安装。原生Basix面组件已做当前complex128/int64、MPI1 ABI及60s资源窗口。全过程预算14400s，CPU-only、空闲物理核/线程1、warn1.75/hard2GiB、自身swap/OOC0，系统及384GiB邻增长预留保持；截至证据冻结观测2390.29s，最终费用在封存资源记录更新。采样树峰179499008B；这是已采样阶段峰，不冒称启动前拒绝或全客户端连续内核上限。新Maxwell全局/局部因子、solve、Gram、NN训练均0；面多项式坐标转换的小型Vandermonde求解另计，不能称完全没有任何代数求解。

保留初期CPU准入拒绝及两次有新窗口的再准入；分派接线、compact负控字段、格式及缺失mpmath分别定位修复，环境不安装而改用标准库Decimal80/110。失败前worker未启动的记录如实关闭，不覆盖原日志；P0两次有修复重试完成，资格化后的面组件没有重放。43-test早期XML被后续47-test覆盖，原XML为NOT_RETAINED，原worker日志和费用保留；最终47-test XML独立保存。[测试/限制](outcomes/records/targeted_tests_v23.json)完整区分这些事实。

旧V22的实际敏感原点投影FAIL、ORACLE_ACCURACY_UNRESOLVED、有限p场/模式FAIL及REFERENCE_LIMITED不改。M3600较好态、Mfinal退化、D0成本否决/D1未运行、失联3284s、历史费用和UNKNOWN均保留。全32060-key原件在主线端已核验，本机缺件不影响本接口，但本轮不是全key/目标网格资格；主线和dot仍按自己的合同执行。本支维持 **FEINN_MAIN_SOLVER_ON_HOLD / NO_VERIFIED_NN_INCREMENT / FULL_TARGET_NOT_QUALIFIED**。

唯一最终目标仍为原50×25×140nm、Si17/120nm、λ0.7、全部内部场/双Floquet/完整端口三维FE，十进制2e12B整机、swap/OOC0、172800s完整流程及原精度门，尚未达成。没有production或merge approval。有限补查本回应与专题的实际GitHub呈现，旧Review V22已封存的7表/1公式/9图按hash复用，见[渲染记录](outcomes/records/render_check_v23.json)。提交推送精确本分支、确认清场后只发一次正式完成通知，随后停止，不再安排同类优化或档案批次。
