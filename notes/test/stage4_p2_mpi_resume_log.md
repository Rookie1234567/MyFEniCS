# Stage 4 p=2 MPI 续接记录

## 2026-07-01 更新：Stage4A p=2 MPI 污染已修复

本轮已修复 `stage4_flat_layer_sanity + nedelec_degree=2` 在 MPI 下出现的 Ex/Ez 异常污染。根因是 p=2 Floquet face-interior dof 的局部 face transform 在部分 MPI 分区下不满足真实 Nedelec moment 约束。

### 已完成

- 修改 `src/constraints/floquet_3d.py`
  - p=2 edge dof 仍走显式拓扑配对。
  - p=2 face-interior dof 改为每个周期 face 的局部 4x4 Nedelec moment fit。
  - 不恢复 whole-plane probe/pinv，不构造 dense side transform。
- 新增诊断脚本 `src/test/diagnose_p2_mpc_constraints.py`
  - 用解析周期场检查 x/y edge、x/y face、corner 的 slave/master 系数残差。
  - MPI2/MPI4 下所有 bad rows 均为 0。
- 完成实跑：
  - `h20, p2, np2`
  - `h20, p2, np4`
  - `h10, p2, np2`
- 完成基础测试：
  - `python3 -m compileall -q src`
  - `python3 -m unittest discover -s src/test -p "test_*.py"`，结果为 `54 tests OK, 10 skipped`。

### 关键结果

| case | 结果 |
|---|---|
| p2 constraint diagnostic np2 | x_edge/x_face/y_edge/y_face/corner bad = 0，最大残差约 `5.4e-13` |
| p2 constraint diagnostic np4 | x_edge/x_face/y_edge/y_face/corner bad = 0，最大残差约 `5.4e-13` |
| Stage4A h20 p2 np2 | `max Ex/Ey/Ez = 2.78e-12 / 1.00 / 2.76e-12`，`R/T = 9.21e-13 / 1.00` |
| Stage4A h20 p2 np4 | `max Ex/Ey/Ez = 2.80e-12 / 1.00 / 2.71e-12`，`R/T = 9.21e-13 / 1.00` |
| Stage4A h10 p2 np2 | `max Ex/Ey/Ez = 1.36e-11 / 1.00 / 1.20e-11`，`R/T = 4.52e-15 / 1.00` |

### 后续建议

1. Stage4A flat-layer sanity 可以继续作为 p=2 Floquet + zero-order DtN 的 MPI sanity。
2. Stage4B block grating 仍不要立刻开放 p=2；下一步需要单独做 block grating 的 p=2 物理验证。
3. 若继续推进高阶，应先把这个诊断脚本收敛成正式 MPI smoke 测试脚本，避免未来改 Floquet 时回归。

## 2026-06-30 历史记录：曾误判为 DtN 端口主因

当时观察到 Stage4A p=2 MPI 下 Ex/Ez 污染严重，并排查过后处理 ghost cell、quadrature、grad-div、解向量回填等方向。后续 2026-07-01 的系数残差诊断表明，真正根因是 p=2 face-interior Floquet 局部 transform，而不是 zero-order DtN 端口本身。
