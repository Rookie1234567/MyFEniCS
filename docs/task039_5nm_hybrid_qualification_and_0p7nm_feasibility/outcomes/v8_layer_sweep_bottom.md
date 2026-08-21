# V8-3：bottom layer-sweep 组件结果

## 结论先行

本次只运行了 5 nm、1°、phi=0、S、p6/h4、M480、MPI8 的 bottom 组件。它把六层的稀疏块扫法按
`J1 → F1 → FB1 → FB2 → FB4` 顺序逐一试用：每个候选完成后销毁临时 Woodbury 对象，再进入下一个候选。
这不是完整散射工作流，也没有进入 top、both-side、outer 或 recovery。

| 项目 | 实测/裁决 | 说明 |
|---|---:|---|
| 正式分类 | `LAYER_SWEEP_NUMERICAL_LIMIT_NOT_REACHED_BY_FB4` | 五个候选到 FB4 仍未通过数值 Gate |
| worker | exit `3`，`component_numerical_failed` | 数值 Gate 受控退出，不是资源终止 |
| construction process-tree peak | `23916404736 B = 22.273887634 GiB` | `<=45 GiB`，parent authority pass |
| overall retained interval | `not_available / not_run` | 数值失败后没有 preferred rehydration，不能宣称 `<=30 GiB` |
| peak swap | `0 B` | zero-swap pass |
| layer factors | ready `6` → cleanup `0` | 六个局部层因子，不是 full-side exact factor |
| full-side/global direct factor | `0 / 0` | formal inventory |
| nested KSP / QEP | `0 / 0` | 未构造 outer solver 或 QEP |

退出码 3 在这里表示 worker 已完成候选数值评估但未通过 Gate；raw ledger 的
`controlled_stop` 同样表示数值负结论。parent `termination=null`、`warning=false`，45 GiB 硬线没有触发，
因此不能把本次分类写成 memory stop。

## 方法与五个冻结 probe

这里的“残差”是 action 输出与冻结 exact-spool 参考的真实相对残差。`physical_side_rhs` 为零，按合同只作
degenerate 记录；其余五个 label 都必须参与 Gate。`preferred modal/external max` 是三项 preferred
通道（正模态、负模态、external）的最大值；它不是可以忽略的诊断字段。

| method | K rank / condition | setup s | apply wall s | worst mandatory residual | preferred modal/external max | max repeat | max linearity | 结论 |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| J1 | 296 / 63.94325058975744 | 74.049002075 | 4.768835524 | 45.24747348981373 | 34.24246487175865 | 2.1517e-13 | 2.3087e-13 | residual fail |
| F1 | 296 / 63.94325058975718 | 82.200138326 | 5.133227528 | 141.532433583195 | 137.9502681252083 | 1.7451e-10 | 1.2509e-10 | repeat/linearity/residual fail |
| FB1 | 296 / 19096010.927585065 | 159.145945567 | 9.839546085 | 1244.7282511892267 | 1244.7282511892267 | 5.1217e-09 | 5.0354e-09 | repeat/linearity/residual fail |
| FB2 | 296 / 7847304509017.3955 | 337.447901805 | 20.597998448 | 52831.65459906019 | 52831.65459906019 | 2.1347e-04 | 2.0448e-04 | repeat/linearity/residual fail |
| FB4 | 55 / 3.1808907871836678e25 | 696.156728291 | 42.186354544 | 2025057925864.6484 | 1147917207920.235 | 1.8963 | 3.2920 | repeat/linearity/residual fail |

阈值是：finite；repeat、linearity `<=1e-10`；全部非退化 mandatory true residual `<=1e-2`；
positive/negative modal 和 external `<=1e-3`；exact/global direct factor `0/0`；nested KSP `0`；swap `0`。
J1 只有 finite/repeat/linearity 通过，残差不通过；F1、FB1、FB2、FB4 的 repeat、linearity 和 residual
均未通过。FB4 仍未通过，所以不能选择 preferred action，也不能发出 retained apply-state pass。

六层扫法使用的固定代数可用下面的简式理解；`D_i` 是第 `i` 层的稀疏对角块，`L_i/U_i` 是相邻层
耦合块，`r_i` 是该层输入：

```math
J1:\quad x_i=D_i^{-1}r_i,\qquad
F1:\quad y_i=D_i^{-1}(r_i-L_i y_{i-1}) .
```

FB 候选在此基础上固定次数地做 defect correction；本次没有扫描其他次数或调参。

逐 probe 的 true residual 如下，数值均来自 worker record，compact record 只做同一 raw 的 hash-bound 摘要：

| label | J1 | F1 | FB1 | FB2 | FB4 | limit |
|---|---:|---:|---:|---:|---:|---:|
| modal traction + | 26.698419668 | 85.382397660 | 1244.728251189 | 52831.654599060 | 814266778812.2222 | `1e-2` mandatory; `1e-3` preferred |
| modal traction - | 34.242464872 | 89.987011092 | 856.931253723 | 40024.586527771 | 235173765223.59402 | `1e-2` mandatory; `1e-3` preferred |
| external C | 24.441460345 | 137.950268125 | 683.313614558 | 24634.595556879 | 1147917207920.235 | `1e-2` mandatory; `1e-3` preferred |
| fixed random 773 | 45.145500025 | 140.136506144 | 916.197838302 | 18662.360832410 | 1325994975045.71 | `1e-2` |
| fixed random 779 | 45.247473490 | 141.532433583 | 739.432542357 | 16501.790196910 | 2025057925864.6484 | `1e-2` |

## 资源与生命周期口径

parent samples 对完整 `construction_begin → construction_end` 区间取峰值，得到
`22.273887634 GiB <=45 GiB`。五个方法各自的 interval 只是 `evidence_only_checkpoint`，用于比较候选的
局部峰值；它们不能替代 Review 定义的 preferred `retained_apply_state_ready → retained_state_release`
整体区间。由于 numerical Gate 在 FB4 后失败，preferred rehydration 未运行，overall retained 是
`not_available / not_run`，不能把任何临时方法的 `22.15–22.27 GiB` 写成 `30 GiB` retained pass。

每个方法都在下一个方法开始前完成 Woodbury destroy 和 collective cleanup；最后六个 layer factors、
side components、system、spool 和 sweep 均释放。`sweep_diagnostics_after_cleanup.method` 在 raw 中为
`FB1`，这是对象的默认/非候选裁决字段；五个方法的权威身份只来自 `method_records` 与对应 markers，
不能用该字段替代最后方法身份。

raw `memory_object_ledger.status=controlled_stop` 与 worker exit 3 共同表示数值 Gate 受控退出。parent
`termination=null`、`warning=false` 且 peak 远低于 45 GiB，说明这不是资源 stop。raw 的 generic
`task039_memory_budget` 仍有 `224000000000 B`，那是历史通用预算；V8 authority 只能使用
`absolute_terminate_memory_bytes=48318382080 B`、effective hard stop `45 GiB`。

## 身份、边界与未运行项

正式 route identity 是 schema/profile/method/source SHA：
`task039.v8.h4.layer_sweep.bottom_component.v1` /
`task039_v8_h4_layer_sweep_bottom` /
`c3c84a8d2538f6e534aac65fd7da94f1b51d4d83`。raw generic `run_id` 含 `v4`，仅作为 inherited input
record 的观察字段，不作为 V8 route 身份。

本次复用的 frozen exact-bottom holdout 由 producer source
`7e5d9b57a10b1093f0cb062eaf7bc12797c47e1f`、catalog SHA256
`a2a7fb6fb01df4f795d31ff94f6ac6adf957ac4fe4a5c1a8d05176e3d64c0384` 绑定：8 个 producer ranks、6 个
labels、96 个 response artifacts；catalog 是对 sorted relative path、byte count 和 file SHA256 rows
取 SHA256。继承 authority record 的 SHA256 为
`00c8b889d75b7fa0b77a6563d4ffe708a07d00f23133dec06b5929e4cabe3368`。

selected-mode packet 没有打开；exact spool 只在 basis/setup 之后用于冻结 holdout。没有 QEP、outer KSP、
full-side exact/global factor、top/both-side/full formal、recovery、R/T/A 或 field export。

compact hash-bound record：[task039_v8_layer_sweep_bottom_v1.json](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v8_layer_sweep_bottom_v1.json)。
完整 raw 是 ignored local evidence：`results/task039_v8_h4_layer_sweep_bottom_component_mpi8_c3c84a8d/`，
不提交 `.jsonl`、worker stdout 或其他大型结果。

## 通俗解释

六层 sweep 的目的，是用逐层稀疏因子和相邻层耦合，降低一次性保存完整 side factor 的内存压力。它确实把
construction 控制在 45 GiB 以下，并把六个层因子从 6 个清理到 0 个；但这只说明内存生命周期可行，
不说明修正方向已经足够好。五个冻结物理 source 的残差仍远高于 `1e-2`，并且后几个 FB 候选的线性重复误差
也超过 `1e-10`，所以本次结论是 source/action 数值容量不足，而不是“内存优化成功即算法通过”。
