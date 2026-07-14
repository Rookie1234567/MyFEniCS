# Task032 Phase 6a 上下局部 FEM 网格

## 1. 本子步骤解决什么

Phase 6a 只建立 Hybrid 直接法的两个局部三维 FEM 域：

```text
bottom local FEM: z = -10 ... 10 nm
middle modal:     z =  10 ... 110 nm
top local FEM:    z = 110 ... 130 nm
```

实现位于 `src/geometry/hybrid_local_mesh.py`。中间 100 nm 的 z 不变体域不再创建
三维单元；本子步骤尚不装配外端口 DtN、内部 modal coupling 或 MUMPS 增广系统。

## 2. 网格与标签合同

`build_hybrid_local_mesh` 从已经审查过的 Stage-4 tensor-grid axis plan 精确切片，
因此两个接口仍与二维截面共享同一组 x/y 节点。当前仅接受：

- `rectangular_block_grating`；
- hexahedron；
- 位于既有 z 网格平面的 `z=10/110 nm` 接口。

每个局部网格重新生成自己的 boundary tags。bottom 的 `z_max` 和 top 的 `z_min`
现在是内部接口；另外一侧分别仍是原有外部 Fourier-DtN 端口。代码在 MPI 下按 owned
facets 做全局求和，并要求接口面和外端口面都恰好含 `nx*ny` 个 facets。

## 3. 法向合同

| 接口 | local FEM outward | modal-domain outward |
|---|---:|---:|
| bottom, z=10 nm | `+z` | `-z` |
| top, z=110 nm | `-z` | `+z` |

两侧法向显式存入 `HybridLocalMesh`，后续 traction coupling 不允许从字符串或矩阵块
位置隐式猜符号。

## 4. p=2 Floquet 与材料覆盖

局部域继续使用原有 3D N1curl(p2) double-Floquet MPC。测试要求两个局部空间都生成
topological trace constraints，且 x/y 相位与 full Stage-4 配置完全一致。材料方面：

- bottom 保留 substrate、grating 以及 grating 周围空气；
- top 保留 grating 顶部与 air；
- top 不再含 substrate。

测试还要求两个局部空间的总 DoF 小于完整 140 nm 三维空间，证明中间体域确实没有
以隐藏 ghost 或重复网格的形式残留。

## 5. 验证入口与边界

```bash
python -m unittest -v src.test.test_36_task032_hybrid_local_mesh
mpiexec -n 4 python -m unittest -v src.test.test_36_task032_hybrid_local_mesh
```

当前串行和 MPI4 均为 3/3 通过。这个结果只资格化局部网格、标签、材料、法向和
Floquet ownership；它不声称 Phase 6 augmented direct 已完成，也不产生 Hybrid R/T/A。

## 6. Phase 6b 单侧外端口 DtN

`src/solvers/hybrid_local_dtn.py` 在每个局部网格上继续装配原 Stage-4 auxiliary
Fourier-DtN，但只保留该局部域真正拥有的外端口：

```text
bottom block unknown = [bottom FE, 40 bottom external auxiliaries]
top block unknown    = [top FE,    40 top external auxiliaries]
```

内部接口不进入这个 DtN loop。bottom 没有入射源；top 保留原有 top incident traction
以及 incident modal projection。每个 auxiliary row 的小块对角仍为 1，FE-to-modal 和
modal-to-FE coupling 仍只沿外端口 trace 稀疏插入。

```bash
python -m unittest -v src.test.test_37_task032_hybrid_local_dtn
mpiexec -n 4 python -m unittest -v src.test.test_37_task032_hybrid_local_dtn
```

串行和 MPI4 均为 4/4 通过，覆盖单侧 mode 计数、外部/内部 tag 隔离、auxiliary
identity rows、top-only incident source、无 dense auxiliary block，以及局部 FE DoF
之和小于现场构造的 full Stage-4 FE 空间。此时两个局部块仍彼此独立；内部 mode
traction/projection 与最终 monolithic MUMPS solve 留到后续子步骤。
