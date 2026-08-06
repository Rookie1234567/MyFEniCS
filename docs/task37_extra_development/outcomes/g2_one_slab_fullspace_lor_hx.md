# G2 一个 slab 的 full-space identity 与 ILU inventory

本 outcome 合并记录 G2.2 的代数 identity 和 G2.3 的一次正式
full-space factor inventory。这里的 full-space 是“一个 slab 内每个 cell 的
interior DoF 加 owner trace 行”的局部对象，不是整个 Full3D uncondensed
global matrix。

## 结论边界

| lane | 状态 | 允许的解释 |
|---|---|---|
| G2.2 full-space/trace identity | `pass_algebraic_identity_only` | tiny fixture、真实 slab14 的 3 个 deterministic vectors 与 1 个 iter20 residual direction 均通过 `<=1e-10` |
| G2.3 full-space p6 ILU inventory | `inventory_measurement_qualified` | raw 与 patched checker 合同闭合；不是预条件器有效性结论 |
| plain full-space ILU route | `close_fullspace_ilu_only_route` | retained-payload 25% Gate 未达到，且 iter20 one-apply rho 更差 |
| G2.4 LOR mesh/transfer | `pending_not_run` | 未实现、未运行 |
| G2.5 LOR-HX/V-cycle | `pending_not_run` | 未实现、未运行 |
| G2.6 one/two V-cycle Gate | `pending_not_run` | 未运行 |

因此不能把本 outcome 写成整体 G2 通过，也不能宣称 minimum contraction、
full solve 或 production promotion。

## 首次解释：两个研究指标

`retained payload lower bound` 可以理解为“保留一个因子和两份工作向量至少
需要的数组空间”：这里按 factor CSR 结构性 payload 加两个 PETSc Vec 数组
计算，不包括 PETSc allocator、排序置换等额外开销。它用于两个局部对象的
同口径比较，不能等同进程 RSS 峰值。

`rho` 是一次 correction 后的残差范数除以 correction 前输入残差范数。`rho`
小于 1 表示该方向一次缩小残差，大于 1 表示一次放大残差；它是 stationary
one-apply 诊断，不是外层 FGMRES 收敛率，更不是物理 R/T/A 收敛。

## G2.2：代数 identity

同一个 slab trace vector 分别经过现有 trace Schur action 和 full-space cell
block recovery/action，再投影回 trace。检查的公式为：

```math
S_j v = R_t\mathcal A_j
\begin{bmatrix}
-A_{ii}^{-1}A_{it}v\\
v
\end{bmatrix}.
```

它解决的是 full-space 组装、interior recovery、Floquet/trace expansion 和
slab 边界列是否接错的问题；只证明两条代数路径对同一输入一致，不证明
预条件器有效或外层求解收敛。

primary 固定为 slab14，因为 G0 的 iter20 local residual 最大；control 为
slab5；slab13 只作为最大正 ablation-damage comparator，不替换 primary。

| G2.2 字段 | v2 值 |
|---|---:|
| owner / cells / unique blocks | `0 / 54 / 6` |
| owner active rows | `8424` |
| source / retained / dropped active columns | `23328 / 17064 / 6264` |
| partial cells | `18` |
| sparse `C` NNZ / bytes | `17064 / 434808` |
| deterministic relative errors | `2.9248960201709676e-15`；`2.978578754981666e-15`；`2.6617554455542794e-15` |
| iter20 local residual norm | `0.42723143961943305` |
| iter20 identity error | `1.7721399154913289e-15` |

边界语义与既有 principal restriction 一致：保留完整 local block/trace rows，
`C` 只保留属于 owner rows 的 active trace 列，外部列等价于零延拓，因此
`23328 = 17064 + 6264`。第一次 source
`5bb270715d5610d7752d5d9f99e112c467765630` 因错误要求 cell 的全部 active IDs
都属于 owner rows，在进入 solver 前受控失败；该负证据没有被隐藏。

## G2.3：正式 inventory 身份

| 项目 | 值 |
|---|---|
| raw numerical source SHA | `1a2dd825e295c38e3cecf30e98fa62b7a3510e1d` |
| checker fix/requalification SHA | `e3447748391a902d27323bc796c008c8a1c8770b` |
| scope | p6/h10/S、MPI1、M2c never-materialized、M3a overlap0.125 partition、screen20 |
| flags | identity + factor inventory；G0 diagnostics 未启用 |
| run directory | `benchmarks/artifacts/101_task37_extra_development/g2_slab14_factor_inventory_mpi1_screen20_1a2dd825` |
| watchdog policy | poll `0.25` s；warning `10` GiB；terminate `14` GiB；timeout `1800` s；no swap |

原始 watchdog summary 保持 `task037_extra_g2_slab14_factor_inventory_not_pass`，
外层 parent return code 为 `2`，唯一失败为
`task037_g2_factor_route_reduction_raw`。旧 checker 把 signed reduction 错限
为非负；它没有反映数值计算失败。patched checker 在
`e3447748391a902d27323bc796c008c8a1c8770b` 上只读同一 raw，结果为
`pass=true`、`failures=[]`、`34/34` G2 factor checks，且不改写原始 summary。

screen20 solver 以固定上限 `DIVERGED_MAX_IT(-3)` 结束；因此
`official_result=false`、`official_rta=false`，没有 official postprocess。这
个 screen 仍可作为 inventory 资格边界，不能作为收敛或物理结果。

## G2.3 collector 与 materialization

| 字段 | slab14 正式值 |
|---|---:|
| cells / unique blocks | `54 / 6` |
| full rows | `32724` |
| interior + trace rows | `24300 + 8424` |
| source / retained / dropped active columns | `23328 / 17064 / 6264` |
| partial cells | `18` |
| sparse `C` NNZ / bytes | `17064 / 434808` |
| primary / control / comparator | `14 / 5 / 13` |
| global A / global F | `false / false` |
| inventory-only / used in outer preconditioner | `true / false` |

完整 local block 和 trace rows 被保留，`C` 的 outside-slab active columns 作零
延拓；没有形成全局 uncondensed `A/F`。G2.3 因而是局部 inventory 测量，不能
被解释为已替换 16-slab preconditioner。

## retained-payload 对照

| inventory | current trace factor | full-space ILU(0)/RCM |
|---|---:|---:|
| rows | `8424` | `32724` |
| matrix NNZ / factor NNZ | `6086016 / 6086016` | `32378616 / 32378616` |
| matrix CSR payload | — | `647703220 B` |
| retained payload lower bound | `122023588 B = 116.37076187133789 MiB` | `648750388 B = 618.6965827941895 MiB` |
| full factor setup | — | `18.97298593702726 s` |

full/trace 比率为 `5.316598197391147`，差值为
`526726800 B = 502.32582092285156 MiB`。signed reduction 为
`-4.316598197391147`，表示 full-space retained payload 增加约 `431.66%`，
不是“下降 431.66%”。25% Gate 为 `false`，route 为
`close_fullspace_ilu_only_route`。这是关闭 plain full-space ILU-only 路线的
明确科学负结果；它不等于整个 G2 失败，也不等于其他未运行路线的结论。

## iter20 one-apply 结果

iter20 使用 solver 内部真实 `r=b-Ax`，owner-local residual norm 为
`0.42723143961943305`，trace RHS exact/finite。两种 correction 使用同一
owner row order 和 current shift：

| 字段 | current trace ILU | full-space ILU |
|---|---:|---:|
| input norm | `0.42723143961943305` | `0.42723143961943305` |
| post norm | `0.5385209372860695` | `0.7716852789816032` |
| rho | `1.2604899530937386` | `1.806246468352144` |
| correction norm | `0.8014811021173734` | `0.8237278810044446` |
| correction SHA256 | `892d7aa29811b0ccf403377af754fc448d1ba2dee914244a0ecb6c1deb8a9d40` | `02eea6f53e8a5df4f86b17826477a1826dff7a1ab9ff570e493f407d5ae9a72f` |

full-space minus trace rho 为 `0.5457565152584054`，ratio 为
`1.4329717296983637`；二者都大于 1，full-space 更差。full-space apply
两次且 finite/deterministic，耗时 `0.24651467008516192 s`；matrix assembly
为 `30.55818408995401 s`。

## 资源 authority 与阶段峰值

| 指标 | 正式 G2.3 authority |
|---|---:|
| process-tree RSS | `7647.62109375 MB = 7.468379974365234 GiB` |
| worker RSS / PSS / USS | `7633.734375 / 7582.0400390625 / 7537.23046875 MB` |
| swap | `0` |
| warning / termination / timeout | `false / false / false` |
| wall / samples | `349.65642845397815 s / 1267` |

现有 16 个 trace factors 在额外 oracle 期间仍保留，所以阶段峰值不是替代
候选的独立峰值：

| progress stage | process-tree RSS |
|---|---:|
| `g2_fullspace_matrix_assembly_started` | `7605.90625 MB` |
| `g2_fullspace_factor_setup_started` | `7605.91015625 MB` |
| `g2_fullspace_factor_setup_ready` | `7605.9609375 MB` |

## Evidence

紧凑 tracked record：
[g2_slab14_fullspace_factor_inventory.json](/home/shenjh/Projects/MyFEniCSx_task37_extra/benchmarks/cases/101_task37_extra_development/records/g2_slab14_fullspace_factor_inventory.json)。raw artifact 均在 ignored run directory；关键 hash 为：

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

## Pending

G2.4、G2.5、G2.6 均为 `pending_not_run`。本轮停止在 G2.3 inventory
measurement qualified / plain full-space ILU route closed；没有启动新的
PDE，也没有把本 compact evidence 解释为 global candidate、minimum
contraction、full solve 或 production promotion。
