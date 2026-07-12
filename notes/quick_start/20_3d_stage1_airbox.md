# 3D Stage 1 空气盒

Stage 1 只验证三维 H(curl) 空间、解析平面波、边界条件、直接求解和场输出；它不包含 Floquet、PML、材料界面或光栅。

```bash
python src/main.py --preset 3d_stage1_airbox_smoke
```

这是无参数 PyCharm Run 的默认 preset。调用链：`main` -> `run_3d_cases` -> `solve_maxwell_3d_stage_1_airbox` -> `common_3d_case_flow`。

## 通过标准

| 检查 | 含义 |
|---|---|
| 线性残差 | 代数系统已正确求解 |
| E/H 相对误差 | 数值场与解析平面波一致 |
| Poynting 方向余弦 | 功率传播方向正确 |
| MPI2 benchmark | 分区后仍给出一致全局系统 |

Stage 1 通过不能证明 Stage 4 端口或 RTA。理论见 [`../theory/3d_stages_and_validation_ladder.md`](../theory/3d_stages_and_validation_ladder.md)，基准见 [`../../benchmarks/cases/010_3d_stage1_airbox/README.md`](../../benchmarks/cases/010_3d_stage1_airbox/README.md)。
