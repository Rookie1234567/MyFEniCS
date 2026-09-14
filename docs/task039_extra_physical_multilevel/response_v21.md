# Task39extra Response V21 / Review V20：低内存生命周期方案完成一场 original 通过，但仍是时间—内存取舍

本轮先把完整 p6 数学表达式编译成计算代码，再建立供反复回代使用的 p4 分解数据，减少编译器与大因子同时占用内存。另将不改变输入向量的 450 阶单位算子改为只读共享数组，并在完整场保存、原 A6 真实残差核验和必要数据包完成后，释放不再需要的求解对象，再做官方后处理。p4 原矩阵因后端仍借用其数据而安全保留到因子销毁。这些动作保持原算法，分别核验数组载荷、对象生命周期和操作系统实测内存。

## 第一屏结论

| 问题 | Y3 正式证据 | 结论 |
|---|---|---|
| 编译是否提前 | p6 condensation target 在 `schur_factor_symbolic_started` 之前实际 cache miss；编译器在场采样 76 次，target 编译耗时 `56.762399450992234 s` | 是；不是只复用 warm cache。全过程峰值仍包含编译器 |
| identity/cache 是否精简 | 12 个逻辑类别、450×450、float64 identity 共用 1 份只读存储；`unique_numpy_bytes=183282224`，V19 为 `201102224` | 实际少 `17820000 B` 数值 payload；不把这部分直接当 RSS 收益 |
| p4 矩阵是否提前释放 | PETSc 3.19.6 的实际转换路径把 SeqAIJ 数值指针交给 MUMPS；未找到安全的 public detach 证明 | `MATRIX_RETAINED_BACKEND_DEPENDENCY`；因子按生命周期释放，原 p4 矩阵不在 factor 活跃时提前销毁，记账节省为 0 |
| 最终释放是否破坏结果 | 完整场 packet、释放前/后 native A6、端口闭合、内部残差、80 个端口和物理后处理均通过 | 释放顺序正确；后处理使用已保存的完整场/必要 packet |
| 正式数值 | original，112 步；独立重算 A6=`9.730817853580463e-7`，worker post-release=`9.730817853580687e-7`，限值 `1e-6` | 数值、物理和资源安全通过 |
| 内存取舍 | 全过程树 RSS `2831749120 B`；V19 为 `3965534208 B`，V18 为 `2528460800 B` | 比 V19 低 `28.59098%`，但比 V18 高 `11.99498%`；不能称全面省内存 |
| 时间取舍 | measured full-workflow monotonic=`1479.1772295139963 s`；V19=`1352.0121227929922 s` | 比 V19 慢 `9.4056%`；`1611.2442379729905 s` 是保守 billing，不是 measured runtime |

因此本轮状态是 **`PASS_ORIGINAL_MEMORY_LIFECYCLE_MIXED_TRADEOFF`**：授权范围已完成，新 profile 保持了 V19 的收敛和物理结果，降低了实测全峰，代价是本场时间增加。建议在本次固定 original、内存优先时采用显式 V20 lowmem 配置，保留 V19 为时间基线、V18 为较低 RSS 基线。后两项比较不构成新增 Gate。普通默认不变，不自动合入 master，不恢复 notch，不扩展到 5 nm、0.7 nm、MPI2/4 或生产可扩展性结论。

## 1. 身份、范围和环境

正式根目录为
`results/euv_grazing1_phi0/task39extra_v20_y3_lowmem_original__full3d_iterative__mpi1__Mna/20260914T163338.120918Z`，对应输入 `input/task39extra/v20_y3_lowmem_original.dat`。正式源码 SHA 是 `b337d215c3d278d0c1e715f53e28b69f7f0ee3fe`，Y0/Y1 审查基线是 `322cec9d699d24e0feed045136a7bbc41cfc10ab`，分支为 `task39extra`。

模型仍是固定的 13.5 nm、252 个轴对齐仿射六面体、Full3D p6/h10、MPI1、线程1、80 个 DtN 通道、同一 physical/mode/RHS identity。ABI preflight 为 PETSc 3.19.6、`complex128`、`int32`、DOLFINx 0.10.0.post2、Basix 0.10.0、SLEPc 3.19.6；解释器为资格化 `.venv`。Y1 冻结合同检查显示 47 个文件、25 个 profile 均未被正式运行修改。

这是一场 one-dat/one-run 的 Y3 original：formal run `1`、PDE replay `0`。旧 V19 与 V18 记录没有被覆盖；notch 是 `not_run`，原因是 Review V20 明确不恢复它，而不是本轮数值拒绝。

## 2. 五个问题的直接回答

### 2.1 编译确实发生在大因子前，但 cold cache 只能证明本场顺序收益

连续 watchdog 记录到的顺序是：form preparation → p4 symbolic/factor 与 H6/p6 cache setup → outer KSP → field packet/A6 → release → official postprocess。p6 condensation target 在大因子前发生一次实际 miss，formal cache 中生成了该模块；其他评价 kernel 复用同一正式 cache。编译使用 `-O2`、`-g0`、`cffi_debug=false`，准备窗口前置且只有一个 preparation window。

本场 cache 不是简单的全 warm 命中：eligible 文件 140 个、`1417038702 B`，没有复制（hardlink 140 个）；另外排除旧 module family `libffcx_forms_9c081a2454e80304289733853e6aa2b2d94badd9` 的 `196161200 B`、4 个文件。正式 p6 target miss 的 `.so` module file 为 `43662736 B`，编译器在场采样 76 次；生成 C 源码本身为 `108831921 B`。新旧 target 具有相同 form signature、ABI、选项和源码大小，但 raw C 的 SHA 不同、新旧 inode 不同；Y3 的诊断只确认“实际重新编译”，没有宣称生成 C 文本逐字节相同，也没有继续追究所有文本差异的原因。

全过程峰值 `2831749120 B` 正好包含 compiler descendant；因此下面的峰值没有剔除 `cc1`。编译提前避免了 V19 中“大因子/编译器叠峰”的已知形态，但准备本身仍然是全过程的一部分。

### 2.2 identity 实际减少了 payload；p4 矩阵没有被危险地假设为可释放

450 阶数组在 12 个逻辑类别中代表同一个 identity operator，三个角色是内部 RHS projection、solution embedding 和 residual projection。正式表示是一个 `450×450`、`float64`、只读、按 interior shape 共享的对象：`unique_storage_count=1`、`unique_storage_bytes=1620000`。完整 p6 数值 cache descriptor 的 content SHA 为 `c79e781afb4b866db0e38bcaafd92d80f8148c847e1de6bec594ebc4994db62e`；它不是某一张 identity 数组的单独 SHA。与 V19 的 `201102224 B` unique NumPy payload 对照，本场为 `183282224 B`，差值 `17820000 B`。这是数组账本中的确定节省，不是同量 RSS 返还承诺。

p4 方面，Y0 读取了实际安装的 PETSc/MUMPS 路径和 v3.19.6 wrapper：转换过程调用 `MatSeqAIJGetArrayRead`，随后把得到的数值指针交给 MUMPS；没有验证过的 public detach 能证明 MUMPS 后续 solve/JOB_END 已不再依赖它。因此正式策略是 `MATRIX_RETAINED_BACKEND_DEPENDENCY`：

- p4 CSR shape=`21824×21824`、NNZ=`8184464`、dtype=`complex128`；
- CSR、mapping、values hash 在 factor 前、factor 后及最终释放前保持：`19b9fbf759e6dc586d1316b53c69099647bd3a23e43378535b718c1db2c218d8`、`aeaabb3ae1358a3979fc3dbd98b0c59d0b39e3c8fa2c3d31433b1ccdfed75b89`、`1641af69d3380132fb9dd84372defef6998f38373e203bf6dc85cc5f08e473b8`；
- Y0 后端账本另报 MUMPS allocated upper=`1463000000 B`、used upper=`838000000 B`、matrix=`232205060 B`；它们不是 RSS，不能作为“已释放字节”相加或替代 RSS；
- 非 Hermitian、非零 RHS 的 10×10 后端 fixture 中，四次 solve 都发生在 factor 仍存活时，最大 residual `2.835794086517554e-16`；factor 销毁后只核对矩阵仍可读且内容未变，未测试销毁 factor 后继续 solve，更未测试 factor 活着时先 free 原矩阵，后者标为 `NOT_RUN_NO_LIFETIME_PROOF`；
- 因而 early matrix release 未实施，矩阵载荷节省为 `0 B`；没有 ctypes/private-pointer、手工 free 或另复制整张矩阵的规避。

### 2.3 释放对象的顺序通过，RSS 只小幅下降

Y3 的独立 lifecycle checker 验证了以下顺序（每个事件恰一次）：

```text
完整场 packet 保存
→ independent final residual complete
→ release gate
→ preconditioner release → p6 release → p4 factor release
→ post-release native A6 complete
→ official physical output comparison
```

释放前最近 watchdog 样本的树 RSS 为 `2278993920 B`；p4 release 后最近样本为 `2253828096 B`，差约 `25165824 B`（约 25.17 MB）。这是采样到的 simultaneous RSS 变化，不能解释为“全部 MUMPS allocated payload 已归还”。同理，MUMPS 的 allocated 字段、Python/PETSc 对象账本和 RSS 是不同口径；本轮没有加入 `malloc_trim`、allocator 扫描或 gc 调参来制造归因。

### 2.4 原残差、完整场和 official 输出仍正确

worker 每 8 步保存一次 Schur/恢复后的原 A6 checkpoint，independent checker 读取这些保存值并重算；重复的 checkpoint 行去重后为：

| iteration | original A6 relative residual |
|---:|---:|
| 0 | `1.0000000000000004` |
| 8 | `0.07149884433355884` |
| 16 | `0.00903590941193259` |
| 24 | `0.0017208335140301643` |
| 32 | `0.00028444254527382787` |
| 40 | `0.00026094029460383127` |
| 48 | `0.00012760011574671415` |
| 56 | `0.00005129021279317979` |
| 64 | `0.000017690954651964774` |
| 72 | `0.000017380663782453644` |
| 80 | `0.000012626743662104743` |
| 88 | `0.000004539202102579487` |
| 96 | `0.0000014932835709058237` |
| 104 | `0.0000013902011012104626` |
| 112 | `9.730817853580463e-7` |

最终 independent retained checks 为：port closure `5.8476980231808125e-16`、internal residual `2.1627175873860883e-17`、native identity `8.175908441682495e-12`、Schur port identity `1.1206608495164462e-29`。worker 的 post-release summary 记录 A6=`9.730817853580687e-7`；两份值都通过 `1e-6` Gate。

完整场保存后与 V19 的 saved-array comparison 显示：solution SHA 都是 `e077e0bd92fc93a54673aae4246fcc1d7c0dc3aceba9c3ee3fb48103c1e76cd3`，x 逐字节相同，field、R/T/A/`A_volume`、modal 和 E/H sample metrics 数值相同；未把仅因 run-dependent evidence path 不同造成的字典差异误报为物理差异。

官方结果为（表中 reference 是既有离散参考，V19 也使用它；不是把 reference 数值冒充成 V19 本场重新测得的字段）：

| 量 | Y3 current | 既有离散参考（V19 同样使用） | absolute difference |
|---|---:|---:|---:|
| `R` | `0.3656258136701664` | `0.3656257891008744` | `2.4569291989795516e-8` |
| `T` | `0.012990624019505325` | `0.012990632411728584` | `8.392223258338327e-9` |
| `A` | `0.6213835623103282` | `0.621383578487397` | `1.6177068795641958e-8` |
| `A_volume` | `0.6213833803349053` | `0.6213835784928156` | `1.981579103027542e-7` |

最大 total power 差 `1.981579103027542e-7 < 1e-5`；modal power 最大差 `2.4579416113557073e-8 < 1e-6`，amplitude relative difference `1.4777111110917282e-7 < 1e-4`；selected field 最大 relative difference `8.291924787930399e-7 < 1e-4`。E/H、curl、坐标、80 模式、能量守恒和 absorption consistency 均通过。

### 2.5 新 profile、V19 快路线和 V18 低峰基线如何取舍

| 同一 original，Full3D p6/h10，MPI1 | V18 | V19 | V20 Y3 |
|---|---:|---:|---:|
| outer steps | 564 | 112 | 112 |
| final A6 | `9.923147187151997e-7` | `9.730817853580463e-7` | `9.730817853580463e-7` independent |
| full tree RSS (B) | `2528460800` | `3965534208` | `2831749120` |
| full tree PSS (B) | `2494237696` | `3931141120` | `2797270016` |
| numerical inventory (B) | `1830284886` | `2031387110` | `2013567110` |
| workspace peak (B) | `396129600` | `423441224` | `423441224` |
| full workflow monotonic (s) | `6609.6613787800015` | `1352.0121227929922` | `1479.1772295139963` |

由实测字段派生：V20 full RSS 比 V19 少 `1133785088 B`、`28.59098%`；比 V18 多 `303288320 B`、`11.99498%`。V20 full monotonic 比 V19 多 `127.1651067210041 s`、约 `9.4056%`。KSP monotonic 为 V20 `1151.635034 s`、V19 `1049.785037 s`，操作数相同；这说明本场总成本变化，但不足以把增加全部归因为某一个内部优化。

V19 已保存的四段 RSS 峰值依次为 preparation/factor-H6-p6-cache/iteration/postprocess=`825548800 / 3965534208 / 2565308416 / 2684796928 B`。这些旧 phase 是从事件边界推断的有限证据，首个 solver checkpoint 不是精确 KSP 起点，后续 setup 中的 JIT 另列 compiler subset；因此只用于定位 V19 的叠峰，不冒称与 V20 四段是严格同窗。V20 新四段为 `2831749120 / 2274676736 / 2278993920 / 2372825088 B`，全过程峰值包含 compiler。

原 p4 的全部 226 次在线 A4 检查通过，最大相对残差为 `5.0455949355168026e-11 <= 1e-10`；V20 full field L2/scaled-curl 为 `1.5860495296312503e-7 / 1.5359268899003175e-7`，均低于 `1e-4`。数学路径 `J M_aug J^H`、FGMRES32、`max_it=2048` 不变。setup 诊断调用 PC 一次，外层调用 112 次，合计 BAL_H/H6 各 113 次；p4 MatSolve 分别为 setup 2 次、外层 224 次。没有附加的 p4 提前释放回代试验。

Y3 父工作流的 conservative-realtime billing 是 `1611.2442379729905 s`，记录的 UTC 相对 monotonic 正差约 `132.068021 s`。该字段用于保守账本，**不能写成 measured runtime，也不能与 `1479.1772295139963 s` 相加**。V19 已有 `1474.858420017083 s` 保守结算、V18 结算和更早的 `43200/600 s` 政策占用、actual unknown 均保留，未清零或返还。工程修复总墙钟时间没有连续测量，保留 unknown；各项测试和检查耗时单列，不伪造总数。

## 3. 测试、失败和证据边界

Y1 最终 focused suite 为 `116 passed / 1 skipped`（skip 是 MPI2/4 专用 fixture），compileall 和 diff-check 通过；ABI 与 frozen-contract 检查通过。Y4 文档合同 `21 passed`，本地表格、fence、链接和 JSON/hash 核对通过；未声称 GitHub 网页视觉核验。正式 run 只有 `1`，replay 为 `0`。此前小范围工程问题如实保留：

1. 后端 fixture 初次读回使用 NumPy 默认 `int64`，在 PETSc `IntType=int32` 下触发安全 cast 错误；修正为 PETSc.IntType 索引后通过。该错误没有启动 PDE。
2. Codex 默认 sandbox 曾因 Open MPI/PMIx listener `errno=1` 无法初始化 singleton；在授权的实际宿主 namespace 完成 qualified ABI/MPI1 检查，故不把 sandbox-only 现象计作 ABI 或数值失败。
3. Y1/Y3 期间的 adapter cache fixture、Y3 事件前缀和 public input schema 小修复均在正式 source `b337…` 前完成并纳入 focused tests；没有因这些问题进行 formal PDE replay。

没有新增 notch、5 nm/0.7 nm、MPI scaling、full repository pytest、Ruff 或 CI 资格。重型 field/matrix/factor/cache/timeline 仍在 ignored artifact root；本轮 tracked 交付只保存轻量 docs/JSON 证据。

## 4. 证据索引和选择性合并

- [V20 详细 memory/lifecycle 结果](outcomes/dual_condensed_memory_v20.md)
- [V20 compact](outcomes/records/dual_condensed_memory_v20_compact.json)
- [V20 decision](outcomes/records/dual_condensed_memory_v20_decision.json)
- [V20 selective manifest](outcomes/selective_merge_manifest_v21.md)
- [增量 run index](outcomes/records/run_index.json)
- independent checker：`benchmarks/artifacts/task39extra/dual_condensed_lowmem_v20/root_engineering/y3_independent.json`
- lifecycle：`benchmarks/artifacts/task39extra/dual_condensed_lowmem_v20/root_engineering/y3_root_lifecycle_review.json`
- saved-array comparison：`benchmarks/artifacts/task39extra/dual_condensed_lowmem_v20/root_engineering/y3_actual_v19_observable_comparison.json`
- Y1 tests/ABI：`benchmarks/artifacts/task39extra/dual_condensed_lowmem_v20/root_engineering/y1_final_focused.log`、`y1_final_abi.json`、`y1_frozen_contract_check.json`

具体采用建议是：在本次固定 p6/h10、MPI1 original 且内存优先时，采用显式 V20 lowmem 配置；保留 V19 时间基线、V18 较低 RSS 基线和普通默认。p4 活跃期间提前释放未实施，是合同允许的后端依赖分支，不阻断本轮收口。若后续另获授权继续降低峰值，当前主要瓶颈是完整 p6 form 编译窗口：树 RSS 为 `2.832 GB`，其中 cc1 为 `1.577 GB`；本轮不再调查 detach 或调 allocator，也不追加计算。该结果不构成短波或任意三维 production 资格。源码实现 SHA 为 `b337d215c3d278d0c1e715f53e28b69f7f0ee3fe`，结果提交到同一 task39extra 分支等待审核，master merge 未批准。
