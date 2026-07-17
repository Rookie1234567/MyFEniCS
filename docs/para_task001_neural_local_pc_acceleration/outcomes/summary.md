# PARA-Task001 阶段结果总结

## 1. 最终状态

```text
task = PARA-Task001
branch = ChatGPT/20260715-para-task-neural-local-pc
current_classification = h5_numeric_pass_engineering_negative
ordinary_default_changed = false
production_claim_allowed = false
h3_allowed = false
h2_allowed = false
```

当前阶段完成了仓库一致性审计、持久 WSL complex FE 环境、稳定 local-slab abstraction、两次独立真实 Krylov capture、GPU POD-MLP 离线训练、frozen checkpoint/checksum、NN-only 与 ILU+NN runtime safety，以及真实 MPI4 h5 baseline/one-slab A/B。one-slab ILU+NN 保持数值正确且局部修正有效，但总时间变为 2.888×，因此工程 Gate 失败并停止 h3/h2。

## 2. 任务目标与非目标

目标是只替换或增强 physical-slab 局部修正，保持 exact condensed operator、right FGMRES、75D coarse、MPI ownership、full true residual 和 official R/T/A 不变。非目标是改 ordinary default、用训练 loss 冒充求解成功、跳过 h5 直接跑 h3/h2，或把大型 dataset/checkpoint 提交 Git。

## 3. 基线、冻结配置和环境

冻结物理与 Task030/031 相同。正式 A/B 继续固定 MPI4；机器资源用于数据和训练，不改变 baseline 并行度。

| 资源 | 实测 |
|---|---:|
| WSL | Ubuntu 24.04 / WSL2 |
| CPU | Intel Xeon Platinum 8260，48 visible cores |
| WSL memory / swap | 228 GiB / 32 GiB |
| GPU | 2× Quadro RTX 8000，49152/46080 MiB |
| PyTorch | 2.7.1+cu118，CUDA 可见 2 卡 |
| FE solver | DOLFINx 0.10.0.post2；PETSc 3.19.6 complex；MPC 0.10.1 complex user build |
| ML trainer | conda `fenics-ml`；PyTorch 2.7.1+cu118 |

项目已改用持久 WSL complex FEniCS 栈，不再使用 Docker。Ubuntu 的 MPC Python 包只链接 real ABI，因此从官方 v0.10.1 源码在用户目录重编译；`ldd` 已确认只加载 complex DOLFINx/PETSc/SLEPc。MPI2 adapter 与 MPI4 h5 均通过。

## 4. 实现与方法

| 方法 | 目的 | 代码 |
|---|---|---|
| portable complex CSR | 唯一保存每个 owner slab operator、fingerprint 和 metadata | `local_slab_solver.py` |
| stable backend protocol | 统一 ILU/Jacobi/NN/ILU+NN 的 `solve(rhs,out)` | `local_slab_solver.py` |
| frozen POD-MLP | 避免大型 dense `Linear(n_s,n_s)` | `neural_local_pc.py` |
| residual/nondegradation safety | finite、norm、rho、fallback、NN-only fail closed | `neural_local_pc.py` |
| bounded real capture | 从 `_apply_once()` 按 stride 采 real Krylov RHS/ILU correction | `petsc_capture.py` |
| offline GPU training | CUDA POD + MLP，联合 correction/residual loss | `train_local_pc.py` |
| explicit runtime integration | checkpoint root/lane/rho 作为 research-only runner flags | `run_workstation_iterative.py` |

## 5. 实验矩阵

见 `experiment_matrix.csv`。已运行 pure unit、compile、CUDA toy、MPI4 h5 baseline、两次独立 capture、三类代表 slab dataset、slab-9 GPU training/evaluation 与 one-slab guarded A/B。all-slab、h3、h2 因 h5 工程 Gate 失败而没有运行。

## 6. 关键结果

| 指标 | toy validation |
|---|---:|
| samples | 205 |
| rho median | 0.133051 |
| rho p95 | 0.145946 |
| correction error median | 0.133512 |
| determinism error | 0 |
| mean / p95 frozen NumPy inference | 35.3 / 52.7 µs |
| local feasibility Gate | pass |

训练为 1024 samples、POD rank 48、hidden 128、batch 512、300 epochs、seed `20260717`。final validation correction/residual loss 为 0.005630/0.006114；loss 只作训练诊断，Gate 使用上表 local action residual。

真实 slab 9 的 rank256/hidden512 候选在独立 `ilu_residual` validation 上达到 `rho median/p95=0.5733/0.7116`；全体 validation 的 NN-only `p95=0.9929`，因此 NN-only 明确失败，只放行带 ILU 和 non-degradation 的 Lane B。在线 5124 次调用全部被安全检查接受，`rho median/p95=0.3779/0.5303`，fallback 为 0。

## 7. 数值正确性与 Gate

新增 6 个 pure tests 与 PETSc owner-computes adapter 已在 single rank/MPI2 通过。完整 suite 为 182 tests；恢复原虚拟 `P^H` 后，PETSc 3.19 仅有一个未使用的 p/h Galerkin research test 因版本能力不支持，neural/75D 主路径不调用它。one-slab h5 的 condensed/full residual 均为 `9.903219e-7`，official R/T/A 为 `0.0890216041/0.4425882733/0.4683901210`，closure `-1.529e-9`。

## 8. 性能和资源

RTX 8000 toy training 为 3.679 s。真实 slab-9 最终训练为 8.988 s，GPU peak allocated/reserved 277,752,832/291,504,128 bytes，checkpoint 为 45,094,912 bytes。

| h5 run | iterations | solve / total s | peak GiB |
|---|---:|---:|---:|
| original ILU baseline | 861 | 93.312 / 156.746 | 1.602940 |
| one-slab ILU+NN | 854 | 412.318 / 452.641 | 1.654888 |

迭代数只下降 0.813%，solve/total 分别恶化到 4.419×/2.888×；peak 增加 3.241%。NN inference 与 residual check 分别累计 35.036/69.543 s，one-level mean apply 从 0.00937 s 增到 0.07125 s。h5 的 `>=20%` wall-time 加速 Gate 明确失败。

## 9. 根因解释

真实结果说明 reduced model 确实能改善被选 slab 的 ILU correction，并轻微减少外层迭代；但 owner rank 的冻结 NumPy dense POD/MLP、两次 sparse residual action 与 MPI 同步等待远大于节省的 7 次 FGMRES 迭代。瓶颈是在线执行方式与收益幅度，而不是 GPU 训练时间或显存。

## 10. 成功路线

可保留的研究基础设施包括 portable dataset schema、独立-run validation、GPU offline trainer、frozen checkpoint、checksum、local residual telemetry、explicit fallback、bounded capture 和 stable adapter。当前 checkpoint/runtime candidate 不应提升；若未来重开，应先做 batched/GPU owner-local inference 或廉价线性 reduced map，并把 residual check 与已有 action 融合，不能直接扩展到 16 slabs。

## 11. 失败、负结果与未运行项

- Docker 路线按用户要求停止；没有构建或保留项目容器。
- conda-forge DOLFINx 0.10 complex spec 不存在，不能把当前 real PETSc 当作 complex 环境。
- NN-only aggregate real-slab Gate 失败；Lane B 只在 runtime-relevant residual 子集通过。
- one-slab h5 数值通过但时间 Gate 严重失败；all-slab、h3、h2 被 Gate 禁止。
- 双 GPU data parallel 未用于小 reduced model，因为同步成本预计高于收益；第二卡留作独立候选训练。

## 12. 代码和文件变化

详见 `changed_files.md`。

## 13. 合并建议

不建议提升 neural runtime 或整体合并 research branch。只可考虑选择性保留 abstraction、dataset/capture schema、安全 fallback、telemetry、tests 和文档；最终 checkpoint 与 one-slab backend 属于负结果。ordinary default 始终不变。

## 14. 局限

当前结论覆盖一个物理 RHS、MPI4 partition、PETSc 3.19 complex 和单个内部 slab；不同运行中有 6/16 slab operator fingerprint 发生位级变化，故 checkpoint 必须逐次 fail-closed 匹配。没有 all-slab、h3/h2、多 RHS 或 GPU在线 batch inference 证据。

## 15. 下一步决定

1. 本任务按 `h5_numeric_pass_engineering_negative` 停止，h3/h2 保持锁定；
2. 若未来重开，先用 batched GPU 或线性 reduced operator 把 one-level overhead 降到接近 baseline；
3. 保留 fingerprint、checksum、fallback、non-degradation 和 true-residual/RTA Gate；
4. 只有新的 one-slab h5 达到 wall-time `>=20%` 改善，才考虑 all-slab/h3。

## 16. 证据索引

- task：`../task.md`；
- benchmark：`benchmarks/cases/090_neural_local_pc_acceleration/`；
- heavy local evidence：`benchmarks/artifacts/cases/090/`；
- implementation：`src/solvers/local_slab_solver.py`、`src/solvers/neural_local_pc.py`；
- training/capture：`benchmarks/neural_pc/`。
