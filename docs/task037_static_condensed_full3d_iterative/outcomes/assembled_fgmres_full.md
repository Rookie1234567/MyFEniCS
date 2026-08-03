# F3 assembled FGMRES full run

## 结论

本次运行把 3D Maxwell 线性系统的内部单元未知量先消去，只在活动 trace 上做 assembled FGMRES；这样避免建立全局 direct factor，同时保留现有 auxiliary recovery、full-FE residual 和 DtN 后处理。它完成了数值 full solve，但资源门槛和 task.md 7.1 的 raw PETSc-index vector 对齐门槛没有同时通过。

| 分项 | 结论 | 证据 |
|---|---|---|
| watchdog/internal solver | pass | return 0；reason 2 `CONVERGED_RTOL`；337 iterations |
| solver residual | pass | reported/condensed/full-augmented/full-FE 均不超过 1e-6 |
| physical observables | pass | R/T/A、energy closure、12/12 powers、12/12 boundary amplitudes |
| raw vector indexwise | fail | active/recovered 相对 L2 分别 1.42103595584163、1.4121310623163326；限值 1e-5 |
| resource | negative | process-tree peak 13.652233123779297 GiB；positive 门槛 10.30 GiB |
| combined Task37 numerical status | not_pass | raw vector 与 resource 两项未通过 |

这不是 code 或 solver 修复结论。raw vector 的比较口径疑似受跨运行 mesh partition/DoF 全局编号影响；物理采样和通道 observables 一致只能作为 inference，不能替代 task.md 7.1 raw-vector Gate。

## 固定身份与源码

| 字段 | 值 |
|---|---|
| source SHA / clean | `00ae05df1553ff672b76ffa0199856747f39372c` / true |
| branch | `codex/20260803-task37-matrix-free-iterative-development` |
| model | 13.5 nm，10° grazing（theta normal 80°），phi 0°，S |
| mesh / FE | resolved cells `(6,3,14)`，p6 Nédélec，h=10 nm |
| MPI / backend | MPI8，`assembly_time_static_condensed` |
| candidate | right FGMRES，unpreconditioned，restart 90，rtol 1e-6，atol 0，max_it 3000 |
| slab candidate | 16 physical z slabs，overlap 0.25，shift 0.1，ILU(0) factor-only，2 pre + 2 post GMRES |
| coarse | 75D Floquet basis，rank 75 |
| run directory | `benchmarks/artifacts/cases/100_static_condensed_full3d_iterative/f3_full_assembled_p6_h10_mpi8_00ae05df` |

## Residual、solver 和结构

| 指标 | observed |
|---|---:|
| reported final relative residual | 9.816614438200463e-7 |
| condensed true residual | 9.816614437558954e-7 |
| full augmented true residual | 9.816614437558954e-7 |
| full-FE relative residual | 9.816614733438022e-7 |
| eliminated interior norm / max | 4.2995856395268345e-11 / 1.113653098277947e-12 |
| active / auxiliary / augmented rows | 51192 / 80 / 51272 |
| full FE DoFs | 173802 |
| matrix NNZ used / allocated | 41989040 / 42625520 |
| operator / coarse / smoother applies | 1093 / 337 / 2022 |

reported history 的关键点为 `0=1.0`、`20=0.034111294771686146`、`100=0.0006069564835830413`、`160=0.0001150269909285317`、`337=9.816614438200463e-7`。condensed true samples 为 `0=1.0`、`10=0.12124920528245725`、`20=0.03411129477168689`、`337=9.816614437558954e-7`。

partition coverage 为 true，union 覆盖 51192 active rows，auxiliary rows in subdomains 为 0，16 个 slab counts 为 `[8424,8424,8424,8424,8424,8424,8424,11988,11988,8424,8424,8424,8424,8424,8424,8424]`。smoother 的 16 个 local solver 全为 ILU；`factor_only_storage=true`，local KSP iterations 为 1，inner smoother 为 2-step GMRES。

no-global-factor inventory 为：`global_direct_factor_count=0`、`global_schur_matrix_materialized=false`，允许范围是 `SmallDenseInverse(H)`、dense coarse LU 和 `COMM_SELF factor_only ILU(0)`。smoother 中的 103336560 是各 local factors 的 aggregate stored nnz，不是 global direct factor；CSR payload 估算为 2067298912 bytes。

## R/T/A 与 energy

| 量 | F3 full | F0 direct | abs diff |
|---|---:|---:|---:|
| R_total | 0.0007628816328838084 | 0.0007628814751145224 | 1.5776928602526802e-10 |
| T_total | 0.6027016326287827 | 0.6027016339867304 | 1.35794764322128e-9 |
| A_balance | 0.3965354857383334 | 0.3965354845381551 | 1.2001782900838975e-9 |
| A_volume | 0.3965354851988998 | 0.3965354845431466 | 6.557532294948487e-10 |
| energy closure | -5.394336088926366e-10 | 4.991562718714704e-12 | 5.444251716113513e-10 |

## Significant channels

下表的 `P` 是 modal power ratio，`A_bnd` 是 outgoing complex amplitude at boundary；每项均比较当前 F3 observed 与 F0 direct observed，并沿用 F0 record tolerance。

| label | P F3 / F0 | abs/tol | A_bnd F3 / F0 | abs/tol | pass |
|---|---|---:|---|---:|---|
| T(-7,0)_s | 2.3611222036370458e-6 / 2.362010447886885e-6 | 8.88244e-10 / 2.15869e-9 | (9.810435e-4,-8.714220e-5) / (9.812211e-4,-8.723750e-5) | 2.01466e-7 / 1.21657e-5 | true |
| T(-5,0)_s | 2.1192689285356505e-7 / 2.1192082561846726e-7 | 6.06724e-12 / 3.89127e-10 | (1.340434e-4,1.469999e-4) / (1.340327e-4,1.470058e-4) | 1.22197e-8 / 1.28065e-6 | true |
| T(-4,0)_s | 4.3727641193711375e-7 / 4.372888972123728e-7 | 1.24853e-11 / 5.25100e-10 | (-2.621312e-4,8.742285e-5) / (-2.621322e-4,8.743227e-5) | 9.47263e-9 / 2.54166e-6 | true |
| T(-2,0)_s | 2.9598138603893445e-6 / 2.9598413950955724e-6 | 2.75347e-11 / 4.65105e-9 | (-6.969981e-4,2.979441e-4) / (-6.970028e-4,2.979421e-4) | 5.14124e-9 / 4.58081e-6 | true |
| T(-1,0)_s | 2.1782362008773167e-5 / 2.1781673986638547e-5 | 6.88022e-10 / 1.11441e-7 | (2.091017e-3,-1.023457e-3) / (2.091013e-3,-1.023380e-3) | 7.68132e-8 / 1.27290e-5 | true |
| T(0,0)_s | 0.6026738712269 / 0.6026738723475807 | 1.12068e-9 / 2.17577e-4 | (0.631379,0.473021) / (0.631379,0.473021) | 2.25348e-9 / 6.77963e-3 | true |
| R(-7,0)_s | 6.267330123103085e-7 / 6.263542421412359e-7 | 3.78770e-10 / 1.24944e-9 | (-5.053768e-4,-2.580464e-5) / (-5.052091e-4,-2.608886e-5) | 3.30027e-7 / 7.99504e-7 | true |
| R(-5,0)_s | 7.457695908592553e-8 / 7.457300547003748e-8 | 3.95362e-12 / 1.19430e-9 | (-9.817660e-5,-6.536289e-5) / (-9.817808e-5,-6.535503e-5) | 7.99505e-9 / 1.11321e-6 | true |
| R(-4,0)_s | 2.675294852492387e-7 / 2.675239611078742e-7 | 5.52414e-12 / 1.08649e-9 | (2.102254e-4,-4.973138e-5) / (2.102233e-4,-4.973044e-5) | 2.27365e-9 / 1.88152e-6 | true |
| R(-2,0)_s | 1.4777267961068516e-6 / 1.477690850543193e-6 | 3.59456e-11 / 1.24228e-9 | (4.942410e-4,-2.055103e-4) / (4.942316e-4,-2.055158e-4) | 1.08434e-8 / 3.18649e-6 | true |
| R(-1,0)_s | 6.66892044141774e-6 / 6.669309653418762e-6 | 3.89212e-10 / 5.11184e-8 | (-1.032717e-3,7.677580e-4) / (-1.032708e-3,7.678339e-4) | 7.64981e-8 / 7.41338e-6 | true |
| R(0,0)_s | 7.537613464884375e-4 / 7.537612200510555e-4 | 1.26437e-10 / 3.19529e-5 | (-2.525230e-2,1.077416e-2) / (-2.525230e-2,1.077415e-2) | 6.95649e-9 / 8.33027e-4 | true |

## Raw vector Gate 与 inference

| vector | shape/dtype | F3 observer-reported SHA | F0 observer-reported SHA | relative L2 | max abs | Gate |
|---|---|---|---|---:|---:|---|
| active trace | `[51192]` / `<c16` | `988c150ea378cdd41e9146b0aa2fa583352fb7b9f1b11727f06d79382932ec88` | `a25524c6137d6c01a3add4264f68a9fe6b76a0998d6e827298af160496e88d98` | 1.42103595584163 | 23.162753233324427 | fail |
| recovered full FE | `[173802]` / `<c16` | `c08b73b987075621a22adb4ff23178545141ef7bafa91f370fade85883d3af8d` | `1a304738066663221eefe8505ab991c4979959e98b9867e1096290b35d706cfc` | 1.4121310623163326 | 22.37051986256637 | fail |

这些 hash 仅对当前 PETSc ownership-order byte stream 可复现；跨独立 mesh partition 尚未证明其物理 canonical。当前与 F0 direct raw vector 的 norm ratio 为 active `0.9999999988716848`、recovered `0.999999998676122`；按 magnitude 排序后的相对 L2 为 active `1.2972699249328836e-6`、recovered `8.332516286068729e-7`。固定物理采样的 E/H/E_t/H_t 相对 L2 为 `4.731432398890806e-7`、`3.04315282290436e-7`、`5.227132151662181e-7`、`1.2371710700670504e-6`。这些是“比较口径疑似非canonical而物理解一致”的 inference，不替代 raw-vector Gate，也不把失败改写为 pass。

## 资源与耗时

| 项目 | observed |
|---|---:|
| process-tree peak RSS | 13.652233123779297 GiB |
| worker peak PSS / USS | 11980.911 / 11776.828 MiB |
| swap | 0 MiB |
| warning / termination / timeout | true / false / false |
| watchdog samples / poll | 1236 / 0.25 s |
| F0 direct peak RSS | 15.255001068 GiB |
| relative RSS reduction | 10.5065% |
| F0 direct wall / F3 full wall | 370.18 / 410.546 s |
| relative wall change | +10.9046% |

当前资源低于 14 GiB controlled-termination cap，但高于 10.30 GiB resource-positive 门槛，也没有达到相对 F0 至少 30% 的目标，因此标记为 `negative`，不称为 resource pass。

## Artifact 与后续边界

| artifact | SHA256 |
|---|---|
| watchdog_summary.json | `07ed6a8b4d7c3db8ca5e1b4a6c9e434760947cc391f5e924bee77d71e545f890` |
| run_summary.json | `c1631b077610e1d8a69aeabc0d53c187ff09265bf70ba82fa1363cc7d439dec1` |
| task037_f3_core_audit.json | `801bef986d92e85bf9bea90871b4e88970ba7905c18344b13e1c0d2b0b5a3cdd` |
| residual history | `3f5d56140723c281b78524519312dd538a3f667a578f292677a43e8e6cf05b4b` |
| active/recovered raw vectors | `576a2ed5cb867b5f2a2d192b3c755cef1f7e3ca44ef974935f08c28f381eee0b` / `b555184b0bad5fd69963c66fafbf0c5fa3b587c521f073436b084312a7036fa6` |
| dtn orders / power metrics / auxiliary amplitudes | `afddbb70b45fe5f704da90f944f2c27282448164cc4811fbc1421898841f996f` / `b173f36ad64ae32a707d22b1ff65e4826eb3b8301c2f7c682c5c37406a9a5e7d` / `7a303d9f7ab089f7d9b9e86436b07865eaf4bf2d0c146f27ef08092125f22a91` |
| timeline / progress / stdout | `9e0b40817db7e944e5545160cf6b2a4e95038ed67efe0e0c1ae6daa4c87275e2` / `96bc563578b7f6542075b9e8440b8701d143e6bda52e82e1e902a2e3212404b9` / `e3bf1829aad0c0068a20050649a8b8d9149ed99295934520a8a132eeaf5943ff` |

F5a action-oracle 已按 physical-gate entry 获授权；本轮不实现 F5a，不修改 solver、runner 或 tests。F4、F5b、matrix-free full、F6 仍未授权。完整 JSON record 位于 `benchmarks/cases/100_static_condensed_full3d_iterative/records/task37_f3_assembled_full_v1.json`。
