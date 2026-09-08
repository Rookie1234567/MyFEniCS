# Review V2 回应：F5 用户要求收尾

| 身份 | 完整值 |
|---|---|
| 分支 / Task base | task39extra / `2dc2e7305f10dc391a13970c6f0f0340cb87b6ee` |
| Review V2 | `abe5fa2cb1240c397f514a815390a2d9fabd5d5f`，审阅基线2b4de1b8802c4702c1abc8e998952a1b7dc3e110 |
| F1 source | `4d30514d52e27d3c854c8d1f4432d3ce977c078e` |
| F3 formal / 当前代码HEAD | `60b8df2a24cbcd96e49e018be22fb64f06eeae3f`；启动/退出均HEAD=origin、clean |
| F5交付状态 | 本轮完成，九份doc-only交付；精确交付SHA及remote身份由主线程提交推送后报告；不自引用未发生SHA，master merge未授权 |
| F3 audit SHA256 | `f4075f4bf8f545082a58f15ffdc35cc58fa3ba1e8af8ede82955efc50c196a69` |

| Review V2 / F5 | 当前结论 |
|---|---|
| F1 / F2 | 完整packed S6数学等价通过；配对中位0.938459>0.75，速度不足，F2 not_run |
| F3原始模型 | 13.5nm/1°/p6h10/MPI1/80modes；source `60b8df2a24cbcd96e49e018be22fb64f06eeae3f`；零初值476步真残差0.10535820013809101>1e-6 |
| 方法与失败含义 | 保留H6–准确p4–H6三个顺序方向，仅末尾联合选权；局部残差比中位0.979479，rank3/无回退；不足以让完整p6收敛 |
| 用户收尾 | USER_REQUESTED_CONTROLLED_STOP；raw worker CONTROLLED_STOP、wrapper WORKER_FAILED/exit4并列；未触发原自动budget/stagnation Gate |
| 时间限制 | workflow monotonic7588.369777 / UTC8363.831318 s；solve至请求monotonic6791.466003 / UTC7478.995420 s；UTC solve超7200，原因未唯一确定，不能声称全部wall预算通过 |
| 资源与清场 | RSS/PSS峰3351887872/3317217280 B，28753样本均可读；cap8525078528 B、至少4GiB余量无违规；swap0，56 PID清场 |
| 后续 | F4/official锁定，无第三候选、续跑或0.7nm资格；仅F5文档/测试/审阅后提交推送，非master merge |


## Review条件与用户停止

F0复核旧证据与停止修复后执行唯一F1。连续排布只改变局部数据布局，保持完整S6数学作用；同输入action/PC通过，但配对中位ratio0.9384593270111676未到0.75，因此F2跳过，按Review进入唯一F3。F3保留原LIGHT按顺序产生的三个方向，只在本次PC末尾共同调整系数，用一次额外原A6检查实际残差；小QR/SVD避免不稳定求解，固定cutoff1e-12与safeguard。收益是局部残差更小，代价是额外action及有限工作数组，不保证整个外层收敛。

F3 fresh empty cache/zero start完成476PC，最后安全原A6真残差0.10535820013809101>1e-6；用户明确表示结果与前次相近，要求现在收尾。核验PID/startticks后只向应用一次SIGTERM，在8.122428637 s内完成最终资源采样及安全退出，无硬杀。worker最小摘要CONTROLLED_STOP，wrapper因exit4记录WORKER_FAILED；两者及泛化的performance stop exception原文保留，派生实际原因为USER_REQUESTED_CONTROLLED_STOP。没有自动7200/stagnation stop_event，不得改判。

F4非可分仅在原始通过时才授权，其条件未满足；official/独立全场authority/h5/direct/5nm/0.7nm均未新增运行。用户要求结束本轮，没有第三候选或续跑；剩余计算预算不是新权限。

## 结果与限制

476次p4原残差最大7.870604378195616e-11≤1e-10，476次joint均rank3、无回退，局部残差比中位0.9794794387162146，约2.05%局部改善。完整PC中位11.460344589024317 s，extra A6累计694.8742099204101 s，QR累计5.928539212793112 s。14完整32步周期加28尾段完整PC，H6/B6/方向A6/extra A6/p4分别952/1904/1428/476/476；没有第477个未完成PC。全部cycle与旧R3同step、同名义monotonic周期时间对照和早/晚分项波动见[中心报告](outcomes/packed_and_joint_mr_v2.md)。不能把rank3和局部收益当全局求解足够快的证据，也不能把晚期耗时波动归因于未证实的复杂度或宿主机原因。

28753资源样本RSS/PSS均可读；同期峰3351887872/3317217280 B，cap8525078528 B，至少4294967296 B余量无违规，swap0，56 PID联集全部消失，cache稳定、cleanup_errors为空。65次monitor中reported/explicit最大差6.589173651150304e-14；全部checkpoint和原始文件hash已核对。成功场恢复/official输出没有发生，停止路径释放不能代替成功release-before-recovery资格。

**时钟口径存在重要限制。**manifest UTC全流程8363.831318 s，而monotonic7588.369777164073 s，相差775.4615408359277 s。首个solve样本至用户请求的UTC区间7478.995419763 s>7200，monotonic区间6791.466002859059 s；末次reported solve为6791.780280707986 s。原Gate只按monotonic未触发，但不能笼统声明两小时wall预算通过。原因尚未唯一确定，不声称clock bug/CPU throttle，不更改raw、不事后换clock重判，也不重跑。workflow两口径均小于10800 s。此前简短状态中的预算通过含义在此纠正。

## 验证与交付边界

F1实现85 passed、F3实现63 passed；原失败fixture和扣账保留。最终一次task-focused回归181 passed、1 skipped（MPI2专用），ABI preflight/compileall通过；pytest117.19 s、外层monotonic109.88929661700968 s、UTC-derived118.71753764152527 s原口径并列，见[测试摘要](outcomes/test_summary.md)，不跑full repository/PDE、不安装Ruff、不声称CI或网页可视验证。F5不改生产代码，因此已有formal源码及测试文件身份保持。最终doc-only commit和remote精确SHA由主审/推送后另报。

V2原monotonic账本与双时钟限制并列于[小JSON](outcomes/records/packed_and_joint_mr_v2.json)；未借V1余额。选择性合并按[依赖组](outcomes/workstation_handoff.md)区分可复用基础、runner/checker、紧凑证据、research-only与do-not-merge；本轮profile不提升production，master未授权合并。任务关闭的是本轮两个候选；p4全局factor、难误差修正机制、独立物理authority和0.7nm扩展仍未解决。

最终V2原monotonic账本16项，累计8820.53636143892 s、余27179.46363856108 s；时间差异见前文。最后测试日志SHA256=`5ad4ca130192568295f721b1730212302f6fdcbbcfeac0964126d6418b9566d1`，JSON/链接/表格/来源与diff静态检查见ignored static_checks.json；无代码变更或新增PDE。
