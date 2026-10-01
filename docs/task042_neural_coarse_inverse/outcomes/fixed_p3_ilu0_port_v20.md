# V20：固定p3不完全因子／端口机制对照

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

## 算子、容量和PC实况

保持原0.7nm/384hex/p3/h0.175/q15，Full3D非可分三维缺口，双Floquet、非零物理/内部/端口RHS、top20+bottom20。full34050、trace18144、internal13824、slave2082、z18184。canonical材料SI_OPTICAL_CONSTANTS_USER_20260929_V1，n=0.999885140474+4.32477054e-6i、epsilon=n*n，source0.699999988 alias nominal0.7，无插值。

K从原cell Schur及Floquet展开装配，合并重复贡献、保留结构零和方向。K仅PC，原ActionPacket/BarAction仍外层及审核。K/Kᴴ四个向量（两固定随机、实际trace、原残差方向）operation-relative最大9.058537194667937e-14；闭合与原作用差/norm(b)最大3.3095003716559877e-12。C/F/Hhat配对通过，不假定F=Cᴴ，Hhat不混为Hp。

规划在分配前完成：贡献nnz上界4497120、CSR上界108076040B、因子显式载荷上界217022992B、同时常驻规划3666561640B≤8GiB。actual K nnz3852576、CSR77124100B，SciPy CSR索引int32；PETSc副本int64，转换/副本/symbolic/numeric/workspace已计入保守规划。独立factor RSS unknown，PETSc MatInfo memory=0不是因子RSS0。

唯一SeqAIJ/COMM_SELF complex128/int64 native PCILU、levels0、natural、shift NONE、out-of-place，无drop/对角救援/外部options。现场zeroPivot=2.220446049250313e-14；setup无零主元错误、factor nz_used=3852576，逐主元极值未导出为unknown。K装配2.723545405s，三次相同因子setup1.213763643/1.312630234/1.620076418s；因one-run进程隔离重建，固定两PC作用跨进程配对通过，不称序列化因子。

PC重复差0、复线性operation-relative5.879253721114988e-14；诊断norm(r-KB0r)/norm(r)=40705.5596054827，说明该近似在该输入上单次作用偏差很大。它不是要求1e-10准确逆的Gate，也不是K的条件数或唯一失败根因。

P40保留40通道，W载荷11612160B，Jp cond2=3197257.074775157、40维solve operation-relative4.147725664824209e-17，setup4.890521413s，安全小解通过。P0 B0应用1040次/79.116167961s；P40 B0 1080次/85.808689240s，F1076次及小解1037次的实测时间详见费用。近似因子端口处理的微小收益不属于神经训练。

## 完整场／功率（UNQUALIFIED_DIAGNOSTIC，非official结果）

| 状态 | R00_s | R00_p | R00_total | R_total | T_total | A_balance | A_volume | 能量缺陷≤1e-5 |
|---|---|---|---|---|---|---|---|---|
| V19-L-GPOLY-FINAL | 0.117644927761 | 1.03447616421e-12 | 0.117644927762 | 0.117645984704 | 0.877049568498 | 0.0053044467988 | 0.00530640713048 | 1.9603316801e-06 |
| V19-L-GNN-FINAL | 0.117640790554 | 4.75697216595e-13 | 0.117640790555 | 0.117641847495 | 0.877042135891 | 0.00531601661368 | 0.00530636059989 | 9.65601379288e-06 |
| N-FINAL | 0.11764492882 | 1.01112753162e-12 | 0.117644928821 | 0.11764598577 | 0.877049590479 | 0.00530442375163 | 0.00530640713844 | 1.98338680613e-06 |
| P0-FINAL | 0.117644927698 | 1.0342094012e-12 | 0.117644927699 | 0.117645984641 | 0.877049568728 | 0.00530444663091 | 0.0053064071302 | 1.96049929135e-06 |
| P40-FINAL | 0.117644927706 | 1.03405975249e-12 | 0.117644927707 | 0.117645984649 | 0.8770495689 | 0.00530444645111 | 0.00530640713072 | 1.9606796049e-06 |


完整total/scattered E/H、scaled-curl、selected复场、40通道原键/极化/reference plane在[field记录](records/field_channel_checks_v20.json)及[通道CSV](records/channel_observables_v20.csv)。原native与独立total-native分母不同，两列保留。参考actual残差不强置零，无幅相校正、参考选点或验证后回训。

## 费用、数据身份与未运行项

全批charged S+SH3193、audit23、B0三角2124、辅助F1080、K装配1、同规格factor setup3、field states5。每路线1024真实Arnoldi更新，拒绝扩大后的not_run不冒充失败。新增持久artifact/日志/缓存快照261230355B（逻辑）/269545472B（allocated），≤2GiB；后置交付证据另记，旧大数组不复制、不清理。

正式SETUP/N/P0/P40/V监督wall分别16.964336413/192.170351080/280.439593997/329.576871897/55.797250034s。stage含加载/资格/audit/I/O，与S、PC、端口的内部计时嵌套，不能相加成新的总数。旧V14G0/V15补空间/V16image/V17–18 LSQR/V19 L均为暖起点必要lineage，两库都有神经G0；上游精确拆账缺项unknown保留。C未准入，无零起点总成本或cold成功声明。

新材料/网格/RHS和mode unchanged：physical2b532f91550316b16a304f3be9ae78605816b5a2aba556f548b5bd794f82e6de、material55aa34e55c5e3cc35f6849eddbd3bcc72d3b694d32bc4885299ef373acd676a2、mode93795b53d7c5aef69af66b4ff0a56fa46515771f1ec43332ec929970270ea262、action9196edb807b534217d0c0eb78882125341342784a48ef20ebe2d9421fe636454；K16187ad4d92cb4a490c73d4b2ebb5fb31ddba73c77c24ba23af500b3ae306b1f。完整父状态NPZ/z和source分别见[lineage](records/input_lineage_v20.json)、[checkpoint](records/checkpoint_inventory_v20.json)、[run index](records/run_index_v20.json)。大CSR/向量/日志仅ignored。

| 未运行项 | 原因 |
|---|---|
| T/C，更多P0/P40周期 | PC未过原方程、改善<10倍，四周期降幅<10% |
| 新hidden/基/参数扫描、旧LSQR/LGMRES | 本批未授权，固定规格已收口 |
| 新p4参考、最大0.7nm、GPU、p6/F5、merge | 硬边界禁止／资格不足 |
| 后置新reader mutation测试 | immutable deadline已过，正monitor budget不足；未启动 |
| full pytest、MPI2/4、Ruff、CI | 邻heavy/本批范围；Ruff未安装，不升级环境或宣称CI |
| 精确GitHub视觉公式／表格 | 页面未取得视觉证据，NOT_VERIFIED |

总elapsed超限不能被正式数值成本较短掩盖，见[deadline](records/deadline_stop_v20.json)。期望最终0.7nm/48小时解仍缺原方程/逐通道功率通过、离散误差、目标规模可扩展容量/时间证据，不能由micro低RSS外推。
