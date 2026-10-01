# V19：固定R末态的原方程抛光与方向保留对照

## 结果范围与资格

P在每个周期重新搜索256个方向，只留下当前解；L额外保留本路线最近至多3个修正方向，用于减少下个周期重复搜索。两者都继续解完整原方程，保留40端口和单元内部的原恢复。这里改变的是重启之间保存的信息，没有训练网络、改变材料或缩减物理未知量。

只处理原0.7nm micro（384hex/p3/h0.175nm/q15；缺口三维非可分几何；grazing1度/azimuth0/s；双Floquet/DtN）。全FE34050含18144trace、13824内部、2082slave，20上+20下端口，完整z18184。此micro不是目标规模，最终0.7nm/48小时资格仍NOT_QUALIFIED。

| 范围 | 实际工作／边界 |
|---|---|
| C0 | 两个实际V18-R末态hash及重闭合；短回归和事务测试；无新Q/image/GK |
| P/L | 四条独立物理校正；同库同R原点、零累计校正；无warm start/参考 |
| VERIFY | 全部solver冻结退出后，一次FE环境审核8个去重固定状态；读取旧REF7，无新LU |
| 当前资格 | FIELD_AND_EQUATION_PROGRESS_NOT_QUALIFIED；完整通过0/8 |
| 神经贡献 | 无hidden训练；两条lineage共同随机神经G0；GPOLY不称完全无神经 |
| 未运行 | 新p4参考、目标模型、GPU、p6、基或PC扩容、oldGK续算、监督拟合、merge |

| 方法／库 | 实际调用 | 原rho起点→最终 | 本路线S+SH | charged wall(s) | 停止原因 |
|---|---|---|---|---|---|
| P_GPOLY | 64 | 0.000146307718165 → 2.23358499521e-05 | 16768 | 2279.93663295 | FIXED_64_CYCLE_LIMIT |
| P_GNN | 64 | 0.000199556374692 → 3.24881797774e-05 | 16768 | 2261.5433094 | FIXED_64_CYCLE_LIMIT |
| L_GPOLY | 64 | 0.000146307718165 → 9.67833470962e-06 | 16962 | 2298.25489228 | FIXED_64_CYCLE_LIMIT |
| L_GNN | 64 | 0.000199556374692 → 1.44393838546e-05 | 16962 | 2327.33009045 | FIXED_64_CYCLE_LIMIT |


| 冻结状态／同一0.7nm micro | 原Schur≤1e-6 | 原native≤1e-6 | 独立total-native≤1e-6 | 散射E≤1e-4 | 散射curl≤1e-4 | 完整资格 |
|---|---|---|---|---|---|---|
| V18-R-GPOLY | 0.000146307718165 | 5.67386863796e-05 | 1.96882893595e-05 | 8.07999012193e-05 | 7.98192590218e-05 | FAIL |
| P_GPOLY-FINAL | 2.23358499521e-05 | 8.66192707661e-06 | 3.0056833815e-06 | 7.99097168553e-05 | 7.98938859115e-05 | FAIL |
| L_GPOLY-FINAL | 9.67833470962e-06 | 3.75329480007e-06 | 1.30239098725e-06 | 7.95003214967e-05 | 7.9510166913e-05 | FAIL |
| P_GPOLY-CYCLE8 | 6.80805905911e-05 | 2.64019104846e-05 | 9.1614467379e-06 | 8.01429875488e-05 | 7.98921410883e-05 | FAIL |
| V18-R-GNN | 0.000199556374692 | 7.7388716746e-05 | 2.68538372247e-05 | 0.000100199130834 | 9.8749639854e-05 | FAIL |
| P_GNN-FINAL | 3.24881797774e-05 | 1.25990389751e-05 | 4.37185878872e-06 | 9.76389690217e-05 | 9.76039356484e-05 | FAIL |
| L_GNN-FINAL | 1.44393838546e-05 | 5.59964766271e-06 | 1.94307429584e-06 | 9.70793047547e-05 | 9.7083009907e-05 | FAIL |
| P_GNN-CYCLE8 | 9.11307000429e-05 | 3.53408300959e-05 | 1.22632463571e-05 | 9.92146330721e-05 | 9.88453864041e-05 | FAIL |


## 起点、物理与源码身份

| 项目 | 冻结身份 |
|---|---|
| branch/upstream | task42_neural_coarse_inverse / origin/task42_neural_coarse_inverse |
| worktree/common Git | /home/fenics/Projects/NN-Lab / /home/fenics/Projects/Maxwell3D-Lab/task-repository.git |
| origin | git@github-myfenics:Rookie1234567/MyFEniCS.git |
| base | ccd357885f7f9be84efe3be07868cc94f13d93fc |
| Review V16 | 5b489b7264b75a9461577303ff0f6bc8907c19dd；安全快进，没有reset/覆写/其他worktree操作 |
| actual numerical source | b58919a4a0dcd677b915eb7d9bbd314520aef0e0；正式运行前commit clean，文档HEAD不冒充运行源码 |
| 材料canonical | input/materials/si_optical_constants_v1.json，SI_OPTICAL_CONSTANTS_USER_20260929_V1 |
| 所选Si | source0.699999988明确alias到nominal0.7；n=0.999885140474+4.32477054e-6i，epsilon=n*n；各Si/背景/下端口一致 |
| material SHA256 | 55aa34e55c5e3cc35f6849eddbd3bcc72d3b694d32bc4885299ef373acd676a2 |
| physical SHA256 | 2b532f91550316b16a304f3be9ae78605816b5a2aba556f548b5bd794f82e6de |
| modes SHA256 | 93795b53d7c5aef69af66b4ff0a56fa46515771f1ec43332ec929970270ea262 |
| original action SHA256 | 9196edb807b534217d0c0eb78882125341342784a48ef20ebe2d9421fe636454 |
| REF7 SHA256 | a0610a5a55e7508196b17277e706595c33e4398ace82b245f70b656e6b9ed355 |

两R-FINAL实际NPZ/z hash、路径、source、mode及历史账见[input lineage](records/input_lineage_v19.json)，本批不从旧标量补造向量、不从G256或V17重新开始。所有正式one-run经scripts/run_case.py；每个8周期slice有自己的input_original/resolved/manifest/hash，继承同一窗口。旧V18目录只读，V19缓存/ledger/artifact/rolling slots独立。研究设计已参考历史REF7审核，不能称新的blind heldout；本轮求解仍不读取其数组。

## 数学与接口

H是原凝聚Hhat，不是Hp。原方程S=[K,C;F,H]，barS=K-CH^-1 F，barb=bt-CH^-1 bp。固定tb的校正rhs为rb=barb-barS*tb；L累计求x，实际trace为tb+x，port=H^-1(bp-F*trace)。P使用逐周期精确残差校正，与该累计表达精确算术等价，原作用配对检查保持。

P为restart256/M=None/maxiter1/pr_norm/相对tol0。L现场SciPy1.11.4，inner_m256/outer_k3/maxiter1/M=None/prepend_outer_v=False/store_outer_Av=False；方法登记BOUNDARY_DRIVEN_LGMRES256_K3。L callback只数外层，内部Arnoldiunknown；每次调用会重置某些局部容差控制量，不宣称与一条长调用逐位一致。

两方法atol始终1e-8*原完整norm(b)，正式原方程门限1e-6。端口没有删除/经验权重。C0实际10次S/0SH、2原audit，两R重闭合与保存残差差0；原恢复/identity≤1e-10、slave0。真实第一次P/L调用计入正式周期，无重复smoke。原close始终完整返回z，caller只切40port。

原action packet与LinearOperator共享，无global S/barS、正规方程、global p4因子、ILU/Riesz/fallback；未加载Q/U/R或旧GK。保留原单元内部恢复和40维Hhat小块解，其成本不是零。独立native/场审核另复用原FE装配，未声称全流程无装配。

## 事务、队列和分流

返回→原子proposed→close→audit_pending→原audit→commit；L先copy待修改x和方向列表，返回时保存同一边界的x/t/有序方向/hash。Av=None，由原作用重算。两个滚动generation只切commit最后，半写或kill保留合法旧边界；已返回但close/audit失败只补审，不重算Arnoldi。未知费用保守扣320上界，不用callback重造向量。

方向最多3，derived持久数组870912B（0.831MiB），这不是全过程RSS。实际inventory与跨调用prior hash见[checkpoint](records/checkpoint_inventory_v19.json)、[逐周期](records/polish_cycles_v19.csv)，fault tests覆盖独立读回继续、错误identity、未更新、info1及零rhs。L正常returned update才登记；P内步实测，L以底层原作用数比较。

四路线按P-GPOLY8→P-GNN8→L-GPOLY8→L-GNN8，再8周期轮转；最近8周期原rho=max(Schur,native,固定完整b端口)下降至少5%才延长。停止原因见表与[配额](records/quota_dispatch_v19.json)，不是数学不可能的证明。选最终状态只用合法commit原rho，REF7此前封存。FIRST_PASS不可覆盖，至多2可选抛光不改变成功门限。

## 冻结后的独立场与功率

误差相对同mesh/p3 REF7。total/scattered E/H由原FE恢复，scaled-curl与磁场对应；selected复E/H及所有通道保留复数，未校相位或重归一化。原未凝聚native值独立重算，参考非零native为 1.43744486619e-12。参考只在全部队列冻结且退出后读取，无反馈和验证后计算。

| 状态 | total E | total curl/H | selected复E | selected复H | 40复通道 | port/完整b | 恢复 | slave |
|---|---|---|---|---|---|---|---|---|
| V18-R-GPOLY | 8.45529144189e-06 | 8.35283082958e-06 | 9.40360981282e-06 | 7.16586310687e-06 | 3.89742720046e-06 | 1.34194767256e-16 | 4.67787038536e-13 | 0 |
| P_GPOLY-FINAL | 8.3621382558e-06 | 8.36064029553e-06 | 9.42882490294e-06 | 7.06599097443e-06 | 3.72368357831e-06 | 1.30187992988e-16 | 4.68902769848e-13 | 0 |
| L_GPOLY-FINAL | 8.31929715055e-06 | 8.32048532642e-06 | 9.39005817635e-06 | 7.13067915795e-06 | 3.67761601799e-06 | 1.35177830335e-16 | 4.72787175389e-13 | 0 |
| P_GPOLY-CYCLE8 | 8.38654882646e-06 | 8.36045770535e-06 | 9.40892850301e-06 | 7.14687942076e-06 | 3.89356109612e-06 | 1.62736325116e-17 | 4.67579955617e-13 | 0 |
| V18-R-GNN | 1.04853204105e-05 | 1.03338347949e-05 | 1.17717218896e-05 | 8.77971120404e-06 | 6.57195853012e-06 | 1.84831403748e-16 | 4.73378020261e-13 | 0 |
| P_GNN-FINAL | 1.02174127283e-05 | 1.02139405046e-05 | 1.14742649191e-05 | 8.81344109191e-06 | 6.62007785233e-06 | 1.84113608258e-16 | 4.72569681481e-13 | 0 |
| L_GNN-FINAL | 1.01588467596e-05 | 1.01594272876e-05 | 1.14309557932e-05 | 8.65583760969e-06 | 6.09112358451e-06 | 1.62735202354e-17 | 4.74098068318e-13 | 0 |
| P_GNN-CYCLE8 | 1.03822978155e-05 | 1.03438543659e-05 | 1.17190906548e-05 | 8.77644611852e-06 | 6.47710329054e-06 | 1.35177823226e-16 | 4.67395481488e-13 | 0 |


所有场门限1e-4；恢复/identity1e-10、slave0；原方程1e-6。全40复通道及参考误差见[channel CSV](records/channel_observables_v19.csv)，原键/极化/参考面不改变。功率下表未合格行仅UNQUALIFIED_DIAGNOSTIC，不能发布official R/T/A。

| 状态／未合格时仅diagnostic | R00_s | R00_p | R00_total | R | T | A_balance | A_volume | 最大通道功率差≤1e-6 | 能量闭合≤1e-5 |
|---|---|---|---|---|---|---|---|---|---|
| V18-R-GPOLY | 0.117644803271 | 1.12739382648e-12 | 0.117644803272 | 0.117645860404 | 0.877049371318 | 0.00530476827775 | 0.00530640587045 | 1.58806402928e-06 | 1.63759269856e-06 |
| P_GPOLY-FINAL | 0.117644934659 | 1.25423066187e-12 | 0.11764493466 | 0.117645991437 | 0.877049439206 | 0.00530456935636 | 0.00530640666653 | 1.65641122762e-06 | 1.83731017511e-06 |
| L_GPOLY-FINAL | 0.117644927761 | 1.03447616421e-12 | 0.117644927762 | 0.117645984704 | 0.877049568498 | 0.0053044467988 | 0.00530640713048 | 1.7855346417e-06 | 1.9603316801e-06 |
| P_GPOLY-CYCLE8 | 0.117644799485 | 1.15935949396e-12 | 0.117644799486 | 0.117645857206 | 0.877049356058 | 0.00530478673573 | 0.00530640602401 | 1.57302214476e-06 | 1.61928827636e-06 |
| V18-R-GNN | 0.117640301228 | 5.37072209844e-13 | 0.117640301228 | 0.117641358097 | 0.877041476614 | 0.00531716528874 | 0.00530635589842 | 6.30612229691e-06 | 1.08093903212e-05 |
| P_GNN-FINAL | 0.117640293177 | 6.15297087626e-13 | 0.117640293178 | 0.117641350138 | 0.877041403738 | 0.00531724612356 | 0.00530635911728 | 6.37923197189e-06 | 1.08870062793e-05 |
| L_GNN-FINAL | 0.117640790554 | 4.75697216595e-13 | 0.117640790555 | 0.117641847495 | 0.877042135891 | 0.00531601661368 | 0.00530636059989 | 5.64706064632e-06 | 9.65601379288e-06 |
| P_GNN-CYCLE8 | 0.11764036516 | 5.01637772327e-13 | 0.11764036516 | 0.117641422165 | 0.877041638989 | 0.0053169388464 | 0.00530635635187 | 6.14351668549e-06 | 1.05824945315e-05 |


R/T/A/A_volume绝对差≤1e-5、每通道功率差≤1e-6、能量闭合≤1e-5，全量Gate数字见[field checks](records/field_channel_checks_v19.json)。R00_s/p/total分列，无含糊零级定义。只有原方程通过且全部同离散指标通过才称MICRO_DISCRETE_PASS_ONLY，不代表离散或目标规模资格。

## 工作量、资源与费用

新增正式one-run监督wall **9199.970576s**；本批辅助监督wall **102.206160s**（截至费用快照，含失败小测试；后续交付开销计入总elapsed）。V6起formal累计下界 **66613.525719s**，旧辅助unknown保持。同时整树采样峰 **796585984B（0.741879GiB）**，own swap/VRAM **0B**。父队列和子one-run计时嵌套，不重复相加；全部成本标shared-workstation。

统一路线wall B=2382s，队列开始冻结；全批S/SH 67543/80000、audit 269/300、场 8/12、新A/image/Q/GK0。没有将未运行路线额度转移；单路线≤19500原作用和64调用。所有失败测试、拒绝/未返回上界、I/O和审核均记账。

same-work的实际审核点见[same work CSV](records/same_work_curves_v19.csv)：按相同完整周期、近邻原作用数和wall读实际值，不插值造结果。路线setup/load及周期内原作用、端口与审核的嵌套计时不能相加。本批保存方向的优势最多是该原点固定校正收益，没有新的神经训练增量；未相同严格精度通过时不称正式加速。

窗口08:46:41Z接手，12:16:41Z停重负载，12:46:41Z截止，未刷新。前置resident规划2GiB≤8GiB；现场系统余量max(128GiB,total10%)加邻增长128GiB加本任务16GiB。MPI1、实时选空闲物理核并避忙SMT、数学/Torch1、DataLoader0；自身nice10/I/O idle，独立cache、own lock、0.5s整树监督。没有cgroup委派，不能宣称连续内核hard cap；监督覆盖所有后代并先做超时/清场测试。

PSI保护仍full avg10≥0.1%连续3次5s；资源重入0，冷却0.0s。监督数据未见相关持续压力，不据此宣称零干扰；没有可比邻任务阶段速度实验，影响INCONCLUSIVE。没有改邻任务/锁/优先级/环境/ABI/BLAS/CUDA，GPU不使用。新持久artifact/TMP/results逻辑合计 1020359436B，上限2GiB；全Task042原artifact容量另记，旧证据没有删除。

求解队列期间系统全局pswpin/pswpout分别增加277288/279795页；此系统量不能归因于Task042，自身进程树VmSwap始终采样0。原监测器字段沿用WSL-global标签，现场实际为原生Linux，该标签不代表WSL环境或本任务发生swap。

收尾的第二次资源核验未能确认空闲物理核，未准入任何新负载；其失败日志/费用保留，不修改资源保护、不自动重启。独立主机只读核验确认V19数值actor为空、自有锁可用、所有已结束监督器后代清场；[清场记录](records/delivery_cleanup_v19.json)给出时间快照。文档、commit/push的低负载收尾计入同一不可刷新窗口。

费用分开：本批增量实测；上游必要建基/image/LSQR通过V14–V18lineage链接保留；多路径研究尝试累计formal下界。旧缺失辅助和每条链精确分摊unknown，不补造48小时预算。两库R逻辑12831/11903不同，不能说上游成本相同。当前低RSS不代表上游大基和目标规模容量已解决。

## 测试、修复与边界

首次接口测试25 passed/3 failed，两个preformal根因（event计数字段冲突；历史测试夹具过晚隔离真实FROZEN目录）最小修复后28 passed；debug+重测包络<103s，单根因时间unknown。后置41/2因V19夹具同样在隔离前读真实FROZEN，测试专用一行修复后43 passed。E01为sandbox MPI socket EPERM执行范围修复，同源同ABI只重放冻结VERIFY1次、solver周期0次；该失败保守64作用/2audit不退账。保守根因总数4/4、修复时间包络≤483s/2400s；原数值实现source始终不变，旧证据未改。

四条路线各64次仍失败，本次固定无PC抛光队列到上限收口。L最终原Schur比P约低56%–57%，散射E/curl只小幅变化；GPOLY最大通道功率差由原点1.5880640292786907e-6增至1.7855346416961737e-6。残差下降不能等同全部物理量改善，不能据此宣布唯一根因或新的神经贡献。

最终reader只读hash与已存数组，原作用/新求解0，独立从raw数字重算Gate；tests、实际6dat schema/stage/validate、compile与publication见[test summary](test_summary.md)。没有CI/Ruff/full pytest/MPI2/4，通过项不可外推。GitHub精确Review16页面无视觉证据NOT_VERIFIED，本地表格/math围栏/链接检查不冒充网页显示PASS。

唯一下一建议：仅申请一个固定p3全trace ILU(0)预条件的短资格对照：先评估原p3 trace体块装配与因子容量、核对同一barS及完整40端口；Gate通过后从L-GPOLY冻结末态做一次预条件GMRES256周期。此方案需要额外装配和因子内存，须由下一份review明确预算与准入，不能沿用本批低RSS作容量保证；不扫描参数、不使用global p4 LU。本批未实施。

只建议、不实施。当前固定无PC抛光队列已收口；任何更强机制需后续review。新p4参考、目标模型、GPU、p6和merge not_run。原task/review/response/raw逐字保留，导航和总账只新增V19前缀。
