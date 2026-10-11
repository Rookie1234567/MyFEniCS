# Task40extra Review V28：复用完整列结构，以稀疏投影完成 q0 数值 CSR 并打通分解续跑

## 0. 审阅结论与本轮决定

**V27 已经完成真正的 saved-only 构建入口和完整 q0 列结构，消除了上一轮“必须与 FE 重建对象共同驻留”的主要障碍。此次停点是固定时间截止时数值填充尚未完成。下一轮应复用这份完整结构，针对现行稠密 q 投影和逐项写入的额外工作量做精确优化，完成全部数值与已有 native 对照，并交付能直接调用的独立分解入口。**

这里的 saved-only 指直接使用已经保存、经过身份核验的局部矩阵和端口贡献；CSR 指把稀疏矩阵保存成“每行起止位置、列号、复数值”三组数组。V27 已经保存前两组，第三组只有完整大小的预分配文件，尚未完成全部贡献的累加。这是实际结构成果，但还不是可求解的完整数值矩阵。[R1][R2]

| 决策项 | 本次结论 |
|---|---|
| 审阅日期 | 2026-10-12，Asia/Singapore |
| 仓库 / 唯一执行分支 | `Rookie1234567/MyFEniCS` / `task40extra_0p7nm_engineering` |
| 审阅冻结结果 HEAD | `4e04f2fe2b3ea22e67cbd93ee1ffebfd66b50a79` |
| 最新结果提交时间 | 2026-10-11 19:44:08 UTC，即 2026-10-12 03:44:08 SGT |
| V27 正式科学源码 | `61530133bd02b18052e3ba64a5f78b87424c57f6` |
| 上一 review | `06eb5ae5cdaaa6de0d4d805937a279f8d06e0351` 中的 Review V27 |
| 增量 | 相对上一 review：7 commits、21 files；正式科学源码之后的 3 commits 仅为文档/证据 |
| 阶段判断 | `pass_with_qualifications`：接受结构成果与续作基础；数值 CSR 仍 `CSR_PENDING` |
| 本轮唯一主交付 | 完整 pattern 复用 → 精确稀疏投影填值 → 完整 CSR/native 回读 → 独立 factor continuation |
| 最终目标 | 0.7 nm、真实三维非分离模型、整机十进制 2 TB、task swap=0、单场全部必要费用 ≤48 h；当前仍未资格化 |
| Chat 工作范围 | 远程源码/compact/索引审阅、算术核对和本报告；没有启动 FE/PDE、工作站、SSH 或项目测试 |

本次核对了 30 份读取文件的 Git blob 身份，以及最新 run index 中 12 份 tracked 文档/记录的 SHA-256，均匹配。大矩阵和原始日志保存在执行机 ignored 目录，本次没有读取其完整数组；对它们的范围和状态判断来自冻结 compact、索引、源码及既有回执，不能将 tracked hash 核对称为重新运行了 raw numerical checker。[R12]

**不撤销已通过的 V26 完整消费者，不重做 producer/native，不再重建本次已保存的 pattern。** 新的数值优化维持同一离散算子、复数约束和端口定义；本轮不需要研制新预条件器或再开缩尺 PDE 面板。普通实现错误应在同一窗口中定向修复后继续；真实身份、数值或资源失败按受影响阶段处理。[R17]

## 1. V27 的实质进展与尚未完成项

### 1.1 实际模型和资格范围

最终 parent target 为原尺寸 50×25×140 nm、0.7 nm、真实非分离 Si/air，工程网格 Nx272/Ny8/Nz14/p6。V27 实际处理的是去除 notch/void 的 regular reference 的 q0：272×2×14=7,616 cells。q 是参考问题沿周期方向分解出的相位支路。构造完整 q0 能给出真实单支路矩阵和分解成本，但不等于带缺口的原尺寸 target 已经求解。[R1][R2][R14]

| 项目 | V27 事实 | 数据身份与解释 |
|---|---:|---|
| q0 增广矩阵维数 | 777,644×777,644 | recorded：773,568 trace rows +4,076 q0 port aliases |
| local sector 端口数 | 7,932 | profile-derived；q0 4,076 +q4 3,856；不是全 target 的 32,060 |
| FE/MPC/native 重建 | 0 | recorded；源码确认 saved-only 路径没有重建 FE/native |
| 完整结构位置 | 577,061,168 | recorded；结构预分配 slots，不是已测 numeric nonzero |
| 有结构的行 | 777,644 /777,644 | recorded；V27 完整 row counts 与 V26 witness 一致 |
| 支撑路由 | 3,428,612 | recorded；用于构造完整列索引的路由 |
| pattern 生成时间 | 2,106.866994 s，35.11445 min | measured；单独结构阶段 |
| 数值状态 | `NUMERIC_FILL_INCOMPLETE` | recorded；没有完整 data hash |
| 数值完成比例、numeric nonzero、exact-zero | UNKNOWN | 不能由预分配文件长度推导 |
| 完整 CSR/native readback、factor、KSP、target PDE、official R/T/A | NOT_RUN | 全 q 完整数值资格仍 0/8 |

V26 两组 q0 保存流/native 比较约 1.9e-14，q0/q4 双向泄漏和 scaled error 在约 1e-16 量级，已经具备继续构造矩阵的基础。这些是被继承的 V26 资格；V27 没有重新执行它们，也没有自动将其提升为新 CSR 的数值资格。[R2][R17]

### 1.2 这次保存了哪些可继续使用的实物？

| Artifact | 文件字节数 | 内容与下一步用途 |
|---|---:|---|
| 完整 row witness | 2,121,772 B | 行计数和偏移量的保存见证 |
| support/routes SQLite | 1,328,558,080 B | 完整结构路由；保留为历史结构资产，数值续填无需重新读取路由 |
| `indptr.npy` | 3,110,708 B | 全部行的起止位置，含 NPY header |
| `indices.npy` | 2,308,244,800 B | 全部列号，含 NPY header |
| `data.npy` | 9,232,978,816 B | 完整 shape 的预分配，含 header；数值尚未完成 |
| 原 manifest | 18,336 B | 原 V27 状态和 hash 绑定；续跑时保留原字节 |

完整 CSR 三数组的有效 payload 为下式，文件 header 另计：

```math
B_{\mathrm{CSR}}
=16N_s+4N_s+4(n+1)
=11{,}544{,}333{,}940\ \mathrm{B},
\qquad n=777{,}644,\quad N_s=577{,}061{,}168.
```

其中 data 有效 payload 为 9,232,978,688 B，列索引加行指针有效 payload 为 2,311,355,252 B。当前 data 文件完整大小只说明空间被预留，并不说明全部值已经写完。`contribution_cursor=null`，原 partial data 必须按清零重填语义处理。[R2][R10]

## 2. 本次是时间停止，不能沿用上一轮的资源失败结论

| 口径 | 最新数值 | 正确解释 |
|---|---:|---|
| process-tree RSS peak | 12,962,181,120 B，约 12.072 GiB | measured；正式 worker 进程树峰值 |
| dedicated cgroup memory peak | 13,374,246,912 B，约 12.456 GiB | measured；含该 cgroup 被计入的页等对象 |
| dedicated cgroup hard cap | 17,179,869,184 B，16 GiB | 本次执行上限 |
| 历史 cgroup peak 与 cap 差 | 3,805,622,272 B | derived 的历史差值，不能当作下一次实时可用内存 |
| task-local swap peak | 0 B | tree/cgroup 任务口径通过 |
| WSL 全局 swap 变化 | pswpin +239 页，pswpout +6,345 页 | 主机级计数，归因 UNKNOWN |
| watchdog monotonic | 11,781.220024 s，3.27256 h | measured；watchdog scope |
| mathematical worker monotonic | 11,781.298810 s | measured；与 watchdog scope 分开 |
| watchdog UTC | 13,088.488086 s，3.63569 h | measured；与 monotonic 差 1,307.268062 s，原因未证明 |
| 数值 cutoff 的 campaign 投影 | 20,405.100316 s | cumulative accounting；数值余量为 0 |
| 终止原因 | `PERFORMANCE_CONTROLLED_STOP` | 固定 campaign 时间门；不是数值误差或 factor 资源失败 |
| 退出与清理 | leader exit15；service wrapper exit3；descendants cleared | 数学 worker 已退出、后代为空 |
| outer required checker | returncode=null，pass=null | 保留 UNKNOWN，不能写正式 checker PASS |

这些事实说明：**V27 已经跨过了此前导致 CSR 在分配前停止的执行路径障碍，开始了全量 data 填充；但尚未证明完成填值、回读和求解的全链内存峰值。** 完整数值 data 的最终工作集可能继续变化，因此下一次仍需实时资源准入。[R3]

同时不要把“6 小时窗口耗尽”写成“数值填充已经运行 6 小时”。窗口含开发、冻结源码、三个前置失败、启动、结构、填值及监督；正式 worker 约 3.273 h monotonic。worker 时间减 pattern 时间还混有加载、hash、清零和其他操作，不能当作纯 fill 时间。当前已交付 compact 未提供持续的填值阶段和完成计数，源码中的数值汇总主要在函数返回后生成，无法可靠判断停止时正在 H、volume 还是 surface，也无法承诺同样程序再给 6 小时必定结束。[R3][R4]

行政收口也应准确记账：较早 main audit 的累计为 21,781.078777 s，对应当时 UTC 超时 181.074672 s；最新 run index 的 sequence45735 已累计 21,990.376181 s，即比 21,600 s 合同累计多 390.376181 s。两者不是同一快照。数值 cutoff 保持执行，行政收口没有恢复数值工作。[R12][R18]

## 3. 源码审阅：哪些工作应保留，哪些地方需要立即改？

### 3.1 保存贡献的数学实现可以保留

`SavedQ0ContributionAdapter` 的坐标是 reduced trace+port。体积项使用保存的 cell expansion 与 Schur class；C 与 -D 使用已经完成 MPC 的 surface 值，仅做 original-to-active lookup；-D 使用普通转置和负号，不加额外共轭；非零 unmapped 值仍被拒绝。[R5]

旧 `_constrain_local_schur` 已经用稀疏 expansion 计算局部约束，不能把它误说成“目前全部 MPC 都在做稠密矩阵乘法”。其 1267–1277 行为：

```math
V_c=E_c^H S_c E_c.
```

V27 后续 q 投影才是本轮重点：对每个局部贡献 V，取稀疏 q 映射 L、R，计算 L^H V R。现行通用投影器先提取支撑，再将 L、R 转为稠密数组。我们要保持这个数学结果，只减少为大量零元素和重复支撑执行的工作。[R6][R13]

### 3.2 具体性能问题及优先级

| 优先级 | 已在源码确认的行为 | 最小改进及边界 |
|---|---|---|
| P0 | `_project_accumulate_v16` 对每个贡献切 sparse map、unique 支撑，再 `toarray` 做 L^H V R；yorbit1840–1967 | 新增显式 opt-in 的精确稀疏局部投影/写入路径；保留当前核心作相关 fixture 对照；不改离散算子 |
| P0 | H 是对角，但 saved_q0753–764 仍生成 local-port×64 的稠密零块，并经通用投影 | 从实际保存的端口映射计算加权对角/小稀疏项，写入既有 pattern；不能把原 h 原样填入，也不能无条件填 I |
| P0 | C/-D 每个 port 单独生成列/行；通用 scatter 对每个目标行重复执行 Python 循环和 searchsorted | 精确稀疏投影；按相同已验证支撑作有界小批处理或专用列/行 scatter，减少逐标量查找 |
| P0 | stage1435–1473 只归并 contribution 标签；projection 标签仍含 cell/provider ID；1459 用 list 上的 `next(...)` 查找 | 用字典按语义阶段索引/汇总，保留次数、峰值、原失败的精确标签；消除随 G 个不同标签累积的 O(G²) 查找 |
| P1 | `_selected_csr_nnz` 逐选中行 Python 求和；相同局部支撑可能重复抽取 | 对已验证行索引使用向量化差分求和或有界缓存；不缓存每个 cell 的整份大矩阵 |
| P1 | 数值统计主要在累加器 return 后写入；中途停止时无阶段/计数 | 在同一次全量填值中持续保存轻量进度和分项用时；进度不是可恢复游标 |

[R5][R6][R7]

这些是源码确认的额外计算与记录成本。**当前没有分项 profile，不能宣称某一个已经被实测为总耗时的 90%，也不能承诺一个未经测量的加速倍数。** 但直接把稀疏映射稠密化、对角项通用化和线性查找日志的路径改掉，具有明确的计算依据，比原样再跑一遍更有推进价值。

具体实施顺序为：先打通 existing-manifest 薄入口与实时准入，补进度；在首个数值 pass 前完成这组局部稀疏投影改动及少量相关 fixture，然后直接在完整 q0 数据上持续填值。不要先做一轮原样 3 小时 profile，再等下一 review 才优化。

### 3.3 精确优化的数学合同

定义 U_t 为实际保存 q0 映射的 trace 部分，U_p 为 port 部分。U_c 是 U_t 限制到第 c 个 cell 的 `active_ids` 行所得的映射，其行顺序与 E_c 的列顺序一致。对第 j 个端口，b_j、d_j 已经处于保存的 reduced 坐标。目标贡献为：

```math
\begin{aligned}
A_{q0,c} &= U_c^H(E_c^H S_c E_c)U_c,\\
C_{q0,j} &= (U_t^H b_j)(e_j^T U_p),\\
(-D)_{q0,j} &= -(U_p^H e_j)(d_j^T U_t),\\
H_{q0} &= U_p^H\mathrm{diag}(h)U_p.
\end{aligned}
```

注意 d_j^T 是普通转置；左侧 q 投影中的 H 是共轭转置，两者不能混为一谈。

局部投影可沿已有稀疏约束 helper 的乘法方式，用 sparse×dense 实现两侧投影，避免构造稠密 L/R。若采用单非零/排列式快速散射，必须先对真实映射证明相应支撑条件；多对一累加、非平凡复相位和多非零行要正确处理，不能以“q0 通常简单”作假设。[R6][R13]

当前端口映射带有 `s=1/sqrt(h)` 归一化；若一行映射只有一个非零 s，其 H 贡献应由保存值计算 `conj(s)*h*s`。它可以接近 1，但实现不应盲填 1 或原始 h。对 q0 映射中严格为空的 q4-alias 行，可以在完成文件身份和结构核验后跳过数值投影；这属于同一 q0 矩阵中的精确零，不是削减物理通道。[R6][R14]

当前 sector 是 7,932 个端口、H block width64，所以现行 H 贡献数为 ceil(7932/64)=124；volume 为 7,616 个 cell；C/-D 至多 15,864 项，总贡献至多 23,604。这些是源码/profile 派生的工作量，不是 V27 已经完成的计数。完整 parent 的 32,060 modes 不应代入本阶段计算贡献数。[R5][R14]

不得为优化而建立完整 COO 列表、全体 cell 投影缓存、全部端口耦合驻留，或越过既有 256 MiB staging 合同。精确零压缩不是本轮前置工作；结构保持 577,061,168 slots，值是否为零在完整数值完成后统计。

### 3.4 SQLite 不是本次数值吞吐的已证实原因

持久 routes 用于结构生成。`fill_saved_q0_csr_values` 调用的数值累加器单遍消费 H、volume、surface，不会为每个 row tile 重扫全部贡献，也不读取 SQLite。不能把当前超时归因于一个不存在的“逐 tile 完整数据重复扫描”，更不能通过再次生成 routes 解决填值问题。[R5][R6]

## 4. 真正可执行的 continuation：补齐入口，而非再交一段示意 API

### 4.1 现有正式 stage 不能直接恢复旧 pattern

stage_runner1656–1686 先 preflight，然后无条件 build structure，再 fill。builder 在 saved_q0941–946 又会拒绝已经存在的 manifest。已有 handoff 说明了底层 API，但没有独立可执行的 fill/factor wrapper。[R5][R7][R10]

本轮应在现有 runner/service 中增加窄的 continuation 分支和可复制命令，使用现有 run_case/watchdog/activation，不再复制一个大 runner。三个动作职责明确：

| 已有状态 / 请求 | 本轮动作 |
|---|---|
| `STRUCTURE_COMPLETE_VALUES_PENDING` 或 `NUMERIC_FILL_INCOMPLETE` | 实时准入 → 清零 data → 完整数值 fill → 回读 |
| `COMPLETE_CSR`，尚无绑定本次数组的 native PASS | 跳过 fill，执行现有四次 matvec readback |
| `COMPLETE_CSR` 且已存在匹配数组 hash 的 native PASS | 跳过 fill/readback，直接做独立 factor preflight/continuation |
| 当前资源无法 factor | 保留 CSR/资格成功，交可运行 factor 命令、真实资源需求及缺口 |

新操作显式接入 V28 window。现有 service429–461、selector837–907/1677–1720、checker5533 等位置绑定 V27 窗口，需按新 continuation 身份窄扩展。不要修改旧 V27 window、复用旧 deadline，或把 donor source 改署名为本轮 source。[R8]

### 4.2 清零前必须有完整 fill 准入

已有 fill API 在 mmap 三数组并清零 data 后才进入 contribution allocation gate；完整 CSR preflight 来自外层 build-first stage。独立调用不能遗漏这个门。[R5]

续填 worker 加载必要 donor adapter 后，必须在 mmap/清零前核算：

- 完整 CSR 页、实际 adapter 与 q0 map；
- 共享 Schur classes；
- 当前路径的有界投影/贡献工作区；
- 相应阶段的向量、hash buffer、监督和系统余量；
- 实时 host/tree/cgroup/disk 与 task swap。

同一 backing 的既有驻留页与新增页只计一次。mmap/file/dirty 页不能当作零内存，也不能把已驻留完整 CSR 再无差别算一份。继续使用真实动态余量和 16 GiB cap，不改宿主 swap 或抬 cap。factor 预算不得成为 fill/readback 的前置门。

### 4.3 保护旧 manifest，同时复用大数组

旧 V27 manifest 的 SHA 为 `1ea707f3c201359c390b620a5122d0102f5b34bd74873b5f00e3a40b673b94de`。当前 fill 会就地修改 manifest；若直接把旧文件交给它，旧 run index 绑定将失效。[R2][R5]

最小方案：

1. 原 V27 manifest、window、回执和行列文件保持原字节。
2. 在既有 CSR 数组所在目录创建独立名称的 V28 continuation manifest，引用相同 indptr/indices，并明确接管原未完成、没有 hash 的 data 工作文件进行清零重填；不将旧 V27 状态改写为成功。
3. 新 manifest 在 heavy pass 开始前就记录 current attempt/source/window、原 pattern manifest 的 hash、donor 身份和 data 复用事件。原 source_identity/donor 保留，新的 fill identity 单列。
4. 既有 arrays 保持同一位置，符合 complete opener 对 manifest 父目录内数组路径的检查；无需复制 11.5 GB payload。
5. 新 attempt 的操作记录指向新 manifest。若不能安全复用原 data，应明确真实磁盘与内存费用后再选择独立 data 文件，不能偷偷覆盖已完成或已 hash 的科学数组。

这些是轻量元数据接线，不需要通用 checkpoint/事务平台。

### 4.4 进度计数与可恢复游标分开

当前一个 contribution 会对多行 data 执行 `+=`。若在贡献中间停止，即使上一个 contribution 已记录完成，下一个也可能已写了一部分。从一个普通计数继续累加会重复写入。因此 V28 默认仍用安全的清零重填语义；实时计数只用于判断吞吐和剩余工作。[R5][R6]

在同一次全量 pass 中，至少约每60 s及 H/volume/surface 阶段边界保存：

- 当前组件、已完成/总 contributions 或 cell/port 数、最后完成标签；
- 读取、局部约束、q 投影、CSR scatter、资源 gate/记录、flush/hash 的用时；
- processed bytes、累计计数、RSS/cgroup anon/file/dirty、task swap；
- remaining workload 的分组件估计和不确定性；不能只用混合贡献总数的百分比预测总时间。

现有 `contribution_observer` 在 yorbit3085–3086 于累加前调用；`completed_count/last_completed_label` 必须在对应投影与 scatter 成功返回后更新，不能把该 observer 当作完成回调。

记录有明确父/子时间口径，不能重复加总；watchdog仍保持独立。若后续实测表明必须跨窗续填，再基于幂等输出 tile 或明确提交协议做数值恢复，不能只添加一个 cursor 就宣称可恢复，也不把事务开发作为本轮前置工作。

## 5. 完整数值验收：复用四次 matvec，立即保存资格

### 5.1 COMPLETE_CSR 尚不等于 native 对照通过

saved_q01192–1202 在数值遍历、统计和 data hash 后标记 `COMPLETE_CSR`；opener1206–1263 检查文件、类型、shape、canonical/sorted 和共享存储。它不验证矩阵与 native 是否相同。因此 standalone factor 不能只凭 COMPLETE_CSR 就进入分解。[R5]

现有 stage_runner1712–1917 已有合理且便宜得多的验证方式：

1. 完整 CSR 作用于已保存的非零输入 x1。
2. 完整 CSR 作用于另一组非零输入 x2。
3. 完整 CSR 作用于 x1 的 trace-only 部分。
4. 完整 CSR 作用于 x1 的 port-only 部分。

利用 trace/port 输出位置即可分离 volume、C、-D、Hhat，同时核对两组 total、分量和重组误差。全部沿用 1e-11 门限。该设计不复制 CSR 子矩阵，也不再执行第二遍 adapter contribution pass，应直接抽取/复用。[R7]

### 5.2 本轮 CSR 完成的验收内容

| 验收项 | 要求 |
|---|---|
| 结构 | shape777644²，stored slots577061168；indptr/indices 与 V27 hash 一致；列排序且唯一 |
| 类型和所有权 | complex128/int32；SciPy CSR 确实共享保存数组；完整页与额外 owner 有账 |
| 数值完整性 | 全部必要贡献已完成，finite；numeric nonzero/exact-zero 真实统计 |
| 持久化 | data完整hash；三数组shape/bytes/hash与新manifest绑定；从文件重新打开 |
| 原生对照 | 现有4次matvec；两个total、volume/C/-D/Hhat、off-block及重组门全部≤1e-11 |
| 资格收据 | 保存输出向量与独立可重算的误差；绑定CSR三数组hash、donor、input、source、window |
| 继续行为 | PASS后立即保存收据，再释放adapter/maps并评估factor；不逐小阶段等待新review |

目前 stage 会先把 native PASS 放在内存 operation，随后尝试 factor，最后才写 operation。V28 要在 readback PASS 后立即原子保存小资格收据；这样 factor 的 bug、资源拒绝或 watchdog 不会丢掉已经取得的完整 CSR 资格。[R7]

新 wrapper 要调用现有 donor verifier。`_adapter_source_bindings` 对 stream 复用已验证 hash，只复查 size，合理的前提是本次消费者已核验输入身份；不能拿一个未经校验的旧字典直接绕过大文件身份。一次已绑定执行中也不必反复读取同一大文件补 hash。[R5][R8]

### 5.3 普通 bug 的处理范围

V27 已保存三项前置失败：python -S bootstrap 导入 NumPy；local H 的7,932 sector aliases错误对照32,060 global modes；正式 NumPy runtime 的私有 NPY API 不兼容。最终61530133源码分别修复了这些问题，成功进入完整 pattern 和 numeric fill；不用再为它们重演失败。[R4][R11]

当前 required checker 为 null 也要保留。V28 应让启动状态、时间停止和 partial receipt 在监督层可落盘，补齐 checker 对 `PERFORMANCE_CONTROLLED_STOP` 的真实分类；现行部分分支只识别 resource controlled stop。此修复与新 continuation 的一次定向 cutoff fixture一起完成，不要求重新跑 V27。[R7][R8]

定向验证只需覆盖新稀疏投影与旧核心的非平凡复映射、多对一、非零复 D/普通转置、空 q 支撑、已保存 pattern 的清零续填、COMPLETE跳过fill、hash变化拒绝以及时间停止留下真实状态。沿资格化 runtime 验证 CLI/公共 NPY header。不要在全量填值前重复整仓或新开小模型 PDE。

## 6. 单 q 分解：已有实现可用，现行 16 GiB 路径仍不可原样容纳

单 q exact factor lifecycle 已在 `run_task40_v26_selected_q0_factor_lifecycle` 实现：complex128/int32/MPI1、canonical CSR、符号分析/INFOG、数值分解、fresh probe、另一组非零 RHS、完整 CSR true residual≤1e-10 和释放。[R9]

V27 没有尝试 factor，因为 CSR_PENDING。不能将报告中的预测预算写成“这轮 factor 实测内存失败”。

| 当前实现的对象账 | 大小 | 数据身份 |
|---|---:|---|
| 一份完整源 CSR，B | 11,544,333,940 B | derived |
| 源 CSR +显式转换副本，2B | 23,088,667,880 B | derived；已高于16GiB |
| 6个完整q0 complex128向量，V | 74,653,824 B | derived |
| 现行保守准入 envelope，7B+V | 80,884,991,404 B | derived；含PETSc/转换及4B symbolic guard；另需其他owner/系统余量 |
| numeric factor 实际峰值、分解用时 | UNKNOWN | 尚未测量 |

这是当前实现和完整结构下的预算，不是普适数学下界，也不是2TB不可行的证据。若后续精确零压缩或所有权真的改变，按新数组和生命周期重新计账，不能永久硬编码80.885GB。[R9][R17]

本轮交付独立 factor 命令/manifest 合同，接受完整CSR与native PASS收据，直接复用已有生命周期。资源允许时在同一获准窗口顺接 symbolic→numeric→probe→第二RHS→evict，分阶段立即保存峰值、INFOG、真实残差和时间。资源不允许时保留CSR成功和精确缺口，不反复启动已知同条件不能通过的分解。

当前 Task40 AGENTS 明确限定本机 canonical worktree，禁止SSH、切工作站/其他项目；16 GiB cap继续沿已资格化campaign和review合同，本报告不自动迁移或抬cap。主控可凭本轮完整文件与命令安排真正已授权的后续资源。执行目标环境尚未指定时，handoff明确该字段待安排，不能编造主机、内存或授权。[R15][R3][R17]

## 7. 如何推进整机2TB、48h，而不只降低迭代次数？

### 7.1 最有价值的下一项实测是完整 q 的 factor 父成本

`ONE_Q_REFACTOR_V19` 保留各q的CSR但只有一个live factor slot。在完整8q遍历中，后续每次PC调用通常都使各q重新经历cache-miss重建，包括必要的转换、symbolic、numeric、probe/hash等。单看迭代次数会漏掉大量重复分解费用。[R9]

```math
\begin{aligned}
T_{\mathrm{field}}={}&T_{\mathrm{prepare/JIT/build}}
+T_{\mathrm{startup\ symbolic}}
+\sum_q N_{\mathrm{rebuild},q}F_q
+\sum_q N_{\mathrm{rhs},q}S_q\\
&+T_{\mathrm{PC,other}}
+T_{\mathrm{target/Krylov}}
+T_{\mathrm{recovery/output/checker}}
\le172{,}800\ \mathrm{s}.
\end{aligned}
```

F_q使用完整cache-miss父成本，并说明是否包含fresh probe；已经包含的子项不再相加。S_q用于业务RHS。PC,other包括q投影、传递、局部凝聚/恢复、端口及augmentation外围费用。必要准备和JIT不能通过未计账预热藏掉。

| 假设每q重建成本 | 8q一轮仅重建成本 | 48h忽略其他一切费用时最多PC调用 |
|---|---:|---:|
| 1 min | 8 min | 360 |
| 5 min | 40 min | 72 |
| 20 min | 160 min | 18 |

上表只做敏感性示例，不是本项目的实测或预测。

### 7.2 用2TB余量减少重复分解，需要实测后决定

最终限制是整机2,000,000,000,000 B，含系统余量、所有共驻对象和任务zero swap。取得一个完整q的真实factor峰值和重建时间后，应评估同时保留更多**相同精确因子**所需的空间与所省时间。这样可以改变缓存/驻留策略而不改变预条件器的数学定义。

q0 CSR×8约92.3547GB只是情景，其余q的alias和复twist未逐一实测。不能凭这一数字认定全部因子能放进2TB，也不能凭当前16GiB限制否决最终2TB方案。需要完整并存账，而不是把各阶段峰值或各q单次峰值简单相加。[R9][R14][R17]

### 7.3 从当前阶段到最终大模型的明确出口

| 阶段 | 退出条件 | 后续动作 |
|---|---|---|
| V28完整q0 CSR | 全值、持久文件、4次native回读、实际吞吐和峰值 | 已有single-q factor直接续作 |
| 一个完整q factor | 实测symbolic/numeric/rebuild/RHS成本、峰值、残差、evict | 决定2TB内因子驻留数量与运行方式 |
| 全q参考及target接线 | 完整q覆盖；一般复twist随首次全q构建校验；真实target算子接线 | 第一次原尺寸工程pilot |
| 原尺寸pilot完整求解 | 真实场、原A6残差、恢复/输出/物理检查与完整时间账 | 精度、通道与资源资格 |
| 最终目标 | 同一准确模型，整机≤2TB、task swap0、全过程≤48h | 才授予目标达成 |

Nx272/Ny8/Nz14/p6是原尺寸工程pilot，不自动等于最终精度合格。完整原A6和物理结果的最终验收属于求解后工作，不能循环作为首次pilot开始前已经完成的条件。[R16][R17]

## 8. V28 执行窗口、持续推进和交付合同

本报告为下一轮Codex建立新的明确工作包；用户转交后按该包连续执行。旧V27窗口和费用继续保留，不恢复旧批次。

- 路径仅使用 `/home/shenjh/Projects/MyFEniCSx_task40extra_0p7nm_engineering`。
- 延续资格化activation、complex128/int32、MPI1/数学线程1、单heavy、独立watchdog、16GiB cap、动态host reserve、task swap0。
- T0从本包第一项实际准备/实现/测试开始冻结，总窗口21,600 s；收口预留1,200 s；数值cutoff=T0+20,400 s，总deadline=T0+21,600 s。修复不重置T0。
- 实施目标是尽早在首个小时内完成薄入口及必要定向验证，进入完整数据续填；这是一项工作安排，不是又一个在第60分钟自动杀进程的门。不要把大部分窗口花在扩展控制器和重复测试。
- 同窗修复明确普通bug并继续当前完整q0工作；真数值失败保留现有CSR和对照数据，修正受影响组件；真资源门按实时对象账处理；不靠缩模型、删通道、改精度、抬cap取得通过。
- 若实测吞吐不支持当前窗口完成，立即在本轮反馈具体组件、已完成量、剩余量和限速来源，在已有权限内作最小修复；不能到deadline才首次告诉主控“data尚未完成”。预测不足不构成自动刷新窗口的授权。
- 主控集中审核、冻结源码、提交和推送；执行者不commit/push，不创建新聊天/项目/worktree，不改master或ordinary default。沿既有窗口协作，不新建执行者subagent或定时自动化。

**下一份response先回答五件事：**完整数值CSR是否完成；是否复用旧pattern且FE/native重建为0；四次native对照的实际误差；真实分项吞吐/峰值和剩余瓶颈；下一次factor怎样用现成命令直接执行。随后再列bugs、测试与文档。

交付 `response_v28.md`、operator/resource compact、完整CSR/readback/factor的命令与manifest入口、run index、summary/test_summary及模型/进度总账。旧数值失败、null checker、未知计数和行政超时保持历史身份。当前导航仍有V26旧描述、summary一处相对链接和模型总账增量需随V28一次整理；这些文档问题不应阻挡全量数值工作。

## 9. 本轮审阅优先级清单

| 编号 | 类别 | 必须完成的改进 | 不能作为本轮终点的替代物 |
|---|---|---|---|
| P0-1 | 可执行入口 | existing-manifest fill/readback/factor分支；新窗口绑定；清零前完整准入 | 只有Python示意调用，没有可运行命令 |
| P0-2 | 填值吞吐 | 精确稀疏q投影、H与C/-D专用写入；去除O(G²)记录查找；有界计数/分项计时 | 原样再跑到time cutoff，没有任何新增诊断 |
| P0-3 | 数值实物 | 完整数值CSR与hash；复用现有4次native matvec并立即保存资格 | 文件全尺寸、测试通过或pattern再次完成 |
| P0-4 | 分解桥梁 | 独立factor入口、既有exact生命周期、真实资源合同 | 用16GiB重复撞现行80.885GB预算；或重新做预条件器 |
| P1-1 | 证据连续性 | 旧manifest保留，新attempt提前落盘，time-stop partial receipt | 覆盖旧hash、把普通进度计数当事务游标 |
| P1-2 | 项目收口 | 真实计时/内存/未运行范围与总账、命令、hash一次对齐 | 单独用一整轮修导航或补历史统计 |

## 附录 A：关键原始资产定位

完整路径和hash均以冻结operator compact及handoff为准。[R2][R10]

- 原V27 attempt：`20261011T153931.649307Z`。
- 原CSR目录：`results/task40extra_nonseparable_0p7nm/task40extra_0p7nm_target_original_ny8_operator_probe_v22__full3d_iterative__mpi1__Mna/20261011T153931.649307Z/v27_q0_csr/`。
- 原manifest：`task40_v27_q0_csr_manifest.json`；SHA-256 `1ea707f3c201359c390b620a5122d0102f5b34bd74873b5f00e3a40b673b94de`。
- indptr SHA-256：`6d24828a2cd820601fedf92c5b6575fc2dd95a905c2533677f3a3367648a7819`。
- indices SHA-256：`9279c5dbfb8921c61dc229ea6a99d30bb76f8b31d005076796d4504a1e7d0d6e`。
- row witness SHA-256：`56d344256ff60e73ec36ecd58d1aade6e6d7dac5164741de60f0631dc0407bda`。
- routes SHA-256：`a27d291a1bc41751b7a70f15bfef6cf1d1fc85aeb9ce4c01fd7f5153143186f1`。
- 原V27 window：`e806c514c8208ae7a887bdb6ddaaec25936c9204a3ccc34a4fb870ad0bb0010d`。
- 当前数学input SHA：`134ea5f08d5d5dbc366870f451ba0de0df5893c5cd73d227dac77f8a11aa2c0b`。
- donor producer：`9d0f4dbfc730dd620b709d048e33e9da6c77520c`；V26 accepted science：`f9093c87f81d52b75fbc156e562b3745df45ccf4`；V26结果base：`399787abc991e0e30975bc694bd18a9a30c5470e`。
- 本轮不改署名上述旧身份；V28 current execution和numeric fill identity另存。

## 附录 B：可直接交给 Codex 的完整文本

以下为待用户转交给既有Task40主控/执行者的文本，本报告没有代发消息。

```text
继续 Task40extra。拉取同一分支 task40extra_0p7nm_engineering 的 review_report_v28.md，完整阅读并按它连续执行。本轮审阅的最新结果 HEAD 是 4e04f2fe2b3ea22e67cbd93ee1ffebfd66b50a79，V27 正式科学源码是 61530133bd02b18052e3ba64a5f78b87424c57f6。

最终目标保持原尺寸50×25×140 nm、0.7 nm、真实非分离Si/air、complex128 Nédélec H(curl)、x/y Floquet、z Fourier-DtN、整机十进制2 TB并有系统余量、task swap0、单场必要准备/JIT/构建/求解/恢复/输出/检查≤48 h。Nx272/Ny8/Nz14/p6是原尺寸工程pilot，尚未自动获得最终精度资格。

V27的进展可以继承：saved-only路径FE/MPC/native重建为0，完整777644×777644、577061168 slots的pattern及indptr/indices已保存。此次是固定时间cutoff时numeric fill未完成；不是factor资源失败。不要撤销V26消费者资格，不重跑producer/native，不重建已有routes/pattern，不再用小面板或新PC代替完整矩阵进展。

本轮主交付：复用现有完整pattern，完成精确稀疏投影的全量数值填充及native对照，交付独立可执行的fill/readback/factor入口。普通bug在同一窗口定向修复后继续，不逐阶段停审。

1. 先打通真正的existing-manifest continuation。
当前stage无条件build再fill，不能直接复用旧pattern。给现有runner/service增加窄的continuation分支和可复制命令：
- pending/incomplete：只做实时准入、清零data、全量fill和readback；
- COMPLETE_CSR但没有匹配native PASS：跳过fill，做现有readback；
- COMPLETE_CSR且有匹配native PASS：直接factor preflight/continuation。
复用现有run_case/watchdog/activation，不复制大runner，不把仅有Python示意API当交付。为V28绑定新window，旧V27/V26 donor/source/window原样保留。

2. 清零前完成实时资源准入，保留历史manifest。
独立fill不能遗漏原build-first提供的完整CSR preflight。加载必要donor adapter后，在mmap/清零9.233GB data前，计入完整CSR页、q0 map/adapter、共享Schur class、有界scratch、向量和系统余量；同一backing已驻留页/新增页只计一次。mmap/file/dirty不算零内存，16GiB cap和task swap0不变。factor的80.885GB账不得阻止fill/readback。
旧V27 manifest的SHA为1ea707f3c201359c390b620a5122d0102f5b34bd74873b5f00e3a40b673b94de，必须保留原字节。可在原CSR数组同目录新建V28 continuation manifest，复用完整indptr/indices，明确接管原未完成且无hash的data工作文件从零重填；不把旧V27改写为成功，不复制整份11.5GB CSR。heavy开始前保存新attempt/source/window、旧pattern hash和data复用事件。donor verifier按现有链调用，不能只信传入的hash字典。

3. 在首个全量numeric pass前，完成精确稀疏投影与记录开销的最小优化。
当前generic _project_accumulate_v16将稀疏L/R转dense做L^H V R；H对角也生成7932×64零块；C/-D逐port走通用逐行scatter。以实际保存q0 map为准，使用sparse×dense或已验证的支撑scatter，保持相同矩阵。已有_constrain_local_schur本来就用稀疏E算E^H S E，不要误改或重做MPC。
H按实际保存映射计算U_p^H diag(h) U_p。selector行的贡献是conj(s)*h*s，s带1/sqrt(h)缩放，不能盲填h或I。C用U_t^H b乘右端口映射；-D保留普通转置、负号及正确左q共轭。空q支撑可在身份/结构确认后精确跳过，不能阈值丢项或删物理通道。C/-D可按同一支撑有界batch/专用scatter，减少逐标量Python/searchsorted；多对一和非平凡复相位必须正确累加。
resource_gates当前next(list)逐项查找且projection标签不归并，改字典按语义阶段聚合，保留计数/峰值和失败原标签，不降低实时资源门。不得建立全局COO、所有cell投影缓存或全部端口驻留；沿256MiB staging合同。保留旧核心作必要fixture对照，不再开小模型PDE。

4. 同一完整fill中持续报告真实吞吐。
约每60秒及组件边界落盘H/volume/surface阶段、已完成/总量、最后完成标签、读取/局部约束/q投影/scatter/gate记录/flush/hash计时、bytes、RSS/cgroup anon/file/dirty及task swap。按组件估计剩余工作并说明不确定性。
local sector为7932 ports、q0为4076 aliases；现行H派生124块、volume7616cells、C/-D至多15864项，这些不是V27已经完成量。不能拿32,060 global modes算本阶段贡献数，不能用data文件长度估计完成比例。
现有contribution_observer在累加前调用，completed_count/last_completed_label必须在投影与scatter成功后更新，不能把它当完成回调。
普通进度计数不是可恢复cursor。当前贡献会跨多行+=，中途停止可能只写了一部分，默认保留clear-all安全语义；不要为事务checkpoint平台推迟完整CSR。若吞吐不能支持窗口完成，在本轮尽早给出实测限速项并作最小修复，不到deadline才第一次汇报未知进度。

5. 完成后直接复用已有四次CSR/native matvec，立即保存资格。
从文件回读完整complex128/int32 CSR；记录stored slots、numeric nonzero、exact-zero、shape/bytes/hash及共享存储。保持V27完整行列hash。
提取现有stage的4次完整CSR作用：x1、x2、x1 trace-only、x1 port-only；由输出分块检查两个total、volume/C/-D/Hhat、native off-block和重组，门限全部1e-11。不要再次遍历全部adapter贡献、重建FE/native或复制CSR子块。
COMPLETE_CSR只表示填完及文件hash通过，不代表native资格通过。4次对照PASS后立即原子保存输出向量和绑定CSR三数组hash、donor/input/source/window的资格收据，再释放adapter/maps等并评估factor。factor失败/拒绝不能抹掉CSR成功。
监督/closeout补齐time cutoff的partial receipt与checker分类，保留V27原checker null，不能要求重跑V27补证据。

6. 交付独立factor命令，复用已有exact生命周期。
使用open_saved_q0_csr_from_manifest和已存在的run_task40_v26_selected_q0_factor_lifecycle；factor入口还必须消费匹配native PASS收据，或先执行上述4次readback。允许环境中直接完成symbolic→numeric→fresh probe→另一非零RHS→evict，full true residual≤1e-10，并立即保存INFOG/时间/峰值/释放证据。
当前保留完整结构时B=11544333940 B，源CSR+显式转换副本2B=23088667880 B，现行保守envelope=80884991404 B，另需其他owner/系统余量。这些是derived、不是实测factor。16GiB下不反复尝试已知同条件无法容纳的路径。交真实完成文件、manifest/资格收据、可运行命令、ABI/资源合同和当前缺口；主控安排真正已授权环境后可直接接续。目标主机未指定就明确待安排，不编造、不SSH、不切工作站/其他项目、不抬cap。若实际存储/所有权改变则重算，不把80.885GB永久硬编码。

7. 48h按真实cache-miss重建成本推进。
ONE_Q_REFACTOR_V19单live factor在完整8q遍历中通常每次PC都会重建各q。记录完整rebuild父成本F_q、业务RHS成本S_q，fresh probe避免重复计账；加上PC其他投影/传递/局部凝聚恢复/端口/augmentation、target作用/Krylov和输出checker。取得单q实测后，按2TB完整共驻账选择能保留多少相同精确因子以减少重复分解，再推进其余q和原尺寸pilot。q0CSR×8约92.35GB仅为情景；一般复twist随首次全q构建自然验收。

8. 窗口与交付。
仅用/home/shenjh/Projects/MyFEniCSx_task40extra_0p7nm_engineering，资格化activation、complex128/int32、MPI1/数学线程1、单heavy、独立watchdog、16GiB cap、动态host reserve、task swap0。主控集中冻结/提交/推送，执行者不commit/push，不创建聊天/项目/worktree，不改master/default。
从本包第一项实际准备/实现/测试冻结新V28 T0，总21600s，收口1200s，数值cutoff=T0+20400s，总deadline=T0+21600s。旧窗口和负结果/unknown保留，bug修复不刷新T0。争取首小时内完成必要薄入口与定向验证进入全量fill，这不是额外60分钟杀进程门。
提交response_v28、operator/resource compact、独立fill/readback/factor命令与manifest、run index、summary/test_summary、模型/进度总账。先回答完整CSR是否完成、旧pattern是否复用、native误差、分项吞吐/峰值/剩余瓶颈、下一次factor如何直接运行；随后再列bug和测试。未运行的全q、target PDE、最终精度、2TB/48h和master merge不写成通过。
```

## 附录 C：冻结来源

所有引用固定到本次结果HEAD；R17固定到上一review提交。源码行号说明针对这些冻结版本。

[R1]: https://github.com/Rookie1234567/MyFEniCS/blob/4e04f2fe2b3ea22e67cbd93ee1ffebfd66b50a79/docs/task40extra_0p7nm_engineering/response_v27.md
[R2]: https://github.com/Rookie1234567/MyFEniCS/blob/4e04f2fe2b3ea22e67cbd93ee1ffebfd66b50a79/docs/task40extra_0p7nm_engineering/outcomes/records/target_operator_probe_v27.json
[R3]: https://github.com/Rookie1234567/MyFEniCS/blob/4e04f2fe2b3ea22e67cbd93ee1ffebfd66b50a79/docs/task40extra_0p7nm_engineering/outcomes/records/time_resource_accounting_v27.json
[R4]: https://github.com/Rookie1234567/MyFEniCS/blob/4e04f2fe2b3ea22e67cbd93ee1ffebfd66b50a79/docs/task40extra_0p7nm_engineering/outcomes/records/review_v27_incremental_workflow_ledger.json
[R5]: https://github.com/Rookie1234567/MyFEniCS/blob/4e04f2fe2b3ea22e67cbd93ee1ffebfd66b50a79/src/solvers/task40_v27_saved_q0.py
[R6]: https://github.com/Rookie1234567/MyFEniCS/blob/4e04f2fe2b3ea22e67cbd93ee1ffebfd66b50a79/src/solvers/task40_v10_p6_yorbit.py
[R7]: https://github.com/Rookie1234567/MyFEniCS/blob/4e04f2fe2b3ea22e67cbd93ee1ffebfd66b50a79/src/runners/task40_v20_stage_runner.py
[R8]: https://github.com/Rookie1234567/MyFEniCS/blob/4e04f2fe2b3ea22e67cbd93ee1ffebfd66b50a79/scripts/task40_v20_service_workflow.py
[R9]: https://github.com/Rookie1234567/MyFEniCS/blob/4e04f2fe2b3ea22e67cbd93ee1ffebfd66b50a79/src/solvers/task40_v10_p6_mumps.py
[R10]: https://github.com/Rookie1234567/MyFEniCS/blob/4e04f2fe2b3ea22e67cbd93ee1ffebfd66b50a79/docs/task40extra_0p7nm_engineering/outcomes/target_stage_handoff_v27.md
[R11]: https://github.com/Rookie1234567/MyFEniCS/blob/4e04f2fe2b3ea22e67cbd93ee1ffebfd66b50a79/docs/task40extra_0p7nm_engineering/outcomes/records/targeted_tests_v27.json
[R12]: https://github.com/Rookie1234567/MyFEniCS/blob/4e04f2fe2b3ea22e67cbd93ee1ffebfd66b50a79/docs/task40extra_0p7nm_engineering/outcomes/records/run_index.json
[R13]: https://github.com/Rookie1234567/MyFEniCS/blob/4e04f2fe2b3ea22e67cbd93ee1ffebfd66b50a79/src/solvers/hcurl_assembly_time_condensation.py
[R14]: https://github.com/Rookie1234567/MyFEniCS/blob/4e04f2fe2b3ea22e67cbd93ee1ffebfd66b50a79/src/solvers/task40_v10_p6_periodic_profile.py
[R15]: https://github.com/Rookie1234567/MyFEniCS/blob/4e04f2fe2b3ea22e67cbd93ee1ffebfd66b50a79/docs/task40extra_0p7nm_engineering/AGENTS.md
[R16]: https://github.com/Rookie1234567/MyFEniCS/blob/4e04f2fe2b3ea22e67cbd93ee1ffebfd66b50a79/docs/task40extra_0p7nm_engineering/task.md
[R17]: https://github.com/Rookie1234567/MyFEniCS/blob/06eb5ae5cdaaa6de0d4d805937a279f8d06e0351/docs/task40extra_0p7nm_engineering/review_report_v27.md
[R18]: https://github.com/Rookie1234567/MyFEniCS/blob/4e04f2fe2b3ea22e67cbd93ee1ffebfd66b50a79/docs/task40extra_0p7nm_engineering/outcomes/records/main_closeout_audit_v27.json
