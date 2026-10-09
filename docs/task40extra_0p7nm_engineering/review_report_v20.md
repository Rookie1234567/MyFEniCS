# Task40extra Review V20：结束小模型基线阶段，接通原尺寸分阶段入口

## 0. 结论与下一步决定

**接受 V19，裁决为 `PASS_WITH_QUALIFICATIONS`。单 q 因子驻留已在 B0-Y8 上保持同离散结果一致，并把当前 p6 reference 路线的 E1 从资源停点推进到完整场。此前约定的小模型最低退出条件已经达到。V20 的主交付改为原尺寸可执行入口、真实目标几何及有界局部/端口组件实测，以及可交接的分阶段运行包；条件允许时只新增一个 E2 完整增长案例。**

这项决定回应两个实际问题：新预条件器的少迭代尚未带来整场成本优势；继续重复相近小模型不能证明原尺寸的内存、时间和精度。下一轮继续使用已有 p6 reference 数学路线与 `ROW_TILE_BOUNDED_CSR_V17 + ONE_Q_REFACTOR_V19`，把工作直接接向真实 `50×25×140 nm` 几何。V20 不以开发第三个预条件器为主任务，也不以 E1 的 Ny=4→8 作为原尺寸准备的前置条件。

| 事项 | 当前结论 | 本报告决定 |
|---|---|---|
| B0-Y8 同离散正确性、单槽生命周期 | 已通过所测范围 | 冻结为回归基线，无改动不再跑完整场 |
| 当前 p6 reference 的 E1 完整场 | 首次完成，原 A6、官方输出、checker 通过 | 小模型阶段最低退出条件达到 |
| 新路线相对旧 p4 的整场优势 | 尚未证明；E1 历史比较仍更慢、峰值更高 | 优先查明外层构建及对象库存，不以三步迭代替代成本判断 |
| 原尺寸候选与 32060-mode 库存 | 有 recipe、身份及结构上界；没有贯通的正式输入/运行入口 | 实现受限参数化与阶段停止点，取得真实目标组件数据 |
| E2 新 p6 reference | 尚未运行 | 唯一条件完整增长案例；资源停止不能阻塞目标准备 |
| 最终 0.7 nm / 2 TB / 48 h | `NOT_QUALIFIED` | 必须由目标阶段实测及最终精度资格关闭 |

**V20 的实质增量应是“已经能按受控步骤进入原尺寸”，并带有真实目标几何、对象和组件成本证据。只有一份外推表或几个新增 PASS 标签，不构成本轮主要交付。**

## 1. 审阅身份与证据范围

| 项目 | 身份 |
|---|---|
| 仓库 / 分支 | `Rookie1234567/MyFEniCS` / `task40extra_0p7nm_engineering` |
| 审阅日期 | 2026-10-09 UTC |
| 本次远程 base | `77ef699156f95fb24e0a75e215d61458bfdedcea` |
| base 时间 / 说明 | `2026-10-09T10:29:29Z` / `Task40 V19: close out one-q B0-Y8 and E1 full-solve evidence` |
| 上轮 Review V19 提交 | `19b7993380728f5c940194b8c4fff4c640d0b4ff` |
| B0-Y8 成功数值 source | `14f5ee6943458b80b582b723c61cc84afd0efc24` |
| E1 首次失败 source | `f23d907bbb60249cbd2844921ca86cfd43f84658` |
| E1 成功数值 source | `71042327e5f3a77cd39a1be7b5dfa46afe52db6b` |
| 后续执行目录 | `/home/shenjh/Projects/MyFEniCSx_task40extra_0p7nm_engineering` |

Review V19 至本次 base 共 5 个提交、32 个变更文件。本次读取 response、四份 V19 compact、run index、summary/test summary、输入、几何/profile、q 装配、MUMPS、worker、checker、资格复用及恢复相关源码，并回读 E1/E2 历史结果和目标 recipe。对四份 compact、response、summary、test summary、任务 README 与 docs README 共九份远程原始 UTF-8 内容，重算 SHA-256 与 Git blob，均与提交内容及索引一致。[S1]–[S8]

这项核验确定的是远程文本身份。完整 FE 场、q CSR、因子、原始 events 和资源采样位于执行机 ignored artifacts/results；本次没有读取这些二进制数组重做数值计算。因此，下文的“实测”指已提交记录所报告并绑定原始证据的实测；引用 checker PASS 不表示 ChatGPT 本次重新施加了 PDE 算子或运行 checker。

本报告只新增 review，不改数值实现、不启动计算。后续由既有 Task40 执行者实现、测试和运行，既有主控冻结源码并集中提交/推送。继续原分支与 canonical worktree，不新建 Codex 聊天、项目、checkout/worktree，不启用 Codex collaboration subagents 或定时自动化，不 SSH、不切到工作站、dot、Task042 或其他项目，不写 master。普通工程修复在本报告范围和既有窗口内连续推进。[S20]

## 2. V19 的数值进展值得接受

### 2.1 单槽改变了因子驻留，没有另换物理方程

当前研究路线的参考预条件器是 p6 的结构化 y-orbit/q 参考逆；旧路线以 p4 reference correction 帮助求解 p6 目标。两者都服务于原三维非可分 p6 目标方程。V19 在已有 p6 reference 上改变的是存储生命周期：全部不可变 q CSR 继续保存，每次至多驻留一个 q 的 PETSc 输入矩阵与数值因子，需要另一个 q 时先销毁当前槽，再构建新槽。[S2]、[S9]、[S10]

因此，V19 的直接作用是减少同时存在的因子和 PETSc 输入对象，并付出重复 symbolic、numeric 和 probe 的成本。它不会自动消除全部 q CSR、局部 LU/Schur、恢复数据、端口库存和外层向量。

### 2.2 两个完整小模型均通过

| 指标 | B0-Y8 V19 | E1 V19 |
|---|---:|---:|
| 网格 cells / p6 full rows | 160 / 110406 | 760 / 514710 |
| axes / ordered modes | 4×8×5 / 532 | 10×4×19 / 588 |
| 外层迭代数 | 3 | 3 |
| 完整原 A6 相对残差 | 1.2189184363208502e-8 | 1.4035843656500764e-8 |
| 独立 native A6 witness | 1.218918601504642e-8 | 1.4035835978415286e-8 |
| R | 0.9842736080921147 | 0.062356541266734324 |
| T | 0.014240518110484091 | 0.9159265055048301 |
| A_balance | 0.001485873797401182 | 0.021716953228435587 |
| A_volume | 0.0014858738441830876 | 0.02171695269501911 |
| R00_s | 0.9842411413335236 | 0.06235610892320111 |
| R00_p | 8.453238781901373e-6 | 1.163750254047193e-23 |
| 最大同时 live factor / PETSc matrix | 1 / 1 | 1 / 1 |
| 官方输出 / 保存输出 checker | PASS / PASS | PASS / PASS |

以上来自正式结果与组件记录。[S2]、[S4] B0 的新旧同离散比较中，已检查的场、模式、几何和参考数组逐位一致；应限定为已检查数组，不能扩大为所有未检查对象都相同。其比较 receipt SHA 为 `7265419fd3b30b7a30933417270c65be46af5a989b22b120ffa8d372fb3fc969`，checker SHA 为 `9f843cd09eeefba80beba1dd53e83f3691aa37450d6ce510bbd32a6502ccd46d`。

E1 成功 run 为 `20261009T065008.007716Z`。它实际使用 `ROW_TILE_BOUNDED_CSR_V17 + ONE_Q_REFACTOR_V19`，而非上轮停点采用的 legacy 入口。588 个 mode rows 均完整，27 个输出文件 hash 被检查；checker SHA 为 `1a92ae14fae3637711cb214d2d339e63388ce39d87f22da31f95efb497037490`。保存输出 checker 重读、重算已保存的残差和物理证据，没有再施加一次完整 PDE 算子。[S4]、[S12]

这里的进展应准确表述为“当前 p6 reference 路线首次得到完整 E1”。历史旧 p4 路线已经解过同一 E1，不应把 V19 写成整个项目第一次算出 E1。[S16]

### 2.3 计数、残差门与保留负诊断一致

B0 有 8 个 q，E1 有 4 个 q。两个正式场均观察到 4 次 startup 完整作用和 3 次 PC 完整作用，没有额外 augmented correction。因此 B0 实际 numeric/probe 各 56 次、symbolic 64 次；E1 numeric/probe 各 28 次、symbolic 32 次。E1 MatSolve 的互斥总账为 startup 16＋PC 初始 12＋probe 28＝56，augmentation 与其他验证为 0。后续目标不能预先保证仍是“4＋3”次完整作用。[S2]、[S5]

E1 某次实际 q solve 为 `1.0923441543837498e-10`，超过旧 strict `1e-10`，但通过 V15 预先冻结的 bounded-inexact `1e-8`。全部 fresh-factor probes 仍通过 `1e-10`，E1 最大值为 `2.186269126691737e-11`。另有 physical-regular-RHS 的三个 strict 诊断超过各自 `1e-10/1e-11/1e-10`；与正式 selected/native case 使用同一冻结分母。正式判定依照此前 V15 的 q/native FE/non-cancelling budget `1e-8`、alpha `1e-9` 等合同通过，V19 没有改变阈值或分母。[S2]

接受本轮 PASS，同时保留 strict 负诊断。不把这些已解释的合同差异重新变成必须重跑 B0/E1 的任务，也不把既有 bounded-inexact 合同描述成全部 strict 指标通过。

### 2.4 已修复的工程失败与局部恢复不再重复卡住

E1 首次 attempt 在 numeric/KSP 前失败，原因是 q=4 的 E1 被错误要求提供 B0 Ny=8 的保存 startup receipt。后续按 q/profile 收窄要求，定向测试 57 passed，冻结 source 后第二次完整场通过；失败目录和原身份保留。这是必要修复后继续推进的正确做法。[S1]、[S7]

原目标保存 S2 数据的直接 LU forward error 曾为 top `2.20293e-11`、bottom `2.42443e-11`，超过 `1e-11`。**V17 已在同一保存数组上用同因子残差修正关闭这项回退**：修正后为 `5.35247e-14`、`5.14331e-14`，独立 checker PASS。原矩阵和解保持 complex128；残差用 complex256 累加，每面最多 3 次，只接受原矩阵残差改善，known state 仅供验证。[S18]

这个已关闭的小系统问题不应再次无改动重跑。新目标 local/port 组件需要明确接入同一有界 helper，并在新的真实单元上保持 known-state forward `1e-11` 与原局部方程 `1e-10`。V17 保存小系统 PASS 不自动覆盖所有 production cell；V15 的 `1e-8` 也不能取代这个独立 forward 门。

## 3. 内存确有进展，但整场成本仍是主要问题

### 3.1 B0 实测峰值下降，workflow 略增

| 同离散 B0 指标 | V18 all-q | V19 one-q | 变化 |
|---|---:|---:|---:|
| process-tree RSS peak | 4,869,050,368 B | 4,012,605,440 B | −856,444,928 B，−17.590% |
| dedicated cgroup peak | 5,899,956,224 B | 5,152,567,296 B | −747,388,928 B，−12.668% |
| run_case workflow | 2474.995817 s | 2501.905429 s | ＋26.909612 s，＋1.087% |

这是两个冻结 source 不同的整场观察。逐位一致和单槽计数支持存储方案有效，但不能把全部 RSS 差严格归因于 one-q，也不能把 MUMPS allocated/used 字段之差当成实际 OS 释放量。[S3]、[S5]

### 3.2 E1 确实完成了，但尚未赢过旧路线的历史整场成本

| 同物理 E1 历史比较 | 旧 p4 reference | 新 p6 reference V19 |
|---|---:|---:|
| run_case workflow | 4580.375191 s，76.340 min | 6584.210970 s，109.737 min |
| process-tree RSS peak | 10,650,341,376 B | 12,093,280,256 B |
| 纯 KSP | 3722.192948 s | 376.171057 s |
| 完整原 A6 | 9.781668525522113e-7 | 1.4035843656500764e-8 |

新场 workflow 比历史旧场高约 **43.748%**，RSS 高约 **13.548%**。两场来自不同冻结 source/runtime 历史，不能称受控的因果性能实验；旧场残差精度也较低，但仍通过原 `1e-6` 门。它们足以说明：当前记录尚不支持“新预条件器已经让完整计算更快、更省内存”。R/T 等量的接近也不替代完整同离散场比较。[S5]、[S16]

V19 E1 的 cgroup peak 为 **12,555,325,440 B**；task tree/cgroup swap 均为 0，OOM/OOM-kill 为 0，PSS 明确为 null/`DISABLED_BY_PROFILE`。V18 E1 只到 symbolic 的 RSS 约 12.518 GB，不能把它与新完整场的 12.093 GB 写成同工作量性能对照。[S3]

### 3.3 因子更省并发，但全部 CSR 和其他大对象仍在

E1 四 q rows 为 `[38424,38508,38508,38508]`，NNZ 为 `[21018000,21325222,21336900,21329326]`。按实际 int32 索引与 complex128 值计算，四 q CSR payload 合计 **1,700,804,768 B**，最大单 q **426,892,036 B**；这些 CSR 全部保留。[S3]

| E1 因子字段 | 数值及含义 |
|---|---|
| 各 q allocated upper | [1.627, 1.647, 1.648, 1.610] 十进制 GB |
| 单槽最大 allocated / used upper | 1.648 / 1.445 GB |
| 串行各 q allocated upper 的和 | 6.532 GB；反事实全驻留字段合计，不是本场同时峰值 |
| 最大 1 次 numeric 子阶段 | 20.031521 s |
| 28 次 numeric 子阶段和 | 223.134378 s |
| 28 次 fresh symbolic / 4 次 initial symbolic | 22.109799 / 1.722654 s |
| 28 次 fresh probe | 3.488056 s |

源码中的 numeric 计时只包围 numeric 调用；`cache_miss_parent_seconds` 还包括转换、身份、准入及审计等工作，且其计时起点前另有扫描/准入，eviction 也有独立成本。因此 223.134 s 不是“全部重新分解成本”，以上子阶段的和也不是完整生命周期成本。[S9]

已记录的 E1 owner 只有部分：local Schur 689,762,304 B，共享 readonly identity 1,620,000 B，unique port owner 682,970,496 B，local carrier 562,975,744 B。含 alias 的 port payload 和 834,531,584 B 不能再与 unique owner 相加。231 类 LU/恢复等数量存在，但完整 payload、同时驻留、最后使用点和 allocator retention 未闭合；`entries={}`、`inventory_peak_bytes=0` 表示未记录。[S3]

下一轮先从已有 build history/events 读回 cache-miss parent、conversion、symbolic、numeric、probe、eviction 的包含关系，以及真实销毁前后的 RSS/cgroup 样本。缺失项保持 UNKNOWN，不能为补表重跑旧场，也不能在尚无测量时承诺释放某个 GB 数。

### 3.4 优化重点应由整场时间决定

E1 的 KSP child 376.171 s 约占 workflow 的 **5.71%**，solver parent 390.731 s 约占 **5.93%**，numeric 子阶段和约占 **3.39%**。这些是嵌套口径，不可相加。外层 solver 之外有大量工作，但现有 compact 不能把全部余量直接归给 FE 装配、JIT、端口或某一个对象。[S5]

这意味着下一轮最有价值的测量是“外层构建究竟在何处花时间、保留了哪些独立 backing”。继续单独追求把三次迭代降到两次，尚无证据能解决当前整场瓶颈。

全冷启动时间仍 UNKNOWN。E1 run_case 为 6584.211 s，而 UTC manifest 区间为 7202.114645 s；两者时钟和边界不同。必要 activation/ABI、冷 JIT 范围以及 worker 后 required checker 缺少统一完整父时钟。新必要 E2 或目标组件/阶段运行，应从执行必要 activation 之前记录 UTC、monotonic、boottime/boot_id，到 required checker 完成；worker 内实际发生的 JIT 已包含在 worker 父时间，不要再重复收费。历史缺失不补造，不为计时回归单独新增 PDE。[S5]

## 4. 原尺寸边界收紧了，但还没有目标容量证明

### 4.1 176.839 GB 是更紧的结构上界

V19 在 `4×8×14=448` 个小网格单元上建立真实 p6 FE/MPC，覆盖目标排列集合 `[0,576,4680,32769,36873]`，将 Ny=8 folded cell trace support 上界从 fallback 432 收紧到 348。校准 FE full/independent/slave rows 为 304860/292608/12252；单进程 RSS 高水位 634,454,016 B，support 扫描 1.601695 s，不包含完整 activation/import/PDE。[S3]

对候选 `272×8×14`、边界 support 上界 78336、全部 32060 modes，使用：

```math
\mathrm{NNZ}^{\mathrm{upper}}_q
=272\cdot14\cdot348^2+2\cdot78336\cdot M_q+M_q^2,
\qquad
B^{\mathrm{upper}}_{\mathrm{CSR},q}
=20\,\mathrm{NNZ}^{\mathrm{upper}}_q+4(n_q+1).
```

复算得到全 q payload 上界 **176,839,493,968 B**，最大单 q **22,330,568,180 B**；较旧 fallback 上界 266,988,562,768 B 少 **90,149,068,800 B，33.765%**。这是结构估计被收紧，没有实际在目标模型上节省 90 GB，也没有测得目标数值 NNZ、factor fill、RSS 或时间。[S3]

目标拓扑推导为 30,464 cells、20,181,348 full rows、19,897,344 periodic independent rows。q modes 为 `[4076,4052,4028,3984,3856,3984,4028,4052]`，augmented rows 为 `[777644,777620,777596,777552,777424,777552,777596,777620]`。这些结构量通过当前 int32 上界检查，不代表目标 native FE、CSR 或 MUMPS numeric 已通过。

### 4.2 不能从 E1 线性放大出 2 TB / 48 h

最终必须同时满足：

```math
M_{\mathrm{task,peak}}+M_{\mathrm{OS+other,reserve}}
\le 2{,}000{,}000{,}000{,}000\ {\rm B},
\qquad
T_{\mathrm{single\ field,required\ path}}\le172800\ {\rm s},
\qquad
\mathrm{task\ swap}=0.
```

任务峰值应从实际同时存在的独立 backing 计算：真实目标与参考局部库存、全部 q CSR、active PETSc 输入、live factors、numeric workspace、外层向量、恢复/输出等，并与真实资源采样对齐。共享 backing 只计一次，MUMPS 字段、RSS 与 cgroup 各自保留口径；实际 OS 和其他常驻进程预留不能设为 0。

时间需要包括必要准备、JIT、网格/局部/端口/q 构建、startup、全部 factor/solve/probe、恢复、输出和 required checker。可作成本模型：

```math
T_{\rm field}
=T_{\rm prepare+build}
+\sum_q B_q\,t_{\rm factor,q}
+T_{\rm solves+validation}
+T_{\rm recovery+output+checker}.
```

这里各项必须是互不重复的真实父/子分项，`B_q` 为实际或明确标为场景的构建次数。因子 fill 与时间、目标迭代次数和 local/port 共享类别不能按 cells 或 E1 行数简单线性外推。当前 one-q 是笔记本准入方案；以后若 2 TB 的实际余额允许合理驻留和重用，可以据目标实测减少重复分解，不能永久强制一槽而牺牲 48 h。

### 4.3 小模型的退出条件已经达到

B0 的缩放比为 `7/135`；在 0.7 nm 下的小几何电尺寸与原几何在 13.5 nm 下相当，但材料仍是 0.7 nm 的材料，不能当作物理上完全相同的问题。原尺寸在同 0.7 nm 下，每方向电尺寸约为 B0 的 19.286 倍。小模型主要证明 FE/Floquet/DtN、凝聚/恢复、q 映射和生命周期在已测输入上正确，不证明原尺寸收敛、因子容量或最终精度。[S1]、[S14]、[S17]

此前需要的是一场新 B0 同离散完整比较、真实内存/时间/调用账，以及一次有意义的 E1 完整推进。V19 已完成这些最低条件。B0 Ny4/Ny8 保存场的新增全 532-mode 混合门也已通过；这是事后新登记的 V19 工程一致性观察，V18 原 NOT_EVALUATED 保留，不能称 continuum convergence。[S4]

**从 V20 起，B0/E1 默认只用于针对真实改动的回归。没有新物理或实现问题时，不再把更多相近小模型 PASS 当作主线里程碑。**

## 5. V20 主合同：让原尺寸成为真正可执行的 case

### 5.1 目前缺少的是接线，不能再只维护结构表

当前输入目录没有原尺寸正式 dat。几何验证依赖全局 `SCALE=7/135`，E1/E2 再乘 1.25/1.5；profile registry 没有原尺寸和新 E2 p6 reference。one-q inverse 只接受明确的 V17 E1 / V18 B0-Y8 profiles，checker、worker、launcher 等也有固定 run/input/profile 绑定。这些限制保护了现有证据身份，但使目标 recipe 尚不能直接通过生产入口。[S9]–[S13]、[S19]

V20 增加两个显式受限 case，名字可按仓库规范调整，但身份及职责不能混淆：

- `E2_P6_REFERENCE_V20`：既有 E2 物理/网格/模式，新的 p6 reference + row-tile + one-q 路线。
- `TARGET_ORIGINAL_NY8_RESOURCE_PILOT_V20`：真实原尺寸、Ny=8 的资源/求解器 pilot，精度尚未资格化。

从单一 case spec 接通 input schema/validation、mesh plan、profile、run_case、launcher、worker、inverse、V15 candidate/augmented correction selection 和 output checker。尤其是 `_registered_v15_profile_inventory()` 当前只接受 V15–V18 前缀；仅把 V20 profile 加入 periodic registry 仍会在后续被拒绝。新增 case 应按明确注册且契约完整的能力准入，保留 q/twist/mode closure 和所有资格检查，不靠版本前缀偶然通过。[S21] 使用显式策略字段决定 row-tile、identity sharing、owner hooks、one-q 和 qualification scope。

原尺寸应有独立 geometry identity 和显式 scale=1；不能把全局 `SCALE` 改成 1，也不能借用 E1 的名字掩盖原尺寸。预期 axes/rows/q inventory 必须由独立拓扑公式与冻结输入生成，运行时再从真实 dofmap/MPC/mapper 读回比较；不能将实测值回填 expected 后自行通过。保留旧 dat、旧 profile、旧失败和既有证书范围。

先用轻量正反例确认两个 case 解析后的实际策略、identity、stop stage 和资源预检，实际调用 profile inventory 与 candidate selector，不能只测 input parsing。重点验证“原尺寸 geometry-only 不会意外创建 20M-row p6 空间”“身份不匹配会在 FE 前拒绝”“未具备目标资格不能得到 full-field PASS”。不需要重新跑全仓库测试或 B0/E1 完整 PDE 来证明字段接线。

### 5.2 冻结原尺寸主 pilot 的具体 recipe

| 项目 | 原尺寸 V20 主 pilot |
|---|---|
| 几何尺寸 / z 范围 | 50×25×140 nm / [-10,130] nm |
| 波长 / 材料 | 0.7 nm；当前 Task40 的 Si/air 复折射率与原材料身份 |
| 主光栅 | x=[16.5,33.5]、y=[0,25]、z=[0,120] nm |
| 三维缺口 | [25,33.5]×[6.25,18.75]×[40,80] nm |
| x 断点 / 分段 cells | [0,16.5,25,33.5,50] / [78,58,58,78] |
| y 节点 | 0,3.125,6.25,…,25 nm，共 8 cells |
| z 断点 / 分段 cells | [-10,0,40,80,120,130] / [1,4,4,4,1] |
| 主网格 | 272×8×14，30464 cells，p6 |
| 模式库存 | 保存的全部 32060 AUTO 传播模式；实际 mapper 读回并逐 key 绑定 |
| 入射/偏振/原点/相位/参考面 | 由保存目标 manifest 与当前 Task40 定义实读冻结，不从 B0 的不同方位角复制 |
| 判定范围 | 原尺寸资源和求解器 pilot；最终 h/p/倏逝模式精度未资格 |

这是把已有 target recipe 落到真实输入，并将 y 主候选取 Ny=8。x/z recipe 原已在 V16 记录中保存；本报告没有把这些节点称为已构建目标 FE。Ny=4 可以保留 metadata/结构对照，本轮不另跑目标 Ny4。[S17]、[S3]

保存 manifest 路径为 `benchmarks/artifacts/task40extra_0p7nm_engineering/target_ledger_v5/original_size_auto_mode_manifest.json`，SHA 为 `52d7ec801de65d11b15aa1b6daff8d2ad43e1f51902dfd91d06597e49715490d`，ordered-mode-key SHA 为 `03c1965cc13d89b256ea61212a5baba9aa97ef7ec20d356b0a04f9d233e95dec`。执行者实读保存文件，核对 λ、材料、入射、物理原点、mode keys 与 generator/source 血统；当前生成器有变化时写清差异和新身份。不能因为数目相同就认为证书相同，不能删模式凑齐 32060，也不能把传播模式库存称为最终倏逝截断已经收敛。

### 5.3 在笔记本上取得真实目标几何与组件数据

这是本轮必须争取的目标实测，不能只写未来命令。

**第一项：原尺寸 geometry-only inventory。** 使用新原尺寸输入构建真实 30464-cell 几何/拓扑、材料标签、缺口与界面平面、几何周期面配对及 cell permutation inventory。分别识别真实非可分目标与结构化参考所需的几何/材料/定向类，并列出其共享关系。只建立几何与必要轻量映射；不顺手构造目标 p6 全局空间、巨大 MPC 数组、全局 C/D、q CSR 或因子。几何面配对通过不能标为 p6 primal/dual mapping 已通过。

**第二项：真实目标 local/port 有界组件。** 在目标实际 cell 尺寸、材料、物理坐标及 0.7 nm 下，按真实类别逐类或覆盖代表构建局部张量、LU、Schur、恢复项。重复类别按生产实现允许的共享关系计数；若只完成部分类型，列明覆盖与未覆盖集合。不能沿用旧 Ny4 的类数，也不能将 E1 的 231 类库存按总 cells 线性放大。

上下边界使用全部保存有序模式，分批执行原生局部行的端口作用和方程检查；可沿用已测的 mode batch=16、point chunk=64 起点，实际批大小和峰值事先冻结。原点、参考面、phase/gauge、上下表面和 mode 分组都绑定真实输入。平移相位与共享模板的关系必须有依据；一个代表面不能自动覆盖所有位置的端口对象。不得构造完整目标 C/D、稠密 32060² Hhat 或全 q 数值 CSR。[S17]、[S18]

局部恢复使用已验证的有界同因子修正机制，保留直接 LU 原值、原矩阵 residual trace、实际尝试/接受次数和 known-state forward；矩阵、解、阈值及最多 3 次修正合同不变。参考已知态不能参与构造解。

组件结果按三类分开：

| 输出 | 必须说明 |
|---|---|
| 实测 | 真实 cell/材料/定向类、上下表面、native rows、mode coverage、独立局部/端口检查、对象 bytes、RSS/cgroup、耗时 |
| 推导 | 以真实类数和生产持有关系计算的目标逻辑库存；逐对象区分 independent backing、alias、共享/最后使用点 |
| 未测 | 目标完整 FE/MPC、数值 q CSR、factor、KSP、完整场、精度与 2 TB/48 h |

若原局部门失败，该组件保持 FAIL/PARTIAL，并作有限、可定位修复；几何库存、其他独立组件和目标运行包继续。已经有效的 V17 保存 S2/D/phase 证据直接复用，不为新 review 编号重跑相同数据。新的计算逻辑进入 `src/`，runner 只做参数和证据组织；不能再把上千行 ignored 研究脚本作为唯一可复现实现。

### 5.4 交付同一生产路线上的阶段停止点

阶段名可以与现有 runner 规范协调；它们是执行停止点，应与现有 `solver.stage` 的数学含义分开，不能通过混用名字绕过资格。原尺寸默认停在 preflight。

| 阶段 | 结果与用途 | 本轮执行范围 |
|---|---|---|
| preflight | 验证 source/input/ABI、case 路由、实际资源、模式/几何身份及阶段预算 | 真实执行 |
| geometry_inventory | 原尺寸几何、标签、类、周期面与排列库存 | 有界执行 |
| local_port_components | 目标尺寸局部/端口组件及 owner/time 数据 | 有界执行 |
| build_and_symbolic | 目标 FE/MPC、q 构建、全部 q symbolic、真实 owner/资源账 | 实现并交接；本轮不在笔记本执行目标 heavy |
| one_q_numeric | 在实际准入后对预声明 q 构建因子、做 probe/实际 RHS，测容量和成本 | 实现并交接；本轮不执行目标 numeric |
| full | 全部必要 startup/q/PC、原 A6、恢复、官方输出及 required checker | 准备入口；目标资格未闭合时明确拒绝 full-field 放行 |

生产流程中的 all-q symbolic-before-numeric 合同保持。首个 numeric q 可以按事前结构估计选取 q0，但 q0 的结构上界最大不保证它具有最大 numeric fill/内存；一次 q0 资源 pilot 不能标成所有 q 都已通过。目标数值试验不需要先物化另一份巨大全局独立 oracle 才允许取得组件资源数据；这不等于获得全目标算子资格。

B0 Ny8 的 64 块/独立全局 Schur 证书、q CSR hashes 和 saved startup receipt 只覆盖原离散，不能直接移给 E2 或原尺寸。分开维护 `geometry/component/resource/operator/full-field` 资格，允许已具备前置条件的资源阶段前进；未来 full 必须具备实际目标映射、全部 q 覆盖、原生算子/恢复见证、原 A6 与物理/输出检查。需要补充的目标算子资格写成具体未关闭项，不能用扩大 allowlist 把 UNKNOWN 变成 PASS。[S10]、[S12]、[S22]

同一次运行可按批准的 stop stage 连续走到后续阶段，避免默认每阶段重建一次大模型。跨进程恢复只有在真实持久化的数据、hash、ABI 和持有关系可验证时才称复用；未保存的因子不能声称仍在。重启发生的重建成本计入真实 workflow。阶段停止使用正常、完整的 partial-result footer：标明完成阶段、`official_result=false`、未运行项和预算消耗，不伪装成完整场 PASS。

交接包必须包含冻结 dat/profile/mesh/mode 身份、必要源码依赖与 ABI 条件、默认 preflight 和各 stop-stage 的可复制命令、每阶段资源准入/停止规则、outer clock/资源采样、输出路径/schema、恢复限制和当前资格表。应验证命令路由与轻量停止行为，并用下节 E2 尽可能验证同一路径的完整流程。所谓“已准备目标 full 命令”不能隐去其尚待满足的资格和机器准入条件。

## 6. 唯一条件增长场：E2 新 p6 reference

### 6.1 为什么选它，以及精确输入

E2 相对 E1 线性尺寸增加 20%，在相同 0.7 nm 下电尺寸更大，并且已有旧 p4 保存场可比较。它能检验新 case 参数化、较大电尺寸下的收敛和资源增长；它仍远小于最终目标，不能成为无限 E3/E4 小模型序列的起点。E1 Ny4→8 是同一小几何的 y 精度试验，本轮保留 DESIGN_ONLY，不作为主任务或原尺寸准备前置门。[S5]、[S16]

| 项目 | E2 V20 冻结要求 |
|---|---|
| 几何 | 3.888888889×1.944444444×10.888888889 nm；沿既有精确输入值 |
| 物理 | 0.7 nm、现有 Si/air、grazing 1°、azimuth 0°、s，原三维缺口 |
| axes / cells / degree | 10×4×22 / 880 / p6 |
| 模式 | manual m=12、n=3，700 ordered keys，实际 mapper 验证 |
| mesh plan | `task40extra.e2.electrical_size_exact_planes.v1` |
| mesh SHA | `6248267865cd1a747b2581c3e3cfdfb9d4e2379a84b1931246a074e1bcb8f2df` |
| 输出衍射采样 | 当前修复输入为 25×24；不得退回导致历史失败的 24×24 |
| q/twist | Ny=4、ell=2、K=2；预期 q ports [100,200,200,200]，以实际 mapper 独立核验 |
| 新路线 | p6 reference + row-tile + one-q；独立 V20 run ID/dat/profile |

预期 full/independent/interior/trace rows 为 595512/573120/396000/177120；每 q spatial/trace rows 为 143280/44280，augmented q rows 为 44380/44480/44480/44480。以上是预期拓扑，运行时必须读回。既有 E2 dat 仍选择旧 p4 reference，不能直接拿它启动新路线；应新增 V20 输入，保留旧 dat。[S19]

历史 E2 原 worker 在完成求解后因衍射采样不足而失败，完整原 A6 为 `9.793073227317083e-7`；随后 saved-field offline output recovery 成功，原 worker 失败分类继续保留。其物理 SHA 为 `48814d5fe34ab0e73de345c2d98661a96ef93ebb9690be738d040edac7cd84a7`，ordered-mode manifest SHA 为 `ca2e97c451d981d0182333381ca9179c2994b3b18916497e536083d2d825da29`。新旧 input/output 元数据不同，不能要求完整 input SHA 相同；相同物理、网格、mode、坐标与 gauge 需独立确认。[S16]

### 6.2 E2 沿现有 Ny4 合同，实测自己的数据

不要求再跑 B0 Ny8 全场，也不把 B0 证书复制给 E2。沿 E1 的 Ny4 机制，在 E2 实际输入上完成：

1. 真实 global/local dofmap、方向/排列、primal/dual、原点/Floquet/gauge 与全部内部/端口映射，mapping 门仍为 `1e-12`。
2. 每个 twist 实际完整 00/01/10/11 q 块与原非对角块 `1e-11` 门；700 有序模式恰好覆盖一次，所有 FE q 均存在。
3. 原四类 V15 startup：generic full、完整 interior-only、全部非零 port、physical incident；原分母、native FE 与恢复关系不变。
4. 每个 fresh factor probe `1e-10`；每次实际 q solve、native FE 与 non-cancelling budget `1e-8`；alpha `1e-9`、decomposition `1e-10`；现有完整 augmented correction 次数预算不放宽，probe 单独计账。
5. 原 target-action identity `1e-10`、完整原 A6 与释放后 A6 `1e-6`、能量闭合及两种吸收一致性的原绝对 `1e-5` 门、官方输出和独立输出 checker。内部 KSP 残差不替代原 A6。[S10]、[S21]、[S23]

用旧保存 E2 解作同离散对照：沿既有 E/H/scaled-curl 与显著复振幅 `1e-4`、R/T/A/A_volume 绝对 `1e-5`、逐模式功率绝对 `1e-6` 合同，事前冻结显著模式集合和归一化，全部模式差异仍保存。不能把 B0 的 y 细化 1% 门替换成同离散门，也不能因弱通道近零分母而事后改门。旧原 worker failure、新恢复证据、新完整场及新比较是不同记录。若旧字段缺失或某比较未过，准确说明其范围，不能覆盖已经得到的原方程或物理检验，也不能声称同离散一致性全部通过。

### 6.3 只有实际资源和剩余时间允许才跑

先使目标输入/阶段入口和轻量 preflight 成为可审阅交付，再决定 E2 heavy。沿现有动态本机 memory gate、task swap=0、OOM=0、单 heavy 与原窗口；不得把目标 2 TB 填入笔记本 guard 以放行。

E1 的 12.093 GB 是新 E2 准入的参考观察，不能用“只多 120 cells”保证可放下。使用新的实际类数、局部/端口预估、全部 q CSR、单槽 symbolic reserve、future workspace 与当前资源做分阶段准入。在构建或 symbolic 已给出资源停止证据时，无需等 OOM 才算有效结果。不得为了通过而缩几何、降 p、删 modes、改精度或取消恢复数据。

E2 只授权这一个增长配置。普通配置/输出/lifecycle bug 经有限定向修复、测试和主控冻结后，可在原窗口内继续同一 case；数值结果可复用的后处理修复优先从保存场恢复。没有新缺陷时不重做已通过阶段。数值预算不足就按真实到达阶段收口，并继续已安全可做的目标包/组件；不因 E2 未完成而把本轮退回小模型调试循环。

## 7. 两项轻量工程收尾并入主线

**完善计时和 owner 证据。** 首先读已有 events/build history，随后仅在下一次必要运行增加少数关键边界：activation 前、FE/local/port/q build、all-q symbolic、numeric/probe、startup/KSP、恢复/输出、required checker。父子项明确、unique backing 与 RSS 峰时间对齐，unknown 不填 0。支持2 TB判断的目标表应列“逻辑必要库存、同时上界、实测、未知”，不能把所有历史峰值相加。

**修补 probe 的异常清理。** 当前 `OneQRefactorV19Mumps._solve_probe` 中 b 创建后、`x=b.duplicate()` 在 try 之前；duplicate 抛错时 b 可能未销毁，finally 中 x.destroy 抛错也可能跳过 b.destroy。将 b/x 初始化为空，分配纳入受保护区，各对象独立清理，保留真实异常；若无法确认某 native owner 已销毁，不得假定释放后继续创建另一个槽。针对实际异常路径加一个小 fixture 即可，无需单独重跑 B0/E1 PDE。[S9]

这项清理是可定位的小修复，不否定已保存成功场。当前 factor 销毁后才移除 owner、销毁失败保留 owner 阻止新槽的主逻辑值得保留。CSR hash 使用连续 memoryview，没有证据表明每次扫描都会复制整个 CSR；若现有 events 显示重复身份扫描耗时显著，再做有证据、身份不削弱的优化，不能凭猜测大改。

## 8. 时间窗口、优先级与退出标准

### 8.1 V20 接续现有窗口，不重新给 24 h

本报告在尚未结束的 V19 immutable window 中明确授权上述新增范围；review 编号变为 V20 不改变时间起点。

| 字段 | 固定值 |
|---|---|
| campaign record | `local_w19_wsl/campaign_window_v19.json` |
| T0 | `2026-10-09T01:45:00.727771902Z` |
| deadline | `2026-10-10T01:45:00.727771902Z` |
| 新加坡/北京时间 deadline | 2026-10-10 09:45:00.727771902 |
| closeout reserve | 600 s |
| window SHA | `b1591b7cf03b79aaf0820d352e636bdb79a6800bb19489eba92375cb73cbe6b0` |

最新提交账 snapshot sequence 55985 的采样时间为 `2026-10-09T10:27:05.095607300Z`，累计保守扣费 31324.373504745337 s、剩余 numerical 54475.62649525466 s。这是 as-of 值，不能复制成接收本报告时余额。用户本次请求时间 `2026-10-09T11:34:58Z` 对应的 UTC 上界余额在扣 600 s 后已至约 50402.728 s；审阅和后续等待继续消耗固定窗口。[S5]

执行者接收时使用既有 campaign API 重新记录 UTC/monotonic/boottime/boot 与剩余额度。启动任何 heavy 前，要能在实际保守预算内完成或安全停止，并保留收口时间；旧费用、失败、unknown 不清零，不因 bug、修复、review 或 commit 刷新 deadline。若收到时窗口已结束，本报告不自动新开窗口，只完成必要收口与已有结果交接。

### 8.2 工作顺序与合格交付

按依赖推进，不逐阶段等待新 review：

1. 核对身份与现有余额；读取已保存成本证据，并接好新的 outer clock。
2. 注册 E2/原尺寸两个受限 case，完成原尺寸 preflight 和阶段防误启动检查；主控及时冻结可用实现。
3. 取得真实原尺寸 geometry inventory 和有界 local/port 组件，形成按实际类数与持有关系计算的目标对象账；同步交付可复制的目标分阶段命令。
4. 在本机资源及剩余时间允许时，执行唯一 E2 增长场或取得明确资源停止证据；与旧保存 E2 场作低成本对照。
5. 更新 V20 response、outcomes/test summary、run index、compact 和全仓库发展/模型总账；由主控审查提交推送。

这不是要求先写完全部文档才允许数值推进。基础身份/资源门通过后，以上独立工作可交错进行，但同时只允许一个 heavy。若 E2 无法安全完成，优先保护真实目标组件和可执行包交付，不能用额外小场替代它。

本轮建议采用分项验收，避免一个布尔 PASS 掩盖差异：

| 验收项 | 完成条件 |
|---|---|
| `TARGET_INPUT_AND_STAGE_ROUTE_READY` | 原尺寸输入/profile、实际解析路由、受控停止点与命令可审阅；轻量正反例通过 |
| `TARGET_GEOMETRY_ONLY_COMPLETE` | 真实 30464-cell 几何、材料、界面、周期面/排列/类别库存有原始证据 |
| `TARGET_LOCAL_PORT_COMPONENT_PASS/PARTIAL` | 新真实尺寸组件有明确覆盖、数值检查、owner/time 和旧证据复用边界 |
| `E2_FULL_PASS/RESOURCE_STOP/NOT_RUN` | 按实际发生记录；NOT_RUN 必须说明资源、时间或具体依赖，不能静默省略 |
| `TARGET_STAGE_READY_V20` | 上述输入/几何/组件与阶段包形成可交接成果；清楚列出未测 heavy/算子资格 |
| `TARGET_SOLVER_QUALIFIED` | 本轮仍为 false；不能由阶段包、单 q 或组件 PASS 自动置 true |

包准备完成后，下一次计算决策应直接针对原尺寸的 build/symbolic、单 q numeric 和全场可行性；或针对本轮明确识别的最大对象作一项结构修正。没有新证据时，不继续默认追加 E1Ny8、E3、Ny16 或相同 B0 回归。

### 8.3 什么情况下才真正可以计算最终大模型

第一道门是**可以开始原尺寸资源 pilot**：准确输入、实际阶段入口、对象账和动态准入已具备，执行机器及运行范围符合既有授权。笔记本不能做目标 q CSR/factor 的事实，只说明本机执行限制，不证明 2 TB 不够。本轮完成可审阅的准备工作，不调用工作站。

第二道门是**可以启动完整原尺寸候选场**：目标真实构建与 all-q symbolic 已关闭资源未知；必要 numeric 因子/工作区实测允许合理的驻留策略；实际目标映射、q/native/operator 与恢复资格和完整预算成立。首个目标 q 通过还不足以证明全部 q 和 48 h。

第三道门是**可以声称最终目标完成**：在最终精度合格的物理、网格和模式设置下，完整原方程残差、恢复、官方物理量与 checker 通过，真实总物理 RAM 含 reserve 不超过 2 TB、task swap=0，单场必要全路径不超过 172800 s。当前 Ny8/Nz14/32060 只是资源 pilot，必须另有原尺寸 h/p/模式截断及主要场量的精度证据；代数残差小不等于离散误差小。精度研究 campaign 与一场计算的时钟分开记，不能把该场必要准备移到表外以宣称 48 h。

若未来目标单 q 数值因子已超过可用内存，单槽轮换不能解决该 q 的容量；若 factor 构建次数乘实测成本使 48 h 没有余量，应依据目标 2 TB 实测评估驻留/重用；若大电尺寸迭代显著恶化，应承认当前参考逆的适用边界。由这些具体证据决定结构改进，不能继续引用 B0/E1 三步作为目标可行性证明。

## 9. 来源与复核入口

以下均绑定本次固定 base；历史记录按其明确 source/run 身份使用。raw artifacts 的路径与 SHA 是仓库记录提供的证据索引，本次未下载其二进制内容。

[S1]: https://github.com/Rookie1234567/MyFEniCS/blob/77ef699156f95fb24e0a75e215d61458bfdedcea/docs/task40extra_0p7nm_engineering/response_v19.md
[S2]: https://github.com/Rookie1234567/MyFEniCS/blob/77ef699156f95fb24e0a75e215d61458bfdedcea/docs/task40extra_0p7nm_engineering/outcomes/records/review_v19_component_closure.json
[S3]: https://github.com/Rookie1234567/MyFEniCS/blob/77ef699156f95fb24e0a75e215d61458bfdedcea/docs/task40extra_0p7nm_engineering/outcomes/records/review_v19_sparse_capacity.json
[S4]: https://github.com/Rookie1234567/MyFEniCS/blob/77ef699156f95fb24e0a75e215d61458bfdedcea/docs/task40extra_0p7nm_engineering/outcomes/records/review_v19_formal_results.json
[S5]: https://github.com/Rookie1234567/MyFEniCS/blob/77ef699156f95fb24e0a75e215d61458bfdedcea/docs/task40extra_0p7nm_engineering/outcomes/records/review_v19_cost_and_readiness.json
[S6]: https://github.com/Rookie1234567/MyFEniCS/blob/77ef699156f95fb24e0a75e215d61458bfdedcea/docs/task40extra_0p7nm_engineering/outcomes/records/run_index.json
[S7]: https://github.com/Rookie1234567/MyFEniCS/blob/77ef699156f95fb24e0a75e215d61458bfdedcea/docs/task40extra_0p7nm_engineering/outcomes/test_summary.md
[S8]: https://github.com/Rookie1234567/MyFEniCS/compare/19b7993380728f5c940194b8c4fff4c640d0b4ff...77ef699156f95fb24e0a75e215d61458bfdedcea
[S9]: https://github.com/Rookie1234567/MyFEniCS/blob/77ef699156f95fb24e0a75e215d61458bfdedcea/src/solvers/task40_v10_p6_mumps.py
[S10]: https://github.com/Rookie1234567/MyFEniCS/blob/77ef699156f95fb24e0a75e215d61458bfdedcea/src/solvers/task40_v10_p6_yorbit.py
[S11]: https://github.com/Rookie1234567/MyFEniCS/blob/77ef699156f95fb24e0a75e215d61458bfdedcea/src/geometry/task40_nonseparable_plan.py
[S12]: https://github.com/Rookie1234567/MyFEniCS/blob/77ef699156f95fb24e0a75e215d61458bfdedcea/src/runners/task40_v10_output_checker.py
[S13]: https://github.com/Rookie1234567/MyFEniCS/blob/77ef699156f95fb24e0a75e215d61458bfdedcea/src/solvers/task40_v10_p6_periodic_profile.py
[S14]: https://github.com/Rookie1234567/MyFEniCS/blob/77ef699156f95fb24e0a75e215d61458bfdedcea/input/task40extra_0p7nm_engineering/b0_p6_reference_v19_ny8.dat
[S15]: https://github.com/Rookie1234567/MyFEniCS/blob/77ef699156f95fb24e0a75e215d61458bfdedcea/input/task40extra_0p7nm_engineering/nonseparable_e1_p6_reference_v19.dat
[S16]: https://github.com/Rookie1234567/MyFEniCS/blob/77ef699156f95fb24e0a75e215d61458bfdedcea/docs/task40extra_0p7nm_engineering/outcomes/records/electrical_size_v2.json
[S17]: https://github.com/Rookie1234567/MyFEniCS/blob/77ef699156f95fb24e0a75e215d61458bfdedcea/docs/task40extra_0p7nm_engineering/outcomes/records/review_v16_target_components.json
[S18]: https://github.com/Rookie1234567/MyFEniCS/blob/77ef699156f95fb24e0a75e215d61458bfdedcea/docs/task40extra_0p7nm_engineering/outcomes/records/review_v17_component_closure.json
[S19]: https://github.com/Rookie1234567/MyFEniCS/blob/77ef699156f95fb24e0a75e215d61458bfdedcea/input/task40extra_0p7nm_engineering/nonseparable_e2_p6_q4_manual_m2_growth.dat
[S20]: https://github.com/Rookie1234567/MyFEniCS/blob/77ef699156f95fb24e0a75e215d61458bfdedcea/docs/task40extra_0p7nm_engineering/AGENTS.md
[S21]: https://github.com/Rookie1234567/MyFEniCS/blob/77ef699156f95fb24e0a75e215d61458bfdedcea/src/solvers/augmented_reference_correction.py
[S22]: https://github.com/Rookie1234567/MyFEniCS/blob/77ef699156f95fb24e0a75e215d61458bfdedcea/src/solvers/task40_v18_ny8_operator_reuse.py
[S23]: https://github.com/Rookie1234567/MyFEniCS/blob/77ef699156f95fb24e0a75e215d61458bfdedcea/docs/task40extra_0p7nm_engineering/review_report_v19.md

- [V19 总回应][S1]、[组件合同][S2]、[资源与结构][S3]、[完整结果][S4]、[成本与目标边界][S5]、[运行索引][S6]、[测试摘要][S7]、[本轮提交差异][S8]。
- [MUMPS 生命周期][S9]、[q 逆与组装][S10]、[几何身份][S11]、[输出 checker][S12]、[profile registry][S13]、[增广修正合同][S21]、[Ny8 资格复用][S22]。
- [B0 V19 输入][S14]、[E1 V19 输入][S15]、[E1/E2 历史记录][S16]、[目标 recipe][S17]、[已关闭的 S2/D/phase 组件][S18]、[旧 E2 输入][S19]。
- [本机工作边界][S20]、[上一轮 Review V19][S23]。
