# Task39 T3 资源账本

本账本区分三种不同口径：RSS 是同时进程树的 resident memory；PSS 是按共享页
分摊后的进程树占用；USS 是进程树独占页。三者的峰值可以出现在不同采样点，
所以不能把它们当成同一时刻的一个向量。T3 使用既有 0.25 s watchdog sampling；
PSS/USS 只作诊断，不参与 hard-stop。

## 1. T3 measured authority

| 指标 | measured 值 | 口径/判定 |
| --- | ---: | --- |
| simultaneous process-tree RSS peak | 15965.453125 MiB | authority peak |
| independent process-tree PSS peak | 13932.458984375 MiB | complete smaps samples |
| independent process-tree USS peak | 13611.3515625 MiB | complete smaps samples |
| attempted/complete smaps samples | 920 / 918 | 2 个边缘 sample 不完整，但 complete>0 |
| telemetry status | measured | per-metric independent peaks |
| process-tree swap peak | 0 MiB | zero-swap requirement pass |
| warning triggered / termination | false / none | 未触发资源终止 |

当前运行前 capacity 为 228.0657501220703 GiB；warning=180 GiB，configured
hard=220 GiB，derived effective hard=min(220,0.90*228.0657501220703)
=205.2591751098633 GiB。T3 的 process-tree RSS 峰值远低于该硬停止边界。

solver rank 的 sum_rank_historical_peaks_upper_bound 为 15438.6640625 MiB；
这是跨 rank 历史峰值求和的上界，不是 simultaneous process-tree RSS，不能和
上表混称或用于声称节省比例。

## 2. 线性代数与阶段时间

| 项目 | 值 | 分类 |
| --- | ---: | --- |
| condensed matrix NNZ | 43283050 used / 47719324 allocated | measured raw summary |
| MUMPS factor NNZ | 217041864 | measured factor inventory |
| DtN assembly | 91.268220 s | measured |
| KSP setup/factor phase | 129.608784 s | measured |
| KSP solve | 0.199135 s | measured |
| postprocess | 8.928812 s | measured |
| total numerical elapsed | 283.036048 s | measured |
| outer run wall | 290.480347 s | measured from manifest |

## 3. Evidence boundary

T3 compact record 为
[task039_t3_full3d_direct_mpi8_v1.json](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_t3_full3d_direct_mpi8_v1.json)。
原始资源/进度文件仍在 ignored results 目录，不进入 Git。outer summary SHA 为
c8b4d0ab14b96665cb07e8a51bd479f3f26c14be552a98acf80f5b250df697cb，
numerical summary SHA 为
8e99f51fab57a184b393927c22a4be0b2b48b45939be480540c3f0fbf1c01ce0，
progress timeline SHA 为
05405559b994476c905be0a9a749a9b60bdacc911426c990ca84e40e956f1ba5。

前两次尝试仍按 configuration failure 和 evidence incomplete 保留，不能用本次
measured resource 覆盖其历史边界。

## 4. T4 Full3D iterative：数值负结果资源记录

T4 的正式迭代运行在 4000 步达到 `DIVERGED_MAX_IT(-3)`，因此下面的资源是
一次真实负结果运行的 measured telemetry，不是成功求解的资格化资源上限。

| 指标 | measured 值 | 口径/判定 |
| --- | ---: | --- |
| simultaneous process-tree RSS peak | 12031.03125 MiB | 进程树同时 RSS 峰值 |
| independent process-tree PSS peak | 10738.3857421875 MiB | complete smaps samples；独立 per-metric peak |
| independent process-tree USS peak | 10534.84765625 MiB | complete smaps samples；独立 per-metric peak |
| attempted/complete smaps samples | 8259 / 8257 | complete>0，telemetry status measured |
| process-tree swap peak | 0 MiB | zero-swap pass |
| warning / termination | false / none | 未触发资源终止 |
| effective hard stop | 205.2591751098633 GiB | derived `min(220, 0.90 × 228.0657501220703)` |
| solver-rank historical peak sum | 11984.98828125 MiB | 历史上界，不是 simultaneous process-tree RSS |

RSS、PSS、USS 的峰值可能出现在不同完整 sample，不能合并成同一时刻的
内存向量。T4 的 `task039_m3a_core_audit.json` 是独立 raw audit；其未嵌入
summary 的证据缺口单独记录，不改变数值负分类。详细 raw 路径和 SHA 见
[T4 negative record](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_t4_full3d_iterative_mpi8_negative_v1.json)。

## 5. T5 Hybrid direct M-convergence measured resources

T5 四次正式候选均使用既有 0.25 s watchdog。下表的 RSS/PSS/USS 是同一进程树在
完整可读 sample 上分别取出的独立峰值；它们可能来自不同 sample。PSS/USS 是诊断
覆盖，不参与 hard-stop。四次候选均 `swap=0`，没有发生 warning 或资源终止。

| M | outer wall (s) | simultaneous process-tree RSS (MiB) | independent PSS (MiB) | independent USS (MiB) | swap (MiB) | smaps attempted/complete |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 120 | 432.931447 | 8929.0625 | 7154.639648 | 6870.980469 | 0 | 1443/1439 |
| 240 | 815.862600 | 10999.851563 | 9222.426758 | 8938.285156 | 0 | 2642/2640 |
| 480 | 1468.884482 | 22798.082031 | 21039.913086 | 20758.953125 | 0 | 4368/4365 |
| 960 | 4812.858962 | 22536.339844 | 21407.276367 | 21222.859375 | 0 | 12594/12592 |

M960 在 canonicalized negative trace authority 处以
`raw_relative_error=1.678e-11 > 1e-12` 停止；其资源是一次真实 authority negative
run 的 measured telemetry，不是成功求解的资源上限。T5 的完整身份、阶段时间和每次
raw file SHA 见
[T5 Hybrid direct convergence record](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_t5_hybrid_direct_m_convergence_v1.json)。

## 6. T9 0.7 nm component-only feasibility

T9 只运行了已提交的纯组件生成器
[`task039_0p7nm_feasibility.py`](../../../benchmarks/task039_0p7nm_feasibility.py)，
没有创建网格、组装矩阵、启动 MPI/PDE，也没有读取 ignored raw。完整紧凑证据见
[T9 record](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_t9_0p7nm_feasibility_v1.json)
和
[T9 feasibility report](feasibility_0p7nm.md)。

| 项目 | 值 | 分类与边界 |
| --- | ---: | --- |
| 空气侧 inventory | 8015 spatial `(m,n)` / 16030 S/P channels；key SHA `28cf61cebf8656b207a5128cc98dda4e0bfcaad4cdb1fe1b784b33bcacd14e4d` | exact component-computed；substrate pending |
| p6/h1 global active trace | 51,192,000 | derived `h^-3` engineering estimate |
| p6/h1 endcap trace per side | 842,400 | derived `h^-2` engineering estimate |
| factor values-only envelope | 3234.18–32341.76 GiB | complex128 values only；不含 indices、metadata、workspace |
| known air-side endcap `W+K_LU` | 205.049–208.878 GiB | derived range；effective hard stop 205.259 GiB，upper exceeds；不是完整 two-endcap measurement |
| two-endcap status | `pending_substrate_material` | substrate、indices、pivot、workspace 和其他 solver 对象未计入 |
| preflight capacity | 256 GiB physical；selected 228.0657501220703 GiB；warning 180 GiB；effective hard 205.2591751098633 GiB | measured preflight capacity + derived threshold；不是 0.7 nm PDE job telemetry |
| preflight process-tree swap | 0 MiB | measured preflight；不等同于不存在的 0.7 nm formal job |

上述 W、K、FE 和 factor 数字都是 tracked evidence 上的 derived estimates，不能与
T3–T5 的 simultaneous process-tree RSS/PSS/USS measured peak 混称。0.7 nm 材料常数
缺失，最终保持 `0P7NM_MATERIAL_INPUT_INCOMPLETE`；同时保留 factor/cache、external
DtN/Woodbury、internal modal Schur 和 convergence-risk 分类，不能升级为
`CURRENT_ARCHITECTURE_PLAUSIBLE`。

T9 的 16030-channel dense K factor 相对于 604-channel baseline 只有约 `18,693x`
的 O(N^3) engineering ratio；absolute K-factor seconds 为 `not_established`，因为
没有 isolated measured 604-channel K-factor timing baseline。完整 two-endcap W 的
authority 为 `not_established/pending_substrate_material`；若假设 substrate 与 air
相同，conditional example 为 `432117504000` bytes（约 `402.44` GiB），不属于
authority、无条件 lower bound 或 substrate 替代。

## 7. E6 M480 H-field diagnostic measured resources

E6 消费的 Hybrid raw 是唯一一次 Review V1 M480 direct H diagnostic rerun；Full3D 一侧
只做 canonical replay 和采样，没有重新组装或求解。因此下表的 Hybrid 数值是 formal
run 的 simultaneous process-tree 监测结果，PSS/USS 仍是独立峰值，不能拼成同一时刻的
内存向量；Full3D replay 的求解资源为 `not_available/not_applicable`。

| 项目 | 值 | 分类/口径 |
| --- | ---: | --- |
| Hybrid M480 numerical elapsed | `1500.0791483931243 s` | measured |
| Hybrid process-tree RSS/PSS/USS | `22785.6796875 / 21028.330078 / 20747.875 MiB` | measured independent peaks |
| Hybrid process-tree swap | `0 MiB` | measured; zero-swap pass |
| Full3D replay assembly/solve | `false / false` | replay contract; no matrix assembly or linear solve |
| Full3D replay process-tree peak | `not_available` | not a formal solve; no resource authority inferred |

E6 的 raw payload、metadata、Full3D replay payload/metadata 和 comparison JSON 的完整 SHA
以及路径见 [E6 H diagnostic outcome](m480_h_field_diagnostic.md)。这些证据不覆盖、也不
改写 T3–T5 的既有资源账本；E6 不进入 E7。

## 8. Review V1 E7/E10：M960 direct 与生命周期边界

E7 的唯一正式 M960 direct run 使用独立的全程 watchdog。其 global process-tree
RSS/PSS/USS 峰值为 `71502.582 / 69746.089 / 69465.102 MiB`，swap 为 `0 MiB`，
smaps attempted/complete 为 `13165/13163`。这些是 measured independent peaks，不能
解释成同一采样点的三维内存向量。

| 运行 | RSS | PSS / USS | stage-aligned snapshot | 分类 |
| --- | ---: | --- | --- | --- |
| M120 | `8.720 GiB` | not_available in E10 series | not_available | T5 measured RSS |
| M240 | `10.742 GiB` | not_available in E10 series | not_available | T5 measured RSS |
| M480 | `22.264 GiB` | not_available in E10 series | not_available | T5 measured RSS |
| M960 prior trace | `22.008 GiB` | not_available | not_available | T5 pre-solution measured RSS |
| M960 formal direct | `71502.582 MiB` (`69.827 GiB`) | `69746.089 / 69465.102 MiB` | not_available | E7 measured global peak |

正式 M960 的 stage-event JSONL、memory_stages JSONL 和 E10 ledger 均未持久化；stdout
只能提供 elapsed boundary，不是阶段 RSS/PSS/USS 峰值。对象容量仍须分开阅读：basis、
coupling、projection 和 augmented estimates 不能相加冒充 resident process-tree peak，
modal Schur 未 materialize，factor resident bytes not_available。详见
[E10 memory forensics](memory_lifecycle_forensics.md) 与
[E10 compact record](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_e10_memory_lifecycle_v1.json)。

E10 attribution taxonomy 的确定项只有
`UNATTRIBUTED_RUNTIME_OR_ALLOCATOR_HIGH_WATER`。`LIFECYCLE_OVERLAP_DOMINANT` 最多为
hypothesis/not_established；QEP workspace、mode replication、coupling assembly、local
FE factor 和 modal Schur dominant 均为 not_established。没有据此开发新的 PC、modal
matrix-free、压缩或 owner-only 生命周期重构。

## 9. Review V2 V2-1：h5 Full3D direct readiness

V2-1 绑定 code/input source commit `c26debf71d2a7b76bcf9b9715412063682b091b0`，仅完成
h5 的 validate/dry-run 与资源、整数宽度和启动前身份审计；没有 h5 assembly、factorization、
solve 或正式峰值，因此下表不能当作运行实测。

| 项目 | 结果 | 口径 |
| --- | --- | --- |
| MemTotal / MemAvailable | `228.066 / 224.432 GiB` | measured；启动条件 MemAvailable≥200 GiB |
| swap / disk free | `0 / 772.330 GiB` | measured；swap immediate stop，disk≥20 GiB |
| warning / critical / absolute hard | `170 / 195 GiB / 224000000000 bytes` | 195 只作 critical checkpoint；hard 为用户 override |
| h5 predicted peak | RSS `90.085–150.108 GiB` | derived estimate；未把预测写成 measured |
| validate / dry-run / inventory | `pass / pass / 604` | 未启动 worker/PDE |
| MUMPS integer risk | `conditional` | PETSc row index 32-bit；MUMPS nnz counters 64-bit；runtime factor path not_established |

记录与容量公式见 [V2-1 readiness record](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v2_h5_full3d_readiness_v1.json)
和 [h5 readiness outcome](full3d_h5_direct_and_convergence.md)。旧路径缺失该字段时仍保持原有
`min(terminate, 0.90×selected)` 行为；这句话记录的是 V2-1 时点；当前 V2-2 formal run 已完成，
V2-3 comparison 已完成 negative，分类为 `FULL3D_DIRECT_5NM_REFERENCE_NOT_CONVERGED_AT_P6H5`；h5 仅为 `best_available_discrete_authority_only`，详见 [V2-3 record](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v2_h6_h5_two_tier_convergence_v1.json) 与 [V2-3 outcome](full3d_h5_direct_and_convergence.md)。

## 10. Review V2 V2-2：h5 Full3D direct measured authority

V2-2 是唯一一次冻结的 h5 Full3D direct MPI8 formal run；下表全部来自该 run 的 launcher
watchdog 或 numerical output。它们是 measured simultaneous process-tree/独立指标，不是预测，
也不构成 h6-vs-h5 convergence。

| 项目 | measured 值 | 口径 |
| --- | ---: | --- |
| process-tree RSS/PSS/USS peak | `92491.328 / 90440.785 / 90103.539 MiB` | 独立峰值；不可拼成同一时刻向量 |
| process-tree swap peak | `0 MiB` | zero-swap Gate pass |
| warning / critical crossing | `false / false` | warning 170 GiB；critical 195 GiB 只记录 crossing |
| absolute hard / poll | `224000000000 bytes / 0.25 s` | 用户覆盖 hard；全程快速采样 |
| stage4 build / KSP setup / KSP solve | `120.759 / 4748.209 / 2.743 s` | measured |
| postprocess / total numerical | `61.988 / 5330.290 s` | measured |

矩阵与对象口径为 cells=`1680`、full FE DoFs=`1127502`、active trace=`336960`、assembled
rows with auxiliary=`337564`，condensed NNZ used/allocated=`283210150/298136764`。MUMPS
raw factor telemetry 的 signed-int32 表示为 raw matrix NNZ=`-1697967296`、INFOG(9)=`-2597`；
`factor_nnz_corrected=2597000000` 仅为校正后的遥测字段，未修复运行时或重跑。完整身份、
artifact hashes、604 inventory、canonical packets 和 own-Gate 见
[V2-2 compact record](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v2_h5_full3d_direct_v1.json)。

V2-2 own-Gate 为 pass；h5 只建立 Full3D h5 discrete authority。h10 仍为
`historical_underresolved_stress_anchor_only`；V2-3 已完成 negative，h5 仅为 `best_available_discrete_authority_only`，详见 [V2-3 record](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v2_h6_h5_two_tier_convergence_v1.json) 与 [V2-3 outcome](full3d_h5_direct_and_convergence.md)。

## 11. Review V2 V2-4：h5 Hybrid direct readiness

本节是启动前证据，不是 formal run。h5 Hybrid M480 的 cross-section、FE/P/T、augmented、
factor 和 RSS/PSS/USS 均为 derived prediction；唯一 measured 的是当前资源快照与
h10 Hybrid、h10/h5 Full3D 锚点。中心值和 `0.8–1.25` 保守区间、公式及 SHA 见
[h5 Hybrid readiness](h5_hybrid_direct_readiness.md)。

用户覆盖 watchdog 为 warning=`170 GiB`、critical=`195 GiB`（只记录 crossing）、
absolute hard=`224000000000 bytes`、poll=`<=0.25 s`、any swap immediate stop。
当前 MemAvailable=`225.03710174560547 GiB`、swap used=`0`、disk free=`808005708 KiB`，
readiness=`conditional launch_eligible=true`。V2-5 尚未运行，不能把任何预测写成
measured peak、factor success 或 Hybrid authority。
