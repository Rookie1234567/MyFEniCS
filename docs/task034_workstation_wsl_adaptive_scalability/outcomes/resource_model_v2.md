# Task034 资源模型 v2

## 结论

本模型废止“直接把 Task33 旧 launch guard 外推到 1 TiB/0.7 nm”的做法，改用组件分离的
engineering prediction。它不是 PDE run，不是 solver pass，也不授权任何重型计算。

| 波长 nm | uniform local FE DoF（预测） | QEP DoF（预测） | M/方向（预测） | total GiB | 最大组件 | 256 GiB | 1 TiB | 2 TiB |
|---:|---:|---:|---:|---:|---|---|---|---|
| 13.5 | 68,396 | 2,053 | 160 | 4.695 | MPI/runtime residual 1.937 GiB | guardband feasible | guardband feasible | guardband feasible |
| 5 | 1,346,239 | 14,967 | 1,167 | 201.533 | dense multi-RHS 93.997 GiB | high risk | guardband feasible | guardband feasible |
| 2 | 21,034,977 | 93,540 | 7,290 | 13,225.875 | dense multi-RHS 9,179.360 GiB | infeasible | infeasible | infeasible |
| 1 | 168,279,809 | 374,160 | 29,160 | 358,034.098 | dense multi-RHS 293,739.510 GiB | infeasible | infeasible | infeasible |
| 0.7 | 490,611,687 | 763,591 | 59,511 | 2,014,975.394 | dense multi-RHS 1,747,721.249 GiB | infeasible | infeasible | infeasible |

13.5 nm 的 4.695 GiB 被校准为已测 p2/h3 Hybrid M160 同时 worker RSS 峰值；其余波长
均为预测。5 nm 的 256 GiB 分类虽然未超过预算，但只剩小于 30% guardband，因此是
`candidate_high_risk`，不是可直接运行结论。

## 实测校准

模型输入并绑定 SHA-256：

- `fixed_geometry_ph_convergence.csv`：p2/h5、p2/h3、p2/h2，p3/h10、h7.5、h5、h3，
  p4/h10、h7.5、h5 的 full3D/Hybrid peak envelope；
- `adaptive_compression.json`：conservative/balanced/aggressive M160 的 DoF、factor NNZ、
  memory 与 wall time；
- p2/h3 uniform Hybrid M160 watchdog：local matrices/factors、QEP shape、right/left vectors、
  projection、Schur、multi-RHS、reconstruction 与 RSS 的组件基准。

三档 adaptive 候选均未通过同误差 Gate。因此资源预测允许的 measured adaptive compression
factor 固定为 `1.0`；raw DoF reduction 不得抵扣未来内存。

## 缩放假设与数据身份

令 `s = 13.5 / wavelength_nm`。当前固定几何、固定 points-per-wavelength 工程模型采用：

| 组件 | 缩放 | 理由与身份 |
|---|---:|---|
| local 3D FE assembly | `s^3` | volume DoF；measured-calibrated / predicted |
| local 3D direct factor | `s^4` | 3D nested-dissection memory proxy；predicted |
| QEP coefficient matrices | `s^2` | transverse DoF；predicted sparse proxy |
| QEP shift-invert factor | `s^3` | 2D direct factor proxy；predicted |
| right/left mode vectors | `s^4` | QEP DoF `s^2` × M `s^2` |
| interface projection `N_interface M` | `s^4` | transverse trace × modes |
| replicated dense modal arrays | `s^4` | six complex `(2M)^2` objects × 48 ranks |
| Hybrid dense multi-RHS | `s^5` | local rows `s^3` × modal RHS `s^2` |
| field reconstruction | `s^3` | local vectors；predicted |
| MPI/process overhead | `s^0` | 13.5 nm measured residual；lower-bound proxy |

M 使用 `160 s^2` 的 transverse reciprocal-order area 预测。真实 material dispersion、cutoff、
evanescent buffer、角度与 S/P 对 M 的影响仍是 unknown，未来必须重新做 M funnel。

## 0.7 nm 组件结果

| 组件 | predicted GiB |
|---|---:|
| local 3D FE assembly | 1,161.650 |
| local 3D direct factorization | 198,690.256 |
| QEP coefficient matrices | 4.096 |
| QEP shift-invert factorization | 29.829 |
| right/left mode vectors | 5,273.235 |
| interface projection | 1,282.690 |
| replicated dense modal arrays | 60,793.265 |
| Hybrid Schur/dense multi-RHS | 1,747,721.249 |
| field reconstruction | 17.187 |
| MPI/process overhead proxy | 1.937 |

单个 complex `(2M)^2` 对象约 211.093 GiB，已经达到 256 GiB 的 82.5%；即使省略所有其他
对象，也不能把当前 replicated modal layout 写成稳健可行。实际 48-rank replicated array
inventory 与 multi-RHS 更早越过全部预算。

## 压缩需求

0.7 nm 若只看总量，进入 256 GiB、1 TiB、2 TiB 分别至少需要约 7,871x、1,968x、984x
联合压缩。把预算各分一半给 local 与 modal/runtime 时：

| 预算 | local 至少压缩 | modal/runtime 至少压缩 |
|---:|---:|---:|
| 256 GiB | 1,561x | 14,181x |
| 1 TiB | 390x | 3,545x |
| 2 TiB | 195x | 1,773x |

这些倍数不是某个单一算法承诺，只表示当前对象体量与预算的距离。因为 local 与 modal 任一
保持不变都已单独超过预算，不能靠只优化另一侧进入 0.7 nm 预算。

## 必需重构

1. 通过物理等误差 Gate 的 field-driven h-adaptivity；
2. matrix-free/low-storage iterative local solver，替代当前 3D direct fill；
3. distributed/streamed right/left vectors；
4. 删除 replicated dense `M^2` arrays；
5. blocked/streamed multi-RHS Schur 与 field recovery。

完整机器可读结果见 `resource_model_v2.json` 与 `resource_model_v2.csv`。

