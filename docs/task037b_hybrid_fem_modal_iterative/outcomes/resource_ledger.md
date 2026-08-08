# Task037b H1 resource ledger

## 口径

本次峰值是 H1 whole-job 在 mode classification 阶段的同步过程树峰值，不是成功 Hybrid 求解的内存需求预测。watchdog authority 使用同时存活 MPI worker 的 RSS 总和；PSS、USS 和 swap 单独记录，不能互相替代。

| 指标 | 实测值 |
|---|---:|
| wall time | 约 49.54 s |
| process-tree / worker RSS peak | 2647.4375 MiB |
| authority peak | 2.58538818359375 GiB |
| worker PSS peak | 1761.02734375 MiB |
| worker USS peak | 1637.375 MiB |
| process-tree swap peak | 0 |
| worker smaps swap | 0 |
| warning threshold | 12 GiB，未触发 |
| termination threshold | 16 GiB，未触发 |
| timeout | 1800 s，未触发 |
| memory authority gate | pass |

## 阶段

| 阶段 | progress elapsed |
|---|---:|
| cross_section_eigen_assembly | 0.00018878397531807423 s |
| cross_section_eigen_solve | 2.219110075966455 s |
| mode_classification | 12.238622940029018 s |
| timeline 最后可读样本 | 49.54167506797239 s |

进程在 mode classification 失败后由 MPI 正常收口；没有残留 worker，没有受控内存终止，也没有 swap 压力。

raw JSON 字段名虽含 max_*_mb，但这些数值由 bytes/1024^2 换算，本文统一显示为 MiB；authority 峰值保持 GiB。

## 证据

| 文件 | SHA256 |
|---|---|
| ../../../benchmarks/artifacts/task037b/h1_direct_authority_3f72ef3_mpi8.json | 2e03dd105665de6a7ad9d796de7dad7117cf803483d0ad4de8da6dd2480b246b |
| ../../../benchmarks/artifacts/task037b/h1_direct_authority_3f72ef3_mpi8/worker_stdout.txt | eb03b75b5fba69bcf8e0304903d95b98286ac2756916749180cde99d851fe28e |
| ../../../benchmarks/artifacts/task037b/h1_direct_authority_3f72ef3_mpi8/memory_timeline.csv | 79ed75dfd7b57fbbc20f9ff0e73749fbfa52ce1d694c2760d6ddf82239418259 |
| ../../../benchmarks/artifacts/task037b/h1_direct_authority_3f72ef3_mpi8/memory_stages.jsonl | 4e35d04896a04d1640438afa0b8241af0a765a3c093b238b464ad7a1dae4193e |

## Post-fix successful solve（2990f357）

首次 classification 失败的 `2.58538818359375 GiB` authority 峰值保留为历史证据；它不是成功 Hybrid solve 的峰值。post-fix formal 在同一冻结 H1 物理条件下完成有效求解，以下为 process-tree/worker simultaneous authority 与原始 timing 字段。

| 指标 | post-fix 实测值 |
|---|---:|
| process-tree RSS peak | 7934.6484375 MiB |
| worker RSS peak | 7926.7109375 MiB |
| worker PSS peak | 6186.951171875 MiB |
| worker USS peak | 5912.7421875 MiB |
| process-tree / worker swap | 0 / 0 |
| worker timing total | 314.0315530579537 s |
| timeline 最后可读 elapsed | 316.6363581159385 s |
| bottom/top streaming recovery | 4.041541184997186 / 3.7041287679458037 s |
| sequential recovery sum | 7.74566995294299 s |

### Post-fix 阶段耗时

| 阶段 | seconds |
|---|---:|
| cross_section_and_qep_assembly | 3.0135245269630104 |
| positive_and_negative_biorthogonal_bases | 52.7131977280369 |
| two_local_fem_dtn_systems | 167.3979164250195 |
| internal_modal_coupling | 47.298344147973694 |
| primary_system_build | 1.4724921690067276 |
| monolithic_assembly | 1.4724921690067276 |
| rta_evaluation | 0.02579140500165522 |
| physical_field_reconstruction | 22.055879381950945 |
| total | 314.0315530579537 |

### Post-fix stage process-tree RSS peaks

| 阶段 | MiB |
|---|---:|
| process_start | 1623.324 |
| cross eigen assembly | 1806.195 |
| cross eigen solve | 2510.660 |
| mode classification | 2605.527 |
| local FEM | 5195.578 |
| interface | 5848.668 |
| augmented factor | 7585.594 |
| official RTA | 7585.598 |
| middle | 7812.992 |
| full3d oracle | 7589.258 |
| record/release | 7934.648 |

post-fix summary 与 solver record 仍为 Git ignored artifact；tracked docs 只保存 hash-bound 引用：summary `e22aa1edfeab331d5a8be13ca085e029d5446a4fdf300a5787a00688ef700db2`，solver `290fc25c119bbf641b8f0277ed5f9a101bc11a4df898c9133509f53c56dd4a1c`，timeline `26aee5647d93d4d5e9657b6a00f63fed98ffb83347506fb7bc8ed82bbbbbb9a6`，stages `a30d7cd52385f5940ac23b90297e85bb7f23dab64e6964f640c3aed3e096dab5`。

## H3 exact block-LDU oracle（e187275）

| 指标 | 实测值 |
|---|---:|
| total wall | `507.2017102949321 s` |
| authority peak | `9.585384368896484 GiB` |
| swap | `0` |
| outer / reason | `1 / 2 (CONVERGED_RTOL)` |
| true global/bottom/top/modal residual | `2.892237294698294e-12 / 3.610918199454199e-12 / 2.0470485206121342e-12 / 9.879221339086588e-13` |
| direct solution/modal relative error | `5.108471533338298e-13 / 6.960336394200873e-13` |
| factors | before `2`，after `0`，released |

H3 offline 12+12 已通过；H3 direct factors 是 oracle 生命周期的一部分，不是最终低内存候选的峰值声明。

## H4 exact Sₘ 与 bounded G-only diagnostic（98046b7）

| 指标 | 实测值 |
|---|---:|
| total wall | `540.3976704040542 s` |
| authority peak | `9.802722930908203 GiB`，stage=`record_and_release` |
| warning / termination | `12 / 16 GiB`，均未触发 |
| swap | `0` |
| H4b factor setup / solve | `31.84789529000409 / 0.5016900589689612 s` |
| post-H3 direct comparison | `28.747818996896967 s` |
| recovery/RTA / RTA evaluation | `7.698509941925295 / 0.02652613096870482 s` |

H4 关键阶段 authority peak（MiB）如下；这是 whole-job allocator/process-tree 观测，必须与 factor lifecycle inventory 分开理解。

| 阶段 | MiB |
|---|---:|
| oracle_local_matrix_build | `4170.0546875` |
| h2b_action_assembly | `6077.83984375` |
| h3_local_factor_setup | `8740.9453125` |
| h4b_g_only_factor_setup | `9034.28125` |
| post_h3_direct_comparison | `9351.921875` |
| recovery_rta | `9684.859375` |
| record_and_release | `10037.98828125` |

H4a 与 H4b 两轮 factors 均 before=`2`、after=`0`，bottom/top released=`true`；H4b 的 G-only 差异是 bounded diagnostic，不是方法负结果。H4 不要求 12+12 comparator。

| H4 证据 | SHA256 |
|---|---|
| `benchmarks/artifacts/task037b/h4_modal_block_98046b7_mpi8.json` | `bce01b0c24ffb8e09ba158b8784353ed6073648ea3c8d1dc57bd03c33b6c0b40` |
| `benchmarks/artifacts/task037b/h4_modal_block_98046b7_mpi8/solver_record.json` | `9a6737d21c93d39310c70020785d0a4231f1d83296b858fa38c2a4bacf3d169f` |
| `benchmarks/artifacts/task037b/h4_modal_block_98046b7_mpi8/memory_stages.jsonl` | `bb27debecbb0ac23c5d15c4c4fe3727b50574252449422243c8643b8cb6bf033` |
| `benchmarks/artifacts/task037b/h4_modal_block_98046b7_mpi8/worker_stdout.txt` | `f13de07c6ccdf73d023606e5f7c8cc19b9926b647440f273b31b947a2690ef61` |

## H5 frozen local inverse formal（216437c）

H5a 是 direct local reference，H5b 是最终双侧同时驻留的 candidate stage。两种峰值不能混称；H5b 数值 Gate 失败，因此较低的 candidate 峰值不是资格化结果。

| 阶段 | worker-rank RSS sum (MiB) | worker-rank PSS sum (MiB) | worker-rank USS sum (MiB) | process-tree RSS (MiB) |
|---|---:|---:|---:|---:|
| action/coupling | 6064.90625 | 4960.2822265625 | 4777.046875 | 6079.53125 |
| H5a direct reference | 7705.8203125 | 6586.92578125 | 6401.30078125 | 7720.4453125 |
| H5b candidate | 6910.75390625 | 5788.64453125 | 5602.4375 | 6925.37890625 |
| post-direct heap trim | not_observed | not_observed | not_observed | not_observed |

| 总时长 | swap | warning / termination | formal return | 分类 |
|---:|---:|---|---:|---|
| `795.0781892240047 s` | `0` | `false / false` | `2` | `LOCAL_INVERSE_FAMILY_NEGATIVE` |

H5a direct 与 H5b candidate 的内存下降是实测阶段差异。H5b process-tree RSS=`6925.37890625 MiB`（约 `6.763 GiB`），高于 H9 后续定义的 eventual `MPI8 resource-positive <=6.0 GiB` 参考线；但 H5b 数值 Gate 未通过且 H9 未运行，不给出正式 resource qualification，也不能把 candidate 内存下降包装成 qualified solution。H5 official R/T/A、field 和 12+12 没有运行。

| H5 evidence | SHA256 |
|---|---|
| `../../../benchmarks/artifacts/task037b/h5_local_inverse_216437c_mpi8/memory_sampler_summary.json` | `feb689c5faff607555f7ae894a7836020771145b30800d48eed4a595a3f8edb4` |
| `../../../benchmarks/artifacts/task037b/h5_local_inverse_216437c_mpi8/solver_record.json` | `887be236f9edc0f3140e0124b82895f14761d22260d79477f8d7c0f00ee90d92` |
| `../../../benchmarks/artifacts/task037b/h5_local_inverse_216437c_mpi8/memory_stages.jsonl` | `a27af6f56fb1028ec0174d1fd08c632279fc4af9258e06918d1166c1021aaabc` |
| `../../../benchmarks/artifacts/task037b/h5_local_inverse_216437c_mpi8/memory_timeline.csv` | `8b060e61c04419abc19d4bee08bbafa572b9ca7ed484978e7d540eaf339e2f2f` |
| `../../../benchmarks/artifacts/task037b/h5_local_inverse_216437c_mpi8/worker_stdout.txt` | `dcab0800a76be977f57d18b3b1fccdcb940b14a76cb4582e71f850b62d5c2178` |

## V1 R1–R5 resource closeout

R1–R5 均为独立 formal MPI8 watchdog 运行；这里的 process-tree 峰值与 worker-rank RSS
分开列出。R5 的 7.0 GiB 是本轮 standalone process-tree review threshold，不是 H9
或 production resource qualification。

| 阶段 | source | worker RSS peak (MiB) | process-tree peak (MiB) | authority peak (GiB) | swap | numeric |
|---|---|---:|---:|---:|---:|---|
| R1 | e2e5767 | 5763.66796875 | 5778.29296875 | 5.628582000732422 | 0 | pass |
| R2 | a9ee706 | 7139.3828125 | 7154.078125 | 6.972053527832031 | 0 | negative |
| R3 | 31d3084 | 7031.91015625 | 7046.53515625 | 6.867099761962891 | 0 | negative |
| R4 | 53faebb | 8006.87109375 | 8021.515625 | 7.819210052490234 | 0 | pass |
| R5 | 2a2ef3d | 6417.9296875 | 6432.54296875 | 6.267509460449219 | 0 | negative |

R5 process-tree peak 为 6432.54296875 MiB，即 6.281780242919922 GiB，低于 7.0 GiB
standalone threshold；swap=0、warning/termination=false、measurement_present=true。但
R5 数值 Gate 失败，所以 H6 不具资格，不能把这个资源结果包装成 production qualification，
也不能替代 H9 的后续资源目标。

### R5 factor、Woodbury 与阶段时间

| 项目 | bottom | top |
|---|---:|---:|
| source/factor NNZ | 6086016 / 6086016 | 6086016 / 6086016 |
| factor CSR payload estimate | 121754080 bytes | 121754080 bytes |
| W local bytes（各 rank） | 825600…944640 | 825600…944640 |
| W distributed sum / max | 5391360 / 944640 bytes | 5391360 / 944640 bytes |
| K replicated bytes per rank | 25600 | 25600 |
| LU replicated bytes per rank | 25760 | 25760 |
| factor before→after | 1→0 | 1→0 |

| R5 stage | seconds |
|---|---:|
| action/coupling build | 210.52379103191197 |
| bottom setup / solves / release | 8.554142217966728 / 215.98842261300888 / 0.000328178983181715 |
| top setup / solves / release | 8.374698366038501 / 238.89191701100208 / 0.00027341709937900305 |
| R5 qualification total | 472.072925756918 |
| watchdog total | 735.0470628660405 |

W 的 local bytes 是按 rank 的实际 owned storage；K/LU 是每 rank replicated storage。factor
NNZ 是 raw record 的 recorded count；payload 是明确公式的估算，不是实测分配量。
