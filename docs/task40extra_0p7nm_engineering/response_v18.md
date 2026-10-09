# Review V18 执行回应

V18 完成了 Ny=8、B0、p6 的小模型完整参考算子与 Full3D 迭代求解，独立输出 checker 通过；同一份执行窗口内，E1 到四个 q 的符号阶段后因资源预算不足受控停止。原尺寸结构上界已按 32,060 个有序模式和 Ny=4/Ny=8 两种候选分别计算，但原尺寸数值矩阵、因子、精度及 2 TB / 48 h 仍未资格化。

Review V18 执行分支从 `origin/task40extra_0p7nm_engineering` 的基点 `33614413731d739d2c0f57106df180c359f4343f`（V17 收口后）开始；截至当前冻结提交形成 11 个提交，代码 HEAD 为 `ff8251dbcede1f736a0827fab8ffa8fb58daa9bd`。主控已审查并冻结两个只读 research entrypoint；该提交没有修改 production 数值源码。正式 Ny=8 运行绑定源码 `3b9457e57ceb15f21306a35baac07f42036840b1`；E1 资源记录绑定源码 `168a727add276633e20000b718a4aa7eaa5f1e61`。固定 campaign T0、deadline 与 600 s 收口保留未改变。本次执行只收口文档和证据索引，不提交、不推送；当前文档变更留在执行分支工作树，供主控统一处理。

| Review 工作 | 结果 | 结论边界 |
|---|---|---|
| Ny=8 完整参考算子 | 八个 q 的新矩阵身份全部匹配；独立 checker 覆盖 64 个 q 块、56 个非对角块和八个独立 Schur 检查；最大重算相对误差分别为 8.296e-16 与 1.257e-14 | 算子组件和 q=4 零端口证人通过；checker 没有重新作用数值算子 |
| Ny=8 B0 p6 正式场 | 160 cells、532 个有序模式、8 q；3 次外层迭代；A6 真残差 1.219e-8，限值 1e-6；官方输出 checker PASS | 通过该小离散模型的代数和物理输出门，不是连续极限或原尺寸精度结论 |
| E1 p6 | 四个 q 的 symbolic 阶段完成后，未来对象储备使投影超过现场 cap 5,851,946,944 B；numeric、KSP、新场和官方输出均未启动 | CONTROLLED_STOP_RESOURCE_GATE，不是数值 solver 失败或 OOM |
| 原尺寸支持上界 | Ny4 与 Ny8 分开计算 q 行、结构 NNZ 与 CSR payload 上界；Ny8 八 q 候选 payload 上界之和约 266.989 GB | 结构上界不是实测数值 NNZ、同时峰值或容量通过 |
| Ny4/Ny8 保存场比较 | 同一物理与派生参数、相同 x/z 轴，仅 y 从 4 格加密到 8 格；共同 160 子单元上 E/H/缩放 curl 最大相对差 4.911e-8 | 属于小模型 y 方向 tested agreement，不能称为连续收敛或原尺寸精度 |

## Ny=8 算子与 q=4

周期参考逆把可平移的参考问题拆成八个相位子问题，各自用已建立的直接因子回代，再合成外层预条件修正。真实三维缺口仍保留在 target 方程中，不能用参考问题的对角分解删除 target 的 q 耦合。

Ny=8 的每个全局 q 都有有限元子空间。q=4 的端口模式数为 0，但它仍有每 q 13,248 个原生有限元行；正式八 q 系统中该 q 的增广行数为 4,248。独立检查还通过了“零端口但有限元行非零”的见证。q4 FE sector 存在，因此没有放宽 mapping 门限，也没有改动数值源码。正式运行绑定的冻结源码 SHA 仍为 `3b9457e57ceb15f21306a35baac07f42036840b1`。

正式成功运行之前的六次 Ny=8 worker failure 全部按独立 attempt 保留，见 [run index](outcomes/records/run_index.json)。其中 source `b9dbe54403849807bec14c634fb358ab7d318092` 的 attempt 明确因候选预算缺少两个 twist-sector lift terms、exit 4。后续 run 重新生成八个 q 的 fresh hash，并由独立 checker 验证所有矩阵块、Schur 与非 Hermitian/global phase 见证；后续通过不覆盖这六条失败记录。

正式八个 q 的行数为 [4324,4324,4324,4324,4248,4324,4324,4324]，NNZ 为 [2274106,2284104,2285718,2268512,2203632,2275424,2284778,2283164]。完整 A6 真残差和独立 native witness 分别为 1.2189184363e-8、1.2189186015e-8。官方结果为 R/T/A_balance/A_volume 0.9842736080921 / 0.0142405181105 / 0.0014858737974 / 0.0014858738442；体吸收分项为 grating 0.0014189088407、substrate 0.00006696500347。零级反射分别为 R00_s=0.9842411413335、R00_p=0.000008453238782 和 R00_total=0.9842495945723。三步迭代、输入身份、A6 和 checker SHA 见 [formal results compact](outcomes/records/review_v18_formal_results.json)。

八个 q 的 live-factor 清单在 `task40_v12_p6_all_q_live_before_destroy.json` 中逐 q 记录，SHA-256 为 `2607e2cec9314917c6f84c44c31844bbed0a61392a05f50fadeba3c6b513b6ff`。q0…q7 同时存活；MUMPS INFOG(9)/(20)/(29) 的 factor-entry 数均为 `[3498592,3344944,3344944,3344944,3131136,3344944,3344944,3344944]`，每个向量合计 26,699,392。逐 q 的 allocated-upper 字节为 `[120000000,117000000,117000000,117000000,113000000,117000000,117000000,117000000]`，used-upper 字节为 `[108000000,105000000,105000000,105000000,102000000,105000000,105000000,105000000]`，总计分别 935,000,000 B 与 840,000,000 B。这是 MUMPS 因子字段的 decimal-MB 上界换算，不是整个进程内存。该 live snapshot 的进程树 RSS 为 4,869,058,560 B；watchdog `resources.jsonl` 第 9603 行在另一个采样时刻记录 4,869,050,368 B，差 8,192 B 保留为两个不同观测，不互相替换。watchdog 样本含 4 个进程、任务 swap 0、PSS disabled。

同一正式记录中的 `reference_pc_audit_before_detach` 明确记有 3 次 reference-PC 调用。原始 events 逐次给出的 initial `factors.calls` 区间为 32→40、40→48、48→56，每次增量 8，合计新增 24；三次 `correction_factor_calls` 均为 null，即没有触发修正。进入第 1 次 PC 前的计数 32 是 combined pre-PC 基线；regular-inverse startup gate 的四类检查各覆盖八个 q，但没有独立保存可把该 32 再细分成 startup 子项的 MatSolve 计数，因此该细分保持 unknown，不能从最终 56 倒推。三次 PC 父计时为 4.252986487、3.750249322、3.690838304 s；其中 native-evaluation 子计时为 3.134674321、3.099261057、3.023207492 s，已经包含在父区间内。`ksp_solve_phase.jsonl` 的纯 `PETSc.KSP.solve_only` 为 22.299832042 s（3 次迭代、converged reason 2、outer PC 3、outer matvec 3、explicit action 2）；25.547952792 s 是更宽的 outer-solver 时钟，不称为 pure KSP。

## Ny4/Ny8 保存场与复振幅

Ny4 原始 PDE worker 的分类仍是 WORKER_FAILED；随后保存场恢复记录为单独的 PASS，恢复后的官方包 SHA 为 df8aadddbb3f2d2a311444e27b01528ac35eefbca0a418d28e518800efa620a7。报告同时保留这两个事实，不把离线恢复改写成原 worker 成功。

全场比较复用既有 artifact v18_ny4_ny8_saved_field_common_subcells.json（SHA-256 4e5e6d9a643c38afabda6350fb6573885e9244e0a855a3d98d9e0de102f6296c）、已有积分比较函数 [task40_saved_field_h_comparison.py](../../src/postprocessing/task40_saved_field_h_comparison.py)（SHA-256 90b3b171608f53f2ba6141893bca8ebed3bd6a354c9e035330c4661f1bae0493）和原 ignored wrapper（SHA-256 4f6268af8ddb91721d2ade4131a89befac585472d8937c8f5e7d018d8d3c852d）。该 wrapper 把输出写入固定 artifact 路径；为保护已保存的比较记录，不应直接照原路径重跑。若需重算，应先复制 wrapper 到临时工作副本并把 OUTPUT 改到新的目标文件，再 source Task40 C1 activation 后运行。本轮复用既有 hash-bound 结果，没有重算积分或覆盖原 artifact。

另外新增了轻量 modal-only 复核。它直接读取 Ny4/Ny8 已保存的 532 个复振幅，不积分场、不建算子、不做因子分解或 KSP。两组 physical_boundary_incident_amplitude 数组逐位相同，L2 差为 0，Ny4 入射向量 L2 正规化量为 1。完整输出振幅向量的旧公共尺度差为 Ny4/Ny8 各约 3.482e-10，仅作诊断。逐模式以该通道 Ny4 复振幅作分母时，最大相对差为 4.766，出现在很弱的 bottom (m,n)=(1,2), p 通道；其 Ny4/Ny8 复振幅分别为 2.7193e-17-1.3605e-16i、5.9129e-16+2.0897e-16i，绝对幅值为 1.3874e-16、6.2713e-16，绝对差为 6.6124e-16，按单位入射向量 L2 归一后的绝对差也是 6.6124e-16。因此这个 4.766 是以极小通道振幅为分母的诊断值，绝对变化仍只有约 6.6e-16。

B0 review 没有冻结“显著模式”的 key 集合或筛选规则，因此 1% 显著模式门保持 NOT_EVALUATED_NO_FROZEN_B0_SIGNIFICANT_MODE_SET。没有套用 Gx560 的 V17 11-key 列表，也没有根据观察到的结果事后挑阈值。Ny8 的残差、官方 R/T/A 和独立 checker 已通过；此模式门的开放状态单独保留，不撤销这些已通过项。v4 modal sidecar 为本轮权威输出，SHA-256 `8a45423765ecaaf353594ef2a0b3bb27834ff733fb8f57345255bc958eea362e`，并在输出中绑定 runner SHA `b7c7e4f177a43a2570f171eb4cda9708ccd2e6bfcd56eed699ef6325717cce61`；v1、v2、v3 均保留。runner 默认使用新的 v4 文件名，若目标已经存在会拒绝覆盖，并以独占写入再次防止竞态覆盖。模态侧证见 [v4 supplement JSON](../../benchmarks/artifacts/task40extra_0p7nm_engineering/local_w17_wsl/v18_ny4_ny8_saved_field_modes_supplement_v4.json)；tracked runner 为 [task40_v18_saved_field_comparison.py](../../benchmarks/task40_v18_saved_field_comparison.py)。

## 目标结构界与 E1 资源停止

P3 runner [task40_v18_p6_support_bounds.py](../../benchmarks/task40_v18_p6_support_bounds.py) 调用已有可复用 support counter，并读取完整 32,060 模式 manifest 与 224-cell p6/MPC 校准。真实目标几何拓扑为 272×4×14=15,232 cells；目标 p6 FE space、数值 CSR 与 factor 均未构造。Ny4 support 校准可迁移时，每 cell 上界为 348、每外边界面上界为 78,336。现存原生校准只覆盖 Ny4；没有 Ny8 目标方向排列和类型覆盖收据，故 Ny8 每 cell 回退到保守 432、每边界面 117,504；不把 Ny4 的 142.503 GB 复制给 Ny8。Ny8 候选每个 q 的结构 NNZ 上界为 1.632–1.685 billion，八个不同 q 的一份 CSR payload 上界和为 266,988,562,768 B。这个和不代表同时驻留量，也没有测得目标数值非零或 RSS。

E1 实测达到 760 cells、p6、588 modes 的四个 q symbolic 阶段。MUMPS INFOG16/17 给出的 q 估计是 [1613,1666,1626,1621] MB，合计 6,526 MB；Gate 使用的 6,530,000,000 B symbolic future reserve 是在此基础上每个 q 另留 1 MB 的保守储备，不能读成实际 factor 内存。再加 pending transform inverse 273,222,720 B 与选定同时存活阶段 190,897,920 B，总 future reserve 为 6,994,120,640 B。Gate 时进程树 RSS 为 12,268,249,088 B，投影 19,396,587,456 B，超过 dynamic cap 13,544,640,512 B 共 5,851,946,944 B。该次 process-tree 峰值为 12,518,109,184 B，专用 cgroup peak 为 12,710,162,432 B，任务 swap 为 0、OOM/OOM-kill 为 0。全局 swap 增量 758/2612 页是宿主级观察，不能归属 E1。

E1 的原始 event ledger 还保存了 sector-ready 记录：两组 q sector 的 `local_inventory` 计数分别是 `[264282,76680,171000,252]` 与 `[264282,76680,171000,336]`，但它不含逐 owner 字节或最后使用时刻。E1 此次实际 assembly strategy 是 `LEGACY_GLOBAL_CSR_SUM`，所以不能把 Ny8 row-tile 的释放收益归给 E1。twist 0 的 parent assembly/numeric 区间为 380.988118742/380.708222575 s，子区间 contribution/projection/sparse accumulation 为 17.808910578/87.606416178/275.254935565 s；925 contributions、3700 projection/accumulation calls。twist 1 对应为 477.394950931/477.114413698 s，子区间 23.263784788/95.576659739/358.227370741 s；1093 contributions、4372 calls。子区间不重叠且已计入 numeric parent，parent 计时还含 loop overhead；不把父子重复相加。E1 inventory 文件 SHA `2dcc233086e8ec88e27a5b17e8a741cb1281530b8a214bb91307ddd369d097ac` 的 entries/components 为空且总量为零，只是空记录账本；owner/backing/last-use 字节仍未完整记录。停止是具体资源准入差额，不是求解器残差失败；numeric/KSP、E1 新场与 R/T/A 都是 not_run。

## 时间、测试与 readiness

由 watchdog 启动至冻结后必需 checker 完成，直接记录的 monotonic/UTC 跨度分别为 3342.078481052071 / 3646.233646301 s；它包含该场 checker 修复与读回，启动前外部 ABI/准备边界仍未知，不能称为完整冷流程。两种时钟口径不相加。

Ny8 run_case full workflow monotonic 为 2474.995817267103 s，resource authority elapsed 为 2474.820380249992 s，两者口径不同不相加；纯 KSP.solve 与更宽 outer-solver clock 已在上面分开记录。watchdog 同时树峰值/cgroup peak 分别为 4,869,050,368/5,899,956,224 B。E1 workflow monotonic 为 5793.324598474894 s，conservative wall interval 为 6318.723884567858 s；是两个时间口径，也不相加。Ny8 启动前的外部 ABI/准备边界没有完整计时，单场完整冷启动关键路径仍为 unknown。

已有记录显示新研究入口 compileall、P3 派生界生成、modal-only 复核及一轮文档合同测试通过；主控另以 C1 核验两个入口拒绝覆盖已有输出且原文件字节未变（PASS_NO_FE）。文档合同测试日志早于本次最终 compact/run-index 更新，因此这里只报告其既有结果，不称为最终文档复测；本次只做 JSON、差异和空白检查，没有追加 FE/PDE。完整命令、日志身份和未运行范围见 [test summary](outcomes/test_summary.md) 与 [run index](outcomes/records/run_index.json)。full repository pytest、MPI4、Ruff 和 CI 未运行，不声称通过。

| 收口判断 | 当前状态 |
|---|---|
| Ny8 B0 p6 小模型完整求解与官方输出 | PASS_WITH_QUALIFICATIONS |
| Ny4/Ny8 小模型 y 方向场观察 | TESTED_AGREEMENT，不是 continuum convergence |
| E1 当前实现 | CONTROLLED_STOP_RESOURCE_GATE |
| 原尺寸结构 support / int32 上界 | DERIVED_BOUNDS_COMPLETE，不是目标矩阵或容量通过 |
| 原尺寸精度、十进制 2 TB 与 48 h | NOT_QUALIFIED |
| ordinary solver default / master merge | 未更改 / 未合并 |

四份 compact、任务 summary/test summary、run index 和项目级 progress/model registry 均已更新。源代码冻结点为 `ff8251dbcede1f736a0827fab8ffa8fb58daa9bd`；文档与证据由主控集中提交推送，最终 HEAD 以远端回读为准。

主控最终收口观察仍绑定原窗口 SHA `83f47e542dc28309d398a55c6b7e1b1ca76dab25dead854d88cc6feb6758ed24`：累计政策 charge 85539.607409756 s，剩余 numerical 260.392590244 s（600 s 收口已扣）。该值是观察时快照，不刷新 deadline；后续 Git 提交/推送费用未独立计时，保留 unknown。主控最终文档/计数器检查 36 passed、134 subtests passed，测试和原始日志身份见 test summary。
