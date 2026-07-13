# 3D Stage4B 光栅 direct 教程：先分清 demo 与 target

## 1. 功能与物理图景

Stage4B 在双周期 3D cell 中加入 rectangular block grating、complex Si、oblique incidence、auxiliary DtN port 和 volume absorption。本页分别说明演示几何与 Task27/28 canonical target，禁止混为一谈。

## 2. 当前能力状态

| 路径 | 物理身份 | 证据 |
|---|---|---|
| `3d_stage4b_demo_*` | 100 x 100 x 100 nm normal demo | 示例/实验 |
| `3d_target_grating_direct_h5` | 50 x 25 x 140 nm target, h5 | canonical Case021 |
| `3d_target_grating_direct_h3` | 同一 target, h3 | canonical，约 8.2 GB |
| target h2 direct | reviewed reference | 约 20.53 GB，本机不重跑 |

## 3. 运行前提

使用 qualified complex image。先运行 Stage4A。target h3 前确认可用内存；不要在 14 GB 配额下尝试 h2 direct。

## 4. PyCharm presets

```python
ACTIVE_PYCHARM_PRESET = "3d_stage4b_demo_direct_h5"
ACTIVE_PYCHARM_PRESET = "3d_target_grating_direct_h5"
ACTIVE_PYCHARM_PRESET = "3d_target_grating_direct_h3"
```

初学者先 demo h5；复现 Benchmark 021 必须使用 `3d_target_*`。

## 5. `main.py` 实际修改位置

demo 来自 `STAGE4_GRATING_3D`。target 来自唯一物理配置工厂：

```text
src.common.config_3d::target_stage4_config
-> Stage4GratingInputs3D::from_simulation_config
-> matrix_diagnostics_assemble_only=False for direct solve
```

因此 target preset 与 workstation config 共享物理值，不手抄第二份常数。

## 6. Target 完整参数块

| 参数 | 值 |
|---|---|
| domain | 50 x 25 x 140 nm |
| air/substrate | 130/10 nm |
| grating | 17 x 25 x 120 nm |
| wavelength | 13.5 nm |
| incidence | theta=80° from z，phi=0° |
| polarization | s |
| material | `0.999002304859+0.00182649365j` Si |
| FE | N1curl p=2 |
| boundary | auxiliary DtN, auto propagating orders |

## 7. 参数含义与资源

| 参数 | 作用 | 资源/资格 |
|---|---|---|
| `mesh_target_size=5` | coarse target | direct RSS 约 2.293 GB |
| `mesh_target_size=3` | finer target | direct RSS 约 8.182 GB |
| `mesh_target_size=2` | reviewed only direct | 约 20.533 GB |
| `nedelec_degree=2` | production p | 改 p 后不继承 record |
| `stage4_dtn_order_policy=auto_propagating` | 端口阶次 | target 固定 |
| `petsc_direct_solver_profile=default` | MUMPS LU | ordinary baseline |

## 8. Qualification 边界

canonical 只覆盖固定 target 的 h5/h3 direct 及历史 h2 reference。demo、其他角度/材料/几何或 local refinement 都是新案例。现有 h5/h3/h2 数值不是本轮 V3 重算。

## 9. CLI 与 PyCharm MPI4 等价配置

普通 serial：

```text
python src/main.py --preset 3d_target_grating_direct_h5
```

复现 canonical 物理问题和 MPI rank：

```text
mpiexec -n 4 python src/main.py --preset 3d_target_grating_direct_h5 \
  --results-root benchmarks/artifacts/cases/021/h5
```

Case 脚本：`H_VALUE=5 sh benchmarks/cases/021_3d_stage4b_direct/run.sh`。

## 10. 真实调用链

```text
main::preset_cli_args
-> run_3d_cases::main
-> config_3d::target_stage4_config
-> solve_maxwell_3d_stage_4b_block_grating::run_stage4b_block_grating_3d_case
-> dtn_port_3d::solve_stage4_dtn_port_total_field
-> common_3d_solve direct MUMPS
-> common_3d_postprocess official RTA
```

## 11. 输出与 record

完整场写 `benchmarks/artifacts/cases/021/`。Case021 `records/*.json` 是 SHA-256 pinned reference，指向顶层 canonical lightweight records，避免复制后漂移。

## 12. ParaView

MPI 打开 PVD，Threshold grating tag，使用 x-z/y-z Slice 查看 block 内外场。固定色标比较 h5/h3；几何不同的 demo 不应放在同一收敛图。

## 13. 成功 Gate

```text
physical_model 与 target factory 完全一致
direct residual 通过
official R/T/A 非负且 closure <= 1e-6
RSS 在计划范围
record/artifact provenance 一致
```

## 14. 常见错误

| 现象 | 原因 |
|---|---|
| h5 结果与 record 完全不同 | 实际运行 demo preset |
| PyCharm 一点就内存高 | 选择了 target h3 |
| 运行只 assemble 不 solve | 使用 workstation config 未关闭 assemble-only |
| h2 OOM | direct reference 超过 14 GB |

## 15. 改成自己的 grating

从 demo 复制建立新 preset；若必须从 target 改，改名并把 record 写到新 artifact 路径。至少做 residual、能量和多网格检查，不覆盖 Case021。

## 16. 链接

- Direct 理论：[`../theory/direct_solvers_and_factorization.md`](../theory/direct_solvers_and_factorization.md)
- 代码：[`../reference/code_walkthrough/30_direct_solver_profiles.md`](../reference/code_walkthrough/30_direct_solver_profiles.md)
- Case021：[`../../benchmarks/cases/021_3d_stage4b_direct/README.md`](../../benchmarks/cases/021_3d_stage4b_direct/README.md)
