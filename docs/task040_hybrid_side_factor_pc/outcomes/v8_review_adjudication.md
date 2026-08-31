# V8-0 Review adjudication

## 当前 V8 authority（置于历史快照之前）

| 路线 | 当前 authority | 结论边界 |
|---|---|---|
| V7 scale-normalized identity | Review V8 `review_adjudicated=true`；selected=`D0_lower_memory`；`V7_SCALE_NORMALIZED_FULL_INTERFACE_IDENTITY_PASS_D0` | raw `formal_adjudication=false` preserved；V6 absolute-threshold negative 不改 |
| dedicated full-spectrum | `FULL_SPECTRUM_IMPLEMENTATION_FAILURE` | transform identity PASS（actual lower/upper=`7560+7560`，`72 channels × 105 harmonics`，`numeric_allgather=false`，`full_plane_numeric_replica=false`）；两个 source entries/orchestration 已形成，但 owner-vector load 失败；无 source begin/end raw marker、无 one-apply/FGMRES checkpoint，apply-count字段=`0` |
| adaptive Stage A | `V8_ADAPTIVE_STAGE_A_LOCAL_GATE_PASS` | 630 patches、rows `432/432/432`、POU error `0`、固定 shift `0.1`；组件 Gate 不是 full numerical pass |
| exact generalized harmonic B1 | `not_completed_at_10800s` | root=`results/task040_v8_adaptive_stage_b1_mpi8_0e92079f_fix1`；wall timeout=`10800s`；无 run summary/数值结果；不是 numerical no-signal |
| adaptive Stage B/C | `ADAPTIVE_ECONOMICAL_COARSE_RESOURCE_UNAVAILABLE` | 630 patches 的 harmonic columns 已形成；symbolic projected peak 超过 45 GiB，未分配 coarse/outer；无 source begin/end raw marker、无 one-apply/FGMRES checkpoint，apply-count字段=`0` |
| 当前任务 | `open / review required`；`selective merge=NO` | 没有 adaptive numerical no-signal，也不创建 Full3D handoff |

当前实现/正式运行身份为 `source HEAD/upstream/worktree=0ed2ebef3916fa209136310b104ec72b54f167d7 / 0ed2ebef3916fa209136310b104ec72b54f167d7 / clean`。下方原有 V7 adjudication 表和 V8-1 预运行文字保留为历史背景；它们不能覆盖上述已完成的 V8 formal evidence。

## 当前正式证据入口

- full-spectrum：`results/task040_v8_full_spectrum_mpi8_089bf8a1_native_phase_repair1`；用户入口中的 source SHA 是 `089bf8a10441b83c5d293a02d649670675b631ca`，不是当前文档源 HEAD。
- adaptive Stage A：`results/task040_v8_adaptive_stage_a_mpi8_0b6c6a26_fix1`；local service Gate pass，global true residual relative=`2.390497409724407` 不作为该 Gate 失败。
- adaptive Stage B/C：`results/task040_v8_adaptive_stage_bc_mpi8_0ed2ebef_native`；live baseline=`19658432512 B`，projected=`130502065136 B`=`121.539519295 GiB`（约 `121.540 GiB`），hard=`48318382080 B`=`45 GiB`，allocation=`false`。

`factor_bytes_global=0` 只表示诊断矩阵 release 后的字段，不表示 factor 内存为零；BC cleanup 的 bare-F before/after hash 均为 `1cc07ab68ed747abfe7599ce1fdfeff95642653b29863d6f261e2fe9239d574f`。完整 stage table 与 SHA 索引见 [V8 response v9](../response_v9.md)。

本页把 Review V8 对既有 V7 证据的项目级裁决与尚未运行的 V8-1 专用路线分开记录。它不修改任何 raw/checker artifact。

| 项目 | 裁决或绑定 |
|---|---|
| Review V8 commit | `0ce67c0c68c36e9677f3293a87c1c124e82c6f70` |
| review adjudication | `review_adjudicated=true` |
| V7 identity | `V7_SCALE_NORMALIZED_FULL_INTERFACE_IDENTITY_PASS_D0` |
| selected | `D0_lower_memory` |
| raw formal field | `raw_formal_adjudication=false_preserved` |
| V6 absolute | negative unchanged; historical absolute thresholds remain authoritative for that record |
| input SHA256 | `4e60924b5997e3ca99e324ea14779f9014efc6a1304a9aa11de9c808353f1811` |
| physical-model SHA256 | `8391d46139646440d869aa43abe6a68bc921fc1972a10030c64be81dffdd527c` |
| resolved-config SHA256 | `f965c38abea08bee0ff83a6603e336ca4823deb932af7064aed3c571f8f63883` |
| selected-mode packet SHA256 | `2dddaf7a6f8f045adabd840970952517d76305c7c0e03c71258642d856c13067` |
| current bare-F identity | implementation audit `c468392a50d671a2cb2bbddc9d4d55400bb2de17554ddf772b2f549071fee24a`; source `e7fee3c2` |
| V7 bundle | `results/task040_v7_scale_normalized_identity_mpi8_e7fee3c2_native/worker/rank0000/v7_scale_normalized_identity_bundle.json`, file SHA256 `dfc137c13e5811aa9b84c107400f6406b8a945f47a2a9d3ddf7631ced637c40e` |
| V7 logical raw/checker | `a2aa1a72655bb695d663ec2c67b33115409715c75c0513e7b8fdf04d26bb59c6` / `768d094726ff6d458906885fe2ef602edbcdb13e9e20ceb2e008b8fc081193a4` |
| last full-spectrum implementation fix | `a2acb9344a9bd246a399c9110207926c7e03460e` |
| moving-PML raw root | `results/task040_v7_moving_pml_mpi8_7b237ea6_native_rerun1`; watchdog summary SHA256 `4d846cdd463f3e8574393fc05f5574cfde0cc71e13695000402acfa4e078cf02` |

V7 的 `review_adjudicated=true` 只接受三尺度、D0/D1、Layer A/B/C 与独立 checker 已有证据；它不把 raw 中的 `formal_adjudication=false` 改写为 true，也不改变 V6 absolute negative。moving-PML owner-serial implementation 已 retired from heavy rerun，但 method family not numerically rejected；其资源 Gate 记录仍保持原样。

## 历史 V8-1 预运行快照

V8-1 的唯一专用入口为 `--v8-full-spectrum-only`。它复用 current bottom bare `F`、V5 frozen RHS/provider、canonical layouts 与已裁决的 D0 action，只进行 full-spectrum transform identity 后的两源 screen；不调用旧三尺度 identity、D0/D1 comparison、refinement/partition、exact packet publication 或 moving-PML。当前实现尚未正式运行，不能预先写 numerical positive/negative。
