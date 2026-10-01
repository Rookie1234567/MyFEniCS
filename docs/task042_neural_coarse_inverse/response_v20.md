# Response V20：固定p3 ILU(0)与40端口校正收口

按Review V17完成S0、N、P0、P40及冻结后的独立V；完整资格 **0/5**。本批实际存在全局p3不完全因子，登记 **GLOBAL_P3_INCOMPLETE_FACTOR_PRESENT**，没有global p4因子、完整S/barS物化、private audit CSR、hidden fallback或hidden训练。旧负结果保留。

ILU(0)把原有限元trace体块做固定稀疏三角近似，把残差变成耦合修正，再由原方程检验；它增加K装配、因子及三角作用成本。P40再用同一因子和40维小系统纳入全部端口耦合，付出40次体块解和每次端口提取/小解成本。它们都没有替换原物理方程或准确参考。

| 路线 | 周期 | 原rho起点 | 原rho最终 | 下降% | S+SH | charged wall(s) | 停止原因 |
|---|---|---|---|---|---|---|---|
| N | 4 | 9.67833470962e-06 | 9.39226219695e-06 | 2.95580305139 | 1052 | 193.57554083 | FIXED_CYCLE_LIMIT |
| P0 | 4 | 9.67833470962e-06 | 9.6529428923e-06 | 0.262357296786 | 1056 | 281.796204941 | FIXED_PROGRESS_RULE_STOP |
| P40 | 4 | 9.67833470962e-06 | 9.63671604509e-06 | 0.430018859409 | 1056 | 330.972634754 | FIXED_PROGRESS_RULE_STOP |


三路线同一V19 L-GPOLY暖原点，独立开始；每周期GMRES256、M=None、tol=0、atol=8.267827694851709e-10，实际1024个Arnoldi步/路线。返回先原子保存y，再By/trace，close返回完整18184维z，port=z[18144:]。info=1仅为周期用尽。原端口/恢复/identity和slave检查通过，不等于原Schur/native通过。原方程正式门限仍1e-6。

P0/P40四周期原rho分别只下降约0.26236%/0.43002%，均低于继续的10%；P40略优于P0，但无PC的N残差更低。PC最佳相对起点改善仅1.004318760倍，未达原方程通过或10倍改善，因此T迁移/C零trace **not_run**。这不是冷启动负结果，也不是资源等待。

| 固定状态 | Schur≤1e-6 | native≤1e-6 | 独立total-native≤1e-6 | 散射E≤1e-4 | 散射curl≤1e-4 | 逐通道功率差≤1e-6 | 完整合格 |
|---|---|---|---|---|---|---|---|
| V19-L-GPOLY-FINAL | 9.67833470962e-06 | 3.75329480007e-06 | 1.30239098725e-06 | 7.95003214967e-05 | 7.9510166913e-05 | 1.7855346417e-06 | False |
| V19-L-GNN-FINAL | 1.44393838546e-05 | 5.59964766271e-06 | 1.94307429584e-06 | 9.70793047547e-05 | 9.7083009907e-05 | 5.64706064632e-06 | False |
| N-FINAL | 9.39226219695e-06 | 3.64235479781e-06 | 1.26389487382e-06 | 7.94653797293e-05 | 7.9475449076e-05 | 1.80752527346e-06 | False |
| P0-FINAL | 9.6529428923e-06 | 3.74344775649e-06 | 1.29897406907e-06 | 7.9499323532e-05 | 7.95092428958e-05 | 1.78576534016e-06 | False |
| P40-FINAL | 9.63671604509e-06 | 3.73715492465e-06 | 1.29679046124e-06 | 7.94990639533e-05 | 7.9509037748e-05 | 1.78593763034e-06 | False |


总/散射E、curl/H、selected复E/H及完整40复通道逐项通过本次场幅门限，但原方程和逐通道功率仍失败。所有状态最大逐通道功率差均高于1e-6，R/T/A/A_volume与能量单项通过不能替代完整资格。N场误差小幅改善，PC增量更小；P40功率误差略恶化。**FIXED_ILU0_PORT_NO_SIGNIFICANT_BENEFIT**；未取得MICRO资格、神经增量或同严格精度加速。

正式actual source `d41470d17d2babf29fabb0960886b0f60ae2aceb`，不是最后文档HEAD。分支`task42_neural_coarse_inverse`、upstream`origin/task42_neural_coarse_inverse`、唯一worktree`/home/fenics/Projects/NN-Lab`、base`ccd357885f7f9be84efe3be07868cc94f13d93fc`。origin与canonical common Git已现场核对，仅同分支非交互fetch/安全快进，未操作其他worktree。

正式五run监督wall **874.948403421s**，launch wall 881.890304327s；辅助监督wall 75.529041533s，失败小测试也计费。正式累计下界 **67488.474122006s**，历史辅助unknown保留，不是一个成功解的时间。同时整树采样峰 **934690816B（0.870499GiB）**，own swap/VRAM0。父队列与子run及PC嵌套计时不重复相加。

固定start为2026-10-01 21:33:21 +08:00，重负载截止2026-10-02 01:03:21、总截止01:33:21。正式V监督及清场在2026-10-01 22:28:02 +08:00结束，处于窗口内。恢复上下文后的实时核验为2026-10-02 06:46:42 +08:00，发现总截止已经过去：**TOTAL_ELAPSED_NOT_COMPLIANT**。压缩摘要中的旧时间不能替代实时钟；不猜测间隔原因、不扣除未知时间、不重置预算。新reader测试因剩余额度0未启动，未验证代码留ignored，后续仅低负载保存/清场/交付，超时事实保留。不能声称本批满足4小时端到端合同。

MPI1、现场逐run CPU0资格、数学线程1/Loader0、GPU不用，独立FE环境/缓存、自有锁、0.5秒整树12/16GiB监督及ownswap0。既有heavy存在但不修改邻任务；正式期间PSI full avg10最大0，资源重入/冷却0。无cgroup委派，不称kernel连续硬限额或绝对零干扰；全部成本shared-workstation，邻任务影响与无争用性能INCONCLUSIVE。

唯一下一建议：申请一次相同K、同level0/shift NONE、固定几何实体邻接ordering的ILU(0)短对照，先做容量/原作用/线性资格，再同一L-GPOLY起点最多四周期。当前只证明natural固定规格无显著收益，尚不能证明ordering是唯一原因；不扫描ordering或shift，本批未实施。

真实source提交前focused回归最终38 passed，compileall/git diff --check通过；七个新dat实际schema验证及真实PC→GMRES→close→保存→audit链通过。两个计划内测试fixture失败保留，正式求解重放0、意外根因修复0。后置reader只重算raw hash/数组/Gate，EVIDENCE_CONSISTENT；其新增mutation pytest因截止not_run，未将未验证代码加入Git。Ruff不可用、full pytest/MPI2/4/CI not_run。

独立REF7实际native3.0179630439596658e-12、独立total-native1.4374448661883937e-12，未置零；只在求解/PC选择/hash冻结后读取，无参考反馈。没有Q/U/R读取、新准确LU、p4参考、p6、最大模型或材料扫描。

完整数值与成本见[详细结果](outcomes/fixed_p3_ilu0_port_v20.md)、[原Gate](outcomes/records/qualification_and_dispatch_v20.json)、[source/run](outcomes/records/run_index_v20.json)、[费用](outcomes/records/resource_costs_v20.json)、[40复通道](outcomes/records/channel_observables_v20.csv)、[截止事实](outcomes/records/deadline_stop_v20.json)。因子实际逐主元 extrema 未导出，unknown；现场默认zeroPivot及PC.view/因子nnz与重复/复线性证据已保留，不用零主元未报错推断主元安全下界。

本地Markdown结构与链接检查单列；精确GitHub页没有视觉证据，NOT_VERIFIED。仅推送执行分支，清理自有进程后停止等待review，不merge。完整最终HEAD见交付回执。
