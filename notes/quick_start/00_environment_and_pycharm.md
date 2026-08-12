# 环境与 PyCharm：从空白到第一次成功运行

## 1. 本教程解决什么问题

本项目依赖 complex PETSc、DOLFINx、dolfinx_mpc、Gmsh 和 MPI。Windows 宿主 Python 只适合阅读文档和运行不导入 DOLFINx 的检查；正式 Maxwell 计算使用资格化环境。完成本页后，应能用显式 `.dat` 输入运行 Stage1，并知道结果在哪里。

## 2. 当前能力状态

| 项目 | 状态 |
|---|---|
| `myfenics-stage4:task28` | `qualified_local_image` |
| PETSc scalar | `numpy.complex128` |
| 普通 public 输入 | 显式 `.dat` 的 direct/adapter 能力 |
| MPI4 workstation | 需要独立 Run Configuration，不由普通 Run 启动 |
| 任意干净机器在线重建 | 未资格化，基础 MPC 镜像没有公开 pull source |

## 3. 运行前提

1. Docker Desktop 正在运行，WSL2 内存上限约 14 GB。
2. 仓库根目录是 `fenics_vector_maxwell_floquet_demo_v2_parallel`。
3. Docker 中存在 `myfenics-stage4:task28`。
4. 当前分支包含 `docker/Dockerfile.stage4` 和 `benchmarks/environment.json`。

检查镜像：

```powershell
docker image inspect myfenics-stage4:task28
```

## 4. PyCharm 选择哪种入口

推荐建立两个配置：

| 配置 | 用途 | 进程数 |
|---|---|---:|
| `Maxwell ordinary dat` | 2D、Stage1/2/4 direct input | 由 `.dat` 的 execution.mpi_size 决定 |
| `Stage4 workstation MPI4` | Benchmark 031 iterative | 4 |

本页先建立第一个；MPI4 配置见 [`40_3d_workstation_iterative.md`](40_3d_workstation_iterative.md)。

## 5. PyCharm 中的实际设置位置

打开 `Settings | Project | Python Interpreter`，选择能够映射仓库到 `/work` 的 Docker/WSL DOLFINx 解释器。随后建立 Python Run Configuration：

```text
Script path       = <repository>/scripts/run_case.py
Parameters        = input/smoke/3d_stage1_airbox_smoke.dat --validate-only
Working directory = <repository>
Environment       = PYTHONUNBUFFERED=1
```

如果 PyCharm 版本不支持该 Docker interpreter，使用 External Tool：

```text
Program           = docker
Arguments         = run --rm -v "$ProjectFileDir$:/work" -w /work
                    myfenics-stage4:task28
                    /dolfinx-env/bin/python /work/scripts/run_case.py
                    /work/input/smoke/3d_stage1_airbox_smoke.dat --validate-only
Working directory = $ProjectFileDir$
```

Windows 找不到 `docker` 时，把 Program 改成 Docker Desktop 的 `docker.exe` 绝对路径。

## 6. 第一次运行使用的参数块

当前 public Stage1 示例是：

```text
input/smoke/3d_stage1_airbox_smoke.dat
```

对应物理问题为 10 x 10 x 10 nm 均匀空气盒，p=1、h=5 nm。不要先改成 Stage4 h=3。

## 7. 参数含义与资格影响

| 参数 | 含义 | 合法值 | 资格影响 |
|---|---|---|---|
| `.dat` 路径 | 一次运行的完整 public 输入 | `input/README.md` 中的模板/案例 | 改动后需重新解析与资格化 |
| `Working directory` | 相对路径基准 | 仓库根 | 错误会导致输出/配置找不到 |
| Docker image | 数值运行环境 | 限定 image/digest | 换镜像必须重新确认 complex PETSc |
| MPI rank | 并行进程数 | 由 `.dat` 的 `execution.mpi_size` 决定 | 资格边界见对应 case/evidence |

查看该 dat 解析后的身份/执行摘要：

```powershell
docker run --rm -v "${PWD}:/work" -w /work myfenics-stage4:task28 `
  /dolfinx-env/bin/python scripts/run_case.py input/smoke/3d_stage1_airbox_smoke.dat --dry-run
```

## 8. CLI 等价命令

```powershell
docker run --rm -v "${PWD}:/work" -w /work myfenics-stage4:task28 `
  /dolfinx-env/bin/python scripts/run_case.py input/smoke/3d_stage1_airbox_smoke.dat
```

public 运行必须显式提供 `.dat`；`src.main` 无参数只显示 usage/deprecation，不启动案例。

## 9. 真实调用链

```text
scripts/run_case.py
-> src.io.load_and_resolve
-> src.runners.task038_input_worker
-> Task38 ordinary/Full3D adapter
-> src.runners.run_3d_cases
-> current stage solver and postprocess
-> common mesh/forms/solve/postprocess
```

## 10. 输出目录树

```text
results/
└── 3D_stage1_airbox_normal_p1_h5p0_<timestamp>/
    ├── run_summary.json
    ├── solver_log.txt
    ├── mesh.msh
    ├── fields_3d_for_paraview.vtu
    └── all_run_summary.json
```

MPI 运行会写 `fields_3d_for_paraview_parallel.pvd` 和 rank-local VTU。

## 11. 第一次应查看的 JSON 字段

| 字段 | 判断 |
|---|---|
| `linear_system_relative_residual` | 应为很小的正数 |
| `num_nedelec_dofs` | 证明不是空网格 |
| `E_relative_error` / `H_relative_error` | Stage1 解析场误差 |
| `poynting_direction_cosine` | 应接近 1 |
| `total_peak_rss_mb` | 本次 MPI 总内存口径 |

## 12. ParaView 显示步骤

1. `File | Open` 选择 VTU；MPI 选择 PVD，不要只开一个 rank 文件。
2. 点击 `Apply`。
3. `Coloring` 选择 `E_total_abs` 或对应场量。
4. 用 `Slice` 检查传播方向，用 `Warp By Vector` 前先确认矢量字段存在。
5. 若画面空白，点击 `Reset Camera` 并检查时间步。

## 13. 成功 Gate

```text
程序 exit code = 0
PETSc ScalarType = complex
run_summary.json 存在
residual 有限且通过案例阈值
场文件可被 ParaView 打开
```

## 14. 常见错误

| 现象 | 原因 | 处理 |
|---|---|---|
| `No module named petsc4py` | 使用 Windows 宿主 Python | 切到 Docker/WSL interpreter |
| `PETSc is not in complex mode` | 错误镜像 | 使用限定 Stage4 镜像 |
| 找不到 `src` | Working directory 错 | 改为仓库根 |
| 输出出现在奇怪目录 | volume/working directory 错 | 同时检查 `-v` 与 `-w` |
| MPI 启动后停住 | rank 异常或资源不足 | 看所有 rank 日志，不要只看 rank0 |

## 15. 从 smoke 改成自己的 case

先复制一个适用的 `.dat` 并改名，不要直接改变 canonical target：

```text
cp input/smoke/3d_stage1_airbox_smoke.dat input/local/my_stage1.dat
# 只在 input/local/my_stage1.dat 中修改公开 TOML 字段
python scripts/run_case.py input/local/my_stage1.dat --validate-only
```

然后补测试和文档。几何、材料、波长、角度或 p/h 改动后，结果自动变为用户案例，不继承原 benchmark qualification。

## 16. 延伸阅读

- 参数：[`01_main_py_parameter_map.md`](01_main_py_parameter_map.md)
- 输出：[`02_results_and_paraview.md`](02_results_and_paraview.md)
- 架构：[`../reference/code_walkthrough/01_main_and_runner_dispatch.md`](../reference/code_walkthrough/01_main_and_runner_dispatch.md)
- 理论：[`../theory/maxwell_strong_weak_and_fem.md`](../theory/maxwell_strong_weak_and_fem.md)
- 默认基准：[`../../benchmarks/cases/010_3d_stage1_airbox/README.md`](../../benchmarks/cases/010_3d_stage1_airbox/README.md)
