# 2D TM scattered-field PML + Floquet 教程

## 1. 功能与物理图景

该路径求解 x 周期结构中的 TM 面内电场 `E=(Ex,Ey)`。左右边界满足 Floquet 相位，上下用复坐标拉伸 PML 吸收散射场；入射场不应在 PML 中被重复吸收。

## 2. 当前能力状态

```text
status = experimental_path_smoke
assembly/solve = 可运行
PML accuracy/convergence = 尚未资格化
official production RTA = 不声明
```

## 3. 运行前提

使用 complex PETSc 镜像；本路径选择 `calculation_method="scattered"`、TM、manual Floquet。先运行默认 smoke，不要直接把 PML 厚度压到一个单元。

## 4. PyCharm preset

```python
ACTIVE_PYCHARM_PRESET = "2d_tm_pml_floquet_smoke"
```

`--list-presets --verbose` 会标记它为 lightweight experimental path smoke。

## 5. `main.py` 实际修改位置

参数来自 `_TM_PML_2D = Inputs2D(...)`。要建立用户案例，用 `replace(_TM_PML_2D, ...)` 创建新名字，不要改 Case001 的冻结合同。

## 6. 当前完整参数块

```python
Inputs2D(
    calculation_method="scattered",
    polarization_type="TM",
    constraint_backend="manual",
    scattering_background="layered",
    period_x=600.0,
    air_height=850.0,
    substrate_thickness=350.0,
    pml_top_thickness=300.0,
    pml_bottom_thickness=300.0,
    pml_alpha=5.0,
    nedelec_degree=1,
    mesh_target_size=80.0,
)
```

## 7. 参数含义、单位和合法值

| 参数 | 单位 | 含义 | 合法/建议 |
|---|---|---|---|
| `period_x` | nm | 周期 | `>0` |
| `pml_*_thickness` | nm | 拉伸层厚度 | `>0`，需多层单元 |
| `pml_alpha` | 无量纲 | 拉伸强度 | 正数；过大会导致离散反射/病态 |
| `scattering_background` | - | 入射背景 | `air` 或 `layered` |
| `incident_angle_deg` | deg | 入射角 | 影响 Floquet phase |
| `mesh_target_size` | nm | 目标单元尺度 | 必须同时解析波和 PML |

## 8. 哪些改动超出 qualification

当前本来就只是 path smoke。改变 PML 厚度、alpha、波长、角度或网格后，需要做反射误差与网格/PML 收敛；单次 residual 很小不能证明 PML 精度。

## 9. CLI 等价命令

```text
python src/main.py --preset 2d_tm_pml_floquet_smoke \
  --results-root benchmarks/artifacts/cases/001
```

Case-contained 入口是 `benchmarks/cases/001_2d_tm_pml_floquet/run.sh`。

## 10. 真实调用链

```text
src.main::preset_cli_args
-> src.runners.run_cases::main
-> src.solvers.solve_vector_maxwell::run_case
-> src.geometry.mesh_builder::build_mesh
-> src.constraints.floquet_constraint::build_floquet_constraints
-> src.common.pml::top_pml_tensors / bottom_pml_tensors
-> src.postprocessing.power_metrics::compute_power_metrics
```

## 11. 输出目录与 JSON

```text
<run>/
├── run_summary.json
├── solver_log.txt
├── mesh.msh
├── fields_for_paraview.vtu
└── diffraction_orders.json/csv
```

先看 `reduced_linear_residual`、`floquet_max_probe_error`、PML cell tags 和 `config`。

## 12. ParaView 步骤

打开 `fields_for_paraview.vtu`，用 `E_scat_abs` 观察散射场；对 PML 做 `Clip` 或 `Threshold`，确认场在外边界前衰减。只看总场可能掩盖反射。

## 13. 成功 Gate

```text
程序完成且 residual 有限
左右 Floquet mismatch 接近机器精度
PML 区域标签存在
场无 NaN/Inf
```

这些 Gate 只证明路径可运行，不证明反射足够小。

## 14. 常见错误

| 现象 | 原因 |
|---|---|
| 外边界强反射 | PML 太薄、alpha/网格不合适 |
| 入射波也快速衰减 | total/scattered field 或背景定义错误 |
| 左右边界断裂 | Floquet 相位/配对错误 |
| residual 小但 R/T 异常 | PML 后处理身份不是 canonical DtN power |

## 15. 从 smoke 改成自己的 case

一次只改一组量：先固定几何扫描 PML 厚度与 alpha，再固定 PML 做网格收敛，最后才改材料和角度。保存每次外边界反射指标，不把 Case001 升级为 accuracy benchmark，除非有解析或高可信参考。

## 16. 链接

- PML 理论：[`../theory/pml_robin_and_open_boundaries.md`](../theory/pml_robin_and_open_boundaries.md)
- 代码导读：[`../reference/code_walkthrough/11_2d_floquet_pml_port_forms.md`](../reference/code_walkthrough/11_2d_floquet_pml_port_forms.md)
- Benchmark：[`../../benchmarks/cases/001_2d_tm_pml_floquet/README.md`](../../benchmarks/cases/001_2d_tm_pml_floquet/README.md)
