# 测试总结

| 检查 | 环境 | 结果 |
|---|---|---|
| compileall / py_compile | host | 通过 |
| Ruff 0.12.0 check；新增文件format | host | 通过 |
| Stage4 Docker build | pinned local base | complex PETSc + gmsh 4.15.2 通过 |
| full Level1 `src/test` suite | `myfenics-stage4:task28` | 91通过，10跳过 |
| focused Level2 MPI1 | 同上 | 14通过 |
| focused Level2 MPI4 | 同上 | 每个rank 14通过 |
| sm2 production branch | 同上，MPI1/MPI4 | explicit reference/repeat/action/destroy 全通过 |
| 2D zero-contrast DtN smoke | 同上 | residual 1.87e-15，R+T=1，写入benchmark artifacts |
| 3D Stage1 MPI2 smoke | 同上 | residual 1.39e-16，RSS 0.520 GB，写入benchmark artifacts |
| automatic Gate checker | host + container | 58/58通过，exit 0 |
| p2 h5 direct response v1 | unified Stage4 image | residual 5.22e-12，RSS 2.293 GB，独立artifact root |
| p2 h3 direct MPI4 | Task027 complex image | residual 2.74e-11，RSS 8.182 GB |
| p2 h5 iterative response v1 | unified Stage4 image | 1201步，full 9.84e-7，RSS 1.991 GB，qualified=true |
| p2 h3 iterative MPI4 | Task027 complex image | 993步，full 9.93e-7 |
| p2 h2 iterative MPI4 | Task027 complex image | 1804步，full 9.997e-7，RSS 13.080 GB |
| Markdown local links | host | 通过 |

Ruff 0.12.0 仍由宿主执行；统一运行镜像不额外安装开发期 lint 工具。Review V1 中发现的第一次 MPI sm2 测试高CPU问题来自 rank-local assertion 提前退出，已改成 MPI allreduce 全局误差断言，重跑正常。

h2 ordinary direct未重复运行：Task008 reviewed reference约需20.533 GB，超过当前14 GB配置；h5/h3 direct已在Task28重跑。
