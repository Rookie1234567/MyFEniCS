# 2D TM PML + Floquet

## 运行

PyCharm preset：`2d_tm_pml_floquet_smoke`。

```bash
python src/main.py --preset 2d_tm_pml_floquet_smoke
```

等价调用链：`main.preset_cli_args` -> `runners.run_cases.main` -> `solve_vector_maxwell.run_case`。runner 强制 scattered 路线使用 PML，左右边界由 manual 或 `dolfinx_mpc` 实现 Floquet 相位约束。

## 可改参数

| 参数 | 作用 | 初次建议 |
|---|---|---|
| `pml_top_thickness/bottom_thickness` | 人工吸收层厚度 | 至少做两档厚度比较 |
| `pml_alpha` | 复坐标拉伸强度 | 从 5 开始，不要只增大 alpha |
| `scattering_background` | air/layered 参考场 | 有基座时优先 layered |
| `mesh_target_size` | 全域目标网格 | PML 与结构区都需足够分辨 |

## 验证

检查 Floquet probe mismatch、线性残差、PML 外边界反射迹象和 RTA。PML 吸收的是离开物理区的场，不应并入材料 `A_volume`。详细公式见 [`../theory/pml_robin_and_open_boundaries.md`](../theory/pml_robin_and_open_boundaries.md)，代码见 [`../reference/code_walkthrough/11_2d_floquet_pml_port_forms.md`](../reference/code_walkthrough/11_2d_floquet_pml_port_forms.md)。

常见失败：PML 太薄、材料面不贴网格、实数 PETSc、把 total field 与 scattered field 混用。旧长文 [`pml_scattered_field_diagnostics.md`](../theory/pml_scattered_field_diagnostics.md) 保留诊断案例。
