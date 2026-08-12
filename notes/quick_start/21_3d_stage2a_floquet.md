# 3D Stage2A 双 Floquet 空气盒教程

## 1. 功能与物理图景

Stage2A 在 Stage1 方程上增加 x/y 两组 Bloch-Floquet 约束，使相对边界切向迹满足 `E(x+Lx)=phase_x E(x)` 与 `E(y+Ly)=phase_y E(y)`。

## 2. 当前能力状态

`status=test_backed_smoke`。双周期配对、p1/p2 约束路径和 MPI consistency 有测试，但该粗网格 smoke 不是物理精度 benchmark。

## 3. 运行前提

先通过 Stage1。当前 smoke 是均匀空气盒，不含 PML、界面或 grating。

## 4. Public dat input

```text
input/smoke/3d_stage2a_floquet_smoke.dat
```

## 5. Dat 输入位置

完整输入位于 `input/smoke/3d_stage2a_floquet_smoke.dat`；stage 映射由 geometry、Floquet 和 boundary 组合决定。

## 6. 完整参数块

```text
[boundary]
use_floquet_x = true
use_floquet_y = true
```

## 7. 参数含义

| 参数 | 作用 |
|---|---|
| `period_x/y` | 两个周期和相位平移 |
| `incident_theta/phi_deg` | `kx,ky` 与两个 Floquet phase |
| `floquet_constraint_mode` | auto/p1/p2 trace 构造 |
| `mesh_cell_type` | 四面体/六面体路径 |
| `nedelec_degree` | trace DoF 数与 orientation |

## 8. Qualification 边界

改变 p、cell type、非匹配边界网格或接近特殊相位后应重跑约束测试。Stage2A 不验证开放 z 边界。

## 9. CLI 等价命令

PyCharm 的 Run Configuration 只填写该 `.dat` 路径。

```text
python scripts/run_case.py input/smoke/3d_stage2a_floquet_smoke.dat
```

PyCharm 的 Run Configuration 只填写该 `.dat` 路径。

## 10. 真实调用链

```text
run_3d_cases::_run_stage_config
-> solve_maxwell_3d_stage_2a_floquet_airbox::run_stage2a_floquet_airbox_3d_case
-> floquet_3d::build_double_floquet_mpc
-> pair x facets and y facets
-> assemble/solve/postprocess
```

## 11. 输出与字段

查看 `floquet_phase_x/y`、pairing error、slave/master 数、constraint mode requested/used、residual 和 field error。

## 12. ParaView

打开完整 VTU/PVD，用相对边界的 Slice 检查幅值连续；相位条件不能只靠彩色幅值判断，应结合 JSON 的 trace mismatch。

## 13. 成功 Gate

```text
x/y pairing 均存在
orientation 与相位 probe 误差通过
residual 有限
MPI rank 结果一致
```

## 14. 常见错误

| 现象 | 原因 |
|---|---|
| slave/master 数不匹配 | 相对面网格拓扑不同 |
| 幅值连续但相位错 | 只看绝对值 |
| p2 约束失败 | trace orientation/模式选择错误 |
| 把 Stage2A 当开放边界 | z 截断尚未验证 |

## 15. 改成自己的周期

先保持均匀介质，只改 `period_x/y` 和角度，核对解析 phase；通过后再进入 Stage2B/2C 或 Stage4。

## 16. 链接

- Floquet 理论：[`../theory/floquet_periodicity.md`](../theory/floquet_periodicity.md)
- 代码：[`../reference/code_walkthrough/21_3d_floquet_and_pml.md`](../reference/code_walkthrough/21_3d_floquet_and_pml.md)
- Case011：[`../../benchmarks/cases/011_3d_stage2a_floquet/README.md`](../../benchmarks/cases/011_3d_stage2a_floquet/README.md)
