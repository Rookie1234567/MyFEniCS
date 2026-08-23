# T40-2 人工界面阻抗身份

本阶段只定义 Level A/B 预条件器使用的人工截面一阶切向阻抗；它只改变局部 PC，不改变冻结的裸算子 F。两侧的外法向仍由接口元数据显式保存并相反，但法向符号属于 traction 与分部积分项，不属于 Robin 质量系数。

## 唯一弱式依据

权威实现是 `src/solvers/dtn_port_3d.py::_zero_order_local_robin_forms`。该函数分别构造 `q_top` 与 `q_bottom`，两者都是 `-1j * beta`，再把同号系数乘到顶、底切向质量积分；函数中的弱式说明法向已经由 H(curl) 分部积分的 traction 项承担。

因此 T40 的实现 `src/solvers/hybrid_side_impedance.py::build_first_order_tangential_impedance` 固定为：

```math
q = -i\beta, \qquad Z_t = q M_t.
```

`build_first_order_interface_impedance` 只验证两侧法向为 `(+1,-1)` 或 `(-1,+1)`，然后返回两个相同的 `Z_t`。它不扫描 beta，不根据数值结果选择符号。

## 传输顺序与验证

前向/后向数据的法向符号仍由 traction/coupling 约定携带；传输动作固定为 forward `0 -> 1 -> 2`、backward `2 -> 1 -> 0`，展开为 `0 -> 1 -> 2 -> 2 -> 1 -> 0`。`src/test/test_297_task040_side_impedance.py` 的符号测试验证：

- 两侧 outward-normal metadata 相反；
- 两侧 Robin mass 数值相同且等于 `-i beta M`；
- 非相反法向被拒绝；
- 反向 sweep 保留前向累计的 lower-coupling contribution，而不会覆盖它；
- 局部阻抗只进入 PC，裸 F 的实际 identity audit 仍通过。

该合同绑定仓库现有弱式，不引入单位 Gram、normal-equation 或 beta 扫描。PETSc 的 formal carrier 后续使用 VecScatter 和局部 Mat；本阶段没有启动 formal PDE 或重型运行。

## T40-3 formal result

T40-3 沿用上述唯一阻抗合同：两个人工界面使用同号 q=-i beta，法向只进入 traction/coupling。
两侧 interface mass/support、bare F identity、finite、zero-map、repeat、linearity 和
restriction/prolongation 均通过；三个 cross-section exact factor 仅为
`oracle_only=true`，不是 scalable candidate，cleanup 后 factor count 为 0。

| source | rho | Gate |
|---|---:|---|
| modal traction positive | 16.512689191540417 | mandatory `<1`：fail；preferred `<=0.90`：fail |
| modal traction negative | 14.24201480051629 | mandatory `<1`：fail；preferred `<=0.90`：fail |
| external DtN coupling | 22.945123935386228 | mandatory `<1`：fail；preferred `<=0.90`：fail |
| fixed random repeat 0 | 28.316064601533686 | mandatory `<1`：fail；worst `<=0.95`：fail |
| fixed random repeat 1 | 25.70701839061571 | mandatory `<1`：fail |

因此本次是正式数值负结果 `TRANSMISSION_MECHANISM_FAIL`，不是实现错误或资源停止。
T40-4 及以后依赖阶段不运行；不调 beta、不翻符号、不改变阻抗或 sweep。

## V1-8 资源边界

V1-2 Run B 保留了本页的接口身份，并到达两个 artificial-interface mass 阶段以及 exact-oracle
ready/release markers。随后在接口 probe record 序列化前触及 45 GiB watchdog 线。这不是修改
`q`、法向符号、beta 或 sweep 顺序的依据；身份继续冻结，projected transmission 仍未资格化。
