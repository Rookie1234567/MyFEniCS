# Task041 V4：共同布局响应等价记录

## C2d 最新收口：既有 C2 raw 的离线修正视图

这里的 `PASS` 是对既有 C2 raw artifacts 的离线 checker 复核，不是重新启动服务或重新
计算。原始 C2 summary 因合并 bug 将 `apply_count` 写成 `8`，虽然 raw 中已经有 8 对、
16 个主响应；把该字段改为 raw 重算的 `16` 后，原 checker 的全部身份、layout、lifecycle、
残差和响应条件通过。原 service 终态仍为 `PAIRING_SETUP_FAILURE` / `service_boundary_failure`
（systemd exit status `3`），原 summary、run/finalizer/journal 和 raw 不改写。
通俗地说，`e_x` 是相同 RHS 下两次解的相对差，`e_A` 是把解差代回同一个原方程后的相对差。

| 项目 | 实际值 |
|---|---|
| 离线状态 | `COMMON_LAYOUT_EQUIVALENCE_PASS_OFFLINE_DERIVED`；不是新 service PASS |
| 计数 | 8 对、16 主响应；每侧 4 对；16 response manifests/128 rank shards，16 diagnostic manifests/128 rank shards |
| 响应最大值 | `e_x=3.0316012438358734e-9`，`e_A=8.229180550916894e-9`；阈值均 `1e-8` |
| residual 最大值 | bottom legacy/optimized `0.009208186034505522/0.009208186034505515`；top `0.009453705395968726/0.009453705395971615` |
| 原数值门 | 每项 reason>0、explicit true residual≤`1e-2`；保留真实 iterations 和 residual，tiny RHS 不使用绝对 floor |
| C2 C3 / P / PH / PC | 原 `consumer_summary.setup.admission_audit.sides.*.balanced_pc` 的 P/PH relative 均为 `0`；PC relative bottom `6.149584203535856e-13`、top `2.2220413770924415e-13`（门 `1e-8`），实际 PC call count bottom `266`、top `298` |
| 独立基本动作证据 | C1b/R2e tiny-FE serial/MPI2 的 P、PH 全局 relative 也均为 `0`；不替代 C2 response Gate |
| 组件诊断 wall | baseline/optimized `1981.6339287383016/1454.4546840919647 s`，减少 `26.6033%`；不代表完整 cold/service 提速 |
| 全树 RSS | C2 raw 峰 `51501744128 B`，cap `53221163008 B`；不等于双侧 full 资格 |
| C2 service wall / 收尾 | public nested/total `6121.790274919942/6124.439315116033 s`；service phase `6125.609746061964 s`、parent-from-unit `6125.770416472 s`、finalizer `6126.252856925 s`；来源层级分开，cgroup、post-hash、ledger 完成，原 service exit3 保留 |
| 账本 | C2c `7.820470533 s` 加本次文档 JSON/diff 检查 `0.066910437 s`；used `17762.27669256989 s`，shared remaining `3837.723307430111 s`，SHA `e5803851257eabd643be7048e81fae2c8d5e9957c4309c7f433b75ddd3805e27` |

逐对记录、原/派生 summary SHA、checker 结果及命令日志见
[C2c offline index](../../../results/task041_side_balh_component_audit/c2c_validation_20260916_5b57375d/c2c_offline_review_index.json)
（SHA `db0f4a1d247f6a75002981db927241d162375a82b425f9c0fe9acce2e3940aca`）。这次离线
结果只闭合同一次 C2 side layout；跨 fresh-run 的 physical-row identity 仍不补，旧
`PAIRING_IDENTITY_UNPROVEN` 和 S1f 双侧 `process_tree_rss_limit` 负证据继续有效。

完成通知未通过既有 RPC 唤醒主控属于通知事故；本次 sampler 连续，不能解释为资源采样断档。

### 八对逐项结果

下表是从 C2c offline index 复制的精简 raw-derived 字段，直接随本 tracked 报告可审阅；
完整 rank shards 和诊断仍由 compact/index 按 hash 绑定。

| ordinal | side | formal column | order | legacy reason / iters / true residual | optimized reason / iters / true residual | e_x | e_A |
|---:|---|---:|---|---|---|---:|---:|
| 0 | bottom | 207 | legacy → optimized | 2 / 17 / 0.008369286568900507 | 2 / 17 / 0.008369286568899832 | 4.11545611714438e-13 | 5.530436429171848e-13 |
| 1 | bottom | 15 | optimized → legacy | 2 / 49 / 0.008589298457491311 | 2 / 49 / 0.008589298457523386 | 7.228248127071995e-13 | 1.6200654657740586e-12 |
| 2 | bottom | 671 | legacy → optimized | 2 / 17 / 0.009208186034505522 | 2 / 17 / 0.009208186034505515 | 3.553309460417907e-14 | 1.153703633346392e-13 |
| 3 | bottom | 493 | optimized → legacy | 2 / 49 / 0.00884167581121773 | 2 / 49 / 0.008841675811138606 | 4.8535924021102015e-12 | 1.056868109377526e-11 |
| 4 | top | 310 | legacy → optimized | 2 / 17 / 0.009202848153253724 | 2 / 17 / 0.009202848153253935 | 1.251437720408365e-13 | 8.151842280570904e-14 |
| 5 | top | 12 | optimized → legacy | 2 / 57 / 0.009387047164137696 | 2 / 57 / 0.009387047164154868 | 5.849845044680001e-10 | 1.593783344066858e-09 |
| 6 | top | 666 | legacy → optimized | 2 / 17 / 0.009453705395968726 | 2 / 17 / 0.009453705395971615 | 4.020263106622586e-13 | 5.371995396204957e-13 |
| 7 | top | 493 | optimized → legacy | 2 / 57 / 0.009387047156722884 | 2 / 57 / 0.009387047156698324 | 3.0316012438358734e-09 | 8.229180550916894e-09 |

## V4-A0 历史状态（保留）

以下 A0 段是历史准备记录；本记录最新状态见上面的 C2d 段。本记录原先是 V4-A0 的准备性
compact 说明，不是一次计算结果。宿主在启动前仍有受保护的
Full3D heavy 作业，故状态为 `BLOCKED_BY_ACTIVE_HEAVY_JOB`；C1 尚未实现，C1–C3 和
16 项主响应均 `not_run`。

| 维度 | V4 记录 |
|---|---|
| profile / scope | `task041_schur_speed_v2` / `representative_rhs` |
| comparison mode | `common_layout_equivalence`（显式 opt-in，尚未实现） |
| side schedule | `sequential_component` |
| 主响应 | `0/16`；expected `16` |
| 响应配对 | `0/8`；expected `8` |
| layout、P、PH、PC、response 等价 | `not_run` |
| new RSS / speed | `not_measured` |
| runroot / unit | `null`；本轮没有启动，不能填假路径 |

后续 C2/C3 若获准，资源固定为 MPI8、CPU `0–7`、每 rank 一个数学线程和同一严格 RSS
cap；C1 仅预计秒至分钟级，C2/C3 不在本记录中给出新时长预测。旧 R2 wall 仅作历史
排程参考，不冒充 V4 预计或实测。

## 比较合同

两种实现必须在同一侧、同一 layout epoch、同一 owned RHS 下运行。mesh、MPC、凝聚映射、
原始 global action/RHS 和 p4 factor 只准备一次；bottom 完成四项后释放并确认真实
diagnostics 的 p4/KSP 为零，才允许构造 top。这样可以把差异归因于 owner transfer 和
伴随向量实现，而不把两个运行的编号差异误当成 response 差异。

固定 entry 顺序为：

| ordinal | side | audit index → formal column |
|---:|---|---|
| 0 | bottom / positive | 227 → 207 |
| 1 | bottom / positive | 35 → 15 |
| 2 | bottom / negative | 691 → 671 |
| 3 | bottom / negative | 513 → 493 |
| 4 | top / positive | 330 → 310 |
| 5 | top / positive | 32 → 12 |
| 6 | top / negative | 686 → 666 |
| 7 | top / negative | 513 → 493 |

偶数 ordinal 先运行 legacy，奇数 ordinal 先运行 optimized；两者均 zero-start，不使用
KSP recycle 或 warm initial guess。每项记录原始 audit、reason、iteration、explicit
residual、owned range/array hash 和 identity。不得按数值排序、相位拟合、跨运行重排或
引入新 canonicalization。

## Gate 与停止条件

保留原有 action/transfer、duplicate-row、ghost/MPC、P/PH、p4/refinement、BAL_H 和 KSP
检查。阈值为 action/transfer `1e-11`、p4 residual `1e-10`、BAL_H `1e-8`、每响应
explicit residual `1e-2` 且 reason>0；同布局响应的诊断字段为
`threshold_e_x/threshold_e_A=1e-8`，实际值为 `null/null`，
不替代原线性门或凭空建立近似 KSP 的 `1e-11` 硬门。

资源仍由现有 service/supervisor 负责：process-tree RSS cap `53221163008 B`、90% warning、
reserve/cgroup 安全线、job/global swap 与 time-stop 全部保留。出现资源、身份、数值或
生命周期 Gate 时保留负证据并停止，不自动重试；本次启动前 heavy Gate 已足以阻止 C1。

## 历史边界

旧 R2/R2g 的分侧 apply `1680.27495998214 → 1258.8479048048612 s` 和 full-tree RSS
`51975606272 → 51796770816 B` 是另一组跨 fresh-run 历史，不能与 C2 common-layout
组件 wall 同名或混列。跨 fresh run 的 132300 condensed rows 缺少稳定物理 row key，
所以正式状态仍为 `PAIRING_IDENTITY_UNPROVEN`；旧 S1f `53331742720 B > 53221163008 B`
的双侧资源受控停止仍是独立 blocker。

离线内存表使用已有 `r2b_analysis_v2.json` 和旧 compact 的库存/marker 括号；它不是
新的采样，也不是双侧资格。`inventory` 是 rank-local exposed payload，RSS 是约 0.3 s
级全树采样在 marker 前后的括号，PSS/USS 才是稀疏诊断；不同阶段的数值不相加，native
workspace 和 allocator retention 不推测。

| 范围 | 已有可核对事实 | 不能推出的内容 |
|---|---|---|
| public / borrowed | p6 mesh、FE/MPC、global action/RHS、physical inputs 由 side system 借用；已暴露的 action/input payload 是 rank-local、非加和 | 全树 RSS 的组成或 native workspace 字节 |
| bottom 保留与释放 | `before_release` bracket `37383737344 B`；`bottom_after_release` bracket `32090693632 B`；owned p4/KSP diagnostics 归零，借用对象仍在 | 同刻完全返还、allocator 是否归还给 OS |
| top 构造 / 工作区 | top p4 factor bracket `51259228160/51315433472 B`；transfer/H6 后续 brackets 单列 | 各构造对象的完整 native/LU/MUMPS 字节 |
| 诊断 scratch | C2 raw 保存 delta/A_delta/residual pair 的 packet 与有限短数组记录；没有把 scratch 复制为常驻场 | scratch 的完整 native payload、瞬时峰值是否落在采样间隔内 |
| 同时驻留增量 | C2 是 bottom→release→top，未同时保留两侧 adapter；同一时刻双侧增量 `unknown` | 不能由分侧 peak 或 factor count 预测 full-dual 峰 |

上述表的来源与更细字段见 [C2c offline index](../../../results/task041_side_balh_component_audit/c2c_validation_20260916_5b57375d/c2c_offline_review_index.json)
及 [Response V5 历史内存表](../response_v5.md#31-旧-r2b-构造内存摘录非-v4-测量)。
旧 R2 baseline/optimized 全树峰的 cap 余量仍为 `1245556736/1424392192 B`；这是 R2
历史值，不是 C2 的新预算或资格结论。

本轮最终只执行新 compact 的 `python -m json.tool`（输出丢弃）和 `git diff --check`，
两项均 exit `0`；父侧 `CLOCK_MONOTONIC` wall 为 `0.063355920 s`。记录见
[`v4a0_final_json_diff_check.json`](../../../results/task041_side_balh_component_audit/v4a0_preparation_20260916_b5d0a39e/v4a0_final_json_diff_check.json)，
并已在唯一 V2 ledger 中一次追加本轮可追溯静态检查成本；账本当前
`11145.708812196894 s`，shared remaining `10454.291187803106 s`，SHA256
`c1c0ef6ab626f3c53b9d252abc43037b341ec73f53cdc93b86fc8626bc338dad`。
