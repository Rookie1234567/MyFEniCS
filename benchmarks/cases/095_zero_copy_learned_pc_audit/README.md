# Case095：Zero-Copy Learned-PC Audit Architecture

本 Case 对应 PARA-Task006，只资格化 R4 learned-output audit architecture。它复用
Task005 冻结 checkpoint，不训练 full16 模型，不执行 learned-active global solve。

| 编号 | 冻结合同 |
|---|---|
| 1. | task = PARA-Task006 |
| 2. | predecessor = Task005 Review V1 |
| 3. | mesh = h5 only |
| 4. | wavelength = 13.5 nm |
| 5. | material = current validated complex Si |
| 6. | element = p2 Nédélec hexahedral |
| 7. | FE DoF = 44,698 |
| 8. | periodicity = double Floquet |
| 9. | ports = 80 Fourier-DtN unknowns |
| 10. | outer = right FGMRES90 |
| 11. | coarse = fixed 75D true-action Galerkin |
| 12. | physical slabs = 16 |
| 13. | overlap = 0.25 layers |
| 14. | formal live shadow = MPI4 |
| 15. | R4 = 0,5,9,15 |
| 16. | reused model = Task005 A_D0_R64 |
| 17. | private persistent local CSR bytes = 0 |
| 18. | proxy thresholds use Q0 only |
| 19. | periodic audit K candidates = 4,8,16,32 |
| 20. | ILU writes back during live shadow |
| 21. | ordinary default changed = false |
| 22. | production claim allowed = false |

## 物理问题

物理与 Task005 相同：13.5 nm complex-Si periodic block grating、theta 80°、
phi 0°、S polarization、p2 Nédélec、double Floquet 和 80 个 Fourier-DtN
unknowns。第一阶段只运行 h5，不运行 h3/h2。

## 参数说明

冻结 16 slabs、0.25 overlap、two-step smoother、post-smooth、75D coarse、
right FGMRES90、rtol 1e-6。正式 shadow 为 MPI4 且每 rank/BLAS 单线程。
R4 只含 slab 0、5、9、15。

首选模型是 Task005 `A_D0_R64` linear low-rank policy。checkpoint、operator
fingerprint 和 dataset checksum 必须先匹配；不允许 retraining。H 的身份为
consumed screening split，V 未用于 Task005 候选选择。

## PyCharm

Windows PyCharm 使用 WSL FEniCS 解释器
`/home/fenics/.local/bin/myfenics-python-complex`，working directory 为
`/mnt/c/Users/Administrator/Desktop/MyProject`。纯 ML replay 使用同一 WSL 中
`/home/fenics/miniforge3/envs/fenics-ml/bin/python`。

## CLI 或测试

正式 baseline/shadow 由 `benchmarks.run_task031_memory_forensics` 包装
`benchmarks.run_workstation_iterative`。qualification 脚本和 heavy records 放在
`benchmarks/artifacts/cases/095/`，tracked case 只保存配置、合同与轻量摘要。

## 代码路径与理论

borrowed exact action 复用 `DistributedPhysicalSlabSmoother` 已有 union scatter 和
shifted-F/global action：将 local correction lift 到 global vector，执行既有 MatMult，
再 restrict 回原 slab。不得构造或持久保存 local CSR。

proxy 只保存 reduced certificate、procedural sketch metadata 和小型 buffers。
“strict”仅表示在冻结 operator/corpus/threshold/fault set 上 zero observed false
accept，并由 periodic exact audit 与 fail-closed runtime 补充，不是普适证明。

## 当前证据

Task005 R4 fixed-operator local quality 与 model-only runtime 为正信号，但 private
exact-audit CSR 使最小 owner storage 达到 68.282 MiB。Task006 P1 已证明 16/16
borrowed action 等价且 persistent CSR 为 0；P2 的 12 个 Q0 proxy family 全部因
false reject 过高失败，P3-P7 按 Gate 未运行。

## 结果解释

P0-P8 必须按序通过。P1 borrowed action 要求 16/16 CSR/action 与 rho 等价误差
`<=1e-12`；P2 只能看 Q0 冻结 proxy；P3-P5 才可做 locked replay、故障注入和
K=4/8/16/32 周期比较。

最终分类为 `audit_architecture_false_reject_failure`。没有 proxy threshold 被锁定，
Q1-Q5 未读取，live shadow 未解锁；不得恢复 Task005 P3。

## 限制

结论限定于当前 h5、R4、冻结模型、冻结 qualification corpus、单一物理/RHS 和
规定故障集合。不得外推到 full16 learned profile、未知误差分布、h3/h2 或
production default。
