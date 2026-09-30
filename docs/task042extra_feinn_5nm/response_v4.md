# Task42extra Response V4：持久检查点与 Adam500 后段重放

| 身份 | 准确值 |
| --- | --- |
| branch / worktree | `task42extra_feinn_5nm`；`/home/fenics/Projects/NN-Lab-V2`，原生 Linux canonical linked worktree |
| common Git | `/home/fenics/Projects/Maxwell3D-Lab/task-repository.git`，现场核对；旧 NN-Lab 只读 |
| 本文生成前、独立复验完成时 HEAD | `c8a057a46645542aaa17a38b78e64c6add80cb68`；运行时工作树 clean |
| R0 / 唯一 R1 实际 source | `538c6320679d9a3ce3efe5e6d6ebef062963f601` |
| R2 实际 source | `c8a057a46645542aaa17a38b78e64c6add80cb68`；后续文档提交不是训练源码 |
| 原冻结 base / 新 review | `fbac3d8777fcfd897d93b898cb9f460f79ddd6ff` / `4dc7c38b60acf2a5ee3d9c6b9770b084a874fb04`，均为祖先 |
| upstream 配置 | remote=`origin`，merge=`refs/heads/task42extra_feinn_5nm`；共享 fetch 映射不含本分支，`@{upstream}`不可解析 |
| 本轮远端核对 | 用命令级精确 refspec 与 `refs/remotes/origin/task42extra_feinn_5nm`；未修改共享配置或其他 worktree |

最终交付 HEAD、显式 tracking ref 的 ahead/behind 和工作树状态由推送回执及最终答复给出；上表是实算 source 和成文前 HEAD，不是把文档 HEAD 当运行源码。入口、原始 run、完整 hash 和费用见 [run index](outcomes/records/run_index_v4.json) 与 [资源账](outcomes/records/resource_costs_v4.json)。

本轮取得了**保存完整参数及匹配优化器、可独立复验的终态**。G 场误差由 Adam500 的 `0.2008211341` 降至 `0.01387169130`，但未满足表示诊断的部分门限 `0.01`，严格原方程/场/功率也未通过，分类为 `REPRESENTATION_OR_FIT_OPTIMIZATION_UNRESOLVED`。这说明本固定配置和预算内仍未达到要求，不能单独判断网络数学上无法表示。旧 V3 仍为 `INTERRUPTED_FIT_NO_FINAL_STATE`，第817次参数/优化器仍为 `NOT_RETAINED`，旧观察825仅是日志下界，失联原因仍 unknown。

本轮有一个明确执行偏差：C1 的训练截止时钟在 worker 导入后开始，遗漏了这段开销。实际整个 launcher 到 summary 为 `10690.413s`，监督 wall 为 `10688.702s`，都小于10800s；但闭包收口的120s留白被前置开销侵占，未满足“至少120s”保留规则。退出后全 launcher 剩余 `109.587s`、监督口径剩余 `111.298s`，它们是观测余量，不冒称最初保存留白。C2 已改为 launcher 单调时钟、150s收口留白，定向计时测试通过；**该修正未重新正式重放资格化，本轮没有第二次启动**。这项偏差与数值未达标分别记录，不把它改写为 OOM、失联或成功收敛。

## R0：保全资格及其边界

持久执行让整套 launcher、watchdog、worker 在任务独立 tmux 会话里继续运行；输出写任务文件，worker 仍受整树监督。成功落盘的完整step是保全边界：先写同目录临时文件、flush/fsync、原子替换，再更新指针并发布 committed 审核行。每代保存模型、buffers、参数顺序、完整 L-BFGS state、RNG、阶段/计数、source/输入/标签/矩 hash 和预算，保留最新两代及锚点/审核/终态。SIGKILL不保证执行finally，保证范围仅为此前已成功落盘的完整边界。

9项小问题测试及4类自身进程故障检查通过：保存/加载、Adam结束到 fresh L-BFGS 的路径等价，非零 strong-Wolfe 试探中的异常/预算回滚，原子写入中断、启动端退出及输出关闭、明确停止、监督死亡清场。后续计时及标签修正后的11项 targeted tests通过。[保全检查](outcomes/records/durability_checks_v4.json)是 C1 启动前的不可变小测试快照，其 `numerical_boundary_status=NOT_RUN`描述当时；后来真实 M5 资格见 [补充检查](outcomes/records/post_fit_checks_v4.json)及 run index。模拟断开不等于所有平台/cgroup回收路径通过。

真实 M5 只用了2次完整loss/gradient，没有更新参数；原 Adam500 文件 SHA256 `4e818a16b876ffd0776e74438654ca7de5632b1e17269a38e87749b5b3ad6a97` 通过。参数生成c差0、旧/新目标与梯度差0，E_G=`0.20082113406866917`、native=`14.263463207213235`，fresh L-BFGS 空历史。原 NPZ 没保存 center/half_width；它们按冻结几何及未改变的构造器重建，再用完整c与梯度配对资格化，不能说原buffers早已存盘。旧代码确实在保存 Adam500 后才创建 L-BFGS，故此次是特定切换边界重放，不是恢复第817次优化历史。

## R1：一次重放及真实工作量

| 固定模型与执行 / measured | 本轮值 | 解释 |
| --- | --- | --- |
| 路线 | `FEINN-REFERENCE-FIT-G-ADAM500-REPLAY` | 读取已知参考的监督表示诊断 |
| 模型 / 网络 | 5nm M5、384hex、p3/q15、31968独立复FE、40端口；3×64 tanh、6输出、8966实参数、FP64 | 边3744、面14400、内部13824全保留，物理/材料/边界不改 |
| inherited Adam / 新 Adam | 500 / 0 | 只加载阶段锚点，没有重算前500步 |
| 新完整闭包 / logical path | 2129 / 2629 | 闭包是一次完整loss＋gradient；L-BFGS线搜索可多次调用，并非epoch或接受更新次数 |
| 已提交边界闭包 / 完整外层step | 2122 / 93 | 第94次外层尝试在预算处回滚；7次额外试探费用保留 |
| 原方程审核 / 唯一正式启动 | 23 / 1 | 起末及每跨100闭包在持久态审核，未超40次 |
| 停止 / final | `WALL_BUDGET` / `DURABLE_BOUNDARY_REPLAY_COMPLETE` | 正常保存终态，不是优化收敛PASS |
| 新 Gram factor / Gsolve / Maxwell factor | 0 / 0 / 0 | fit闭包仅G matvec＋完整矩VJP；A/Aᴴ闭包调用0，审核另计 |
| G matvec / 存盘成本 | 2154次、95.4165s / 3.8402s | 计入父阶段wall，不重复加计 |
| 保留检查点payload | 88,078,236B | 对象/磁盘体积，不是RSS |

L-BFGS保持lr1/history20/strong-Wolfe/max_iter20/max_eval25/tolerance_grad1e-7/tolerance_change1e-9。接受更新量在外层step返回后计算；trial displacement单列。最新final模型、优化器、梯度和RNG与上一完整边界逐项相同。95代登记含锚点、93完整step、final；保留的固定点及完整文件hash见 [checkpoint index](outcomes/records/checkpoint_index_v4.json)。原V3至少825次与本轮2129次合计至少2954次实做拟合闭包，另有R0核验；旧后段的重复费用及失联3284s没有删除。

## R2：冻结后的独立审核

| 同一 M5 / 同p3参考 / measured | 原 Adam500 留存态 | V4 final | 预登记限值与结论 |
| --- | ---: | ---: | --- |
| G场误差 | 0.2008211341 | 0.01387169130 | 表示正/部分均要求三项≤0.001/0.01；未达部分 |
| 散射E L2 / scaled-curl | 0.1620127280 / 0.2017046510 | 0.01325124766 / 0.01388700270 | 严格各≤1e-4，失败 |
| total E L2 / scaled-curl | 0.111101 / 0.137924 | 0.009087097891 / 0.009495805966 | 严格各≤1e-4，失败 |
| 六点 total E / H_code | 0.112268 / 0.132886 | 0.009751978017 / 0.007167388173 | 严格≤1e-4，失败；全部点和散射量也保存 |
| native / augmented / 独立total原方程 | 14.263463 / 14.263463 / 6.756627642 | 1.608844720 / 1.608844720 / 0.7621125774 | 各≤1e-6，失败 |
| 40级原total / 真出射 / scattered复幅差 | 0.137244 / 0.0658706 / 0.243664 | 0.02134370402 / 0.01024394361 / 0.03789375775 | 各≤1e-4，失败；各用自身参考向量范数 |
| R/T/A_balance/A_volume | 0.828087/0.0419968/0.129916/0.171617 | 0.8130577901/0.03273817418/0.1542040357/0.1553880257 | 参考0.8124264991/0.03246239610/0.1551111048/0.1551111048；差超1e-5 |
| 能量闭合 / 最大逐通道功率差 | 0.0417012 / 0.0130081 | 0.001183989956 / 0.0003513448473 | ≤1e-5 / ≤1e-6，失败 |
| 参数→c / q30→q15 | 0 / 2.8584e-12 | 0 / 8.5141e-13 | ≤1e-12 / ≤1e-8，通过，仅为身份/求积资格 |

所有值是同离散的诊断，候选R/T/A不是official结果。完整40级复值、六点复E/H、绝对误差/实际分母、原air/substrate/grating/interface-near集合及能量重算见 [独立Gate](outcomes/records/gate_decisions_v4.json)；更详细的定义见 [durable replay](outcomes/durable_replay_v4.md)。常数μ_r=1下H_code=curl(E)/(i k0)，完整H相对L2差等于相应curl相对差；scaled-curl积分采用原1/k0尺度，G内积另用ell=5nm，不混称两个范数。port恢复及slave存储通过，不能替代失败的体方程。

ML与FE是独立进程，FE preflight确认complex128/int64、MPI1且Torch未导入。q30只复核冻结参数，没有改q15后重训。V1参考只读取，新MUMPS symbolic/numeric/solve计数全部0。

## 资源、标签与下一步

| 口径 / measured或保守计费 | 本轮值 | 边界 |
| --- | --- | --- |
| R0真实边界监督wall / 树RSS | 15.8439s / 533,176,320B | 轻核验2GiB内；整launcher计费22.0154s |
| 唯一R1监督wall / 树RSS峰 | 10688.7017s / 764,751,872B | 约0.71223GiB；CPU12现场准入，CPU-only/MPI1/线程1 |
| R2 ML / FE监督wall、树RSS | 17.5170s、523,923,456B / 18.1646s、584,249,344B | 串行，结束后清场 |
| 本页数值冻结时V4全账快照 | 10934.6917s，含直接/最终120s保守费用 | 后续checker/文档/浏览器费用追加在资源JSON，非最终账 |
| 旧累计 / 原16h余额（该快照） | 33070.5267s / 13594.7816s | 旧失联3284s完整保留；本批4h尚余3465.3083s |
| tmux管理开销 | 单次样本4,702,208B、swap0 | 在数值树外，稀疏样本不当连续峰值；wall已包含 |
| 自身swap / OOC | 全自有树采样swap0 / 未用 | 全机swap活动只观察，不能归罪本任务 |

无cgroup委派，沿用约0.5s整树同时RSS采样和自身停止，不冒称内核连续hard limit。每阶段系统余量加至少384GiB邻任务增长及自身预算现场准入；未暂停、终止、修改其他项目环境/亲和性/锁/watchdog。共享运行无法证明零干扰。历史Gram因子费用留旧账，本轮只加载146,851,456B稀疏G payload，不重新建立因子。没有full pytest、环境重装或旧E0/E1/P0重跑。

manifest、checkpoint和results均保留 `reference_used_for_training=true`、`pde_only_solve=false`、`production_initialization_allowed=false`、`pde_only_solver_qualified=false`、`official_candidate_results=false`。因此下降的场误差不构成神经求解增量，V1/V2无标签负结果不改。新review及必要V4页的GitHub实际渲染状态由 [渲染记录](outcomes/records/render_check_v4.json)给出，本地Markdown解析不能替代该检查。

已排除本次终态缺失、参数/完整矩配对错误、q15求积漂移及端口恢复这几类已测问题；仍不能区分固定网络表示限制、有限拟合预算和优化停滞，也未证明p/h离散或目标尺寸可用。**下一最小建议：先review这个完整终态与已修正但未再次正式验证的计时协议，另行决定是否授权区分表示和优化的单项诊断。** 本轮不继续训练、不接回无标签路线、不做p4、目标尺寸5nm或0.7nm；仅提交推送本分支后等待review，不合并。
