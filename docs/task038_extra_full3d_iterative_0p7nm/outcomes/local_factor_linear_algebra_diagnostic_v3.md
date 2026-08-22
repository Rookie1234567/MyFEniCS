# V5 LA0/LA1：v3 formal Path T 诊断

## 结论

“局部因子”是把一个局部矩阵拆成下三角矩阵 `L`，这样可以先解 `L y=b`，再解
`L^H x=y`。本次 LA0/LA1 只诊断 N2 首个失败类的线性代数路径，不代表完整 N2
setup 或生产求解器已经通过。

v3 在同一次 formal attempt 中成功捕获并重现了首个已知失败类。独立 checker
确认 S0 与旧 N2 v1 residual 完全一致，S1 专用下/上三角解通过 `1e-11`，因此
决策为 `Path T`。这只是 LA1 numerical candidate；production
`_PackedCholesky.solve` 当时尚未修改。

## Formal facts

| 项目 | 实际值 |
|---|---|
| source SHA | `6b8f6cc7cf39aec0a6138b7e24329da3f6a69392` |
| case / attempt | p6/h10 MPI1 / 唯一一次 |
| marker | `preflight → mesh_space_mpc → subdomain_inventory → local_factor_build → linear_algebra_diagnostic → failure` |
| marker span | `159.357953491 s` |
| watchdog elapsed / samples | `160.51165314597893 s` / `160` |
| captured class digest | `0c6b9830423f8baf83b6714ac178c724b63af1359d01b3ca5badd1d40c070a67` |
| rows / slot / representative rank | `882` / `1` / `0` |
| representative | tag `1`；widths `8.25, 8.333333333333332, 10.0`；free-row descriptor SHA `dc472b4bc91616cb54740593e8df75feb966197d16f7593e0542db1baa5db5c5` |
| frozen RHS | `arange(n)+(0.125+0.25j)` |
| Gate | `relative residual <= 1e-11` |
| LA0 reproduction | PASS；S0 frozen-v1 agreement `0` |
| LA1 decision | `Path T / PATH_T_DEDICATED_TRIANGULAR_PASS` |

## S0–S3 independent measurements

| path | relative residual | normalized backward error | repeat |
|---|---:|---:|---|
| S0 packed + generic solve | `1.0426245523812324e-11` | `9.01854818500637e-19` | exact |
| S1 dedicated triangular solve | `9.316208748538303e-12` | `8.058382790658791e-19` | exact |
| S2 direct diagnostic solve | `2.544882468429781e-11` | `2.2012856990841358e-18` | exact |
| S3 S1 + exactly one refinement | `6.672944399115928e-12` | `5.771998219478778e-19` | exact |

其它独立指标：Hermitian defect `9.757433025229162e-17`；factorization residual
`8.158904706122267e-16`；`lambda_min=0.00045043462322559666`；
`lambda_max=25934.54102501312`；`kappa2=57576704.11589122`。packed roundtrip
exact、relative `0`，重建 hash 相同；S0–S3 repeat 均 exact、relative `0`。
所有 S0–S3 pairwise solution differences 均记录在 compact，最大值为
`1.135334055192972e-12`。

## 资源与边界

process-tree peak 为 `1,487,138,816 B`，watchdog process-tree swap gate 通过，
`already_exited`、no orphan、无 SIGKILL，worker diagnostic rc=0。这个峰值覆盖的是
LA0/LA1 诊断阶段，不是完整 N2 setup retained 资格；没有 post-setup sample，也没有
252 patch inventory、regional/top、Z/AZ/E 或 N2 resource qualification。

## 证据索引

| artifact | bytes | SHA-256 |
|---|---:|---|
| tracked v3 checker compact `outcomes/records/n2_local_factor_la_v3.json` | 3,679 | `ff6b1ba2c158dc9c9a105390dfb033a3a185e3d258e501a66affad88293e9698` |
| ignored worker record | 15,104 | `87b79b3ab5c582205d3e9117e50905ed941f824260fcdfa01452cd967d7d0168` |
| ignored watchdog raw | 225,874 | `d24a7533c97bf7db26e78f70f7dc2301015b630246d1e2d3c7933e5807e220ae` |
| ignored watchdog compact | 2,460 | `61589fa5075750bfb3736f64512a7553448d3652e19f1de2513fb7c080ac0f83` |
| ignored worker log | 1,833 | `33403e4227bbb9dac5be84cf74a116be13f2f3d78079ed7ce9715a860b267790` |
| ignored `failed_B.npy` | 12,446,912 | `ec6fa132758735531e272532529bc43a0ac6f1cbf8c1e3c3f3656f19383fcbcd` |
| ignored `failed_rhs.npy` | 14,240 | `da2a800306714ebe4218ae03fa09493d782a18351f5aa6c05eec7e15cb300983` |

raw root：
`benchmarks/artifacts/task038_extra_full3d_n2_la_v3/6b8f6cc/p6_h10_mpi1/`。

## 解释边界

旧 N2 v1 的 residual `1.0426245523812324e-11` 仍是历史 controlled negative；v3
证明了一个确定类的专用三角路径可以达到 Gate，但没有证明完整 class 集或 N2
setup 通过。随后 production repair 才被单独实现并绑定到新的 fresh N2 attempt。

## Selective merge 边界

| 项目 | 当前分类 |
|---|---|
| marker ownership/allowlist 修复 | 可独立审阅；不改变数值语义 |
| dedicated triangular repair | 虽有单-class formal Path T依据，但完整 N2 class set失败；不得合入 ordinary production default，仅保留为执行分支 research candidate，等待 review |
| 旧负证据 | `do-not-delete`；不因本次诊断或修复而重分类 |
