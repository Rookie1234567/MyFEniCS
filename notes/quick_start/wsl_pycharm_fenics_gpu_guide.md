# Windows PyCharm + WSL complex FEniCS + GPU 训练指南

## 1. 环境结构

本机不再使用 Docker。项目在同一个 Ubuntu-24.04 WSL 中保留两个明确入口：

| 用途 | 解释器 | 原因 |
|---|---|---|
| complex Maxwell、PETSc、DOLFINx-MPC、MPI | `/home/fenics/.local/bin/myfenics-python-complex` | 使用 Ubuntu/PPA 的 complex PETSc ABI |
| PyTorch GPU 离线训练 | `/home/fenics/miniforge3/envs/fenics-ml/bin/python` | 已安装 PyTorch 2.7.1+cu118，可见两张 RTX 8000 |

不要在同一进程混用 conda MPICH/real PETSc 与 Ubuntu OpenMPI/complex PETSc。FE solver 导出 dataset/checkpoint 路径；GPU trainer 读取文件训练；solver 再读取 frozen checkpoint 推理。

## 2. 一次性安装 PyCharm wrapper

complex 系统包完成后，在 Windows PowerShell 执行：

```powershell
wsl -d Ubuntu-24.04 -- bash /mnt/c/Users/Administrator/Desktop/MyProject/scripts/install_wsl_pycharm_wrapper.sh
```

验证：

```powershell
wsl -d Ubuntu-24.04 -- /home/fenics/.local/bin/myfenics-python-complex -c "from petsc4py import PETSc; import dolfinx,dolfinx_mpc,importlib.metadata as m; print(PETSc.ScalarType,dolfinx.__version__,m.version('dolfinx_mpc'),dolfinx_mpc.__file__)"
```

`PETSc.ScalarType` 必须是 `numpy.complex128`，MPC 路径必须位于 `/home/fenics/opt/dolfinx-mpc-0.10.1-complex-petsc3.19-v2/`。Ubuntu PPA 的 MPC Python 扩展链接 real ABI，因此本机从官方 v0.10.1 源码重编译了隔离的 complex 扩展；wrapper 会优先加载它。wrapper 同时固定 `OMP_NUM_THREADS=1` 和 `OPENBLAS_NUM_THREADS=1`，避免 MPI4 A/B 因线程数变化失去可比性。

## 3. PyCharm 配置 complex FEniCS 解释器

1. 打开 Windows PyCharm，打开目录 `C:\Users\Administrator\Desktop\MyProject`。
2. `Settings | Project | Python Interpreter | Add Interpreter | On WSL`。
3. Distribution 选择 `Ubuntu-24.04`。
4. Interpreter path 选择 `/home/fenics/.local/bin/myfenics-python-complex`。
5. 等待 PyCharm 建立 skeleton/index；首次扫描 DOLFINx/PETSc 会较慢。
6. Run Configuration 的 working directory 使用 `/mnt/c/Users/Administrator/Desktop/MyProject`。
7. 普通单 rank smoke 可用 module，例如 `src.main`；参数按现有 quick-start 文档填写。

若 PyCharm 不接受 shell wrapper 作为 interpreter，则选择 `/usr/bin/python3`，并在 Run Configuration 添加：

```text
PETSC_DIR=/usr/lib/petscdir/petsc-complex
SLEPC_DIR=/usr/lib/slepcdir/slepc-complex
PYTHONPATH=/home/fenics/opt/dolfinx-mpc-0.10.1-complex-petsc3.19-v2/python:/usr/lib/petscdir/petsc3.19/x86_64-linux-gnu-complex/lib/python3/dist-packages:/usr/lib/python3/dist-packages:/mnt/c/Users/Administrator/Desktop/MyProject
LD_LIBRARY_PATH=/home/fenics/opt/dolfinx-mpc-0.10.1-complex-petsc3.19-v2/lib:/usr/lib/petscdir/petsc3.19/x86_64-linux-gnu-complex/lib:/usr/lib/slepcdir/slepc3.19/x86_64-linux-gnu-complex/lib
OMP_NUM_THREADS=1
OPENBLAS_NUM_THREADS=1
```

实际版本化目录可用以下命令检查：

```bash
ls -d /usr/lib/petscdir/*complex* /usr/lib/slepcdir/*complex*
```

## 4. PyCharm 配置 GPU 训练解释器

再添加第二个 WSL interpreter：

```text
/home/fenics/miniforge3/envs/fenics-ml/bin/python
```

建立 Python Module run configuration：

```text
Module name: benchmarks.run_neural_local_pc
Parameters: --mode toy-smoke --device cuda:0 --artifact-root benchmarks/artifacts/cases/090/toy_smoke
Working directory: /mnt/c/Users/Administrator/Desktop/MyProject
```

验证 GPU：

```python
import torch
print(torch.cuda.is_available())
print([torch.cuda.get_device_name(i) for i in range(torch.cuda.device_count())])
```

当前小型 POD-MLP 默认单卡 `cuda:0`，因为双卡同步开销通常大于收益；第二张 RTX 8000 用于独立候选训练。不要把单卡与双卡时间直接混成严格 A/B。

## 5. PyCharm 中运行 MPI4

PyCharm 的普通 Run 按钮不应伪装成 MPI4。建立 `Settings | Tools | External Tools`：

```text
Name: MyFEniCS MPI4 WSL
Program: C:\Windows\System32\wsl.exe
Arguments: -d Ubuntu-24.04 -- mpiexec -n 4 /home/fenics/.local/bin/myfenics-python-complex -m benchmarks.run_workstation_iterative <其余参数>
Working directory: C:\Users\Administrator\Desktop\MyProject
```

先用 h5 和独立 record/artifact 路径。正式 neural capture 示例见 Case090 README。h3/h2 仍受任务 Gate 限制。

## 6. 常见问题

- `PETSc.ScalarType` 是 `float64`：用了 conda `fenics-ml` 跑 FE；切回 complex wrapper。
- `No module named dolfinx_mpc`：没有使用 wrapper，或本机 complex MPC 用户安装缺失；重新运行安装 wrapper 脚本只能刷新入口，不能替代 `/home/fenics/opt/...` 下已编译的扩展。
- `create_matrix ... Form_float64`：错误加载了 PPA 的 real MPC 扩展；检查 `dolfinx_mpc.__file__` 必须指向上述用户目录，并用 `ldd cpp*.so` 确认没有 `_real` 依赖。
- MPI import/ABI 错误：混用了 conda `mpiexec` 与 `/usr/bin/python3`；complex FE 一律使用系统 `mpiexec`。
- CUDA 可见但 FE 不用 GPU：正常；当前 GPU 只用于 NN 训练/可选局部 inference，PETSc 全局向量不搬入 GPU。
- `/mnt/c` 大量小文件慢：重型 dataset 可临时放 WSL ext4，再在任务记录中保存路径/checksum；Git 只保留轻量摘要。
