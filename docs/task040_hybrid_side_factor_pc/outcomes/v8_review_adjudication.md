# V8-0 Review adjudication

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

V8-1 的唯一专用入口为 `--v8-full-spectrum-only`。它复用 current bottom bare `F`、V5 frozen RHS/provider、canonical layouts 与已裁决的 D0 action，只进行 full-spectrum transform identity 后的两源 screen；不调用旧三尺度 identity、D0/D1 comparison、refinement/partition、exact packet publication 或 moving-PML。当前实现尚未正式运行，不能预先写 numerical positive/negative。
