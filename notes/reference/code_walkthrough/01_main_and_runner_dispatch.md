# `main.py` 与 runner 分发

本文沿一个显式 `.dat` 输入或保留的 research preset 入口走到 2D/3D runner。入口层只负责选择、校验和分发，不装配有限元矩阵，也不改变求解器默认值。

## 1. 文件与公开入口

| 文件 | 关键入口 | 责任 |
|---|---|---|
| `scripts/run_case.py` | `main()` | 普通用户的 `.dat`、validate-only 和 dry-run 入口 |
| `src/main.py` | `main()`、`preset_cli_args(name)` | 迁移 dat 的兼容 alias、保留 preset 清单和 legacy CLI facade |
| `src/runners/run_cases.py` | `main(argv=None)` | 2D 参数解析与 TM/TE、scattered/port 分发 |
| `src/runners/run_3d_cases.py` | `main(argv=None)` | 3D stage 参数解析、配置构造与输出目录 |
| `src/common/config.py` | `SimulationConfig` | 2D resolved configuration 与派生物理量 |
| `src/common/config_3d.py` | `SimulationConfig3D`、`target_stage4_config(...)` | 3D resolved configuration 和唯一 target 工厂 |

`src/main.py` 无参数时只显示 usage/deprecation 并非零退出；它不再选择隐式 ACTIVE preset。普通输入必须显式传给 `scripts/run_case.py`；T8 保留的六个 research/history preset 仍可通过 `--preset` 走旧内部 runner。

## 2. Preset 对象和签名

```text
Stage4GratingInputs3D
PresetInfo(name, geometry, discretization, resource_class, evidence_status, purpose)

available_preset_names() -> tuple[str, ...]
preset_info(name: str) -> PresetInfo
format_preset_listing(verbose: bool = False) -> str
preset_cli_args(name: str) -> tuple[str, list[str]]
```

保留的 Stage4 dataclass 保存 Python 标量、复数和可选值，不包含 DOLFINx/PETSc 对象。迁移 preset 的 `preset_cli_args` 返回同一 public `.dat` 相对路径；保留 preset 才返回旧 3D runner token，因此契约测试无需导入有限元运行时。

## 3. Demo 与 target 的物理身份

Stage4 名称被有意拆成两组：

| 名称前缀 | 几何来源 | 身份 |
|---|---|---|
| `3d_stage4b_demo_*` | `Stage4GratingInputs3D` 内的 100 x 100 nm 演示几何 | demo，不与 Task27 target record 比较 |
| `3d_target_grating_direct_*` | `config_3d::target_stage4_config(degree=2,h_nm=...)` | 与 Case021 的 50 x 25 x 140 nm target 对齐 |

target preset 先由唯一配置工厂生成，再经 `Stage4GratingInputs3D.from_simulation_config` 转换；普通 direct 只把 `matrix_diagnostics_assemble_only` 从 `True` 改为 `False`。测试逐字段比较几何、材料、角度、偏振、阶次、网格和 DtN 策略，防止复制参数漂移。

运行 `python src/main.py --list-presets --verbose` 时，11 个迁移项只显示 dat 路径和迁移状态，6 个保留 preset 显示 `geometry`、`discretization`、`resource` 和 `status`。其中 p=2、h=3 target direct 属于高资源运行，名称可用不等于当前 14 GB 环境保证成功。

## 4. 2D 参数流

真实调用顺序为：

```text
scripts/run_case.py
-> load_and_resolve(.dat)
-> task038_input_worker / ordinary 2D adapter
-> run_cases solver entry
-> argparse
-> run_cases::_base_updates
-> SimulationConfig(**updates)
-> solve_vector_maxwell::run_case            # TM scattered
   solve_port_maxwell::run_port_case          # TM port
   solve_te_maxwell::run_te_case              # TE scattered
   solve_te_maxwell::run_te_port_case         # TE port
```

`run_cases::_parse_complex_index(text)` 接受 `1.45`、`0.999+0.002j` 和 `0.999+0.002i`。输入是折射率 `n`，配置中的介电常数是 `epsilon_r=n^2`。`_normalize_method`、`_formulation_list` 和 `_port_model_list` 可展开显式请求；`_backends_for_case` 会拒绝目前不支持的 MPI manual 或 MPI nonlocal DtN 组合。

2D config 是单个 Python 对象；进入网格后，函数空间的全局 DoF 数由 `V.dofmap.index_map.size_global * index_map_bs` 决定。manual 路径把串行 PETSc 矩阵转为 SciPy CSR 并形成约束降阶系统；MPC 路径保留 PETSc 分布式 ownership。

## 5. 3D 参数流

```text
scripts/run_case.py
-> load_and_resolve(.dat)
-> task038_input_worker / 3D adapter
-> run_3d_cases::main(argv)
-> run_3d_cases::_stage_defaults(stage_case)
-> run_3d_cases::_config_updates(args)
-> SimulationConfig3D(**resolved)
-> run_3d_cases::_run_stage_config(cfg,out_dir)
-> 对应 solve_maxwell_3d_stage_*::run_*
-> common_3d_case_flow::run_prepared_3d_case_flow
```

`_stage_defaults` 一次只选择一个明确 stage，不存在 `stage2_all`、`stage4_all` 或 `both`。`_parse_petsc_option_tokens` 和 `_parse_petsc_extra_option` 把显式覆盖转换为 PETSc option 字典；最终 option 会写入 summary，不能只凭 preset 名推断实际求解器。

3D 运行中的 config 在所有 rank 上复制；mesh、Nedelec 向量、矩阵和 KSP 按 PETSc ownership 分布。只有 rank 0 写 JSON/索引文本，ParaView 场由各 rank 写 owned cells。

## 6. 参数优先级和偏离

参数优先级是：

```text
schema default/conditional resolution
-> explicit `.dat` fields
-> adapter-specific accepted capability checks
-> runner 构造的 resolved config
```

public `.dat` 入口不接受物理、solver、MPI 或 results-root CLI override；这些字段必须写在输入文件中。保留的 research/history `--preset` replay 继续遵循旧 parser 语义，但不属于普通 public input。

## 7. 输出对象

runner 返回或汇总普通 Python dict，主要包含：

| 字段 | 来源 |
|---|---|
| `config` / `resolved_config` | 最终 dataclass 序列化 |
| `num_*_dofs`、matrix stats | 函数空间与 PETSc/SciPy 系统 |
| residual、KSP reason | solver 真残差与 PETSc 状态 |
| `power_metrics` / official RTA | 后处理 |
| `elapsed_seconds`、RSS | case/runtime 资源记录 |
| `out_dir` / artifact provenance | runner 输出管理 |

普通运行保留在 `results/`；canonical benchmark 的轻量 JSON 进入 Git，重型网格、VTU 和完整日志进入 gitignored `benchmarks/artifacts/`。

## 8. 一次可复核调用

```powershell
python scripts/run_case.py input/smoke/2d_tm_dtn_auxiliary_smoke.dat --dry-run
python src/main.py --list-presets --verbose
python src/main.py --preset 3d_target_grating_direct_h5
```

最后一个命令仍是保留 research/history target direct 的参数入口，资源资格应以对应 Case 为准。普通迁移输入不再通过 `src.main` 重建物理参数；迭代生产路径仍按其受控 runner/Task38 dat 合同启动。

## 9. 公式到入口的关系

入口不实现物理公式。它只把 `lambda0`、`n`、角度、偏振、几何和离散参数传入 config；`k0=2*pi/lambda0`、Bloch 相位、`epsilon_r=n^2` 等派生量由 config 统一计算，弱式和端口算子在 solver 中使用。这样同一 preset 的 CLI 与 PyCharm 路径不会形成两套方程。

## 10. 测试、身份与限制

- `src/test/test_27_main_preset_contract.py`：名称唯一、默认安全、verbose 资源身份、全部 token 被真实 parser 接受、demo/target 不混名。
- Case021：target direct h5/h3 的物理身份和 records。
- Case031：唯一 qualified 的 workstation MPI4 iterative 流程。
- official：resolved config、solver/RTA 输出；preset 描述只是入口元数据。
- 限制：main 不验证网格收敛，也不会把参数扫描自动升级为 canonical；非 frozen 参数必须标记 experimental。

操作说明见 [`../../quick_start/01_main_py_parameter_map.md`](../../quick_start/01_main_py_parameter_map.md)，整体生命周期见 [`20_3d_staged_architecture.md`](20_3d_staged_architecture.md)。
