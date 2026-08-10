# Task037b H3/H4 exact block-LDU 与模态块诊断

## 当前结论

H3 与 H4 均已在冻结的 p6/h10、M120、MPI8、S 偏振、10° 掠射、10/110 nm 接口条件下完成。H3 是 exact block-LDU iterative oracle；H4 在同一 exact Sₘ 基线上增加 bounded G-only modal-block diagnostic。两者都不是 ordinary default，也不是最终低内存 iterative candidate 的资格化证明。

| 阶段 | source SHA | 状态 | 边界 |
|---|---|---|---|
| H3 | `e187275cd3d194dcedb9453d36e52bb035ad34dc` | formal、numeric、no-swap PASS | exact local direct factors 只用于 oracle；offline 12+12 已完成 |
| H4a | `98046b7297b5de23d121b60898afe9e9007abc6e` | exact Sₘ PASS | 复现 H3 algebra/direct/field/RTA/lifecycle Gate |
| H4b | `98046b7297b5de23d121b60898afe9e9007abc6e` | diagnostic complete | G-only 允许负 KSP reason 与较大残差，不作失败判定 |

## H3 exact block-LDU

| 指标 | 实际值 |
|---|---:|
| return / formal / numeric / no-swap | `0 / pass / pass / pass` |
| outer iterations / reason | `1 / 2 (CONVERGED_RTOL)` |
| reported global residual | `2.892497666184978e-12` |
| true global residual | `2.892237294698294e-12` |
| bottom / top / modal true residual | `3.610918199454199e-12 / 2.0470485206121342e-12 / 9.879221339086588e-13` |
| direct solution / modal relative error | `5.108471533338298e-13 / 6.960336394200873e-13` |
| factors | before 2，after 0，released |
| frozen 12+12 | powers `12/12`，amplitudes `12/12` |
| maximum power / amplitude error | `1.865e-12 / 2.084e-12` |
| R / T / A / A_volume | `0.0007628814751516535 / 0.6027016339842497 / 0.3965354845405986 / 0.3965354846965839` |
| closure error | `1.5598522473680987e-10` |

H3 总时长为 `507.2017102949321 s`，authority peak 为 `9.585384368896484 GiB`，swap 为 0。H3 的 offline comparator 结果绑定于独立 compact artifact，未把 direct factor 阶段误称为 candidate 内存峰值。

## H4 bounded modal-block diagnostic

H4a 使用 exact Sₘ；H4b 只把 240×240 modal solve block 替换为 G。两轮 local factors 顺序建立、释放，不同时驻留。

| 指标 | H4a exact Sₘ | H4b G-only |
|---|---:|---:|
| outer iterations | `1` | `3` |
| reason | `2 (CONVERGED_RTOL)` | `-3 (DIVERGED_ITS)`，诊断字段 |
| reported global residual | `2.7238001757092862e-12` | `0.01538429995364092` |
| true global residual | `2.7239301070596716e-12` | `0.015384299953641066` |
| bottom / top / modal residual | `3.982460029685523e-12 / 1.7429945983458624e-12 / 1.001248228432052e-12` | `4.29650936428029e-12 / 2.1213389122910122e-04 / 1.511249790494066e-02` |
| solution / modal error to H4a | — | `0.004900532829746777 / 0.009905532844701982` |
| finite / evidence / lifecycle | pass / pass / pass | pass / pass / pass |

H4b 差异是预期的 bounded diagnostic：不触发调参、重跑、阈值放宽，也不归类为 Task37b negative。H4a/H4b 的 factor inventory 均为 before `2`、after `0`，after 的 bottom/top released 均为 `true`。

### Sₘ、G 与 operator contract

| 项目 | 值 |
|---|---:|
| Sₘ/G shape | `240×240 / 240×240` |
| Sₘ/G dtype | `complex128 / complex128` |
| Sₘ/G condition | `8.506393910953664 / 9.809898278230046` |
| feedback Frobenius norm | `19.517257662402848` |
| feedback relative to Sₘ / G | `0.5655707066195622 / 1.0002181415666924` |
| candidate operator | MatPython、matrix-free |
| global A / bottom F / top F | `false / false / false` |
| explicit external C / D | `0 / 0` |
| p6 direct factor count | `0` |

端部反馈不可忽略；后续按任务书由 approximate local inverse 构造 approximate Sₘ，不采用 G-only 作为最终近似。

### H4 物理、资源与 timing

| 指标 | 实际值 |
|---|---:|
| R / T / A | `0.0007628814751444795 / 0.6027016339840818 / 0.3965354845407737` |
| A_volume | `0.3965354846964806` |
| closure error | `1.557070028468388e-10` |
| vs pinned Full3D ΔR / ΔT / ΔA | `1.8619003908093568e-14 / -1.4558354521909678e-12 / 1.4371837053772651e-12` |
| total wall | `540.3976704040542 s` |
| authority peak | `9.802722930908203 GiB`，stage=`record_and_release` |
| warning / termination / swap | `未触发 / 未触发 / 0` |

H4 关键 timing：H4b factor setup/solve=`31.84789529000409 / 0.5016900589689612 s`；post-H3 direct comparison=`28.747818996896967 s`；recovery/RTA=`7.698509941925295 s`；RTA evaluation=`0.02652613096870482 s`。该 peak 是 H4 whole-job oracle peak，不是最终 iterative 预测；allocator high-water 与 lifecycle inventory 必须区分。

## 证据与下一阶段

原始输出位于 Git ignored artifact 目录；tracked docs 只保存 hash-bound 引用。

| 证据 | 路径 | SHA256 |
|---|---|---|
| H3 solver | `benchmarks/artifacts/task037b/h3_exact_block_ldu_e187275_mpi8/solver_record.json` | `606c8f8299b7344921a9404554b7769e87a021e0291b085eaded56e05bf4dd1f` |
| H3 summary | `benchmarks/artifacts/task037b/h3_exact_block_ldu_e187275_mpi8.json` | `e93cf4659812479cc458a0352b243b99605ef392817dcc49fc56b54d4618b0a9` |
| H3 offline comparator | `benchmarks/artifacts/task037b/h3_exact_block_ldu_e187275_mpi8/h3_offline_12_channel_comparison.json` | `bc97055753ff061cac99587b8046e15da3bdc26391aa251eed11a8cfb7af6159` |
| H3 stages | `benchmarks/artifacts/task037b/h3_exact_block_ldu_e187275_mpi8/memory_stages.jsonl` | `451fb15813ae091168f88847559584829a5f231bde9299ee8e73eaf2fd6e478f` |
| H3 stdout | `benchmarks/artifacts/task037b/h3_exact_block_ldu_e187275_mpi8/worker_stdout.txt` | `12cc17da51a491b87179846be819d353ed4e61c3ecc2d0210ac145f0bbf481e0` |
| H4 solver | `benchmarks/artifacts/task037b/h4_modal_block_98046b7_mpi8/solver_record.json` | `9a6737d21c93d39310c70020785d0a4231f1d83296b858fa38c2a4bacf3d169f` |
| H4 summary | `benchmarks/artifacts/task037b/h4_modal_block_98046b7_mpi8.json` | `bce01b0c24ffb8e09ba158b8784353ed6073648ea3c8d1dc57bd03c33b6c0b40` |
| H4 stages | `benchmarks/artifacts/task037b/h4_modal_block_98046b7_mpi8/memory_stages.jsonl` | `bb27debecbb0ac23c5d15c4c4fe3727b50574252449422243c8643b8cb6bf033` |
| H4 stdout | `benchmarks/artifacts/task037b/h4_modal_block_98046b7_mpi8/worker_stdout.txt` | `f13de07c6ccdf73d023606e5f7c8cc19b9926b647440f273b31b947a2690ef61` |

H5 为下一阶段；H6-H10 必须按任务顺序等待 H5。H3/H4 direct-factor oracle 不得冒充最终低内存候选，ordinary defaults 保持不变，Hybrid-P 仍未 production-qualified。
