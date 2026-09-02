# Task040 Review V9 response v10

## 当前总裁决

本响应只整理已存在的 raw evidence，不重跑任何 route，也不把后续实现计划写成结果。

| 项目 | 当前状态 | 说明 |
|---|---|---|
| Task040 response status | `OPEN_AWAITING_REVIEW` | 表示本轮文档结束后等待 review，不改写 Review V9 历史中的 `OPEN_CONTINUE` |
| selective merge | `NO` | 未取得可合并的 production numerical/core candidate |
| master merge approval | `NO` | 不合入 master |
| stop Gate | fallback 无 qualified physical positive + structured implementation budget exhausted + physical LOR external numerical no-signal | V9-E 双入口已成立；fallback 仍未取得 qualified physical positive |

“static condensation”在这里是把单元内部未知量先消去，只保留边界/接口未知量；它可以降低接口问题规模，但不能替代完整残差证据。文中所有 `measured`、`failed`、`not_run` 和 `controlled` 均保持该语义。

### 四个机制的通俗解释

| 机制 | 解决的问题 | 代价与边界 |
|---|---|---|
| canonical bridge | 按物理实体而非 MPI raw 行号对齐源值，避免 rank 重排造成错配 | 需要维护 key/packet；只证明 source identity，不证明求解收敛 |
| full-spectrum transform | 把有限元 trace 转到完整 Floquet channel/harmonic 网格，检查多模传播方向 | 需要更大的变换与 screen 计算；本次两源结果为 no-signal |
| adaptive coarse | 汇总局部 patch 成较小粗空间，尝试降低全局侧向对象内存 | 粗对象仍可能触发资源闸门；本次没有完整 outer residual |
| fixed LOR | 用固定低阶局部 trace 逆作 right preconditioner，减少高阶局部因子压力 | 这是近似 PC，不改变物理算子；h10/h5 不能替代 V9-E 主 Gate |

## 身份绑定

| 身份 | 值 |
|---|---|
| Review/source base | `fdfd7046c2d8ec37b5b6e353733266b98c45321` |
| pre-docs HEAD | `3bf9441425ca2dd4967551d5a43b2c7031049c0f` |
| branch | `codex/20260822-task40-hybrid-side-factor-pc` |
| upstream | `origin/codex/20260822-task40-hybrid-side-factor-pc` at `3bf9441425ca2dd4967551d5a43b2c7031049c0f` |
| worktree at documentation start | clean；本轮文档写入后按预期变为 dirty |

本响应不能自引用本轮最终 docs commit SHA；最终交接报告提供该 SHA。这里保留的是 formal
source SHA 与 pre-docs HEAD，不把未来提交身份提前写入 evidence。

### fdfd…3bf 的关键阶段

下表列出与 V9 evidence 直接相关的关键提交，不把它当作完整 commit listing；完整历史仍由 Git 保存。

| commit | 阶段 |
|---|---|
| `9c18f88d..4e857fcd` | source bridge / full-spectrum |
| `9eac1797..43729bc3` | C0 |
| `06021c2a..ec8eaaea` | structured / tiny |
| `21b583b8..3bf94414` | LOR / external |

### Source bridge 与 corrected full-spectrum 的 formal identity

两次 formal 均为 MPI8、threads=`1`，使用 native marker=`1`、仓库 `.venv` Python、
PETSc `complex128` / `int32`；两次 p6h4 输入身份均为 input SHA
`4e60924b5997e3ca99e324ea14779f9014efc6a1304a9aa11de9c808353f1811`、physical SHA
`8391d46139646440d869aa43abe6a68bc921fc1972a10030c64be81dffdd527c`、resolved config SHA
`f965c38abea08bee0ff83a6603e336ca4823deb932af7064aed3c571f8f63883`。

source bridge 的 raw worker 命令为：

```text
mpiexec -n 8 /home/fenics/Projects/MyFEniCS/.venv/bin/python -m benchmarks.task040_level_a --input /home/fenics/Projects/MyFEniCS/input/official/task039/5nm_p6h4_v4_1deg_hybrid_iterative_m480_mpi8.dat --exact-spool-root /home/fenics/Projects/MyFEniCS/results/task040_v5_2_fresh_bare_f_authority_mpi8_fd7bea41/worker/bare_f_authority --run-directory /home/fenics/Projects/MyFEniCS/results/task040_v9_source_bridge_mpi8_17cf5ae2_native_fix1/worker --source-sha 17cf5ae28ccdcf7b0a28548ec1296b9956390509 --memory-stages /home/fenics/Projects/MyFEniCS/results/task040_v9_source_bridge_mpi8_17cf5ae2_native_fix1/memory_stages.jsonl --memory-markers /home/fenics/Projects/MyFEniCS/results/task040_v9_source_bridge_mpi8_17cf5ae2_native_fix1/memory_stage_markers.raw.jsonl --v9-source-bridge-only --watchdog-hard-stop-bytes 48318382080 --watchdog-enabled --bottom-route-only
```

corrected full-spectrum 的 raw worker 命令为：

```text
mpiexec -n 8 /home/fenics/Projects/MyFEniCS/.venv/bin/python -m benchmarks.task040_level_a --input /home/fenics/Projects/MyFEniCS/input/official/task039/5nm_p6h4_v4_1deg_hybrid_iterative_m480_mpi8.dat --exact-spool-root /home/fenics/Projects/MyFEniCS/results/task040_v5_2_fresh_bare_f_authority_mpi8_fd7bea41/worker/bare_f_authority --run-directory /home/fenics/Projects/MyFEniCS/results/task040_v9_full_spectrum_mpi8_4e857fcd_native_fix1/worker --source-sha 4e857fcdf73caa94805cd255bf7aad44ea4f95f1 --memory-stages /home/fenics/Projects/MyFEniCS/results/task040_v9_full_spectrum_mpi8_4e857fcd_native_fix1/memory_stages.jsonl --memory-markers /home/fenics/Projects/MyFEniCS/results/task040_v9_full_spectrum_mpi8_4e857fcd_native_fix1/memory_stage_markers.raw.jsonl --v8-full-spectrum-only --v9-source-packet-root /home/fenics/Projects/MyFEniCS/results/task040_v9_source_bridge_mpi8_17cf5ae2_native_fix1/worker --v9-source-packet-manifest-sha256 98610d2826342b963e0243ff57dd53753a82d0379021c89130069a9a0900ebd0 --watchdog-hard-stop-bytes 48318382080 --watchdog-enabled --bottom-route-only
```

## V9 route evidence

| 路线 | classification | measured / failed / not_run / controlled 事实 |
|---|---|---|
| source canonical bridge | measured component pass | canonical keys/packet identity与roundtrip机制通过；不等于 two-source solve |
| full-spectrum | `FULL_SPECTRUM_SWEEP_NO_SIGNAL` | transform pass；actual lower/upper=`7560+7560`，`72 channels × 105 harmonics`；两源 one-apply/r8/r16/r32/r64齐全，strict no-signal |
| adaptive Stage A | `V8_ADAPTIVE_STAGE_A_LOCAL_GATE_PASS` | 630 patches、432 rows；local service通过；global true residual=`2.390497409724407` 仅为完整算子诊断 |
| adaptive Stage B/C | `ADAPTIVE_ECONOMICAL_COARSE_RESOURCE_UNAVAILABLE` | symbolic projection=`130502065136 B`=`121.539519295 GiB`，超过45 GiB；无 source/outer residual |
| C0 explicit coarse | worker numerical no-signal measured；watchdog terminal resource metadata gap | worker `rho_coarse=6.778773552009804`、`rho_local=2.390497409724407`；watchdog raw gap仅影响资源元数据，不推翻数值 Gate |
| C1 matrix-free Galerkin | `not_run_by_numerical_gate` | C0 numerical no-signal 已形成；旧 watchdog next=C1及resource gap仅作元数据保留 |
| B0/B1 tiny | measured component identity evidence；B0/B1 improvement Gate `>=8` 已通过 | serial B0 best=`0.032778129179444594`、final=`7.473487968169046e-15`、improvement=`4385921181522.289`、`b0_positive=true`；MPI2 B0 best=`0.032776771424794904`、final=`7.844174153538335e-15`、improvement=`4178485941698.5303`、`b0_positive=true`；serial B1 best=`0.032778129179444594`、final=`1.7990718431044546e-14`、improvement=`1821946650161.7349`、direct=`1.6039075528205737e-14`、`b1_positive=true`、`direct_identity_pass=true`；MPI2 B1 best=`0.032776771424794904`、final=`1.5332004278102346e-14`、improvement=`2137800826967.3997`、direct=`2.1440084159556094e-14`、`b1_positive=true`、`direct_identity_pass=true`；因此流程上具备进入 reduced 5 nm pilot 的依据，但仅是 tiny component identity evidence，无 formal JSON/hash，绝不是 physical formal positive |
| S3 dynamic action | infrastructure/approximation evidence | matched formal S3a off-block ratio=`0.1241–0.2308`；audited approximation，不是 positive solver signal |
| LOR L2 h10 | local formal action-screen measured pass | explicit residual=`9.49183402945266e-9`，211 iterations；component evidence，不替代 V9-E 主 Gate |
| LOR L2 h5 | local formal action-screen measured fail | fixed 256 iterations、reason=`-3`、explicit residual=`3.743078556589845e-7`；h5 refinement/action-screen negative，不外推为 h-independent conclusion |
| physical bare-F external old root | controlled implementation/authority failure | root `..._18b00b58_native` 保留，不改写 |
| physical bare-F external corrected root | worker no-signal；watchdog unresolved | worker explicit residual=`0.7349227023138162`；watchdog raw resource authority未闭合 |
| five-source/top/both-side/full Hybrid/recovery/RTA | `not_run` | 没有满足继续条件 |
| qualified Full3D architecture candidate | `NOT_ESTABLISHED` | V9-E入口成立，但无 qualified physical positive；handoff 文档记录边界，非已建立候选 |

上述 B0/B1/S3/LOR 和 external pilot 结果均为 component/formal evidence；不把 tiny/component 结果冒充 physical positive。V9-E 双入口由 full-spectrum 与 C0 的真实 numerical no-signal 构成。

source bridge 的双源 key/value digest 与全部固定 `1e-12` Gate 的逐字段 raw 表见
[source outcome](outcomes/v9_source_canonical_bridge.md)。

## Formal Git provenance coverage

| formal / roots | raw Git provenance coverage |
|---|---|
| source bridge `17cf5ae28ccdcf7b0a28548ec1296b9956390509` | raw 明确 branch exact、upstream_sha=source、ahead/behind=`0/0`、worktree clean |
| full-spectrum `4e857fcdf73caa94805cd255bf7aad44ea4f95f1` | raw 明确 branch exact、upstream_sha=source、ahead/behind=`0/0`、worktree clean |
| C0 `3564fe3ea491d1393e9e3d6741114fbbefc0ddc9` | raw 明确 branch exact、upstream_sha=source、ahead/behind=`0/0`、worktree clean |
| S3 `7bfef8e9e7abdbed0f25c1d5f487d41d601df318` / `8b9fb0b8a21e47942260ffee89106a41ad2ceb02` / `e2ec5e4a66430e85ac1c7f7e49cc013b2063dd19` | raw 有 source SHA；branch/upstream/worktree 未序列化 |
| LOR L2 h10/h5 `8c19b841a388cd5b4e2f785d79d791fabe4db021`；external `788966983f436625bccd732e373f55766bc77a08` | worker/watchdog 有 source SHA；branch/upstream/worktree 未序列化 |
| tiny B0/B1 | 不是 formal JSON，不纳入“每个 formal Git 字段已序列化” |

“未序列化”是证据覆盖缺口，不改写 numerical 结果。当前 docs 提交的最终
branch/upstream/clean 由最终交接报告提供；上述三个 outcome 的详细表仍以
各自 raw evidence 为准。

## Corrected full-spectrum formal detail

| 项目 | 实测值 |
|---|---|
| root / source / classification | `results/task040_v9_full_spectrum_mpi8_4e857fcd_native_fix1` / `4e857fcdf73caa94805cd255bf7aad44ea4f95f1` / `FULL_SPECTRUM_SWEEP_NO_SIGNAL` |
| execution / transform | `executed=true`；lower/upper=`7560+7560`；`72 × 105`；transform pass；`numeric_allgather=false` |
| external checkpoints | one=`2.4925577678654536`；r8=`1.0847758611958496`；r16=`1.0337741915450838`；r32=`1.0000192505910723`；r64=`0.9969676750006529` |
| external 32→64 | `0.0013272830728985237` |
| random0 checkpoints | one=`64.24596183468168`；r8=`6.295285267481751`；r16=`5.81369638252774`；r32=`5.707565383934817`；r64=`5.534173218910557` |
| random0 32→64 | `0.013398146942032231` |
| lifecycle / resource | action=`142`；PC=`130`；factors ready/simultaneous=`3`；cleanup=`0`；natural；wall=`1013.0478316960507s`；peak RSS=`37884526592B`；swap=`0` |
| hashes | run=`e5b6db01b84344f70b29f0e129aae67b9b80202b1efde36f61e7aa4e08816af2`；watchdog=`ed02b43b723acc881fec7746af6293de90c420453aed1d62f2f07fcd69a5fc19`；markers=`ebcab72d0bbaa1d4d263f6368121b30686a023053a3a1ff13903040b63f31008`；stages=`7e0966ef750b7a2b14ac694a599ca0830f0cba3724621fe27beb39fbe9b234d0`；samples=`813924a7f8382d79d3dfc02617731b9fe82a2cb697f2f7bac6b11bdaa33eb357` |

两源 r64 均大于 `0.8`，且 32→64 drop 均小于 `0.10`，所以这是 measured strict numerical
no-signal；`rhs_vectors_loaded=2`、`exact_output_vectors_loaded=0` 是本轮禁止 exact-output
producer 的预期值，不是 source integration failure。

V9 corrected full-spectrum 的 current marker、owner-vector 和 factor inventory
明细见 [full-spectrum outcome](outcomes/full_spectrum_floquet_sweep.md)。

## C0 raw authority（不可改写）

C0 使用与 p6h4 source/full-spectrum formal 相同的 current input identity：input SHA
`4e60924b5997e3ca99e324ea14779f9014efc6a1304a9aa11de9c808353f1811`、physical SHA
`8391d46139646440d869aa43abe6a68bc921fc1972a10030c64be81dffdd527c`、resolved config SHA
`f965c38abea08bee0ff83a6603e336ca4823deb932af7064aed3c571f8f63883`；MPI8、threads=`1`、
native marker=`1`、repository `.venv`、PETSc `complex128`/`int32`。这些身份与 worker
provenance 绑定；C0 raw watchdog 的资源字段仍不构成 authority-qualified resource pass。

| 字段 | worker `run_summary.json` | watchdog `watchdog_summary.json` |
|---|---|---|
| root | `results/task040_v9_c0_explicit_coarse_mpi8_3564fe3e_native` | 同左 |
| method | `task040_v9_c0_explicit_coarse_oracle` | 同左 |
| result | `status=complete`；`CURRENT_160_PER_PATCH_HARMONIC_COARSE_NO_SIGNAL` | `return_code=0`，natural exit |
| one apply | finite；wall=`239.8155699960189s`；relative=`6.778773552009804` | raw resource rows readable/pass；terminal authority gap仅影响 watchdog resource metadata |
| outer | `outer_record=null`；`r8=null`；outer solver未建立 | 不得把 `v9_c0_outer_checkpoint` marker当 outer residual |
| resource | worker one-apply resource rows `all_status_readable=true`、`pass=true`、swap=`0` | raw final classification=`ADAPTIVE_COARSE_EXPLICIT_RESOURCE_OR_TIME_UNAVAILABLE`；这是 terminal metadata gap，不是对 worker 数值 Gate 的改写 |
| next | worker label指向 `V9_E_STRUCTURED_BACKGROUND_FIXED_LOR` | watchdog raw/non-governing next metadata=`V9_C1_MATRIX_FREE_GALERKIN_COARSE` |

worker 的 no-signal 是实际 one-apply 数值观察；watchdog 的 resource/time metadata gap 也是真实 raw 事实。两者并列，不能把 watchdog gap改写为 resource pass，也不能用它推翻已形成的 C0 numerical Gate。

### C0 命令、结构和生命周期

```text
mpiexec -n 8 /home/fenics/Projects/MyFEniCS/.venv/bin/python -m benchmarks.task040_level_a --input /home/fenics/Projects/MyFEniCS/input/official/task039/5nm_p6h4_v4_1deg_hybrid_iterative_m480_mpi8.dat --exact-spool-root /home/fenics/Projects/MyFEniCS/results/task040_v5_2_fresh_bare_f_authority_mpi8_fd7bea41/worker/bare_f_authority --run-directory /home/fenics/Projects/MyFEniCS/results/task040_v9_c0_explicit_coarse_mpi8_3564fe3e_native/worker --source-sha 3564fe3ea491d1393e9e3d6741114fbbefc0ddc9 --memory-stages /home/fenics/Projects/MyFEniCS/results/task040_v9_c0_explicit_coarse_mpi8_3564fe3e_native/memory_stages.jsonl --memory-markers /home/fenics/Projects/MyFEniCS/results/task040_v9_c0_explicit_coarse_mpi8_3564fe3e_native/memory_stage_markers.raw.jsonl --v9-c0-explicit-coarse-only --watchdog-hard-stop-bytes 206158430208 --watchdog-enabled --bottom-route-only
```

| 结构/生命周期字段 | 值 |
|---|---:|
| patches / selected modes | `630` / `100800`（160 per patch） |
| owner factor loads | `[71,66,75,76,72,78,70,66]`；ready total=`574` |
| factor rows / global direct factor | rows=`432`；global direct/full-side factor=`0` |
| raw observed peak RSS / raw observed swap / watchdog wall | `86960574464 B` / `0` / `2541.745083810005s` |
| worker one-apply residual | `6.778773552009804`，finite |
| cleanup | system/action/provider/source vectors complete；factor ready count由574释放到0；outer solver未创建 |

raw hash（均由 root 直接重算）：

| 文件 | SHA256 |
|---|---|
| C0 `worker/run_summary.json` | `260204d69312533df4f72150991fa2b5bc242e7eda2adcc48fe30f5fdd3b7dc9` |
| C0 `watchdog_summary.json` | `99706a6d475d5e6e3e912648a8df1c7f5caee6e439bf4c3cabfb753881b6db33` |
| C0 markers | `084c52b602c1fcd82ae709b73287826e437d80194cb07ce30257180d9a45ee52` |
| C0 stages | `d217860d6035ba1f588e669d922e2d909e55d4d1658cb0f84549283eb17d9224` |
| C0 process samples | `d195a260c8937ac67c6cf7aaf4d64e4704c84fa8b1f1026e86582f59ba996c76` |
| C0 worker stdout | `555e300bc6d61f7d967108c43565d0f15f28808c313cc27aa6256690ca1dd350` |

## Corrected physical bare-F external h10 raw

官方输入为 `input/official/task039/5nm_p6h10_full3d_direct_mpi8.dat`，input SHA 为 `e8b60ba70daa2074c21603d463790a28c881d35d7bd17b2b8315fef0318007b6`，physical SHA 为 `db52c70d667caa726e2b2e04b646402415a377fa7bbcef42c87ffc816b9b2a7a`，source SHA 为 `788966983f436625bccd732e373f55766bc77a08`。

```text
mpiexec -n 8 /home/fenics/Projects/MyFEniCS/.venv/bin/python -m benchmarks.task040_level_a --input /home/fenics/Projects/MyFEniCS/input/official/task039/5nm_p6h10_full3d_direct_mpi8.dat --exact-spool-root /home/fenics/Projects/MyFEniCS/results/task040_v5_2_fresh_bare_f_authority_mpi8_fd7bea41/worker/bare_f_authority --run-directory /home/fenics/Projects/MyFEniCS/results/task040_v9_e_lor_bare_f_external_h10_mpi8_78896698_native/worker --source-sha 788966983f436625bccd732e373f55766bc77a08 --memory-stages /home/fenics/Projects/MyFEniCS/results/task040_v9_e_lor_bare_f_external_h10_mpi8_78896698_native/memory_stages.jsonl --memory-markers /home/fenics/Projects/MyFEniCS/results/task040_v9_e_lor_bare_f_external_h10_mpi8_78896698_native/memory_stage_markers.raw.jsonl --v9-e-lor-bare-f-external-only --watchdog-hard-stop-bytes 48318382080 --watchdog-enabled --bottom-route-only
```

上面是 watchdog 原样记录的 worker 命令；外层 watchdog wrapper 只负责 process-tree
监控和资源收口。

| 项目 | worker | watchdog |
|---|---|---|
| classification | `V9_E_LOR_BARE_F_EXTERNAL_NUMERICAL_NO_SIGNAL` | `requires_result_adjudication`；resource=`requires_resource_adjudication` |
| explicit residual | `0.7349227023138162`，finite | 不重新裁决 worker 数值 |
| KSP | FGMRES/right，restart=`64`，iterations=`256`，reason=`-3`；checkpoints `r0=102.62259067409134`、`r8=99.57176462522295`、`r16=96.32327892011965`、`r32=93.51638140466038`、`r64=83.96027881243891`、`r128=78.86664205332832`、`r256=75.41967165664788` | natural exit，`181.50410642300267s` |
| structure | active rows=`8424`；global factor/coarse factor=`0`；physical DtN=`false`；operator=`P_plus_curlcurl_plus_mass` | peak RSS=`5728456704 B`；swap=`0`；359 samples |
| operator role | outer operator=`current physical bare-F`；P+ curl/mass=`1/1` 仅作 right preconditioner；`role=right_preconditioner_not_physical_operator` | 不把 P+ 当作物理算子 |
| lifecycle | KSP/PC context/service/bridges/counting/static/condensed/system destroyed；MPC=`not_applicable`（no destroy hook）；official RTA=`not_run` | terminal marker旧 raw status错位，`cleanup_complete=false`；不改写 raw |

corrected root 的直接 hash：

| 文件 | SHA256 |
|---|---|
| worker `run_summary.json` | `a9a8c8bd855b4ab9fbab958a7985ad46c00bbfc61c213b93c2065760adef8d57` |
| `watchdog_summary.json` | `97e620afe1f006ff43d613c8cbe7667327a942cfc146f1a03c9b69b1a7b4b257` |
| markers | `4770288b29a3f5f31860dc747786fafafcf9fd599aa192347396eb2bab089894` |
| stages | `fd01df616489e78e437bd7d7a2284cd25f045a8dff8d4b2d463fac9aa4920bbe` |
| process samples | `f6889813882816596ff15361f212e31f04b8b1767cc580d1e183ce46e9f7e9a2` |
| worker stdout | `555e300bc6d61f7d967108c43565d0f15f28808c313cc27aa6256690ca1dd350` |

后续 `3bf94414` 只修 terminal cleanup marker 并有 regression；它防止未来同类误判，但没有重跑或改写该一次性 raw。旧 `_18b00b58_native` root 也原样保留为 source-integration/authority failure。

## V9-E failure/formal ledger

下面的表和命令均从对应 raw root 的 worker/watchdog 记录整理；`not_serialized_in_this_raw`
表示该 raw 没有该字段，不能用别的 case 或文档值补齐。

### Structured S3 J1 baseline attempts

三次尝试均为 MPI8、threads=`1`、bottom-only；worker raw 没有序列化 ABI 字段，故 ABI=
`not_serialized_in_this_raw`。三次都在 one-apply/FGMRES 前以同一实现分类失败，
`action_apply_count=0`、`pc_apply_count=0`，不是 numerical no-signal。

```text
mpiexec -n 8 /home/fenics/Projects/MyFEniCS/.venv/bin/python -m benchmarks.task040_level_a --input /home/fenics/Projects/MyFEniCS/input/official/task039/5nm_p6h10_hybrid_iterative_m120_candidate_mpi8.dat --exact-spool-root /home/fenics/Projects/MyFEniCS/results/task040_v9_e_s3_unused_exact_spool_7bfef8e9_native --run-directory /home/fenics/Projects/MyFEniCS/results/task040_v9_e_s3_j1_baseline_mpi8_7bfef8e9_native/worker --source-sha 7bfef8e9e7abdbed0f25c1d5f487d41d601df318 --memory-stages /home/fenics/Projects/MyFEniCS/results/task040_v9_e_s3_j1_baseline_mpi8_7bfef8e9_native/memory_stages.jsonl --memory-markers /home/fenics/Projects/MyFEniCS/results/task040_v9_e_s3_j1_baseline_mpi8_7bfef8e9_native/memory_stage_markers.raw.jsonl --v9-e-s3-j1-baseline-only --watchdog-hard-stop-bytes 48318382080 --watchdog-enabled --bottom-route-only
mpiexec -n 8 /home/fenics/Projects/MyFEniCS/.venv/bin/python -m benchmarks.task040_level_a --input /home/fenics/Projects/MyFEniCS/input/official/task039/5nm_p6h10_hybrid_iterative_m120_candidate_mpi8.dat --exact-spool-root /home/fenics/Projects/MyFEniCS/results/task040_v9_e_s3_unused_exact_spool_8b9fb0b8_native_fix1 --run-directory /home/fenics/Projects/MyFEniCS/results/task040_v9_e_s3_j1_baseline_mpi8_8b9fb0b8_native_fix1/worker --source-sha 8b9fb0b8a21e47942260ffee89106a41ad2ceb02 --memory-stages /home/fenics/Projects/MyFEniCS/results/task040_v9_e_s3_j1_baseline_mpi8_8b9fb0b8_native_fix1/memory_stages.jsonl --memory-markers /home/fenics/Projects/MyFEniCS/results/task040_v9_e_s3_j1_baseline_mpi8_8b9fb0b8_native_fix1/memory_stage_markers.raw.jsonl --v9-e-s3-j1-baseline-only --watchdog-hard-stop-bytes 48318382080 --watchdog-enabled --bottom-route-only
mpiexec -n 8 /home/fenics/Projects/MyFEniCS/.venv/bin/python -m benchmarks.task040_level_a --input /home/fenics/Projects/MyFEniCS/input/official/task039/5nm_p6h10_hybrid_iterative_m120_candidate_mpi8.dat --exact-spool-root /home/fenics/Projects/MyFEniCS/results/task040_v9_e_s3_unused_exact_spool_e2ec5e4a_native_fix2 --run-directory /home/fenics/Projects/MyFEniCS/results/task040_v9_e_s3_j1_baseline_mpi8_e2ec5e4a_native_fix2/worker --source-sha e2ec5e4a66430e85ac1c7f7e49cc013b2063dd19 --memory-stages /home/fenics/Projects/MyFEniCS/results/task040_v9_e_s3_j1_baseline_mpi8_e2ec5e4a_native_fix2/memory_stages.jsonl --memory-markers /home/fenics/Projects/MyFEniCS/results/task040_v9_e_s3_j1_baseline_mpi8_e2ec5e4a_native_fix2/memory_stage_markers.raw.jsonl --v9-e-s3-j1-baseline-only --watchdog-hard-stop-bytes 48318382080 --watchdog-enabled --bottom-route-only
```

| root / source SHA | 首个 raw failure | worker wall / watchdog wall；watchdog peak RSS；swap | raw hashes（run / watchdog / marker） | factor/vector lifecycle |
|---|---|---|---|---|
| `results/task040_v9_e_s3_j1_baseline_mpi8_7bfef8e9_native` / `7bfef8e9e7abdbed0f25c1d5f487d41d601df318` | `C shape (8424,300)`，要求 `(8424,296)` | `72.31749812298222s` / `74.66919081198284s`；`3647008768 B`；`0` | `3cd08d8061d589a00faa846e212c9ed96bbb4a62749c8da467ad2e1d1571f3f6` / `4635b7ef8fc9e268d6a8ac6dcf55f23eff69d05f64db2e0fd8b059bd7ea4f5de` / `80b4936965427663913df2f30d07722820602ca6f667393205ed7ff9d6c07360` | factor ready=`0`；full/direct/coarse/cross=`0`；solver vectors=`0`；source_destroyed=`false`；no one-apply/FGMRES |
| `results/task040_v9_e_s3_j1_baseline_mpi8_8b9fb0b8_native_fix1` / `8b9fb0b8a21e47942260ffee89106a41ad2ceb02` | canonical token count `9786 != 8424` | `74.43764859699877s` / `76.9369262100081s`；`3652943872 B`；`0` | `965c7888bacb8457bc726e52882e2a840cfc65149c42c4501bb47611ccca5d85` / `92375ca8a6b83e54834021852b67d24be66a4d2923a9e8879096b2dffa8fcffc` / `3191097ce6e5db4734330308401a856804987f82a5b41414027ed01c351f4455` | factor ready=`0`；full/direct/coarse/cross=`0`；solver vectors=`0`；source_destroyed=`false`；no one-apply/FGMRES |
| `results/task040_v9_e_s3_j1_baseline_mpi8_e2ec5e4a_native_fix2` / `e2ec5e4a66430e85ac1c7f7e49cc013b2063dd19` | exactly six real layers required，实际 `2` | `73.20668218901847s` / `75.76027313398663s`；`3656544256 B`；`0` | `fdafa110e99a572273eb8dd42e93646e0765758fb3bfd6accbcbf5276a9e6ede` / `7ce10a67dddbfdaa77914fd8c5dc49532b2d01b2a11c07f10faddff53f98eb7e` / `d3af71c91e44c0f7a5fb3b6db3c590a7b8fa9b02e0b9658b0bc294b934e5f782` | factor ready=`0`；full/direct/coarse/cross=`0`；solver vectors=`0`；source_destroyed=`true`；no one-apply/FGMRES |

三次 raw 的 physical SHA 都是 `db52c70d667caa726e2b2e04b646402415a377fa7bbcef42c87ffc816b9b2a7a`，
input SHA 都是 `3fa567d482ba45495fe9d097ba16946c330b0ba208fc8c4c5e47b7fcd6315161`；resolved
config SHA=`not_serialized_in_this_raw`。resource rows 各自 `all_status_readable=true`、
`swap=0`；implementation budget 在第三次 fix2 后耗尽，随后按冻结顺序转 fixed LOR，
不把这三次 failure 写成 no-signal。

### Fixed-LOR L2 h10/h5 formal records

两案的 MPI8 来自下列 raw worker command；worker `run_summary.json` 序列化
`scalar_type=complex128`、`int_type=numpy.int32`。threads=`1` 与 native activation marker=`1`
未在该 worker JSON 序列化，分别作为 command/provenance 与 stage-time provenance 记录；不冒充
worker JSON 字段。resolved config SHA=`not_serialized_in_this_raw`。P+ fixed LOR 只作
action-screen/right PC 组件，
不是 physical operator。以下命令是各自 watchdog 记录的精确 worker command：

```text
mpiexec -n 8 /home/fenics/Projects/MyFEniCS/.venv/bin/python -m benchmarks.task040_level_a --input /home/fenics/Projects/MyFEniCS/input/official/task039/5nm_p6h10_full3d_direct_mpi8.dat --exact-spool-root /home/fenics/Projects/MyFEniCS/results/task040_v5_2_fresh_bare_f_authority_mpi8_fd7bea41/worker/bare_f_authority --run-directory /home/fenics/Projects/MyFEniCS/results/task040_v9_e_lor_l2_h10_mpi8_8c19b841_native/worker --source-sha 8c19b841a388cd5b4e2f785d79d791fabe4db021 --memory-stages /home/fenics/Projects/MyFEniCS/results/task040_v9_e_lor_l2_h10_mpi8_8c19b841_native/memory_stages.jsonl --memory-markers /home/fenics/Projects/MyFEniCS/results/task040_v9_e_lor_l2_h10_mpi8_8c19b841_native/memory_stage_markers.raw.jsonl --v9-e-lor-l2-only --watchdog-hard-stop-bytes 48318382080 --watchdog-enabled --bottom-route-only
mpiexec -n 8 /home/fenics/Projects/MyFEniCS/.venv/bin/python -m benchmarks.task040_level_a --input /home/fenics/Projects/MyFEniCS/input/official/task039/5nm_p6h5_full3d_direct_mpi8.dat --exact-spool-root /home/fenics/Projects/MyFEniCS/results/task040_v5_2_fresh_bare_f_authority_mpi8_fd7bea41/worker/bare_f_authority --run-directory /home/fenics/Projects/MyFEniCS/results/task040_v9_e_lor_l2_h5_mpi8_8c19b841_native/worker --source-sha 8c19b841a388cd5b4e2f785d79d791fabe4db021 --memory-stages /home/fenics/Projects/MyFEniCS/results/task040_v9_e_lor_l2_h5_mpi8_8c19b841_native/memory_stages.jsonl --memory-markers /home/fenics/Projects/MyFEniCS/results/task040_v9_e_lor_l2_h5_mpi8_8c19b841_native/memory_stage_markers.raw.jsonl --v9-e-lor-l2-only --watchdog-hard-stop-bytes 48318382080 --watchdog-enabled --bottom-route-only
```

| case / identity | classification；explicit residual；iterations/reason；checkpoints | wall / peak RSS / swap | action / PC；rows；factor inventory | lifecycle；raw hashes（run / watchdog / marker / stages / samples） |
|---|---|---|---|---|
| h10；input=`e8b60ba70daa2074c21603d463790a28c881d35d7bd17b2b8315fef0318007b6`；physical=`db52c70d667caa726e2b2e04b646402415a377fa7bbcef42c87ffc816b9b2a7a`；source=`8c19b841a388cd5b4e2f785d79d791fabe4db021` | `V9_E_LOR_L2_ONLY_ACTION_PASS`；`9.49183402945266e-9`；`211/2`；r0=`21454.73735384569`、r8=`3473.252013095208`、r16=`1407.754267637361`、r32=`208.6805415315554`、r64=`14.656174593868663`、r128=`0.10487537743331045` | worker=`1386.0537793239928s`；watchdog=`1389.6292548999772s`；`10264653824 B`；`0` | action=`216`、PC=`211`；active=`51192`；max rows=`432`；factor local/rank-sum=`29/221`；pc_factor_map_bytes_rank_sum=`662515200`；pc_work_vector_payload_bytes_rank_sum=`2021760`；cache reuse=`2` | KSP/PC/service/bridge/static/condensed/counting destroyed=`true`；MPC raw `mpc_destroyed=false`；destroy-hook语义未序列化，因此不推断 leak/pass/not_applicable；cleanup raw=`false`；`05b081e30021e2cccc1980b085a475e2d93b222a4eec529a736993cf947674cb` / `041a0f89b5c231a2ef01788093b17766c8fb4d9478648cd459388c6889120f39` / `4acda8a42956cb8d5df1b47ee3bc8c5e592967e1e973f04f841333826ab1b812` / `0adb046a7b4b1ff23a120717b4252342c719ef48bd5f759fa95afe13c551057a` / `a47cb6fd38e9631e6be28d304a7d3793e3d5f3fc88d9ad8f2d26244ee1252334` |
| h5；input=`9432de4711d6ceb60b840532dd4038ed02579fc1b55ca6632308c56f5c34aecb`；physical=`e35907c72ab97069d9ab66958fd00787f98dea08dce1aa6f64c053b7bda46cdb`；source=`8c19b841a388cd5b4e2f785d79d791fabe4db021` | `V9_E_LOR_L2_ONLY_ACTION_FAIL`；`3.743078556589845e-7`；`256/-3`；r0=`90205.50439762919`、r8=`19336.8963265271`、r16=`9302.755402969331`、r32=`2412.6802722758334`、r64=`285.40830308123134`、r128=`10.499096384219763`、r256=`0.033764628919673814` | worker=`4605.458017062978s`；watchdog=`4610.74300463096s`；`19517489152 B`；`0` | action=`262`、PC=`256`；active=`336960`；max rows=`432`；factor local/rank-sum=`93/667`；pc_factor_map_bytes_rank_sum=`2009069568`；pc_work_vector_payload_bytes_rank_sum=`11850240`；cache reuse=`117` | KSP/PC/service/bridge/static/condensed/counting destroyed=`true`；MPC raw `mpc_destroyed=false`；destroy-hook语义未序列化，因此不推断 leak/pass/not_applicable；cleanup raw=`false`；`4bf4e0c17591b6fe96ea1aab967b45dfe33a614c7594405f2a4de32568ffd2c8` / `3787fadf12ad2600ff2c7df5f826c698acc47d660b95690d4eb49f32ab93d619` / `1779604f14e91e7cb537edf7fc0cce5e41ec6ce3be529e59137d23ec17a36e37` / `78a9d531c2cc2d81b46bab00354b0eac01c091037b51d6aa2544415fa8cd47e2` / `6ae51d77fa00d5d6327ab7467d4d2295dd0898ba9011581733deb771cb6d85db` |

h10 的 preliminary root `results/task040_v9_e_lor_l2_h10_mpi8_9cba44c0_native` 只有
`run-directory already exists` 的 path/orchestration implementation failure；没有
watchdog/run summary，不把它当 formal。两案都没有 serialized resolved config SHA，不能从旧
文档反推。

### External bare-F root ledger

| root | raw classification / reason | formal boundary |
|---|---|---|
| `results/task040_v9_e_lor_bare_f_external_h10_mpi8_18b00b58_native` | `IMPLEMENTATION/authority failure`；current external-mode authority 未供给；watchdog rc=`1`、无 worker run summary | 不是 numerical result；marker/stages/samples/stdout 仍保留，见旧 root |
| `results/task040_v9_e_lor_bare_f_external_h10_mpi8_78896698_native` | worker=`V9_E_LOR_BARE_F_EXTERNAL_NUMERICAL_NO_SIGNAL`；explicit=`0.7349227023138162`；watchdog `requires_result_adjudication` / `requires_resource_adjudication` | input=`e8b60ba70daa2074c21603d463790a28c881d35d7bd17b2b8315fef0318007b6`；physical=`db52c70d667caa726e2b2e04b646402415a377fa7bbcef42c87ffc816b9b2a7a`；resolved=`a35bb4e35088a33ecd59161bf41307c092cae4a11dba30e8336026833bc40c3e`；MPI8/threads1/native `complex128/int32`；worker formed numerical no-signal, old terminal cleanup bookkeeping leaves resource/result wrapper unresolved |

external corrected raw worker command、359 samples、lifecycle和六份 hash 已在上节完整列出；其
`run_summary` SHA 必须保持 `a9a8c8bd855b4ab9fbab958a7985ad46c00bbfc61c213b93c2065760adef8d57`，
不改写一次性 raw。B0/B1 tiny 引用 `results/task040_v9_e_tiny_identity_ec8eaaea_native_final` 的
serial/MPI2 stdout：四项 improvement 均通过固定 `>=8` Gate（serial B0=`4385921181522.289`、
MPI2 B0=`4178485941698.5303`、serial B1=`1821946650161.7349`、
MPI2 B1=`2137800826967.3997`），并保留各自 best/final/direct/b0_positive/b1_positive 详值于
上方 route evidence。该结果使进入 reduced 5 nm pilot 在流程上有依据，但仍是 component
identity evidence，没有 formal JSON/hash，绝不是 physical formal positive。

## Final focused test evidence

最终 closeout contracts 已在 native activation（marker=1）下通过：

`python -m pytest -q src/test/test_24_repository_work_principles.py src/test/test_25_benchmark_contract.py src/test/test_26_documentation_contract.py src/test/test_29_task_retrospective_contract.py`

rc=`0`，`34 passed`、`0 failed`、`0 skipped`；pytest=`0.45s`，shell
command wall=`0.534s`，无 warning/stderr。该结果只是本地轻量合同通过，
不代表 full repository pytest、CI 或 Task40 numerical/MPI/PDE。

以下命令均在同一 shell 先执行 `source .venv/bin/activate_myfenics_native.sh`；表内命令省略
该激活前缀。

| 项目 | 精确范围/命令 | 结果与口径 |
|---|---|---|
| serial | `python -m pytest -q src/test/test_339_task040_fixed_lor_external_pilot.py` | `5 passed`；`71.03s`；已有 stage-time targeted evidence |
| MPI2 | `mpiexec -n 2 python -m pytest -q src/test/test_339_task040_fixed_lor_external_pilot.py` | 每个 rank `5 passed`；`72.00s`；已有 stage-time targeted evidence |
| Ruff | `python -m ruff check src/solvers/hybrid_bare_f_external_lor_pilot.py src/test/test_339_task040_fixed_lor_external_pilot.py` | `passed`；stage-time evidence |
| compileall | `python -m compileall -q src/solvers/hybrid_bare_f_external_lor_pilot.py src/test/test_339_task040_fixed_lor_external_pilot.py` | `passed`；stage-time evidence |
| whitespace | `git diff --check` | `passed`；stage-time evidence |

以上是本轮已有的 focused evidence；final closeout contracts 已通过，但只是本地轻量
合同，不代表 full repository pytest、CI 或 Task40 numerical/MPI/PDE。

该表只记录已有 raw 可核验结果，不声称 full repository pytest、CI 或 formal PDE 测试。

## V9 required outcomes 与 stop Gate

| required outcome | 状态 | 当前依据 |
|---|---|---|
| source canonical bridge | measured component | identity/packet mechanism具备；后续 full-spectrum 两源 screen 已另行形成 strict no-signal |
| full-spectrum numerical two-source | measured strict no-signal | 两源 one-apply 与 r8/r16/r32/r64齐全，r64/drop Gate未通过 |
| adaptive local/coarse | Stage A measured；B/C resource stopped | no valid full outer result |
| C0 numerical + watchdog authority | worker measured no-signal；watchdog terminal resource metadata gap | numerical Gate成立；resource gap不改写为resource pass |
| V9-E dual real no-signal | established | full-spectrum与C0均有真实 no-signal；fallback未取得 qualified physical positive |
| qualified Full3D architecture candidate | `NOT_ESTABLISHED` | V9-E入口成立，但无 qualified physical positive；handoff 文档记录边界 |

因此最终建议是保持 V9-E 漏斗停止，等待 review 决定后续架构任务；C1 按 numerical Gate 不运行。代码按依赖分组处理，不把全部代码笼统写成 do-not-merge。

C0 的完整 current marker、Mat 与 factor 表见
[adaptive outcome](outcomes/adaptive_spectral_schwarz.md)。

## Selective-merge dependency groups

| 依赖组 | 文件/依赖 | 数值行为 | 测试或 fresh evidence | 建议顺序/边界 |
|---|---|---|---|---|
| production numerical/core | 本轮没有 qualified production core；新增 `src/solvers` research helpers 不属于此组 | ordinary default 未改变 | 无 qualified production fresh evidence | 暂不合入 |
| reusable runner/watchdog | `benchmarks/task040_level_a.py`（混合路线 wiring，仅 file/hunk-level 审阅，排除 S3/未闭合路径）、`benchmarks/task040_level_a_watchdog.py`、`benchmarks/task040_v6_2_interface_schur.py`；依赖 research helpers | 仅 opt-in plumbing；ordinary route 不变 | 对应 raw routes；final closeout contracts 34 passed（本地轻量合同） | 按依赖审阅，仍未自动提升 production |
| checker/benchmark | 本轮未新增独立 checker 或 case record；focused tests 是验证资产，不是 checker | 不改变 solver promotion | test339 stage-time serial/MPI2；其余 raw evidence | 不称为 checker |
| compact evidence/docs | `response_v10.md`、`development_progress.md`、`outcomes/{v9_source_canonical_bridge,matrix_free_galerkin_coarse,full3d_0p7nm_architecture_handoff,full_spectrum_floquet_sweep,adaptive_spectral_schwarz,route_signal_ledger,memory_residual_time_pareto,0p7nm_side_pc_capacity,summary}.md` | 不改变数值 | raw hash、命令和已有 targeted evidence | 作为 compact evidence 归档，不把 raw 当 Git merge 项 |
| research-only | `src/solvers/floquet_background_hcurl*.py`（不含 `floquet_background_hcurl_s3_formal.py`、`floquet_background_hcurl_s3_pilot.py`）、`src/solvers/hcurl_fixed_lor*.py`、canonical/full-spectrum/C0 helpers、`src/solvers/hybrid_bare_f_external_lor_pilot.py`；对应 `src/test/test_298*`、`test_319*`、`test_326*`–`test_329*`、`test_331*`–`test_339*` | 不具 production 资格；ordinary physics/default 不变 | 各 component/focused evidence 与 MPI8 roots | 保留研究/复核，不作 production promotion |
| do-not-merge | `src/solvers/floquet_background_hcurl_s3_formal.py`、`src/solvers/floquet_background_hcurl_s3_pilot.py`、`src/test/test_330_task040_v9_s3b_pilot.py`、`benchmarks/task040_level_a.py` 中的 S3 wiring，以及其他未闭合/旧 raw-row paths | 不提升失败路径为 numerical behavior | failed roots retained/archived；raw artifacts 不是 Git 项 | 明确禁止合入 |

## 未运行与未声明

本响应没有运行 full repository pytest、CI、MPI4、C1、five-source、top/both-side/full Hybrid、recovery、RTA、p6h3 或 0.7 nm PDE，也没有修改 Task39、master、物理方程、M480、physical DtN 或 ordinary defaults。
