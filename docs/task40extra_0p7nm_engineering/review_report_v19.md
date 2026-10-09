# Task40extra Review V19：先以单 q 因子驻留推动 E1 完整求解

## 0. 审阅结论与下一轮唯一主候选

**接受 V18 的 Ny=8 完整参考算子资格和 160-cell 非可分完整离散场，裁决为 `PASS_WITH_QUALIFICATIONS`。E1 已有新的四 q symbolic 实测，但仍未进入 numeric factorization 和 KSP；该次使用旧 V15 legacy 装配，逐对象内存账为空。下一轮选择一个直接针对峰值的实现：`ONE_Q_REFACTOR_V19`，一次至多保留一个 q 的 PETSc 输入矩阵和数值因子，保留全部不可变 q CSR，需要时重新分解。结合已有优化装配入口，优先争取 E1 完整场。**

通俗地说，当前参考预条件器把问题变换成多个 q 子问题，并把这些子问题的直接分解结果同时留在内存中。新候选按需只保留一个分解结果，用额外分解时间换取更低的同时内存。各 q 的方程、全部右端项、原三维目标算子和验收精度保持原合同。它是一个可以在已有小模型上直接对照、在 E1 上验证内存收益的具体工程试验；不是已经得到的资源成绩。

| 问题 | 本次裁决 | 下一轮动作 |
|---|---|---|
| Ny=8 完整算子及独立 Schur 资格 | 接受已测范围内 PASS | 数学输入和全部 q CSR 身份成立时复用；新因子生命周期单独资格化 |
| B0-Y8 的完整非可分 p6 求解 | 接受原 A6 与 official 输出 | 作为新生命周期的同离散对照，保留原场 |
| Ny=4 / Ny=8 的场变化 | 接受已测场比较；显著模式门尚未评价 | 读保存场/模式做低成本补齐，不因此挡住 E1 |
| E1 的当前 p6 reference 路线 | 仅 symbolic 完成，资源受控停止 | 改正入口并实现单 q 生命周期，安全则连续完成整场 |
| 全冷启动成本、目标网格和端口截断 | 仍有关键缺口 | 新必要运行计时；目标层面做有界计数与误差计划 |
| 原尺寸 0.7 nm、2 TB、48 h | `NOT_QUALIFIED` | 不由三步迭代、小模型或 CSR 上界推导通过 |

**本轮新增成果的优先顺序是：可运行的新生命周期 → 小模型数学等价与真实资源/时间对照 → E1 完整场或缩小后的精确资源缺口 → 目标尺度边界。** 单独增加 PASS 字段、再跑一次相同 legacy symbolic 停点，不能作为主要增量。

## 1. 审阅身份、证据与工作边界

| 项目 | 固定身份 |
|---|---|
| 仓库 / 执行分支 | `Rookie1234567/MyFEniCS` / `task40extra_0p7nm_engineering` |
| 审阅日期 | 2026-10-09 UTC |
| 审阅 base | `64f1a0432db3d0e59335c5ba1f40b36cd0ae68f9` |
| base 提交时间 / 说明 | `2026-10-09T00:26:02Z` / `docs(task40): close Review V18 Ny8 solve and E1 capacity evidence` |
| 上轮 review 提交 | `33614413731d739d2c0f57106df180c359f4343f` |
| Ny=8 成功数值运行源码 | `3b9457e57ceb15f21306a35baac07f42036840b1` |
| E1 本次实际源码 | `168a727add276633e20000b718a4aa7eaa5f1e61` |
| V18 结项前实现冻结 | `ff8251dbcede1f736a0827fab8ffa8fb58daa9bd` |
| 后续执行目录 | `/home/shenjh/Projects/MyFEniCSx_task40extra_0p7nm_engineering` |

本次审阅读取 V18 response、四份 compact、run index、summary/test summary、相关输入，以及 Ny=8 qualification/reuse、worker、q 组装、MUMPS、局部凝聚和目标结构计数源码。上轮 review 至本次 base 有 12 个提交、43 个变更文件。对四份 compact 与 response、summary、test summary、README 共八份远程 UTF-8 内容，重算 SHA-256 和 Git blob 身份，均与索引相符。[S1]–[S7]

这证明已提交文本的内容身份。大场、稀疏矩阵、因子和原始 events 位于执行机 ignored artifact/results，本次没有远程读取这些数值数组并重算 FE/PDE。下面把远程记录中的实测、源码推导、条件场景和未知项分开；引用原记录的 checker PASS 不等于本次重新执行了 checker。

本报告只新增审阅文档，不修改数值代码，不启动执行机或计算窗口。后续仍由既有 Task40 执行者实现/测试/运行，既有主控审查、冻结源码并集中提交推送。执行者不 commit/push。保留 Task40 本机单一链路，不新建 Codex 聊天、项目、checkout/worktree，不启用 Codex collaboration subagents 或定时任务，不 SSH、不切到工作站、dot、Task042 或其他任务，不写 master。

## 2. V18 已带来的实质进展

### 2.1 Ny=8 已跨过完整参考算子资格门

V18 的独立参考先装配完整 native FE 体积算子和原始 C/D/H 端口块，再做完整 q 变换；独立全局内部 Schur 与候选局部凝聚结果比较。资格覆盖 64 个 q 块、56 个非对角块和 8 个独立 Schur 比较，避免仅以随机向量作用或候选自己的中间量为 oracle。[S2]、[S16]

| 指标 | V18 记录值 | 判断 |
|---|---|---|
| 完整非对角块最大归一化范数 | `8.295647911548953e-16` | 通过原 `1e-11` |
| 独立 Schur 最大相对差 | `1.2566990957931308e-14` | 通过原 `1e-11` |
| mapping 最大误差 | `2.929458332060444e-15` | 通过原 `1e-12` |
| q 模式数 | `[76,76,76,76,0,76,76,76]` | 覆盖完整有序 inventory |
| q=4 | 0 port，但 13248 个 native FE rows、4248 个约化 augmented rows | 正确保留非零 FE 子问题 |
| 非平凡全局相位、复材料、非 Hermitian witness | PASS | 已覆盖本次资格场景 |

后续成功运行通过全部八个 fresh q 矩阵 hash 复用上述资格，并由独立 checker 重读保存的资格量。这里应称“矩阵身份匹配的资格复用”，不能称成功场重新执行了完整独立算子计算。六次先前 Ny=8 worker 失败保留；包括预算未覆盖两个 twist-sector lift 项等可定位问题，经修复后确实推进到了完整场，而非停在首个实现异常。[S2]

### 2.2 B0-Y8 已得到完整非可分三维离散场

本场是 B0 缩小解析几何的 y 二分：`4×8×5=160` cells，p6，110406 full rows，532 ordered modes；仍是 0.7 nm、grazing=1°、azimuth=5°、s 偏振。实际几何约 `2.59259×1.29630×7.25926 nm`，不是最终 `50×25×140 nm` 模型。Gx560 使用另一组入射/模式/网格身份，不能直接把两者 R 的差归因于 Ny 变化。[S1]、[S4]、[S15]

| 量 | V18 Ny=8 正式结果 |
|---|---|
| outer iterations / worker exit / official | 3 / 0 / true |
| 释放后完整原 A6 | `1.2189184363208502e-8` |
| 独立 native A6 witness | `1.218918601504642e-8` |
| R | `0.9842736080921147` |
| T | `0.014240518110484091` |
| A_balance / A_volume | `0.001485873797401182` / `0.0014858738441830876` |
| R00_s / R00_p / R00_total | `0.9842411413335236` / `8.453238781901373e-6` / `0.9842495945723054` |
| 全部 q 数值因子同时 live | 8 |
| MUMPS allocated upper 合计 / used upper 合计 | 935000000 B / 840000000 B |
| process-tree RSS peak / dedicated cgroup peak | 4869050368 B / 5899956224 B |
| task swap / OOM | 0 / 0 |
| run_case workflow / 纯 KSP | 2474.995817267103 s / 22.299832042 s |

两个吸收量绝对差约 `4.6782e-11`。三次 PC 的初始 q 右端求解数均为 8，未触发额外 augmented correction。PC 的既有 RHS solve 前后累计计数为 `32→40→48→56`；32 是进入第一个 PC 前的累计值，不能倒推出未独立保存的 startup 子类调用数。现有计数器不计 constructor 内 factor probe，不能把这一 RHS 累计数称为包含探针的 backend MatSolve 总次数。三个 PC 父耗时约 4.253、3.750、3.691 s，内部 native 检查耗时是其子项，不能再次加到父项上。[S4]

记录已支持本场求解通过，但 compact 尚未给每次 PC 的 q/native FE/alpha/noncancelling budget 数值最大值。V19 从现有 events 读回这些量与 gate，不重做历史 FE，也不把原先缺失字段补写进旧失败收据。

### 2.3 y 方向场比较有力，但尚未完成全部模式精度判断

Ny=4 原 worker 失败与后续保存场恢复 PASS 是两个不同事实，继续并列保留。恢复后的 Ny=4 与 Ny=8 在共同 160 子单元上比较，E/H/scaled-curl 的最大相对 L2 变化为 `4.9114215261280976e-8`；覆盖 9 个接口、288 个候选 facet tiles，其中 106 个为材料界面。它支持已测试的小型 B0 场对 y 二分的稳定性，不证明目标尺度 x/y/z 与模式截断已经收敛。[S4]

全部 532 个模式的入射数组相同、归一化范数为 1。某个近零 bottom (1,2), p 通道的逐通道相对差为 4.7661，但两场幅度约 `1.39e-16` 和 `6.27e-16`，绝对差约 `6.61e-16`。这个近零分母比值不能解释成显著物理场相差数倍。

原 `NOT_EVALUATED_NO_FROZEN_B0_SIGNIFICANT_MODE_SET` 继续保留。V19 可在任何新的场比较前，公开冻结一个**新 V19 工程判断规则**并应用于保存的全部 532 通道，例如：

```math
|a_{8,j}-a_{4,j}|
\le 10^{-8}\|a_{\mathrm{inc}}\|_2
+0.01\max(|a_{4,j}|,|a_{8,j}|).
```

本报告授权此式作为新增 all-mode 混合绝对/相对观察门：`1e-8` 是以单位入射幅度计的绝对误差预算，`1%` 沿用方向细化观察目标。它没有经过独立误差理论证明，且是在看过 V18 摘要后提出；明确标为 V19 新评价，不追溯改写成 V18 事先冻结的 PASS。逐模式绝对差、相对差、功率差仍全部保留，原功率/场门不放宽。若有限数据使这一补充无法完成，精确列缺失项；它不成为 E1 因子内存研究的前置阻塞。

### 2.4 “三步”尚未说明 48 h 是否可达

本场纯 KSP 只占 run_case workflow 约 **0.9010%**。已测 run_case 为约 41.25 min；watchdog 启动到必需 checker 结束的 monotonic 差为 3342.078481 s，UTC 差为 3646.233646 s。两者口径与 clock 身份未完全闭合，不能互加或相减后声称得到某个准备阶段耗时；watchdog 之前 ABI/必要准备也未完整覆盖。[S5]

目前真正缺少的是：一个合格场从必要准备开始，经 JIT/装配/分解/求解/恢复/输出到必需 checker 结束的全冷启动父时钟及主要阶段。V19 对新的必要场补齐；历史 unknown 保留，不为“补一张漂亮计时表”重跑旧 PDE。

## 3. E1 的实际停点与源码原因

### 3.1 资源缺口已经量化，但不是 numeric 结果

E1 是 `10×4×19=760` cells、p6、588 ordered modes。四 q rows 为 `[38424,38508,38508,38508]`，NNZ 为 `[21010722,21303127,21314038,21307427]`。此次四 q symbolic 全部完成，然后因资源门停止；没有 numeric factorization、KSP、新场或 official 输出。[S3]

| E1 同一 gate 的量 | B，除另注 |
|---|---:|
| current tree RSS | 12268249088 |
| 四 q symbolic INFOG16/17 | 1613、1666、1626、1621 MB |
| 按原规则得到的未来因子储备 | 6530000000 |
| pending transform inverse | 273222720 |
| selected co-resident phase | 190897920 |
| 未来储备小计 | 6994120640 |
| 额外 headroom | 134217728（128 MiB） |
| projected tree RSS | 19396587456 |
| 当时 effective dynamic cap | 13544640512 |
| projected excess | 5851946944 |

投影核对为：

```math
12268249088+6530000000+273222720+190897920+134217728
=19396587456.
```

其中每 q symbolic 的 MB 估计按原 gate 加 1 MB，四 q 合计 `6530` 十进制 MB；它不是实测 allocated/used。128 MiB 来自实际 gate 公式，不应在人工重算时漏掉。[S3]、[S10]

全过程 process-tree peak 为 12518109184 B，dedicated cgroup peak 为 12710162432 B；task swap=0、OOM=0。run_case workflow 为 5793.324598 s，约 96.56 min，时间门当时通过。不能把 19.397 GB 投影写成 19.397 GB 实测峰值，也不能把该笔记本动态 cap 带到 2 TB 目标机器。

### 3.2 该次使用旧入口，已有优化没有全部进入 E1

本次 E1 run directory 和 input SHA 明确绑定 `nonseparable_e1_p6_reference_v15.dat`，配置为 `LEGACY_GLOBAL_CSR_SUM`，row-tile=false。仓库已经有同物理的 `nonseparable_e1_p6_reference_v17.dat`，配置为 `ROW_TILE_BOUNDED_CSR_V17`。两份输入的差异是 run identity、preconditioner/profile 和装配策略，物理输入保持同一 E1。[S8]、[S9]

worker 源码中，优化路线标志还决定 target 的 `share_identity_cache` 和 richer owner hooks。使用 V15 入口时两者没有按 V17 路线开启；这解释了“当前源码已有优化，但 E1 compact 的 inventory 仍是 entries/components 空、total=0”的一部分原因。空账只表示未记录，不能解释为没有 live 对象。这不是已经证明的 silent fallback，应如实称“正式运行选择了旧输入”。[S11]、[S13]

下一轮启动 FE 前先做一次轻量配置解析，确认实际策略、profile、identity sharing、owner hook 和新 factor lifecycle 全部贯通；打印解析后的实际值并绑定输入。不要等近百分钟的装配结束，才发现仍在 legacy 分支。新入口继承 E1 的物理/网格/mode 身份，保留原 V15/V17 输入及历史证据。

### 3.3 row-tile 有价值，但不能单凭名称填上 5.85 GB

E1 两个 sector 的 q 装配父耗时合计约 858.383 s，其中 CSR accumulation 子项合计约 633.482 s。它说明组装确有优化空间；余下 workflow 时间缺乏完整父阶段分类，不能全部归为 JIT、局部缓存或某个单一瓶颈。[S3]

真正要跨过当前内存门，需要同时处理组装后的对象驻留。现有 `AllQExactMumps` 把全部 q CSR、PETSc 输入矩阵和 factor 对象保留；创建 PETSc 输入时还显式复制 values/indices/indptr。规范 CSR 的 source/canonical 可能是同一对象或同一 backing，仅删除字典别名不会释放一份 CSR。PETSc 内部实际持有哪块存储和销毁后的进程/cgroup 变化仍须实测。[S10]

局部凝聚核心已经提供 retained numeric cache 和 temporary cache 审计。`share_identity_cache=False` 时，每个定向类型可以保留一个 `450×450` 的 float64 identity；三组 RHS/recovery 引用是 alias，不应算成三份。共享模式按形状保留一份只读 identity。原始/定向临时张量在 builder 返回后的生命周期已有说明，不能假设它们全部一直驻留到 factor 阶段，再凭空登记“释放收益”。恢复和原 A6 必需的 LU/映射/Schur 数据也不能为凑预算删除。[S13]

V19 复用现有审计与 unique backing helper，在真实阶段边界增加缺失信息。每个主要 owner 写明独立 backing、字节、持有者、最后使用点、alias、销毁/释放前后采样。无需另造逐 scalar 平行账本。


## 4. V19 主候选：ONE_Q_REFACTOR_V19

### 4.1 数学作用不变，改变的是分解结果的存储时间

沿现有生产 fold、凝聚和恢复定义：

```math
b_q=F_q(r), \qquad y_q=A_q^{-1}b_q,
\qquad z=\mathcal R(r,y_0,\ldots,y_{N_y-1}).
```

`F_q` 包含原 RHS 的正确 FE/端口变换和内部凝聚；`R` 包含原非零内部 RHS、trace、端口的完整恢复。不能把它简化为忽略内部恢复项的裸 q 解之和。V19 保留全部 `A_q`、全部 q、complex128、原 MUMPS 数值选项和真正残差门，仅把“所有因子常驻”改为“需要哪个 q 就建立哪个 q 的因子”。FGMRES 接收的仍是原合同下的参考修正，浮点差异由既有同离散与真残差门检验。

实现作为显式 research opt-in，不提升为普通生产默认。参数名/枚举统一使用 `ONE_Q_REFACTOR_V19`；代码进入合适的 `src/solvers` 模块，现有 runner 只负责接线、资源和证据。第一版只实现一槽，不同时引入多容量缓存、磁盘因子、BLR/OOC、排序/主元扫描或另一种近似预条件器。

### 4.2 有界生命周期必须覆盖构造、作用、异常和关闭

| 阶段 | 必须保持的行为 | 需要留下的证据 |
|---|---|---|
| 输入验证 | 全部 q source CSR 形状、NNZ、indices 和内容身份成立；规范化后不再改写 | input/physical/source hash、per-q CSR hash、IntType 检查 |
| symbolic 预审 | 每次只创建一个 q 的 PETSc 输入与 symbolic 对象；所有 q 均覆盖；只保留标量/身份/统计报告，销毁后再处理下一 q | 全 q 估计、每次 live 数、阶段峰值和销毁后采样 |
| factor cache miss | 先销毁旧 numerical factor 与旧 PETSc 输入，再创建当前 q；从已保留 CSR 重建，必要时重做 symbolic | eviction 顺序、current RSS/cgroup、转换临时数组与数值分解储备 |
| numeric + probe | 保持既有数值配置；每次新 factor 的必要探针达到原门 | INFOG 原值及解码、allocated/used、probe 残差/次数/耗时 |
| 实际 RHS solve | 保留非零内部和端口 RHS；求真实 q/native/budget/closure；原允许的整次 augmented correction 仍有界 | 按实际调用分类的计数、逐次真残差及父子计时 |
| 异常与 close | 清理当前 factor/matrix；不可把未完成 q 当作零或 inactive；保留原 attempt | 首个失败阶段、清理结果、task swap/OOM、真实终态 |

**任何时刻至多一个 live q numerical factor 和一个 live q PETSc 输入矩阵。** 已保留的全部 q source CSR、FE/port 恢复数据和当前 RHS/PC/native 检查向量另行计入同时内存；这一合同不声称整条路径只保留一个 q 的所有数据。

audit、symbolic_states 或闭包不能继续持有已淘汰对象；销毁失败不能先把 live 计数清零再建新对象。驱逐后只从保留的不可变 q CSR 重建 PETSc/factor，不重做 FE、Schur 或 q CSR 装配。

每次 cache miss 都应在**当时**的 fold、PC/native、correction 工作数组已经驻留的背景下做准入。只在 constructor 做一次低背景 RSS 检查不够。销毁后 Python 引用消失、PETSc destroy 返回和 OS/cgroup 实际下降是不同证据；无法证明释放的占用继续计入。若 one-slot 对象都容纳不了，受控停止并报告最少还差多少、哪些 owner 不能释放，不能绕过 gate。

### 4.3 上层契约和调用计数要同时接通

当前实现不只在 MUMPS 类中保留全部 q。上层构造检查会要求 factor 字典包含全部 Ny，增广纠正审计也使用“全部 q factor 已复用”等旧语义。仅替换 MUMPS 对象生命周期会被旧检查挡住，或生成错误 PASS。[S10]–[S12]

V19 增加显式能力/策略契约，区分“全部 q 数学输入与可求解资格已覆盖”和“全部 q 数值因子同时 live”。旧 all-resident 路线继续保留原含义；新路线按 all-q coverage、max-live≤1、逐次重建和真残差资格判断。不得把 `all_q_factors_reused=true` 硬填到新策略，也不得直接删除相关检查。

建议用不重叠类别记录：

- `pc_initial_rhs_mat_solve_count`：每次 PC 初始全 q 右端求解，正常应为 Ny；
- `pc_augmentation_rhs_mat_solve_count`：原允许的一次整次 augmented correction 所需求解，上限 Ny；
- `startup_rhs_mat_solve_count`：启动阶段真实右端作用；
- `factor_probe_mat_solve_count`：每次新分解后的构建验证；
- `other_validation_rhs_mat_solve_count`：若确有其他参考作用，逐类说明原因；
- `numeric_factor_build_count`、`symbolic_build_count`、`cache_miss_count`、`eviction_count`，及最大 live factor/matrix 数。

所有实际 MatSolve 总数必须等于以上互斥 RHS/probe 类别之和，并保存前后累计值。新策略的构建探针可以使总 backend MatSolve 超过旧每 PC 的 Ny，但**没有扩张用于修正实际 PC RHS 的内层工作上限**；probe 与新分解成本必须显式进入 wall/CPU 和次数。不能把“maximum_extra_mat_solves=Ny”既用作 augmented RHS 上限又假装涵盖所有新 probe。

当前完整逆按固定 q 顺序访问；在一次作用结束后，下一次通常又从首 q 开始，一槽几乎没有跨完整作用的命中。因此按每次完整逆约 Ny 次 numeric build 规划，包含 startup、PC、必要 correction 和验证。不要把旧 Ny=8 的 22.3 s KSP 当作新策略时间上界。

### 4.4 Ny=8 旧 operator 资格的复用要从特定失败 attempt 中解耦

现有 V18 reuse helper 绑定一次 `WORKER_FAILED`、exit=4 的历史 attempt、特定 profile 和完全相同 input SHA，并要求旧 all-eight-live 证据。它成功解决了 V18 的特定历史桥接，不能原样用来读取一个成功的 V18 run 再评价新生命周期。[S17]

允许最小泛化为“已审阅完整 operator 资格的证书复用”：

1. 保存旧 receipt、原始覆盖量、checker、artifact hashes 与出处；允许来源是有合格 operator 证据的成功或失败 run，run 终态与 operator 资格各自表达。
2. 新 run 重新核对全部 q CSR 的 shape/NNZ/内容 hash；物理、axes、MPC、mode inventory、carrier 和完整算子语义必须可追踪地一致。
3. 新 input SHA/source SHA 仍记录完整值。若只变 run ID、装配策略或 factor 生命周期，显式列字段差异与数学身份对应；不把它们静默从 provenance 删除。
4. 当前依赖源码也需绑定，逐项解释改变是否触及算子。factor 调度不自动使原算子 oracle 失效；若候选 q 矩阵或数学输入实质改变，按受影响范围重新资格化。
5. 保存新 fresh-factor/完整 RHS/目标场检查，不能用旧 operator 证书代替新 factor 生命周期正确性。

上述复用只覆盖相同 B0-Y8 算子，不自然推广到 E1、目标几何或变化后的数学矩阵。优先复用已存完整证据，不机械重做昂贵 native full operator。旧 helper 的失败证据与历史判定保持不变；新证书仍由实际数值和 hash 支持，不能退化成读取任意 `status=PASS` 就放行。

## 5. E1 的条件内存筛算：为什么值得试，为什么还不能宣布成功

四 q CSR 的 complex128 data 加 int32 indices/indptr 逻辑 payload 合计：

```math
B_{\mathrm{CSR}}
=20\sum_q\mathrm{nnz}_q+4\sum_q(n_q+1)
=1699322088\ {\rm B}.
```

最大单 q payload 为 426434796 B。原未来因子储备为 6530000000 B；按同一 symbolic 加 1 MB 规则，最大单 q 为 1667000000 B。以下仅做**条件筛选场景**，用于决定值得实施哪一项，不是新 RSS 预测或准入凭据。[S3]、[S10]

| 条件变化 | 逻辑差额 / 场景结果 |
|---|---:|
| 四 q future factor reserve 改成最大单 q | 减少 4863000000 B |
| 假设原 PETSc 输入确有独立 CSR 等量 backing，释放其余三个 | 至多按此模型减少 1272887292 B |
| 将两项从旧投影相减 | 13260700164 B |
| 相对当时 cap 的剩余 | 283940348 B |
| 若 target 恰有 231 个对应类型，可把独立 float64 identity 共享为一份 | 另有 372600000 B 逻辑 payload 机会 |

最后一项计算是 `(231−1)×450×450×8`；引用 231 类只是当前 E1 类型场景。只有实际 owner、dtype、shape、shared backing 和原未共享状态都确认，才可登记真实收益。不能把三组 alias 当三份 identity，不能把上述差额全部相加后标成 measured。

由此有两个判断：

- **方向有足够量级，值得一轮直接实现。** 只减 factor reserve 还不足以抹平原 5.852 GB 缺口；同时约束 PETSc 输入副本与局部共享才可能进入可运行区间。
- **原 cap 下约 284 MB 的场景余量很薄。** PETSc 转换临时量、symbolic/numeric 工作区、allocator 未返还、FGMRES 和恢复/checker 重叠、系统可用内存变化都可能吃掉它。原 projection 与新生命周期的阶段也不同，最终必须用当前阶段上界及实测决定。

第一轮不把 all-q CSR 改成磁盘流式，也不实现跨 target/reference 的新 LU bank。若 one-slot 与已有共享仍不足，则按最大真实 owner 的字节和最后使用点选择下一项最小变更，不盲目继续缩门槛。

## 6. 下一轮连续执行：从实现直接走到 E1

### 6.1 工作顺序和实际交付

| 阶段 | 工作 | 可以进入下一步的证据 |
|---|---|---|
| P0：前置核对 | 在既有目录核对 branch/source/worktree、已结束旧窗口、ABI、E1 物理/mode 身份；解析优化入口；读取已有 PC/模式补充数据 | 真实执行参数已贯通；不花重 FE 成本验证配置字符串 |
| P1：一个主实现 | 实现 one-slot backend、上层能力契约、bounded symbolic、每次 miss 准入、计数和清理；复用 owner hooks；处理资格证书最小泛化 | 最小相关生命周期/异常/身份测试与必要真实 q 作用检查通过 |
| P2：B0-Y8 对照 | 固定与 V18 相同物理、网格和 532 modes；新策略完整 startup、KSP、恢复和 checker；对保存的 V18 场做同离散比较 | 全 q 作用与原 A6/物理门通过；max-live≤1；真实成本与同离散差量齐全 |
| P3：E1 整场 | 使用同物理 E1 的优化装配/共享和新生命周期；覆盖四 q symbolic，逐次安全准入后直接 numeric、startup、KSP、恢复、输出、checker | 新完整场，或精确到当前阶段/owner/所需 bytes 的受控停止 |
| P4：目标推导 | 有界 Ny=8 原生 support 校准/计数、目标 owner/factor/time 场景和下一精度对照设计 | 哪个未知量被缩小、哪个仍控制 2 TB/48 h 明确 |
| P5：集中收口 | 四份 V19 compact、response、summary/test summary、run index、项目账本 | 正负结果、实际 SHA/成本/窗口终态齐全；主控集中提交推送 |

P0 的模式/历史计时整理可以与实现准备先后交错，不作为 P1/P3 的形式前置门。**正常正式科学配置收敛为新生命周期 B0-Y8 与条件安全的 E1 两个。** 必要 bug 修复后只定向重放受影响项；不要机械插入 Gx560、Gx784、Ny=16 或一批线程/参数扫描。

阶段应尽早形成真实结果。建议前段完成首次可用组件和 B0-Y8，中段给 E1 一个有效尝试，把余量留给定向修复与收口；这些是工作顺序，不是给正常 factor/PDE 加任意短 timeout。任一重型运行启动前检查剩余窗口是否覆盖它的必要完整流程与收口。

### 6.2 对新生命周期只验证新增风险

最小验证覆盖：

- 至少两次跨 q 切换、再访问被驱逐 q，重建前后 CSR 不变、factor/matrix 上界成立；
- symbolic/numeric/probe/RHS 失败和 close 的清理，缺失 q 不被当成零；
- 原真实 q 矩阵上的非零 FE/port RHS，与旧 all-resident 结果及真残差比较；
- 完整 fold/solve/recovery，含 q=4 的 zero-port/nonzero-FE、原 twist-sector K 归一化和非零内部 RHS；
- 原允许的整次 augmented correction 路径、计数与 budget；没有触发时如实记录，不编造新正式负例；
- B0-Y8 完整场的原 A6、恢复、所有通道、功率与同离散对照。

复用未变的原 operator、保存恢复和 ABI 证据，仅按实际变更运行必要 tests。阶段收口遵守已有相关 serial/MPI、文档与最终测试门，不因字段或文档小改动重复整套 heavy qualification。官方结果和新策略推广资格分开：参考证据足够才能称等价，新完整场不等于目标尺度通过。

### 6.3 E1 成功与受控停止都必须比 V18 多回答问题

首选成功定义是：E1 完成新策略整场，原 A6≤`1e-6`，全部原 native/port/物理门通过，任务 swap=0，真实峰值在当前 resource policy 内，记录全过程 wall、所有 numeric build/probe/RHS 次数和原场输出。

如果 still blocked：

1. 给出最后完成阶段及 source/input/strategy，证明实际已走优化入口。
2. 给当前 RSS/cgroup、独立 owner payload、峰值发生时 live q/PETSc/factor 数、未来阶段上界、dynamic cap 与最小缺口。
3. 给 numeric 是否真正启动、哪个 q 能/不能容纳、实际 allocated/used 或只 symbolic，保持未知区别。
4. 给相对 V18 的可比改善：少了哪些真实对象/储备，哪些步骤完成；物理/网格/模式变化为零。
5. 同一窗口有明确安全的最小生命周期修复时完成并继续；若没有，转 P4 和收口，保留未完成整场，不原样重复旧失败。

不能以“新 schema 完成”“又过一次 symbolic”或“只因一个名字错误就等待下轮 review”替代以上结果。


## 7. 对 0.7 nm、2 TB、48 h 目标的推进意义与剩余问题

### 7.1 两个目标拓扑已可计数，数值因子和最终精度仍未知

最终合同是原尺寸 `50×25×140 nm`、真实三维非可分几何与材料、complex128 Nédélec H(curl)、x/y Floquet 和 z Fourier-DtN。约 2 TB 指 `2000000000000 B` 总物理 RAM，需要另留系统/监督/共存开销；任务 swap=0。48 h 是单个合格场必要准备到必需检查结束的 `172800 s`，不与开发窗口混用。[S15]

| 当前原尺寸拓扑候选 | Ny=4 | Ny=8 |
|---|---:|---:|
| cell axes / cells | 272×4×14 / 15232 | 272×8×14 / 30464 |
| ordered modes | 32060 | 32060 |
| 单 cell support 上界 | 348，匹配原生校准 | 432，当前 fallback |
| boundary support 上界 | 78336 | 117504 |
| 单 q augmented rows 范围 | 781500–781624 | 777424–777644 |
| 全部不同 q CSR payload 上界 | 142503121344 B | 266988562768 B |
| 当前单 q CSR payload 最大上界 | 35767382500 B | 33706522100 B |
| 结构级 int32 判断 | PASS | PASS |
| 目标实际 numeric NNZ / factor / 整场 | 未测 | 未测 |

这些来自纯结构计数，不是目标数值装配峰值。Ny=8 的 432 fallback 是因为现有 calibration 的 Ny/target permutation 覆盖不匹配；266.989 GB 同时受 q 数量和较松支撑上界影响，不能把相对 Ny=4 的增量全部归为实际新增非零存储。[S3]、[S14]

在固定 Nx/Nz 下，当前参考分解的每 q FE trace 行数没有随 Ny 翻倍而大幅下降。因而 Ny 加密会增加 q 个数，而每个 q 仍然很大。**one-slot 的目标价值是避免把全部大 q 因子同时求和占用内存，给必须的 y 细化留出一种工程选择。** 它仍保留全部 q CSR；最大单 q 因子、FE/local/port 数据可能单独造成超预算。

32060 是当前 AUTO 传播通道 inventory，尚未完成目标倏逝通道截断资格。int32 的结构计数通过也不证明最终更细网格、额外通道、后端 factor 索引或目标 ABI 已资格化。

### 7.2 目标内存模型按真实共存阶段建立

```math
M_{\rm peak}
=\max_t\left[
M_{\rm FE/local/ports}(t)
+M_{\rm all\ q\ CSR}(t)
+M_{\rm active\ PETSc}(t)
+M_{\rm active\ factor}(t)
+M_{\rm temporary/Krylov/output}(t)
+M_{\rm other}(t)\right].
```

在 one-slot 正确实现的阶段，active factor 从同时所有 q 的总和改成当时一个 q；全流程最大值仍要覆盖建 CSR、转换、numeric、PC/native、恢复和检查的不同阶段。不得只拿最大单 q CSR 与 2 TB 比较。新的 E1 symbolic/numeric 是校准点，但不允许把小例 factor/CSR 比例直接乘目标结构上界宣布通过。

V19 的目标工作只做有界原生 support 校准和计数：先检查已有 Ny=8 小网格是否覆盖目标所有方向/排列类；不足时用一个有界小型原生网格/空间补测缺少的 support，保持真实 MPC 和方向身份。不能未经证明把 348 搬到 Ny=8，也不能为了“实测 target”建立笔记本上完整目标 FE、CSR 或 factor。覆盖不足继续保留 432 fallback，并列可被下一项证据缩紧的具体项。[S14]、[S18]

### 7.3 时间代价必须把反复分解完整计入

对新策略，可采用可重算的阶段模型：

```math
T_{\rm field}
=T_{\rm prep/JIT/FE/CSR}
+\sum_q n_{{\rm build},q}T_{{\rm build},q}
+T_{\rm RHS/native/KSP/recovery/output/check}.
```

每 q build 明确包含哪些 PETSc 转换、symbolic、numeric 和 probe 子项；若已计入 build，不再在后一项重复计 probe。KSP 若包含 factor build，汇总时使用父阶段或拆开的互斥子项，不同时相加。

B0-Y8 直接测新增 build 次数及代价，E1 进一步测较大 q 的真实构建时间。若 one-slot 大幅节省内存但使重复分解成为主要 wall，应先用这些数据判断目标 172800 s 的缺口。不能从本机小例外推工作站多线程加速，也不能在本轮自动启动工作站或新的缓存策略扫描。

每个新必要整场从 activation/ABI/必要准备之前设置一个外层父时钟，到 required checker 和必要输出结束；记录 UTC、monotonic、boot ID 及现有保守 elapsed 规则。开发、测试、算子资格、运行前资产制作与单场工作各自列出；若前置资产是该场必需，给冷启动成本及可复用条件/读写成本。历史起点缺失保留 unknown，不补成零。

### 7.4 下一份精度证据要回答最终网格，而不是继续证明残差很小

V19 不自动铺开新网格扫描；应冻结下一次**同物理**精度对照的具体问题：

- x/y/z 哪个方向、哪个材料界面或倏逝通道截断尚未检验；
- 比较双方的几何、材料、入射、模式键及场坐标如何保持一致；
- E/H、散射场、scaled-curl、界面邻域和全部模式/功率采用什么共同积分与归一化；
- 所需资源和 cold cost 是否有依据。

沿用方向观察门：E/H/scaled-curl 1%，R/T/A/A_volume 绝对 1e-3，并报告显著衍射级和散射量。两个网格一致最多是 tested agreement，不能称连续极限证明。B0 的 y 比较只对其小几何和入射成立；E1 与 B0 若不是同一物理/mesh 比较合同，也不能拼成目标精度证明。

V19 的工程优先级仍是跑通当前更大的 E1。网格/模式精度计划与容量模型并行收敛，为后续真正扩大电尺寸和目标尺寸资格创造条件。

## 8. 普通 bug 连续修复，真实 gate 保持

普通的 NameError、shape/序列化、profile/入口接线、factor 生命周期接口、计数或 checker 错误，应保存原 attempt/source/raw evidence，在同一窗口内最小修复、定向验证、由主控冻结源码后继续。有效保存场因后处理错误不能自动重解；metadata/证书适配不能默认触发全量独立 FE oracle。

同一根因重复失败时先做能区分原因的局部重现与调用链检查，不第三次原样启动重型前缀。所有修复和重放成本计入原窗口，不以 bug 为由重开时钟。正常计算期间无输出先看 CPU、进程树、日志/heartbeat 和是否等待交互；不得用未经论证的短 timeout 杀掉正常 factor。

身份不符、NaN/Inf、终态数值/物理门失败、资源不足、task swap、OOM 风险或窗口截止，停止受影响路径，保留数据；继续不依赖该路径的安全工作。尚在收敛中的迭代不是终态失败，主控询问状态也不是 kill 指令。若新策略数学门失败，不能用资源收益抵消，更不能临时放宽门。

| 项目 | V19 保持的条件 |
|---|---|
| 参考 PC | 原 `NATIVE_AUGMENTED_RESIDUAL_QUALIFIED_V15` 数值合同 |
| actual q bounded / native FE / 非抵消 budget | 原各 `1e-8` 及其冻结归一化尺度 |
| 每个 fresh factor probe / strict q 结果 | 原 `1e-10`，与 bounded 结果分别报告 |
| alpha closure / decomposition closure | 原 `1e-9` / `1e-10` |
| augmented correction | 最多原允许的一次完整修正；RHS 额外求解上限 Ny；新建 factor probe 另记成本 |
| target identity / 原 A6 与释放后 A6 | 原 `1e-10` / ≤`1e-6` |
| 能量闭合 / 两种吸收一致性 | 原绝对 `1e-5` |
| 同离散实现比较 | E/H/scaled-curl、显著复振幅 `1e-4`；R/T/A/A_volume 绝对 `1e-5`；逐模式功率绝对 `1e-6` |
| mapping / regular operator 非对角 | 原 `1e-12` / `1e-11` |
| 局部 known-state 恢复 / 原与约化方程 | 原 `1e-11` / `1e-10` |
| 内存 / swap | 当前真实 physical/cgroup resource policy，保留系统余量；task swap=0 |

旧三次迭代是观测值，不要求新策略恰好三次才通过。正常科学误差、资源负结果和真实实现错误分开，不借“修 bug”反复筛选快样本。

## 9. V19 执行窗口与角色

V17/V18 共用旧窗口为 `2026-10-08T00:38:07.073088478Z` 至 `2026-10-09T00:38:07.073088478Z`，原 600 s 收口保留不变。V18 结项 snapshot 的 remaining 是当时值，不能在接收本报告时继续复制使用。旧窗口现已过期，历史累计费用、unknown、失败和终态永久保留。[S5]

**本次用户明确请求继续实质推进；本报告授权既有主控在接收 V19、核对旧 heavy 已结束且无重叠后，建立一次独立的 V19 开发窗口：最多 24 h，保留 600 s 收口。** T0 取实际启动此轮时刻，使用现有 campaign API 保存 manifest、parent window、UTC/monotonic/boot 身份、资源策略和预算。该窗口由执行链路实际建立，本次 ChatGPT 文档审阅没有启动它。

新窗口不覆盖或刷新 V17/V18，也不因普通 bug、新 commit、状态询问、测试或后续措辞澄清刷新。到期按原监督结束重型工作并收口；不由此推出自动连续开窗。24 h 开发窗口与最终单场 48 h 性能目标分别记账。

既有执行者在 canonical worktree 完成 P0–P5；既有主控处理源码冻结、集中提交/推送与结果核查，无需为本报告已经明确授权的每个后续阶段再向用户请示。继续单 heavy、资格化 activation、同一 ABI、原线程配置与独立 watchdog。真实凭据/访问边界未授权时按既有规则处理，不能换机器或项目绕过。

## 10. 交付物和 V19 结束时必须回答的问题

沿既有四份 compact 组织，避免新增一批彼此不一致的平行账本：

| 文件 | 必须回答 |
|---|---|
| `outcomes/records/review_v19_component_closure.json` | 策略/能力契约、全部 q 身份、资格复用范围、重建/淘汰/异常、RHS/probe/总计数、原数值 gate 是否闭合 |
| `outcomes/records/review_v19_sparse_capacity.json` | E1 入口是否优化；独立 owner 与阶段峰值；one-slot actual/estimated factor；销毁前后占用；目标 Ny=8 support 与 2 TB 缺口 |
| `outcomes/records/review_v19_formal_results.json` | 新 B0-Y8 同离散对照；E1 全部已完成阶段、场、R/T/A/A_volume/R00、全部通道、checker、真实失败 |
| `outcomes/records/review_v19_cost_and_readiness.json` | 全部 build/probe/RHS 次数及互斥成本；整场 cold/warm 边界；原尺寸精度/因子/时间未知项；新旧窗口终态 |
| `response_v19.md`、summary/test summary、run index、项目账本 | 主要结论、实际输入/source SHA、原始路径/hash、相对 V18 增量、下一项唯一优先工作 |

必要时在已有 compact 内增加所需字段，不要求为每个概念建一个新文件。所有事件追加；每个新 attempt 独立路径，保存输出不可默认覆盖旧比较/正式场。大型矩阵、因子、场和全 events 留在既有 ignored artifact/results。

V19 回应首先用数字回答：

1. 是否真正把最多 live factor/PETSc 从 Ny 降至 1，完整数学作用和同离散场通过了哪些门？
2. B0/E1 因此减少了多少**实测同时占用**，多少仅是 reserve 或逻辑 payload 差？
3. E1 是否首次完成当前 p6 reference 的 numeric、KSP 和官方场？若没有，新的最小缺口、主 owner 和首个不可跨越阶段是什么？
4. 为节省内存多做多少次 symbolic/numeric/probe，整场多花多少秒；主要成本从哪里迁移到哪里？
5. 目标 Ny=8 的 support、单 q 因子、所有 CSR/local/port 库存、最终网格和 172800 s，哪些已缩小未知范围，哪些仍不能判断？

**本次裁决：接受 V18 已验证成果，按本报告推进 V19。原尺寸 0.7 nm、2 TB、48 h 仍 `NOT_QUALIFIED`。** 这次的重点是把已有正确求解能力变成可测的内存/时间交换，并推动更大的同物理 E1 跨过 numeric 与整场阶段。

本报告提交前核对远程证据内容身份、数值转录与算术、Markdown 表格列数、围栏、引用及行尾空白。没有运行仓库 pytest、FE/PDE 或 CI。GitHub 网页实际 rendered view 未验证；这是文档展示边界，不是要求重算科学任务的理由。

## 11. 固定来源

以下链接全部固定到本次审阅 base，便于后续提交后复核原始依据。S7 为汇总与测试记录集合；S12 为完整参考逆及增广纠正两个相关实现。

- **[S1]** [V18 response](https://github.com/Rookie1234567/MyFEniCS/blob/64f1a0432db3d0e59335c5ba1f40b36cd0ae68f9/docs/task40extra_0p7nm_engineering/response_v18.md)。
- **[S2]** [V18 component closure](https://github.com/Rookie1234567/MyFEniCS/blob/64f1a0432db3d0e59335c5ba1f40b36cd0ae68f9/docs/task40extra_0p7nm_engineering/outcomes/records/review_v18_component_closure.json)。
- **[S3]** [V18 sparse capacity](https://github.com/Rookie1234567/MyFEniCS/blob/64f1a0432db3d0e59335c5ba1f40b36cd0ae68f9/docs/task40extra_0p7nm_engineering/outcomes/records/review_v18_sparse_capacity.json)。
- **[S4]** [V18 formal results](https://github.com/Rookie1234567/MyFEniCS/blob/64f1a0432db3d0e59335c5ba1f40b36cd0ae68f9/docs/task40extra_0p7nm_engineering/outcomes/records/review_v18_formal_results.json)。
- **[S5]** [V18 cost and readiness](https://github.com/Rookie1234567/MyFEniCS/blob/64f1a0432db3d0e59335c5ba1f40b36cd0ae68f9/docs/task40extra_0p7nm_engineering/outcomes/records/review_v18_cost_and_readiness.json)。
- **[S6]** [Run index](https://github.com/Rookie1234567/MyFEniCS/blob/64f1a0432db3d0e59335c5ba1f40b36cd0ae68f9/docs/task40extra_0p7nm_engineering/outcomes/records/run_index.json)。
- **[S7]** [Outcomes summary](https://github.com/Rookie1234567/MyFEniCS/blob/64f1a0432db3d0e59335c5ba1f40b36cd0ae68f9/docs/task40extra_0p7nm_engineering/outcomes/summary.md)；[test summary](https://github.com/Rookie1234567/MyFEniCS/blob/64f1a0432db3d0e59335c5ba1f40b36cd0ae68f9/docs/task40extra_0p7nm_engineering/outcomes/test_summary.md)；[任务 README](https://github.com/Rookie1234567/MyFEniCS/blob/64f1a0432db3d0e59335c5ba1f40b36cd0ae68f9/docs/task40extra_0p7nm_engineering/README.md)。
- **[S8]** [E1 V15 输入](https://github.com/Rookie1234567/MyFEniCS/blob/64f1a0432db3d0e59335c5ba1f40b36cd0ae68f9/input/task40extra_0p7nm_engineering/nonseparable_e1_p6_reference_v15.dat)。
- **[S9]** [E1 V17 输入](https://github.com/Rookie1234567/MyFEniCS/blob/64f1a0432db3d0e59335c5ba1f40b36cd0ae68f9/input/task40extra_0p7nm_engineering/nonseparable_e1_p6_reference_v17.dat)。
- **[S10]** [AllQExactMumps 生命周期与准入](https://github.com/Rookie1234567/MyFEniCS/blob/64f1a0432db3d0e59335c5ba1f40b36cd0ae68f9/src/solvers/task40_v10_p6_mumps.py)。
- **[S11]** [Worker 入口、共享缓存和 owner hooks](https://github.com/Rookie1234567/MyFEniCS/blob/64f1a0432db3d0e59335c5ba1f40b36cd0ae68f9/src/runners/task40_v10_worker.py)。
- **[S12]** [完整 q reference inverse](https://github.com/Rookie1234567/MyFEniCS/blob/64f1a0432db3d0e59335c5ba1f40b36cd0ae68f9/src/solvers/task40_v10_p6_yorbit.py)；[augmented reference correction](https://github.com/Rookie1234567/MyFEniCS/blob/64f1a0432db3d0e59335c5ba1f40b36cd0ae68f9/src/solvers/augmented_reference_correction.py)。
- **[S13]** [局部凝聚与缓存共享](https://github.com/Rookie1234567/MyFEniCS/blob/64f1a0432db3d0e59335c5ba1f40b36cd0ae68f9/src/solvers/hcurl_assembly_time_condensation.py)。
- **[S14]** [目标 support 与 CSR 结构上界](https://github.com/Rookie1234567/MyFEniCS/blob/64f1a0432db3d0e59335c5ba1f40b36cd0ae68f9/src/solvers/task40_p6_support_bounds.py)。
- **[S15]** [Review V18 与既有验收合同](https://github.com/Rookie1234567/MyFEniCS/blob/64f1a0432db3d0e59335c5ba1f40b36cd0ae68f9/docs/task40extra_0p7nm_engineering/review_report_v18.md)；[task.md](https://github.com/Rookie1234567/MyFEniCS/blob/64f1a0432db3d0e59335c5ba1f40b36cd0ae68f9/docs/task40extra_0p7nm_engineering/task.md)。
- **[S16]** [Ny=8 完整 operator qualification](https://github.com/Rookie1234567/MyFEniCS/blob/64f1a0432db3d0e59335c5ba1f40b36cd0ae68f9/src/solvers/task40_v18_ny8_operator_qualification.py)。
- **[S17]** [Ny=8 operator qualification reuse](https://github.com/Rookie1234567/MyFEniCS/blob/64f1a0432db3d0e59335c5ba1f40b36cd0ae68f9/src/solvers/task40_v18_ny8_operator_reuse.py)。
- **[S18]** [周期网格 profile 与原生校准](https://github.com/Rookie1234567/MyFEniCS/blob/64f1a0432db3d0e59335c5ba1f40b36cd0ae68f9/src/solvers/task40_v10_p6_periodic_profile.py)。
