# `main.py` 参数地图：知道自己改了什么

## 1. 功能与物理图景

`src/main.py` 是 PyCharm facade，不是第二套求解器。它把一个命名 preset 翻译成 `run_cases` 或 `run_3d_cases` 的真实 CLI 参数。物理方程、网格、边界和求解仍在 `src/` 对应模块中完成。

## 2. 当前能力状态

```text
2D presets = 6
3D presets = 11
ordinary default = 3d_stage1_airbox_smoke
iterative preset = 无；MPI4 使用独立 benchmark 配置
```

## 3. 运行前提

先完成 [`00_environment_and_pycharm.md`](00_environment_and_pycharm.md)，确认 complex PETSc。用以下命令查看每个 preset 的几何、p/h、资源和证据身份：

```text
python src/main.py --list-presets --verbose
```

## 4. PyCharm 选择位置

只改顶部这一行即可选择已有功能：

```python
ACTIVE_PYCHARM_PRESET = "2d_complex_absorption"
```

不要同时寻找旧的 `SIMULATION_DIMENSION`、`stage2_all` 或 `stage4_all`；它们不是当前入口。

## 5. `main.py` 中的实际参数块

| 配置类 | 用途 |
|---|---|
| `Inputs2D` | 2D TM/TE、PML/Robin/DtN |
| `Stage1AirboxInputs3D` | Stage1 |
| `Stage2NoGratingInputs3D` | Stage2A/2B/2C |
| `Stage4GratingInputs3D` | Stage4A/4B direct |
| `PresetInfo` | 几何、离散、资源和证据身份 |

冻结 dataclass 防止运行时意外改值；源码中使用 `replace(base, field=value)` 产生新配置。

## 6. 完整自定义参数示例

```python
MY_2D = replace(
    PRESETS_2D["2d_tm_dtn_auxiliary_smoke"],
    period_x=120.0,
    lambda0=13.5,
    n_substrate=0.999 + 0.002j,
    mesh_target_size=3.0,
)
PRESETS_2D["2d_my_lossy_cell"] = MY_2D
PRESET_INFO["2d_my_lossy_cell"] = PresetInfo(
    physical_geometry="120 nm user cell",
    discretization="TM N1curl p=2, h=3 nm",
    resource_class="unmeasured",
    evidence_status="user_experimental",
    purpose="User-defined parameter study",
)
```

## 7. 2D 参数含义

| 参数 | 单位 | 合法/典型值 | 改动影响 |
|---|---|---|---|
| `period_x` | nm | `>0` | Floquet 相位和衍射阶 |
| `air_height`、`substrate_thickness` | nm | `>0` | port 面位置与吸收传播距离 |
| `grating_width/height` | nm | 落在周期域内 | 材料标签和几何 |
| `lambda0` | nm | `>0` | `k0=2pi/lambda0` |
| `incident_angle_deg` | deg | 避开未处理 Rayleigh 点 | `kx` 与传播阶 |
| `n_*` | 无量纲复数 | `a+bj` | `epsilon_r=n^2` |
| `nedelec_degree` | 无量纲 | TM 常用 1/2 | DoF 和内存 |
| `mesh_target_size` | nm | `>0` | 精度与资源，不保证自动收敛 |

在 `exp(-i omega t)` 约定下，本项目使用正 `Im(epsilon_r)` 表示吸收；外部数据库若使用相反时间约定，必须先转换符号。

## 8. 3D 参数含义

| 参数 | 物理对象 | 资格边界 |
|---|---|---|
| `period_x/y` | 双周期尺寸 | 改后不再是 target record |
| `air_height/substrate_thickness` | z 向分层 | 影响端口和吸收 |
| `grating_width_x/y/height` | 3D block | 必须落在 cell 内 |
| `incident_theta/phi_deg` | 从 `-z` 的倾角/方位角 | target 为 80/0 |
| `polarization_kind` | `s`/`p`/`custom` | target 为 `s` |
| `stage4_boundary_model` | `dtn_port`/诊断 PML/Robin | production target 使用 DtN |
| `stage4_dtn_order_policy` | auto/zero/manual | target 使用 auto propagating |
| `petsc_direct_solver_profile` | default/OOC/BLR | BLR 仍是 direct |

## 9. Demo 与 target 的区别

| 名称前缀 | 物理身份 |
|---|---|
| `3d_stage4b_demo_*` | 100 x 100 x 100 nm、normal-incidence 演示，不对应 Case021 |
| `3d_target_grating_*` | 50 x 25 x 140 nm、80° s 偏振 canonical target |

target preset 的物理参数来自 `src.common.config_3d::target_stage4_config`，不是第二份手抄常数。

## 10. CLI 等价命令

```text
python src/main.py --preset 2d_complex_absorption
python src/main.py --preset 3d_target_grating_direct_h5
```

命令末尾可追加真实 runner 参数；后出现的同名参数覆盖 preset 值，但这会形成用户变体，不应覆盖 canonical record。

## 11. 真实调用链

```text
PRESETS_2D/PRESETS_3D
-> preset_cli_args
-> _pycharm_args_2d/_pycharm_args_3d
-> run_cases::main / run_3d_cases::main
-> SimulationConfig / SimulationConfig3D
```

`test_27_main_preset_contract.py` 把全部 preset 参数交给真实 parser，防止 facade 与 runner 漂移。

## 12. 输出与关键字段

默认 `results/`；benchmark 使用显式 `benchmarks/artifacts/`。检查 `run_summary.json` 的 `config`，确认实际解析值，而不是只相信源文件注释。

## 13. 成功 Gate

```text
preset 名称唯一
PRESET_INFO 完整
runner parser 接受全部参数
demo/target 名称不混淆
ordinary default 仍为轻量 direct
```

## 14. 常见错误

| 错误 | 原因 |
|---|---|
| 改了未激活 dataclass 但结果不变 | `ACTIVE_PYCHARM_PRESET` 指向别处 |
| 把 `n` 当成 `epsilon` 输入 | 程序还会再平方 |
| 用 demo 与 target record 比较 | 两者几何和入射不同 |
| 参数扫描写到 canonical record | `--record` 路径使用错误 |

## 15. 如何进入自己的案例

先从最近的 smoke 复制、改名、放到新的 artifact root；跑 residual、能量和网格收敛后，再考虑建立新的 benchmark。不要修改 Case021/031 的 `config.json` 来容纳个人扫描。

## 16. 链接

- 入口代码：[`../reference/code_walkthrough/01_main_and_runner_dispatch.md`](../reference/code_walkthrough/01_main_and_runner_dispatch.md)
- 物理符号：[`../theory/README.md`](../theory/README.md)
- Target direct：[`31_3d_stage4b_grating_direct.md`](31_3d_stage4b_grating_direct.md)
- Benchmark 021：[`../../benchmarks/cases/021_3d_stage4b_direct/README.md`](../../benchmarks/cases/021_3d_stage4b_direct/README.md)
