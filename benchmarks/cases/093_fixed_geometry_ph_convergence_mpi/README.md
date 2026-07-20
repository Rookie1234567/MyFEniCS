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

## 物理问题

Case093 使用 Task034 冻结的 13.5 nm rectangular block grating。周期为
`50 nm × 25 nm`，grating height 为 120 nm，入射角为 80°，生产矩阵以 S
polarization 为主。Full3D 与 Hybrid 必须共享几何、材料、入射波、reference planes、
采样点和 official diffraction/absorption 定义。

本 Case 判断有限元离散序列、同阶方法闭合和代表性 MPI 数值身份；不以有限个网格点
证明 continuum convergence，也不把 Hybrid 的 modal convergence 替代 spatial error。

## 参数说明

| 编号 | 参数或 observable | Case093 约定 |
|---|---|---|
| 1. | wavelength | 13.5 nm |
| 2. | period x | 50 nm |
| 3. | period y | 25 nm |
| 4. | grating height | 120 nm |
| 5. | incident theta | 80 degree |
| 6. | incident phi | 0 degree |
| 7. | primary polarization | S |
| 8. | formal MPI set | 1, 8, 16 on p3/h5 |
| 9. | exploratory MPI | 32；不替代 MPI16 |
| 10. | degrees | p2, p3, p4 |
| 11. | uniform p2 h | 5, 3, 2 nm |
| 12. | uniform p3 h | 7.5, 5, 3 nm |
| 13. | uniform p4 h | 10, 7.5, 5 nm |
| 14. | Hybrid selected modes | M160 per direction |
| 15. | official scalar observables | R_total, T_total, A_balance, A_volume |
| 16. | field observables | five-plane E/H relative L2 |
| 17. | interface observables | tangential E/H relative L2 |
| 18. | order observables | significant power/amplitude/phase |
| 19. | algebraic gate | explicit full true relative residual |
| 20. | resource gate | process-tree peak memory and zero job swap |
| 21. | source gate | clean and stable SHA; no nonignored untracked files |
| 22. | physical identity | SHA-256 bound in convergence summary |

## PyCharm

在 PyCharm 中选择 `/home/Projects/MyFEniCS/.venv/bin/python`，working directory
设为仓库根目录。运行配置使用 module name `benchmarks.task034_case093`，参数为
`check --case-dir benchmarks/cases/093_fixed_geometry_ph_convergence_mpi`。checker 是
轻量验证，不会启动新的 PDE。

## CLI 或测试

上述 CLI 必须返回零退出码。仓库级测试可运行：

```bash
pytest -q src/test/test_82_task034_case093.py
```

重型原始 PDE 只能按 Task034 staged Gate、one-heavy-case-at-a-time 和 watchdog 规则
重建；`test_command.txt` 给出 Case-contained 的轻量入口。

## 代码路径与理论

聚合/checker 位于 `benchmarks/task034_case093.py`。Full3D 使用三维 H(curl) Nédélec
离散与 DtN port；Hybrid 使用相同 degree/h 的局部 FEM、QEP modes 与 modal Schur
coupling。两种方法只在完整 reference binding 和同阶 observable vector 上比较。

理论解释沿用 `notes/theory/` 中 Floquet、DtN、QEP、true residual 与 diffraction
定义；Case093 不重新定义 official observable，也不允许从 R/T/A closure 推断场误差。

## 当前证据

`records/convergence_summary.json` 保存 uniform p–h 和 closure authority；
`records/mpi_identity_summary.json` 保存 p3/h5 MPI1/8/16 资格化与 MPI32 exploratory；
`records/canonical_benchmark_manifest.json` 冻结每个 qualified degree 的 canonical
anchor。所有 compact records 均绑定 ignored raw artifact 的路径与 SHA-256。

当前 S 主矩阵中，p2、p3、p4 各有三个成功 Full3D/Hybrid 同阶点；p3/h10 Hybrid
formal negative、用户新增细网格的资源停止和其他 failures 仍保留，不从 authority
中过滤掉。

## 结果解释

相邻离散差下降只能称 measured convergence sequence。Full3D–Hybrid closure 说明
selected M 对同一 degree/h 的 observable 一致；MPI identity 说明代表案例的数值不受
rank 数量影响。三者是不同 Gate，任何一个不能替代另一个。

`best_available_discrete_reference_for_case093` 是工程身份，不是 exact solution。
P polarization 只证明 p2/h5 可计算；不扩展成 P 收敛矩阵。

## 限制

Case093 没有独立 continuum reference，没有建立观察收敛阶，也没有覆盖所有 p/h 的
MPI1/8/16。MPI32 只作 exploratory。raw mesh、matrix、field 和 timeline 为 gitignored
本机证据，tracked compact records 通过 hash binding 供审查与可移植 checker 使用。
