# Stage4 环境限定

## 当前状态

Task28 的源码和数值记录可由 clean checkout 检查，但基础镜像 `code-dolfinx-mpc` 目前只存在于本机镜像仓库，没有可公开拉取的上游地址。因此环境状态严格标记为 `qualified_local_image`，不宣称 clean machine 可直接联网重建。

固定基础镜像：

```text
code-dolfinx-mpc@sha256:4f9ce26eb5cd30199895620eec622f91c17e4783568931307ca5529e2a0f31f6
```

该镜像包含 real/complex 双构建；`Dockerfile.stage4` 显式选择 `linux-gnu-complex128-32`，并安装 `gmsh==4.15.2`。最终稳定 profile 不调用 HPDDM 或 SLEPc eigensolver。

## 构建和验证

```powershell
docker build -f docker/Dockerfile.stage4 -t myfenics-stage4:task28 .
docker run --rm myfenics-stage4:task28 python -c "from petsc4py import PETSc; import dolfinx_mpc, gmsh; print(PETSc.ScalarType, gmsh.__version__)"
```

预期标量类型为 `numpy.complex128`。仓库挂载与运行命令见 `docs/quick_start.md`。

## Clean machine 恢复计划

1. 在当前合格工作站导出基础镜像：`docker save code-dolfinx-mpc@sha256:4f9c... -o code-dolfinx-mpc-task28-base.tar`。
2. 另行保存 tar 文件的 SHA-256；镜像归档属于大型外部制品，不进入 Git。
3. 在 clean machine 上执行 `docker load -i ...`，确认 image ID 后构建 `Dockerfile.stage4`。
4. 运行 `benchmarks/scripts/run_level1.sh`、`run_level2_mpi.sh` 和 h=5 qualification。
5. 将来只有在基础镜像 Dockerfile 或可拉取 OCI registry digest 进入项目基础设施后，才能把状态升级为 `reproducible`。

这项限制不影响本轮数值结论，但会使最终合并资格保持 `pass_with_environment_qualification`。
