# T40-2 人工界面阻抗身份

本阶段只定义 Level A/B 预条件器使用的人工截面一阶切向阻抗；它只改变局部 PC，不改变冻结的裸算子 F。两侧的外法向仍由接口元数据显式保存并相反，但法向符号属于 traction 与分部积分项，不属于 Robin 质量系数。

## 唯一弱式依据

权威实现是 `src/solvers/dtn_port_3d.py::_zero_order_local_robin_forms`（1837–1865 行）。该函数在 1854–1855 行分别构造 `q_top` 与 `q_bottom`，两者都是 `-1j * beta`；随后在 1861–1865 行把同号系数分别乘到顶、底切向质量积分。其 1840–1844 行说明法向已经由 H(curl) 分部积分的 traction 项承担。

因此 T40 的实现 `src/solvers/hybrid_side_impedance.py::build_first_order_tangential_impedance`（37–58 行）固定为：

```math
q = -i\beta, \qquad Z_t = q M_t.
```

`build_first_order_interface_impedance`（61–76 行）只验证两侧法向为 `(+1,-1)` 或 `(-1,+1)`，然后返回两个相同的 `Z_t`。它不扫描 beta，不根据数值结果选择符号。

## 传输顺序与验证

前向/后向数据的法向符号仍由 traction/coupling 约定携带；传输动作固定为 `0 -> 1 -> 2 -> 1 -> 0`。`src/test/test_297_task040_side_impedance.py` 的符号测试验证：

- 两侧 outward-normal metadata 相反；
- 两侧 Robin mass 数值相同且等于 `-i beta M`；
- 非相反法向被拒绝；
- 反向 sweep 保留前向累计的 lower-coupling contribution，而不会覆盖它；
- 局部阻抗只进入 PC，裸 F 的实际 identity audit 仍通过。

该合同绑定仓库现有弱式，不引入单位 Gram、normal-equation 或 beta 扫描。PETSc 的 formal carrier 后续使用 VecScatter 和局部 Mat；本阶段没有启动 formal PDE 或重型运行。
