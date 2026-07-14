# Task031：compact physical-slab 内存优先结构优化结果总结

## 1. 最终状态

```text
task = Task031
branch = codex/20260714-task31-compact-pc-memory-optimization
base = Task030 merged master 545165b3d29396dcc3a8d5b029089175eafa3c4a
clean implementation commit = 45a0fc6e19535cb8f14fbfb186f099019612fec2
classification = strong_memory_success_slow_but_memory_efficient
ordinary_default_changed = false
review_status = Review V1 response_v1 hardening complete; pending final review
master_decision = pending review and explicit user approval
```

Task031 在冻结 3D p2 Nédélec、双 Floquet、80 模态、exact condensed DtN 与 official R/T/A 的条件下，取得 h2 external simultaneous worker RSS 7.897675 GiB，并保持 full true residual `<=1e-6`。相对 Task030 历史 9.374729 GiB 的观察降幅约 15.8%，但采样实现并非完全同口径；以 Task31 legacy internal 8.176441 GiB 对照时约降 12.8%，故保守表述为从约 9.4 GiB 压缩到约 8.0–8.2 GiB。这是强内存成功，但 h2 solve 约 3.33 小时，明确标记 `slow_but_memory_efficient`，不提升 ordinary default。

## 2. 任务目标与非目标

目标是先保证 frozen target 的真实收敛，再尽可能压缩 Krylov、assembled fine `F`、slab factor 和对象生命周期的峰值存储。非目标包括改变物理/80 modes/RTA 定义、以 current RSS 冒充 peak、近似 factor sharing、静默修改普通 profile，以及宣称任意 Maxwell 参数无条件收敛。

## 3. 基线、冻结配置和环境

冻结几何为 50×25×140 nm cell 与 17×25×120 nm Si block；波长 13.5 nm，theta=80°、phi=0°、s polarization；p2 Nédélec、double Floquet、80 个 auto-propagating DtN unknowns；MPI4 complex PETSc/DOLFINx。

| mesh | FE DoF | Task030 iterations | Task030 full residual | Task030 peak |
|---|---:|---:|---:|---:|
| h5 | 44,698 | 855 | `9.924905e-7` | 1.687653 GiB |
| h3 | 198,438 | 962 | `9.903890e-7` | 3.792912 GiB |
| h2 | 615,108 | 1,873 | `9.972228e-7` | 9.374729 GiB |

正式 run 均来自 clean SHA `45a0fc6e...`，镜像 `myfenics-stage4:task28`，digest `sha256:08c61b...76d`。Task31 外部采样每 0.25 s 同时读取四个 worker RSS、process tree、cgroup current/peak 与 WSL swap；禁止把各 rank 不同时刻的 historical peak 相加。

## 4. 实现与方法

| 方法 | 目的 | 实现/证据 |
|---|---|---|
| external memory forensics | 给出同时 RSS/cgroup/swap/stage authority | `run_task031_memory_forensics.py` |
| assembled-F-free public MPC form action | solve 中不保留 assembled `F`，又保持约束 slave unit rows | `mpc_form_action.py`，action error `<1e-15`；每次 apply 仍执行 form assembly/通信 |
| condensed operator lifecycle | 允许 external fine action，并安全 `require_f/release_f` | `condensed_dtn.py` |
| overlap0.125 | 降低 factor rows/nnz | h5 factor nnz -19.59% |
| compact lifecycle | RTA 前销毁 KSP/PC/factors/work vectors | stage ledger + no-double-destroy tests |
| PC certification | 阻止非线性 flexible PC 与 ordinary GMRES 错配 | linearity fail-closed |
| exact factor fingerprint | 只允许精确重复共享 | 16/16 unique，dedup lane 停止 |

## 5. 实验/运行矩阵

| lane | 实际运行 | 结果/状态 |
|---|---|---|
| Krylov restart | FGMRES90/50，200-step h5 | restart50 内存 -1.89%、更慢且 residual 更差；停止 |
| ordinary GMRES | adaptive PC | linearity `2.374308e-2`，fail closed |
| fixed linear PC | Richardson + GMRES90 | linearity `3.611e-15`，但 200 步 residual 0.7703；numeric negative |
| overlap/slabs | 16/20 slab、overlap0.125 | 16 slab weak-positive；20 slab 更差 |
| selective local solver | boundary Jacobi1 | stored factor nnz 下降，residual 恶化到 0.0118 且 RSS 无收益；停止 |
| public form-action fine | assembled equivalence + 200-step | residual 等价，RSS -2.03%，screen time 3.18x；因内存优先保留 |
| full h5 | combined candidate | 1,157 步 full pass |
| full h3 attempt1 | max_it=1600 | residual `5.490e-6`，未通过；保留负结果 |
| full h3 qualification | same candidate, max_it=5000 | 1,994 步 full pass + 3.474 GiB |
| conditional h2 | two predictions + watchdog | 1,977 步 full pass + 7.898 GiB |

## 6. 关键结果表

| mesh | iterations | reported / condensed / full | simultaneous worker peak | cgroup current peak | solve / total (s) |
|---|---:|---|---:|---:|---:|
| h5 | 1,157 | `9.959903e-7 / 9.959903e-7 / 9.959903e-7` | 1.619598 GiB | 1.056248 GiB | 350.851 / 374.342 |
| h3 | 1,994 | `9.973853e-7 / 9.973853e-7 / 9.973853e-7` | 3.474346 GiB | 2.899216 GiB | 2311.581 / 2370.351 |
| h2 | 1,977 | `9.998454e-7 / 9.998454e-7 / 9.998454e-7` | 7.897675 GiB | 7.424026 GiB | 11982.581 / 12173.086 |

相对 Task030 历史基线，h5/h3/h2 的辅助观察降幅分别为 4.032%、8.399%、15.756%；这不是严格相同 sampler 的精确 A/B。Task31 h2 自身的 external simultaneous / legacy internal peak 分别为 7.897675 / 8.176441 GiB，后者相对 Task030 历史值约降 12.8%。主要结论是 h3 external peak `<=3.50 GiB`、h2 external peak `<=8.0 GiB`，保守工程范围约 8.0–8.2 GiB；h2 未达到 `<=7.0` stretch。

## 7. 数值正确性与 Gate

三套正式 solve 的 KSP reason 都为 2，reported/condensed/full residual 均 `<=1e-6`。h5/h3/h2 official R/T/A 分别为：

- h5：`0.089021602568 / 0.442588275323 / 0.468390124569`，closure `2.460e-9`；
- h3：`0.004613031629 / 0.583653357934 / 0.411733610310`，closure `-1.270e-10`；
- h2：`0.001342934186 / 0.599213235569 / 0.399443835926`，closure `5.682e-9`。

对 canonical direct 的最大 R/T/A delta 分别为 `6.162e-9 / 1.104e-9 / 6.125e-9`，远低于 `1e-6`。public form action 对 assembled `F` 的 action error 为 `9.718e-16 / 9.460e-16 / 9.248e-16`，ledger 证明 solve 中不再保留 assembled `F`。

## 8. 性能或资源结果

h2 外部峰值发生在 `outer_krylov_solve`，为 7.897675 GiB；coarse operator ready 为 7.867531 GiB。solver stack release 后同时 RSS 约 6.50 GiB，RTA complete 约 6.498 GiB。全程 swap in/out delta 都为 0，9.5 GiB warning 与 11 GiB termination 均未触发。

内存收益的成本很高：h2 solve 相对 Task030 约 5.01x。h5 200-step public form-action screen 也从 assembled action 的 18.478 s 增到 58.837 s。释放 `F` 本身只是一次性生命周期动作；主要时间成本是每次 outer apply 都进行 MPC Function 写入/backsubstitution、`ufl.action`、`assemble_vector` 和通信。故这条路线适用于内存受限工作站，不适合作为默认高吞吐 profile。

## 9. 根因解释

峰值下降来自三个互补机制，而不是 Krylov restart：assembled-F-free public form action 消除 solve 中常驻 `F`；overlap0.125 把 slab factor nnz 压低约 19.6%；compact lifecycle 明确缩短 KSP/PC/factor/work-vector 与 RTA 的重叠。FGMRES50 只降低约 1.9% worker RSS且更慢，达不到 3% 停止规则。这里的“matrix-free”不是已缓存优化的低层 element-kernel 实现，当前路径每次 apply 仍调用 `assemble_vector(ufl.action(...))`。

h3/h2 迭代数上升不是 false convergence：稀疏 true-residual history 持续下降，最终三残差一致并通过 R/T/A。adaptive inner GMRES 令 PC 非线性，因此 FGMRES 是合法性要求，不是可随意替换的偏好。fixed Richardson 虽恢复线性，却丢失了有效平滑能力。

## 10. 成功路线

接受的 opt-in profile 是 Task030 physical-slab/wave coarse + 16 slab overlap0.125 + ILU0 symmetric pre/post + local shift + factor-only + FGMRES90 + assembled-F-free public form action + compact lifecycle。h5/h3/h2 都在 clean source 上 full pass，h2 达到 strong memory success。

## 11. 失败、负结果与未运行项

factor dedup 因 16 个 exact fingerprints 全部不同而停止；禁止近似共享。restart50 收益不足 3%；20 slabs 更慢且 residual 更差；boundary Jacobi 大幅破坏残差；fixed linear PC 200 步 residual 0.7703；h3 max_it1600 未收敛。没有运行第二个 h2：任务书最多一个最佳候选，且第一个已达到 8.0 GiB 以下，第二候选没有 `<=7.5 GiB` 的可信预测。

## 12. 代码和文件变化

新增 external sampler 与 public MPC form action；扩展 condensed operator 的 external action/释放生命周期；扩展 physical slab 的 fixed/selective research path；runner 加入 KSP/PC certification、assembled-F-free action、ledger 与 compact lifecycle opt-in。Case070、Task031 outcomes、理论/走读、统一端口文档、solver guide 与合同测试同步更新。完整清单见 `changed_files.md`。

## 13. 最终合并建议

建议经 review 后选择性合并通用 memory sampler、public MPC form action、safe lifecycle、PC certification、ledger、测试、Case070 与文档。最终 candidate 必须保持显式 opt-in；ordinary default 不变。失败的 fixed Richardson/selective Jacobi 不得成为公共 profile；factor dedup 没有实现共享，因为没有 exact duplicate。

## 14. 局限

“保证收敛”只表示冻结 target、MPI4、当前 partition 与 RHS 经 explicit true residual/full RTA 验证，不是一般数学保证。当前单点为 13.5 nm、固定 Si、theta=80°（10° grazing）、S polarization；项目规划中的 1–10° grazing + S/P 仍需后续逐点资格化。memory authority 与 Task030 历史 peak 的采样口径并非完全相同，因此报告同时保留外部 simultaneous、cgroup 与 legacy internal 值。h2 只运行一次 clean final candidate；多次运行方差、其他机器、其他角度和多 RHS 未覆盖。

## 15. 下一步决定

下一步不应继续压 restart 或近似 factor sharing；它们已被证据否定。若需要兼顾计算资源，应优先研究可缓存/批量的 public matrix-free action、减少 form-action 通信/装配开销，或构造既固定线性又保持平滑能力的 local polynomial/Chebyshev PC；任何新方案先在 h5 做 action/true-residual/峰值联合 Gate，再进入 h3/h2。

## 16. 证据索引

- task：`docs/task031_compact_physical_slab_memory_optimization/task.md`；
- outcomes：本目录全部文件；
- benchmark：`benchmarks/cases/070_compact_physical_slab_memory_optimization/README.md`；
- lightweight records：Case070 `records/`；
- heavy evidence：`benchmarks/artifacts/cases/070/`（ignored）；
- implementation：`benchmarks/run_task031_memory_forensics.py`、`benchmarks/run_workstation_iterative.py`、`src/solvers/mpc_form_action.py`、`src/solvers/condensed_dtn.py`、`src/solvers/physical_slab_two_level.py`；
- ports/guide：`docs/iterative_solver_ports.md`、`docs/solver_guide.md`；
- theory/walkthrough：`notes/theory/iterative_solver_and_preconditioner.md`、walkthrough 32/33/50。
