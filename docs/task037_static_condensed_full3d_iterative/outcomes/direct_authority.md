# Task37 F0：当前源码 direct authority

## 当前源码 v2 authority

本节是当前 source `2631a4c47258c9def919530787e409774b8ce029` 的 Direct MPI8 v2 记录；旧的 F0 retry1 段落保留为历史证据，不被覆盖。compact record 为 [task37_direct_authority_v2.json](../../../benchmarks/cases/100_static_condensed_full3d_iterative/records/task37_direct_authority_v2.json)，raw artifact 为 `benchmarks/artifacts/task037/f0_direct_canonical_p6_h10_mpi8_2631a4c4`。

| Gate | 当前 v2 |
|---|---:|
| status / return / official | `full3d_reference_pass` / 0 / true |
| true residual | `1.17818264392128e-11` |
| R / T / A_balance | `0.000762881475132771` / `0.6027016339861171` / `0.3965354845387501` |
| A_volume / energy closure | `0.3965354845429724` / `4.222400207254395e-12` |
| whole wall / process-tree authority | `218.851869611 s` / `15.059223175048828 GiB` |
| full residual timing | `0.9020630560116842 s` |
| canonical manifests | active `e01458aa...`；full `095c19ee...`；8 shards each |

v2 来源信息将 watchdog 的真实 `worker_command` 与 `parent_launch_equivalent_argv` 分开保存；其中包含 `mpiexec -n 8`、绝对路径的 qualified `.venv` Python、`--worker` 以及 parent descriptor/SHA。

## 历史 F0 v1 快照（已由上节 v2 authority 取代）

F0 retry1 在当前 clean source `03f4fa02aece62bb2f193c01616177bffff0aa51` 上完成。
watchdog `status=full3d_reference_pass`，qualification 为 16/16，`failures=[]`，
`return_code=0`。本文件只记录 F0 closeout；没有开始 F1--F6。

### F0 Gate

| Gate | 结果 | 实测值/证据 |
|---|---|---|
| current direct source clean | PASS | branch `codex/20260803-task37-matrix-free-iterative-development`；SHA `03f4fa02aece62bb2f193c01616177bffff0aa51`；run 前后 clean |
| reported/full true residual | PASS | relative `2.809405792283611e-11`；reduced trace norm `3.6824889828937726e-10`；eliminated interior norm `4.3151175559767913e-11`，max `1.227441486594023e-12` |
| significant powers | PASS | Case096 frozen reference gate `12/12` |
| boundary complex amplitudes | PASS | 固定字段 `outgoing_amplitude_at_boundary`，Case096 frozen reference gate `12/12` |
| R/T/A and energy | PASS | `R=0.0007628814751145224`，`T=0.6027016339867304`，`A_volume=0.3965354845431466`；closure `4.991562718714704e-12` |
| row identity | PASS | full/storage FE `173802`；full trace `60402`；independent active trace `51192`；aux `80`；augmented `51272` |
| external memory readable | PASS | 1153 samples；1150 fully-readable MPI8 smaps samples |
| swap | PASS | process-tree/worker swap `0` |

### 冻结身份、矩阵与残差

| 项目 | 当前 F0 值 |
|---|---:|
| wavelength / incidence / phi | 13.5 nm / theta normal 80°（grazing 10°）/ 0° |
| polarization / element / MPI | S / p6 Nédélec / 8 |
| mesh | hexahedron；requested `5×3×14`，resolved `6×3×14`；252 cells |
| assembly backend | `assembly_time_static_condensed` |
| matrix NNZ used / allocated | `41,989,040` / `42,625,520` |
| MUMPS factor NNZ | `209,772,680` |
| factor source | PETSc factor matrix raw `matrix_nnz_used`；positive MUMPS INFOG(9)=`209,772,680`；`factor_nnz_corrected=null` |
| historical Case096 factor NNZ | `212,343,992`；当前低 `1.2109181784620493%`，不回写历史值 |
| KSP | reason `4` / `CONVERGED_ITS` |
| full residual method | reduced trace+DtN Mat action 与 matrix-free DOLFINx MPC UFL action 合并，并投影到所有 active eliminated cell-interior tests |

### Case096 对比

当前 R/T/A 与 Case096 `full_static` 的绝对差为：

| 量 | 当前值 | Case096 值 | absolute error |
|---|---:|---:|---:|
| R_total | 0.0007628814751145224 | 0.0007628814751258605 | `1.1338152638984411e-14` |
| T_total | 0.6027016339867304 | 0.6027016339855377 | `1.1927125953548057e-12` |
| A_volume | 0.3965354845431466 | 0.39653548454280696 | `3.396172232328354e-13` |

Case096 acceptance record：
`benchmarks/cases/096_hybrid_channel_memory_closure/records/p6_h10_mpi8_six_path_v1.json`，
SHA `7e7474fa5b67d65ae255c198982010acc5d6d4d5087f793eb7c2de76c5bbee0a`。

### 12 个冻结 significant channels

逐行使用 Case096 原有 `full_static` frozen gate；复振幅均为
`outgoing_amplitude_at_boundary`。`observed`、`error`、`tolerance` 和 `pass`
均保留在 compact record；下表给出同一组复核值。

| channel | power observed | power error / tol / pass | boundary amplitude observed `(re, im)` | amplitude error / tol / pass |
|---|---:|---|---|---|
| T(-7,0)_s | `2.362010447886885e-06` | `1.3531050635691173e-15 / 2.1586938039525714e-09 / true` | `(0.0009812210505609988, -8.723749948527052e-05)` | `2.967982533658631e-13 / 1.2165650664394503e-05 / true` |
| T(-5,0)_s | `2.1192082561846726e-07` | `1.0197752583305662e-16 / 3.891272584918786e-10 / true` | `(0.00013403269653884445, 0.00014700578428296102)` | `6.800764043181944e-14 / 1.28064572388584e-06 / true` |
| T(-4,0)_s | `4.372888972123728e-07` | `5.7497655250805975e-18 / 5.251002536670234e-10 / true` | `(-0.00026213220753842367, 8.743226902075484e-05)` | `1.8388586716527712e-14 / 2.541657906333072e-06 / true` |
| T(-2,0)_s | `2.9598413950955724e-06` | `3.3574691963265957e-17 / 4.651045293875445e-09 / true` | `(-0.0006970027805739936, 0.0002979420806725957)` | `5.064678060587999e-14 / 4.580806193893276e-06 / true` |
| T(-1,0)_s | `2.1781673986638547e-05` | `1.0917136606617556e-15 / 1.1144136652304436e-07 / true` | `(0.0020910133853935717, -0.0010233798627913193)` | `1.0463498548630346e-13 / 1.2728990676557803e-05 / true` |
| T(0,0)_s | `0.6026738723475807` | `6.140643549201741e-13 / 0.00021757657401122454 / true` | `(0.6313787033481696, 0.47302098103906065)` | `7.126088773958265e-13 / 0.006779628645197135 / true` |
| R(-7,0)_s | `6.263542421412359e-07` | `8.123744766350225e-17 / 1.2494442957486303e-09 / true` | `(-0.0005052091112072291, -2.6088861836139873e-05)` | `1.4119705443647793e-13 / 7.995038740979746e-07 / true` |
| R(-5,0)_s | `7.457300547003748e-08` | `1.0233232675883777e-16 / 1.1943015599631952e-09 / true` | `(-9.817807925786532e-05, -6.535503249665643e-05)` | `8.134631190347891e-14 / 1.113206415872461e-06 / true` |
| R(-4,0)_s | `2.675239611078742e-07` | `1.40553365014708e-16 / 1.086491588133722e-09 / true` | `(0.0002102233361642234, -4.9730436209712475e-05)` | `9.046882965072711e-14 / 1.8815249525164472e-06 / true` |
| R(-2,0)_s | `1.477690850543193e-06` | `7.597271437984315e-16 / 1.2422824425350593e-09 / true` | `(0.0004942316169335791, -0.00020551576971282503)` | `1.3761546299312216e-13 / 3.1864912826411788e-06 / true` |
| R(-1,0)_s | `6.669309653418762e-06` | `8.334363743849743e-16 / 5.111835340427464e-08 / true` | `(-0.001032707715847578, 0.0007678339217166858)` | `8.161444812663801e-14 / 7.413384075620187e-06 / true` |
| R(0,0)_s | `0.0007537612200510555` | `1.6448105898125842e-14 / 3.195286914614711e-05 / true` | `(-0.025252304353464303, 0.010774151701691648)` | `4.723989377447651e-13 / 0.0008330266538614554 / true` |

### 向量身份

| vector | source | shape | dtype | canonical SHA |
|---|---|---:|---|---|
| active trace | `linear_system.x` prefix；ownership-range ascending | `[51192]` | `<c16` | `a25524c6137d6c01a3add4264f68a9fe6b76a0998d6e827298af160496e88d98` |
| recovered full FE | `field.x.petsc_vec` owned entries；ownership-range ascending | `[173802]` | `<c16` | `1a304738066663221eefe8505ab991c4979959e98b9867e1096290b35d706cfc` |

raw `.npy` 只在 ignored run directory；compact JSON 只保留 canonical identity、来源和 raw file hash。

### Wall 与资源

| 项目 | 值 |
|---|---:|
| parent total wall | `370.18 s` |
| worker final wall | 约 `366.98 s` |
| solver-summary elapsed | `364.6542664730223 s`；与 parent/worker wall 不混用 |
| assembly build | `90.9635258979979 s` |
| factor setup | `140.38291110901628 s` |
| backsolve | `0.1941251559765078 s` |
| recovery | `0.12598704599076882 s` |
| full residual | `109.50969229999464 s` |
| RTA/postprocess | `8.616433746996336 s` |
| process-tree RSS authority | `15621.121 MiB = 15.255001068115234 GiB` |
| simultaneous worker RSS / PSS / USS | `15248.320 / 13254.321 / 13047.027 MiB` |
| swap | `0 MiB` |
| historical Case096 peak | `14.721755981445312 GiB`；当前高 `3.6221568088888425%` |

Direct watchdog 的 32 GiB warning、48 GiB termination、7200 s timeout、0.25 s
poll 和 TERM→5 s grace→KILL 未触发。Task37 iterative candidate 的 10/14 GiB
限制保持原值，不能因当前 direct baseline 较高而放宽。

### Provenance 与命令

本次为 qualified WSL native environment，没有 container image；因此记录
`execution_image.kind=qualified_wsl_environment`、`digest=null`、
`status=not_applicable_no_container_image`，没有伪造 digest。activation=1，
Python 为 `/home/Projects/MyFEniCS/.venv/bin/python`，PETSc scalar/int 为
complex128/int32，DOLFINx `0.10.0.post2`，Basix `0.10.0`，Open MPI `4.1.6`，
`OMP_NUM_THREADS=1`。

parent launch command 与 raw worker command 分开保存在
`records/task37_direct_authority_v1.json`；parent command 未使用 `--record`，
raw watchdog 输出全部留在 ignored run directory。

### 首次 pre-assembly 失败与修复边界

首次启动在 2.69 s、PDE assembly 前 fail-fast，唯一异常为：

`ValueError: variable-p live observer requires the exact-sequence assembly-time variable-p backend`

根因是 F0 callback 被错误传入既有 `variable_p_live_observer` 插槽，而不是
`solution_observer`。修复提交 `03f4fa02aece62bb2f193c01616177bffff0aa51` 只分离
两个 observer slot，并由 test217 forwarding regression 覆盖；没有修改 solver、
hash、Gate、阈值或普通默认。首次失败 raw 证据仍在：
`benchmarks/artifacts/cases/100_static_condensed_full3d_iterative/f0_direct_p6_h10_mpi8_14a84f87/failed_watchdog_record.json`。

### Raw evidence 索引

完整 watchdog/run summary、channel JSON、memory timeline、progress、stdout、
parent descriptor 和 `.npy` 路径及 SHA 均在 compact record 的 `raw_evidence`/
`vectors` 字段中；raw evidence 不进入 Git。F0 closeout 后停止，未生成
response_v0，未开始 F1。
