# 2026-06-29 更新：3D 求解器按案例拆分重构验证报告

本轮已把旧的 3D 大求解流程拆成按案例入口，并完成重构后小规模 baseline 对比。结论：

```text
单元测试：48 个测试通过，8 个按原设置跳过。
新入口 baseline：Stage 1、2A、2B、2C、4A、4B 全部跑通。
关键指标：与重构前 baseline 一致。
```

注意：本报告只证明“重构没有改变旧行为”。Stage 2C 中 `R+T > 1` 的历史问题仍然按原样保留，没有在本轮重构中修改物理模型。

## 新入口

以后 3D 单案例运行入口为：

```bash
python3 -m src.runners.run_3d_cases --stage-case stage1_airbox --case normal
```

允许的 `stage_case` 只有：

```text
stage1_airbox
floquet_airbox
pml_airbox
fresnel_interface
stage4_flat_layer_sanity
stage4_block_grating
```

允许的 `--case` 只有：

```text
normal
oblique
```

旧的 `both`、`stage2_all`、`stage4_all` 不再作为 3D runner 内部功能；批量扫描以后用外部脚本显式循环。

## 新旧对比表

| 案例 | 旧结果目录 | 新结果目录 | cells/dofs | 关键指标对比 |
|---|---|---|---:|---|
| Stage 1 normal | `3D_stage1_airbox_normal_p1_h100p0_20260629_125123` | `3D_stage1_airbox_normal_p1_h100p0_20260629_131724` | 1620 / 2297 | `E_err=0.7886975612797782`, `H_err=0.9538208035648067` |
| Stage 1 oblique | `3D_stage1_airbox_oblique_p1_h100p0_20260629_125127` | `3D_stage1_airbox_oblique_p1_h100p0_20260629_131729` | 1620 / 2297 | `E_err=0.5166082271067061`, `H_err=0.6429011336345416` |
| 2A Floquet oblique | `3D_floquet_airbox_oblique_p1_h100p0_20260629_125130` | `3D_floquet_airbox_oblique_p1_h100p0_20260629_131732` | 270 / 1088 | `E_err=0.11670409541016687`, `floquet_x=0` |
| 2B PML theta30 | `3D_pml_airbox_oblique_p1_h100p0_20260629_125135` | `3D_pml_airbox_oblique_p1_h100p0_20260629_131956` | 420 / 1653 | `E_err=0.16176383107786782`, `pml_proxy=7.50739387701947e-18` |
| 2C Fresnel s theta30 | `3D_fresnel_interface_oblique_p1_h100p0_20260629_125328` | `3D_fresnel_interface_oblique_p1_h100p0_20260629_132147` | 420 / 1653 | `R=0.054607072317658`, `T=1.1283458388371244`, `R+T=1.1829529111547823` |
| 2C Fresnel p theta30 | `3D_fresnel_interface_oblique_p1_h100p0_20260629_125516` | `3D_fresnel_interface_oblique_p1_h100p0_20260629_132335` | 420 / 1653 | `R=0.05667056384896965`, `T=1.1580495669471271`, `R+T=1.2147201307960969` |
| 4A flat layer | `3D_stage4_flat_layer_sanity_normal_p1_h10p0_20260629_125537` | `3D_stage4_flat_layer_sanity_normal_p1_h10p0_20260629_132356` | 1500 / 5335 | `R=0.9999999999954342`, `T=4.55937646173546e-12`, `R+T=0.9999999999999936` |
| 4B block grating | `3D_stage4_block_grating_normal_p1_h10p0_20260629_125545` | `3D_stage4_block_grating_normal_p1_h10p0_20260629_132404` | 1815 / 6384 | `R=0.9999999999969063`, `T=3.0878347615628622e-12`, `R+T=0.9999999999999941` |

## 已执行检查

```bash
python3 -m compileall -q src
python3 -m unittest discover -s src/test -p "test_*.py"
```

Docker 单元测试结果：

```text
Ran 48 tests in 1.931s
OK (skipped=8)
```

## 新代码结构

公共工具层：

```text
src/solvers/common_3d_utils.py        计时、日志、summary/json 写出
src/solvers/common_3d_solve.py        Nedelec 空间、直接求解器、矩阵/残差诊断
src/solvers/common_3d_fields.py       平面波、Fresnel 背景、场叠加与采样
src/solvers/common_3d_forms.py        curl-curl 弱式、PML 张量弱式、RHS source norm
src/solvers/common_3d_postprocess.py  Floquet/PML/Fresnel/Stage-4 指标
src/solvers/common_3d_case_flow.py    不按 stage 分流的共享 FEM 流程积木
```

按案例求解入口：

```text
src/solvers/solve_maxwell_3d_stage_1_airbox.py
src/solvers/solve_maxwell_3d_stage_2a_floquet_airbox.py
src/solvers/solve_maxwell_3d_stage_2b_pml_airbox.py
src/solvers/solve_maxwell_3d_stage_2c_fresnel_interface.py
src/solvers/solve_maxwell_3d_stage_4a_flat_layer_sanity.py
src/solvers/solve_maxwell_3d_stage_4b_block_grating.py
```

历史文件保留为：

```text
src/solvers/solve_maxwell_3d_common_old.py
src/solvers/solve_airbox_maxwell_3d_old.py
src/solvers/solve_maxwell_3d_stage_2_no_grating_old.py
src/solvers/solve_maxwell_3d_stage_4_grating_old.py
src/runners/run_3d_airbox_old.py
```
