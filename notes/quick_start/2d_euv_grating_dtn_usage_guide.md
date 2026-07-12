# 2D EUV 光栅 DtN 使用指南

> **文档状态：历史验证长文。** 当前运行入口见 [`11_2d_dtn_floquet.md`](11_2d_dtn_floquet.md) 与 [`12_2d_te_tm_and_complex_material.md`](12_2d_te_tm_and_complex_material.md)；旧 `ACTIVE_2D_INPUT_GROUP="euv_grating"` 已被命名 preset 取代。

## 2026-06-29 更新：p=1 细网格续跑命令

一阶单元 `p=1` 的三角形网格已经补算到 `h=0.35 nm`，但还没有达到“连续两次核心指标相对变化 < 0.1%”的严格收敛标准。下一步建议从 `h=0.3 nm` 继续：

```bash
python3 -m src.studies.run_2d_euv_validation \
  --study mesh_convergence \
  --incident-angle-deg 0 \
  --nedelec-degree 1 \
  --visualization-degree 2 \
  --mesh-sizes 0.3 \
  --cell-shapes triangle

python3 -m src.studies.run_2d_euv_validation \
  --study mesh_convergence \
  --incident-angle-deg 80 \
  --nedelec-degree 1 \
  --visualization-degree 2 \
  --mesh-sizes 0.3 \
  --cell-shapes triangle
```

如果 `h=0.3 nm` 仍未满足 0.1%，再继续尝试 `h=0.25 nm`。注意这已经是几十万到更多自由度的直接法计算，运行时间和内存都会明显增加。

## 2026-06-29 更新：一阶单元 p=1 完整 study 与结果目录说明

本轮把之前所有 2D EUV study 又用一阶单元跑了一遍，包含 0° 法向入射和 80° 掠入射：

```bash
python3 -m src.studies.run_2d_euv_validation \
  --study all \
  --incident-angle-deg 0 \
  --nedelec-degree 1 \
  --visualization-degree 2 \
  --scan-mesh-size 1.0 \
  --scan-cell-shape triangle

python3 -m src.studies.run_2d_euv_validation \
  --study all \
  --incident-angle-deg 80 \
  --nedelec-degree 1 \
  --visualization-degree 2 \
  --scan-mesh-size 1.0 \
  --scan-cell-shape triangle
```

结果目录名会带上角度和单元阶次，例如：

```text
results/studies/2D_EUV_mesh_convergence_theta80p0_p1_20260629_064325
```

单个 case 的目录名也会编码主要参数，例如 `p1` 表示一阶单元，`h1p0` 表示 `mesh_target_size=1.0 nm`，`tri/quad` 分别表示三角形/四边形结构化网格，`t80p0` 表示 80° 入射。完整命名规则和 p=1 全部结果表见 `notes/test/2d_euv_validation_report.md` 顶部。

PNG 预览图现在默认关闭，后续结果目录只保留 ParaView 文件和 JSON/CSV 数值文件。需要临时生成 PNG 时，在 `src.runners.run_cases` 命令中显式加 `--generate-png-plots`；批量 study 默认不生成 PNG。

## 2026-06-29 更新：80° 入射和单元阶次 study 参数

`src/studies/run_2d_euv_validation.py` 现在可以直接指定入射角和单元阶次，不需要改源码：

```bash
python3 -m src.studies.run_2d_euv_validation \
  --study all \
  --incident-angle-deg 80 \
  --nedelec-degree 2 \
  --visualization-degree 3 \
  --scan-mesh-size 1.0 \
  --scan-cell-shape triangle
```

说明：
```text
1. 上一轮 0° 法向入射验证本身已经是 p=2。
2. 本轮 80° 掠入射仍使用 p=2，完整结果写在 notes/test/2d_euv_validation_report.md 顶部。
3. study 输出目录会自动带 theta80p0_p2，避免和法向入射结果混在一起。
```

## 2026-06-29 更新：完整验证后的推荐用法

完整验证已经跑完：`method_compare`、`mesh_convergence`、`air_scan`、`substrate_scan`、`combined_scan` 都通过。

当前正式推荐：
```text
mesh_cell_shape = triangle
mesh_target_size = 1.0 nm
port_boundary_model = dtn
port_dtn_assembly = auxiliary
polarization = TM
```

原因：
```text
1. DtN auxiliary 与 DtN explicit 的 R/T、近场积分一致。
2. triangle 网格在 h=1.5 -> 1.25 -> 1.0 nm 连续两次满足核心指标变化小于 0.1%。
3. quadrilateral h=1.0 nm 仍未达到 0.1% 严格收敛阈值，暂时作为对照路径。
4. 空气厚度、基座厚度和随机组合厚度扫描中，DtN 端口 R+T 都等于 1 到数值舍入精度。
```

完整结果见：
```text
notes/test/2d_euv_validation_report.md
```

## 2026-06-29 更新：新增 100 nm 周期 EUV 矩形光栅基准

本案例用于验证 2D DtN 端口、衍射级 R/T 和近场积分，不代表真实 EUV 材料库。

默认结构：

```text
period_x = 100 nm
substrate_thickness = 50 nm
air_height = 100 nm
grating_width = 50 nm
grating_height = 50 nm
lambda0 = 13.5 nm
polarization = TM
incident_angle_deg = 0
n_air = 1.0
n_substrate = 1.1
n_grating = 1.2
```

推荐先看 `src/main.py`：

```text
SIMULATION_DIMENSION = "2d"
ACTIVE_2D_INPUT_GROUP = "euv_grating"
EUVGratingInputs2D(...)
```

PyCharm 直接运行 `src/main.py` 时会读取 `EUVGratingInputs2D`，并转换成 `src/runners/run_cases.py` 的 CLI 参数。

## 推荐命令

三角形结构化网格 smoke：

```bash
python3 -m src.runners.run_cases \
  --formulation port \
  --constraint-backend manual \
  --port-boundary-model dtn \
  --port-dtn-assembly auxiliary \
  --port-use-diffraction-orders \
  --polarization-type TM \
  --period-x 100 \
  --air-height 100 \
  --substrate-thickness 50 \
  --grating-width 50 \
  --grating-height 50 \
  --lambda0 13.5 \
  --n-air 1.0 \
  --n-substrate 1.1 \
  --n-grating 1.2 \
  --incident-angle-deg 0 \
  --nedelec-degree 2 \
  --visualization-degree 2 \
  --mesh-target-size 5 \
  --mesh-cell-shape triangle \
  --lock-near-field-template \
  --compute-power-metrics
```

四边形结构化网格只改一项：

```bash
--mesh-cell-shape quadrilateral
```

## 研究脚本

批量研究入口：

```bash
python3 -m src.studies.run_2d_euv_validation --study method_compare
python3 -m src.studies.run_2d_euv_validation --study mesh_convergence
python3 -m src.studies.run_2d_euv_validation --study air_scan
python3 -m src.studies.run_2d_euv_validation --study substrate_scan
python3 -m src.studies.run_2d_euv_validation --study combined_scan
```

先只看会跑哪些命令：

```bash
python3 -m src.studies.run_2d_euv_validation --study mesh_convergence --dry-run
```

输出位置：

```text
results/studies/2D_EUV_<study>_<timestamp>/
  study_plan.json
  study_summary.csv
  study_summary.json
```

## 输出怎么看

正式 R/T 以 DtN 端口量为准，优先看：

```text
dtn_auxiliary_power_metrics.json
run_summary.json -> dtn_auxiliary_power_metrics
```

`power_metrics.json` 使用内部 probe line 重建模态，当前保留为诊断，不作为 EUV DtN 主判据。

近场积分位于：

```text
run_summary.json -> near_field_integrals
dtn_auxiliary_power_metrics.json -> near_field_integrals
```

字段含义：

```text
I_grating  = ∫_grating |E|^2 dΩ
I_air_near = ∫_air_near |E|^2 dΩ
I_sub_near = ∫_sub_near |E|^2 dΩ
```

默认近场区域：

```text
air_near: 光栅左右各扩 25 nm，y=0 到 min(air_height,100 nm)，去掉光栅本体
sub_near: 光栅左右各扩 25 nm，y=-min(substrate_thickness,50 nm) 到 0
```

厚度扫描时使用 `--lock-near-field-template`，会插入固定网格面，尽量保证光栅和近场区域的网格不随远处空气/基座厚度变化。
