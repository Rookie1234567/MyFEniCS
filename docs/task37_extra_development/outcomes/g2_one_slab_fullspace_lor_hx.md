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
| G2.4 LOR mesh/transfer | `pass_transfer_build_and_algebra_only` | 真实 slab14 的 LOR build、周期身份、重复 action 与伴随通过；不证明 HX/V-cycle 或收敛 |
| G2.5 LOR-HX/V-cycle | `pass_build_only` | 真实 p6/slab14 hierarchy build-only 通过；retained-payload memory signal 失败；未调用 1V/2V |
| G2.6 one/two V-cycle Gate | `measurement_qualified` | raw 完整、自洽且 finite/deterministic；minimum、strong 失败，apply-time overall false |
| G2 overall | `G2_FAIL` | minimum contraction 已失败；不是 `G2_PARTIAL`，不允许 rooted repair 或 G3 |
| G3 16-slab additive LOR-HX | `not_started_and_prohibited_by_G2_FAIL` | G2_FAIL 后禁止启动 |

`measurement_qualified` 只表示 raw 证据结构和数值闭合，不表示性能通过。正式整体
分类为 `G2_FAIL`：G2.6 的 iter20/mixed minimum contraction、iter0/iter20 strong
contraction、apply-time overall 以及 D3b retained-payload memory signal 均未通过。按照
任务书，G2_FAIL 不享有一次 rooted local repair，G3 标记为
`not_started_and_prohibited_by_G2_FAIL`。

## G2.4 fixture foundation

| focused fixture | 覆盖内容 | 阶段 commit |
|---|---|---|
| test258 | p2/p3 topology、edge orientation、constant/affine/curl-compatible field、`T/T^H` 与 cache | `d9ccb62` |
| test259 | multi-parent child-edge 去重、periodic Floquet identity、独立 cochain 与伴随 | `c6c8765` |
| test260 | owner-local full-space row packing、唯一 writer 与 `C` reconstruction | `9205ae1` |
| test261 | owner-local collector 与 MPI partition invariance | `817d8bb` |
| test262 | 真实 p2 Floquet `C` 与 LOR `E/T` crosscheck | `4d7bebe` |

在最终 source SHA `579c1912177411d1d5036a08f04c11661bc51965`，主审记录的
focused component tests 为：serial test258--262 `20 passed in 2.24s`；MPI2
test261+262 两 rank 各 `2 passed in 1.30s`。这些是组件合同测试，不是新 PDE。

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
| G2.2 full-space/trace identity deterministic-vector relative errors | `2.9248960201709676e-15`；`2.978578754981666e-15`；`2.6617554455542794e-15` |
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

## G2.4：真实 slab14 LOR transfer build 与 algebra-only audit

LOR（lowest-order refinement）把每个 p6 hexa parent 细化成 lowest-order
edge 网格；`T` 把独立 LOR edge cochain 连接到 p6 full-space stored
coefficients，`T^H` 是其精确伴随。本轮只证明真实 slab14 的 LOR 拓扑、周期
physical identity、可重复 action 与伴随关系能够构造并通过审计，不证明 HX 或
V-cycle 预条件器有效，更不证明外层 FGMRES 或物理量收敛。

### 运行身份与状态

| 项目 | 正式 C2b 值 |
|---|---|
| source SHA | `579c1912177411d1d5036a08f04c11661bc51965` |
| run directory | `benchmarks/artifacts/101_task37_extra_development/g2_slab14_lor_transfer_mpi1_screen20_579c1912` |
| scope | p6/h10/S、MPI1、M2c never-materialized、M3a overlap0.125 partition、screen20 |
| flags | identity + LOR；factor=false；G0 diagnostics=false |
| watchdog | `task037_extra_g2_slab14_lor_transfer_pass`；return `0`；failures `[]` |
| solver screen | 20 步，`DIVERGED_MAX_IT(-3)` |
| official result / RTA | `false / false`；postprocess skipped |

### identity 与 LOR audit

| 字段 | 正式值 |
|---|---:|
| owner / parent cells / unique blocks | `0 / 54 / 6` |
| full / interior / trace rows | `32724 / 24300 / 8424` |
| source / retained / dropped active columns | `23328 / 17064 / 6264` |
| partial / complete / incomplete trace rows | `18 / 17064 / 6264` |
| sparse `C` NNZ / bytes | `17064 / 434808` |
| physical / active / periodic-slave edges | `38304 / 36288 / 2016` |
| periodic relations | `2016` |
| matched / merged physical blocks | `93 / 401` |
| gathered identity blocks / high-order transform gathered | `401 / false` |
| unique parent transfer stencils | `2` |
| missing writer | `0` |
| shared trace / complete C max error | `1.7200665360018798e-15 / 9.56091885020216e-16` |

Identity hashes：

| identity | SHA256 |
|---|---|
| parent IDs | `ac7e3532a1ecf55826a25a99b1f5197fb7c9952a084bf88f4ca15bad79511023` |
| physical edge keys | `69b351698907f0067b09cf14c0f889d1566a86d1bcfec78d7a48121659635054` |
| active edge keys | `a359da92b3a781ff447f5bf81ce7dc845c1be022464948526ee489874c77010a` |
| owner active rows | `6f7c32c5fef8058a9c3a36deeaa65bce5f726c57c0d426220c065f683b57dade` |

G2.2 full-space/trace identity 的 3 个 deterministic vectors relative errors 为
`2.9248960201709676e-15`、`2.978578754981666e-15`、
`2.6617554455542794e-15`；均 finite、deterministic、gate pass。iter20 使用
solver 内部真实 `r=b-Ax`，owner-local norm 为 `0.42723143961943305`，
identity error 为 `1.7721399154913289e-15`，residual vector SHA256 为
`3aa610ed9bbb63047188b64d21d5dcab04184ffc6316196458e99aab520bb195`。
current local shift count/norm/hash 为 `8424 / 475.7236793796778 /
986bfe37dbc54cabd71ac2fd83dbd10df7adc69fe53c3bd030935dfa7017fec9`。

LOR measurement 使用 7 次 forward apply 和 1 次 adjoint apply；结果 finite、
deterministic，adjoint relative error 为 `1.5008209190777043e-14`，build 用时
`49.17991871200502 s`。global dense `T`、condensed trace matrix、global `A/F`
均未物化。

### residual 与 official 边界

| iteration | true residual | reported residual |
|---:|---:|---:|
| 0 | `1.0` | `1.0` |
| 10 | `0.14446444295860594` | `0.14446444295860714` |
| 20 | `0.04474243612765` | `0.04474243612765121` |

`DIVERGED_MAX_IT(-3)` 是 screen20 的固定步数边界，不是 LOR identity 失败。
因此本轮没有 official field、official RTA 或物理后处理，也不能把 watchdog
status 解读为 G2 overall pass。

### 资源口径

progress event 的 rank RSS 为：started `1060.25 MB`，ready
`1166.61328125 MB`，差 `106.36328125 MB`。watchdog 的
`stage_peaks[g2_lor_transfer_build_started]` 覆盖真实 LOR build 区间，
process-tree max 为 `1180.4296875 MB = 1.1527633666992188 GiB`，worker max
为 `1166.61328125 MB`。

名称为 `stage_peaks[g2_lor_transfer_build_ready]` 的
`4877.80078125 MB` 采样区间从 ready 事件延续到 `all_slab_factors_ready`，
包含随后既有 16-slab trace-factor setup；它不是 LOR build/ready 峰值。

whole-run authority 为 process-tree `4920.34765625 MB = 4.805027008056641
GiB`；worker RSS/PSS/USS 为 `4906.53125 / 4855.1728515625 /
4810.64453125 MB`，swap `0`。同机较旧 G2.2 identity authority 为
`4655.9453125 MB = 4.546821594238281 GiB`，差 `264.40234375 MB`（约 5.68%）；
由于 source SHA 不同，这只能作同机背景，不能归因成纯 LOR retained 增量。

retained numeric payload lower bound 为 `18735740 B = 17.867794036865234
MiB`，只包含 T/Tᴴ/E/Eᴴ/packing/reference CSR arrays，不是 RSS，也不含
Python object 或 allocator 开销。

### raw evidence

compact record：[g2_slab14_lor_transfer.json](/home/shenjh/Projects/MyFEniCSx_task37_extra/benchmarks/cases/101_task37_extra_development/records/g2_slab14_lor_transfer.json)。raw 均保留在 ignored run directory：

| raw 文件 | SHA256 |
|---|---|
| `watchdog_summary.json` | `41e148b957b3fcba3ebc06c27e6b11c9c7a5736e3b82b258a117b200a9b300ec` |
| `run_summary.json` | `aefc2a7b3503b4e15114a1a7299e8fff02957c59aa2eaa3c3073d867dd394631` |
| `task037_f3_core_audit.json` | `8bd07800ecaa5615937f7f74c546e66bf2e7a2f4256eb51f5d7dd49024585e85` |
| `progress_3d.jsonl` | `dcc0ff8dd12862d4b17ec5806f71054d080d7c295388b27a825e2be2872e2aed` |
| `memory_timeline.csv` | `8d8624ee3fbc0bd4dd5a02033728069fd1712e0fdbfdb07919df0f2e37257efb` |
| `task037_f3_residual_history.jsonl` | `75f0bc3ebec3648b60fdfc55daa9afd036b81cf6d5fe0ef1f7051a83e0f24940` |
| `parent_launch_descriptor.json` | `e4cf1db4daf1597eec562838cd32840b46dac436ab00673ae57195271e367423` |
| `worker_stdout.txt` / `solver_log.txt` | `0ad5399df6b37c9643175c6cec172a330c62cbe31dc6b80c37344b82776dd979` |
| `NO_OFFICIAL_FIELD_OUTPUT.txt` | `e11465d92e416af3e4321c581b7291b7d4df5c932b425541f9b0114e259d3f38` |

## G2.5 D3b：真实 p6/slab14 LOR-HX build-only（历史阶段记录）

### 这次 build-only 检查解决什么问题

固定 low-storage V-cycle 是一种局部近似逆：它先用便宜的细层 Jacobi 修正，再用标量
H1 梯度和向量 H1 辅助空间修正，最后只在很小的最粗层保留精确因子。这样做的目标是
避免在 p6 trace 或大 LOR 层保存大 ILU；代价是要常驻转移矩阵、H1 层级和两个最粗层因子，
并支付较长的 setup 时间。本轮只构建并盘点这些对象，没有执行任何 V-cycle，因此不能从
本轮推断它是否能缩小真实残差。

| 项目 | D3b 正式值 |
|---|---|
| source / scope | `c7c7a26c1946a9244845c6423872e5fe69095289`；p6/h10/S、MPI1、screen20 |
| run directory | `benchmarks/artifacts/101_task37_extra_development/g2_slab14_lor_hx_build_mpi1_screen20_c7c7a26` |
| watchdog | `task037_extra_g2_slab14_lor_hx_oracle_pass_build_only`；return `0`；failures `[]`；swap `0` |
| flags | identity=true；LOR transfer=true；LOR-HX oracle=true；factor-inventory=false；G0=false |
| solver boundary | 20 步 `DIVERGED_MAX_IT(-3)`；true residual `0.04474243612765`；reported `0.04474243612765121` |
| official result / RTA | `false / false`；postprocess skipped；这不是 solver convergence |
| global materialization | global A/F=false；exact outer unchanged |

正式运行实际由 raw `watchdog_summary.command` 记录的 worker command 执行；该字段和
`parent_launch_descriptor.json` 已分别 hash 绑定。独立 parent shell command 没有在 raw 中
另存一份，因此本记录不伪造 parent command。

### identity、material 与 storage

| 字段 | 值 |
|---|---:|
| primary / owner / parent cells | `14 / 0 / 54` |
| full / interior / trace rows | `32724 / 24300 / 8424` |
| active LOR rows | `36288` |
| parent ID hash | `ac7e3532a1ecf55826a25a99b1f5197fb7c9952a084bf88f4ca15bad79511023` |
| physical edge hash | `69b351698907f0067b09cf14c0f889d1566a86d1bcfec78d7a48121659635054` |
| active edge hash | `a359da92b3a781ff447f5bf81ce7dc845c1be022464948526ee489874c77010a` |
| transfer retained payload | `18735740 B` |
| D2c hierarchy payload | `3109473612 B` |
| total retained numeric payload lower bound | `3128209352 B = 2983.2929153442383 MiB = 2.9133719876408577 GiB` |
| factor inventory | total `2`；coarsest-only=true |
| large/fine factors | fine p6 trace/full/intermediate/large LOR 全为 `0` |
| object lifetime | HX 完成后 parent topologies、persistent full/LOR RHS、global dense 均为 `false` |
| physical proxy | affine volume only；curl coefficient `(1, 0)`；material tags `1/3` 有 complex mass coefficient；no DtN surface proxy |
| shift / p6 interpretation | `diag <- diag - 1j*0.1*max(abs(diag), 1e-12*max(abs(diag)))`；`literal_p6_shift_galerkin=false`；不是 coercivity 结论 |

三类 identity 仍继承已审查的结果：真实 iter20 owner-local `r=b-Ax` 的 norm2 为
`0.42723143961943305`，SHA256 为
`3aa610ed9bbb63047188b64d21d5dcab04184ffc6316196458e99aab520bb195`；3 个 deterministic
vectors 与 identity Gate 通过。transfer 的 `parent_id_hash`、physical edge hash、active
edge hash 与 identity raw 完全一致。

### memory signal：明确失败，但不作整体 G2 分类

任务定义的同口径 trace-ILU baseline 是 `122023588 B`，其 `0.60` threshold 为
`73214152.8 B`。D3b total hierarchy retained payload 为 `3128209352 B`：

| 指标 | 实测/派生值 |
|---|---:|
| HX / trace baseline | `25.63610366874313` |
| HX / 0.60 threshold | `42.72683944790521` |
| memory signal | `FAIL` |
| 含义 | build-only hierarchy 明显超过最低存储目标，不能称 memory positive |

这是 D3b 当时的资源信号失败；当时 contraction 尚未运行，故该阶段记录保持
`not_claimed`，不改写历史阶段语境。本数字是 retained numeric payload lower bound，
只包括 T/TH/E/EH、packing、reference CSR、H1 hierarchy、inverse diagonal 和最粗层因子
的数组口径，不等同 RSS，也不包括 Python object/allocator/permutation overhead。

### build 时间、资源与 lifecycle

| 阶段/指标 | raw authority |
|---|---:|
| transfer build | `43.800458488985896 s` |
| HX build | `571.4551421470242 s` |
| transfer interval process-tree max | `1186.52734375 MiB` |
| HX build interval process-tree max | `5528.63671875 MiB` |
| whole-run process-tree RSS | `7964.97265625 MiB = 7.778293609619141 GiB` |
| worker RSS / PSS / USS | `7951.1875 / 7899.833984375 / 7855.32421875 MB` |
| worker/process-tree swap | `0 / 0 MB` |
| sample count / poll | `3250 / 0.25 s` |
| run elapsed | `832.8251509650145 s` |
| historical container cgroup peak | `13279.546875 MB`；不是本次 authority |

`stage_peaks[g2_lor_hx_build_ready]` 的 raw process-tree max 为 `7923.4296875 MB`，
但该区间继续覆盖后续 existing trace-factor setup，不能称 HX build/ready 峰值。有效的
HX build 区间以 `g2_lor_hx_build_started` 为 authority。四个 lifecycle stage
`g2_lor_transfer_build_started/ready` 和 `g2_lor_hx_build_started/ready` 均存在。

### contraction 明确未运行

| 量 | 1V | 2V |
|---|---|---|
| apply count | `not_run` | `not_run` |
| rho | `not_run` | `not_run` |
| apply time | `not_run` | `not_run` |

因此没有 one/two-cycle contraction 结论，也没有进入 G2.6 或 G3。

### 首次 launch 负证据

第一次 launch 在 PDE 前使用了根目录空 `.git` 挂载，tracked-authority 检查失败，未创建
run directory，也未开始数值工作。这不是数值 retry；随后成功运行在同一 shell 显式设置
`GIT_DIR=.git-codex` 和 `GIT_WORK_TREE`。首次受控失败保留为 provenance 事实，不改写为普通调试。

### D3b raw evidence

以下 SHA 均由成功 run directory 中的原文件直接计算；网格和说明文件也列出 hash，但不把它们
当作数值 Gate：

| raw 文件 | SHA256 |
|---|---|
| `watchdog_summary.json` | `d1f470e42914752e490d363a7107f1bf1b2d593f94e10f4d81d80ccf88d3bb1a` |
| `run_summary.json` | `4486e1fead530bcd5b859183269adb2dfde5353a6592f556b02ebc3c8134f6af` |
| `task037_f3_core_audit.json` | `b6b12fa31c48d863431bb72e26a7a84a51f8c237d26ee2347b382cab30e7ba67` |
| `progress_3d.jsonl` | `0a9b4345646ae3bf1cdc6681f4f6786a454b0f2f666394e9913d6b20e57ddd34` |
| `task037_f3_residual_history.jsonl` | `75f0bc3ebec3648b60fdfc55daa9afd036b81cf6d5fe0ef1f7051a83e0f24940` |
| `memory_timeline.csv` | `71be2609b821897d81f275786d00c08180c68b6a2202625cbf72d0e2810c2722` |
| `parent_launch_descriptor.json` | `fcb9e4e6a18ddf9ca1c049c361b0fee393c4eb5eeb05f055c4cdb6d40d09daa7` |
| `worker_stdout.txt` | `5a7b9cbe88dfef87a463a421d395a7e3e59f4d258f8172a32c49caee120d4bd8` |
| `solver_log.txt` | `5a7b9cbe88dfef87a463a421d395a7e3e59f4d258f8172a32c49caee120d4bd8` |
| `NO_OFFICIAL_FIELD_OUTPUT.txt` | `e11465d92e416af3e4321c581b7291b7d4df5c932b425541f9b0114e259d3f38` |
| `mesh_3d.h5` | `71c17d7e60beb920922bcaabc178078959ec48d5ec257aaabe42d14c64102a3b` |
| `mesh_3d.xdmf` | `e40e1b05f3269101fe93e96416481f14bcaa64fb1df5f030381c747b484b9864` |
| `mesh_3d_partition_note.txt` | `0a3e481d76798fa867ac1151dee5b3899920e623606faf36f175ee670c9ed974` |

## G2.6 D3c：真实 p6/slab14 LOR-HX contraction measurement

### 这次 measurement 检查解决什么问题

V-cycle 是一次固定的局部近似逆：1V 或 2V 依次做边缘 Jacobi、标量 H1 修正、向量
H1 修正和最粗层小因子修正。这里的 `rho` 是 exact shifted full-space Schur action
作用 correction 后的残差范数除以输入残差范数；`rho<1` 表示缩小该方向，`rho>1`
表示放大。`measurement_qualified` 只说明这四种方法的 raw 作用、重复性和派生字段
一致，不能把 finite/deterministic 当作预条件器有效。

| source | current trace ILU rho | B4 GMRES(4) rho | LOR-HX 1V rho | LOR-HX 2V rho | best LOR-HX |
|---|---:|---:|---:|---:|---:|
| real M3a iter0 | 2.422027189163481 | 0.9440411915945912 | 5611759.4667701805 | 4885392465721929.0 | 5611759.4667701805 (1V) |
| real M3a iter20 | 1.2604899530937386 | 0.755818683406265 | 3465823.613309288 | 1651097278181490.5 | 3465823.613309288 (1V) |
| normalized manufactured mixed/high | 4.455510654442446 | 0.8584226047142137 | 61738549.74675689 | 1.4084260534619966e16 | 61738549.74675689 (1V) |

iter0 与 iter20 是 M3a screen 的真实 `r=b-Ax`；它们不是 B4 i200 或 long-tail
residual。B4 long-tail raw 本轮未单独测量。任务要求的 mixed/high source 已单独测得
best rho `61738549.74675689`，远大于 `(2/3)*0.8584226047142137`，所以 task-level
minimum signal 已确定失败，不依赖未测的 B4 long-tail source，也不为 hard stop 补跑。
iter20 另有 G2.3 full-space p6 ILU 对照 `rho=1.806246468352144`，来自
不同 run，但使用相同 residual hash `3aa610ed9bbb63047188b64d21d5dcab04184ffc6316196458e99aab520bb195`，不能伪装成当前 run 的同一 timing sample。

| measured gate | threshold | result |
|---|---|---|
| minimum：iter20、mixed/high | `rho_LORHX <= (2/3) rho_B4` | `false / false` |
| strong：iter0、iter20 | `rho_LORHX <= 2 rho_ILU` | `false / false` |
| apply-time：每源至少一个 1V/2V <= 10x ILU | ratios `312.2772206993064/4.246395389906666`、`1842.4615404593533/81.26242051814305`、`1.272784014360302/1.4723523740894053` | `true / false / true`；overall `false` |

1V best 仍约为 `5.61e6`、`3.47e6`、`6.17e7`，2V 更差；这不是边界误差。所有 rho
由 `apply_fullspace_slab_schur_action` 得到，而不是 LOR proxy 自评。

### build、storage 与资源闭合

| 项目 | 正式值 |
|---|---:|
| source SHA / scope | `30e179799b8eb6dee1be1bb976002550424bb40d`；p6/h10/S、MPI1、screen20 |
| watchdog / return / qualification | `task037_extra_g2_slab14_lor_hx_contraction_measurement_qualified` / `0` / `pass` |
| full/interior/trace rows | `32724 / 24300 / 8424` |
| cells / active LOR rows | `54 / 36288` |
| transfer / D2c hierarchy / total retained payload | `18735740 / 3109473612 / 3128209352 B` |
| factor inventory | `2`，coarsest-only；fine p6/full/trace/intermediate/large LOR 均 `0` |
| build seconds | transfer `51.72637021099217`；HX `607.4379243750591` |
| process-tree authority | `8333.12890625 MB = 8.137821197509766 GiB` |
| worker RSS/PSS/USS | `8319.29296875 / 8267.7822265625 / 8223.19140625 MB` |
| swap / warning / termination / timeout | `0 / false / false / false` |

物理对象是 affine volume proxy：curl coefficient `(1,0)`，material tags 1/3 有
complex mass coefficient；无 DtN surface proxy，非 literal p6 Galerkin，exact outer
operator 未改变。global dense matrix、parent topologies、persistent full/LOR RHS 均未保留。

同口径 trace-ILU baseline 是 `122023588 B`，`0.60` threshold 是 `73214152.8 B`；
HX/trace=`25.63610366874313`，所以 retained-payload memory signal 为 `FAIL`。
这是数组下界，不是 RSS，也不含 Python object/allocator/permutation overhead。
`g2_lor_hx_build_started` 区间 process-tree peak 为 `5529.8125 MB`；
`g2_lor_hx_build_ready` 的 `7924.58984375 MB` 还覆盖随后既有 trace-factor setup，
不能称纯 HX build peak。whole-run authority 为 `8.137821197509766 GiB`，historical
cgroup peak `13279.546875 MB` 不是本次 authority。

### G2_FAIL 与停止边界

本轮 raw status 是 `measurement_qualified`，但它不是性能 pass。minimum contraction
失败已经触发任务书的科学 hard stop；同时 strong、apply-time 和 memory signal 也失败。
因此最终分类是 `G2_FAIL`，不是 `G2_PARTIAL`，不提出 rooted local repair，不 sweep，
不进入 G3。没有 official field、official RTA 或物理收敛结果。

### D3c raw evidence

compact record：[g2_slab14_lor_hx_contraction.json](/home/shenjh/Projects/MyFEniCSx_task37_extra/benchmarks/cases/101_task37_extra_development/records/g2_slab14_lor_hx_contraction.json)。run directory 为 `benchmarks/artifacts/101_task37_extra_development/g2_slab14_lor_hx_contraction_mpi1_screen20_30e17979`；关键 raw SHA256：

| raw 文件 | SHA256 |
|---|---|
| `watchdog_summary.json` | `b52125f40f946da4bbf792174224beb4a1526c1d20eab04e3b3bc748da95b2f4` |
| `run_summary.json` | `a6e53c655f896ddb26de3ef86fd39e147da3b74bfda558fd4998870e9ec32f65` |
| `task037_f3_core_audit.json` | `a87537cc899d3ae6df8068a8f797fbd5da4061e32e7400c32d20f33e3595f9e4` |
| `progress_3d.jsonl` | `db8c0f2e8de7f6924dc953b65026f74abfc304c1f0eda8d43fb0c49f2664227d` |
| `memory_timeline.csv` | `ca7ff04921b5be4e8b1cb31f356f7baff9eda1203479f0ca666fe9b193759dad` |
| `task037_f3_residual_history.jsonl` | `75f0bc3ebec3648b60fdfc55daa9afd036b81cf6d5fe0ef1f7051a83e0f24940` |
| `parent_launch_descriptor.json` | `19854ce17d27bfe2fde1e6dfb4de280249fc4f49ddad4605c29542094c756b57` |
| `worker_stdout.txt` / `solver_log.txt` | `a6a3509af15b95064729acfd1ba0c1904b44fb14826d4a4b6c9e6663b50a5dde` |
| `NO_OFFICIAL_FIELD_OUTPUT.txt` | `e11465d92e416af3e4321c581b7291b7d4df5c932b425541f9b0114e259d3f38` |

## Closed stop

G2.5 的 build-only 结果、G2.6 的 measurement-qualified raw、G2.3 的
`inventory_measurement_qualified / plain full-space ILU route closed` 以及 G2.4 的
transfer/algebra-only 结果均保留。当前 overall 已闭合为 `G2_FAIL`；G2.5/G2.6 不再是
当前 pending，G3 为 `not_started_and_prohibited_by_G2_FAIL`。本 outcome 不声称
production promotion、full solve 或 G2 overall pass。
