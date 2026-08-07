# Task037-extra G2.4 C2c 证据收口

本轮只收口一次真实 p6/slab14 LOR transfer screen。LOR（低阶细化）把一个
p6 hexa parent 拆成 lowest-order edge 网格；独立的 LOR edge cochain 通过
`T` 转成 p6 full-space stored coefficients，`T^H` 是同一转移的精确共轭转置。
这解决的是“低阶边变量与高阶单元变量能否以同一物理/周期身份互相作用”的
代数接口问题，不是新的求解器或 V-cycle。

## 结论

| 范围 | 状态 | 本轮含义 |
|---|---|---|
| G2.4 slab14 LOR transfer | `pass_transfer_build_and_algebra_only` | 真实 build、周期身份、重复 action 与伴随合同通过 |
| G2.3 plain full-space ILU | `close_fullspace_ilu_only_route` | 原有负结论保持不变 |
| G2.5 LOR-HX/V-cycle | `pending_not_run` | 未实现、未运行 |
| G2.6 contraction | `pending_not_run` | 未运行 |
| G3 / official field / RTA | `pending_not_run` | 未运行；没有 official field 或 RTA |

这不是 `G2_PASS`，也不证明 HX/V-cycle 有效、外层 FGMRES 收敛或生产方案晋级。

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

## 运行身份与 solver 边界

| 项目 | 值 |
|---|---|
| source SHA | `579c1912177411d1d5036a08f04c11661bc51965` |
| run directory | `benchmarks/artifacts/101_task37_extra_development/g2_slab14_lor_transfer_mpi1_screen20_579c1912` |
| scope | p6/h10/S、MPI1、M2c never-materialized、M3a overlap0.125 partition、screen20 |
| flags | identity=true；LOR=true；factor-inventory=false；G0 diagnostics=false |
| watchdog | `task037_extra_g2_slab14_lor_transfer_pass`；return code `0`；failures `[]` |
| solver | 20-step screen，`DIVERGED_MAX_IT(-3)` |
| official result / RTA | `false / false` |
| global A / global F | `false / false` |
| preflight authority SHA256 | `96ac3949efc236393d4c2dbc6e1fa334ad5ccb0e9796bdeba13fbe0515577dd8` |

`DIVERGED_MAX_IT(-3)` 是预先限定 20 步 screen 的外层边界，不是 transfer
代数 Gate 失败；由于没有收敛，official field 和 RTA 不产生。

正式 parent command 为：

```text
python -m benchmarks.run_task033_full3d_watchdog --degree 6 --h-nm 10 --polarization-kind s --run-kind full-solve --mpi-size 1 --profile default --stage4-full3d-assembly-backend assembly_time_static_condensed --task035c-p6-h10-gate --task035c-p6-preflight-authority benchmarks/cases/095_high_order_local_hp_resource_envelope/records/global_hexa_p1_p6_h10_p6_assembly_time_condensed_independent_mpi8.json --task035c-p6-preflight-sha256 96ac3949efc236393d4c2dbc6e1fa334ad5ccb0e9796bdeba13fbe0515577dd8 --verified-clean-sha 579c1912177411d1d5036a08f04c11661bc51965 --task037-f3-screen 20 --poll-interval 0.25 --warning-gib 10 --terminate-gib 14 --timeout-seconds 1800 --task037-m2c-never-materialized --task037-m3a-overlap0125-partition --task037-extra-g2-slab14-identity --task037-extra-g2-slab14-lor-transfer --run-dir benchmarks/artifacts/101_task37_extra_development/g2_slab14_lor_transfer_mpi1_screen20_579c1912
```

## slab14 identity 与 LOR audit

| 指标 | 值 |
|---|---:|
| owner / cells / unique blocks | `0 / 54 / 6` |
| full / interior / trace rows | `32724 / 24300 / 8424` |
| trace offset | `24300` |
| source / retained / dropped active columns | `23328 / 17064 / 6264` |
| partial cells | `18` |
| retained `C` NNZ / bytes | `17064 / 434808` |
| iter20 local residual norm2 | `0.42723143961943305` |
| iter20 residual vector SHA256 | `3aa610ed9bbb63047188b64d21d5dcab04184ffc6316196458e99aab520bb195` |

完整 local block 和 trace rows 被保留，`C` 只保留 owner active columns，外部列
等价于零延拓；因此 `23328 = 17064 + 6264`。这是与既有 principal
restriction 一致的边界 cell 语义，不是丢弃跨界 parent cell。

| LOR physical/audit 字段 | 值 |
|---|---:|
| physical / active / periodic-slave edges | `38304 / 36288 / 2016` |
| periodic relations | `2016` |
| physical edge hash | `69b351698907f0067b09cf14c0f889d1566a86d1bcfec78d7a48121659635054` |
| active edge hash | `a359da92b3a781ff447f5bf81ce7dc845c1be022464948526ee489874c77010a` |
| matched / merged / gathered identity blocks | `93 / 401 / 401` |
| gathered physical identity payload | `84688 B` |
| missing writer / shared error / complete-C error | `0 / 1.7200665360018798e-15 / 9.56091885020216e-16` |
| unique T stencil patterns | `2` |
| build seconds | `49.17991871200502` |

G2.2 full-space/trace identity 的 3 个 deterministic vectors relative errors 为
`2.9248960201709676e-15`、`2.978578754981666e-15`、
`2.6617554455542794e-15`；iter20 residual direction的 identity error 为
`1.7721399154913289e-15`。LOR measurement 使用 `forward_apply_count=7`、
`adjoint_apply_count=1`，结果 finite/deterministic，伴随相对误差为
`1.5008209190777043e-14`，且 `global_dense_T_retained=false`。

## residual trajectory

| iteration | true relative residual | reported relative residual |
|---:|---:|---:|
| 0 | `1.0` | `1.0` |
| 10 | `0.14446444295860594` | `0.14446444295860714` |
| 20 | `0.04474243612765` | `0.04474243612765121` |

这些 scalar residual只用于记录 screen 轨迹；iter20 LOR direction 使用 solver
生命周期中真实的 `r=b-Ax` owner-local 向量，不从 scalar residual 伪造。

## 资源口径

`progress` 中的 rank RSS 是事件瞬间采样，不等于整个阶段峰值：开始事件为
`1060.25 MB`，ready 事件为 `1166.61328125 MB`，两者差
`106.36328125 MB`。watchdog 的 `stage_peaks[g2_lor_transfer_build_started]`
覆盖实际 LOR build 区间，process-tree 最大值为
`1180.4296875 MB = 1.1527633666992188 GiB`。

名为 `stage_peaks[g2_lor_transfer_build_ready]` 的
`4877.80078125 MB` 采样区间从 ready 事件之后持续到
`all_slab_factors_ready`，包含后续既有 16-slab trace-factor setup；它不能写成
LOR build/ready 峰值。

| 资源字段 | authority |
|---|---:|
| whole-run process-tree RSS | `4920.34765625 MB = 4.805027008056641 GiB` |
| worker RSS / PSS / USS | `4906.53125 / 4855.1728515625 / 4810.64453125 MB` |
| swap | `0` |
| warning / termination / timeout | `false / false / false` |
| wall | `277.6128281370038 s` |
| retained numeric lower bound | `18735740 B = 17.867794036865234 MiB` |

retained numeric lower bound只计入唯一的 `T/T^H/E/E^H`、packing 和 reference
CSR arrays，不是 RSS，也不含 Python 对象和 allocator 开销。旧 G2.2 identity
authority（source `44f5931c479eba86c9d12c57109e3b052e2962e4`）的 process-tree
RSS 为 `4655.9453125 MB = 4.546821594238281 GiB`；本次高
`264.40234375 MB`、约 `5.68%`。由于 source SHA 不同，这只是同机背景，不能
归因成纯 LOR retained 增量。

## raw evidence

compact record：[g2_slab14_lor_transfer.json](/home/shenjh/Projects/MyFEniCSx_task37_extra/benchmarks/cases/101_task37_extra_development/records/g2_slab14_lor_transfer.json)。原始文件均保留在 ignored run directory：

| raw 文件 | SHA256 |
|---|---|
| `watchdog_summary.json` | `41e148b957b3fcba3ebc06c27e6b11c9c7a5736e3b82b258a117b200a9b300ec` |
| `run_summary.json` | `aefc2a7b3503b4e15114a1a7299e8fff02957c59aa2eaa3c3073d867dd394631` |
| `task037_f3_core_audit.json` | `8bd07800ecaa5615937f7f74c546e66bf2e7a2f4256eb51f5d7dd49024585e85` |
| `progress_3d.jsonl` | `dcc0ff8dd12862d4b17ec5806f71054d080d7c295388b27a825e2be2872e2aed` |
| `memory_timeline.csv` | `8d8624ee3fbc0bd4dd5a02033728069fd1712e0fdbfdb07919df0f2e37257efb` |
| `task037_f3_residual_history.jsonl` | `75f0bc3ebec3648b60fdfc55daa9afd036b81cf6d5fe0ef1f7051a83e0f24940` |
| `parent_launch_descriptor.json` | `e4cf1db4daf1597eec562838cd32840b46dac436ab00673ae57195271e367423` |
| `worker_stdout.txt` | `0ad5399df6b37c9643175c6cec172a330c62cbe31dc6b80c37344b82776dd979` |

## 未运行项

G2.5 HX/V-cycle、G2.6 contraction、G3 以及 official field/RTA 均未运行。本轮
停止在“真实 slab14 LOR transfer 可构造、可重复作用、周期身份和伴随代数通过”；
不把它升级为 G2 overall pass，也不把它解释为预条件器有效或物理收敛。
