# Task40 identity recovery：R1–R5 结果

## 读者先看结论

单元凝聚是先在每个有限元单元内部消去未知量，从而缩小需要整体求解的矩阵；最后再把内部场恢复出来。attempt4 的错误发生在这个“单元内部局部计算”的缓存识别：代码把实际网格宽度四舍五入到 12 位后当作缓存键，两个略有不同的宽度因此可能误用同一个局部算子。修复让 Task40 局部算子按精确几何身份取键，没有改物理方程、材料、模式或严格残差阈值。

修复后的新鲜 G0/G1 求解均通过 full explicit A6 真残差和 strict identity 限值；G0 的独立 same-discrete direct reference 也通过残差，且场、模态、总功率比较通过。旧 attempt4 仍是失败历史，不由新结果改写。结论只适用于本批缩小网格与固定 80 modes。

## 根因、修复和离线复核

| 项目 | 记录 | 含义 |
|---|---|---|
| attempt4 | source de44f5bb4da48cd076df2b295ef6fe08b83d52fa；A6=0.16667295750232392（限值1e-6）；native identity=3.0748104980683956e-10（限值1e-10）；worker 原分类 V20_RELEASE_GATE_FAIL | identity 停止值仍作为原始负结果保存；raw callback/PETSc reason 未持久化，因此 callback 名称属于源码推导 |
| 根因 | p6 局部动作缓存把精确单元宽度舍入到 12 位 | 几何不同的局部问题可能命中同一缓存项 |
| 修复 | 提交 33b773d161b5e5dc218a29b122cdb4044ca01800；Task40 p6 cache key 使用精确几何 | 旧 profile 默认值不变；方程、材料和 Gate 未改 |
| R1 离线重算 | iteration-8 保存向量上的 native identity=1.3369675137611322e-11；internal=6.207153842462271e-18；Schur-port=8.484168951217582e-30 | 通过各自原限值，但仅是保存向量核验，不是 fresh solve |
| 回放覆盖缺口 | 3 个 geometry-dominant spot checks 中 local RHS 与 B alpha 都为零；完整 inventory 中 Bi、Di 各 984 个非零项 | 保留为覆盖缺口，不把回放夸成完整 p4 因子或 G0 PDE 证明 |

## 正式 G0 / G1 新解

正式输入保持原 0.7 nm Si/air、同解析几何、双 Floquet 与冻结的 80-mode keys。G0、G1 使用同一 source b8a20bd24848a83f2f4fa50b1ccaaa4ec9be9672，但分别绑定输入 SHA 6654ec211efbc6112f3ccba13ad67ff3a97cdbc471bdd48e39f891819f51a41e 和 989a351fb27fe5320942ca2392d0e7e872909f0354509e5d59c8c25e43061c86。计算采用 complex128、MPI1、数学线程1。

| 网格 | cells / full rows / active rows | 凝聚 rows / NNZ | 迭代与终态 Gate | 当前结果 |
|---|---:|---:|---|---|
| G0 | 336 / 229,680 / 68,256 | p6 trace+port 68,336；q4 凝聚因子 29,072 / 10,912,592 | FGMRES 152 步；A6=9.798664008005796e-7；identity=1.520588963522625e-11 | DISCRETE_SOLVE_AND_CONSISTENCY_PASS_AUTHORITY_LIMITED |
| G1 | 880 / 595,512 / 177,120 | p6 trace+port 177,200；q4 凝聚因子 75,280 / 28,705,330 | FGMRES 127 步；A6=9.901397191660007e-7；identity=3.2542694546811876e-11 | DISCRETE_SOLVE_AND_CONSISTENCY_PASS_AUTHORITY_LIMITED |

两个 A6 都低于 1e-6，identity 都低于 1e-10。internal、port closure 和 Schur-port identity 的具体数值以及 R/T/A/A_volume 在 [compact result](records/identity_recovery_v1_results.json) 和 [run index](records/run_index.json) 中；R/T 来自端口模态振幅，A_volume 是硅区域体积分吸收值。G0/G1 fixed-coordinate h agreement 的总场/功率差通过任务的工程阈值，但仅比较两个网格，不能当作连续收敛。

## G0 同离散 direct reference

直接法一次性组装并因式分解 G0 同一离散系统。它提供这个矩阵方程的对照解，用于判断 iterative 解相对同离散解的误差；它本身不说明离散网格已达到连续解。输入 SHA 为 c80c921834cb268a9251459795fbda5acf4e9f25347d16ee24dec3b9d85c6c56，source 为 393e5c0dddb933848945ab2e18edb73cf69cc224。直接输入的原始 physical SHA 为 1f53e9f90d63a595b1184a975ab1dce12d4fa1362f86f224753584e3992e17bc；按 frozen physical sections 规范化后与 G0 physical SHA 51854af3fb60c7ffebb166e1f06ff0a89e2e184dcbd9ba06ab4beb321b920661 一致。唯一变化是离散 assembly backend 标签：standard_full 对 assembly_time_static_condensed。

reference_summary 状态 REFERENCE_PASS；保存场的 full residual 为 5.055376131651821e-11，限值 1e-10。主控对保存数组做独立离线重算：读取 reference_full_residual.npz，仅用保存的 b 和 Ax 复算 norm(b-Ax)/norm(b)，结果与记录完全相同，残差向量逐元素最大差为 0。direct 的 MUMPS 全局 LU 为 p6 trace+port 共 68,336 rows；229,680 是恢复完整场的存储维数，不是被直接因子分解的全局 A6 行数。执行了 1 次 symbolic、1 次 numeric、2 次 solve calls 和 1 次 correction call，随后释放 factor，再做 recovery/native 原算子核验。

| 比较 Gate | 实测差值 | 限值 | 判定 |
|---|---:|---:|---|
| FE L2 | 1.0643994068890889e-7 | 1e-4 | pass |
| FE scaled-curl | 1.0590110456109757e-7 | 1e-4 | pass |
| 同坐标 E/H、界面 tangential E/H | 最大相对差 4.95900726941708e-7 | 1e-4 | pass |
| 80 mode outgoing amplitude | 1.337435981717596e-7（向量整体相对差） | 1e-4 | pass |
| 每模 power | 最大绝对差 7.507099208936552e-8 | 1e-6 | pass |
| R/T/A/A_volume 总量 | 最大绝对差 7.591423312192092e-8 | 1e-5 | pass |
| reference energy closure | 1.6774137634456565e-11 | 1e-5 | pass |

完整 Gate 清单见 ignored run 的 matched_reference.json。三套数组文件、reference summary 和 watchdog 的 SHA 记录在 compact JSON。直接参考资源峰值为同时进程树 RSS 11,505,573,888 B，峰值样本的 outer stage 为 workflow、worker stage 为 fine_reference_residual_completed；任务树 swap 0，PSS disabled；PETSc 输入矩阵 MatInfo 报 nz_allocated/nz_used=56,834,000/55,984,880 项；MUMPS INFOG16/17=7,932/7,932 decimal MB（预估、max/sum），INFOG18/19=8,277/8,277 decimal MB（实分配、max/sum），INFOG22=6,798 decimal MB（实用、跨进程和），INFOG29=346,831,808 个因子项。它们都不是 RSS。symbolic admission 的7,932 decimal MB是预估，不代表实测峰值。字段定义见 [PETSc MUMPS INFOG 输出](https://petsc.org/release/src/mat/impls/aij/mpi/mumps/impl/imumps.c.html)。

## 运行纪律与边界

正式 direct 是唯一获准的重型参考场。执行中发现 outer command 由 Codex shell 直接启动，没有经过 user-service wrapper，cgroup 为 /init.scope。发现偏差后没有重启、迁移或终止该 run；独立 subreaper watchdog 仍完成了进程树身份追踪，记录 exit 0、descendants cleared、树 swap 0、RSS 峰值及时间。详见 [R5 execution context](records/r5_execution_context.json)。报告不将 watchdog completion 写成 user-service 合规。

R1 full p6 operator diagnosis耗时14,039.107309384039 s；v1 builder主动中止约101 s（近似）；v2 exact-geometry离线replay耗时198.79226663301233 s；旧attempt1–4 shared ledger累计530.8867869906425 s。review_v1 G0/G1 workflow monotonic分别1204.0178907530499/4097.993754097028 s，direct watchdog elapsed/launch charged分别1647.5270624320256/1801.4672110320269 s。各值处于不同阶段/时钟，不能相加推导阶段工时。

G0/G1/direct 的同时树 RSS 峰分别为 3,776,098,304 / 6,855,741,440 / 11,505,573,888 B；PSS 均按 profile disabled。direct watchdog elapsed 1647.5270624320256 s，launch charged 1801.4672110320269 s；没有可靠 symbolic/numeric/solve 分阶段耗时，保持 unknown。80-mode cutoff 仍未资格化、continuum convergence 未建立、约 2 TB 目标容量仍 unknown。普通默认未改变，未选 Phase II PC，也未合并 master。
