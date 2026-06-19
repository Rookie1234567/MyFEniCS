# Stage 2 十层测试框架

## 2026-06-18 更新：测试代码已放入 src/test

本目录记录 3D Stage 2 的测试目标、过程和结果。测试代码统一放在：

```text
src/test/
```

日常快速单元测试命令：

```bash
python3 -m unittest discover -s src/test -p "test_*.py"
```

这个命令默认严格运行 Level 0 到 Level 3。Level 4 到 Level 10 会被跳过，除非显式打开 PDE 测试：

```bash
RUN_STAGE2_PDE_TESTS=1 python3 -m unittest discover -s src/test -p "test_*.py"
```

这样设计是为了避免普通检查直接变成 3D Maxwell 压力测试。

## 十个测试层级

Level 0：数学约定和单位

检查波长、几何和网格目标尺寸都使用 nm；检查 `k0 = 2*pi/lambda0`；检查相位约定为 `exp(i k·r) exp(-i omega t)`。

Level 1：解析平面波工具

检查入射方向归一化、TE/TM 偏振正交性、`k·p=0`、H 场方向和 Poynting 矢量方向。

Level 2：PML 张量

检查物理区复坐标不变；检查 top/bottom PML 中出射波衰减；检查 `eps = eps_r diag(s,s,1/s)` 和 `mu_inv = diag(1/s,1/s,s)`。

Level 3：Fresnel 解析系数

检查法向波数恒等式、`n_sub=1` 时无界面退化、TE/TM 无损情形 `R+T=1`。

Level 4：3D 空气盒 Dirichlet PDE

无 Floquet、无 PML，六面施加解析切向电场。用于验证 3D Nedelec 空间、curl-curl 弱式和解析边界。

Level 5：Floquet 自由度约束

先检查解析场满足 x/y/xy Floquet 相位；再在 PDE 测试中检查 Nedelec dof pairing、orientation 和 corner phase。

Level 6：双周期 Floquet 空气盒 PDE

x/y 侧面施加 Floquet MPC，上下 z 面施加解析 Dirichlet。用于验证约束进入 PDE 后是否稳定。

Level 7：PML 空气盒衰减

打开上下 PML，检查物理区误差、PML 衰减和 `pml_reflection_proxy`。其中当前 proxy 是从数值场拟合出来的向上/向下波幅值比。

Level 8：平界面 Fresnel 总场

空气/基底平界面，使用解析 Fresnel 总场作为边界，检查数值场和 R/T 后处理。

Level 9：Fresnel + PML

空气/基底平界面 + x/y Floquet + 上下 PML，检查 `R_num`、`T_num` 和 Fresnel 解析值的一致性。

Level 10：最终组合 sanity

重点检查 `n_sub=1` 情形，理论上界面消失，应有 `R≈0`、`T≈1`。当前硬门槛定义在 no PML/Floquet 和 Floquet-only 两条隔离路径上，因为 total-field 入射波穿过 top PML 时会在复坐标延拓中增长，PML+总场版本仍是 smoke/诊断项。

## 当前验收原则

Level 0 到 Level 3 是公式和工具层测试，必须严格通过。

Level 4 到 Level 10 先作为小网格 PDE 验证和扫描入口。粗网格误差不强行要求一开始低于 1%，但必须记录误差、趋势和失败原因。若 no PML/Floquet 或 Floquet-only 的 `n_sub=1` sanity 失败，不进入 Stage 3；PML+总场 sanity 需要等 PML 注入/采样口径修好后再升级为硬门槛。

## 2026-06-19 Stage 2 当前验收状态

```text
Level 0-3:
  默认单元测试通过。

Level 4-6:
  stage1_airbox、floquet_airbox normal/oblique、MPI 2 h300/h500 smoke 通过。

Level 7:
  PML airbox smoke 通过，bottom decay ratio 对角度、alpha 和厚度有响应。

Level 8:
  Fresnel no PML/Floquet 小扫描完成，n_sub=1 sanity 通过。

Level 9:
  Fresnel+PML 能跑通并输出 R/T，但 total-field+PML 口径仍是诊断项，不作为当前硬门槛。

Level 10:
  n_sub=1 no PML/Floquet 与 Floquet-only sanity 均通过；测试代码已经覆盖这两条。
```
