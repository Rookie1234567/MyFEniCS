# Case095：高阶 local-hp 资源包络

本 case 只研究 Task034 的 fixed rectangular block grating。它不创建、不运行
任何不规则几何；相关原 Task035b G1/G2/Phase F 条目均为
`out_of_scope_by_user / not_run / not_a_completion_gate`。

## 当前目标

- 在同一实际 mesh instance 和同一 mesh/cell-tag/facet-tag hash 上运行
  global p4/p5/p6；
- 保存 H(curl) edge、face-interior、cell-interior DoF 分解；
- 实测 augmented rows、NNZ、average/max row width、MUMPS factor NNZ/fill、
  simultaneous peak memory 和分阶段时间；
- 只把 static-condensation trace rows 报告为
  `derived_not_measured`，直到真正 condensation 系统完成装配与求解；
- ordinary default 保持不变。

## 固定网格身份

当前 structured hexa h10 网格为 `(6, 3, 14)`、252 cells，所有材料面
严格对齐：

- mesh SHA-256:
  `f0eef2aa28e86014b661a921993bcfd45e6db1892da350402f2be11ec64dd857`
- cell-tag SHA-256:
  `42f511fc7ffddcbc2972d641018e16a845f48c11067ccd9a9686695ad5cfc131`
- facet-tag SHA-256:
  `0adbcfed35e1840460f826cb1ca1695ed87c0c3960e2073377d2f50871c3c0bd`

## 已完成 formal records

| record | source SHA | 状态 | simultaneous peak |
|---|---|---|---:|
| `records/global_hexa_p4_p5_h10_mpi8.json` | `2e91d2bf0195056e55be670af226b7716096284c` | `actual_global_r5_pass` | 14.928 GiB |

p5/h10 的 101,815 FE DoF 分解为 edge 5,335、face-interior 36,000、
cell-interior 60,480；加 80 个 DtN auxiliary 后实测为 101,895 rows。
理论上消去全部 cell-interior 后为 41,415 rows（2.460x row projection），
但这不是当前矩阵实测值。

## 复现

必须先使用仓库资格化 activation；正式运行还必须把
`--verified-clean-sha` 替换为当前干净完整 SHA。

```bash
cd /home/Projects/MyFEniCS
source scripts/activate_myfenics_wsl.sh
python -m benchmarks.run_task035_actual_r5 \
  --coarse-degree 4 --enriched-degree 5 \
  --h-nm 10 --mesh-cell-type hexahedron --single-mesh-pair \
  --mpi-size 8 --warning-gib 48 --terminate-gib 96 \
  --timeout-seconds 7200 --verified-clean-sha <FULL_SHA> \
  --record benchmarks/cases/095_high_order_local_hp_resource_envelope/records/global_hexa_p4_p5_h10_mpi8.json
```

原始 mesh、field、长日志和 memory timeline 位于 gitignored
`benchmarks/artifacts/task035/actual_global_r5/`；tracked JSON 通过 SHA-256
绑定这些证据。
