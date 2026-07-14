# Case070：Task031 compact physical-slab 内存优先结构优化

## 当前状态

Case070 的最终分类是 `strong_memory_success_slow_but_memory_efficient`。在不改变冻结物理、80 个 DtN 模态、exact condensation 或 ordinary default 的前提下，h2 MPI4 full solve 的外部同时 worker RSS 峰值从 Task030 的 9.374729 GiB 降到 7.897675 GiB（-15.756%），真实 full residual 为 `9.998454e-7`，official R/T/A 与 direct 最大差 `6.126e-9`，且无 swap。

这不是 production default，也不是对任意 Maxwell 参数的无条件收敛保证。它是冻结 target 上经过 h5/h3/h2 true-residual 与 R/T/A Gate 的显式 opt-in 研究 profile。代价是 h2 solve 从 Task030 的 2393.689 s 增加到 11982.581 s（约 5.01 倍）。

## 22 项合同

| 项目 | 值 |
|---|---|
| 1. ID | `070_compact_physical_slab_memory_optimization` |
| 2. 证明 | 冻结 target 上 matrix-free fine action、较小 overlap 与 compact lifecycle 可在真实收敛下把 h2 同时 RSS 压到 8 GiB 以下 |
| 3. 不证明 | 任意角度/材料/网格鲁棒、mesh-independent、多 RHS 高吞吐或 production default |
| 4. 几何 | 50×25×140 nm cell；17×25×120 nm Si block |
| 5. 材料 | 13.5 nm complex Si，`0.999002304859+0.00182649365j` |
| 6. 入射 | theta=80°、phi=0°、s polarization |
| 7. FE | p2 Nédélec；h5/h3/h2 |
| 8. 边界 | double Floquet + auxiliary Fourier-DtN |
| 9. modal identity | 80，top/bottom 各 40 |
| 10. operator | exact `F-C H^-1D`；solve 中 fine `F` action 为 form/MPC matrix-free |
| 11. MPI | 4 ranks |
| 12. outer Krylov | right FGMRES restart90、rtol `1e-6` |
| 13. smoother | 16 physical z-slabs、overlap0.125、ILU0、symmetric pre/post sm2 |
| 14. coarse | Task030/Task027 75D Floquet z-hat wave coarse |
| 15. storage | factor-only、subdomain-local shift、matrix-free fine、compact lifecycle |
| 16. PC legality | adaptive local GMRES PC 非线性，只允许 FGMRES；fixed Richardson 线性但不收敛 |
| 17. memory authority | 0.25 s 外部同时 worker RSS sum；cgroup 单独记录；不求和 per-rank historical peaks |
| 18. h2 watchdog | 9.5 GiB warning、11 GiB controlled termination、禁止 swap |
| 19. numeric Gate | reported/condensed/full residual `<=1e-6` + official R/T/A + closure/direct delta |
| 20. provenance | clean implementation SHA `45a0fc6e...`、image digest、真实命令和 artifact SHA-256 |
| 21. heavy artifacts | `benchmarks/artifacts/cases/070/`，gitignored |
| 22. ordinary default | 不改变；全部新行为显式 opt-in |

## 物理问题

物理问题严格继承 Case031/060 frozen target：complex-Si EUV block grating、p2 Nédélec、double Floquet、80-mode auxiliary DtN 与 exact condensation。任何物理、模式或 RTA 改动都不是本 Case。

## 参数说明

`config.json` 冻结最终显式 profile；`expected/gates.json` 冻结 residual、action、h3 continuation、h2 prediction 与 strong-memory 阈值。ordinary config 不读取这些 research flags。

## 当前证据

## 最终结果

| mesh | FE DoF | iterations | full residual | simultaneous worker peak | Task030 reduction | solve / total (s) |
|---|---:|---:|---:|---:|---:|---:|
| h5 | 44,698 | 1,157 | `9.959903e-7` | 1.619598 GiB | 4.032% | 350.851 / 374.342 |
| h3 | 198,438 | 1,994 | `9.973853e-7` | 3.474346 GiB | 8.399% | 2311.581 / 2370.351 |
| h2 | 615,108 | 1,977 | `9.998454e-7` | 7.897675 GiB | 15.756% | 11982.581 / 12173.086 |

h3 同时满足绝对 `<=3.50 GiB` 和相对 `>=8%` Gate。h2 的 central predictions 为 8.501/8.587 GiB，保守上界 9.447 GiB；实测 7.898 GiB 低于两者，并达到 strong memory success。三份正式 record 都来自同一 tracked-source-clean commit；h2 无 warning、无 termination、swap in/out 都为 0。

## 正确性与结构证据

- matrix-free fine action 相对 assembled `F` 的误差为 h5 `9.718e-16`、h3 `9.460e-16`、h2 `9.248e-16`；solve ledger 中不再保留 `F`。
- h5 200-step assembled 与 matrix-free residual 分别为 `8.611995756e-4` 和 `8.611995763e-4`，差异仅约 `6.3e-13`；matrix-free screen 时间约 3.18 倍。
- overlap0.25 -> 0.125 把 h5 factor nnz 从 7,046,752 降到 5,666,368（-19.59%），但收敛变慢；最终仍通过 h5/h3/h2 full solve。
- 16 个 local factor 的 exact SHA-256 fingerprint 全部不同，`exact_duplicate_factor_count=0`；factor dedup lane 可靠停止，禁止近似共享。
- final adaptive PC 的线性误差为 `2.374308e-2`，普通 GMRES 被 fail-closed；fixed Richardson 达到 `3.611e-15` 线性误差，但 200 步 residual 为 0.7703，故拒绝。
- compact lifecycle 在 h2 把 solver stack release 后 current RSS 降到约 6.50 GiB；但所有 peak claim 都使用全 run 外部最大值，不把 current RSS 下降冒充 peak success。

## 结果解释

内存收益来自 assembled F 生命周期、较小 overlap factor 与 solver/RTA 对象解耦；restart50 和 selective Jacobi 没有形成足够收益。matrix-free form action 是主要时间代价，因此 Case070 是 memory-first，不是吞吐优化。

## 代码路径与理论

调用链是 `run_task031_memory_forensics -> run_workstation_iterative -> mpc_form_action / condensed_dtn / physical_slab_two_level -> official RTA`。理论与对象生命周期见 iterative theory 以及 walkthrough 31/32/33/50。

## PyCharm

普通 Windows Python 没有 complex PETSc/DOLFINx 资格环境。PyCharm 使用 Docker interpreter `myfenics-stage4:task28`，working directory 设为仓库根目录，模块设为 `benchmarks.run_task031_memory_forensics`。h5 可用本目录 `run.sh`；h2 还必须显式增加 `--unlock-h2`，并保留 watchdog。

## CLI 或测试

示例：

```bash
mpiexec -n 4 python -m benchmarks.run_task031_memory_forensics \
  --h-nm 5 --num-slabs 16 --overlap-layers 0.125 \
  --ksp-type fgmres --smoother-ksp-type gmres --restart 90 \
  --max-it 5000 --matrix-free-fine --compact-lifecycle --no-certify-pc \
  --case-label task031_reproduction --run-dir /tmp/task031_reproduction \
  --verified-clean-sha <full-clean-sha>
```

## 限制

`records/best_h5.json`、`best_h3.json`、`best_h2.json` 是可提交轻量记录；`baseline_*.json` 固定 Task030 比较值；`candidate_screen.json`、`pc_linearity.json`、`object_lifecycle.json` 与 `memory_components.json` 保存机制证据。完整 solver JSON、0.25 s timeline 和 field/RTA heavy outputs 留在 ignored artifact 目录。

最终 profile 的收敛证据只覆盖冻结 RHS/物理/分区。FGMRES 的 flexible PC 不是数学意义上的任意问题“保证收敛”；本 Case 的“保证”是 explicit three-residual full solve Gate。matrix-free form action 造成明显时间代价，适合内存受限而非追求吞吐的机器。
