# Response V17：全空间续算完成，GMRES接线失败保留

本轮执行Review V14；原0.7nm/384hex/p3/q15/40端口/canonical材料和原方程保持。R0/R1/R2/R3及冻结后独立验证已完成；G两库真实尝试但接线FAILED、0完整周期，未训练hidden。原低维Q之外的全空间修正继续改善残差，但严格同离散资格 **0/8**。

唯一branch `task42_neural_coarse_inverse`、upstream `origin/task42_neural_coarse_inverse`、worktree `/home/fenics/Projects/NN-Lab`；base `ccd357885f7f9be84efe3be07868cc94f13d93fc`。canonical common Git `/home/fenics/Projects/Maxwell3D-Lab/task-repository.git`；Review V14 `f834c008110131433de0f269195de394a6856871`安全快进取得。最终文档HEAD在提交回执报告，与下述真实run source分开。

| 同一0.7nm micro／固定Q3098 | 最终LSQR逻辑步 | 新GK measured..charged | G周期 | Arnoldi步 | 最终Schur | 最终native | 散射E误差 | 散射curl误差 | LSQR停止／G停止 |
|---|---|---|---|---|---|---|---|---|---|
| GPOLY | 6347 | 6091..6091 | 0 | unknown; discarded 0..64 | 0.000490220469 | 0.000190109352 | 0.000265162174 | 0.0002631196 | LSQR_RESERVED_G_BOUNDARY / GMRES_INTERFACE_FAILED |
| GNN | 6119 | 6119..6135 | 0 | unknown; discarded 0..64 | 0.000594477082 | 0.00023054046 | 0.000249203787 | 0.000245918456 | LSQR_RESERVED_G_BOUNDARY / GMRES_INTERFACE_FAILED |


完整递推每16步双滚动槽原子保存、每64步原场先保存再audit。GPOLY真实旧256步续算，GNN从原f零状态；正常恢复11/10次，校正重启0、PSI重入0。R1两库32与16+独立读取+16的全GK/z/原作用差0。旧GP816/GN85仅有标量的终态没有猜造；旧失败费用和新重算均保留。

4个修复循环用尽，含一次可避免的stage前缀接线错误；两个真实失败加载及保守计数完整保留。另有G接线错误：误把close返回的完整z当port再次拼接，原action拒绝错误shape；两库未保存合格G周期，实际Arnoldi计数unknown（每库0..64上界）。没有绕过修复额度重跑G，已保存LSQR通过另一条正确restore链。两次维护仅停自身driver，当前slice正常完成后才变HEAD，不混称数值重启。新A/image QR均0，复用V16 frozen image；无global p4因子、隐藏fallback或新参考LU。独立native审核仍有原FE装配成本。

所有求解/选择/hash冻结并退出后，一次独立FE进程读原REF7，native 1.43744486619e-12；原Schur/native/增广/port、恢复/slave、total/scattered E/H/curl、selected复场、完整40通道及R/T/A/A_volume/能量见[完整结果](outcomes/resumable_full_trace_campaign_v17.md)、[候选CSV](outcomes/records/candidate_comparison_v17.csv)。未合格功率只作diagnostic。GPOLY/GNN共同含神经G0，本批没有神经训练或同精度加速资格。

新增正式数值监督wall **16284.035028s**；V6起formal累计下界 **37508.426009s**。同时整树采样峰 **2577092608B（2.400105GiB）**，own swap **0B**、GPU分配0；全部成本为shared-workstation。 历史未知费用不补造，queue/嵌套计时不重复累加。总start15:10:06Z、heavy截止21:40:06Z、总deadline22:10:06Z；每库B9000/G900、16GiB hard/12GiB warn和ownswap0保持。独立.5s整树监督、实时选核/MPI1/线程1、NN-Lab缓存；无cgroup委派，不声称连续kernel限制或绝对零干扰。

真实运行source与输入/物理/material/mode/数组/资源见[run index](outcomes/records/run_index_v17.json)，最终文档HEAD以提交回执报告；HEAD不冒充早期运行source。原task/review/response/raw保持，测试/导航/summary和两总账已同步。未运行新p4参考、最大模型、GPU或merge，GitHub未取得页面像素时按NOT_VERIFIED记录。

唯一下一建议：仅在下一份review重新授权后，修复GMRES入口对BarAction.close完整z返回值的接线，并增加一个覆盖真实端口闭合／原audit的最小回归；从当前两库最后可信LSQR trace各完成同一固定GMRES64对照，补齐本批因实现失败而缺失的证据，不增加基、PC、迭代预算或读取参考选点。本批不实施。

清场、关闭预算后只推送本执行分支，停止等待review，不merge。
