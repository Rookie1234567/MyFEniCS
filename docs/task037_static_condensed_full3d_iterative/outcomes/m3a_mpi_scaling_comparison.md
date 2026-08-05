# M3a MPI1/2/4/8 Full3D full-solve 对比

## 结论

本报告比较同一 p6/h10、13.5 nm、S 偏振、M3a overlap `0.125`、
partition-of-unity、16-slab、full-solve 候选在 MPI1/2/4/8 下的正式结果。
四组计算都完成迭代收敛、full explicit residual、official R/T/A 和 canonical
field 导出，且 swap 均为 0。MPI1/2/8 相对 MPI4 的 active-trace 与 full-FE
canonical relative L2 全部通过 `<=1e-5`，因此同一离散问题的跨 MPI 数值一致性
已经建立。

资源结论不是“MPI 越多越省内存”：MPI1 的 process-tree 峰值最低，为
`4.600486755371094 GiB`；MPI8 最快，但峰值升至
`12.59341049194336 GiB`，唯一失败项是 Task37 的绝对内存 Gate
`<=10.30 GiB`。在该模型和当前实现下，MPI4 是内存 Gate 内速度较快的折中；
若优先极致省内存，应选择 MPI1 或 MPI2。

结构化记录见
[task37_m3a_mpi_scaling_v1.json](../../../benchmarks/cases/100_static_condensed_full3d_iterative/records/task37_m3a_mpi_scaling_v1.json)。

## 比较身份与边界

| 项目 | 值 |
|---|---|
| branch | `codex/20260803-task37-matrix-free-iterative-development` |
| MPI4 numerical/canonical source | `2631a4c47258c9def919530787e409774b8ce029` |
| MPI1/2/8 carrier source | `a51c54576655f36078446766f856fcb96431e190` |
| carrier delta | 只把 M3a runner 的允许 MPI 集合从 MPI4/8 扩为 MPI1/2/4/8，并更新 parser tests；没有改变 `src/` 数值内核、M3a candidate 或 ordinary defaults |
| model | p6 Nedelec / h10 / 13.5 nm / theta normal 80 deg / phi 0 / S / 252 cells |
| solver | action-only static-condensed right FGMRES；16 owner-local slabs；overlap 0.125；partition weights；factor-only ILU(0)；75D coarse |
| solved rows | 51192 independent trace + 80 auxiliary = 51272 augmented rows |
| resource authority | simultaneous process-tree RSS；worker RSS/PSS/USS 另列；swap 必须为 0 |
| production / 0.7 nm qualification | NO / NO |

MPI4 与其余三组的完整仓库 SHA 不相同，因此这里不宣称“同一 Git SHA”。允许
比较的依据是：`2631a4c4..a51c5457` 没有 `src/` 数值内核变化，而
`a51c5457` 本身只改变 M3a 的 MPI admission/parser coverage。raw artifact 仍分别
绑定各自完整 source SHA，不把 carrier SHA 冒充 numerical kernel SHA。

## 数值收敛与物理结果

| MPI | iterations | full-FE true residual | R_total | T_total | A_volume | energy closure | official |
|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | 352 | `9.973612808764094e-7` | `0.0007628808460340567` | `0.6027016359436813` | `0.39653548322357507` | `1.3290479827787749e-11` | true |
| 2 | 352 | `9.998092180122628e-7` | `0.0007628809668627569` | `0.6027016342628001` | `0.3965354830689079` | `-1.7014292197359282e-9` | true |
| 4 | 365 | `9.923273535279698e-7` | `0.0007628813414779686` | `0.6027016365247442` | `0.396535483656842` | `1.5230641192687244e-9` | true |
| 8 | 341 | `9.861361777006587e-7` | `0.000762881851194442` | `0.6027016332025633` | `0.3965354818843407` | `-3.0619016211375083e-9` | true |

相对 MPI4，MPI1/2/8 的最大 total absolute differences 分别为：

| MPI vs MPI4 | abs dR | abs dT | abs dA_balance | abs dA_volume |
|---:|---:|---:|---:|---:|
| 1 | `4.954439119164364e-10` | `5.810628644908888e-10` | `1.0765067726126176e-9` | `4.332669223394703e-10` |
| 2 | `3.746152116811119e-10` | `2.2619440764870546e-9` | `2.6365593042143587e-9` | `5.879340903014452e-10` |
| 8 | `5.097164733477641e-10` | `3.322180863740698e-9` | `2.812464372503598e-9` | `1.7725013123914835e-9` |

全部 80 个 `(side,m,n,polarization)` modal order 的 key set 都是
`80/80`、missing=0、extra=0。相对 MPI4 的最大单通道绝对差为：

| MPI vs MPI4 | max power abs diff | channel | max boundary-amplitude abs diff | channel |
|---:|---:|---|---:|---|
| 1 | `3.3459776060951185e-9` | `T(0,0)_s` | `4.4489116663045123e-7` | `R(-7,0)_s` |
| 2 | `5.143571013555004e-9` | `T(0,0)_s` | `4.6149409675294e-7` | `R(-7,0)_s` |
| 8 | `4.139281251092086e-9` | `T(0,0)_s` | `2.811637742495472e-7` | top `(-1,-1)_s` |

## Canonical field 跨 MPI 一致性

canonical comparison 直接从每组 manifest/shards 重新读取 canonical key 与
complex128 coefficient，不使用 partition-local raw vector 顺序。所有比较的
duplicate、missing、extra 都为 0。

| candidate vs MPI4 | active count | active relative L2 | active max abs | full-FE count | full-FE relative L2 | full-FE max abs | Gate |
|---:|---:|---:|---:|---:|---:|---:|---|
| MPI1 | 60402 | `1.9214832706239463e-6` | `6.239896061341726e-5` | 173802 | `1.2052664767630616e-6` | `6.239896061341726e-5` | PASS |
| MPI2 | 60402 | `1.9255151928308462e-6` | `6.217918919290708e-5` | 173802 | `1.2092442772177141e-6` | `6.217918919290708e-5` | PASS |
| MPI8 | 60402 | `1.1920243946216614e-6` | `3.559275876022748e-5` | 173802 | `7.372655278259994e-7` | `3.559275876022748e-5` | PASS |

这里的 Gate 是 relative coefficient L2 `<=1e-5`。max abs 仅作为局部最大系数
差异记录，不单独作为失败判据。

## 内存、耗时与并行效率

为保证四行 wall 口径一致，本表使用 watchdog 的
`environment_before.timestamp_utc -> environment_after.timestamp_utc` 生命周期
差。旧 MPI4 compact record 中 `701.6504903390305 s` 是更窄的既有 parent scope，
继续作为历史字段保留；不得与本表 wall 混算。

| MPI | process-tree peak GiB | worker RSS/PSS/USS MiB | derived GiB/rank | wall s | speedup vs MPI1 | efficiency | `<=10.30 GiB` |
|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | `4.600486755371094` | `4696.379 / 4640.899 / 4595.418` | `4.600487` | `1999.033196` | `1.000` | `1.000` | PASS |
| 2 | `5.682544708251953` | `5804.449 / 5467.450 / 5204.203` | `2.841272` | `1153.018865` | `1.733738` | `0.866869` | PASS |
| 4 | `8.265838623046875` | `8449.641 / 7505.691 / 7209.094` | `2.066460` | `711.570295` | `2.809326` | `0.702332` | PASS |
| 8 | `12.59341049194336` | `12881.059 / 10866.601 / 10558.777` | `1.574176` | `470.571549` | `4.248096` | `0.531012` | FAIL |

相对 MPI4：MPI1 总内存低 `44.34%`、wall 高 `180.93%`；MPI2 总内存低
`31.25%`、wall 高 `62.04%`；MPI8 wall 低 `33.87%`，但总内存高
`52.35%`。单 rank 平均内存随 MPI 增加而下降，但 process-tree 总内存因每 rank
运行时、函数空间、ghost/metadata、PETSc object 和输出工作区重复而上升。

### 分阶段 process-tree 峰值

| MPI | process start | FE setup | static-condensed assembly | solver/factor stage | after field | canonical export |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | `0.195` | `0.261` | `0.651` | `4.262` | `4.405` | `4.600` |
| 2 | `0.380` | `0.522` | `1.429` | `5.308` | `5.486` | `5.683` |
| 4 | `0.743` | `0.963` | `3.069` | `7.693` | `8.056` | `8.266` |
| 8 | `1.450` | `1.913` | `5.918` | `11.630` | `12.356` | `12.593` |

单位均为 GiB。`solver/factor stage` 是 watchdog 的宽阶段标签，包含 slab factor
setup 与 FGMRES solve，不能解读为一张已物化的 augmented matrix；四组记录都明确
`global_A=false`、`global_F=false`、global direct factor count=0。

## 因子分布与为何总内存随 MPI 增加

四组的全局因子工作量相同：factor rows `127656`、stored factor NNZ
`91415952`、CSR payload 下界 `1828829728` bytes。变化的是 owner 分布与每 rank
重复开销：

| MPI | max/min owner rows | unique exact factor classes | exact duplicate count | core setup s | core solve s |
|---:|---:|---:|---:|---:|---:|
| 1 | `127656 / 127656` | 7 | 9 | `166.883792301` | `1395.517657680` |
| 2 | `63828 / 63828` | 10 | 6 | `143.095201208` | `731.545896218` |
| 4 | `33696 / 30132` | 15 | 1 | `126.837074135` | `393.260218908` |
| 8 | `16848 / 13284` | 15 | 1 | `122.113068160` | `223.090014526` |

MPI1 把所有 slab 放在一个进程内，能够观察到中央 slab 的 9 个 exact duplicates；
当前实现仍逐个因子化，并没有复用它们。MPI 增加后相同物理 slab 分散到不同进程，
单 rank factor workspace 下降，但跨进程不能直接共享 PETSc COMM_SELF factor，且
每 rank 固定开销增加。这解释了“更快、每 rank 更小、但总内存更大”的组合。

## Gate 汇总与建议

| Gate | MPI1 | MPI2 | MPI4 | MPI8 |
|---|---|---|---|---|
| converged/full true residual | PASS | PASS | PASS | PASS |
| official R/T/A and energy closure | PASS | PASS | PASS | PASS |
| canonical identity vs MPI4 | PASS | PASS | reference | PASS |
| all 80 modal keys aligned | PASS | PASS | reference | PASS |
| zero swap | PASS | PASS | PASS | PASS |
| process-tree memory `<=10.30 GiB` | PASS | PASS | PASS | FAIL |

因此推荐：

1. 当前模型在 `<=10.30 GiB` 约束下优先 MPI4；如果更看重最低总内存，选择 MPI1，
   如果希望在内存和时间之间进一步折中，选择 MPI2。
2. 不应通过单纯提高 MPI 数来追求总内存下降；MPI8 只适用于允许约 12.6 GiB
   process-tree 峰值且优先速度的场景。
3. 下一项最有针对性的内存研究是 MPI1 的 exact factor-class reuse，而不是继续扫描
   更多 MPI 数。它属于后续优化，本报告没有修改代码或运行新的 PDE。
4. 本结果只资格化当前 13.5 nm p6/h10 离散模型，不外推为 0.7 nm scalability 或
   production qualification。

## 验证与证据状态

本报告使用既有四组 full-solve raw artifacts，未重新运行 PDE。发布前执行了：

- 重新读取并校验四组 watchdog/run/core audit；
- MPI1/2/8 对 MPI4 的 active/full-FE canonical manifest comparison；
- 80 个 modal order 的 key-set 与 power/amplitude 差异重算；
- compact JSON parse、Markdown link/static consistency 和 `git diff --check`。

大型 mesh、field、canonical shards、timeline 和 raw logs 继续留在 ignored
`benchmarks/artifacts/task037/`，只提交 hash-bound compact record 与本报告。
