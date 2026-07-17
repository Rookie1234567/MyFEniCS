# Case093：Full 16-slab no-hidden-ILU exact oracle

本 Case 对应 PARA-Task004，只测量全 slab exact-local-inverse 的全局理论上限，不训练模型。

| 编号 | 冻结合同 |
|---|---|
| 1. | task = PARA-Task004 |
| 2. | predecessor = PARA-Task003 Review V1 |
| 3. | mesh = h5 only |
| 4. | wavelength = 13.5 nm |
| 5. | geometry = validated full-3D Si block grating |
| 6. | element = p2 Nédélec hexahedral |
| 7. | FE DoF = 44,698 |
| 8. | periodicity = double Floquet |
| 9. | ports = 80 Fourier-DtN unknowns |
| 10. | outer = right FGMRES90 |
| 11. | coarse = fixed 75D true-action Galerkin |
| 12. | physical slabs = 16 |
| 13. | overlap = 0.25 layers |
| 14. | formal parallelism = MPI4 |
| 15. | G4 = 0,5,10,15 |
| 16. | G8 = 0,2,5,7,8,10,13,15 |
| 17. | G16 = 0..15 |
| 18. | Lane A = G16 two-step |
| 19. | Lane B = G16 one-step |
| 20. | exact slab ILU factor/apply = zero |
| 21. | model training = prohibited |
| 22. | ordinary default changed = false |

## 物理问题

物理保持 13.5 nm complex-Si periodic block grating、S polarization、p2 Nédélec、double Floquet 和 80 个 Fourier-DtN unknowns。Task003 的一个 exact slab 没有正信号，三个 exact slabs 只把迭代从 860 降到 840。

## 参数说明

Case093 使用预先冻结的嵌套 G4/G8/G16 集合，回答全部 16 个局部逆达到 sparse-LU 精度时，outer iterations 和 operator actions 最多能改善多少。除 exact allow-list 和条件性的 smoother step 数外，物理、网格、coarse、FGMRES90、slab partition、overlap 和线程设置不变。

## No-hidden-ILU 合同

runner 必须在 factorization 前解析 `LocalBackendPlan`。exact-enabled slab 的 `requires_ilu_factor=false`、`allows_fallback=false`；不得先构造 PETSc ILU 再覆盖 action。

Full G16 的硬条件为：

```text
exact_backend_count = 16
ilu_factor_constructed_count = 0
global_stored_ilu_factor_nnz = 0
ilu_apply_count = 0
hidden_fallback_count = 0
```

所有 rank 的 16 个 slab diagnostics 必须汇集到 root record，包括 owner、factor nnz/storage、factorization、apply count/mean/p95 和 destroy 状态。

## 阶段顺序

1. 用 clean implementation HEAD 运行同轮 h5 ILU baseline；
2. 单独 capture 16 个 portable local operators；
3. 逐 slab factorize/destroy，完成 census 和安全预测；
4. 运行 G4 two-step；
5. 运行 G8 two-step；
6. 运行 G16 two-step；
7. 只有 G16 numeric/resource Gate 通过才运行 G16 one-step；
8. 按 iteration/action Gate 决定 learned-PC 路线，不自动训练。

## 数值与资源 Gate

每个正式点必须 KSP 正收敛，reported、condensed 和 full residual 均不超过 `1e-6`，official R/T/A 相对同轮 baseline 最大差不超过 `1e-6`，closure 通过且所有输出 finite。WSL swap 增量必须为 0；外部 sampler 使用 9.5 GiB warning 和 11 GiB controlled stop。

## 结果分类

G16 two-step iteration reduction `>=40%` 为 strong，`>=20%` 为 positive，`10–20%` 为 weak，`<10%` 为 no signal。Lane B 若总 operator actions 降低至少 25% 且 outer iterations 增加不超过 10%，也可形成 positive architecture signal。

即使 positive，本 Task 也只允许建议后续 Task005；不得创建 dataset、checkpoint 或模型。若 two-step `<10%` 且 one-step action reduction `<25%`，停止 local-inverse learning 主路线并转向 coarse/deflation/global correction。

## 运行环境

FEniCS 正式运行使用 WSL complex wrapper：

```text
/home/fenics/.local/bin/myfenics-python-complex
```

MPI/OMP/BLAS 固定为 MPI4、每 rank 单线程。外部 simultaneous RSS 由 `benchmarks.run_task031_memory_forensics` 复用采样；Task004 对 wrapper 新增 exact allow-list 与 smoother-step 透传，不改变其默认行为。

## PyCharm

Windows PyCharm 使用 WSL 解释器 `/home/fenics/.local/bin/myfenics-python-complex`，working directory 为 `/mnt/c/Users/Administrator/Desktop/MyProject`。factor census 也使用该 complex 环境；本 Task 不进入 `fenics-ml` GPU 训练。

## CLI 或测试

正式 worker 入口是 `python -m benchmarks.run_workstation_iterative`，外部 memory sampler 是 `python -m benchmarks.run_task031_memory_forensics`，factor census 是 `python -m benchmarks.neural_pc.benchmark_all_slab_exact_oracle`。测试覆盖 backend plan、no-hidden fallback、MPI gather、allow-list、one/two-step 和 lifecycle。

## 代码路径与理论

backend planning 位于 `local_slab_solver.py` 和 `physical_slab_two_level.py`；sparse-LU backend 位于 `lu_teacher_local_solver.py`。理论上限以 exact local inverse 的 outer iteration/operator-action 收益判断，exact-LU wall time不代表未来 NN wall time。

## 当前证据

开始执行前只有 Task003 的历史 1/3-slab oracle：860→862 和 860→840。G4/G8/G16、no-hidden-ILU 内存、one-step actions 和 learned runtime budget 均等待本 Task 正式运行，不预写为通过。

## 结果解释

G4/G8 只解释趋势和资源 scaling，最终 local-inverse learning 的 go/no-go 由 G16 two-step 与条件性 G16 one-step Gate 决定。exact factor memory只代表 oracle lifecycle，不冒充 neural model memory。

## 限制

结论限定于当前 h5、MPI4、单一物理 RHS、16-slab/75D coarse 架构。Task004 不测试 h3/h2、多物理参数、shared/expert model、learned coarse 或 production default。

## 证据位置

重型 solver record、timeline、raw stdout 和 captured CSR 位于 `benchmarks/artifacts/cases/093/` 并保持 Git ignored。Git 只保存 `records/` 下的轻量摘要、outcomes、配置、合同测试和代码。
