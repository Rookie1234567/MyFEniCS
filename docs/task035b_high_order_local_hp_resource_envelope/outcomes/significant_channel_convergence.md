# Task035b 显著衍射通道收敛参考 v1

## 结论

| 项目 | 结果 |
|---|---|
| JSON status | `significant_channel_reference_v1_frozen` |
| 顶层 pass | `true` |
| 机械校验 | `true` |
| 参考中心 | global structured-hexa p6/h10，MPI8 |
| 显著通道 | 12；p6/h10 power floor = `1e-8` |
| 严格 p/h 单调 | 11 / 12 |
| bounded final-h confirmation | 1 / 12：`R(-7,0)_s` |
| 未收敛通道 | 无 |
| production qualified | `false` |
| ordinary default changed | `false` |
| authority manifest SHA256 | `c8538133617ffbeffb1de2f18f8a7134082018f9f85d6a50ea72e0e83ff718b2` |
| reference payload SHA256 | `bb78f17a0eb3a664620b9acf7cad47dd75c1881899cf885cc243328e320177ba` |

本文件冻结的是当前 fixed rectangular block grating 的 best-available same-code 离散参考，不宣称 continuum truth，也不把 reference v1 提升为 production default。

## 12 通道中心、band 与不变 v0 Gate

| 通道 | p6/h10 power | amplitude Re | amplitude Im | amplitude magnitude | unwrap phase (deg) | numerical power band | numerical amplitude-norm band | phase band (deg) | v0 power tol | v0 amplitude-norm tol | p/h 趋势 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| T(-7,0)_s | 2.362010449240e-06 | 9.812210508339e-04 | -8.723749960195e-05 | 9.850914332875e-04 | -5.080642027 | 6.788985490928e-09 | 1.945555807017e-05 | 1.129416345e+00 | 2.158693803953e-09 | 1.216565066439e-05 | p/h strict monotone |
| T(-5,0)_s | 2.119208257204e-07 | 1.340326966068e-04 | 1.470057842858e-04 | 1.989358297873e-04 | 47.642968622 | 3.891272584919e-10 | 1.633020959664e-06 | 4.688770143e-01 | 3.891272584919e-10 | 1.280645723886e-06 | p/h strict monotone |
| T(-4,0)_s | 4.372888972066e-07 | -2.621322075309e-04 | 8.743226903754e-05 | 2.763289631835e-04 | 161.554258605 | 2.193277840925e-09 | 4.044028207304e-06 | 8.269945248e-01 | 5.251002536670e-10 | 2.541657906333e-06 | p/h strict monotone |
| T(-2,0)_s | 2.959841395129e-06 | -6.970027805581e-04 | 2.979420807207e-04 | 7.580121104375e-04 | 156.855141472 | 4.651045293875e-09 | 4.871917002038e-06 | 3.672597983e-01 | 4.651045293875e-09 | 4.580806193893e-06 | p/h strict monotone |
| T(-1,0)_s | 2.178167398555e-05 | 2.091013385303e-03 | -1.023379862844e-03 | 2.328012740771e-03 | -26.077963996 | 1.190593438994e-07 | 1.479012618740e-05 | 3.290234035e-01 | 1.114413665230e-07 | 1.272899067656e-05 | p/h strict monotone |
| T(0,0)_s | 6.026738723470e-01 | 6.313787033482e-01 | 4.730209810383e-01 | 7.889156580675e-01 | 36.840089239 | 2.476319170339e-04 | 7.609860598196e-03 | 5.526182136e-01 | 2.175765740112e-04 | 6.779628645197e-03 | p/h strict monotone |
| R(-7,0)_s | 6.263542422225e-07 | -5.052091112471e-04 | -2.608886170068e-05 | 5.058822736486e-04 | -177.043887246 | 1.249444295749e-09 | 7.995038740980e-07 | 7.506558857e-02 | 1.249444295749e-09 | 7.995038740980e-07 | p monotone；h bounded confirmation |
| R(-5,0)_s | 7.457300536771e-08 | -9.817807918591e-05 | -6.535503245872e-05 | 1.179415766399e-04 | -146.349148905 | 1.194301559963e-09 | 1.113206415872e-06 | 2.880380548e-01 | 1.194301559963e-09 | 1.113206415872e-06 | p/h strict monotone |
| R(-4,0)_s | 2.675239609673e-07 | 2.102233361252e-04 | -4.973043612808e-05 | 2.160253858441e-04 | -13.309226334 | 3.140671805311e-09 | 3.147616116824e-06 | 7.660110783e-01 | 1.086491588134e-09 | 1.881524952516e-06 | p/h strict monotone |
| R(-2,0)_s | 1.477690851303e-06 | 4.942316170615e-04 | -2.055157697636e-04 | 5.352584636647e-04 | -22.578950990 | 3.009352271937e-09 | 3.186491282641e-06 | 3.401702812e-01 | 1.242282442535e-09 | 3.186491282641e-06 | p/h strict monotone |
| R(-1,0)_s | 6.669309654252e-06 | -1.032707715920e-03 | 7.678339217534e-04 | 1.286877677915e-03 | 143.368635185 | 5.909665791641e-08 | 8.558395113884e-06 | 2.840262593e-01 | 5.111835340427e-08 | 7.413384075620e-06 | p/h strict monotone |
| R(0,0)_s | 7.537612200675e-04 | -2.525230435360e-02 | 1.077415170215e-02 | 2.745471216508e-02 | 156.893989518 | 3.609563851989e-05 | 9.361680180524e-04 | 1.390110773e+00 | 3.195286914615e-05 | 8.330266538615e-04 | p/h strict monotone |

numerical band 对每个分量分别取以下三项绝对差的最大值：`|p4/h5-p4/h7.5|`、`|p6/h10-p5/h10|`、`|p6/h10-p4/h5|`。它只描述离散 spread，绝不作为放宽 Gate 的替代 tolerance。

不变 v0 Gate 仍逐通道严格使用：

- power tolerance = `max(|power(p6/h10)-power(p5/h10)|, 1e-12)`；
- complex-amplitude tolerance = `max(|a(p6/h10)-a(p5/h10)|, 1e-10)`；
- `uses_numerical_convergence_band=false`；
- `uses_h15_or_fixed_diagnostics=false`。

### `R(-7,0)_s` bounded 说明

该通道的 p 方向全部分量单调；p4 h10→h7.5→h5 中 power、amplitude Re 和 magnitude 在最后一步存在微小回摆。它们的 p4/h5→p6/h10 误差均不大于独立 h10 p5→p6 修正，因此按预先写入记录的 bounded-final-h 判据通过；非单调分量仍完整保留，未改写为 strict monotone。

## COMSOL cross-code scalar context

| scalar | COMSOL direct convergence center | 使用范围 |
|---|---:|---|
| R00 | 0.000752895 | cross-code scalar context only |
| R total | 0.000762014 | cross-code scalar context only |
| T total | 0.6027075 | cross-code scalar context only |

| COMSOL 约束 | 值 |
|---|---|
| authority | `docs/COMSOL_direct_solver_report.md` |
| authority SHA256 | `80d32c80f28f0bcc87470881f639bbbfe54b468b7a7da53c31a26b3785cd6ec4` |
| software | `COMSOL 6.4.0.293` |
| solver scope | `MUMPS direct solver tables only` |
| selected row identity SHA256 | `d4783e468ab5bae3b61d159966c55a756643ba4cebb9c6a4e4e9f567e4f36146` |
| excluded_from_channel_band | `true` |
| excluded_from_12_channel_gate | `true` |
| complex channel amplitudes | `not available` |
| changes unchanged_v0 acceptance gate | `false` |

中心由以下 5 个直接法表行逐分量取 median，并按原报告结论精度舍入。COMSOL Lagrange 与 FEniCS Nédélec 阶次不可一一映射；这里不从 scalar 表推断任何衍射通道复振幅。

| COMSOL 表 | MPH | element | h (nm) | solution | DOFs | R00 | R | T |
|---|---|---|---:|---|---:|---:|---:|---:|
| 直接法：四阶拉格朗日单元 | `3D_benchmark_direct_5to2p4.mph` | 六面体 | 2.0 | `sol47` | 4,818,792 | 0.000752895 | 0.000762014 | 0.602707488 |
| 直接法：四阶拉格朗日单元 | `3D_benchmark_direct_5to2p4.mph` | 四面体 | 3.0 | `sol42` | 4,323,924 | 0.000752897 | 0.000762016 | 0.602707468 |
| 直接法：四阶拉格朗日单元 | `3D_benchmark_direct_5to2p4.mph` | 四面体 | 2.5 | `sol43` | 7,490,900 | 0.000752891 | 0.000762010 | 0.602707520 |
| 直接法：六阶拉格朗日单元 | `3D_benchmark_direct_p6.mph` | 六面体 | 7.5 | `sol44` | 488,150 | 0.000752896 | 0.000762015 | 0.602707484 |
| 直接法：六阶拉格朗日单元 | `3D_benchmark_direct_p6.mph` | 四面体 | 7.0 | `sol50` | 950,924 | 0.000752895 | 0.000762014 | 0.602707512 |

## FEniCS authority identity

| sample | role | p / h (nm) | source SHA | record SHA | raw DtN-order SHA | mesh / legacy identity |
|---|---|---|---|---|---|---|
| p4_h10 | `trend_only` | 4 / 10.0 | `e0917859aa53cd6cff6bc3bc411b29255aeac9e2` | `ec949270b4440a0f68ac1406a345882d25f7daa34048397b89095895ffb8d6c1` | `f4e48e7547816d189b21b389c1f73fd6d350f62164bdfb983dd3c49232a79792` | `qualified_legacy_axis_plan_no_partition_hash`; plan `[6, 3, 14]` |
| p4_h7p5 | `numerical_band` | 4 / 7.5 | `e0917859aa53cd6cff6bc3bc411b29255aeac9e2` | `09e3b01da9800578b391df4a42b4e4d6fb8b411722867906a942dfefe495f7aa` | `51a1b236b0fcd93b6cda5cf3e359fc8fee3748405cfa83313225390aa45d96e4` | `qualified_legacy_axis_plan_no_partition_hash`; plan `[9, 4, 20]` |
| p4_h5 | `numerical_band` | 4 / 5.0 | `e0917859aa53cd6cff6bc3bc411b29255aeac9e2` | `879816e0c7c9f345deeb23435607560be9af7ad431142f8b2e3ea4f9a8022cab` | `e034219a6f6308c3af7f2fde326ca7a63d457a9e93e7df462c856151b8fb4e64` | `qualified_legacy_axis_plan_no_partition_hash`; plan `[12, 5, 28]` |
| p5_h10 | `unchanged_v0_gate` | 5 / 10.0 | `65bf6fb034d6717e190a5d1ab4a2025fb1c4ff3b` | `7984c18b128134a58ce496106ea06b46b5820d0b5cea813e2d51a9ec59b8bf74` | `e69ac315fa8cfdec0ae039b474cdab8aee3eaeab6ece762ce08996c4f1de5606` | mesh `f0eef2aa28e86014b661a921993bcfd45e6db1892da350402f2be11ec64dd857`; cell-tag `42f511fc7ffddcbc2972d641018e16a845f48c11067ccd9a9686695ad5cfc131`; facet-tag `0adbcfed35e1840460f826cb1ca1695ed87c0c3960e2073377d2f50871c3c0bd` |
| p6_h10 | `reference_center` | 6 / 10.0 | `65bf6fb034d6717e190a5d1ab4a2025fb1c4ff3b` | `7984c18b128134a58ce496106ea06b46b5820d0b5cea813e2d51a9ec59b8bf74` | `363865d51102eed02ae74fc08d32678467f8d067611255b474e89c153a745913` | mesh `f0eef2aa28e86014b661a921993bcfd45e6db1892da350402f2be11ec64dd857`; cell-tag `42f511fc7ffddcbc2972d641018e16a845f48c11067ccd9a9686695ad5cfc131`; facet-tag `0adbcfed35e1840460f826cb1ca1695ed87c0c3960e2073377d2f50871c3c0bd` |
| p5_h15 | `underresolved_diagnostic` | 5 / 15.0 | `5d75c5ed8ae0dd4382eccf0c47e22fce01391184` | `59859ef7b49ac6c40e2e3d803a366c71742a29411f7d9591384c62dc8fa923f9` | `0bb1f7835132eedef825698f4e12d49aee979574a09f3da0b239363331a3daa3` | mesh `f6ed05e9f88f05cb88631698c2fe6692f054bfd41fd615272efda436362e3cc0`; cell-tag `a326daa4edcb470ab6159b30be56a8c69619d0a61290b8f96aadce098a187d63`; facet-tag `e898956f4c0eb1b463e0bca42033b832b5a9b350c44da659f1578c13aa2a9797` |
| p6_h15 | `underresolved_diagnostic` | 6 / 15.0 | `5d75c5ed8ae0dd4382eccf0c47e22fce01391184` | `59859ef7b49ac6c40e2e3d803a366c71742a29411f7d9591384c62dc8fa923f9` | `e803ae7454b5e5088de76795f23d961f806c73274aac28b733bceb6e6a29c6c3` | mesh `f6ed05e9f88f05cb88631698c2fe6692f054bfd41fd615272efda436362e3cc0`; cell-tag `a326daa4edcb470ab6159b30be56a8c69619d0a61290b8f96aadce098a187d63`; facet-tag `e898956f4c0eb1b463e0bca42033b832b5a9b350c44da659f1578c13aa2a9797` |
| fixed_p5trace_p6interior_h15 | `underresolved_trace_diagnostic` | p5_trace_p6_interior / 15.0 | `7f61d554b0441d7b224c096aba402d3b3ac2baa6` | `1ffde81be08c24232e62c1d2dfbf1b7ad2dcb3623444ea40af68b5c6585758e3` | `e585cdce2dfc10e10eb52198a56009d2ff5725fbb09d869706d88d9eb9e1d06e` | `h15_fixed_trace_controlled_negative` |

## 诊断与排除

- global p5/p6 h15 与 fixed p5-trace/p6-interior h15 仅作为 underresolved/trace diagnostic，不进入 numerical band 或 v0 Gate；
- Task035 tetra theta0p4 p5/p6 h50 保留为 `excluded_controlled_negative`，不作为 structured-hexa same-error authority；
- 本次只聚合既有记录，没有运行新 PDE；
- 所有 12 通道的 power、复振幅 Re/Im、magnitude、unwrap phase、p/h 差、绝对/相对 spread 均保存在对应 JSON channel 对象中。
