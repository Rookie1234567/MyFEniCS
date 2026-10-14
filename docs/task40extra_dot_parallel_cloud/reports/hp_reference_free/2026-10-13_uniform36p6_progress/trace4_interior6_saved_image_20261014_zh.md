# trace4_interior6_saved_image_20261014

日期：2026-10-14（UTC）。实际终态、独立证据核验及 v72 成本账已绑定；科学分类仍为未决。

## 1. 结论：128 步封顶未决，原端口门失败

有界 LSMR 完成 128 步并触及预设迭代上限（istop=7）。选定候选的 native 单位 q 残差比为 0.8537943314895308，原端口相对闭合误差为 0.9394413894559671，远高于原 1e-10 门槛。因此本轮结论严格为 INCONCLUSIVE，port=FAIL；按此止点发布，不继续 LS。

这不是全局最小值、不可达证明或 trace 缺失的因果证据，也不是合法 PC 改进。程序 exit 0 只表示按计划完成、记录和清理，不能覆盖科学未决及原端口失败。未接受物理解，未执行 outer/CG 步。

## 2. 此次诊断具体在问什么

在同一冻结 6656 native residual 方向上，以 10,304 维系数（10,224 trace-p4 + 原 80 个自由端口系数）搜索 retained 像。E=diag(Pt,I80)，其中 Pt 为原有未阈值化的实际 oriented/MPC 映射，E 为 24,056 × 10,304。

搜索算子为 L_n=J A_saved R E，其中 R=diag(Qb,I80)、J=diag(Qbᴴ,Hp)。saved CSR 未改变；目标函数使用原 native retained 欧氏范数。伴随为 EᴴRᴴA_savedᴴJᴴ；不把历史坐标转移的“对偶名称”误当作所需共轭转置。

目标 q 来自原 native RHS 减去原 mapped checkpoint 的 native S6 动作，经原 PETSc 归一化；没有换成 saved RHS 或 mapped saved residual。原始范数 0.013898680225977397，双 hash 保持：

- raw：`7a0f317f14c13dfa3235d34cb2586ceeecbdd3a43addd6555ebfb66af84daca2`
- unit：`3cd6bb01aba4adbcdb87a9b678796cc7a6ba45cd0296d6d3a05b9961147abfce`

端口系数在像搜索中是自由的，因此小总残差也必须另外通过原端口条件，才可能属于合法端口像；更不能直接当作 BAL_H 输出。此诊断不构建正规矩阵、显式全局像矩阵或新 K，不改变物理算子或 P 系数。

## 3. 实际资格与选定候选

最终冻结命令 SHA-256：`636680a46b1ff102dec03be15f15ae0c6e4b7cfd417630e007df92e0e14abb50`。最终源码包通过 78 项 stdlib 测试。三个实际复数伴随配对均通过 1e-10 门槛，最大相对误差 2.6424294986545061e-15。这只验证线性动作的伴随配对，不验证任意非零端口 solve。

LSMR 结果：

- itn=128，istop=7，迭代上限到达；没有收敛证书。
- LSMR normr=0.8537943314895722；独立重算的 native eta=0.8537943314895308。
- 使用同一 native 范数的 mapped-saved eta=0.8537943314895684。
- 独立重算 ‖L_nᴴ(L_ny−q)‖=63.50193872767886；除以原 q 范数后为 63.501938727678734，不能当作已收敛的正规残差。
- LSMR 内部 condA 估计为 10.658730376891038，不是全谱/全局最优性或不可达的证书。

对选定 y，仅额外执行一次 native S6，native 与 mapped-saved 像的差为 1.2312449764699958e-12（按原 q 范数）。这是该选定候选上的一致性证据，不能撤销旧 checkpoint 或 saved/native PC 的 raw 失败，也不是所有方向的算子误差界。

native 残差分解：trace 为 0.8537943238983767，port 为 0.00011385328904239144，总范数为 0.8537943314895324；原 q 分母为 1.000000000000002。saved 自身坐标下的相对残差 0.8537943271875853 另列，不能偷换为 native 目标范数。

选定系数范数 ‖y‖=0.0010661890352508905；trace 部分为 0.0010661861543184111，port 部分为 2.4785538004177096e-6。这些是最后候选的描述，不是最优系数证明。

## 4. 为什么端口 FAIL 不能被总范数稀释

按原局部齐次 interior 恢复一次场，再应用原 D，独立检查 q_port + Du − Hpα：

- 原 q_port 范数：5.778000052683001e-13
- ‖Du‖：0.0001136193214380345
- ‖Hpα‖：0.000007573218913540739
- 端口绝对残差：0.00011385328904239144
- 原端口 operation scale：0.00012119254092937524
- 原端口相对误差：0.9394413894559671；原门槛 1e-10，FAIL

端口绝对残差占总 q 范数看似很小，但原门使用端口自身尺度，不能被较大的 trace 残差掩盖。一次局部齐次恢复仅用于此核验；没有接受或导出物理场。

预设 small-image threshold 为 0.02，本次 eta 约 0.854 未达到。verified_free_port_existence_upper_bound=false、legal_port_image_upper_bound=false、legal_PC_improvement_claimed=false。该候选只是一个已测残差，未给出 ≤0.02 的小残差见证；迭代封顶后的大残差不是最小值下界，不能据此证明方向不可达或 trace 空间必定缺少某模式。

## 5. 有界工作、资源与本地证据

L 总调用 132，Lᴴ 总调用 133；其中 LSMR 为 128/129，其余为三个配对及最终 forward/normal-residual 核验，均低于各自 136 的硬调用上限。native 输入动作四次，选定候选 native S6 一次，局部齐次恢复一次，原 D 动作一次。

global K、JOB1、global numeric factor、global factor solve、H3、BAL_H、CG 和 outer 均为零。原 fine bank 的 33 raw / 44 oriented 局部 LU 构建与恢复存在，不能写成“完全没有分解或局部 solve”。

本次监督墙钟 71.989610691 s，283 个资源采样，采样树峰值 2,405,855,232 B；63 次准入均已做资源核验。预计 tree 最大为 4,341,713,700 B；记录到的 VmSize 快照最大 3,117,539,328 B。采样/快照不是连续峰值。原 6 GiB AS、8 GiB tree、host 1 GiB、零 swap、600 s、disk 4 GiB、总输出 128 MiB、MPI1/thread1 与单科学子进程边界不变。

联合 CSC/LS 加原 allocator/diagnostic 预留的命名增量为 1,074,641,636 B；tree 口径另计 ELF 后为 1,949,989,668 B。原守卫当前 VmSize + 命名增量的 AS 门与整树/host 门分别执行，不能以 tree 值冒充 AS；不从快照下降推断 allocator 已归还内存。

独立终审复核 44 个最终源码 pin、16 个缓存角色、全部资源/准入与标量一致性。11 个已知所有者清理回调正常返回，监督器确认 child exit 0、清理通过、无剩余进程。hwloc sysfs topology 警告及 UCX /sys/class/net 发现错误按原日志保留，不说成无警告。已知所有者清理不等于每个历史 helper 隐藏的部分 native 句柄都有显式销毁证明。

四个局部 complex128 NPY 仅用于有界独立证据：q_native、coarse_y、native_image、native_residual，合计 1,320,064 B，单文件最多 385,024 B。它们保留在本地，不上传；不是已接受解、矩阵或因子。发布者只读标量 JSON/source，不自行读取这些数组。独立核验使用 stdlib 检查四个 NPY 的 header、shape、dtype、原始/typed SHA、有限性和分量关系，native_image − q − native_residual 的分量最大差为 0；fsum 范数重算 eta=0.8537943314895303，与运行记录一致到浮点误差。

该复核验证本地保存证据的一致性，没有重新应用 native S6，也没有重读大 saved CSR 或重算 Lᴴ normal action。选定 native 动作依靠已批准阶段的固定源码/事件及一次动作计数，不将文件核验冒充第二次数值实验。

## 6. 旧失败、成本及本轮止点

原 g=1 压力资格 FAIL、saved/native checkpoint raw mismatch、actual-only 中 saved/native PC 与 prediction raw FAIL 全部保留；all_diagnostics_passed_claimed=false、field_accepted=false、solution_accepted=false。

本次 71.989610691 s，加此前 trace4 五次 875.770228062 s，本路线六次实际阶段合计 947.759838753 s。最终 v72 账本记录已知终态 science 累计 21,157.21482817612 s、含中断记录的累计下界 29,071.207111019103 s，均非精确总墙钟；本轮只向 science 和加入 71.989610691 s。独立文件核验耗时未单独测量，另列且不能记零；准备、源码复核和等待未知，不能记零，分时内存峰值不相加。

本轮止点是“128 未决 + 原端口失败”；不继续 LSMR，不追加科学动作，不启动 outer。后续端口严格消元仅限静态方案，没有新数值准入。此自由端口像搜索的 eta 不能与此前固定 BAL_H 方向的最佳单方向残差直接称作 PC 改进。

前序事实见同目录 [actual-only 受限诊断](trace4_interior6_actual_only_20261014_zh.md) 与 [fixed-control 失败记录](trace4_interior6_fixed_control_20261014_zh.md)。本提交只有中文报告和有界 JSON，不上传代码或大数据。

## 7. 证据索引

以下是 hp_resume_20261013 中相对证据名及 SHA-256；不表示原始文件已公开上传。

- `phase4_trace4_interior6_saved_image_reachability_source_review.json`（38398 B）：`e6c263c10e7bc95a139b05b50f318283e358975f391f148fd848061ee7fc26ce`
- `phase4_trace4_interior6_saved_image_runtime_review.json`（5427 B）：`cb09f441b42ccbc1e184d34943715140e429d210a0753616e2db0d2effedfbde`
- `phase4_trace4_interior6_saved_image_attempt01/summary.json`（1215 B）：`ddd911adfd2cce37f0f1874bd7d1073623fbab3a2528eb72d64006216422d48c`
- `phase4_trace4_interior6_saved_image_attempt01/result.json`（224789 B）：`082d87291e38ccc99cf2311d836ba18ed3fb4c21475451c2845ae1df39d8ab70`
- `phase4_trace4_interior6_actual_only_attempt01_terminal_review.json`（53776 B）：`212ce4b58428b38844fbf64e3ae6ddd6db3fddcf346615d84ac866a0032f20da`
- `phase4_trace4_interior6_fixed_attempt02_terminal_review.json`（46750 B）：`18072bd040eb4e7831e66d5ede0197120a915e1ce3125c8b3ec809c29f4f3b2e`
- `phase4_trace4_interior6_saved_image_attempt01_terminal_review.json`（32242 B）：`b40285f8aa7d1fa48c9be2f07c50136889005f71eeef73c3f6bb326680da35fb`
- `phase4_execution_ledger_v72.json`（48679 B）：`0287d8c99cef5531fe0600253a9b55a5d5ad51f518d8eaa8bef54da9ecdc3f83`
- `phase4_trace4_interior6_independent_review/saved_image_attempt01_small_vector_checks.json`（2236 B）：`b8e96c68c8db42fc3ce4695131596532e42ec6e8d0291eaf1d2808dedce15b6f`
