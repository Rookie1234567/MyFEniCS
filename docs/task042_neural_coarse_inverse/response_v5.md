# Task042 Response V5：固定对象失效定位完成

12/12共同state均可用；D0–D4完成，终态 `FIXED_OPERATOR_LOCALIZATION_COMPLETE`。本轮支持当前残差覆盖不足及部分固定组合利用不佳，未找到真实近零补空间作用的充分证据；允许多因素并存，不宣称唯一根因。原strict资格仍 `NOT_QUALIFIED`，没有新完整求解通过。

| 必答项 | measured结果 / 边界 | 证据 |
|---|---|---|
| 同一组r/e覆盖 | 物理初态OLDPOD eta_r/eta_e=0.9990665004/0.2216303110；ERROR=0.9997844639/0.7134416377。其余同12状态全部列出 | [覆盖CSV](outcomes/records/coverage_v5.csv) |
| 同r的B/C/B2与保留方向 | 初始port-only：B最优0.9845924930，OLDPOD B2=0.9926200741、ZB-LS=0.6171863522；ERROR B2=0.9872461168、ZB-LS=0.7423358405。原A4/port未严格合格，Schur改善不能当物理解通过 | [192审核](outcomes/records/same_residual_actions_v5.csv)、[分解/系数](outcomes/records/action_details_v5.json) |
| 补空间完整像 | 有效探针rank16/16；OLDPOD完整TV最小奇异值4.771224799，ERROR=3.034800156；独立最弱见证Tv/Hv=0.7646470682/0.368869284 | [完整输出](outcomes/records/complement_probes_v5.json) |
| 尚未确定 | 未采样补空间/非正规累积、全局谱、空间内关键方向与方程尺度的相互作用。小VᴴTV不能证明真实T/B2奇异，有限反事实不能保证augmentation收敛 | [D4](outcomes/records/localization_decisions_v5.json) |
| 原方程 / 历史 | 9历史最终native逐项重现；3旧准确参考资格通过，192诊断修正strict0/192；V1–V4负结果保留，不恢复旧KSP | [状态](outcomes/records/common_state_manifest_v5.json)、[离线teacher](outcomes/records/teacher_exception_v5.json) |
| 新运行成本 | wall1144.401529s，整树采样RSS峰1135407104B=1.057430GiB，own swap0；四次normal release / 后代清场 | [run index](outcomes/records/run_index_v5.json) |
| 实现 / 静态检查 | source5d…前检55 passed、adapter/准入/监督9 passed，raw independent Gate通过；最终Markdown5与局部静态见记录，旧checker基线问题不清理 | [前检](outcomes/records/pre_run_checks_v5.json)、[最终](outcomes/records/static_checks_v5.json) |

完整解释、所有同向量对照、绝对量/分母、容量及selective merge分组见[中心结果](outcomes/failure_localization_v5.md)。残差/误差是canonical trace＋80port complex128坐标；D1只读旧准确teacher0/10/11，原归一化还原，准确解减当前解得到e，Se=r−r_star核验。teacher独立进程释放，只输出标量/hash，D2/D3不加载teacher、不更改基或初值。

唯一模型仍原Si13.5nm/1°/s，p6h10对应p4，252cells、53084FE行/21824reduced/8184464NNZ、完整80通道。两套Z/U/R rank128、几何R-GEO-CELL80-v3和S字节/哈希绑定不变；构造前representation/workspace296234496B、因子302309536B均小于512MiB，252个≤272行patch与小R实测核对。没有global p4 factor、private audit CSR、fallback、在线teacher、新NN或新KSP。诊断自检不是strict1e-10返回资格。

Git开始核实本地c3bcb0e6b9eec87eca3bdeb54f71d524c01a6ceb，clean/own lock空闲无活跃Task042；仅fetch同执行分支并快进到Review `91c4a0dbfa2e8a14df273eab5e27726059d7c835`，未reset/rewrite或操作邻worktree。四正式FE经4个独立one-run dat，启动前clean实现source `5d82651af0f723c73487783deb43969f05d46ed3`，upstream始终origin/task42_neural_coarse_inverse；common Git `/home/fenics/Projects/Maxwell3D-Lab/task-repository.git`，NN-Lab为canonical linked worktree。冻结base `ccd357885f7f9be84efe3be07868cc94f13d93fc` 与初始文档anchor `f8c51c8e614edc806cf72120ac2cfd14ae8b62f7`均保留在历史。最终完整交付HEAD由推送回执报告，不能将文档HEAD代替运行source。

本批准确继续用户只对Task042的受控共享CPU授权，覆盖原task §2.3 heavy与全机独占限制，未宣称F0已正式review通过。实时选核后D0/D1/OLDPOD实际CPU0、ERROR实际CPU13（非永久配置）、MPI1/实际BLAS1，Task042 own lock、整树16GiB hard/12GiB warn/自身swap0与系统reserve＋邻增长128GiB不变；nice10/idleI/O仅自身设置。cgroup未委派，真实0.5s采样停树而非内核连续限制；无GPU、ABI升级或环境重装。所有可写cache/output都在NN-Lab，原库prefix只读，没有改邻任务、其亲和性/环境/priority/watchdog/锁。未观测持续PSI压力，邻CPU推进和短记录只读；缺可比阶段指标，影响/性能inconclusive，不承诺零干扰或无争用加速。全部费用标shared-workstation，嵌套timer不重复累计，[辅助失败及费用](outcomes/records/post_checks_v5.json)另记。

Review V2实际GitHub HTML5表/7公式块通过，未改review；新发布表格/公式绑定实际HEAD，见[Review渲染](outcomes/records/review_render_check_v5.json)和[发布检查](outcomes/records/publication_checks_v5.json)。旧schema/总账checker问题与Review91完全相同，未触发全仓清理、full pytest或昂贵重放。

**唯一下一最小试验（仅建议）：** 仅在已消费port-only RHS index10上，对比一条保留原Br＋冻结OLDPOD Z搜索方向的有界augmentation组织，其他S/B/Z/rank128、RIGHT FGMRES32/max256、原A4/port/恢复1e-10和资源预算保持；原B2历史作对照。它只检验固定组合是否丢失可用方向，不预测必然收敛。需下一review授权后实施。

停止原因是本次有限D0–D4完成；不自动实施建议。seed42062016项fresh仍未消费、未生成/读取；F5/p6/短波/GPU/新训练/global谱及official R/T/A/A_volume/场/衍射均not_run。只推送task42_neural_coarse_inverse，推送后等ChatGPT review，不merge master/其他分支。
