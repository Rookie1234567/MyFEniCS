# Case090：Neural local PC acceleration

## 当前状态

Case090 是 PARA-Task001 的显式 opt-in research case。真实 MPI4 h5 baseline、独立 capture、slab-9 GPU 训练和 one-slab ILU+NN A/B 已完成。候选保持 true residual/RTA 并把迭代从 861 降到 854，但总时间恶化到 2.888×，因此分类为 `h5_numeric_pass_engineering_negative`，不得宣称全局 Maxwell 加速，也不得进入 h3/h2。

## 物理问题

真实阶段沿用冻结的三维周期 Maxwell block-grating 问题；神经网络只替换或增强 owner rank 上的 physical-slab 局部修正，不改变 condensed operator、75D coarse、right FGMRES、边界条件或 R/T/A 定义。

## 参数说明

## 22 项合同

| 项目 | 值 |
|---|---|
| 1. ID | `090_neural_local_pc_acceleration` |
| 2. 证明 | 冻结 POD-MLP 可在 complex sparse toy 上给出确定、有限且通过局部 residual Gate 的修正 |
| 3. 不证明 | h5/h3/h2 全局收敛、wall-time 加速、内存下降或 production 能力 |
| 4. 几何 | 真实阶段冻结为 50×25×140 nm cell、17×25×120 nm Si block |
| 5. 材料 | 真实阶段冻结 13.5 nm complex Si |
| 6. 入射 | theta=80°、phi=0°、S polarization |
| 7. FE | 真实阶段 p2 Nédélec；顺序 h5→h3→h2 |
| 8. 边界 | double Floquet + 80 auxiliary Fourier-DtN unknowns |
| 9. operator | exact condensed `F-C H^-1D` 不变；NN 只进入 local slab backend |
| 10. baseline | Task030 speed 与 Task031 memory-first 分开比较 |
| 11. MPI | 正式 A/B 固定 4 ranks |
| 12. coarse | 固定 75D true-action Galerkin coarse |
| 13. local lanes | NN-only、优先 ILU+NN residual correction、条件 one-step smoother |
| 14. data | unique slab CSR + synthetic/teacher/real-Krylov/ILU-residual；全局 A/b 禁止保存 |
| 15. training | offline PyTorch GPU；solver runtime 禁止在线反向传播 |
| 16. runtime | frozen NumPy/PyTorch inference，CPU fallback 必须保留 |
| 17. safety | finite/norm/local-rho/checksum；无 fallback 的 NN-only fail closed |
| 18. telemetry | apply/fallback/rho/inference/transfer/model memory |
| 19. numeric Gate | full residual、official R/T/A、closure 均沿用现有口径 |
| 20. performance Gate | h5 同 action baseline wall time 至少下降 20%，peak 增加不超过 10% |
| 21. artifacts | dataset/checkpoint/profiler 写入 `benchmarks/artifacts/cases/090/` |
| 22. ordinary default | 不改变；失败 backend 留在 research branch |

## 当前机器参数

WSL2 为 Ubuntu 24.04，可见 48 个 Xeon Platinum 8260 核、约 228 GiB 内存、32 GiB swap 和两张 Quadro RTX 8000。正式 solver A/B 保持 MPI4、每 rank 单线程，以维持既有 baseline 口径。GPU 训练默认 `cuda:0`；POD rank 128、hidden width 256、batch 512 是真实 h5 起点。该 reduced model 尺寸下单卡比双卡同步更合理；第二张卡留作独立超参数候选，不把不同并行策略混入同一 A/B。

## PyCharm

Windows PyCharm 使用 WSL system interpreter wrapper 运行复数 FEniCS 求解器，使用 `fenics-ml` conda interpreter 运行 CUDA 训练。完整配置见 `notes/quick_start/wsl_pycharm_fenics_gpu_guide.md`；两个解释器不可混用，以免把 real PETSc 动态库加载进 complex 求解进程。

## 当前 toy 结果

固定 seed `20260717`、1024 samples、POD rank 48、hidden 128、batch 512、300 epochs：GPU training 约 3.679 s，peak allocated/reserved 为 20,136,960/25,165,824 bytes；validation `rho_median=0.133051`、`rho_p95=0.145946`、determinism error 0。这些值来自 ignored artifact，轻量摘要写入本任务 outcomes。

## CLI 或测试

```bash
conda run -n fenics-ml python -m benchmarks.run_neural_local_pc \
  --mode toy-smoke --device cuda:0 \
  --artifact-root benchmarks/artifacts/cases/090/toy_smoke
```

真实 h5 数据采集使用 workstation runner 的显式参数：

```bash
mpiexec -n 4 python -m benchmarks.run_workstation_iterative \
  <Task030-or-Task031 same-action flags> \
  --neural-capture-dir benchmarks/artifacts/cases/090/h5_capture \
  --neural-capture-limit 128 --neural-capture-stride 10 \
  --record benchmarks/artifacts/cases/090/h5_capture_record.json
```

## 代码路径与理论

- local backend port：`src/solvers/local_slab_solver.py`；
- frozen runtime：`src/solvers/neural_local_pc.py`；
- capture/training/evaluation：`benchmarks/neural_pc/`；
- solver integration：`src/solvers/physical_slab_two_level.py` 与 `benchmarks/run_workstation_iterative.py`；
- 数学和 Gate：`docs/para_task001_neural_local_pc_acceleration/task.md`。

## 当前证据

pure NumPy tests、complex PETSc adapter single-rank/MPI2、CUDA toy、MPI4 h5 baseline、两次独立 capture 和 one-slab guarded A/B 已通过执行。one-slab full residual 为 `9.903219e-7`，R/T/A 与 baseline 差均低于 `2e-9`；但 solve/total 为 4.419×/2.888×，性能 Gate 失败，因此本 Case 不进入 canonical production manifest。

## 结果解释

真实 h5 说明 reduced correction 可以改善一个内部 slab 的局部 residual 并轻微减少迭代，但冻结 NumPy inference、sparse residual checks 和 MPI 等待远大于收益。峰值只增加 3.241%，时间却严重恶化，故结论是数值可行、工程加速失败。

## 限制

复数 system FE 栈与 CUDA conda 栈是两个解释器；数据通过 NPZ/JSON artifact 交换。当前只验证一个 RHS、MPI4 和 slab 9；6/16 slab 在独立 run 间出现位级 fingerprint 变化，必须逐次 fail closed。h3/h2 以及 all-slab 运行均被性能 Gate 禁止，checkpoint 和大型 CSR 不提交 Git。
