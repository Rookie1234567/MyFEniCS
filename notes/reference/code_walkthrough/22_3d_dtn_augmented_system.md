# 3D DtN 增广系统

## 模态来源

`modes_3d.enumerate_diffraction_orders_3d` 根据周期和 Rayleigh tolerance 枚举 order；`polarization_basis_3d` 给出切向极化；`mode_eh_vectors/mode_power` 建 E/H 和归一化；`outgoing_port_modes_3d` 合并 top/bottom 模态。

## 表面装配

`dtn_port_3d.py` 的核心对象和函数：

| 名称 | 责任 |
|---|---|
| `_surface_vector_form` | 一个极化/相位的 FE 线性形式 |
| `_ReusableSurfaceComponentAssembler` | 重用表面装配，降低重复成本 |
| `_copy_base_matrix_to_augmented` | F -> 更大 `[F *;* *]` |
| `_augmented_vec_from_base` | f -> `[f;0]` |
| `_traction_vector` | modal E -> Maxwell traction |
| `_incident_projection_onto_top_mode` | top 入射幅值 |
| `_dtn_surface_quadrature_degree` | 高 order 表面积分阶次 |
| `_solve_augmented_system` | 写 C/D/H、解与残差 |
| `_assign_fe_solution_from_augmented` | 提取 FE 场 |
| `_gather_auxiliary_values` | MPI 收集小 modal block |
| `_port_power_metrics` | auxiliary official R/T |

zero-order local Robin 是小平层优化/诊断；多 order 正式路径使用完整 sparse auxiliary coupling。

## 对象所有权

base FE matrix/vector 由 stage flow 创建；增广 matrix/vector/solution 由 DtN result 管理；FE Function 只复制 FE segment；auxiliary 数组是小型可序列化数据。失败路径必须保留足够 PETSc 对象直到写完诊断，再统一 destroy，避免 double destroy。

## 方程对应

F 来自 `common_3d_forms` + MPC，C/D 来自表面投影/traction，H 表示 modal relation，f/g 含体源和 top incident source。精确凝聚对应见 `31_exact_condensation.md`。

## 证据

`test_14` 检查 mode/DtN；`test_22` 检查 block condensation；case 020/022 检查平层与等价性；case 031 检查完整 target solve。
