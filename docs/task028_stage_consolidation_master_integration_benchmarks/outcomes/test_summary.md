# 测试总结

| 检查 | 环境 | 结果 |
|---|---|---|
| compileall / py_compile | host | 通过 |
| Ruff 0.12.0 check；新增文件format | host | 通过 |
| full `src/test` suite | complex DOLFINx | 80通过，10跳过 |
| focused unit MPI1 | complex DOLFINx | 10通过 |
| focused unit MPI4 | complex DOLFINx | 每个rank 10通过 |
| 2D zero-contrast DtN smoke | `code-dolfinx:latest` | residual 1.56e-15，R+T=1 |
| 3D Stage1 MPI2 smoke | Task027 complex image | residual 1.39e-16 |
| p2 h5 direct MPI4 | Task027 complex image | residual 6.33e-12，RSS 2.290 GB |
| p2 h3 direct MPI4 | Task027 complex image | residual 2.74e-11，RSS 8.182 GB |
| p2 h5 iterative MPI4 | Task027 complex image | 1201步，full 9.84e-7 |
| p2 h3 iterative MPI4 | Task027 complex image | 993步，full 9.93e-7 |
| p2 h2 iterative MPI4 | Task027 complex image | 1804步，full 9.997e-7，RSS 13.080 GB |
| Markdown local links | host | 通过 |

容器 Task027 image 没有 Ruff和gmsh。lint使用宿主Ruff；2D smoke使用既有complex+gmsh镜像。第一次不支持的2D `mpc_official + DtN` 组合被接口保护拒绝，改用现有manual backend后通过。

h2 ordinary direct未重复运行：Task008 reviewed reference约需20.533 GB，超过当前14 GB配置；h5/h3 direct已在Task28重跑。
