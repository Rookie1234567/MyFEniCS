# Task37b：MPI1/2/4/8 冻结 candidate 数量对比

## 1. 范围与身份

本报告记录 V7 结项后用户明确授权的 **research-only MPI scaling diagnostic**。它把同一个 M10 Hybrid iterative candidate 在 MPI1、MPI2、MPI4、MPI8 上各运行一次；只改变 MPI 数，未改变离散、物理、求解器、预条件器或普通默认路径。MPI1/2/4 使用 scaling carrier `28cbead4ef90a7fbe17d93ed8c9061e09bc92e3d`，MPI8 保留 M10 的 source `b291f3dfdf5f0064ff243038f6809172f811d7aa`，因此不是同一 Git SHA 的四次重跑。

本 compact 记录是[四路证据索引](../../../benchmarks/cases/101_hybrid_iterative_block_solver/records/task037b_v6_mpi_scaling_1_2_4_8_v1.json)。历史 M1–M10 结项仍见[总结果](summary.md)、[资源账本](resource_ledger.md)、[测试摘要](test_summary.md)与[变更边界](changed_files.md)。`benchmarks/artifacts/` 下 raw 文件为 ignored evidence，正文使用代码路径和 compact SHA 索引，不把它们当作 tracked 文档链接。

冻结配置为 p6/h10、modal p6/h10、13.5 nm、S 偏振、10° 入射、上下接口 10/110 nm、M120/candidate240、每端 40 个 DtN mode、exact monolithic Hybrid operator、双侧 fixed whole-endcap ILU(0)+40-mode DtN Woodbury、right FGMRES restart 90、`max_it=1000`、`rtol=5e-9`、zero initial。四次均无 retry、warm start、continuation 或调参；warning/termination/wall 为 10/14 GiB/7200 s。

## 2. 在线数值与物理结果

`reported` 是 KSP reported residual；`global`、`bottom`、`top`、`modal` 是 postsolve explicit true residual。traction 是上下端精确 traction 相对误差。`reason=2` 是 raw solver 的正常收敛原因。raw online status 在四路均为 `task037b_v6_full_solve_awaiting_authority_payload`；这只表示当时尚未执行离线 authority 聚合，不是数值失败。随后唯一 aggregate checker 已完成 combined authority 裁决。

| MPI | iterations / reason | reported / global residual | bottom / top residual | modal residual | bottom / top exact traction |
|---:|---:|---:|---:|---:|---:|
| 1 | 794 / 2 | 3.3215100572982853e-9 / 3.321510667580213e-9 | 4.880734623133094e-9 / 2.392946477781962e-9 | 1.1434214268040558e-15 | 4.779869683523763e-9 / 2.392946477781962e-9 |
| 2 | 758 / 2 | 3.4870906448810887e-9 / 3.487090442354436e-9 | 4.901528219680154e-9 / 2.5699873423201828e-9 | 1.375232793635146e-15 | 4.8002335584542226e-9 / 2.5699873423201828e-9 |
| 4 | 760 / 2 | 3.427064378621666e-9 / 3.4270644353004737e-9 | 4.918228169219773e-9 / 2.4999887824951896e-9 | 1.2737653053297348e-15 | 4.8165883867526956e-9 / 2.4999887824951896e-9 |
| 8 | 792 / 2 | 3.578062165607276e-9 / 3.578062144715876e-9 | 4.921856578759462e-9 / 2.6635965562403923e-9 | 1.4561321294580367e-15 | 4.820141813913522e-9 / 2.6635965562403923e-9 |

| MPI | R | T | A | A_volume | R+T+A_volume | closure error |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 0.0007628815876484841 | 0.602701633835465 | 0.3965354845768865 | 0.39653548477543893 | 1.0000000001985525 | 1.9855250776856792e-10 |
| 2 | 0.0007628816646597273 | 0.6027016351705309 | 0.39653548316480935 | 0.3965354855990189 | 1.0000000024342095 | 2.4342095006346653e-9 |
| 4 | 0.0007628817040162669 | 0.6027016354081336 | 0.3965354828878501 | 0.39653548571506975 | 1.0000000028272196 | 2.8272195695677738e-9 |
| 8 | 0.0007628816277266691 | 0.6027016338728337 | 0.39653548449943965 | 0.39653548508184505 | 1.0000000005824054 | 5.82405457194568e-10 |

四路 residual、dual traction、recovery、own-physics、energy 与 online canonical/lifecycle gates 均通过。本轮 6 GiB 比较字段/研究 Gate 使用完整 process-tree RSS，不使用 worker RSS、PSS 或 USS 替代；这不是 production qualification。

## 3. 资源与耗时

| MPI | process-tree RSS peak MiB / GiB | peak stage（raw） | worker RSS sum at peak | worker PSS / USS at RSS peak | swap | total s |
|---:|---:|---|---:|---:|---:|---:|
| 1 | 1637.765625 / 1.5993804931640625 | `outer_iter_630` | 1623.25390625 | 1611.8427734375 / 1605.10546875 | 0 | 1035.158474470023 |
| 2 | 2423.6640625 / 2.3668594360351562 | `outer_iter_270` | 2409.20703125 | 2220.15234375 / 2048.51953125 | 0 | 687.5406564989826 |
| 4 | 3907.26953125 / 3.815692901611328 | `v6_pre_canonical_heap_cleanup_started` | 3892.65234375 | 3091.7041015625 / 2821.9765625 | 0 | 512.5570110660046 |
| 8 | 6018.57421875 / 5.877513885498047 | `v6_top_recovery_heap_cleanup_finished` | 6003.94140625 | 4369.6455078125 / 4102.09375 | 0 | 467.8611913640052 |

PSS/USS 是 timeline 同一 RSS 峰值采样的 worker-rank companion；全 timeline 最大值另为 MPI4 `3343.5205078125/3166.76171875` MiB、MPI8 `4668.7451171875/4487.77734375` MiB，其余两路与 RSS 峰值相同。四路 swap 均为 0。MPI8 的 stage 必须以 raw `memory.max_simultaneous_worker_rss_stage`/checker `metrics.peak_stage` 为准，即 `v6_top_recovery_heap_cleanup_finished`；不能沿用早期口头摘要的 pre-canonical 标签。

主要阶段耗时（秒，均为 measured）：

| MPI | basis | action coupling | setup | outer | v4_total |
|---:|---:|---:|---:|---:|---:|
| 1 | 116.30771053500939 | 591.3045624910155 | 46.97087202803232 | 224.64719663304277 | 1035.1559926810442 |
| 2 | 78.1022637259448 | 365.4417977859266 | 45.81929409899749 | 163.08849123097025 | 687.5377933069831 |
| 4 | 63.805899617029354 | 235.9006323630456 | 45.79946504498366 | 136.67621929000597 | 512.5539998679888 |
| 8 | 52.80422486108728 | 209.0848679660121 | 47.52676464605611 | 131.28534154291265 | 467.8580347279785 |

### 3.1 派生数量对比

以下是本机单次样本的 derived 量：内存分母为 MPI8 process-tree RSS peak，耗时分母为相应 total；不是误差条、稳定性统计或一般 MPI 模型。

| MPI | 相对 MPI8 峰值节省 | 相对 MPI8 耗时变化 | 相对 MPI1 speedup | parallel efficiency（相对 MPI1） |
|---:|---:|---:|---:|---:|
| 1 | 72.7881460712443% | +121.25333188079055% | 1.0x | 1.0 |
| 2 | 59.73026211175689% | +46.95398318773194% | 1.5055960177557222x | 0.7527980088778611 |
| 4 | 35.07981476613738% | +9.55322230760216% | 2.0195967514269753x | 0.5048991878567438 |
| 8 | 0% | 0% | 2.2125333188079055x | 0.2765666648509882 |

setup 约保持 46–47 秒；本次主要缩放差来自 basis、action coupling 和 outer。峰值 stage 随 MPI 变化，只用于生命周期解释，不把各 RSS 分量相加，也不由 stage 标签推断单一因果。

## 4. Cross-MPI 能量差与 authority checker

下面的能量差是 aggregate checker 明确给出的 MPI1/2/4 相对 MPI8 字段；它不是从订单数组自行重算的替代指标。

| MPI 对 MPI8 | abs(ΔR) | abs(ΔT) | abs(ΔA) | abs(ΔA_volume) |
|---:|---:|---:|---:|---:|
| 1 | 4.007818501985255e-11 | 3.7368663718950756e-11 | 7.744682672949921e-11 | 3.064061226965009e-10 |
| 2 | 3.693305817425996e-11 | 1.2976971719425023e-9 | 1.3346302951688926e-9 | 5.171738592935071e-10 |
| 4 | 7.628959779442529e-11 | 1.5352998872231183e-9 | 1.6115895284940507e-9 | 6.332246949014575e-10 |

订单层没有 checker 提供的 cross-MPI 逐通道差值，故不将下面的 significant error 误写成 MPI-vs-MPI8：

| MPI | order coverage | significant | below floor | Hybrid vs frozen Full3D max power relative | max amplitude relative |
|---:|---:|---:|---:|---:|---:|
| 1 | 80/80 | 12/12 | 68 | 1.002148932775072e-06 | 1.0207074844363997e-06 |
| 2 | 80/80 | 12/12 | 68 | 6.704952404640707e-07 | 4.1275026732858674e-07 |
| 4 | 80/80 | 12/12 | 68 | 3.84705410181447e-07 | 4.461584615891588e-07 |
| 8 | 80/80 | 12/12 | 68 | 6.693230816107301e-07 | 5.300716804376366e-07 |

四路 aggregate checker 的 `pass=true`、`failures=[]`、`evidence_integrity_pass=true`、`authority_bindings_pass=true`。每路 significant order 的 12/12 power 与 amplitude 通过；canonical 四角色 key coverage/relative-L2 通过；selected bottom/top/middle E/H coordinate alignment 与各字段通过；q、energy、12+12 通过。selected-field 最大 E/H relative L2 分别为 MPI1 `3.5069584392855125e-09/3.1398105831334865e-09`、MPI2 `3.567384961149536e-09/3.164839220190852e-09`、MPI4 `3.4747919737760407e-09/2.9657637063524264e-09`、MPI8 `3.6550910104971564e-09/3.0693657611802307e-09`，阈值 0.005。

modal raw coefficient 保持 `diagnostic_not_comparable_independent_qep_gauge`，不把逐项 raw mismatch 说成 pass；四路物理 magnitude relative L2 为 `8.365213349300108e-09`、`1.1602339847303398e-08`、`7.2122713293287614e-09`、`1.4759171008539638e-09`，qualification pass。pinned Full3D 没有 modal/canonical/selected E/H 数组，因此 `iterative_vs_full3d` 的这些维度是 `not_available`；direct-Hybrid vs Full3D 的 analytic identity、power、amplitude 均为 12/12，最大绝对误差为 `1.984856723424855e-12/2.0684155314519094e-12`。

checker 输出为 `benchmarks/artifacts/task037b/v6_mpi_scaling_1_2_4_8_checker_28cbead.json`，SHA256 `1574620bb548f67b3f9d5380f8ac20e56b8012c4cbe2c7d330883cf9575cc105`。checker 每 case wall 约 30 秒、RSS `123.58203125 MiB`；`online_rss_included=false`，不计入 MPI8 online authority。

## 5. 结论与边界

- 本次单样本中 MPI4 是时间/内存的平衡点：相对 MPI8 峰值少 35.07981476613738%，总耗时只增加 9.55322230760216%。MPI1 最省内存但约为 MPI8 的 2.2125 倍耗时；MPI2 介于两者之间。
- MPI1 是本机、本冻结 candidate、本次运行的最低实测峰值，不能宣称一般极限；没有误差条或稳定性统计。
- MPI8 process-tree peak `6018.57421875 MiB` 低于 6 GiB（6144 MiB），但这只是本冻结研究候选的资源观察，不把低 MPI 数结果提升为 production qualification。
- 结果不能外推到 0.7 nm、continuum convergence 或 mode-count convergence；Hybrid-P、低秩 direct 和本迭代候选仍不改变 ordinary defaults，也不授权 master/Task37c 合入。
- V7 的 selective-master/handoff 边界不因这次 post-V7 diagnostic 改写。四路 raw、唯一 aggregate checker 和本报告只构成可审计的数量对照。
