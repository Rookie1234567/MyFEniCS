# PARA-Task004 结果总结

## 1. 最终状态

```text
task = PARA-Task004
branch = ChatGPT/20260715-para-task-neural-local-pc
implementation_commit = c8a70dc17e405fcf0bcd5742592530967d26bbc1
classification = all_slab_oracle_positive_signal
lane_a_g16_signal = positive
lane_b_one_step = numeric_failure / architecture_signal_fail
model_training_run = false
h3_run = false
h2_run = false
ordinary_default_changed = false
```

Task004 在 clean implementation HEAD 上完成了同轮 h5/MPI4 baseline、16-slab factor census、冻结 G4/G8/G16 two-step oracle 和条件解锁的 G16 one-step。G16 two-step 把 outer iterations 从 861 降至 566，下降 34.26%，达到 `>=20%` positive Gate，但未达到 `>=40%` strong Gate。因此全 slab local-inverse learning 存在明确理论上限，后续 Task005 可进入审阅/用户决策；本 Task 没有训练任何模型。

One-step 在 1200 步上限处 full residual 仍为 `1.048e-5`，numeric Gate 失败；其 total operator actions 反而增加，不能作为架构正信号。

## 2. 任务目标与非目标

目标是回答全部 16 个 physical slabs 使用 exact local inverse 且对应 ILU factor 真正不存在时，当前 75D coarse + right FGMRES90 的最大 outer/action 收益。非目标包括 NN/linear/shared/expert model、checkpoint、h3/h2、coarse/overlap/slab 调参、ordinary default 或 production claim。

## 3. 冻结配置与环境

| 类别 | 冻结值 |
|---|---|
| 物理 | 13.5 nm complex-Si block grating，theta 80°，phi 0°，S polarization |
| 离散 | p2 Nédélec hexahedral，h5，44,698 FE DoF |
| 端口/算子 | 80 Fourier-DtN unknowns，exact condensed action |
| two-level | 16 physical slabs，overlap 0.25，75D true-action Galerkin coarse |
| Krylov | right FGMRES90，rtol `1e-6`，max_it 1200 |
| local baseline | shifted-F ILU0，two-step，post-smooth，factor-only storage |
| formal parallelism | MPI4；OMP/OPENBLAS/MKL/NUMEXPR threads = 1 |

| 环境 | 实测 |
|---|---|
| WSL/kernel | Ubuntu 24.04；Linux 6.18.33.2-microsoft-standard-WSL2 |
| CPU | Intel Xeon Platinum 8260，48 visible cores |
| memory/swap | 239,144,268 / 33,554,432 kB |
| Python/NumPy/SciPy | 3.12.3 / 1.26.4 / 1.11.4 |
| DOLFINx/MPC/PETSc | 0.10.0.post2 / 0.10.1 / 3.19.6 complex128 |
| GPU | 2× Quadro RTX 8000；本 Task 未训练、未使用 GPU |

## 4. 实现与方法

| 方法 | 目的 | 关键合同 |
|---|---|---|
| `LocalBackendPlan` | factorization 前决定 backend/lifecycle | exact plan 不允许 ILU 或 fallback |
| no-hidden-ILU setup | exact slab 直接由 portable CSR 构造 sparse LU | 不先建 ILU 再覆盖 |
| MPI global diagnostics | 汇集所有 rank 的 16 slab | owner/factor/apply/timing/destroy 完整 |
| sequential factor census | 正式 G16 前逐 slab factorize/test/destroy | residual、storage、per-rank predictor |
| external sampler | 0.25 s simultaneous worker RSS/swap | 不相加不同时间的 rank historical peaks |
| explicit smoother steps | 比较 two-step 与 one-step | 只改变 `smoother_iterations` |

任务书引用的 `src/solvers/sparse_galerkin_two_level.py` 在当前分支不存在；实际 coarse/smoother 实现位于 `physical_slab_two_level.py`，未擅自同步其他分支。

## 5. 实验矩阵

| 阶段 | 实际执行 | 状态 | 说明 |
|---|---|---|---|
| Task003 Review V1 response | 是 | pass | 统一 2.576 s；接受限定 |
| P0 clean baseline | 是 | pass | clean SHA `c8a70dc...` |
| operator capture | 是 | diagnostic | max_it=1，仅为 ignored CSR |
| P1 no-hidden infrastructure | 是 | pass | unit + MPI2 |
| P2 factor census | 是 | pass | 16/16 residual/destroy/safety |
| P3 G4 two-step | 是 | numeric pass | 冻结 `{0,5,10,15}` |
| P4 G8 two-step | 是 | numeric pass | 冻结嵌套 8 slabs |
| P5 G16 two-step | 是 | positive signal | 主要 oracle |
| P6 G16 one-step | 是 | numeric fail | 1200 步未收敛 |
| model training/h3/h2 | 否 | prohibited/not_run | 超出 Task004 |

## 6. Oracle 梯度关键结果

| run | exact/ILU slabs | iterations | iteration reduction | operator applies | one-level applies | solve s |
|---|---:|---:|---:|---:|---:|---:|
| same-run ILU baseline | 0 / 16 | 861 | baseline | 2,603 | 5,166 | 89.190 |
| G4 two-step | 4 / 12 | 804 | 6.62% | 2,430 | 4,824 | 153.415 |
| G8 two-step | 8 / 8 | 792 | 8.01% | 2,394 | 4,752 | 198.548 |
| G16 two-step | 16 / 0 | 566 | **34.26%** | 1,712 | 3,396 | 174.429 |
| G16 one-step | 16 / 0 | 1200 | -39.37% | 3,629 | 2,400 | 140.115 |

G4→G8 改善较缓，G16 出现明显非线性增益，说明少量 isolated replacements 不能代表 all-slab spectrum。Exact-LU wall time较慢，不用于判断未来 learned action 的实测速度。

## 7. 数值正确性

| run | KSP reason | reported residual | condensed/full residual | max R/T/A delta | closure |
|---|---:|---:|---:|---:|---:|
| baseline | positive | `9.992481e-7` | `9.992481e-7` | baseline | `-1.808e-9` |
| G4 | positive | `9.937502e-7` | `9.937502e-7` | `1.685e-9` | `-1.503e-9` |
| G8 | positive | `9.887252e-7` | `9.887252e-7` | `2.191e-9` | `-2.902e-9` |
| G16 two-step | positive | `9.974429e-7` | `9.974429e-7` | `6.131e-9` | `-5.484e-9` |
| G16 one-step | `-3` | `1.048139e-5` | `1.048139e-5` | not_run | R/T/A gated |

所有 converged runs 的 R/T/A delta 远低于 `1e-6`。One-step 没有用未收敛场计算 official R/T/A。

## 8. No-hidden-ILU 与 factor lifecycle

| G16 hard contract | 实测 | 结果 |
|---|---:|---|
| exact backend count | 16 | pass |
| ILU factor constructed count | 0 | pass |
| global stored ILU factor nnz | 0 | pass |
| ILU apply count | 0 | pass |
| hidden fallback count | 0 | pass |
| exact apply count | 54,336 | recorded |
| destroy diagnostics | 16/16 destroyed | pass |

Formal G16 exact factor为 45,747,719 nnz、916,096,012 B。Census 为 45,724,195 nnz、915,625,532 B；六个 3,670-row boundary/near-boundary factors 的 SuperLU numeric pivot fill 略有变化，总 storage 差约 0.05%，operator fingerprints 完全一致，不影响 residual 或安全结论。

## 9. 内存与 rank balance

| run | external simultaneous worker peak | internal incl. RTA peak | swap delta |
|---|---:|---:|---:|
| baseline | 1.607 GiB | 1.599 GiB | 0 / 0 |
| G4 | 2.017 GiB | 2.010 GiB | 0 / 0 |
| G8 | 2.419 GiB | 2.409 GiB | 0 / 0 |
| G16 two-step | 3.275 GiB | 3.268 GiB | 0 / 0 |
| G16 one-step | 3.262 GiB | 3.252 GiB | 0 / 0 |

G16 per-rank exact factor storage为 228.70–229.35 MB，factorization sum为 6.563–6.601 s，critical rank exact solve accumulated time为 142.176 s；owner assignment非常均衡。Baseline removed ILU estimate为 141,220,416 B global，exact oracle net factor payload增加约 738.98 MiB。该值是 oracle factor memory，不是 NN model memory。

## 10. Operator actions 与 one-step 负结果

G16 two-step相对 baseline：

- outer iterations：-34.26%；
- total condensed operator applies：2,603→1,712，-34.23%；
- one-level applies：5,166→3,396，-34.26%。

One-step 虽把 one-level applies 降至 2,400（-53.54%），但 outer 迭代达到 1200 上限（至少 +39.37%），total operator applies 增至 3,629（+39.42%）。它同时失败 numeric Gate、operator-action Gate 和 outer-increase Gate。

## 11. Learned runtime/storage budget

Baseline root/critical one-level path累计约 46.989 s；作为包含 gather/scatter 与 ILU solves 的上界，得到 baseline non-local estimate 42.201 s。G16 critical exact rank累计 142.176 s，G16 solve 174.429 s，故同一 action-count下 non-local observed estimate为 32.252 s。

要使 projected learned G16 solve `<=0.8×89.190=71.352 s`，critical local learned budget最多 39.100 s：

| 预算口径 | 上限 |
|---|---:|
| independent per-slab call（4 slabs/owner 串行） | 2.878 ms |
| per-owner batch（4 local slabs） | 11.514 ms / one-level apply |
| all-rank synchronized critical path | 11.514 ms / global one-level apply |
| memory-neutral model+basis+buffers global | 134.678 MiB |
| memory-neutral per owner rank | 33.670 MiB |

这是由 oracle telemetry 推出的预测预算，不是 NN 性能、训练成本或泛化实测。

## 12. 根因解释

Task003 的 1/3-slab 信号弱，是因为大部分 local blocks仍由 ILU控制；G16 同时改善全部 Schwarz local inverses后，outer spectrum出现 34% 收益。G4/G8 到 G16 的非线性跳变说明不能按 slab 数线性外推。

Two-step 仍是当前可靠架构。One-step 减少每次 PC 的 local actions，却显著削弱平滑，导致 outer actions增加并未在 1200 步收敛。后续 learned-PC若开展，应近似 G16 two-step，而不是以本次 one-step 作为默认目标。

## 13. 成功、失败与未运行

| 对象 | 最终身份 |
|---|---|
| backend planning / MPI diagnostics / census | accepted research infrastructure |
| G16 two-step exact oracle | positive global signal |
| G4/G8 | numeric-pass trend diagnostics |
| G16 one-step | numeric and architecture negative |
| exact-LU wall time | oracle-only，非 learned speed |
| learned model | not run in Task004 |
| h3/h2 | not run / prohibited |

## 14. 最终决策与边界

最终分类为 `all_slab_oracle_positive_signal`。Task004 允许最终 review 建议新的 Task005，在用户明确决定后比较 16 independent models、3 expert classes 或 shared trunk + slab adapters；Task004 本身不自动启动训练。

ordinary default不变，不作 neural acceleration、memory saving、production-ready 或多参数泛化声明。One-step不得提升。Large CSR/factors/raw logs/timelines继续 Git ignored。

## 15. 局限与下一步

结论只覆盖当前 h5、MPI4、单一物理/RHS、16-slab/75D coarse 架构。Sparse-LU runtime慢且 host-only；它只给谱质量上限。未来 Task005 必须先满足 2.878 ms per-slab/11.514 ms per-owner-batch预算、33.670 MiB per-rank storage budget和独立 validation，然后才允许 shadow/active。

若未来 learned approximation无法保持足够 local quality或超过预算，应转向 learned coarse/deflation/cross-slab correction，而不是用训练 loss绕过 full residual和global speed Gate。

## 16. 验证与 provenance

| 检查 | 结果 |
|---|---|
| Task004 targeted contracts | 22 passed |
| complete `src/test` suite | 195 passed，11 skipped |
| MPI2 exact owner/gather/lifecycle | 每 rank 4 passed |
| Ruff changed Python | pass |
| compileall `src benchmarks` | pass |
| `git diff --check` | pass |
| heavy artifact ignore | pass |

Baseline、G4、G8、G16 two-step和one-step均由clean implementation SHA `c8a70dc17e405fcf0bcd5742592530967d26bbc1`运行，formal wrapper写入`tracked_source_dirty=false`和host clean attestation。每份lightweight record固定对应heavy solver JSON的SHA-256。

External sampler复用了历史`run_task031_memory_forensics.py`，因此ignored sampler summary顶层兼容字段仍写`task=Task031`；`case=para093_*`、worker command、source SHA、Case093 records和Task004 outcomes均明确标识本任务。这是wrapper schema的遗留标签，不改变采样数据或solver provenance。

## 17. 证据索引

- Task：`../task.md`
- Review predecessor：`../../para_task003_lu_teacher_nn_only_local_inverse/review_report_v1.md`
- Case093：`benchmarks/cases/093_full_16_slab_exact_oracle/`
- Heavy local evidence：`benchmarks/artifacts/cases/093/`
- Implementation：`local_slab_solver.py`、`physical_slab_two_level.py`、`lu_teacher_local_solver.py`
- Census：`benchmark_all_slab_exact_oracle.py`
- Lightweight records：`benchmarks/cases/093_full_16_slab_exact_oracle/records/`
