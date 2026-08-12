# PyCharm Professional 使用 MPC Docker Compose 解释器

> **文档状态：环境历史长文。** 镜像身份以 [`../../benchmarks/environment.json`](../../benchmarks/environment.json) 和 [`00_environment_and_pycharm.md`](00_environment_and_pycharm.md) 为准；本文保留 IDE 操作细节。

本文说明如何在 PyCharm Professional 中切换到当前 Maxwell/Floquet 算例需要的新 Docker 环境。

> **历史资料说明：** 本文保留 Docker/PyCharm 环境操作记录；旧 module runner 和独立 wrapper 已移除。当前普通入口是 `python scripts/run_case.py <one-case.dat>`，参数与示例见 [`input/README.md`](../../input/README.md)。manual 与 `mpc_official` 必须分别写在两个独立 dat 的 `[method] constraint_backend` 中。

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

本文原先的 module 配置仅是历史记录；不要再把已删除的旧 runner 填入 PyCharm。当前运行配置应调用唯一 public command：

```text
python scripts/run_case.py input/path/to/case.dat
```

将 manual 与 `mpc_official` 作为两个独立 dat 示例保存，分别在 `[method]` 中写入：

```toml
constraint_backend = "manual"
```

或：

```toml
constraint_backend = "mpc_official"
```

不要在命令行追加物理、solver、MPI 或 backend override；Docker/PyCharm 环境细节只用于历史环境复现。

## 6. 只运行某一个版本

“某一个版本”现在由所选 dat 的 `method.constraint_backend` 和其他公开字段决定，而不是由 Python module 名称决定。完整键、适用性和当前模板见 [`input/README.md`](../../input/README.md)。

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

PyCharm/Docker 解释器仍可按本文前述历史环境步骤配置，但运行目标应是仓库根目录中的 public command：

```text
python scripts/run_case.py input/path/to/case.dat
```

结果目录、`--validate-only`、`--dry-run` 和完整参数说明以 [`input/README.md`](../../input/README.md) 为准；不要修改 `main.py` 或通过 CLI 覆盖 dat。
