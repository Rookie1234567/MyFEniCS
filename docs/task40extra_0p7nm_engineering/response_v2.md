# Response V2：Task40extra B 线 R0–R5 收口

## 结论

精确几何键修复后，G0 与 G1 在原严格 identity 限值下都完成了当前离散方程求解；G0 的同离散直接参考也完成，保存的场、80 个端口模式和总功率对照均通过任务限值。结果支持“这个缩小的 0.7 nm 连续介质模型已经得到可复核的离散解”。它们没有证明 80 模式截断收敛、连续极限收敛或约 2 TB 目标规模可行。

| 运行 | 网格与方法 | 物理解算与一致性 | 正式功率与吸收 | 资源与时间 |
|---|---|---|---|---|
| G0 review_v1 | 336 cells；p6 完整场存储 229,680 rows、活跃 trace 68,256 rows；p6 外层 trace+port 共 68,336 rows；独立 q4 凝聚因子 29,072 rows / 10,912,592 NNZ；FGMRES 152 步；80 modes | full A6 = 9.798664008005796e-7（限值1e-6）；strict identity = 1.520588963522625e-11（限值1e-10）；internal 6.1149e-18、port closure 2.5365e-16、Schur-port 7.7840e-30 | R=0.07565196449717393；T=0.9062068564432124；A_balance=0.018141179059613655；A_volume=0.01814125705170932；闭合误差 7.799209567060927e-8 | watchdog 树 RSS 峰 3,776,098,304 B；swap 0；workflow monotonic 1204.018 s；KSP-only 787.135 s |
| G1 review_v1 | 880 cells；p6 完整场存储 595,512 rows、活跃 trace 177,120 rows；p6 外层 trace+port 共 177,200 rows；独立 q4 凝聚因子 75,280 rows / 28,705,330 NNZ；FGMRES 127 步；80 modes | full A6 = 9.901397191660007e-7（限值1e-6）；strict identity = 3.2542694546811876e-11（限值1e-10）；internal 3.2745e-18、port closure 8.3927e-16、Schur-port 2.0617e-29 | R=0.07612406206792088；T=0.905769220572286；A_balance=0.01810671735979308；A_volume=0.018106712729780598；闭合误差 -4.630012484518886e-9 | watchdog 树 RSS 峰 6,855,741,440 B；swap 0；workflow monotonic 4097.994 s；KSP-only 3135.913 s |
| G0 same-discrete direct | 与 G0 相同的 68,336 p6 trace+port global LU rows / 80 modes；229,680 是恢复完整场的存储维数，不是 MUMPS 全局 A6 因子行数 | 独立 full A6 = 5.055376131651821e-11（限值1e-10）；1 symbolic、1 numeric、2 solve calls；factor 释放后做独立原算子核验 | reference R=0.07565196365429899；T=0.9062067813718543；A_balance=0.018141254973846777；A_volume=0.018141254990620734；能量闭合 1.6774137634456565e-11 | watchdog 树 RSS 峰 11,505,573,888 B（峰值样本 outer stage=workflow、worker stage=fine_reference_residual_completed）；树 swap 0；PSS 禁用；PETSc 输入矩阵 MatInfo 为 nz_allocated/nz_used=56,834,000/55,984,880 项；MUMPS INFOG16/17=7,932/7,932 decimal MB（预估、max/sum），INFOG18/19=8,277/8,277 decimal MB（实分配、max/sum），INFOG22=6,798 decimal MB（实用、跨进程和），INFOG29=346,831,808 个因子矩阵项；均与进程树 RSS 分开记录；watchdog elapsed 1647.527 s，charged 1801.467 s，两个时钟分别保留 |

正式 G0/G1 source SHA 为 b8a20bd24848a83f2f4fa50b1ccaaa4ec9be9672；G0/G1 input SHA 分别为 6654ec211efbc6112f3ccba13ad67ff3a97cdbc471bdd48e39f891819f51a41e 和 989a351fb27fe5320942ca2392d0e7e872909f0354509e5d59c8c25e43061c86。direct source SHA 为 393e5c0dddb933848945ab2e18edb73cf69cc224，direct input SHA 为 c80c921834cb268a9251459795fbda5acf4e9f25347d16ee24dec3b9d85c6c56。direct 原始 physical SHA 为 1f53e9f90d63a595b1184a975ab1dce12d4fa1362f86f224753584e3992e17bc；规范化 physical sections 后等于 G0 的 51854af3fb60c7ffebb166e1f06ff0a89e2e184dcbd9ba06ab4beb321b920661；唯一差异是 assembly backend 标签。ordered mode SHA 为 c3ff9c0cf35e2d183f44ed3fb7448d4aa586bb6fdf7f9dc9ba78dc25011c693a。

R、T、A_balance 来自端口模态振幅；A_volume 是在实体含硅区域对吸收积分。它们表示反射、透射和两种吸收核算；能量闭合用来检查功率账是否相符。负的闭合误差是实测带符号差值，不是失败标签。G0/G1 都是 strict identity 与真实 full residual 同时通过后生成的正式离散结果，状态仍为 authority-limited，因为参考、网格和 mode 截断的适用范围有限。

## identity 缺陷与修复

恢复 identity 检查的是：局部消去单元内部未知量后，重新构造完整电磁场，代回原方程是否仍与凝聚计算一致。旧实现把精确单元宽度四舍五入到 12 位后作为局部算子缓存键；略有差异的几何宽度可能错误共用一个缓存算子。attempt4 因此记录 native identity 3.0748104980683956e-10，大于 1e-10 限值，同时 full A6 为 0.16667295750232392。原 worker 分类 V20_RELEASE_GATE_FAIL 保留为历史负结果。

修复只让 Task40 p6 局部算子缓存按精确几何身份取键，未更改方程、材料、模式或 strict Gate；legacy profile 默认不变。R1 中的离线回放使用保存的第 8 步向量，strict identity 重算为 1.3369675137611322e-11，通过 1e-10。回放未装配全局 p4 因子或做 fresh solve，且抽查单元覆盖不完整；这项缺口仍保留。其后 fresh G0/G1 运行分别以 1.5206e-11 和 3.2543e-11 通过 strict Gate，依据是正式运行本身，而不是离线向量回放。

## 同离散参考与网格比较

同离散参考用完整场原方程残差验证 MUMPS 解，再与 G0 iterative 场比较。主控对保存数组做独立离线重算：从 b、Ax 数组重算 norm(b-Ax)/norm(b)=5.055376131651821e-11；它与记录相同，残差向量的逐元素最大差为 0。匹配比较状态为 MATCHED_REFERENCE_PASS：FE L2 相对差 1.0644e-7、scaled-curl 相对差 1.0590e-7；固定坐标 E/H 与界面迹全部低于 4.9591e-7；80-mode outgoing amplitude 向量整体相对差 1.3374e-7；每模功率最大绝对差 7.5071e-8。R/T/A/A_volume 最大总量绝对差为 7.5915e-8，小于 1e-5 的参考限值。场差说明 iterative 解在本 G0 离散上紧贴该 direct reference，不构成连续解误差估计。

G0 到 G1 的固定坐标总场 E/H 相对变化分别为 0.37395% / 0.39272%，最大逐 z 平面变化为 0.4031%；总 R/T/A_balance/A_volume 的绝对变化均小于 0.000473，过任务 0.001 工程 Gate。该比较使用 4,000 个共同采样点与相同 80-mode keys，只支持这两个网格的工程一致性，不证明连续收敛。通道截断状态仍为 CHANNEL_TRUNCATION_UNQUALIFIED。

### Setup、求解和后处理时间

| 模型 | setup | outer adapter | KSP-only | final native / release checks | official postprocess | 主内存对象记录 |
|---|---:|---:|---:|---:|---:|---|
| G0 | 373.096 s | 798.552 s | 787.135 s | 2.045 / 8.730 s | 11.707 s | worker inventory peak 4,429,493,610 B；workspace peak 1,731,541,832 B；Krylov workspace upper 80,909,824 B；同时树RSS峰 3,776,098,304 B |
| G1 | 908.009 s | 3150.090 s | 3135.913 s | 4.890 / 15.448 s | 14.035 s | worker inventory peak 6,627,841,642 B；workspace peak 1,970,721,416 B；Krylov workspace upper 209,804,800 B；同时树RSS峰 6,855,741,440 B |
| G0 direct | setup/factor阶段无可独立确认的 wall-time 切分 | 不适用 | 不适用 | recovery 0.632 s；其余检查独立阶段时间 unknown | 包含在总 charged 时间内，未独立计时 | PETSc 输入矩阵 MatInfo nz_allocated/nz_used=56,834,000/55,984,880 项；MUMPS INFOG16/17=7,932/7,932 decimal MB、INFOG18/19=8,277/8,277 decimal MB、INFOG22=6,798 decimal MB、INFOG29=346,831,808因子项；同时树RSS峰 11,505,573,888 B，峰值worker stage fine_reference_residual_completed |

outer adapter 已包含 KSP-only；这些时长不能相加当作独立阶段总耗时。direct 计时只报告 watchdog elapsed 1647.527 s 与 launch charged 1801.467 s，不从二者差值分配 symbolic、numeric 或 solve 阶段耗时。PETSc 输入矩阵项数、MUMPS 内存量与 MUMPS 因子项数是三类字段；7,932 MB 是 MUMPS INFOG 预估，不是 RSS 峰值。字段定义见 [PETSc MUMPS INFOG 输出](https://petsc.org/release/src/mat/impls/aij/mpi/mumps/impl/imumps.c.html)。

## 资源、计时与执行偏差

| 阶段成本 | 记录值 | 口径与边界 |
|---|---:|---|
| R1 全 p6 operator identity diagnosis | 14,039.107309384039 s | 单次 full operator diagnosis；未建全局 p4 factor |
| v1 identity-localization builder stop | 约 101 s | 审查修正后主动停止；近似值，保留原 stop record |
| v2 exact-geometry replay | 198.79226663301233 s | 离线用保存向量复核；没有 fresh PDE/KSP |
| 旧 attempt1–4 shared ledger cumulative | 530.8867869906425 s | 历史共享账本累计值，独立于后续 review_v1 runs |
| review_v1 G0 / G1 | 1204.0178907530499 / 4097.993754097028 s | workflow monotonic |
| review_v1 direct | 1647.5270624320256 / 1801.4672110320269 s | watchdog elapsed / launch charged，分开保留 |

这些数字来自不同阶段和时钟，不相加倒推出单阶段工时。R1、v1 stop、v2 replay 与历史 shared ledger 的证据入口见 identity recovery report 和其中链接的 compact records。

三次正式模型的资源口径都是 watchdog 监督的同时进程树 RSS 峰值；G0、G1、direct 分别为 3,776,098,304 B、6,855,741,440 B、11,505,573,888 B。进程树 swap 均为 0；PSS 按 profile 禁用。WSL 全局 swap 计数增加不能归因到这棵任务树，记录为未能归因。direct symbolic admission 估算为 7,932 decimal MB，是准入估计，不是实测峰值或峰值预测。

G0/G1 的 setup monotonic 分别为 373.096 / 908.009 s，KSP-only 为 787.135 / 3135.913 s，official postprocess 为 11.707 / 14.035 s；其他计时见 compact run record。direct reference 没有 iterative KSP 阶段，symbolic / numeric / solve 各自耗时没有可靠独立字段，记为 unknown；不从 watchdog 与 charged 两个计时差推导子阶段。

本次 direct 外层命令直接由 Codex shell 启动，没有经过规定的 user-service wrapper，观察到 cgroup 为 /init.scope。发现偏差后没有重启、迁移或终止这唯一 direct run。独立 subreaper watchdog 仍记录完整进程身份、所有后代退出、exit 0、树 swap 0 与 RSS 峰值。此处如实标为启动纪律偏差，不声称 user service 持有该进程。

## 保留的边界与下一步

| 项目 | 当前判定 |
|---|---|
| G0、G1 离散方程及物理 Gate | PASS，authority-limited |
| G0 同离散 direct reference | MATCHED_REFERENCE_PASS |
| G0–G1 fixed-sample / power agreement | PASS_ENGINEERING_ONLY |
| 80-mode channel truncation | CHANNEL_TRUNCATION_UNQUALIFIED |
| continuum convergence | NOT_ESTABLISHED |
| 约 2 TB 目标容量 | UNKNOWN；不得从三次小模型 RSS 外推 |
| ordinary default / Phase II PC / master merge | 未改变 / 未选定 / 未执行 |

R5 收口没有新增 PDE；R4 review_v1 阶段实际运行了 G0、G1 与一场 direct reference。文档和证据提交后等待 review。旧 attempt1–4、V1 response 与旧 NOT_RUN 快照均保留，并在 run index 与阶段账本中注明时序。下一轮唯一建议候选是任务书 §8.1 的“有界局部问题 + 多层全局波动纠错”：限制各局部问题尺寸，并加入能处理跨子域传播和反射的接口/粗空间校正，避免依赖覆盖全域的大因子。它必须与旧 42 宏块 complete-PC 方向区分；Task39 V11 的 fresh negative 证据已将旧 complete-PC efficiency 排除为 production candidate：64步后 residual 为 0.7666389832389989，node32/64 场差为 0.9384007607744688 / 0.9488237463600627。下一 review 需冻结新传播/接口作用、递归粗空间构造、每层有界局部解法与所有局部因子总预算，再规定对照准确 p4 的验证顺序；这是区别于重用旧42个完整 PC 宏块的机制。本轮不执行 Phase II，也不声称此候选有效。80-mode 截断仍需资格化。选择性合并仍限 compact evidence/docs 与已审阅的可复用修复；Task40 profile 不因此成为 production default。

## 测试与文档核验范围

R4 运行前的 targeted code checks 共 43 项：34 项来自 test_372、test_373 与 test_task40_direct_reference_identity，另有 test_374_reference_incident_quadrature.py 的 9 项。15 项 exact-geometry/R3 修复检查，以及两个 nonzero-RHS/recovery 测试组 3 项和 2 项分别记录在 test summary / identity policy evidence 中，不并入这 43 项。R5 只改结果记录与文档，没有重跑 pytest；全库 pytest、MPI2/4、Ruff 和 CI 未运行。

## 证据索引

- [R5 identity recovery 报告](outcomes/identity_recovery_v1.md)
- [R5 summary](outcomes/summary.md)、[精度与容量](outcomes/accuracy_and_capacity.md)、[测试摘要](outcomes/test_summary.md)
- [identity recovery compact record](outcomes/records/identity_recovery_v1_results.json)、[run index](outcomes/records/run_index.json)、[phase-I ledger](outcomes/records/phase_I_results.json)、[execution-context deviation](outcomes/records/r5_execution_context.json)
- direct ignored artifacts：benchmarks/artifacts/task40extra_0p7nm_engineering/direct_reference_v1/393e5c0dddb933848945ab2e18edb73cf69cc224/；含 full residual、MUMPS summary、matched_reference 与 watchdog summary。主要 SHA 见 compact record。
- formal G0/G1 raw runs：run index 中的完整目录和 file hash；G0 run_id 为 task40extra_0p7nm_nonseparable_g0_iterative_review_v1，G1 为 task40extra_0p7nm_nonseparable_g1_iterative_review_v1。
