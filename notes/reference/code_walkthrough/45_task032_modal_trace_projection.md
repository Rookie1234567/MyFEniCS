# Task032 Phase 5 匹配接口迹与模态投影

## 1. 本阶段解决什么

Phase 5 把两个已经独立验证的对象连接起来：

```text
3D hexahedron N1curl(p2) field
        -> matched interface tangential trace
2D cross-section N1curl(p2) right/left modes
        -> reconstruction / Petrov projection
```

实现位于 `src/coupling/modal_trace_projection.py`。它只建立单接口闭环，
不装配 Phase 6 Hybrid 增广矩阵，也不声称已经得到 Hybrid R/T/A。

## 2. canonical trace 与法向约定

`InterfaceConvention` 始终把电场迹保存成 `(E_x,E_y)`。canonical trace 本身
不暗含正负号；需要 `n x E_t` 时才显式应用法向：

| 接口 | z (nm) | local FEM outward | modal outward | middle-side source cell |
|---|---:|---:|---:|---:|
| bottom | 10 | `+z` | `-z` | `+z` side |
| top | 110 | `-z` | `+z` | `-z` side |

对 `n=s z_hat` 和 `E_t=(E_x,E_y)`，代码使用

```text
n x E_t = (-s E_y, s E_x).
```

`build_matched_interface_trace` 同时检查 3D/2D x-y 轴、接口 z 平面、全局接口
facet 数和中间侧相邻 cell 数。这样 top/bottom 符号或接口取错单元不能静默通过。

## 3. 3D Nedelec 切向迹提取

3D N1curl 的 value shape 是 3，而 2D N1curl 的 value shape 是 2，不能把两者
当作同 shape Function 直接 nonmatching interpolate。`extract_tangential_trace`
采用以下分布式流程：

```text
2D N1curl interpolation points (x,y)
 -> embed as (x,y,z_interface)
 -> determine_point_ownership, restricted to middle-side 3D cells
 -> source rank evaluates 3D E
 -> return only (E_x,E_y) to request rank
 -> target element performs its normal N1curl interpolation/DOF transforms
```

合法的 MPI rank 可能没有本地 source evaluation；实现对空 `dest_points` 保留
`(0,3)` shape，并仍参与 collective。通信只包含接口插值点和每点两个复切向值，
不 allgather 完整 3D field、完整 mode vector 或体网格。

## 4. right reconstruction 与 left projection

Phase 3 的 full mode vector 已由分布式约束变换 `u=Tq` 重构，包含 Floquet slave
值。`transverse_to_mixed` collapse map 把其中横向 N1curl 部分复制到 canonical
trace space，得到右迹列 `Q_gamma` 和左迹列 `W_gamma`。

设 `B_gamma` 为稀疏 2D trace L2 mass matrix：

```text
G = W_gamma^H B_gamma Q_gamma
u_gamma = Q_gamma a
a = G^{-1} W_gamma^H B_gamma u_gamma.
```

`ModalTraceProjection` 不假设 Phase 3 的 `Q'(beta)` 归一化会使接口 L2 Gram
自动成为单位阵，而是显式计算小型 `G` 并在条件数超过 `1e12` 时 fail closed。
投影、重构和 residual 都由分布式 PETSc vectors/matrix 完成。

对象 shape 为：

```text
Q_gamma: N_gamma x M, distributed columns
W_gamma: N_gamma x M, distributed columns
B_gamma: N_gamma x N_gamma, sparse distributed
G:       M x M, small replicated dense block
```

禁止形成 dense `N_gamma x N_gamma` 接口算子。当前非正式 h10 MPI4 研究运行中，
`N_gamma=162`、`M=2`；左右 trace columns 各 5184 bytes（全局分布量），每 rank
复制的 Gram 仅 64 bytes。

## 5. 近简并块为什么比较子空间

同一近简并二维空间可以在不改变物理 span 的情况下作任意 unitary rotation，
因此逐向量 equality 不是合法 Gate。`trace_subspace_report` 先用 `B_gamma` 对两组
基白化，再对 cross Gram 做 SVD；它报告 singular values、最大 principal angle
和 projector error。

测试故意旋转 air 的两维近简并 right-trace basis。第一个旋转向量与原向量明显
不同，但两个 span 的 projector error 约为浮点精度量级；Gate 只使用子空间误差。

## 6. 验证入口与当前边界

```bash
python -m unittest -v src.test.test_35_task032_modal_trace_projection
mpiexec -n 4 python -m unittest -v src.test.test_35_task032_modal_trace_projection
mpiexec -n 4 python -m benchmarks.run_task032_phase5_trace --allow-dirty-research
VERIFIED_CLEAN_SHA=<full-sha> sh benchmarks/cases/080_hybrid_fem_modal_direct_baseline/run_phase5.sh
```

单元/集成测试覆盖 affine complex 3D N1curl field 的 bottom/top 取迹、空 source
rank、法向相反、真实 Stage4/air 模态 round trip、左/右投影、近简并 unitary
rotation 和无 dense interface square。正式 clean record 为
`benchmarks/cases/080_hybrid_fem_modal_direct_baseline/records/trace_phase5.json`，
来源是 `b565ac4610dee08a2d313060b7cb26b48145370d`，SHA-256 为
`8b0eeff9e8666ed327f36e0ab243561e5cecbfc305cb353cab8f2108d6ac7aed`。
MPI4 runner 8/8 Gate 和 Case080 checker `290/290` 均通过；它资格化单接口
coupling，但不把尚未实现的 Phase 6 Hybrid augmented solve 写成已完成。
