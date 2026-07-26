# Task035c 结果总结：Hybrid 逐通道与高阶内存闭合

> `measured` 表示正式运行直接测得，`derived` 表示由同一批实测数值计算，
> `not_run` 表示按范围或停止规则没有运行。峰值内存统一优先使用同一时刻
> live MPI worker/process-tree RSS；不是各 rank 不同时刻峰值的简单相加。

## 1. 最终状态与适用范围

| 项目 | 最终值 | 数据身份 | 范围 / baseline | 证据 |
|---|---|---|---|---|
| formal classification | `HYBRID_CHANNEL_AND_MEMORY_CLOSURE_SUCCESS` | derived decision | Review V4 mandatory 物理、15%内存、25% preferred 与1.35×总时间 Gate | Case096 |
| numerical source | `244b62e1fb4f299a468363cf90a2dd548dc34ff6` | measured Git identity | clean branch source；六条 MPI8 authority 相同 | raw records |
| physical model | fixed rectangular block grating，13.5 nm，S偏振，10°掠入射 | measured input | Task034/035b frozen geometry | task / Case096 |
| high-order model | structured hexa `p6/h10`，`(6,3,14)`、252 cells | measured input | best available global-p discrete reference，不是 continuum truth | Case095/096 |
| MPI8 six paths | 6/6 完成并通过数值与资源采样 | measured | Full3D standard/static；Hybrid standard/static M120/M160 | Case096 |
| significant channels | 12/12 powers + 12/12 boundary-plane complex amplitudes | measured + independent recomputation | reference-v1 tolerance 未放宽 | channel checker |
| static Hybrid memory | M120 `-31.8919%`；M160 `-29.4977%` | derived from measured RSS | 同 p/h/M/MPI/输出合同的 standard baseline | §5 |
| MPI8 PSS/USS | M120 PSS `-38.8828%`、USS `-40.3146%`；M160 PSS `-35.8083%`、USS `-37.1575%` | derived from original simultaneous per-rank smaps samples | 全 8 rank 同时可读；不是 RSS 推算；不替代正式 RSS Gate | PSS/USS ledger |
| 50% user target | not achieved | measured negative | M120/M160 同路径比较 | §6 |
| p3/h7.5 | `out_of_scope / not_run` | not_run | 用户和修订 Review V4 明确禁止 | task |
| M240 | `not_run_no_M_signal` | not_run | M120→M160 已在 `1e-9` 以下闭合 | §4 |
| ordinary default | unchanged | measured configuration | `standard_full` | code/tests |

这里的“闭合成功”有明确限定：Task035c 正式门槛要求 static Hybrid 峰值至少
下降 15%，优选 25%；M120/M160 都超过这两个门槛。用户进一步希望下降 50%
以上，这一更强研究目标没有达到，不能把 `31.89%` 写成“已经接近理论最低内存”。

### 1.1 资格化范围

正式通过只覆盖：

```text
fixed rectangular block grating
structured tensor-product mesh
axis-aligned first-order affine hexahedra
uniform z segmentation in the modal middle region
one well-defined axial h for the scalar CG(p) chain
supported axial degree p1-p6
complex128
Floquet periodicity
sparse auxiliary DtN
direct standard/static Full3D and Hybrid
```

以下范围没有被 Task035c 证明：nonuniform z、local-h/hanging-node hexa、
curved/distorted hexa、高阶曲面 geometry mapping、tetra static condensation、
hexa/tetra/prism/pyramid mixed mesh、sloped/rounded/rough/defect geometry、
任意 irregular geometry 和 production automatic hp adaptivity。离散
`full3d_uniform_cg` phase 与 `scalar_cg_discrete_derivative` traction 对
这些输入必须 fail closed，不能静默使用 ordinary continuous symbol。

## 2. 方法与根因

### 2.1 为什么旧 Hybrid 的弱通道会错

Full3D 在中间规则层的 z 方向仍是一个有限元离散链。它传播的并非连续解析波
`exp(i beta L)`，而是 scalar CG(p) 链对应的离散相位；端点磁场/牵引也由同一
离散链的动态刚度决定。旧 Hybrid 只把连续 QEP 的 `beta` 用于相位和 traction，
总 R/T/A 对这种小差异不敏感，但 `1e-8` 附近弱衍射级的相位和功率会被放大。

| p2/h5 判别 | power / amplitude | 解释 | 状态 |
|---|---:|---|---|
| modal trace rank | `320/320` | modal basis 已覆盖所需接口子空间 | pass |
| M120→M160 | 原错误几乎不变 | 不是 M 截断不足 | discriminator pass |
| 只换 scalar-CG 离散相位 | `4/12 + 4/12` | 相位是必要条件，但仍缺端点 traction | controlled negative |
| 离散相位 + 离散端点 traction | M120/M160 均 `12/12 + 12/12` | 与 Full3D 同一 z 离散符号 | pass |

修复后的两个 opt-in 端口为：

```text
internal_propagation_model = full3d_uniform_cg
internal_traction_model = scalar_cg_discrete_derivative
```

它们只对已资格化的 fixed rectangular、均匀 z 层和支持的 degree 开放；其他
网格必须 fail closed。详细推导和 p2/h5 数值见
[`p2_h5_channel_root_cause.md`](p2_h5_channel_root_cause.md)。

### 2.2 static condensation 改变了什么

静态凝聚在每个三维有限元单元内精确解出 cell-interior 自由度与 trace 的关系，
只组装 trace Schur 矩阵。它没有把内部系数设成零，也没有删除物理场；完整场在
求解后逐块恢复，并用 full-operator 和 eliminated-interior residual 审计。

Task035c 另证明 p6 横截面 Floquet 约束、周期 orientation 和 trace 投影支持
p1–p6。roundoff audit 分开处理：

- periodic slave 必须满足严格 absolute `1e-12`；
- 理论为零的 cell-interior 投影允许与全局 active scale 成比例的浮点舍入；
- 非有限值、真正 slave 泄漏或超过比例上限仍 fail closed。

## 3. p6/h10 MPI8 六路径统一结果

下表中 Hybrid rows/NNZ/factor 为上下两个 local FEM block 合计；`2M` 个内部
模态振幅另计入 total rows。Full3D 的 rows 含 80 个外部 DtN 辅助量。

| 路径 | active rows | matrix NNZ | factor NNZ | true residual | R / T / Aclosure | peak GiB | total s | 数据身份 |
|---|---:|---:|---:|---:|---|---:|---:|---|
| Full3D standard | 173,882 | 210,353,168 | 438,050,956 | `1.709e-11` | `0.000762881475133 / 0.602701633983338 / 0.396535484541529` | 34.041210 | 2581.549788 | measured MPI8 |
| Full3D static | 51,272 | 41,989,040 | 212,343,992 | `3.092e-11` | `0.000762881475126 / 0.602701633985538 / 0.396535484539337` | 14.721756 | 260.736180 | measured MPI8 |
| Hybrid standard M120 | 52,292 | 60,434,236 | 141,010,528 | `4.858e-12` | `0.000762881475147 / 0.602701633983422 / 0.396535484541431` | 11.076893 | 942.026047 | measured MPI8 |
| Hybrid static M120 | 17,168 | 12,313,232 | 45,293,792 | `2.079e-12` | `0.000762881475142 / 0.602701633984217 / 0.396535484540641` | 7.544262 | 322.781788 | measured MPI8 |
| Hybrid standard M160 | 52,372 | 60,434,236 | 141,010,528 | `7.878e-12` | `0.000762881475143 / 0.602701633983403 / 0.396535484541454` | 11.247025 | 1014.706182 | measured MPI8 |
| Hybrid static M160 | 17,248 | 12,313,232 | 45,293,792 | `2.368e-12` | `0.000762881475138 / 0.602701633984275 / 0.396535484540587` | 7.929413 | 393.840814 | measured MPI8 |

六条路径均为零 swap。Hybrid 的独立 `A_volume` 为：

| Hybrid path | Avolume | `Aclosure-Avolume` 量级 | field / residual Gate |
|---|---:|---:|---|
| standard M120 | `0.396535484696121` | `1.55e-10` | all pass |
| static M120 | `0.396535484696529` | `1.56e-10` | all pass |
| standard M160 | `0.396535484687084` | `1.46e-10` | all pass |
| static M160 | `0.396535484687489` | `1.47e-10` | all pass |

这些差值小于正式 `1e-5` volume-energy Gate。Full3D/Hybrid 的
best-available discrete reference 仍不能替代独立 continuum convergence。

## 4. 12 个显著通道与复振幅

reference v1 使用 `p6/h10` Full3D standard 的 physical boundary plane
振幅。功率是 S/P 两个传播偏振的合计；下表复振幅列出主 S 分量的
`outgoing_amplitude_at_boundary`，不从功率开方反推。

| channel | reference power | boundary-plane complex amplitude |
|---|---:|---|
| `R(0,0)` / `r(0,0)` | `7.537612200699e-4` | `-2.525230435366e-2 + 1.077415170210e-2 i` |
| `R(-1,0)` / `r(-1,0)` | `6.669309653233e-6` | `-1.032707715867e-3 + 7.678339216602e-4 i` |
| `R(-2,0)` / `r(-2,0)` | `1.477690850611e-6` | `4.942316169501e-4 - 2.055157697050e-4 i` |
| `R(-4,0)` / `r(-4,0)` | `2.675239609494e-7` | `2.102233361056e-4 - 4.973043617933e-5 i` |
| `R(-5,0)` / `r(-5,0)` | `7.457300541253e-8` | `-9.817807924523e-5 - 6.535503243357e-5 i` |
| `R(-7,0)` / `r(-7,0)` | `6.263542421918e-7` | `-5.052091112350e-4 - 2.608886169331e-5 i` |
| `T(0,0)` / `t(0,0)` | `6.026738723442e-1` | `6.313787033458e-1 + 4.730209810385e-1 i` |
| `T(-1,0)` / `t(-1,0)` | `2.178167398397e-5` | `2.091013385254e-3 - 1.023379862752e-3 i` |
| `T(-2,0)` / `t(-2,0)` | `2.959841394773e-6` | `-6.970027805317e-4 + 2.979420806665e-4 i` |
| `T(-4,0)` / `t(-4,0)` | `4.372888971080e-7` | `-2.621322074939e-4 + 8.743226905009e-5 i` |
| `T(-5,0)` / `t(-5,0)` | `2.119208256123e-7` | `1.340326965591e-4 + 1.470057842605e-4 i` |
| `T(-7,0)` / `t(-7,0)` | `2.362010448510e-6` | `9.812210506877e-4 - 8.723749952673e-5 i` |

| 比较 | power pass | amplitude pass | 最大相对差 | 结论 |
|---|---:|---:|---|---|
| Full3D standard ↔ Full3D static | 12/12 | 12/12 | `3.404e-10 / 4.158e-10` | exact static equivalence |
| Full3D ↔ Hybrid standard M120 | 12/12 | 12/12 | `<9.81e-10 / <5.22e-10` | pass |
| Full3D ↔ Hybrid static M120 | 12/12 | 12/12 | `<7.98e-10 / <6.64e-10` | pass |
| Hybrid standard ↔ static M120 | 12/12 | 12/12 | `2.539e-10 / 3.632e-10` | exact static equivalence |
| Full3D ↔ Hybrid standard M160 | 12/12 | 12/12 | `<8.61e-10 / <4.45e-10` | pass |
| Full3D ↔ Hybrid static M160 | 12/12 | 12/12 | `<8.42e-10 / <6.43e-10` | pass |
| Hybrid standard ↔ static M160 | 12/12 | 12/12 | `5.077e-10 / 3.827e-10` | exact static equivalence |
| static Hybrid M120 ↔ M160 | 12/12 | 12/12 | `1.866e-10 / 1.611e-10` | M funnel converged；不运行 M240 |

最大差由 compact checker 从原始 80 个 DtN order 重算，reference-v1
`1e-3` relative tolerance 与 `1e-8` significance floor 均未改变。

## 5. 内存、矩阵和时间 Gate

### 5.1 static 相对 standard

| 对照 | rows reduction | matrix NNZ reduction | factor NNZ reduction | peak reduction | modal time ratio | total time ratio | 正式判定 |
|---|---:|---:|---:|---:|---:|---:|---|
| Full3D | 70.5133% | 80.0388% | 51.5253% | 56.7531% | n/a | 0.101000× | engineering success |
| Hybrid M120 | 67.1690% | 79.6254% | 67.8791% | 31.8919% | 1.075654× | 0.342646× | mandatory/preferred pass；50% fail |
| Hybrid M160 | 67.0664% | 79.6254% | 67.8791% | 29.4977% | 1.076308× | 0.388133× | mandatory/preferred pass；50% fail |

用户取消了 modal time `<=1.25×` 硬限制；上表只报告实测比值。即便沿用旧
1.25×标准，两点也仍通过。总时间都远低于 `1.35×` 上限。

### 5.2 PSS/USS historical backfill

原始六路径 MPI8 timeline 含逐 rank `/proc/<pid>/smaps_rollup` 字段。compact
生成器逐文件验证 timeline 和 watchdog SHA，只接受 rank 0–7 在同一时刻全部
可读的样本；启动、退出或部分可读样本不参与峰值。各指标独立取自身时间序列
最大值，因此 PSS、USS 与正式 watchdog RSS peak 不要求出现在同一时刻。

| path | qualified samples | PSS peak GiB | USS peak GiB | smaps swap |
|---|---:|---:|---:|---|
| Full3D standard | 7,617 | 32.298626 | 32.047173 | 0 |
| Full3D static | 818 | 12.806003 | 12.602608 | 0 |
| Hybrid standard M120 | 2,990 | 9.440656 | 9.200600 | 0 |
| Hybrid static M120 | 1,071 | 5.769862 | 5.491413 | 0 |
| Hybrid standard M160 | 3,215 | 9.610866 | 9.370529 | 0 |
| Hybrid static M160 | 1,294 | 6.169376 | 5.888676 | 0 |

Full3D standard→static 的 PSS/USS 降幅为 `60.3512%/60.6748%`；Hybrid M120
为 `38.8828%/40.3146%`，M160 为 `35.8083%/37.1575%`。这些值来自原始
smaps 样本，不是由 RSS 反推，也没有重跑 PDE。正式 Task035c 相对内存 Gate
仍使用同一原 campaign 的 simultaneous process-tree/live-worker RSS，以保持
与已冻结 resource contract 一致。证据见
[`p6_h10_mpi8_pss_uss_ledger_v1.json`](../../../benchmarks/cases/096_hybrid_channel_memory_closure/records/p6_h10_mpi8_pss_uss_ledger_v1.json)。

### 5.3 为什么矩阵缩小约80%，峰值只降约30%

M120 static 的 `interface_projection_and_coupling` stage peak 为
`5894.387 MiB = 5.756237 GiB`，低于最终 `7.544262 GiB`。峰值随后出现在：

| M120 static stage | simultaneous worker RSS | 直观含义 |
|---|---:|---|
| interface projection/coupling | 5.756237 GiB | 模态、接口投影和局部系统正在耦合 |
| local factor / Schur | 6.668–6.817 GiB | 上下局部 MUMPS factor 与 Schur contribution 共存 |
| field recovery / trace oracle | 7.199–7.203 GiB | 因子、恢复缓存和采样对象重叠 |
| middle-plane reconstruction | 7.421211 GiB | 中间场采样又增加临时对象 |
| record and release | 7.544262 GiB | 序列化/收尾时仍有 native factor 与后处理对象共驻 |

所以 50%缺口不在 modal Schur 小矩阵本身，也不说明静态凝聚“没有价值”。
真正问题是 local factors、QEP/modes、field recovery、middle reconstruction
和 record serialization 的生命周期仍重叠。后续若要从约32%推进到50%，应先：

1. 在生成 compact observable 后立即销毁 local factor/native solver objects；
2. 把 middle reconstruction 改为分平面/分 mode streaming；
3. 避免 record builder 同时持有完整嵌套 Python dict 和大 native payload；
4. 在现有 per-rank PSS/USS ledger 上增加 native-object create/release 事件，
   再按峰值时刻逐个缩短生命周期。

M120 的 50%目标要求峰值不超过 `5.538446 GiB`。当前 coupling stage 已为
`5.756237 GiB`，local factor/Schur stage 又达到 `6.817 GiB`；因此只在
postprocess 或 JSON 写出前增加 `del/gc/destroy`，即使完全消除后处理增量，
也不可能达到50%。需要同时重构 interface projection/coupling 的分块驻留和
上下 local factor/Schur 的顺序生命周期。这会改变正式资源路径，并要求
Full3D standard/static 与 Hybrid standard/static M120/M160 在新同一源码上
重新资格化。本轮没有用一次低风险清理名义启动整组六路径重跑。

## 6. M120 选择与 M160 停止

| static Hybrid | peak | coupling | total | 12-channel physics | 决定 |
|---|---:|---:|---:|---|---|
| M120 | 7.544262 GiB | 37.340495 s | 322.781788 s | 12/12 + 12/12 | selected |
| M160 | 7.929413 GiB | 51.869917 s | 393.840814 s | 12/12 + 12/12 | not selected |
| M160 / M120 change | +5.1052% | +38.9106% | +22.0146% | 无可测物理收益 | stop；no M240 |

## 7. MPI rank 研究与受控负结果

Review V4 要求从 MPI1/2/4/8 选择合理两三个点，而不是默认 MPI8 最省内存。
本任务运行 MPI1 和 MPI2 后出现两个相互独立的 Gate 负信号，因此按停止规则
关闭 lane，没有继续 MPI4。

| MPI | Full3D static peak / total | Hybrid static M120 | 实际失败项 | status |
|---:|---|---|---|---|
| 1 | 6.165108 GiB / 1256.061 s；formal pass | 1.751698 GiB / 1328.717 s；12/12+12/12物理通过 | positive QEP biorthogonality `1.197600e-6 > 1e-6`；negative side `7.524818e-7` | `controlled_negative_numerical` |
| 2 | 8.159409 GiB / 701.613 s；formal pass | measured 3.141788 GiB / 798.201 s；numeric pass | terminal launcher-drain sample unreadable，`terminated_for_authority_unreadable=true`；不能作为正式 peak | `controlled_negative_resource_authority` |
| 4 | not run | not run | MPI1、MPI2 连续两个负信号触发 lane stop | `not_run_by_stop_rule` |
| 8 | 14.721756 GiB / 260.736 s | 7.544262 GiB / 322.782 s；formal pass | 无 | main authority |

MPI1 Full3D 相对 MPI8 内存低 `58.12%`，但总时间为 `4.817×`。这个结果说明
较少 rank 的确可以减少进程复制，却不能用一次 QEP Gate 失败的 Hybrid 记录
宣称“1.7517 GiB 是合格最低内存”。MPI2 的 `3.1418 GiB` 同样只能保留为
非正式测量，不能追溯性提升。

## 8. 依赖失败、修复与证据保留

| 失败 | 实际值 / 原因 | 修复 | 处置 |
|---|---|---|---|
| p6 cross-section Floquet | 原路径只允许 N1curl p1–p4 | 使用 Basix exact entity DoF 与 interval transforms，资格化 p1–p6 | 首次失败保留 |
| static M120 projection | eliminated interior roundoff `1.187e-12` 超固定 `1e-12` | 引入 active-scale audit | 首次失败保留 |
| static M160 projection | interior `1.078e-12`，旧 cutoff `1.032e-12` | slave absolute 与 interior scale 分开；nonfinite/true leakage仍失败 | 首次失败保留 |
| M120 launcher startup | 无 solver payload；authority sample unreadable | 同 source、unbuffered controlled retry | 原记录保留；retry为authority |
| checker full-reference hash | 旧读取错误地只查顶层 key | 改读 `launch_gate.matching_full3d_reference` nested hash | 不改数值 |
| checker amplitude | 旧字段用未平移 `outgoing_amplitude` | 改用冻结 reference-v1 的 `outgoing_amplitude_at_boundary` | 不放宽 tolerance |

详见 [`dependency_failures.md`](dependency_failures.md)。

## 9. 完成、未运行与能力边界

| 项目 | 状态 | 原因 / 边界 |
|---|---|---|
| p2/h5 root cause | complete | 离散 phase + traction 修复后12/12+12/12 |
| p6/h10 six-path authority | complete | 同一 numerical source，MPI8，零 swap |
| mandatory 15% / preferred 25% Hybrid memory | pass | M120/M160均通过 |
| user 50% Hybrid memory target | not achieved | postprocess/record lifecycle共驻 |
| p3/h7.5 | out_of_scope / not_run | 用户明确禁止 |
| M240 | not_run | M120→M160已收敛且M160成本更高 |
| MPI4 rank point | not_run_by_stop_rule | MPI1数值 + MPI2资源两负信号 |
| h13 adaptive Hybrid | not run | Task035c非目标；等待本任务审阅 |
| 0.7 nm / 2 TiB update | not run | Task035c非目标 |
| irregular / tetra / mixed static | not run / unsupported | 非资格化范围 |
| production selective trace / new iterative | not run | Review V4明确排除 |

Task035c PSS/USS compact ledger 已由历史 raw timeline 回填；后续 heavy
campaign 仍必须从进程启动时同步保存 RSS、PSS、USS、cgroup 和 swap，不能把
本次回填机制当成缺失采样时的估算许可。
| ordinary default | unchanged | opt-in only |

## 10. 证据索引

| 证据 | 用途 |
|---|---|
| [Case096 README](../../../benchmarks/cases/096_hybrid_channel_memory_closure/README.md) | compact records、hash、复算命令和正式状态 |
| [`p6_h10_channel_closure.md`](p6_h10_channel_closure.md) | 六路径逐项数值与原始 artifact hash |
| [`object_lifecycle_and_rank_study.md`](object_lifecycle_and_rank_study.md) | stage peaks、50%缺口和rank lane |
| [`dependency_failures.md`](dependency_failures.md) | preserved failures与superseding修复 |
| [`test_summary.md`](test_summary.md) | targeted/MPI/checker/quality验证 |
| `benchmarks/artifacts/task035c_hybrid_channel_memory/` | ignored raw watchdog JSON |
| `benchmarks/artifacts/cases/091/` | ignored场样本、orders、timeline和stdout |

Task035c 的完成不授权修改 ordinary default，也不自动授权合并 master、启动
h13 adaptive Hybrid 或进行0.7 nm外推；这些决定继续由后续 Review 和用户明确授权。
