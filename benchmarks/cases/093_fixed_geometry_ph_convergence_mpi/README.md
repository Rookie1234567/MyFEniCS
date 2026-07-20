# Case093：固定结构 p–h 收敛与 MPI identity

本 Case 冻结 Task034 的固定物理结构、S 偏振 uniform p2/p3/p4 收敛、同阶
Full3D–Hybrid closure，以及代表性 p3/h5 的 MPI1/MPI8/MPI16 数值身份。MPI32
只作为 exploratory。用户已批准缩减范围：不执行每个 degree 的完整 MPI 矩阵，P
偏振只保留 p2/h5 MPI8 Full3D 与 Hybrid M160 可计算性示例。

`records/` 仅保存轻量、hash-bound 数据；mesh、field、matrix、factor、timeline 和完整
日志保留在 gitignored 的 `benchmarks/artifacts/task034/phase_f/`。checker 从紧凑记录
重新计算 residual、observable-vector 完整性、MPI identity、hash binding 与 adaptive
unlock，不信任单独的 `status` 字段。

当前最佳离散参考为 `p4/h5`，正式身份仅是
`best_available_discrete_reference_for_case093`：

```text
grid_convergence_proven = false
continuum_reference = false
```

验证：

```bash
cd /home/Projects/MyFEniCS
source .venv/bin/activate-myfenics
python -m benchmarks.task034_case093 check \
  --case-dir benchmarks/cases/093_fixed_geometry_ph_convergence_mpi
```
