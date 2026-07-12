# main 与 runner 分发

## `src/main.py`

`ACTIVE_PYCHARM_PRESET` 是无参数运行的唯一选择。`PRESETS_2D/PRESETS_3D` 保存不可变 dataclass；`available_preset_names` 提供稳定清单；`preset_cli_args` 只做翻译，不 import DOLFINx，因此可在主机上做契约测试。

| 函数 | 输入/输出 | 责任 |
|---|---|---|
| `_selected_*_inputs` | preset -> dataclass | 名称验证 |
| `_add_value/_add_bool` | 字段 -> CLI token | 保留 None/三态语义 |
| `_pycharm_args_2d/3d` | dataclass -> args | 完整参数映射 |
| `preset_cli_args` | name -> `(dimension,args)` | 测试与显式调用 facade |
| `main` | `sys.argv` | list/preset/2d/3d 分发 |

默认 `3d_stage1_airbox_smoke` 是安全控制。`mumps_blr` preset 仍翻译成 direct profile；MPI4 iterative 没有 preset。

## `run_cases.py`

1. argparse 读取 formulation/backend/material/mesh/PML/port/output。
2. `_parse_complex_index` 把实数或 `a+bj` 转成 complex。
3. `_normalize_method` 和 `_formulation_list` 展开 scattered/port/all。
4. `_backends_for_case` 阻止 MPI manual 和 MPI nonlocal DtN 非法组合。
5. `_base_updates` 只覆盖显式参数，生成 `SimulationConfig`。
6. 分发到 TM scattered、TM port、TE scattered 或 TE port。
7. 每个 case 保留独立目录并汇总 `all_run_summary.json`。

## `run_3d_cases.py`

1. `_parse_petsc_option_tokens/_parse_petsc_extra_option` 解析 PETSc 覆盖。
2. `_stage_defaults` 为一个显式 stage 设置 geometry/PML/Floquet；没有“全部阶段”隐式值。
3. `_case_configs` 只接受 normal 或 oblique，一个调用对应一个配置。
4. `_run_stage_config` 按 stage 常量集合调用包装器。
5. 普通输出默认 `results/`；只有显式 `--results-root` 才改变。

## 参数优先级

`main preset dataclass` -> CLI tokens -> runner argparse -> config default + 非空更新。若 `python src/main.py --preset NAME` 后再追加相同 flag，argparse 使用后出现的值；该运行已偏离 preset，应在日志/配置中读取 resolved value，而不是只引用 preset 名。

## 测试

`test_27_main_preset_contract.py` 验证名称唯一、所有 token 被 parser 接受、默认安全、无虚构 stage/case、迭代不会静默 qualified。入口参数物理含义见 quick start `01_main_py_parameter_map.md`。
