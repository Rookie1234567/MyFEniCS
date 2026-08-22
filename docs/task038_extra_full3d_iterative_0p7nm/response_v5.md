# Task038-extra Review V5 response

本文只记录 V5 授权的 LA0/LA1 唯一 formal attempt 及其启动层 hard stop。`action` 是一次矩阵自由算子作用；`factor solve` 是用局部三角因子解固定线性方程；`controlled stop` 是保留真实现场后按合同停止，不等于数值算法已经通过或永远不可行。

## 1. 身份、分支和 worktree

| 项目 | 值 |
|---|---|
| branch | `codex/20260820-task38-extra-full3d-iterative-0p7nm` |
| frozen master base | `438caf150439343ee7c4c58ad7e02a3da812a23c` |
| Review V5 start / reviewed HEAD | `5636cd49b2c385f320b87dc07e9c9eb935ac1e2d` |
| pre-V5 response_v4 parent | `8cb3cfd62586f4e050afe41932b54a823ee2f5d8` |
| formal source | `4b9ccbcc411ef529a5a1258cc11bddc691d11b95` |
| upstream at formal source | `5636cd49b2c385f320b87dc07e9c9eb935ac1e2d` |
| source commit relation | ahead/behind `1/0` |
| source commit worktree | clean |
| docs closure worktree | 3 个待审文件：compact、diagnostic 文档、response_v5；未提交 |
| ABI | qualified WSL/Linux，complex128/int32，MPI1，threads=1 |

本轮没有修改 master、没有新分支/worktree、没有 LA2/N2/N3/N4、没有 push。此前沙箱 MPI singleton 的 PMIx listener 失败后，qualified non-sandbox preflight 通过；这不是数值结果。

## 2. old N2 v1 negative 是否保持不变

保持不变，仍是 `CONTROLLED_NEGATIVE_LOCAL_FACTOR_SOLVE_GATE`：source `907fe8fb204cffa34a921c6d0cab7ff4dd4831b8`，fixed RHS residual `1.0426245523812324e-11`，Gate `1.0e-11`。旧 compact 路径及 SHA 为：

`docs/task038_extra_full3d_iterative_0p7nm/outcomes/records/n2_local_spectral_setup_mpi1_v1.json`；SHA-256 `d02f416956a560c0837d067636d8f62d253c9d04da4e6bbe3b6194dd10098d40`。

本次 LA0 启动停止没有覆盖或重分类旧 negative。

## 3. failed class digest、rows、matrix/RHS hashes

本次 worker 在 preflight 前退出，没有 class extraction，因此 failed exact-class digest、representative identity、rows、matrix SHA-256 和 RHS SHA-256 全部为 `not_run`。不能用旧 N2 的类身份填充本次证据。

## 4. Hermitian defect、lambda、condition

`Hermitian defect`、`lambda_min`、`lambda_max`、`kappa2` 均为 `not_run`。没有加载或提交失败 class 的 dense B。

## 5. factorization residual

为 `not_run`。本次没有执行 Cholesky、packed roundtrip 或 `L L^H` 对照。

## 6. S0/S1/S2/S3 residual 和 backward error

四条路径的 residual、normalized backward error、pairwise solution differences 和 repeat 均为 `not_run`。因此没有任何 LA1 数值指标可用于判断专用三角解、直接解或 refinement。

## 7. 最终 Path

`Path = not_determined`。不是 T、R、P、C、A 或 close；决策树没有看到可计算的 class。

## 8. production solve 是否修改

没有修改 production `_PackedCholesky.solve`、B0、patch、overlap、mode、coarse 或物理 action。LA0/LA1 代码只提供一次性诊断捕获和独立计算入口；启动停止发生在这些路径实际调用前。

## 9. 原 `1e-11` Gate

完全未变。LA0/LA1 仍绑定 `<= 1.0e-11`；本次没有任何“接近通过”的数值结果，也没有放宽或添加 class-specific exception。

## 10. diagnostic resource 和 lifecycle

watchdog 在 startup 阶段取得 3 个有效 sample，process-tree memory authority peak 为 `14,446,592 B`，process-tree swap 为 `0 B`，sampled elapsed 约 `2.0098296020005364 s`。这个数值仅是 startup process-tree measured，不能称 LA0/LA1 resource pass。

实际生命周期是：watchdog startup → worker 命令进入 `_prepare_paths` → 因已存在 `raw/markers` 立即抛 `FileExistsError` → worker rc=1。worker 自行返回；watchdog 未发 SIGTERM/SIGKILL，随后 `already_exited`、process group exited、no orphan；compact `natural_exit=false`。

## 11. N2 MPI1 inventory、factor/mode/coarse、Z/AZ/E、资源

没有运行到 N2 worker preflight 或 mesh。因此 252 patch/cell inventory、exact classes、factor bytes、mode shards、regional Z16、top Z32、AZ32、E32、zero identity apply、post-setup retained sample 和完整 setup resource 全部 `not_run`。这次不是完整 setup negative，也不能用 N0 derived budget代替实测。

## 12. MPI2 identity 和 factor ownership

MPI2 未运行。cross-MPI identity、canonical setup packet、class-owner identity、factor ownership 和 MPI2 resource 均 `not_run`。

## 13. N3 五类 source、coarse-only/full PC rho 和资源

N3 未运行。physical RHS、gradient、curl、checkerboard/high-frequency、R3 long-tail 五类 source 的 coarse-only/full PC rho、repeat、closure 和资源均 `not_run`。

## 14. N4 20/100/150/200 true residual 和资源

N4 未运行。20、100、150、200 及 final true residual、contraction、KSP/PDE、资源均 `not_run`。

## 15. 证据分类

| 分类 | 本轮内容 |
|---|---|
| measured | startup process-tree peak `14,446,592 B`、swap `0 B`、3 samples、worker/checker/watchdog rc |
| exact | source SHA、一次尝试约束、启动异常、raw/compact/check/log bytes 与 SHA |
| derived | 没有用 derived 数值替代 LA1 measured Gate |
| budget | watchdog warning `1,800,000,000 B`、hard `2,000,000,000 B`；本次均未达到 |
| failed | worker 启动路径失败；independent checker 对缺失成功字段 fail-closed |
| controlled_negative | 旧 N2 v1 的 local factor solve Gate negative，保持不变 |
| controlled_stop | 本次 `CONTROLLED_STOP_LA0_RUNNER_LIFECYCLE_PATH_ALREADY_EXISTS` |
| not_run | LA0 class extraction、LA1 S0–S3/Path、N2 setup/MPI2、N3、N4、T6 和后续 PDE |

## 16. T6-F、official physics、T7–T9 和 0.7 nm

T6-F、official physics、T7–T9 和 full 0.7 nm PDE 均未运行，也未获得授权。没有 R/T/A、true residual、物理性能或完整 workflow 内存结论。

## 17. selective merge 建议

| 依赖组 | 建议 |
|---|---|
| production numerical/core | 本轮无新增 production numerical claim；`_PackedCholesky.solve` 保持不变 |
| reusable runner/watchdog | LA0 runner 与现有 watchdog 的本次启动现场不具备资格化 formal 结果 |
| checker/benchmark | LA0/LA1 runner、checker、diagnostic hook 和 focused tests 标为 research-only / not-qualified；不得提升为 ordinary default |
| compact evidence/docs | 保留本 compact、V5 response 和启动 raw hash，作为 controlled-stop evidence |
| research-only | LA0/LA1 归因代码可供后续 review 审查，但不能据本次结果进入 N2 |
| do-not-merge | old N2 negative、Candidate C/T4 已关闭路径和任何未资格化后续 coarse/PDE 结论均不改写、不提升 |

## 18. tracked compact 和 ignored raw hash 索引

| artifact | bytes | SHA-256 |
|---|---:|---|
| tracked compact `outcomes/records/n2_local_factor_la_v1.json` | 7,220 | `e0d161d2827b2bed390fe4ab6ef7238891606edc094adb0513a3e0ba4c10a739` |
| ignored worker backfill record | 1,788 | `dfcbfb751c2bbee41f56a2668944e19dd374275f0482280de8eaec3b26aff77b` |
| ignored watchdog raw | 5,113 | `858eab4a3a13218991c9a2c605d3f0bf6298af4962750d4cc45424e912e0e482` |
| ignored watchdog compact | 1,821 | `69de7ed21736ad18488dd998f5bc11d9e9e1695efcc01bd2215a7b3073b38238` |
| ignored independent checker output | 1,121 | `33bfc1b5cb0f9e21073ea30110cdfdaf40625f8ca565f6134efc5b769e3099bd` |
| ignored worker log | 1,553 | `865b1319133ddba30baf7e89b93afe17e87245b10f21294db38648aafc795c2d` |

Raw root：

`benchmarks/artifacts/task038_extra_full3d_n2_la_v1/4b9ccbc/p6_h10_mpi1/`

本 response 的 docs closure 尚未提交，不能在本文中自引用未来 commit。当前实现测试边界为本地 `test290 + test291 = 27 passed`、compileall pass、AST duplicate-key pass、`git diff --check` pass；没有重跑数值/PDE/full pytest。

## 用户补充授权 continuation / final current status

以下是 V5 审阅后用户明确授权的 marker 修复、LA0/LA1 v3 诊断、Path T production
修复和 fresh N2 MPI1 attempt。本节由最终 docs closure commit 携带；final docs SHA
无法自引用，见交付报告。本文追加，不改写前文旧 negative 或启动停止结论。

| # | Review V5 项目 | 当前事实与边界 |
|---:|---|---|
| 1 | identity / commits / upstream | frozen master base `438caf150439343ee7c4c58ad7e02a3da812a23c`；Review V5 start `5636cd49b2c385f320b87dc07e9c9eb935ac1e2d`；用户补充授权前 latest HEAD `9b7e0b4d6190957e2d40ca9650e0151383cbe1b9`；formal production source `b20de4960db4210f510195cff6136c72cd990b3f`；pre-doc-closure upstream/ahead `6ce8a2c567b5fb2e138219306f06e5001704af26 / 3/0`；final docs commit/upstream/ahead 见交付报告。 |
| 2 | old negatives | old N2 v1 `n2_local_spectral_setup_mpi1_v1.json` SHA `d02f416956a560c0837d067636d8f62d253c9d04da4e6bbe3b6194dd10098d40`；第一次 LA0 v1 compact SHA `e0d161d2827b2bed390fe4ab6ef7238891606edc094adb0513a3e0ba4c10a739`；v2 marker compact SHA `9610f69826092a31a69d6c3a7cbcb8cefd69ada0954c767b11953abafed47d44`。均保持不变。 |
| 3 | v3 failed class | v3 digest `0c6b9830423f8baf83b6714ac178c724b63af1359d01b3ca5badd1d40c070a67`，rows `882`，matrix file SHA `ec6fa132758735531e272532529bc43a0ac6f1cbf8c1e3c3f3656f19383fcbcd`，RHS file SHA `da2a800306714ebe4218ae03fa09493d782a18351f5aa6c05eec7e15cb300983`。 |
| 4 | v3 linear algebra | Hermitian defect `9.757433025229162e-17`；lambda min/max `0.00045043462322559666 / 25934.54102501312`；kappa2 `57576704.11589122`；factorization residual `8.158904706122267e-16`。 |
| 5 | v3 S0–S3 | residual `1.0426245523812324e-11 / 9.316208748538303e-12 / 2.544882468429781e-11 / 6.672944399115928e-12`；backward error `9.01854818500637e-19 / 8.058382790658791e-19 / 2.2012856990841358e-18 / 5.771998219478778e-19`；repeat 四条 exact；S3 恰好一次 refinement。 |
| 6 | decision | v3 independent checker 为 `Path T / PATH_T_DEDICATED_TRIANGULAR_PASS`；这是诊断资格，不是 N2 setup PASS。 |
| 7 | marker repair | marker allowlist fix commit `6b8f6cc7cf39aec0a6138b7e24329da3f6a69392`；标准 N2 planned markers 未变，`linear_algebra_diagnostic` 只进入显式 diagnostic allowlist。 |
| 8 | production repair | dedicated `scipy.linalg.solve_triangular` 两次调用提交于 `b20de4960db4210f510195cff6136c72cd990b3f`；无 refinement、fallback、packing/B0/patch/mode/coarse 参数变化。 |
| 9 | numerical Gate | fixed RHS solve Gate 仍严格为 `<=1e-11`，没有放宽或 class-specific exception。 |
| 10 | v3 resource/lifecycle | v3 process-tree peak `1,487,138,816 B`，160 samples，约 `160.51165314597893 s`，process-tree swap=0，already_exited/no orphan/no SIGKILL；没有 post-setup sample，不能称完整 N2 resource pass。 |
| 11 | fresh N2 MPI1 | source `b20de...`；marker `preflight → mesh_space_mpc → JIT → subdomain_inventory → local_factor_build → failure`；residual `1.1089747142000698e-11 > 1e-11`；worker/watchdog/checker rc `1/1/1`；process-tree peak `1,504,804,864 B`，swap=0，no orphan。 |
| 12 | fresh N2 identity boundary | 本次 standard N2 worker 未记录 failed class digest/representative identity/rows；不得用 v3 digest冒充。它是完整 class registration 的未具名 class，residual 与 v3 值不同，精确 identity unavailable。 |
| 13 | fresh N2 completeness | failure before complete inventory/post-retained/modes/regional/top/Z/AZ/E/identity；这些均 `not_run_by_numerical_gate`，失败点前 peak 不构成 complete setup memory qualification。 |
| 14 | later lanes | MPI2、N3、N4、T6-F/EH/RTA、official physics、T7–T9、full 0.7 nm 全部 `not_run_by_gate`；没有 contraction 或 PDE 结果。 |
| 15 | measured / derived / failed / not_run | measured：marker、rc、watchdog peak/swap/termination 和 v3/v2 raw facts；derived：仅 LA1 array-byte账本；failed：fresh N2 fixed-RHS Gate；not_run：完整 N2、MPI2 及后续 physics。资源只称失败点前 peak，不称 PASS。 |
| 16 | evidence paths | v3 root `benchmarks/artifacts/task038_extra_full3d_n2_la_v3/6b8f6cc/p6_h10_mpi1/`；fresh N2 v2 root `benchmarks/artifacts/task038_extra_full3d_n2_formal_v2/b20de49/p6_h10_mpi1/`；tracked outputs 分别为 `records/n2_local_factor_la_v3.json` 与 `records/n2_local_spectral_setup_mpi1_v2.json`。两套 raw/watchdog/log 均 ignored。 |
| 17 | evidence hashes | v3 worker `15,104 B / 87b79b3ab5c582205d3e9117e50905ed941f824260fcdfa01452cd967d7d0168`；raw `225,874 B / d24a7533c97bf7db26e78f70f7dc2301015b630246d1e2d3c7933e5807e220ae`；compact `2,460 B / 61589fa5075750bfb3736f64512a7553448d3652e19f1de2513fb7c080ac0f83`；log `1,833 B / 33403e4227bbb9dac5be84cf74a116be13f2f3d78079ed7ce9715a860b267790`。fresh N2 worker `6,617 B / fa24d8dd1462ee3823fff9f49144bd32fb9172d7cf09720efe7d26da19942d3c`；raw `40,310 B / 7bb37b3765201fb01e6477f36d4adca6a604c09f987a8c53e95a73dde4c0ba5e`；compact `2,353 B / d6283c7c68529dc2e928ad2a371de0e55e83bc541b363448de4622ee0a3c1215`；log `2,532 B / 8b0511e4cd7a8714d2908ec41a80efc9101d43ab3a76f3a5f3ca31e3c3211ee3`；tracked checker `3,521 B / d88330f2c9b038946c8f0b15e22b5850e6812c868366fa50f04e1e9b3962f763`。 |
| 18 | selective merge / final boundary | marker ownership/allowlist 修复可独立审阅；dedicated triangular repair虽有单-class formal Path T依据，但完整 N2 class set失败，当前不得合入 ordinary production default，只保留执行分支 research candidate，等待 review。LA0/LA1 diagnostic evidence 保持 research-only；旧负证据 `do-not-delete`。未授权 production coarse、MPI2、N3/N4 或 official physics。无 CI 声明。 |

当前结论：`N2_MPI1_CONTROLLED_NEGATIVE_LOCAL_FACTOR_SOLVE_GATE`。三角求解修复解决了
v3 已诊断 class，但完整 class 集仍未通过固定 RHS Gate；因此不能进入 coarse、contraction
或 PDE。最终 docs commit SHA 不能由本文自引用，待后续交付报告给出。
