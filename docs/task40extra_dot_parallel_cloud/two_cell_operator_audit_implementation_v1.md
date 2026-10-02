# Q0–Q2 两胞元 full3D 运算编排候选

|项目|当前边界|
|---|---|
|状态|source35dd9e5c的Q0–Q2审计与独立checker4842/4842已通过；原NOT_RUN为历史准备状态|
|原始空间|80 个真实3D六面体，p4，15872 independent /8640 interior /7232 trace|
|候选参考|两个40-cell真实3D空间，各保持7936 independent /4320 interior /3616 trace|
|模式|两个显式 twist，各两条分支，完整 q0/1/2/3；原始532模式分为228/304，原对象和索引保留|
|因子边界|global/q factor_count=0；原有108×108胞元内部 LU 用于精确消元/恢复|
|资源|aggregate whole-tree1.5GiB、总audit+checker600s、zeroSwap、MPI1/thread1；每次分配另留128MiB|
|后续|Q3–Q5 quotient inverse/完整物理forcing/notch/output仍待独立批准；目标大小没有资格|

直接构造两个本地FE/MPC空间，显式使用 eta=exp(i(ky Ly+2pi b)/4) 和 tau=eta²。全Ny原始空间仅保留原始完整3D action与实体局部 moment 块；不创建候选全Ny S/F/Q。局部空间所有 y 内部通道保留，几何和材料不平均。旧全Ny S/maps只作为 validation authority。

primal lift 是 P=R_N E_b R_2^-1，dual fold 是 P^H；D 已含物理共轭，功能行变换使用 transpose。C/D本地对应 full 除sqrtK，原H对应 full/K；本地 masked C/D重新 lift到原native storage，与旧记录逐模式比较。fresh原始raw与local raw在两个方向比较，随后独立literal oracle验证同一live本地carrier。两阶段production cutoff保持原样，任何noncommutation保留失败，不能改阈值。

每个q全部3968 FE列（含内部）以不超过32列panel对旧fullQ比较，门1e-12。四本地congruence diagonal保留每个CSR entry，对旧positive-H q块比较norm/max门1e-11。四同twist off-block来自真实local贡献；八跨twist off-block从旧原始S和validation maps计算，使用刚证明完整列相等的表示，并明确记录该控制的来源。全部12对采用两diagonal中较弱者的norm和max缩放，门1e-11。

新鲜full original action witness保持所有内部通道，检查 A_local x=P^H A_full P x。manufactured augmented state产生非零4320 interior RHS和全部port RHS，用原live volume/carrier构造，再使用原有reduce/recover恢复原native场；没有global/q solve。Q0–Q2仍是operator audit，不提供物理解或正式观测量。

source35dd9e5c已完成183 targeted checks、1 evidence-only skip、4 actual-FFCx/532 deselected；随后单次Q0–Q2及独立checker4842/4842通过。最初13个isolated coordinate/source contracts只证明坐标接线。测试使用固定nonunitary moment coordinate blocks核对复杂phase的primal/dual/functional代数；它们不构成FE物理资格。本轮实际FFCx/MPC/raw-oracle/Schur/原action门已有受监督保存证据，详见[Response V10](response_v10.md)。Q3–Q5、目标规模和默认路径仍未资格。
