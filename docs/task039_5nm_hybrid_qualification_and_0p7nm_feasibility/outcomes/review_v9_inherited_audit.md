# Task039 V9-0：Schur-aware side baseline 继承审计

本文件是 V9-0 的 docs-only inherited audit。它把 V7/V8 已完成的事实、负结果和冻结边界
整理为 V9 的起点；不修改 Python、配置、测试阈值或既有 compact record，也不启动
pytest、MPI、QEP、factor、solver 或 PDE。V8 以前的 raw root 仍在 ignored local path，
本文件不把 raw artifact 加入 Git。

## 1. 审计身份与工作树

| 字段 | 实测/冻结值 | 口径 |
|---|---|---|
| branch | `codex/20260812-task39-5nm-hybrid-0p7nm-feasibility` | 唯一 Task39 执行分支 |
| V9 review reviewed_head | `72addb495b7b996c879ae0a8f3026ad32225e8fd` | `review_report_v9.md` 内的审阅祖先 |
| V9-0 audit base HEAD | `9613290258aa8527c9a650a3e3254f1a3c46249d` | 本轮按用户指定 fast-forward 到的目标；提交后以最终 HEAD 为准 |
| upstream | `origin/codex/20260812-task39-5nm-hybrid-0p7nm-feasibility` at `9613290258aa8527c9a650a3e3254f1a3c46249d` | exact match |
| ahead / behind | `0 / 0` | `HEAD...@{upstream}` |
| worktree | `clean` | V9-0 开始时无 tracked 或 untracked 修改 |
| review_report_v9 SHA256 | `6b5790d1cedc734a7bd9cd6e24730c44b12309ca49cb47636fb5cb76678fe4a8` | 当前 V9 权威审阅文件 |

`9613290` 相对 reviewed head 只带入 V9 review 及同步所需的已推送历史，未改变 V8
数值证据。本文件提交后，工作树预期只包含本文件的 docs-only 变更。

## 2. 5 nm h4 输入与物理身份

| 项目 | 值 |
|---|---|
| input | `input/official/task039/5nm_p6h4_v4_1deg_hybrid_iterative_m480_mpi8.dat` |
| input SHA256 | `4e60924b5997e3ca99e324ea14779f9014efc6a1304a9aa11de9c808353f1811` |
| physical model SHA256 | `8391d46139646440d869aa43abe6a68bc921fc1972a10030c64be81dffdd527c` |
| physical case | 5 nm / 1° grazing / phi=0° / S / p6/h4 / M480 |
| formal MPI identity | MPI8 |
| selected packet root | `results/task039_v4_h4_m480_shared_packet_eaad0f94` |
| selected manifest SHA256 | `2dddaf7a6f8f045adabd840970952517d76305c7c0e03c71258642d856c13067` |
| selected identity SHA256 | `b3bb870fe6fa17cb262b6161f7317cc1950944755c9270d4628dd5c79e950690` |
| selected runtime identity SHA256 | `cfd5704b48bff980fa2d819f4deee9a59bb9a3db39bc24a70c53f42f067d39e9` |

V7/V8 的 selected packet 只作为既有物理身份和历史证据；V9-0 不 hydrate packet，也不
从它生成新 basis。V9-0 继承的 exact-bottom holdout 是：

| 项目 | 值 |
|---|---|
| exact spool root | `results/task039_v5_h4_mumps_blr_side_component_mpi8_7e5d9b57_1e3/numerical_output` |
| holdout producer/source SHA | `7e5d9b57a10b1093f0cb062eaf7bc12797c47e1f` |
| catalog SHA256 | `a2a7fb6fb01df4f795d31ff94f6ac6adf957ac4fe4a5c1a8d05176e3d64c0384` |
| inventory | 8 producer ranks / 6 labels / 96 response artifacts |
| catalog method | sorted relative path、byte count、file SHA256 rows 的 SHA256 |
| role | frozen oracle/holdout only；不进入训练 |

## 3. V7 完整工作流与组件边界

下表严格区分完整 workflow 和 component。component 的低 RSS 不能换算为完整 solver 的
memory saving。

| inherited path | scope | measured result | V9 解释 |
|---|---|---:|---|
| matched h4 Hybrid direct | full workflow | `93.377006531 GiB` | direct reference |
| V7 Lane A setup-only | setup-only | `81.056903839 GiB`；`10649.634795 s` | measured setup peak；`84.039305878 GiB` 是 advancement threshold，不是 measured peak |
| V7 Lane A exact-side full formal | full workflow | `80.025856018 GiB`；`10126.231902 s`；1 outer iter | 唯一完整低于 direct 的正式结果；saving `14.298113646%`，通过 5% tier、未达到 20% tier |
| V7 streamed producer | component | `11.630760193 GiB`；约 `415.6 s` | resource/lifecycle pass；不是 full workflow |
| V7 streamed consumer | bottom component | `23.038208008 GiB`；约 `632.8 s` | rank64/128/256/512 residual negative |
| V8-1 layer-block reconstruction | component/structure | `15.0692863464 GiB` | local-F graph/action authority；不是 solver pass |
| V8-3 layer sweep | bottom component | `22.273887634 GiB` | construction resource pass；numerical negative；overall retained not_run |

V7 Lane A 的完整结论仍为 `5NM_EXACT_SIDE_LOWER_MEMORY_CASE_RESULT`，同时保留
`NOT_0P7NM_SCALABLE_DUE_FULL_SIDE_FACTORS`。它的 full-side factors 使该结果不能被当作
0.7 nm 可扩展架构证明。V7 streamed Petrov、V8 sweep 的负结果均为 source/method
capacity 的真实负证据，不是被资源硬线终止的伪失败。

V7 Lane A 的 tracked compact record 与既有 outcome 身份如下；这里只引用并核对 hash，
不重写历史证据：

| 证据 | path | SHA256 |
|---|---|---|
| exact-side full record | `benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v7_exact_side_full_formal_v1.json` | `412610be438423e893c6886bf617132b3cb5f0241937243e3cd1fb1303104bd2` |
| setup-limit outcome | `outcomes/v7_exact_side_limit.md` | `c2949060d5b152f904c504e85478ff1531bcc3157e62a2403010e37e91e8b289` |

## 4. V8-1 layer-block authority

V8-1 的 tracked compact record 没有另造一份独立 JSON；为避免把 V8-3 record 冒充 V8-1，
这里明确绑定 outcome 与 raw authority：

| 证据 | path | SHA256 / 身份 |
|---|---|---|
| V8-1 outcome | `outcomes/v8_layer_block_operator.md` | `9efe6a1bcb1b1161fb45aa759d5bdfb91357d4b24fd1834efb902759bc2d7a9c` |
| raw root | `results/task039_v8_h4_layer_block_reconstruction_mpi8_f6fc04a5` | source `f6fc04a53928c948873a5c2b3e0c95c10fcfeb5b` |
| raw run summary | `.../run_summary.json` | `164a651e6266bef0ddca52251f21d34e4692989db5788563cd4ffe5ee7b9dbb4` |
| raw diagnostic | `.../numerical_output/v3_v7_diagnostic.json` | `65da0a73e6ada42e86ec9a58595bb45a2e0814c0cbe51c7a93c61a5a86309bcc` |

其独立 authority 是真实 h4 `F` 的 local block reconstruction：6 layers、132300 rows、
105038640 NNZ，其中 same-layer `75327840`、adjacent-layer `29710800`、long-range `0`、
half-bandwidth `1`，8 个 hash-bound complex vectors 的原 F/action identity 通过。完整
JSONL process-tree peak 为 `16180523008 B = 15.0692863464 GiB`；PSS/USS 未测量。
该图只描述 bare local `F`，明确排除 DtN 的 global low-rank correction。

## 5. V8-3 layer sweep negative authority

V8-3 compact record 是下列五方法表的唯一数字源：

[`task039_v8_layer_sweep_bottom_v1.json`](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v8_layer_sweep_bottom_v1.json)

其 SHA256 为 `1a13216ccf9dfcb17e2f19abdf07376014f5a5bf7aa9a969fa84c3367c46812a`；raw root 为
`results/task039_v8_h4_layer_sweep_bottom_component_mpi8_c3c84a8d`，source SHA 为
`c3c84a8d2538f6e534aac65fd7da94f1b51d4d83`。五方法严格按 J1→F1→FB1→FB2→FB4 串行，
每次 Woodbury destroy 后 collective cleanup；没有 preferred rehydration，因此 overall
retained 是 `not_available/not_run`，不能用临时 method interval 冒充 30 GiB Gate。

| method | K rank / condition | worst mandatory residual (`<=1e-2`) | repeat / linearity (`<=1e-10`) | result |
|---|---:|---:|---:|---|
| J1 | `296 / 63.94325058975744` | `45.24747348981373` | `2.1517e-13 / 2.3087e-13` | residual fail |
| F1 | `296 / 63.94325058975718` | `141.532433583195` | `1.7451e-10 / 1.2509e-10` | repeat/linearity/residual fail |
| FB1 | `296 / 19096010.927585065` | `1244.7282511892267` | `5.1217e-09 / 5.0354e-09` | repeat/linearity/residual fail |
| FB2 | `296 / 7847304509017.3955` | `52831.65459906019` | `2.1347e-04 / 2.0448e-04` | repeat/linearity/residual fail |
| FB4 | `55 / 3.1808907871836678e25` | `2025057925864.6484` | `1.8963 / 3.2920` | repeat/linearity/residual fail |

J1 仅 finite/repeat/linearity 通过，仍未达到 residual Gate；F1/FB1/FB2/FB4 的稳定性和
residual 均失败。`lifecycle.sweep_diagnostics_after_cleanup.method=FB1` 是对象默认字段，
不是最后方法身份；方法裁决只取 compact record 的 `method_records`/raw markers。
`controlled_numerical_negative`/worker exit3 是数值 Gate 的受控退出，不是资源 stop；
parent termination 为 null、warning 为 false、45 GiB hard line 未触发。

## 6. V9-0 资源与 ABI 快照

以下是本轮 qualified activation 下的只读 host snapshot，不是 PDE readiness，也不是 V9
component resource Gate：

| 项目 | measured |
|---|---|
| qualified activation | `_MYFENICS_WSL_QUALIFIED_ACTIVATION=1` |
| interpreter | `/home/Projects/MyFEniCS/.venv/bin/python` |
| MPI | Open MPI `4.1.6`；本探针 world size `1`；formal identity 仍为 MPI8 |
| PETSc | Scalar `complex128`；Int `int32` |
| DOLFINx / SLEPc | import available / import available |
| threads | `OMP_NUM_THREADS=1`；`MKL_NUM_THREADS=1`；`OPENBLAS_NUM_THREADS=1` |
| MemAvailable | `235420132 kB` |
| swap | total `33554432 kB`；free `33554432 kB`；used `0 kB` |
| filesystem free | `/home/Projects/MyFEniCS`：`817265295360 bytes` |

## 7. V9 阶段顺序、Gate 与本轮停止边界

V9-0 只完成本继承审计。后续阶段的授权边界如下，均未在本轮启动：

| 阶段 | frozen scope | 主要 Gate / stop |
|---|---|---|
| V9-1 | 只重评 J1/F1 的 bare `F` 与完整 `A_side` 五 holdout residual | 逐 label `r_F`/`r_A`、amplification、K/W/C/D/H inventory；不重跑 FB1/2/4 |
| V9-2 | tiny exact Schur algebra；h4 固定 SN0=[0,1]、SN1=[2,3]、SN2=[4,5] | SN2-J 与 SN2-SGS；只允许3 supernode factors，construction `<=45 GiB`、retained `<=30 GiB`、swap0 |
| V9-3 | 直接求 `A_side x=b` 的 bottom inner FGMRES | max_it `4→8→16`；只有16步相对4步下降两 decade且持续下降才允许一次32；报告真实 history，不伪造 linearity |
| V9-4 | 条件 Schur-update compressibility audit | 仅由 V9-3 条件触发；固定 sketch rank `16/32/64`，rank64 holdout action error `<=1e-3` |

V9 的数学身份保持：

```math
A_{\mathrm{side}} = F - C H^{-1}D.
```

V8 graph 只证明 `F` 的局部 block-tridiagonal 结构，不证明完整 `A_side` 仍为局部带状
矩阵。若采用 inner FGMRES，必须直接处理完整 side action；不能把 variable/nonlinear
inner solve 静默写成固定线性 Woodbury inverse。

## 8. 冻结项、禁止项与结论

本轮以及后续未获新 review 前保持：ordinary defaults unchanged、master untouched、无新
branch/worktree、5 nm/1°/phi0/S/p6h4/M480/MPI8 身份不变。以下项目在 V9-0 均
`forbidden/not_run`：

- Hybrid direct rerun、V7 exact-side full rerun、V7 raw-source Petrov 原样重跑；
- FB8/FB16、damping/relaxation、普通 ILU/drop-tolerance 或 generic budget sweep；
- Petrov rank >512、第三 BLR、new Full3D heavy、完整 0.7 nm PDE；
- 未经 bottom Gate 的 top、both-side、full Hybrid formal；
- 删除/覆盖历史负结果、implementation failure、raw root 或 compact record。

V9-0 的结论是：V8 已证明 local-F 的层结构和低内存 block reconstruction 可行，但简单
`D_i` sweep 对真实 side source family 数值不足；V9 下一步必须先把 bare `F` 误差与
DtN low-rank 组合误差分开，再审查 Schur-aware preconditioner。该结论不提升任何
ordinary/default solver，也不改变 V7/V8 的负结果。
