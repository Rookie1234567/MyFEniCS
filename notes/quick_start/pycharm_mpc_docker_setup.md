# PyCharm Professional 使用 MPC Docker Compose 解释器

本文说明如何在 PyCharm Professional 中切换到当前 Maxwell/Floquet 算例需要的新 Docker 环境。

正确流程是：

```text
先添加 Docker 连接
再添加 Docker Compose Python 解释器
最后选择 docker-compose.yml 里的 dolfinx_mpc 服务
```

这和之前使用 PyCharm 跑 DOLFINx 的方式一致，只是这次要换成新的 compose 服务：

```text
dolfinx_mpc
```

不要继续用旧服务：

```text
dolfinx
```

旧服务 `dolfinx` 对应旧镜像 `code-dolfinx:latest`，可以继续跑以前的普通 DOLFINx 例子；当前这个双版本 Maxwell/Floquet 算例需要 `dolfinx_mpc`，所以应使用新服务 `dolfinx_mpc`，对应镜像：

```text
code-dolfinx-mpc:latest
```

## 1. 当前 Compose 里有两个服务

项目根目录的：

```text
C:\Users\admin\Desktop\Code\docker-compose.yml
```

现在包含两个服务：

```text
dolfinx      -> code-dolfinx:latest
dolfinx_mpc  -> code-dolfinx-mpc:latest
```

当前算例请选择：

```text
dolfinx_mpc
```

我已经在 `dolfinx_mpc` 服务里写好了 complex PETSc/DOLFINx 环境变量，所以 PyCharm 通过 Docker Compose 解释器运行时，应直接进入复数环境。

## 2. 先确认 Docker 镜像存在

在 PowerShell 中进入项目目录：

```powershell
cd C:\Users\admin\Desktop\Code
```

查看镜像：

```powershell
& "$env:LOCALAPPDATA\Programs\DockerDesktop\resources\bin\docker.exe" image ls code-dolfinx-mpc
```

如果看到：

```text
code-dolfinx-mpc   latest
```

说明新环境已经在本机。

如果没有，可以构建：

```powershell
& "$env:LOCALAPPDATA\Programs\DockerDesktop\resources\bin\docker.exe" compose build dolfinx_mpc
```

也可以直接运行一次：

```powershell
& "$env:LOCALAPPDATA\Programs\DockerDesktop\resources\bin\docker.exe" compose run --rm dolfinx_mpc python3 -c "from petsc4py import PETSc; import dolfinx, dolfinx_mpc; print(PETSc.ScalarType); print(dolfinx.__file__); print(dolfinx_mpc.__file__)"
```

正确输出应包含：

```text
<class 'numpy.complex128'>
/usr/local/dolfinx-complex/...
/usr/local/dolfinx-complex/...
```

如果看到：

```text
<class 'numpy.float64'>
/usr/local/dolfinx-real/...
```

说明没有进入 complex 模式，需要检查 `docker-compose.yml` 中 `dolfinx_mpc` 服务的环境变量。

## 3. 在 PyCharm 里添加 Docker 连接

1. 打开 PyCharm Professional。
2. 进入：

```text
File -> Settings
```

3. 打开：

```text
Build, Execution, Deployment -> Docker
```

4. 点击 `+`。
5. 选择 Docker Desktop / Windows Docker。
6. 点击 `Test Connection`。
7. 看到 `Connection successful` 后点击 `OK`。

这一步只是让 PyCharm 知道 Docker 在哪里。

## 4. 添加 Docker Compose Python 解释器

进入：

```text
File -> Settings -> Project: Code -> Python Interpreter
```

点击解释器旁边的齿轮或 `Add Interpreter`，选择：

```text
On Docker Compose
```

或类似名称：

```text
Docker Compose
```

然后填写：

```text
Configuration file:
C:\Users\admin\Desktop\Code\docker-compose.yml

Service:
dolfinx_mpc

Python interpreter path:
/usr/bin/python3
```

路径映射如果需要手动填写：

```text
Local path:  C:\Users\admin\Desktop\Code
Remote path: /work
```

建议把解释器命名为：

```text
Docker Compose (dolfinx_mpc complex)
```

这样它不会和旧的：

```text
Docker Compose (dolfinx)
```

混在一起。

## 5. 运行配置怎么填

进入：

```text
Run -> Edit Configurations...
```

新建一个 Python 配置。

推荐运行整个双版本对比：

```text
Module name:
fenics_vector_maxwell_floquet_demo_v2_parallel.src.main

Parameters:
--constraint-backend both
```

解释器选择：

```text
Docker Compose (dolfinx_mpc complex)
```

工作目录：

```text
C:\Users\admin\Desktop\Code
```

如果 PyCharm 显示的是容器路径，就填：

```text
/work
```

一般不需要在 Run Configuration 里再手动填 complex 环境变量，因为它们已经写在 `docker-compose.yml` 的 `dolfinx_mpc` 服务中。

## 6. 只运行某一个版本

只运行官方 `dolfinx_mpc` 版本：

```text
Module name:
fenics_vector_maxwell_floquet_demo_v2_parallel.src.runners.run_grating_mpc_official
```

只运行手写矩阵版本：

```text
Module name:
fenics_vector_maxwell_floquet_demo_v2_parallel.src.runners.run_grating_manual
```

双版本对比仍推荐：

```text
Module name:
fenics_vector_maxwell_floquet_demo_v2_parallel.src.main

Parameters:
--constraint-backend both
```

## 7. 验证 PyCharm 解释器是否选对

可以新建一个临时 Python 配置，运行：

```python
from petsc4py import PETSc
import dolfinx
import dolfinx_mpc

print(PETSc.ScalarType)
print(dolfinx.__file__)
print(dolfinx_mpc.__file__)
```

正确结果应该类似：

```text
<class 'numpy.complex128'>
/usr/local/dolfinx-complex/lib/python3.12/dist-packages/dolfinx/__init__.py
/usr/local/dolfinx-complex/lib/python3.12/dist-packages/dolfinx_mpc/__init__.py
```

如果出现：

```text
<class 'numpy.float64'>
/usr/local/dolfinx-real/...
```

说明选到了 real 环境，或 PyCharm 没有使用 `dolfinx_mpc` 服务。

如果出现：

```text
ModuleNotFoundError: No module named 'dolfinx_mpc'
```

说明还在用旧服务 `dolfinx` 或旧镜像 `code-dolfinx:latest`。

## 8. 运行后结果在哪里

运行成功后会生成：

```text
fenics_vector_maxwell_floquet_demo_v2_parallel/results/2D_grating_.../
fenics_vector_maxwell_floquet_demo_v2_parallel/results/2D_grating_.../sc_lay_man/
fenics_vector_maxwell_floquet_demo_v2_parallel/results/2D_grating_.../backend_comparison.json
```

ParaView 推荐打开：

```text
fenics_vector_maxwell_floquet_demo_v2_parallel/results/2D_grating_.../fields_for_paraview.vtu
```

常用数组：

```text
E_total_abs
E_total_Ex_real
E_total_Ey_real
E_scat_abs
E_inc_abs
domain_tag
material_id
```

材料标签：

```text
domain_tag = 1  air
domain_tag = 2  substrate
domain_tag = 3  grating
domain_tag = 4  top_pml
domain_tag = 5  bottom_pml
```

## 9. 如果 PyCharm 里看不到 dolfinx_mpc 服务

先确认当前打开的是项目根目录：

```text
C:\Users\admin\Desktop\Code
```

然后在 PowerShell 验证 compose 配置：

```powershell
& "$env:LOCALAPPDATA\Programs\DockerDesktop\resources\bin\docker.exe" compose config
```

输出里应该能看到：

```text
services:
  dolfinx:
  dolfinx_mpc:
```

如果 PyCharm 仍看不到，重启 PyCharm，或者重新添加 Docker Compose interpreter。

## 10. 一句话总结

当前这个算例在 PyCharm Professional 里应选择：

```text
Interpreter type: Docker Compose
Compose file:     C:\Users\admin\Desktop\Code\docker-compose.yml
Service:          dolfinx_mpc
Python path:      /usr/bin/python3
PETSc mode:       complex
```

最终用下面这句确认：

```text
PETSc.ScalarType == numpy.complex128
```

## 11. 用 PyCharm 运行当前算例

PyCharm 解释器仍然选择同一个 Docker Compose 服务：

```text
Service: dolfinx_mpc
Python path: /usr/bin/python3
```

现在推荐在运行配置里直接选择脚本文件：

```text
C:\Users\admin\Desktop\Code\fenics_vector_maxwell_floquet_demo_v2_parallel\src\main.py
```

然后运行参数可以留空。你需要改的选择放在 `main.py` 文件开头，例如：

```python
CALCULATION_METHOD = "scattered"
CONSTRAINT_BACKEND = "mpc_official"
SCATTERING_BACKGROUND = "layered"
PORT_BOUNDARY_MODEL = "robin"
COMPUTE_POWER_METRICS = True
```

如果要跑端口总场法，改成：

```python
CALCULATION_METHOD = "port"
CONSTRAINT_BACKEND = "mpc_official"
PORT_BOUNDARY_MODEL = "robin"
```

默认每次运行都会在：

```text
fenics_vector_maxwell_floquet_demo_v2_parallel/results/
```

下面生成新的 `2D_grating_*_YYYYMMDD_HHMMSS` 文件夹。这样在 PyCharm 中反复运行也不会覆盖上一轮结果。
现在 v2 的新结果目录已改成更短的名字，例如：

```text
2D_grating_sc_lay_p2_h25p0_t85p0_mpc_YYYYMMDD_HHMMSS
```

如果只运行一个 case，`.vtu`、`power_metrics.json`、`run_summary.json` 会直接在这个目录下；一次运行多个 case 时才会建立短子目录。

如果想在 PyCharm 里运行更接近 COMSOL 多衍射级次周期端口的 DtN 版本，可以改 `main.py`：

```python
CALCULATION_METHOD = "port"
CONSTRAINT_BACKEND = "manual"
PORT_BOUNDARY_MODEL = "dtn"
```

这里暂时不要选 `--constraint-backend both`，因为多级次 Fourier 端口目前只在手写矩阵后端中实现。

更多 PyCharm 入口说明见：

```text
pycharm_main_run_guide.md
```
