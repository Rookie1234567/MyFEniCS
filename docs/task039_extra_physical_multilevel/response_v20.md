# Task39extra Response V20 / Review V19：original 112步完整通过，以更高内存换取时间

单元凝聚是在每个有限元单元内先解掉内部未知量，只迭代相邻单元共享的边界与原80端口；最后把内部场准确恢复。本轮把这个过程也用于p6，p4继续用V18准确凝聚LU。这样减少外层向量与全局纠错次数，代价是新增局部缓存；原p6本来就是matrix-free，没有删除一张原本存在的全局A6矩阵。

| 指标（同一 original，Full3D p6/h10，13.5 nm，MPI1） | V18 准确 p4、完整 p6 空间 | V19 p6/p4 双层凝聚 | 结论 |
|---|---:|---:|---|
| 外层向量长度 | 173802 storage | 51272 trace＋端口 | 少70.50%，属于载荷/维数变化 |
| FGMRES32 步数 | 564 | 112 | 少80.1418% |
| KSP 算子作用 / 求解PC | 581 / 564 | 115 / 112 | 同一KSP；X1另1次PC |
| 原 A6 最终真实残差 | 9.92314718715201e-7 | 9.730817853580687e-7 | 均≤1e-6 |
| L2 / scaled-curl | 1.3644783293e-8 / 4.3714257233e-9 | 1.5860495296e-7 / 1.5359268899e-7 | 均≤1e-4；新场误差没有更小 |
| 全过程树 RSS，B | 2528460800 | 3965534208 | **增加1437073408 B，+56.8359%** |
| 同口径 PSS，B | 2494237696 | 3931141120 | +57.6089% |
| 数值常驻库存，B | 1830284886 | 2031387110 | +201102224 B，+10.9875% |
| 同时临时池上界，B | 396129600 | 423441224 | +6.8946%；不是RSS |
| 完整流程 monotonic，s | 6609.6613787800015 | 1352.0121227929922 | **减少5257.649256 s，-79.5449%** |
| 保守账本结算，s | 7210.314084736167 | 1474.858420017083 | 与monotonic分列，不相加 |
| 完整数值 / 物理 / 资源安全 | PASS / PASS / PASS | PASS / PASS / PASS | 资源安全不等于节省内存 |

**推荐把V19保留为下一轮唯一优先验证候选：此固定模型完整通过，时间显著降低；同时承认内存退步，V18保留为内存较低的已通过基线。** 这不是生产默认切换或新计算授权。状态为`PASS_ORIGINAL_TIME_GAIN_MEMORY_REGRESSION`，不能写成“全面省资源”，也不能忽略实测时间收益而写成“无任何资源收益”。

新original仅一场、无正式重放；独立用户服务正常结束，整树零swap且清场。旧notch保持用户关闭/最终未知，本批没有notch、BLR、其他PC、参数扫描或新参考，不影响5nm线。完整数据和同scope边界见下方报告；普通默认不变，不合并master，等待统一审阅。

## 对本轮要求的直接回答

| 问题 | 结论与证据 |
|---|---|
| p6是否真正只在保留空间迭代？ | 是；FGMRES32向量51272，实际112步、115个KSP action。p6全局A6/S6均未构建；完整173802维scratch仅用于原BAL_H及恢复/核验。 |
| p4准确作用有没有改变？ | 没有；CSR hash与V18相同，一份21824行准确LU，226次回代各一次MatSolve，最大原A4残差5.04559e-11。 |
| 为什么无需trace Galerkin假设？ | 用增广逆的保留块`J M_aug J^H`，一次PC仍一次BAL_H、两次p4回代；不是直接截P64。小oracle与同根X1均通过。 |
| 原A6是否最终通过？ | 112步后独立native重算9.730817853580687e-7；端口闭合5.84770e-16，内部与恒等式通过；L2/curl、E/H、80模式、R/T/A/A_volume与守恒全部合格。 |
| 总工作量、内存、时间是否降低？ | 全局迭代/回代次数确实减少，完整monotonic少79.5449%；全峰RSS却多56.8359%，库存多10.9875%。未测FLOP或独立正交化，不能由向量长度代替这些指标。 |
| 缓存抵消多少向量载荷？ | 新p6数组201102224 B，超过65向量理论节省127431200 B达73671024 B；载荷差不能替代RSS。 |
| 后续采用哪条路径？ | 建议V19作为下一轮唯一优先验证候选，以更高峰值换取本场约4.89倍总时间优势；V18留作内存较低基线。普通默认不变，须统一review后另行授权下一次运行。 |

## 阶段与成本

X0：82 passed/1 skipped、compileall和public dat通过；一次非PDE服务探针先因漏phase_path失败，修正后通过，保留两次工程尝试。X1：同一正式根的3个固定向量，恒等式最大5.97668e-14；一次PC计数1/1/2正确，沿同对象直接进入X2。X2：一场完整original通过；无正式重放。X3：原数组独立checker、资源/进程清场与完整比较通过，提交文档收口。

完整流程1352.0121227929922 s（monotonic），保守结算1474.858420017083 s；UTC/monotonic差约122.844 s均保留，observe_only不恢复时间停线。p6 adapter setup160.878790 s，p4 setup32.614560 s；KSP本身1049.785037 monotonic s。桥总980.540728 s内含BAL_H978.177721 s；226次p4缩减—回代—恢复46.998367 s已包含于PC。嵌套时间不能相加。正交化及p4三段各自时间未单独测量，组合区间与总成本均已保存。

RSS比较覆盖两场全部case后代、setup/JIT/求解/恢复/最终评价/清理，因子在最终物理评价后释放；两个峰均含编译器，没有拿warm峰对旧cold峰。两场复用既有缓存，新增p6内核JIT内容不同，故不宣称warm-only内存因果收益或多次运行稳定加速，不为消除该差异重跑基线。新全峰3.966 GB仍通过原8 GiB树上限，库存/临时分别低于6/1 GiB，reserve、零swap和清场通过。

## 交付身份与证据

- 用户base：`3c7b6ecfd7aede2651dd973052a097dbed601d03`。
- clean正式source（运行前后相同）：`8eff068b06f4713cc6d1281c92ed82d370060403`。后续提交仅为数据和文档，最终远端完整HEAD由回复提供。
- 执行分支`task39extra`，canonical worktree，未合并master；V18冻结文件/24个旧profile与5nm工作线不变。
- [完整结果与复现命令](outcomes/dual_cell_condensed_v19.md)、[compact](outcomes/records/dual_cell_condensed_v19_compact.json)、[decision](outcomes/records/dual_cell_condensed_v19_decision.json)、[run index](outcomes/records/run_index.json)、[测试](outcomes/test_summary.md)、[selective manifest](outcomes/selective_merge_manifest_v20.md)。

最终静态检查通过：132份证据文件hash、43项独立checker条件、36条历史运行记录、45个冻结文件与24个旧profile均核验；JSON、Markdown解析、表格列数、公式围栏及本地链接通过。已目视核验残差/成本图，生成本地HTML；Codex文件预览请求处于排队，浏览器公式和GitHub网页渲染未目视核验。静态证据为`benchmarks/artifacts/task39extra/dual_cell_condensed_v19/root_engineering/x3_static_checks.json`。

旧notch最终结果/实耗unknown、旧43200秒与600秒政策占用和所有负结果仍原样保留。没有新notch、BLR、5nm/0.7nm、第三路线或参数扫描；不作连续收敛与生产可扩展承诺。不声称CI、Ruff、全库pytest或MPI2/4通过。统一推送后等待审核。
