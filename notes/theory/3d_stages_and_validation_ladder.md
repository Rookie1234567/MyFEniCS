# 3D 分阶段体系与验证阶梯

分阶段的目的，是让每次新增一个机制时都有更简单的参考问题。后级失败时先回退到最近一级，而不是同时怀疑网格、Floquet、PML、端口、材料和求解器。

## 阶段表

| Stage | 新增机制 | 主要参考 | 当前证据 | 不证明 |
|---|---|---|---|---|
| 1 airbox | 3D H(curl)、解析平面波、边界、direct、输出 | 解析 E/H | MPI2 smoke | Floquet/PML/材料/端口 |
| 2A Floquet | x/y Bloch MPC、p1/p2 trace | 周期平面波 | 约束与 PDE tests | 开放边界 |
| 2B PML | 上下 z-PML 张量 | 衰减/参考 correction | 实验 smoke | 任意参数生产精度 |
| 2C Fresnel | 平界面、复基座、背景场 | Fresnel 解 | 诊断 tests | 光栅/多模 DtN |
| 4A flat | total-field DtN、auxiliary、RTA | Fresnel + 吸收恒等式 | 平层 sanity | 几何散射精度 |
| 4B grating | 块光栅、多衍射级、完整 RTA | direct/iterative 交叉 | target h5/h3/h2 records | 任意新几何外推 |

## Stage 1

`solve_maxwell_3d_stage_1_airbox.py` 只验证共享求解骨架。无参数 main 默认选它，是因为它能快速暴露 complex 模式、网格、空间和 MPI direct 环境问题。

## Stage 2A

`solve_maxwell_3d_stage_2a_floquet_airbox.py` 通过 `common_3d_case_flow` 启用双 Floquet。为了避免封闭周期腔近离散本征值放大，sanity 路径可求解参考 correction，而不是把放大误读为约束错误。

## Stage 2B

`solve_maxwell_3d_stage_2b_pml_airbox.py` 加入 PML cell tags 和变换张量。它用于检查 PML 实现，但 Stage 2 历史扫描表明结果会依赖离散、场重构和 PML 口径；能力矩阵应写 experimental/validated smoke，而不是 production。

## Stage 2C

`solve_maxwell_3d_stage_2c_fresnel_interface.py` 使用 incident-scattered 体源和分层解析参考。它能定位材料标签与 Fresnel 方向，但 p=2 旧诊断仍有已知精度限制，因此不能替代 Stage 4A 的 DtN 功率闭合。

## Stage 4A

`solve_maxwell_3d_stage_4a_flat_layer_sanity.py` 复用 Stage 4 DtN 主路径，只去掉几何 contrast。10 x 10 x 10 nm 小域降低 DoF；空气/基座各 5 nm。它应验证端口、辅助幅值、Fresnel 与体吸收，而不是用横向大尺寸增加成本。

## Stage 4B

`solve_maxwell_3d_stage_4b_block_grating.py` 只做 stage guard，真正流程在：

1. `mesh_builder_3d` 建边界贴合网格和 tags；
2. `common_3d_forms` 建 FE 体块；
3. `floquet_3d` 建双周期 MPC；
4. `dtn_port_3d` 建辅助模态系统；
5. direct 或 `stage4_runtime`/benchmark 迭代求解；
6. `rta_3d` 与 `postprocess_3d` 输出。

## 状态判定

`solver converged` 只属于代数层；`RTA closes` 属于离散守恒层；`h convergence` 才属于数值精度层；与实验/COMSOL 一致还需要材料和几何建模层。文档与 benchmark 不应跨层夸大结论。
