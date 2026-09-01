# Direct authority packet audit v1

本审计只整理已经存在的 compact record，不启动或生成新的 PDE。它回答的是：当前 13.5 nm、p6/h10、grazing 1° 的结果，是否已有可直接用于物理场比较的独立权威数据。结果是 `AUTHORITY_ARRAYS_MISSING`：已有 scalar 能量总量，但没有可核验的 E/H、near-field 和衍射复振幅数组。

## 结论

| 项目 | 事实 |
|---|---|
| classification | `AUTHORITY_ARRAYS_MISSING` |
| 当前输入 | 13.5 nm，p6/h10，s，grazing 1°，theta 89°，phi 0° |
| 输入 SHA | `819fc99caea2dbc8ea22546917fbe3898c822a955d079b4582c4a27e34ebba41` |
| physical model SHA | `9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f` |
| ordered mode manifest SHA | `dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2` |
| V13 C1 | 四个 exact-input p6 positive source 均 PASS；`selected_hierarchy=same_mesh_hcurl_pmg_v1_requalified` |
| V13 P0 | cold setup 在 `2,024,108,032 B` 触发 `2,000,000,000 B` hard stop；swap=0，仅到 `paths_ready` |
| 新 PDE | 未运行、未生成 |

C1 positive 资格说明预条件器在正定辅助算子上的行为；它不是含波动与 streaming DtN 的 physical Maxwell 结果。P0 的资源停止也不是数值失败。V11/V12 的 negative 和 selected-none 结论均保持冻结。

## 物理参数对齐、canonical identity 未证明的 scalar packet

Task037c compact 的源记录自身标记 `verified_clean=true`，source SHA 为
`f2d7719b6253251a06e8cd8388fd443bbf47d443`；这是该历史记录的源码身份，
不是当前 Task038 source SHA。它只提供物理参数对齐的 scalar packet，不能被称为
完整的 exact-input authority。

| 记录 | profile 对齐情况 | 可用事实 | 缺失事实 |
|---|---|---|---|
| [Task037c MPI8 compact](../../../benchmarks/cases/102_hybrid_iterative_robustness/records/task037c_mpi8_three_way_qualification_v1.json) | degree=6，h=10 nm，wavelength=13.5 nm，s，grazing=1°，phi=0° 对齐 | direct M120/M160 的 scalar `R/T/A/A_volume`、residual、记录 SHA；`verified_clean=true`，source SHA=`f2d7719b6253251a06e8cd8388fd443bbf47d443` | compact 没有 Task038 的 input/model SHA，canonical identity 未由 compact 证明；`arrays_included=false`；无 E/H、near-field、12 个 significant identity 的 power 数组和 12 个对应 complex boundary-amplitude 数组；原始 direct 路径不在当前 checkout |
| [Task037c MPI1 compact](../../../benchmarks/cases/102_hybrid_iterative_robustness/records/task037c_mpi1_identity_and_resource_v1.json) | degree=6，h=10 nm，wavelength=13.5 nm，s，grazing=1°，phi=0° | MPI1 identity/resource 交叉记录 | 同样没有 field/channel arrays，不能替代完整 authority |
| [T6 input-driven compact](../../../docs/task038_input_driven_configuration/outcomes/records/t6_hybrid_iterative_mpi8_equivalence_v1.json) | 1° physical profile 的 hybrid 交叉证据 | 输入/几何/方法身份线索 | 不是当前 same-mesh fullspace direct authority，不能提供缺失数组 |
| `task37_direct_authority_v2.json` | **不匹配**：theta=80°、grazing=10° | 仅作历史边界记录 | 不得冒充本 Task038 的 1° authority |

Task037c MPI8 compact 的 SHA256 是 `eec638b833679937252982ae394012e88e679c058cccc0c4f6c091d33754fbd8`。其 direct scalar 两次结果如下；冻结比较容差为 `1e-5`，不是本审计自创的容差：

| scalar | direct M120 | direct M160 | 绝对差 |
|---|---:|---:|---:|
| R | 0.3656257891787136 | 0.3656257891784510 | 2.625677453238495e-13 |
| T | 0.01299063241062439 | 0.012990632410629291 | 4.90059381963448e-15 |
| A | 0.6213835784106620 | 0.6213835784109197 | 2.5768276401549883e-13 |
| A_volume | 0.6213835795387049 | 0.6213835795287246 | 9.980349879867845e-12 |

这只形成 `scalar_only` packet；它不能使 E/H、near-field 或 12+12 field/channel Gate 通过。

## 冻结的 Task038 结果入口

| 结果 | 记录入口 |
|---|---|
| C1 random | [record](records/same_mesh_hcurl_pmg_p6_positive_exact1_random_v4.json) |
| C1 gradient | [record](records/same_mesh_hcurl_pmg_p6_positive_exact1_gradient_v4.json) |
| C1 curl | [record](records/same_mesh_hcurl_pmg_p6_positive_exact1_curl_v4.json) |
| C1 checkerboard | [record](records/same_mesh_hcurl_pmg_p6_positive_exact1_checkerboard_v4.json) |
| P0 watchdog | [tracked watchdog](records/same_mesh_hcurl_pmg_p0_physical_v1_watchdog.json) |
| P0 paths marker | [tracked marker](records/same_mesh_hcurl_pmg_p0_physical_v1_paths_ready.json) |

P0 hard stop 的差额为 `24,108,032 B`，约为 `1.2054%`；“只超一点”仍是严格失败。其 root 没有 bundle/setup、worker record、checkpoint、residual、recovery 或 official physics 输出。

## 本地 artifact 检查

| 检查对象 | 只读观察 |
|---|---|
| Task039 | 当前仓库没有本地 Task039 文件或 artifact 路径 |
| Task037c direct raw | compact 指向的 `/home/Projects/MyFEniCS/...` 原始路径在当前 checkout 不存在 |
| Task038 p6/h10 positive cache | 已有 exact-input C1 artifact；可见 p6/p3/p1 的四个 positive cache module，作为历史运行事实保留，不重新使用为新 PDE authority |
| Task038 P0 root | 只有 paths marker、watchdog/cache 现场；不创建假的 worker record/checker |

因此后续 physical comparison 必须保持 fail-closed：现有 scalar direct packet 可用于有限的 `R/T/A/A_volume` 交叉检查，但完整 E/H、near-field 及同一 12 个 significant diffraction identities 的 12 power + 12 complex boundary-amplitude Gate 仍需独立 raw authority。

## V14 J5 更新

J0 的 `AUTHORITY_ARRAYS_MISSING` 结论没有改变。J5 v3 在用户控制停止前没有进入 recovery 或 official export，因此没有新增可冒充 direct authority 的 E/H、near-field 或 12+12 raw arrays。Task037c compact 仍只是物理参数对齐、canonical identity 未由 compact 证明的 scalar packet；旧 10° authority 仍不匹配，不能用于当前 1° Task038 physical comparison。
