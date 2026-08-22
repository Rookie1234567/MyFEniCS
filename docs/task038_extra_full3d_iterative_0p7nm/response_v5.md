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
