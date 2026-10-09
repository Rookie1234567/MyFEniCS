# Task40extra Response V19：one-q 生命周期下 B0 Ny=8 与 E1 p6 小模型通过，原尺寸仍未资格化

V19 在 B0 Ny=8 与 E1 p6 两个缩小离散模型完成完整 Full3D 求解、full explicit A6 残差检查、官方 R/T/A 输出和独立 checker。B0 绑定 source 14f5ee6943458b80b582b723c61cc84afd0efc24、input SHA-256 1c9c907da734e14a583d92ae1ae6aa216b296bddbe710701758b5571387dd0e8、physical SHA-256 e8002d20258fa5c1e4f8f0888bca68f621b1006492f3f1b8aaff6b0d82099903；E1 绑定 source 71042327e5f3a77cd39a1be7b5dfa46afe52db6b、input SHA-256 f34f8bf11bf4ed0715178ca0edc3ead361f50e25f04741f94ae9e50c2301995a、physical SHA-256 6ea7e95a9b415b3bcc97c67e3c4d3580c7a6999211fbfb3f15bc42fad2ce821d。每次只驻留一个 q 的 PETSc 输入矩阵和数值因子；全部 q 的原始稀疏结构、右端项和恢复关系仍保留。它降低并发因子占用，但增加反复 symbolic/numeric build 和 probe 的时间成本。原尺寸 50×25×140 nm、2 TB RAM 和单场 48 h 仍 NOT_QUALIFIED。

## 1. B0 与 E1 的方程、离散和官方结果分别是什么？

这里的 q 是 y 周期边界条件下不同相位的子问题。每个 q 都有自己的方程和必须完成的右端项检查。因子是对矩阵预先做分解得到的数据，使后续右端项能快速回代。one-q 路线一次只把一个 q 的矩阵交给 PETSc 并建立一个因子；一个 q 完成后释放它，再重建下一个 q。数学方程、复数精度、q 集合、右端项和 full residual 门没有改变。

| 模型 | 网格、自由度与 q | A6 真残差与迭代 | R/T/A_balance/A_volume | 独立 checker 与范围 |
|---|---|---|---|---|
| B0 Ny=8 p6 | 4×8×5=160 cells；532 modes；full FE 110,406 rows；q rows 为 4,324/4,324/4,324/4,324/4,248/4,324/4,324/4,324；q NNZ 为 2,274,106/2,284,104/2,285,718/2,268,512/2,203,632/2,275,424/2,284,778/2,283,164 | 3 次迭代；full explicit A6=1.2189184363e-8，native witness=1.2189186015e-8；门限 1e-6 | 0.98427360809 / 0.01424051811 / 0.001485873797 / 0.001485873844 | PASS，checker SHA-256 9f843cd09eeefba80beba1dd53e83f3691aa37450d6ce510bbd32a6502ccd46d；B0 V18 同离散保存输出逐位相同 |
| E1 p6 | 10×4×19=760 cells；588 modes；full FE 514,710 rows；q rows 为 38,424/38,508/38,508/38,508；q NNZ 为 21,018,000/21,325,222/21,336,900/21,329,326 | 3 次迭代；full explicit A6=1.40358436565e-8，native witness=1.40358359784e-8；门限 1e-6 | 0.06235654127 / 0.91592650550 / 0.02171695323 / 0.02171695270 | PASS，588 行和27个输出文件哈希通过；checker 重算保存残差，但没有重新施加 PDE 算子 |

零级反射分别报告为 B0 的 R00_s=0.98424114133、R00_p=8.45323878e-6、R00_total=0.98424959457；E1 的 R00_s=0.06235610892、R00_p=1.16375025e-23、R00_total=0.06235610892。E1 的 R+T+A_volume 闭合差为 5.33416422e-10，A_balance 与 A_volume 的差为 5.33416478e-10。两组结果都是对应缩小几何的离散解，不是原尺寸场或 continuum convergence。

## 2. P4 support 校准实际测了什么，哪些目标值仍只是推导？

独立的 Ny=8 support 校准在 4×8×14=448 个小网格单元上建立真实 p6 FE 空间和 Floquet MPC（周期边界约束），扫描得到完整的目标排列类型覆盖。304,860 个 full FE rows 中有 292,608 个独立行和 12,252 个受约束行；目标 cell permutation code [0,576,4680,32769,36873] 均被校准覆盖。每个折叠 cell 的 trace support 上界为 348，每个目标边界面的保守 support 为 78,336。单进程 RSS 高水位 634,454,016 B，扫描时间 1.601695 s。

随后用完整 32,060-mode manifest 只推导原尺寸 Ny=8 的 CSR 结构上界：目标拓扑 272×8×14=30,464 cells；各 q NNZ 上界为 1,116,372,880、1,112,417,680、1,108,463,632、1,101,217,536、1,080,160,000、1,101,217,536、1,108,463,632、1,112,417,680。八个 q 的结构 payload 上界和为 176,839,493,968 B，最大单 q 为 22,330,568,180 B；相对旧 support=432 fallback 推导减少 90,149,068,800 B（33.765%）。这些是 derived CSR 结构上界，不是实测数值 NNZ、同时驻留内存、factor 或 solver 结果。目标 FE、CSR、因子和 PDE 均未构造。

校准脚本是 ignored artifacts 中的历史研究脚本（1,422行），不应称作轻量wrapper或复制进production；它调用tracked的通用支持计数器及FE/MPC core依赖。校准脚本 SHA 为 eba6ccfa592a4c60f33acc3221e7a524a74b283f71ec94e4956f35e38d4f4335，投影脚本 SHA 为 5714281251c0e34e03b122ed09d170ab9193b506e34d4b4657cd494e1c7c5913；两份 attempt03 receipts 的 SHA 分别为 2c4c9f45f2d3eb635f4b32beab5da4e5604ae5237bc8e1ae26d561ecede09891 和 630e9b57a1ad7419cde7fac9f84e0f36ff8f9f6b3f42d5d3a3d1cfa57a203473。完整依赖 hash 和历史命令见 [sparse capacity compact](outcomes/records/review_v19_sparse_capacity.json)。上述离线文档阶段不重跑 P4。

## 3. one-q 生命周期多做了多少工作，V15 startup admission 实际如何判定？

B0 八个 q 完成56次数值因子build、64次symbolic build和56次probe；E1四个q完成28次数值build、32次symbolic build和28次probe。E1的MatSolve互斥计数为startup RHS=16、PC initial RHS=12、augmentation=0、factor probe=28、other validation=0，总计56。E1数值build elapsed合计223.134 s，重复symbolic合计22.110 s，四q初始symbolic为1.723 s，probe合计3.488 s。阶段时间不再加到launcher/watchdog本场workflow上。

V15 frozen selected/native admission 使用每个case的固定尺度。B0与E1的 candidate regular_inverse_checks 都包含四个完整候选状态；全部q、ordered port modes与interior-only rows被覆盖。每项的 candidate selection 和 reference-PC selection 都选中初始整体状态（index 0），candidate admission 为true，reference PC状态为V15_REFERENCE_PC_PASS。下表列出实际冻结分母；所有八个case均通过。

| 模型 / case | 覆盖 | selected candidate / V15 native | 冻结分母：alpha / full equation / local combined |
|---|---|---|---|
| B0 generic_full_independent | 8 q，532 modes，72,000 interior rows | index 0 / PASS | 257.625768 / 461.492198 / 922.983199 |
| B0 interior_only_all_72000 | 8 q，532 modes，72,000 interior rows | index 0 / PASS | 255.468584 / 380.242919 / 760.483175 |
| B0 nonzero_all_mode_port_rhs | 8 q，532 modes，72,000 interior rows | index 0 / PASS | 49.460818 / 1,249.388313 / 2,467.837990 |
| B0 physical_regular_incident_rhs | 8 q，532 modes，72,000 interior rows | index 0 / PASS | 1.824553 / 2.707980 / 2.707980 |
| E1 generic_full_independent | 4 q，588 modes，342,000 interior rows | index 0 / PASS | 391.656333 / 994.954352 / 1,407.077889 |
| E1 interior_only_all_342000 | 4 q，588 modes，342,000 interior rows | index 0 / PASS | 126.968205 / 828.036427 / 1,171.019049 |
| E1 nonzero_all_mode_port_rhs | 4 q，588 modes，342,000 interior rows | index 0 / PASS | 51.306426 / 1,779.916711 / 2,491.206912 |
| E1 physical_regular_incident_rhs | 4 q，588 modes，342,000 interior rows | index 0 / PASS | 3.310646 / 1.515113 / 1.515113 |

另将一份使用原始 strict normalization 的 E1 physical_regular_incident_rhs receipt 原样保留为独立负诊断：original regular equation=1.1132298656e-10（限值1e-10），independent sector action consistency=1.3329901315e-11（限值1e-11），two local original equations=1.1029072508e-10（限值1e-10）。这份 receipt 与上表 E1 case 使用完全相同的冻结分母（alpha/full/local = 3.3106462004/1.5151129763459958/1.5151129763459956）；三项超限是相对于各自原始 strict 限值。正式 selected/native admission 按 V15 事先冻结的合同判定：alpha closure ≤1e-9，完整增广 FE、消元 FE、non-cancelling budget 和每 q 实际 MatSolve ≤1e-8，初始 factor probe 仍须 ≤1e-10，并满足 mapping、覆盖与结构门。该 case 的 selected 指标依次为 q residual/alpha closure/完整增广 FE/消元 FE/non-cancelling budget = 6.85399e-11/2.54595e-13/1.05721e-10/1.11323e-10/1.72444e-10，因此满足 V15 合同。V19 没有调整阈值或分母；正式 PASS 不表示这三项 strict 诊断也通过。

三次reference-PC apply也均通过V15 bounded总门。B0所有q残差严格低于1e-10。E1第二次调用q=0为1.0923441544e-10，高于strict 1e-10但低于原bounded限值1e-8，应标为bounded-inexact-only；另两次E1调用的q残差低于strict限值。alpha closure限值1e-9，完整增广FE、消元FE和non-cancelling budget各1e-8，原始分解闭合限值1e-10；三次调用的其余项均在冻结门内。fresh factor probes最大残差为B0 9.94558776e-12、E1 2.18626913e-11，所有q低于strict限值。逐case分母、原始严格诊断receipt及完整metrics见[component closure compact](outcomes/records/review_v19_component_closure.json)。

E1第一次启动scope attempt在numeric/KSP之前失败，因为q=4的E1被错误要求提供只适用于B0 Ny=8的V18启动receipt。失败attempt、source和worker分类均保留。最小修复按q_count/profile限定该要求，修复定向测试57 passed in 3.48 s。冻结源码71042327e5f3a77cd39a1be7b5dfa46afe52db6b的E1第二次正式运行通过，未覆盖失败目录，也未在本轮再次运行PDE。

## 4. B0 Ny4/Ny8 模式比较是否完成，下一次精度对照是什么？

V19 按 Review V19 §2.3 对保存的 B0 Ny4/Ny8 数组新做了 all-mode mixed gate。每个模式的绝对幅差不超过两项之和：入射数组 L2 范数的 1e-8 倍，加上 Ny4/Ny8 两个幅值中较大者的1%。判定式为：

```math
|a_{8,j}-a_{4,j}| \le 10^{-8}\lVert a_{\mathrm{inc}}\rVert_2 + 0.01\max(|a_{4,j}|,|a_{8,j}|)
```

incident arrays 逐位相同且范数为1；比较使用 boundary_plane gauge，不拟合相位。532/532通过，0失败。最大绝对幅差为2.86767961e-10（top (0,0,s)），最大混合门比值为0.0008598042（bottom (-4,-2,s)）。常规以 Ny4 单通道振幅作分母的最大比值4.766出现在近零 bottom (1,2,p)，其绝对差仅6.61242198e-16；该大相对比值不推翻混合门。所有逐通道功率差都已保存，但没有另造功率阈值。R 的差为-5.6233e-13，T 的差为-3.3505e-11。

V18 compact 中原先的 NOT_EVALUATED_NO_FROZEN_B0_SIGNIFICANT_MODE_SET 历史结论保留，不改写成事前已有规则；V19 这个新的全模式混合观察门单独登记。它只支持该 B0 小几何下的 saved-field agreement，不是 continuum convergence。新 runner 和输出收据分别为 v19_b0_y4_y8_mixed_mode_gate.py SHA-256 54b8c92c290e95b1780082ad67154ad67b29434fe868b35508aad869c3d04b4e、JSON SHA-256 28ca4936017a48db2e3a80a625a99122e8d41d8b92894b7aec4bff3c58cb9a53。

下一项精度对照只登记设计：同一 E1 物理模型、材料和 p6，Ny=4 对 Ny=8，固定 Nx=10、Nz=19、几何、缺口、材料界面、入射、方位角与全部588个有序 mode keys，只细化 y，网格 cells 从760变为1520。共同子单元的 E/H/scaled-curl 使用冻结 Ny4 reference 范数；若分母为零则给绝对差并将相对值置 null。比较 R/T/A_balance/A_volume、全部入射归一化复振幅和每通道功率。拟冻结的观察门为场和 scaled-curl 相对 L2 1%、R/T/A绝对差1e-3、全部模式振幅混合门沿用上式；逐通道功率全部记录，若要判通过需事前另冻结阈值。该计划尚未运行；启动正式 E1 Ny8 前需要完成该新模型的operator qualification和资源admission，当前已资格化runtime无需重装。

## 5. 同时内存、阶段时钟与原尺寸结论是什么？

B0 同离散 V18/V19 对比中，process-tree RSS 峰从4,869,050,368 B变为4,012,605,440 B，cgroup peak 从5,899,956,224 B变为5,152,567,296 B；这是两次 source revision 不同的整场运行差，不能全归因于 one-q。MUMPS factor allocated/used 字段是因子自身十进制 MB 上界，不是 process RSS。E1 process-tree/cgroup peak 为12,093,280,256/12,555,325,440 B，任务 tree/cgroup swap均为0，OOM/OOM-kill均为0。PSS 的记录为 JSON null，状态 DISABLED_BY_PROFILE。

E1 owner payload 只是部分记录：local Schur 689,762,304 B、shared identity cache 1,620,000 B、unique port owner 682,970,496 B、带 alias 的 port payload 和834,531,584 B、local carrier 562,975,744 B、HP 9,408 B、Hhat 0 B。它们不是完整 time-indexed 并发账；空 inventory entries 不代表零 live memory，payload 与 RSS 峰的时间重合、释放回 OS 和 allocator retention 仍未知。

| 时钟边界 | B0 Ny=8 | E1 p6 | 说明 |
|---|---:|---:|---|
| launcher/watchdog full-case workflow（run_case parent monotonic） | 2501.905429 s | 6584.210970 s | 本场 launcher/watchdog workflow；不是净 worker-only 时间 |
| watchdog resource-authority | 2501.784192 s | 6584.038481 s | 独立采样时钟，不与 parent相加 |
| solver parent | 43.886409 s | 390.730518 s | 不是 KSP子阶段之外可额外相加的总账 |
| KSP child | 40.887723 s | 376.171057 s | child与parent范围有重叠 |
| factor audit setup | 2.103701 s | 11.684010 s | 后端初始 symbolic 等阶段；不是完整 FE setup |
| KSP event记录到worker complete | 15.044710 s | 141.353212 s | event-tail范围，不补全缺失前置阶段 |

UTC run manifest 分别记录 B0 03:36:16.766628–04:21:42.075276 和 E1 06:50:08.021483–08:50:10.136128（2026-10-09 UTC）。这与monotonic和watchdog采用不同边界，不能相加。checker在worker后运行，checker耗时和activation/ABI前置准备时间均 UNKNOWN；实际发生在worker内的cache-miss JIT已经计入workflow，但现有记录不能给出完整冷JIT成本或完整cold activation-to-required-checker时间，不补造早期阶段起点。

原尺寸的最终网格、target numeric NNZ、factor大小/耗时、local/port owner并发和evanescent模式截断均未知；没有构造目标FE/CSR/factor/PDE。2,000,000,000,000 B和172,800 s目标仍NOT_QUALIFIED，不表示数学上不可计算。主控收口沿原窗口追加sequence 55985：截至该采样累计保守扣费31324.373505 s，剩余数值预算54475.626495 s；这是截至收口的经过时间账，不是PDE CPU总和，也不包含未记录的窗口前准备费用。完整UTC/monotonic/boot、未刷新的T0/deadline及收据hash见[cost/readiness compact](outcomes/records/review_v19_cost_and_readiness.json)。旧费用、unknown与失败保留；剩余预算不授权新增算例。执行者不commit/push，主控集中审查提交推送；不合并master。

## 收口测试与证据索引

收口阶段使用 Task40 专用 local_w0_wsl qualified runtime；ABI preflight核验 complex128、int32 和同一Linux runtime prefix。最终文档定向测试、JSON/diff检查和日志路径写入 [test summary](outcomes/test_summary.md) 与 [run index](outcomes/records/run_index.json)。full repository pytest、MPI4和CI未运行，不据此声称通过。完整数值、资源、失败和compact证据分别见 [outcomes summary](outcomes/summary.md) 与四份 V19 compact。
