# 快速开始索引

本目录只回答五个问题：环境怎样准备、在 `src/main.py` 选哪个 preset、等价命令是什么、结果在哪里、失败先看什么。公式推导见 [`../theory/README.md`](../theory/README.md)，函数和数据流见 [`../reference/code_walkthrough.md`](../reference/code_walkthrough.md)，可复核数值见 [`../../benchmarks/cases/README.md`](../../benchmarks/cases/README.md)。

## 最短路线

1. 阅读 [`00_environment_and_pycharm.md`](00_environment_and_pycharm.md)，确认 Docker 复杂数环境。
2. 打开 `src/main.py`，只修改 `ACTIVE_PYCHARM_PRESET`。
3. 第一次保持默认 `3d_stage1_airbox_smoke`，在 PyCharm 运行 `main.py`。
4. 在 `results/` 最新时间戳目录查看 `run_summary.json`、`solver_log.txt` 和 ParaView 文件。
5. 需要正式迭代结果时使用 [`40_3d_workstation_iterative.md`](40_3d_workstation_iterative.md) 的 MPI4 外部命令，普通单进程 `main.py` 不会偷偷启动它。

## 按功能阅读

| 功能 | 文档 | 推荐 preset | 当前定位 |
|---|---|---|---|
| 参数总表 | [`01_main_py_parameter_map.md`](01_main_py_parameter_map.md) | 全部 | 入口契约 |
| 输出与 ParaView | [`02_results_and_paraview.md`](02_results_and_paraview.md) | 全部 | 通用 |
| 2D TM PML | [`10_2d_pml_floquet.md`](10_2d_pml_floquet.md) | `2d_tm_pml_floquet_smoke` | experimental path smoke |
| 2D TM DtN | [`11_2d_dtn_floquet.md`](11_2d_dtn_floquet.md) | `2d_tm_dtn_auxiliary_smoke` | auxiliary 推荐、explicit 交叉核验 |
| 2D TE/TM/复材料 | [`12_2d_te_tm_and_complex_material.md`](12_2d_te_tm_and_complex_material.md) | `2d_complex_absorption` | 已支持 |
| 2D RTA 方法 | [`13_2d_diffraction_and_rta_methods.md`](13_2d_diffraction_and_rta_methods.md) | 2D DtN | official 与 diagnostic 分开 |
| 3D Stage 1 | [`20_3d_stage1_airbox.md`](20_3d_stage1_airbox.md) | `3d_stage1_airbox_smoke` | 默认安全入口 |
| 3D Stage 2A | [`21_3d_stage2a_floquet.md`](21_3d_stage2a_floquet.md) | `3d_stage2a_floquet_smoke` | test-backed Floquet smoke |
| 3D Stage 2B | [`22_3d_stage2b_pml.md`](22_3d_stage2b_pml.md) | `3d_stage2b_pml_smoke` | experimental/not accuracy qualified |
| 3D Stage 2C | [`23_3d_stage2c_fresnel.md`](23_3d_stage2c_fresnel.md) | `3d_stage2c_fresnel_smoke` | experimental/not accuracy qualified |
| 3D Stage 4A | [`30_3d_stage4a_flat_layer.md`](30_3d_stage4a_flat_layer.md) | `3d_stage4a_flat_layer_direct` | 平层功率闭合 |
| 3D Stage 4B direct | [`31_3d_stage4b_grating_direct.md`](31_3d_stage4b_grating_direct.md) | `3d_stage4b_demo_*` / `3d_target_grating_*` | demo 与 canonical target 严格分开 |
| OOC 与 BLR | [`32_3d_direct_ooc_blr.md`](32_3d_direct_ooc_blr.md) | `3d_stage4b_demo_mumps_*` | experimental direct fallback |
| MPI4 迭代生产档 | [`40_3d_workstation_iterative.md`](40_3d_workstation_iterative.md) | 无 main preset | h=5/3/2 已限定验证 |
| 扫描和新案例 | [`50_parameter_scans_and_new_cases.md`](50_parameter_scans_and_new_cases.md) | 从最近 preset 复制 | 新结果必须降级为未验证 |
| Task33 高阶 Floquet / Hybrid h-p / 自适应 | [`60_task033_high_order_hybrid_hp.md`](60_task033_high_order_hybrid_hp.md) | 无 main preset | p3/h5 Hybrid Phase C 组件通过；full3D memory-gated；自适应延期；完整 formal closure 未完成 |

## 旧文档迁移说明

旧指南没有删除，因为其中保存了开发过程和更长的诊断背景。`pycharm_main_run_guide.md`、`config_driven_run_guide.md` 的现行入口已由本索引和 `01_main_py_parameter_map.md` 取代；Stage 1/2/4 与 2D EUV 旧指南作为“历史长文”保留。若旧文档的 preset 名或组合命令与本索引冲突，以 `src/main.py`、runner 的 `argparse` 和本索引为准。

## 状态词

| 状态 | 含义 |
|---|---|
| qualified / 已限定验证 | 只对记录中的几何、材料、次数、MPI 数和容差成立 |
| validated / 已验证 | 通过对应功能测试，但不能外推到任意网格和材料 |
| experimental / 实验 | 可运行入口，尚无足够 benchmark 证明 |
| diagnostic / 诊断 | 用于交叉检查，不是正式物理量来源 |
| legacy / 历史 | 为追溯保留，不在当前调用链 |
