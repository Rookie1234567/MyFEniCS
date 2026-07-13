# 2D 配置、网格与材料

## `SimulationConfig`

dataclass 保存用户输入和派生量。关键 property：

| property | 公式/用途 |
|---|---|
| `eps_air/substrate/grating` | `n**2` |
| `k0`, `omega` | 波数与物理频率 |
| `kx`, `ky` | 入射波矢 |
| `polarization` | TM 面内横向向量 |
| `floquet_phase` | `exp(i*kx*period_x)` |
| `physical_y_*`, `y_*` | 区分物理区与含 PML 域 |
| `as_jsonable` | complex 转 `[real,imag]`，冻结复现参数 |

## 网格

`mesh_builder.mesh_axis_coordinates_2d` 先生成结构轴。`mesh_lock_near_field_template` 插入光栅和近场积分边界，确保厚度扫描时关注区域网格不漂移。`material_tag_for_rect_2d` 按整个矩形是否落在材料子域判定，避免只用单元中点把跨界单元误标。

`build_mesh` 用 Gmsh 生成 triangle 或 recombined quadrilateral，创建 cell/facet tags，并把网格写到案例目录。材料界面必须落在轴坐标上。

## 材料函数

`materials.relative_permittivity` 按 air/substrate/grating tags 写目标 `epsilon_r`；`background_relative_permittivity` 按 air 或 layered 背景写 `epsilon_b`。scattered RHS 正是两者差乘背景场。

## 对象生命周期

config 在 case 全程只读；mesh/tags 被空间、弱式和后处理共享；epsilon Functions 必须活到装配完成。结果 JSON 使用 config 自身序列化，避免文档手工参数与真实运行分离。

## 证据

`test_16` 检查 EUV preset 翻译、材料矩形和近场面积；2D cases 001-003 冻结运行级证据。
