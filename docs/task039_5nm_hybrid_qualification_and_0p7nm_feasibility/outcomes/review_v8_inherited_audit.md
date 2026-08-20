# Task039 Review V8：继承审计（V8-0）

本文件是 V8-0 的 docs-only inherited audit。它核对当前 V8 的代码/证据起点、V7
完整结果和负结果、以及下一阶段的严格边界。本阶段没有修改 Python、配置或测试阈值，
没有启动 PDE、MPI job、QEP、factor、solver 或 heavy run。

## 1. Git 与审计身份

| 字段 | 实测值 | 说明 |
| --- | --- | --- |
| branch | `codex/20260812-task39-5nm-hybrid-0p7nm-feasibility` | 唯一 Task39 执行分支 |
| V8 reviewed ancestor | `58866d6cdc24287e141ae1bcddbddc208c410045` | Review V8 的 reviewed_head；V7 docs/evidence closeout |
| current HEAD | `b025ba2d744b4402e730f03968d452bc93e16614` | V8 review 拉取后的当前审计起点 |
| upstream | `origin/codex/20260812-task39-5nm-hybrid-0p7nm-feasibility` at `b025ba2d744b4402e730f03968d452bc93e16614` | fetch 后精确一致 |
| ahead / behind | `0 / 0` | `HEAD...@{upstream}` |
| initial worktree | `clean` | fast-forward 前后均无 dirty/untracked |
| review_report_v8 SHA256 | `6fadd9172589c8be9f2070b47bdd6d524e9089ecd8d314e0d446f14786e9aa55` | 该 review 是本次 fast-forward 引入的权威文件 |

本审计创建后，文件本身会使工作树变为只含一个 docs-only change；不涉及 master、
新分支或新 worktree。V8 review 的目标与当前 branch 身份一致，没有发现近似分支歧义。

## 2. V7 结果与 compact identity

以下数值沿用既有 V7 evidence，不在本轮重算或改写。`response_v8.md` 是 V7 最终回应，
不是 V8 的新结果回应。

| 文件 | SHA256 | 继承用途 |
| --- | --- | --- |
| [`response_v8.md`](../response_v8.md) | `41a8aba67c61e508e4d8e1d121233c7c648196b01252f45284a8ac7190819312` | V7 full/producer/consumer/graph 结项边界 |
| [`review_v7_inherited_audit.md`](review_v7_inherited_audit.md) | `37be59f9a15b289a6bfc8174486b39905f474e8478555a8b597c698f84773433` | V7 继承审计 |
| [`task039_v7_exact_side_full_formal_v1.json`](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v7_exact_side_full_formal_v1.json) | `412610be438423e893c6886bf617132b3cb5f0241937243e3cd1fb1303104bd2` | Lane A full formal |
| [`task039_v7_exact_side_limit_setup_v1.json`](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v7_exact_side_limit_setup_v1.json) | `746ca172aaa025fd49bac52c2d4212cc14d00b764b3b6056f9d97d0d6d73a85e` | Lane A setup advancement |
| [`task039_v7_streamed_bottom_basis_producer_v1.json`](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v7_streamed_bottom_basis_producer_v1.json) | `ae1dc51123558809023f412b26e7742ce97cbb2df7c25c6c98e35a63fe01cb45` | Lane B producer |
| [`task039_v7_petrov_bottom_consumer_v1.json`](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v7_petrov_bottom_consumer_v1.json) | `0c3ad872d864c60364c5042cd366717c5c055e03b6c6851b689768fd15ff691c` | Lane B consumer |
| [`task039_v7_side_layer_graph_v1.json`](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v7_side_layer_graph_v1.json) | `93c8973e28b316813ccc692f702c8a61b31239469346a1a49e96152b732f71cd` | Lane C graph-only |

## 3. Matched h4 identity、packet 与 holdout

| 项目 | 已冻结事实 |
| --- | --- |
| input | `input/official/task039/5nm_p6h4_v4_1deg_hybrid_iterative_m480_mpi8.dat` |
| input SHA256 | `4e60924b5997e3ca99e324ea14779f9014efc6a1304a9aa11de9c808353f1811` |
| physical model SHA256 | `8391d46139646440d869aa43abe6a68bc921fc1972a10030c64be81dffdd527c` |
| selected packet root | `results/task039_v4_h4_m480_shared_packet_eaad0f94` |
| selected manifest SHA256 | `2dddaf7a6f8f045adabd840970952517d76305c7c0e03c71258642d856c13067` |
| selected identity SHA256 | `b3bb870fe6fa17cb262b6161f7317cc1950944755c9270d4628dd5c79e950690` |
| selected runtime identity SHA256 | `cfd5704b48bff980fa2d819f4deee9a59bb9a3db39bc24a70c53f42f067d39e9` |
| exact bottom holdout root | `results/task039_v5_h4_mumps_blr_side_component_mpi8_7e5d9b57_1e3/numerical_output` |
| holdout source SHA | `7e5d9b57a10b1093f0cb062eaf7bc12797c47e1f` |
| holdout catalog SHA256 | `a2a7fb6fb01df4f795d31ff94f6ac6adf957ac4fe4a5c1a8d05176e3d64c0384` |
| holdout inventory | 8 producer ranks, 6 labels, 96 response artifacts |
| holdout role | frozen oracle/holdout only; never training data |

V7 producer 的最终 basis manifest SHA256 为
`44023b8d8d3932e5cf5d0d42a16711f886e7672570e0318cb0339b44b691c44b`，包含 8 shards、
global rows `132300`、complex128、64/128/256/512 nested prefixes 和连续 ownership。
V8 不把该 Petrov basis 当作新的训练入口；V7 raw-source family 已关闭。

## 4. V7 继承结果边界

| 路径 | 关键实测 | 当前身份 |
| --- | ---: | --- |
| matched h4 Hybrid direct | `93.377006531 GiB` | full-workflow reference |
| Lane A setup-only | `81.056903839 GiB`；`10649.634795 s` | 独立 `f4073ada` setup advancement pass |
| Lane A exact-side full formal | `80.025856018 GiB`；`10126.231902 s`；1 outer iter | 唯一完整低于 direct 的 V7 正结果；节省 `14.298113646%` |
| Lane B streamed producer | `11.630760193 GiB`；约 `415.6 s` | component resource/lifecycle pass |
| Lane B streamed consumer | `23.038208008 GiB`；约 `632.8 s` | component resource pass；rank512 residual negative |
| Lane C graph-only | wall/RSS `not_measured` | independent structural evidence only |

Lane A setup-only 的 measured peak 是 `81.056903839 GiB`，来自先前唯一的
`f4073ada` setup run；`84.039305878 GiB` 是 V7 允许进入 full formal 的 setup
advancement threshold/line，不是 measured peak。Lane A full formal 以严格低于 direct
为 full-workflow resource qualification；它仍保留完整 side factors，不能提升为 0.7 nm
scalable architecture。

Lane B consumer 的四级 coarse `E=Y^H F Z` condition 均低于 `1e12`，但 worst mandatory
residual 为 `219.375773963 / 310.531296720 / 1143.092533433 / 1521.816092530`，因此
classification 为 `NUMERICAL_LIMIT_NOT_REACHED_BY_RANK512`。top、both、outer、recovery、
R/T/A 和 fields 均 `not_run`。V7 的首次 telemetry/ownership implementation failures、
V5/V6 负结果和 raw roots 均保持原样。

Lane C 的独立 local-F 图证据为 bottom/top 均 6 层、132300 rows、105038640 NNZ，
same-layer `75327840`、adjacent-layer `29710800`、long-range `0`、block half-bandwidth `1`。
该统计排除了 DtN global low-rank coupling；它只授权 V8 继续审查 layer-aware operator，
不等于 sweep solver 已实现或通过。

## 5. V8 阶段、Gate 与本轮边界

| 阶段 | 允许内容 | 关键 Gate/停止语义 | 当前状态 |
| --- | --- | --- | --- |
| V8-0 | 继承审计 | docs-only；不运行 heavy | 本文件 |
| V8-1 | 从真实 F 提取 D/L/U block CSR | 8 个 hash-bound complex vectors action error `<=1e-12`；coverage/NNZ exact；long-range `0`；bandwidth `1`；repeat/linearity `<=1e-13` | not_run |
| V8-2 | 六个 bounded layer factor 与固定 J1/F1/FB1/FB2/FB4 | 不得 full side factor、dense Schur、nested variable KSP；不得超过 FB4 | not_run |
| V8-3 | bottom-only layer-sweep component | construction `<=45 GiB`、retained `<=30 GiB`；数值 finite/repeat/linearity、mandatory `<=1e-2`、modal+/−/external `<=1e-3`、swap0 | not_run |
| V8-4 | 条件性的 top、both setup、full formal | bottom 先通过；both setup `<=76.024563217 GiB`；full formal residual/physics/lifecycle 全通过 | forbidden until prior Gates pass |
| V8-5 | 条件性的 matrix-free channel K component | 仅 sweep 通过后；不形成 W/dense K；16 vectors action error `<=1e-10` | not_run |

V8 完整 workflow 的分级线为：direct `93.377006531 GiB`；当前 best `80.025856018 GiB`；
`<=74.701605225` 为 20%，`<=65.363904572` 为 30%，`<=56.026203919` 为 40%，
`<=46.688503266` 为 50%，`<=37.350802612` 为 60%。V8 新算法只有严格低于
`80.025856018 GiB` 才可称 `NEW_ITERATIVE_MEMORY_BEST`。

默认 heavy timeout 为 `21600 s`；只有已进入完整 outer、swap=0、RSS 低于 direct、KSP
仍推进、无 NaN/Inf、真残差持续下降且预计两小时内完成时，才允许一次延长到总 `28800 s`。
component、factor setup、oracle producer、QEP、graph 和未进入 outer 的阶段不得延长。

## 6. 环境与 ABI 轻量快照

以下是 qualified activation 下的只读 probe；它不是 PDE readiness，也不是正式资源 Gate。

| 项目 | measured |
| --- | --- |
| activation / interpreter | `_MYFENICS_WSL_QUALIFIED_ACTIVATION=1`; `/home/Projects/MyFEniCS/.venv/bin/python` |
| platform | Linux WSL2 `6.18.33.2-microsoft-standard-WSL2-x86_64` |
| MPI | Open MPI `4.1.6`; probe world size `1`；V8 formal identity仍冻结 MPI8 |
| PETSc | Scalar `complex128`; Int `int32` |
| SLEPc / DOLFINx | import available / import available |
| threads | `OMP_NUM_THREADS=1`; `MKL_NUM_THREADS=1`; `OPENBLAS_NUM_THREADS=1` |
| MemAvailable | `235330120 kB` |
| swap | total `33554432 kB`; free `33554432 kB`; used `0` |
| filesystem free | `/home/Projects/MyFEniCS`: `817218879488` bytes |

## 7. 冻结项与禁止项

V8 仍冻结 5 nm、1° grazing、phi=0、S、p6/h4、M480、MPI8 物理身份；不得改变材料、
mesh、M、MPI、ordinary solver/default、external identity 或 hard line。明确禁止：新的
Full3D heavy、Hybrid direct/exact-side Lane A rerun、完整 0.7 nm PDE、M sweep、第三 BLR、
ordinary ILU0/ILU1/drop-tolerance scan、fixed-budget scan、Petrov rank >512、原样重跑 V7
raw-source Petrov、多个 heavy 并发、master 写入和新分支/worktree。

Full3D、direct/exact rerun、0.7 nm PDE、第三 BLR 和 ordinary ILU/budget scan 在 V8-0
均是 `forbidden/not_run`。V8-0 不实现 layer block operator、layer factor、z-sweep、
matrix-free K，也不开始 top/both/full formal。

## 8. V8-0 结论

V7 提供了可信的 matched h4 full-workflow baseline、独立六层 local-F graph pattern 和
可复用的 negative/lifecycle evidence，但没有提供 layer sweep 的数值或内存结果。V8-0
因此只确认 V8-1 的问题定义和可审计 Gate：先证明 block extraction 与原 F 等价，再考虑
bounded factors；任何 bottom 数值/资源失败都关闭 top。当前无需、也未获得授权运行下一阶段。
