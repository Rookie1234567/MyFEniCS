# Task037-extra G2.3 证据收口

本文件回答 G2.3 的一次正式 p6 full-space ILU inventory screen。结论是
`G2.3 inventory measurement qualified / plain full-space ILU route closed`：
原始数据和修复后的 checker 合同闭合，但普通 full-space ILU 路线因占用的
保留字节更多且一次 apply 更差而关闭。这不是整体 G2 通过，也不是生产方案晋级。

## 结论总表

| lane | 状态 | 说明 |
|---|---|---|
| G2.2 slab14 full-space/trace identity | `pass_algebraic_identity_only` | tiny fixture、3 个 deterministic vectors 和 1 个 iter20 residual direction 均通过 `<=1e-10` |
| G2.3 slab14 full-space ILU inventory | `inventory_measurement_qualified` | raw 资格检查通过；retained-payload gate 为 false，故 `close_fullspace_ilu_only_route` |
| plain full-space ILU route | `closed` | full-space retained lower bound 是 trace 的 `5.3166x`，iter20 one-apply rho 也更差 |
| G2.4 LOR mesh/transfer | `pending_not_run` | 未实现、未运行 |
| G2.5 LOR-HX/V-cycle | `pending_not_run` | 未实现、未运行 |
| G2.6 one/two V-cycle Gate | `pending_not_run` | 未运行 |

## 两个指标的通俗含义

`retained payload lower bound` 是“为了保留一个因子和两份工作向量，至少要
占多少数组存储”的下界估计：它包含 factor CSR 的结构性 payload 与两个
PETSc Vec 数组，不包含 PETSc allocator、排序置换等额外开销，所以不能直接
当作进程峰值内存。

`rho` 是一次预条件器应用后的残差范数除以输入残差范数。`rho < 1` 才表示
这一次应用在该方向上缩小残差；`rho > 1` 表示该方向反而被放大。它是
stationary one-apply 诊断，不是外层 FGMRES 的收敛率，也不是物理量收敛。

## 运行身份与原始/修复后资格

| 项目 | 值 |
|---|---|
| raw numerical source SHA | `1a2dd825e295c38e3cecf30e98fa62b7a3510e1d` |
| checker fix/requalification SHA | `e3447748391a902d27323bc796c008c8a1c8770b` |
| scope | p6/h10/S、MPI1、M2c never-materialized、M3a overlap0.125 partition、screen20 |
| flags | `--task037-extra-g2-slab14-identity` + `--task037-extra-g2-slab14-factor-inventory` |
| watchdog policy | poll `0.25` s；warning `10` GiB；terminate `14` GiB；timeout `1800` s；no swap |
| run directory | `benchmarks/artifacts/101_task37_extra_development/g2_slab14_factor_inventory_mpi1_screen20_1a2dd825` |

原始 `watchdog_summary.json` 保持其真实状态：`task037_extra_g2_slab14_factor_inventory_not_pass`，外层 parent return code 为 `2`，唯一 qualification failure 是
`task037_g2_factor_route_reduction_raw`。旧 checker 错把 signed
`reduction_fraction` 限制为非负，因此把这个“full-space 更大”的科学负结果
误判为 checker failure；这不是 raw PDE 重新运行，也不是原始 summary 已通过。

在 checker fix SHA 上对同一 ignored raw 做了只读重资格：patched checker
`pass=true`、`failures=[]`、G2 factor checks `34/34`，不回写原始 summary，
也不创建替代 official summary。

## identity 与 materialization

primary 固定为 slab14（G0 iter20 最大 local residual），control 为 slab5；
slab13 只保留为最大正 ablation-damage comparator，不替换 primary。

| 字段 | 正式 screen 值 |
|---|---:|
| cells / unique blocks | `54 / 6` |
| full rows | `32724` |
| interior rows + trace rows | `24300 + 8424` |
| source / retained / dropped active columns | `23328 / 17064 / 6264` |
| partial cells | `18` |
| sparse `C` NNZ / bytes | `17064 / 434808` |
| global A / global F | `false / false` |
| inventory-only / used in outer preconditioner | `true / false` |
| official result unaffected / official result | `true / false` |

完整 local block 和 trace rows 被保留，`C` 只保留 owner active columns，外部
列等价于零延拓；列数闭合为 `23328 = 17064 + 6264`。这沿用既有 principal
restriction，而不是把跨 slab cell 丢掉。screen20 以固定步数边界
`DIVERGED_MAX_IT(-3)` 结束；这不是收敛结果，官方 RTA 没有运行。

## factor inventory 与 retained-payload decision

| inventory | current trace factor | full-space ILU(0)/RCM |
|---|---:|---:|
| rows | `8424` | `32724` |
| matrix NNZ / factor NNZ | `6086016 / 6086016` | `32378616 / 32378616` |
| matrix CSR payload | — | `647703220 B` |
| retained payload lower bound | `122023588 B` = `116.37076187133789 MiB` | `648750388 B` = `618.6965827941895 MiB` |
| setup matrix / factor lifetime | factor-only storage | setup matrix released；factor retained至 oracle destroy |

full/trace retained ratio 为 `5.316598197391147`，差值为
`526726800 B = 502.32582092285156 MiB`。按任务定义的 signed 公式，
`(trace-full)/trace = -4.316598197391147`；这表示 full-space payload 增加
约 `431.66%`，不是“下降 431.66%”。25% Gate 为 `false`，raw route 状态为
`close_fullspace_ilu_only_route`。patched checker 允许 signed reduction，并在
route bytes、status 和 gate 原始字段闭合时让这个科学负结果通过资格检查。

## iter20 residual 与 one-apply 诊断

iter20 输入来自 solver 内部真实 `r=b-Ax` 的 owner-local 路由，没有从 scalar
residual 伪造，也没有把 final solution 当 residual。

| 字段 | current trace ILU | full-space ILU |
|---|---:|---:|
| input norm | `0.42723143961943305` | `0.42723143961943305` |
| post norm | `0.5385209372860695` | `0.7716852789816032` |
| rho | `1.2604899530937386` | `1.806246468352144` |
| correction norm | `0.8014811021173734` | `0.8237278810044446` |
| correction SHA256 | `892d7aa29811b0ccf403377af754fc448d1ba2dee914244a0ecb6c1deb8a9d40` | `02eea6f53e8a5df4f86b17826477a1826dff7a1ab9ff570e493f407d5ae9a72f` |

full-space 相对 trace 的 rho difference 为 `0.5457565152584054`，ratio 为
`1.4329717296983637`；两者都大于 1，full-space 更差。full-space factor
apply `count=2`，结果 finite/deterministic，apply 用时
`0.24651467008516192 s`；matrix assembly 为 `30.55818408995401 s`，factor
setup 为 `18.97298593702726 s`。

## 资源与生命周期证据

| 指标 | authority |
|---|---:|
| process-tree RSS | `7647.62109375 MB = 7.468379974365234 GiB` |
| worker RSS / PSS / USS | `7633.734375 / 7582.0400390625 / 7537.23046875 MB` |
| swap | `0` |
| warning / termination / timeout | `false / false / false` |
| wall / samples | `349.65642845397815 s / 1267` |

阶段峰值如下。此时原有 16 个 trace factors 仍然保留，因而这是“额外构造
full-space inventory oracle”的峰值，不是替代候选的独立峰值。

| progress stage | process-tree RSS |
|---|---:|
| `g2_fullspace_matrix_assembly_started` | `7605.90625 MB` |
| `g2_fullspace_factor_setup_started` | `7605.91015625 MB` |
| `g2_fullspace_factor_setup_ready` | `7605.9609375 MB` |

## raw evidence

compact tracked record：[g2_slab14_fullspace_factor_inventory.json](/home/shenjh/Projects/MyFEniCSx_task37_extra/benchmarks/cases/101_task37_extra_development/records/g2_slab14_fullspace_factor_inventory.json)。raw 均在 ignored run directory 中，以下 hash 绑定本次结论：

| raw 文件 | SHA256 |
|---|---|
| `watchdog_summary.json` | `90b17504fc584cc43ddad53a8ae0918e598ff183940b1b599578ebf59eb59ac1` |
| `run_summary.json` | `5ce1828bddd167a0cc9119260a93bf52284a164bf5592ade0c7f276133bcd101` |
| `task037_f3_core_audit.json` | `65baa175fcfd1c2d2d04e9b6b4b70f44e44a0b53c98995c3c7520d530795be18` |
| `progress_3d.jsonl` | `232c50fc51cac7ed938a2a197a732a1a5c7ad4f3968f843931194810d3ea096c` |
| `memory_timeline.csv` | `3698e5f924d6f9d20a7a8e78b573355e0a3145cf370606451807908c49e39b27` |
| `task037_f3_residual_history.jsonl` | `75f0bc3ebec3648b60fdfc55daa9afd036b81cf6d5fe0ef1f7051a83e0f24940` |
| `parent_launch_descriptor.json` | `0b3340afa3c7e3d557080385860be9ed4e16603f5bee75209302487f32460438` |
| `worker_stdout.txt` | `bb438d24852a755b11532411feebc2767e89b004b5236a4fac2ee25ffb8cf3bd` |

## 下一步边界

本轮只证明：在现有 16-slab trace factors 仍保留的 screen 中，slab14 的
full-space matrix/factor inventory 可以被测量、raw checker 可以重资格，且
plain full-space ILU 路线应关闭。它不证明 full-space 预条件器有效，不证明
global candidate、minimum contraction、full solve 或 production promotion。
G2.4、G2.5、G2.6 均为 `pending_not_run`。
