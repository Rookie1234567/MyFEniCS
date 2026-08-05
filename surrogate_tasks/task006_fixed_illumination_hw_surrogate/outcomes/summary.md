# Task006 outcomes summary：固定三照明 h/w 代理与 forward robustness 受控停止

## 最终状态

Task006 M2R 的 training-only 修正、Case139 独立重放和模型锁均完成。随后按
锁定身份执行了一次且仅一次的 12 几何 × 3 照明 blind FEM 批次。36 条记录
全部尝试完成，其中 34 条通过固定前向 Gate，2 条在真实残差 Gate 失败。
Review V2 的 M3R0 Case143 无 FEM 检查通过后，两个失败 tuple 各执行两次完全
相同身份的 fresh-process 重试；四次都重现同一残差 Gate 失败。因此本任务以
`controlled_stop_blind_forward_incomplete` 收口：没有创建代理资格通过声明，
没有用 blind 响应调参，也没有开始主动加点或 Bayesian inversion。

| 项目 | 结果 |
|---|---|
| Task 状态 | `controlled_stop_blind_forward_incomplete` |
| 固定照明 | A05=(2°,0°), A07=(2°,90°), A09=(4°,60°)，S，13.5 nm |
| forward solver SHA | `fdf961545f217d620e22800f2704ae9913a6d270` |
| forward route | Full3D static uniform N1curl p5/h10/Ny4，mesh (6,4,14)，MUMPS ICNTL(14)=40，MPI2/thread1 |
| immutable training dataset | `task006_fixed_A05_A07_A09_hw_train37_p5_ny4_v1`，manifest `f36ffe992efe44f89c51bcac35e68145256e80979810d60ae5437686fd91cf84` |
| training / blind split | 37 / 12；training tuple hash `7948b6612e8350be1b6fd26aca010036016681f0484f4aa02b56c353f694bb28` |
| M2R selected candidate | `legendre_3`（固定六候选中按 training-only selection score 选择） |
| model lock | `TASK006_MODEL_SELECTION_LOCK.json`，只在 blind 前冻结；未改写 |
| 原始 blind FEM | 36 attempted；34 `measured_pass`，2 `failed_numerical_gate` |
| M3R 重试 FEM | 4 attempted；A07 0/2、A09 0/2 `measured_pass`；四次均只失败 residual Gate |
| blind response / validation target | checker 中未用于拟合；validation target 未访问 |
| formal inversion / active learning | 未运行 |

## M2R 修正与训练证据

S0 是唯一的 side-total authority：先在 `(R,T,A)` 上拟合
`zR=log((R+eps)/(A+eps))` 和 `zT=log((T+eps)/(A+eps))`，再以
`softmax(zR,zT,0)` 恢复三项。S1 不再有独立 production side-total 模型，
只拟合冻结反射/透射 m=0 primary channel 的 selected/other fraction；
selected、other 和 S0 side total、ledger residual 均逐点保存。这样同一侧功率
不会在 aggregate 与 order-resolved 合同中被重复计数。

geometry-grouped 五折 folds 已写入并冻结为
`TRAIN37_GEOMETRY_FOLDS.json`；每个 geometry 的三个照明同折留出，全部
37 个 test membership 恰好一次。原六候选完整重跑的结果写入
`TRAIN37_MODEL_COMPARISON_V2.json`、`TRAIN37_OOF_PREDICTIONS_V2.json`、
`TRAIN37_S1_LEDGER_V2.json`、`TRAIN37_UNCERTAINTY_V2.json` 和
`TRAIN37_SYNTHETIC_RECOVERY_V2.json`。M2R 选出 `legendre_3`，并通过 training
Gate 与 37 点 synthetic recovery；这是对已有训练数据的资格化，不是 blind
结果。

Case139 checker 独立重建 transform、fold membership、OOF prediction hash、
composition、ledger、CV 指标和 recovery，结果为 `pass`。随后创建的模型锁
绑定 dataset/file hashes、forward SHA、S0/S1 合同、candidate、全量拟合元数据、
fold identity 和 blind tuple hash；锁文件在 blind 运行后仍保持原始 pre-run
身份。

## Blind 结果、M3R 重试与失败原因

Blind runner 只接受上述锁，使用固定 `fdf9615`、p5/Ny4、ICNTL(14)=40、
MPI2/thread1，按锁定顺序串行运行 36 个新 FEM。两个原始失败点如下：

| blind key | forward status | 未通过 Gate | 其余关键 Gate |
|---|---|---|---|
| `117.5,17.25/A07` | `failed_numerical_gate` | `true_residual_le_1e-9=false` | direct solve、energy closure、固定 order、topology、n≠0 leakage、raw ledger 均 true |
| `117.5,17.25/A09` | `failed_numerical_gate` | `true_residual_le_1e-9=false` | direct solve、energy closure、固定 order、topology、n≠0 leakage、raw ledger 均 true |

失败记录只有 formal record，没有 production sample；二者各自只尝试一次。没有
提高残差容差、跳过点、删除偏振或改 channel。Case141 checker
验证了 36 个 key/point hash 恰好覆盖、锁 hash 一致、失败记录被保留、成功
sample 的 source/split/solver identity 正确，checker 状态为 `pass`，但
`qualification_status=controlled_stop_blind_forward_incomplete`。

对 34 条成功响应，锁定 Legendre-3 在不改变任何阈值的情况下给出下列只读
诊断（缺失的 A07/A09 两条不被填补）：

| 诊断 | 结果 |
|---|---:|
| S0 successful-row minimum 95% coverage | 1.0 |
| S1 successful-row minimum 95% coverage | 1.0 |
| S0 composition max residual | `1.11e-16` |
| predicted S1 selected/other nonnegative and selected≤side | true |
| predicted side ledger max residual | `0.0` |
| successful response rows | 34 / 36 |
| complete blind geometries available for recovery | 11 / 12 |

11 个完整几何的锁定模型 recovery 本身显式收敛且误差很小，但由于一个 geometry
缺少两个照明的真实响应，12/12 recovery Gate 不能宣称通过。最终失败不是由
删去失败样本或调大容差得到，而是由两个真实 residual Gate 失败直接触发。

### M3R 受控重试

Case143 在没有 FEM 的情况下冻结了仅包含上述两个 tuple 的 retry plan，并核对
了原 Case141 campaign、failure report、模型锁和失败目录的 hash。随后按
`fdf9615`、p5/Ny4、mesh `(6,4,14)`、MUMPS `ICNTL(14)=40`、MPI2/thread1 和
原 `1e-9` residual Gate 运行四个 fresh-process attempts：

| tuple | attempts | relative residual（两次相同） | 唯一失败 Gate | 响应一致 |
|---|---:|---:|---|---|
| `117.5,17.25/A07` | 2/2 | `1.5050283166105661e-09` | `true_residual_le_1e-9` | true |
| `117.5,17.25/A09` | 2/2 | `1.4079544140587495e-09` | `true_residual_le_1e-9` | true |

四次重复均保留 formal record、execution hash、KSP/MUMPS/resource 遥测，且未生成
production sample。Case144 checker 的 `status=pass` 表示它独立确认了四个
attempt 的身份、hash、唯一失败 Gate 和固定 order 复响应一致；其资格字段仍为
`blind_forward_route_not_reproducibly_qualified`。由于两个 tuple 都不是 2/2
`measured_pass`，没有 canonical retry、没有重用 34 条成功记录、没有执行唯一的
12/12 full blind qualification。

## 证据索引与停止边界

- M2R folds/CV/ledger/uncertainty/recovery：`outcomes/TRAIN37_*_V2.json`
- M2R selection：`outcomes/TRAINING_MODEL_SELECTION_CANDIDATE_V2.json`
- Case139：`benchmarks/cases/139_task006_m2r_contract_replay/records/case139_check.json`
- immutable model lock：`outcomes/TASK006_MODEL_SELECTION_LOCK.json`
- blind campaign manifest（ignored raw artifact）：`benchmarks/artifacts/cases/141_task006_blind12_forward/BLIND12_CAMPAIGN.json`
- blind controlled-negative report：`outcomes/TASK006_BLIND_FAILURE_REPORT.json`
- Case141 independent checker：`benchmarks/cases/141_task006_blind12_forward/records/case141_check.json`
- M3R0 failure telemetry：`outcomes/BLIND_FORWARD_FAILURE_TELEMETRY.json/.md`
- M3R0 retry plan：`outcomes/BLIND_RETRY_PLAN.json`
- M3R0 tie audit：`outcomes/MODEL_SELECTION_TIE_AUDIT.json/.md`
- Case143 preflight checker：`benchmarks/cases/143_task006_blind_retry_preflight/records/case143_check.json`
- M3R retry manifest/checker：`benchmarks/cases/144_task006_blind_retry_requalification/records/case144_check.json`
- M3R forward closeout：`outcomes/TASK006_BLIND_FORWARD_RETRY_CLOSEOUT.json/.md`

本轮到此停止并等待后续审阅。不得把这次 blind 负结果或四次 retry 负结果改写
为代理资格通过，不得重复使用这 12 个 geometry 调参后再次声称 blind validation，
也不得在没有新任务书/审阅前开始主动加点、Task007、Bayesian inversion 或新的
输入参数。
