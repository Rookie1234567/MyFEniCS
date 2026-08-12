# Task38 结项摘要：input-driven configuration

本摘要把用户可复现的 `.dat` 流程、实现阶段、正式数值对照和未运行边界放在同一处。`measured` 表示运行中直接记录，`derived` 表示由已核验记录计算，`not_run` 表示没有启动，`diagnostic` 表示用于解释而不计入正式 Gate。

## 最终状态

| 项目 | 结果 | 身份/边界 |
|---|---|---|
| 用户入口 | `python scripts/run_case.py input/path/to/case.dat` | method、solver、MPI、M 全部来自一个 `.dat` |
| public schema | 5 个 identity + 9 个固定 section，100 个字段 | README 与 schema coverage 已通过 |
| migrated preset | 11 个 | 6 个 2D、5 个 3D，均有 dat；T7 静态迁移证明保留 |
| retained preset | 6 个 | research/history replay，仍由旧内部 factory/CLI 支持 |
| 删除旧重复层 | 5 个不可达 3D 副本 | current adapter 仍调用现有 runner/solver |
| ordinary 数值算法 | 未改变 | 未修改 solver 数学、ordinary default 或 retained replay |
| full repository pytest | `1119 passed, 48 skipped, 0 failed in 1514.73s` | environment-corrected final full Gate pass；首轮 ABI identity diagnostic 与 targeted identity verification evidence 另列 |

## 阶段完成矩阵

| 阶段 | 完成内容 | 证据/结果 |
|---|---|---|
| T0 | inherited master、入口、preset、legacy inventory | 两份审计文档；未改算法 |
| T1 | 显式 dat schema、README、四个模板、100-key coverage | `test_260` 及静态 Gate 通过 |
| T2 | 单次 byte-exact loader、strict validation、immutable specification、resolved/hash | `test_261`；纯 Python，无 MPI/PDE |
| T3 | execution plan、worker contract、launcher/provenance、public script | `test_262`/`263`；contract-only MPI1/2/4 smoke 通过 |
| T4 | Full3D direct dat adapter 与共享 3D mapping | T4 MPI1 old/new formal contract pass；canonical export 为 `not_run_by_capability` |
| T5 | Hybrid direct dat adapter、legacy augmented seam | MPI4 formal task contract pass；exact NNZ 为 diagnostic non-invariant |
| T6 | Hybrid iterative accepted profile、MPI8 dat adapter | MPI8 formal pass；第一次仅 adapter source-after 字段错误，已保留负证据并修复 |
| T7 | 11 个 ordinary preset 的静态 dat 迁移与 2D/Stage1 代表性 PDE | 4 次轻量 old/new 对照通过；6 retained 未迁移 |
| T8 | `src.main` 薄 alias、benchmark caller、current guidance | 11 migrated 只走 dat；6 retained replay 不变 |
| T9 | 删除 5 个不可达旧模块、收敛当前教程 | 295 passed、2 skipped；无 formal PDE/MPI/full pytest |
| T10 | 结项文档与最终全仓 Gate | docs Gate 与 environment-corrected final full Gate pass |

## 用户流程与 provenance

1. 用户准备一个完整 `.dat`；不在命令行追加物理、solver 或 MPI override。
2. `load_dat_input` 只读原始 bytes 一次，解析并保存 `input_sha256`。
3. strict validation 生成不可变 `RunSpecification`，共享 mapping 生成内部 runtime config；`physical_model_sha256` 只覆盖 geometry/materials/incidence/discretization/boundary 的 canonical JSON。
4. launcher 生成唯一 run directory，保存 `input_original.dat`、`resolved_config.json`、`run_manifest.json`、两类 hash、`source_sha.txt` 与 parent `run_summary.json`；数值 solver 的 summary 位于 `numerical_output/`。
5. worker 只消费已验证的 resolved/manifest contract；数值失败、资源终止和 source/identity 不匹配均 fail closed。

建议结果目录为：

```text
results/<model_id>/<run_id>__<method>__mpi<N>__M<M-or-na>/<timestamp>/
```

## 正式数值等价与边界

| 对照 | source SHA | residual | 共同物理结果 | 结构/功率结果 | 资源（口径） | 判定 |
|---|---|---:|---|---|---|---|
| T4 Full3D direct MPI1 | `f4f2619aaef234fc12fa4db7e6a6075b383b3205` | `5.520787756471226e-14`（两侧） | cfg 除 `case_name` 外相同；DoF 802；rows/cols 882 | R=`0.9997827084780738`；T=`0.00010870177442776488`；A_volume=`0.00010858974749584228`；A_balance=`0.00010858974749841241`（derived: `1-R-T`）；measured closure=`-2.55351295663786e-15`；全部差值 0 | legacy 218.87109375 MiB 单 rank historical；dat 236.953125 MiB process-tree；不可互比 | formal contract pass |
| T5 Hybrid direct MPI4 | `535c285e8d565b6c79e99cad9a2c899a5ff1658a` | legacy `5.014855373361551e-12`；dat `3.891075584849558e-12` | `standard_full`；M160/candidate320；QEP reduced shape720；matrix shape、orders80 相同 | hash-pinned dat measured R=`0.08902106910587838`；T=`0.4425867427441033`；A_balance=`0.4683921881500183`；A_volume=`0.46839218817098305`；energy_closure_error=`2.096478546320668e-11`；legacy/new delta 分别 `1.5792922525292852e-14`/`1.3433698597964394e-14`/`2.3314683517128287e-15`/`2.609024107869118e-15`/`2.220446049250313e-16`；power `1.569577801063815e-14`；complex amplitude `6.27142620593212e-14` | dat process-tree 1765.50390625 MiB，swap 0；legacy process-tree 未测 | formal task contract pass；exact NNZ 为 diagnostic |
| T6 Hybrid iterative MPI8 | `870a3f9ff1097256ab6ef4b8f50d83a05a010473` | `3.061632638614486e-09` reported；global `3.061639832972372e-09`；bottom `4.880059476090313e-09`；top `2.4282287434315664e-09`；modal `3.106265787799924e-15` | 1771 iterations；exact operator；M120/candidate240；fixed ILU0 + dynamic DtN Woodbury two-pass；80 orders | R=`0.3656257867289616`；T=`0.012990632358457535`；A=`0.6213835809125808`；A_volume=`0.6213835766254876`；closure=`-4.287093235966211e-09`；traction bottom/top=`4.880059476090313e-09`/`2.4282287434315664e-09` | 6585.01953125 MiB simultaneous process-tree，swap 0，998.13832 s；preferred 6144 MiB 为 resource preference，未冒充硬失败 | formal pass；preferred RSS 超出仅作边界记录 |
| T7 2D TM PML old/new | `f86a7e42dc2c44d36c8e5ab6dfa1d9bb8ef8ed42` | `4.595181492041868e-15`（两侧） | mesh400；DoF633；5 orders；R=`0.02561938273503437`；T=`0.8857932785737199`；R+T=`0.9114126613087543`；A_balance=`0.08858733869124569` | 所有共同 power/order 数值差 0 | dat 263.546875 MiB process-tree；legacy RSS not measured | formal light PDE equivalence pass |
| T7 Stage1 old/new | `f86a7e42dc2c44d36c8e5ab6dfa1d9bb8ef8ed42` | `1.0869658196017029e-16`（两侧） | mesh48；DoF/rows98；NNZ1106；solution norm=`35.35501465073796`；R/T/A not applicable | 最大共享数值差 `8.271806125530277e-25`（`mean_poynting_W_per_m2[1]` 舍入） | dat 221.078125 MiB process-tree；legacy 214.02734375 MiB solver-reported historical | formal light PDE equivalence pass |

T5 hash-pinned new summary 已验证：`results/.../20260812T043041.648724Z/numerical_output/run_summary.json` 的 SHA256 为 `2dadaf0554cdaae64a88e90d7d7146b34897f1ec075c25dc2a5c5f1d4ed22505`。因此统一表中的绝对 T5 dat 值来自该绑定 raw；legacy 绝对值未保存在 compact record，未猜测，必要处以 delta/`not_carried` 表示。

Task §17.4 的 MPI1 条件由 inherited accepted MPI1 record 满足：`task037c_mpi1_identity_and_resource_v1.json`，SHA256 `a38d3c280cb655481f63e79baf658c5353a2e86823e46fcefb54a148b2baec5f`，source `f2d7719...`，1472 iterations、1751.3203125 MiB、1903.92164 s。它不是当前 Task38 same-SHA formal comparator，也不是本轮重跑；当前 Task38 MPI1 dat 只做 validate/dry-run。T6 MPI8 才是 Task38 fresh formal run。

T4/T5 canonical vector/selected field comparison 是 `not_run_by_capability`，不是遗漏的数值 pass。T6 online lifecycle/operator/release 通过，但没有把不同 source SHA 的历史 compact record 当作 formal same-SHA array comparison。T5 exact monolithic NNZ 2,011,205 对 2,011,063，delta 142、相对 `7.060443863256108e-05`，因近简并 QEP 基底与 `1e-13` 显著性筛选而归为 `diagnostic_non_invariant`；不修改 solver cutoff 或阈值凑相等。

## 迁移、保留与删除

11 个 migrated dat 与 6 个 retained preset 的逐项 SHA、inactive exclusion、4 次 T7 PDE 证据见 [`preset_migration.md`](preset_migration.md)。T8/T9 的删除、调用图与保留依赖见 [`legacy_cleanup.md`](legacy_cleanup.md)。5 个 removed 文件是不可达旧 3D 副本；`run_cases.py`、`run_3d_cases.py`、Task37 authority、port-order-count、历史 tests/records 仍保留。

## T10 full pytest 与环境诊断

| 阶段 | 命令/环境 | 结果 | 解释 |
|---|---|---|---|
| 首轮 full | `python -m pytest -q`，Task38 worktree 无 `.venv` identity 接线 | `1118 passed, 48 skipped, 1 failed in 1352.60s` | 既有 `test_73_task034_hardening.py::Task034HardeningTests::test_dolfinx_mpc_probe_requires_project_complex_abi` diagnostic failure；原始 excerpt 保留在 `test_summary.md` |
| targeted | 同一 de2e code/config parent，临时 `.venv` symlink 指向 canonical venv；指定 test_73 node | `1 passed in 0.98s` | `_dolfinx_mpc_abi_probe` 9/9 true；这是环境 identity 验证，不是代码修复 |
| final full | 同一 de2e code/config parent，仅纠正 worktree `.venv` identity，`python -m pytest -q` | `1119 passed, 48 skipped, 0 failed in 1514.73s (0:25:14)` | final environment-corrected zero-failure Gate；临时 symlink/excludes 已清理 |

两次 full 使用同一 code/config parent `de2e1880fa90a442996ada58ea321c774752a5ca`；第二次只修正隔离 worktree 对共享 qualified venv 的 identity 接线，没有修改 Python、测试、阈值或 ordinary default。首轮 failure 仍是 diagnostic history，不被 final pass 删除或改写。
