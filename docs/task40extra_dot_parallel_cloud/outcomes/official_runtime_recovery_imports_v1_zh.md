# 官方运行时恢复：包与 import 资格

2026-10-03 UTC。**官方 complex FE/PETSc 包已安装，import/scalar/MPI/API 检查通过；实际 FE action、JIT、MPC 数学接线、factor 与 PDE 仍未运行。** 这不是旧 ABI 恢复，也不关闭 Review V4 的 C1/C2 或原尺寸资格。

## 实際安装与可核验身份

安装位置为 dot 云端独立 prefix；未改系统 MPI、HOME、网络/安全设置、用户机器或其他分支。官方 micromamba2.9.0 通过标准云浏览器下载；conda-forge linux-64/noarch 全 repodata 也通过标准下载取得。离线 solver 给出139个包、402371362B；每个包在复制时和 link 前按 size/SHA256 核验。源码 [manifest](records/runtime_recovery_v1/resolved_packages_manifest.json)保留完整官方 URL、构建与 SHA256；[安装收据](records/runtime_recovery_v1/installed_environment_receipt.json)绑定同一集合，139个 installed name/version/build/filename 全匹配。

| 身份 | 实际结果 |
|---|---|
| Python | 3.12.13，conda-forge |
| DOLFINx / Basix | 0.10.0 / 0.10.0 |
| MPC | Python包无 __version__；conda记录及已加载 native库均0.10.5 |
| PETSc / petsc4py | 3.25.6 / 3.25.6，complex128、int32 |
| MPI | MPICH5.0.1，COMM_WORLD size1/rank0，process-local UCX_TLS=self |
| NumPy / SciPy | 2.5.3 / 1.18.1 |
| UFL / FFCx | UFL2025.2.1；FFCx conda包0.10.1、实际module __version__为0.10.0，两身份保留 |
| MUMPS | 安装包5.8.2；PETSc报告后端enabled，公开方法存在，未创建或分解矩阵 |

[imports-only收据](records/runtime_recovery_v1/imports_only_pass_attempt2.json)绑定实际加载路径、libmpi/libpetsc/libdolfinx/libdolfinx_mpc 等库路径和脚本SHA。它没有检查实际单元 kernel、完整约束或矩阵 factor；public API 存在不等于 backend数学/资源通过。PETSc int32仍是目标尺度的明确容量门，不能据此推断大 NNZ 安全。

## 两个真实 startup stop 与解决

第一次 micromamba create 在读取不存在的全局 ~/.conda/environments.txt 时exit1；当时只有空 conda-meta/history，0个已安装包，没有Python。stdout里的success=true不作为成功裁决。官方2.9源码中registration仅在create_target_directory调用；普通install进入现有空prefix跳过create_env分支，因此无需写全局registry或改变HOME。随后 exact offline explicit set link exit0。

第一次 import 在 MPICH默认UCX初始化失败：/sys/class/net不可用、共享内存Unix socket不允许，exit143；未创建FE矩阵。已安装UCX的self loopback transport可用；process-local UCX_TLS=self后重试import exit0。这只支持MPI1，不授予多rank/网络通信资格。hwloc无法读取sysfs CPU拓扑的warning被原样保存。[失败与解决收据](records/runtime_recovery_v1/startup_failures_and_resolution.json)保留这些停止，旧环境中断的最终checker仍为UNKNOWN。

## 复现的最小 bootstrap 合同

[官方 explicit lock](../../../scripts/task40extra_cloud_recovery/environment_explicit_conda_forge.txt)保留139个完整官方URL及MD5；上述manifest另提供每个archive的SHA256。无需重新solve或取得旧snapshot。先从[官方 micromamba安装文档](https://mamba.readthedocs.io/en/stable/installation/micromamba-installation.html)取得installer；本次archive SHA在[installer收据](records/runtime_recovery_v1/installer_receipt.json)中。工作站如换版本必须记录新installer/ABI，不能继承本收据。

下面是实际使用方式的可移植参数写法；路径由执行者选择，全部应位于其项目工作区。空prefix必须没有已有环境数据；先创建标准conda-meta/history，再用普通install避免全局registry。保持HOME不变：

```sh
mkdir -p "$runtime_prefix/conda-meta" "$cache_root/pkgs"
touch "$runtime_prefix/conda-meta/history"
CONDA_PKGS_DIRS="$cache_root/pkgs" "$micromamba_exe" -r "$cache_root" --no-rc install --yes --safety-checks enabled --extra-safety-checks -p "$runtime_prefix" --file scripts/task40extra_cloud_recovery/environment_explicit_conda_forge.txt
UCX_TLS=self OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 "$runtime_prefix/bin/python" scripts/task40extra_cloud_recovery/qualify_imports_only.py --record imports_only.json
```

这不是无条件执行的shell脚本；执行前需给出明确runtime_prefix/cache_root/micromamba_exe并验证prefix为空。dot本次因shell vendor访问不可用，采用浏览器下载全部archive→每包SHA核验→file://版本的同一exact lock→普通install --offline；这没有更改代理/网络路径或跳过TLS验证。安装与import命令成功不授予FFCx/JIT或C1。为避免重新丢失资料，下次昂贵数学运行必须先落实持久raw位置；此检查点只存小代码/lock/收据，未上传包或旧raw数组。

## 后续仍 held

Review V4 C0的包/import条件已进展，持久raw、实际JIT/FE ABI接线仍待完成。C1先同一fresh full3D fixture验证p6 dense/compact完整内部与非零端口RHS/recovery，再做单独p4/manual532全q regular/notch；C2才测公共backend与有界AUTO投影成本。新环境不复用旧PASS，不重复旧X/XZ/Y或主线accuracy扫描。目标50×25×140nm/λ0.7、整机2e12B/172800s依然未资格化。
