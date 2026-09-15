# Task39extra Response V22 / Review V21：非可分 h10 通过，h7.5 在全局 trace 因子容量 Gate 前止步

本轮 Z5 只汇总已保存的 A/B 原始记录，没有为了补齐表格重跑 PDE、补造 checker 通过或修改历史账本。单元凝聚先在每个有限元单元内消去内部未知量，再在共享 trace 与端口空间求解；正式流程中 p6 局部缓存是在 p4/H6 setup 之后、outer KSP 之前建立，因此 B 若在 p4 numeric factor 前止步就不会有 p6 local-cache 记录。

## 第一屏结论

| 模型 | 求解通过 | 同离散参考 | 跨网格/迭代趋势 | 资源与时间 | 范围限制 |
|---|---|---|---|---|---|
| O10（只读复用） | 已有 original h10：112 步，A6=`9.730817853580463e-7` | V20 matched original 结果 | 仅作 `B/112` 分母，不新运行 | full tree RSS=`2831749120 B`；monotonic=`1479.1772295139963 s` | 只读基线；不是本轮 fresh PDE |
| A / `Z2_NOTCH_H10` | **PASS**；146 步；worker residual=`9.756517234801763e-7`，independent A6=`9.756517234802322e-7` | **MATCHED_REFERENCE_PASS**；65/65 checker checks | 非可分材料与 O10 的差异可观察，但不等于 h7.5 鲁棒性比值 | tree RSS=`2297982976 B`，PSS=`2267706368 B`，swap=`0 B`；monotonic=`1648.8478095369937 s` | 固定 13.5 nm、p6/h10、MPI1、80 modes；ordinary default 不变 |
| B / `Z3_ORIGINAL_H7P5` | **未完成：容量阻断**；p4 凝聚矩阵已数值装配并留有 CSR identity；symbolic factor 后、numeric factor 前停止；outer solve=`not_run` | `not_run`；无同 h7.5 reference 资格 | `B/112=not_run`；没有 outer iterations，不能计算增长 | 实测 tree RSS peak=`2318045184 B`；PSS/RSS 与 symbolic request 分开；monotonic=`79.78535183999338 s` | 派生分类 `H7P5_RESOURCE_BLOCKED_ON_LAPTOP`；不是数值失败，也不是 OOM kill |
| C / `Z4_NOTCH_H7P5` | `not_run` | `not_run` | `C/A=not_run`，`C/B=not_run` | 未启动，因此没有 C RSS、时间或残差 | 按 B 的适用资源前置条件跳过；没有暗换网格、p 或 PC |

四格表中，O10 是既有、只读复用的 official PASS；本批新启动的场只有 A 产生了 official result，B/C 的 official result 为 `false`。B 的 systemd/launcher 原始分类仍保留为 `WORKER_FAILED`，worker summary 为 `CONTROLLED_STOP/RESOURCE_CONTROLLED_STOP`；`H7P5_RESOURCE_BLOCKED_ON_LAPTOP` 是由明确的 independent live inventory cap 推导的审阅分类，不覆盖父层原始字段。

## 1. 直接回答 Review V21 的问题

1. **非可分模型是否可用？** A 在冻结的非可分 h10 缺口上通过真实 fine Maxwell 残差、匹配参考、场/旋度、80 个端口、能量闭合和吸收一致性 Gate；因此本批 A 的非可分模型可用。它只证明这个冻结 cell-wise 缺口，不证明任意三维几何或连续极限收敛。
2. **h7.5 能否完成？** B 没有完成 h7.5 求解。它在 p4 全局 trace 因子的 symbolic 统计完成后、numeric factor 分配前触发容量政策 Gate，故 h7.5 的 outer solve、p6 局部缓存和最终物理量均 `not_run`。
3. **迭代增长多少？** `G_original=n_B/112`、`G_notch=n_C/n_A`、`G_geometry,h7.5=n_C/n_B` 都不能计算：B 没有 outer iteration，C 没有启动。A 的 146 步相对只读 O10 的 112 步可以观察为不同材料变体的结果，但不替代上述 h7.5 鲁棒性指标。
4. **p4 还是局部缓存主导？** 本次 B 的已证阻断对象是 p4 global trace factor 的 symbolic-after/numeric-before 保守库存请求；p6 local cache 尚未构建，不能声称局部缓存主导，也不能用 A 的 cache 账本外推 B。
5. **下一项研究什么？** 先研究全局 p4 trace 因子的规模控制或经审阅的替代表示；本次 closeout 不实施新 PC、不扫描 p、sigma、restart，不重试 B/C。

## 2. A：非可分 h10 正式结果

A 的 PDE 在 `863ec3bcd7eead867795284db11fc39e758a6f08` 上运行；B 的数值 source、当前文档前置 HEAD 为 `f8d0fbf3da48fd3cbe5cc3a226dbff3feb1d9b48`，Z5 文档写入前的 Z1/base SHA 为 `f9e16c21b936673b5a2dadcf52d2c344e61aabe8`。checker 修复没有重跑 PDE。模型为 13.5 nm、Full3D、p6/h10、252 cells、MPI1、complex128/int32、80 个 DtN modes。A 的 p6/p4 计数是 `173802/53084`，保留 outer rows=`51272`，p4 condensed matrix=`21824×21824`、NNZ=`8184464`。

独立 A6 释放前后都是 `9.756517234802322e-7`，worker final explicit true residual 为 `9.756517234801763e-7`，limit=`1e-6`。field L2/scaled-curl 为 `7.179947262584934e-8 / 6.541279198551157e-8`。官方输出为 `R/T/A/A_volume = 0.3371205735636914 / 0.016288676112780145 / 0.6465907503235284 / 0.6465908230964357`；`abs(R+T+A_volume-1)=7.277290725582475e-8`，`abs(A-A_volume)=7.277290725582475e-8`。A 的 release contract 在 final residual 后释放 `183282224 B` p6 local cache，owner refs cleared，释放后 inventory 为零。

A 的 simultaneous full process-tree RSS/PSS peak 为 `2297982976/2267706368 B`，inventory/workspace peak 为 `2013567110/423441224 B`，swap 为零；这些是不同口径，不相加。全过程 monotonic 为 `1648.8478095369937 s`，KSP monotonic 为 `1394.9292688659916 s`，formal conservative billing 为 `1798.8260412538452 s`；billing 不是 measured runtime，三者不相加。

## 3. B：实际运行到 symbolic factor，未进入 numeric solve

B 使用原始 `input/task39extra/v21_z3_original_h7p5.dat`，几何身份为 `v21_original_h7p5`，轴向 cell counts=`[9,5,22]`，owned cells=`990`；p6 counts=`[667152,199260,445500,80]`，p4 counts=`[201520,84600,106920,80]`。forms、geometry、mesh identity、p4 cell-condensed assembly 和必要的 prepared-form cache 已完成；正式 p6 local cache 要到 p4/H6 setup 后、outer KSP 前才建立，B 在此前停止。

### 3.1 已完成的 p4 矩阵装配与 symbolic 统计

停止前的 p4 global trace factor symbolic 记录为：

| 字段 | symbolic 值 | 含义 |
|---|---:|---|
| rows | `84680` | symbolic 矩阵行数 |
| `nz_used` | `32320342` | 同时是已装配 p4 CSR 的 exact stored-entry NNZ；不是 numeric factor NNZ |
| `nz_allocated` | `45403840` | symbolic 结构预分配 NNZ |
| `INFOG(16)` / `INFOG(17)` | `5060 / 5060 MB` | V11 symbolic estimate fields |
| `INFOG(3)` / `INFOG(20)` | `221594144 / 221594144` | symbolic/predicted factor-entry fields |

p4 凝聚矩阵不是未知项：它已 materialize 为 `84680×84680` complex128 CSR，`nnz=32320342`，CSR/mapping/values hashes 分别为 `857bc8bb5f04b28a55283fb960a2b695e1078983e55ff151687780de5dab8ee0`、`bed2794532a40630632e06637cfda5a7bb52a06a7209824d5344085b6fa2cb1d`、`cf081185f6950ebb2c704e0426e02bb0687ef7ae47faf34115d729c8eb832b34`。这是矩阵内容身份和装配结果，不是 numeric factor 的已分配内存。

装配审计还保留了实际 class/cache 账本：raw tensor class `12`（global unique/sum），oriented Schur class `26`，local retained numeric cache=`24541920 B`，其中 LU=`4863456 B`、recovery=`8626176 B`、RHS projection=`2426112 B`、RHS trace=`8626176 B`；assembly-time raw/oriented temporary components 为 `17280000/15335424 B`，返回后释放。p4 matrix assembly 和这些局部对象均不应被抹成“未构建”。尚未知道的是 numeric factor 的 allocated/used bytes 及其 RSS。

按冻结 V11 公式，numeric-before 的保守请求为：

```text
ceil_MB(max(32 MiB, 2*(5060+1)*1e6 + 8 MiB)) = 10131 MB
numeric request = 10,131,000,000 B
```

触发条件是：

```text
current inventory  1,136,131,046 B
+ conservative request 10,131,000,000 B
= projected inventory 11,267,131,046 B
> inventory cap      6,442,450,944 B
```

这里的 `10,131,000,000 B` 只是“symbolic 已知、numeric factor 尚未分配”阶段的保守政策请求；它不是已经分配的 factor 字节数，不是实测 numeric RSS，也不能表述为“p4 实际占用 10 GB”。p4 CSR 的 exact matrix NNZ 已由独立 hash identity 保存；仍未知的是 numeric factor 的 allocated/used bytes 和实际 factor allocation/RSS。

### 3.2 实测资源和终止身份

B 的连续 watchdog authority 实测 simultaneous process-tree RSS peak=`2318045184 B`；worker resource sample RSS/PSS peak=`2318233600/2287882240 B`，inventory peak=`1136131046 B`，workspace peak=`76405680 B`，swap peak=`0 B`，311 个样本，descendants 已清场。full workflow monotonic=`79.78535183999338 s`，conservative workflow=`85.640744153 s`，time gate 没有超限。这些数字只能描述 B 实际运行到 stop 的资源窗口，不能反推未发生的 numeric factor 峰值。

B 的父层 `run_manifest.json`/`run_summary.json` 原始结果为 `WORKER_FAILED`、leader/worker exit status=`4`；systemd 终态为 `MainPID=0`、`ActiveState=failed`、`SubState=failed`、`Result=exit-code`、`ExecMainStatus=3`。worker summary 和停止审计明确记录 `CONTROLLED_STOP/RESOURCE_CONTROLLED_STOP`、`numeric_factor_started=false`、`outer_ksp_started=false`、`not_oom_kill=true`、`not_numerical_failure=true`。两层身份都保留，不能把父层的 `WORKER_FAILED` 擦掉，也不能把它解释成数值 Gate failure。

因此以下字段都是明确的 `not_run` 或 `unknown`，不是零；其中 p4 CSR/局部 class/cache 已完成，不在未知项中：

| B 字段 | 最终状态 | 原因 |
|---|---|---|
| numeric factor allocation / measured numeric factor memory | `not_run` / `unknown` | symbolic cap 在 numeric 前触发 |
| completed p4 condensed matrix NNZ | `32320342` | exact CSR identity 已保存；不是 factor NNZ |
| numeric factor allocated/used entries / measured factor memory | `unknown` | numeric factor 未启动 |
| p6 local cache | `not_built` | outer solve 前停止 |
| KSP actions、outer iterations、true residual | `not_run` | outer KSP 未启动 |
| R/T/A、`A_volume`、80-mode outputs | `not_run` | 没有终态场 |
| B checker PASS | `not_run` | checker 缺少终态 residual/physical fields；不伪造通过 |

### 3.3 prepared-form cache、几何和模型身份

B 的 11 个必要 prepared forms 全部命中（`11/0`）；只读 O10 为 `10/1`，唯一 miss 是 `p6_condensation`。对应 form-preparation event time 为 O10=`56.7998199990252 s`、A=`0.017299229046329856 s`、B=`0.02241471700835973 s`。A/B 都没有 compiler descendant sample；这些是 form event 账本，不是完整 setup/workflow 时间，也不足以宣称 warm cache 带来了 RSS 下降。

冻结几何计划中的 notch union 是 `x=[16.5,33.5] nm`、`y=[0,8.333333333333334] nm`、`z=[40,80] nm`，来自 8 个原始几何实体；不能用历史 center-origin 文字对它再平移。B/C 的 h7.5 mesh 是每轴 `[9,5,22]`、owned cells=`990`，其中包含保持外边界对齐的 neutral alignment planes；它不是旧的 720-cell 数字，也不是把 h10 cell count 乘一个统一比例。

本批正式运行身份仍分开绑定：Z1 base=`f9e16c21b936673b5a2dadcf52d2c344e61aabe8`，B 的 formal source/current pre-Z5 HEAD=`f8d0fbf3da48fd3cbe5cc3a226dbff3feb1d9b48`，A 的 formal solver source=`863ec3bcd7eead867795284db11fc39e758a6f08`。这份 response 不把尚未提交的 Z5 文档变更冒充新的最终 source SHA。

## 4. O10/A 单步与 setup 口径

为回答单步成本，只比较已测 O10/A；KSP 平均含检查/保存，不能称 pure-PC cost。

| 指标 | O10 只读复用 | A / Z2 | 说明 |
|---|---:|---:|---|
| KSP monotonic / outer steps | `1151.6350344140083 / 112 = 10.282455664410788 s/step` | `1394.9292688659916 / 146 = 9.55431006072597 s/step` | 含检查/保存的 KSP 平均 |
| BAL_H total / calls | `1067.2167201989505 / 113 = 9.444395753973014 s/call` | `1292.2156548238418 / 147 = 8.790582685876474 s/call` | 含 setup 一次 |
| p4 setup / symbolic / numeric (s) | `37.73026903902064 / 0.36884564999490976 / 23.69310698399204` | `34.0570986730163 / 0.15249989298172295 / 22.365533358009998` | 分阶段 measured fields |
| frozen symbolic package request | `1953 MB` | `1953 MB` | request policy，不是已分配内存 |
| B symbolic package request | — | `10131 MB` | 预测 request，不能与 O10/A 已分配内存混比 |

这些数字只用于已完成 O10/A 的口径对照；B/C 仍不填迭代增长。

## 5. C 与跨模型比值

C 没有启动，因为 B 的适用 h7.5 resource prerequisite 在 outer solve 前失败。没有 C 的 process tree、residual、physical output、reference comparison 或迭代数；C 不被写成数值失败。

按 Review V21 的预先定义，`B/112`、`C/A` 和 `C/B` 均登记为 `not_run`。O10 的 112 步是只读分母；A 的 146 步只说明该非可分 h10 变体在当前方法下完成，并不能填充 B 的步数，也不能用 A 的 RSS 线性预测 B 的 h7.5 numeric 内存。

## 6. checker 修复、测试和历史边界

A 的原始 failed checker copy 未覆盖，且只保留两项失败：`release_timeline` 与 `summary_schema`。前者是 V21 p6 label 被旧 V20 helper 解读的兼容问题；后者是历史 V14 `record.update` 覆盖了 V21 native schema。修复后的 checker 对 A 使用精确 source/stage/profile/schema 范围内的 hash-bound compatibility，记录 `native_pass=false`，没有把 raw V14 schema 改名，也没有改写 raw events。

最终 checker/recheck 为 `65/65`；原始 failed copy SHA256=`93a7a7663ad3df38a5cea75449d550d0cdcd29ee613feef54e42b7d0718d8f94`，当前 checker source SHA256=`acbad332f35ccf3302fb027335b93ed399941c2a937012c86f2cc51f3beabcb6`，current/recheck checker SHA256=`149747de773e9cded62898195cc4b1e58d0714cf691e5b7b7c20316619590bce`。A 的更正路径修复测试是 **49 passed**；Z1 formal 前工程资格测试是 **99 passed**。这三个数字属于不同集合，不能相加成一个“总通过数”；没有因为文档 closeout 重跑昂贵 PDE。

所有旧失败、历史 unknown、V18/V19 policy debit、外部中断记录和缺失终态均保留。B 的停止 summary、worker log、run manifest、run summary 和资源审计只读保存；没有使用 checker 把 B 变成通过。

## 7. 最终决策与证据入口

- A：`MATCHED_REFERENCE_PASS`，非可分 h10 在本批可用。
- B：`H7P5_RESOURCE_BLOCKED_ON_LAPTOP`，p4 全局 trace factor 的 symbolic-capacity policy 阻断；不称 numerical failure。
- C：`not_run_by_review_condition`。
- ordinary default：unchanged；master merge：`NOT_APPROVED`。
- 下一研究对象：全局 trace factor 的规模/替代方案；本阶段不实现新 PC、不增加新的 heavy case。

机器可读与原始证据：

- [V21 aggregate compact](outcomes/records/dual_condensed_robustness_v21_compact.json)
- [V21 decision](outcomes/records/dual_condensed_robustness_v21_decision.json)
- [V21 detailed outcome](outcomes/dual_condensed_robustness_v21.md)
- [frozen geometry/mesh plan](outcomes/records/v21_frozen_geometry_mesh_plan.json)
- [incremental run index](outcomes/records/run_index.json)
- B stop audit：`benchmarks/artifacts/task39extra/dual_condensed_robustness_v21/root_engineering/z3_root_stop_audit.json`
- B compact：`benchmarks/artifacts/task39extra/dual_condensed_robustness_v21/root_engineering/z3_resource_stop_compact.json`
- B raw root：`results/euv_grazing1_phi0/task39extra_v21_z3_original_h7p5__full3d_iterative__mpi1__Mna/20260915T065308.474983Z`
- A original failed checker：`results/euv_grazing1_phi0/task39extra_v21_z2_notch_h10__full3d_iterative__mpi1__Mna/20260915T053102.148718Z/v21_checker_result.original_failed.json`
- Z5 frozen authority check：`benchmarks/artifacts/task39extra/dual_condensed_robustness_v21/root_engineering/z5_root_frozen_authority_check.json`；SHA256=`880534b2c2bb72939669ef098cb809510b666930101a74a0a1312905e0b3a5b3`；50 frozen files、26 old profiles、changed=`0`、passed=`true`
- Z5 saved cost comparison：`benchmarks/artifacts/task39extra/dual_condensed_robustness_v21/root_engineering/z5_root_saved_cost_comparison.json`；SHA256=`87975d656484936f6b3ca1ca067bd539fd6a752a91a98acb8816fd2e6fe1d577`

本轮 tracked Z5 文档状态：`LOCAL_REVIEWED_REMOTE_PUSH_PENDING_AUTH`。主控已完成执行把关；提交 SHA 以最终回复为准。远端推送仍因 GitHub 凭据未缓存而待完成，本响应不表示 master merge approval。
