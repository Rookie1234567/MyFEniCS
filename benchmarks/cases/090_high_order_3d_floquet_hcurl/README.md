# Case090：高阶 3D Floquet H(curl) 资格化入口

> 2026-07-17 正式阶段已完成：clean source `6613f94b91ebc77eb50e74086475c67df46236f6`
> 上 MPI1/2/4 各 48 个 PDE、总计 144 个；p1–p4 全部核心 Gate 通过。

| 契约字段 | 固定内容 |
|---|---|
| 1. ID | `090_high_order_3d_floquet_hcurl` / Task033 Phase 2 |
| 2. 当前证明 | 两个 10 nm fixture 上 p1–p4 的解析 E/H、Bloch/Fresnel、PDE、MPI1/2/4 与稀疏分布式 Floquet 核心 Gate |
| 3. 尚不证明 | 目标光栅 p3/p4 Hybrid/full3D 同阶等价、QEP 全局资格或自适应收益 |
| 4. 物理问题 | Fixture A 均匀空气 Bloch 平面波；Fixture B 平坦 air–Si 复数 Fresnel 界面 |
| 5. 几何 | `x,y=0..10 nm`、`z=-5..5 nm`；Fixture B 的界面为 `z=0` |
| 6. 材料 | air `n=1`；Si `n=0.999002304859+0.00182649365j` at 13.5 nm |
| 7. 波长/角度/偏振 | 13.5 nm；10° grazing primary；1°/5° smoke；S/P；`phi=0` |
| 8. 边界 | x/y 双 Floquet；z 向使用现有解析均匀端口或经审阅 Fresnel 路径 |
| 9. FE/网格 | Nédélec p1–4；h5/h2.5；Fixture A 要求两个 mesh levels |
| 10. MPI | 1/2/4；核心 Gate 必须精确覆盖全部 12 个 p×MPI 组合 |
| 11. 参数表 | [`fixture.json`](fixture.json) 与 [`expected.json`](expected.json) |
| 12. 精确命令 | `python -m unittest -v src.test.test_44_task033_fixture_oracles` |
| 13. 调用链 | runner -> fixture/oracle builder -> semantic validator -> Draft 2020-12 validator -> JSON record |
| 14. 理论 | `exp(i k·r)`、`exp(-i omega t)`；P 基为每个传播方向的 `k-hat × S` |
| 15. 求解器 | clean-source DOLFINx/PETSc complex128 PDE runner；外部 watchdog 记录资源 |
| 16. RTA 恒等式 | 解析界面记录 `R_interface + T_into_substrate_at_interface = 1`；不是有限体积 A |
| 17. 输出 | [`records/analytic_oracles.json`](records/analytic_oracles.json)，身份恒为 `not_run` |
| 18. Gates | clean source SHA、evidence SHA-256、五个代数阈值、12 项 p×MPI、稀疏/无 allgather/无 dense、p1/p2 回归 |
| 19. Canonical 结果 | `all_core_gates_passed=true`；12 个 p×MPI coverage 全通过 |
| 20. Records | 每 MPI 48 项：Fixture A 16、Fixture B primary 16、Fixture B smoke 16；总计 144 |
| 21. Artifact 规则 | 仅提交轻量确定性 JSON；正式大记录必须来自 tracked-source-clean commit |
| 22. 限制 | Case090 是解析小夹具资格化，不能替代目标光栅 p3/p4 Hybrid/full3D 对照 |

## 物理问题

Fixture A 是 10×10×10 nm 均匀空气盒，从上方空气向负 z 传播。
它为 S/P 斜入射 Bloch 平面波冻结方向、E/H 基、x/y 周期相位和一个场样本，
用于检查高阶 H(curl) 约束、orientation、reduced/full action 与解析场误差。

Fixture B 在同一盒内放置 `z=0` 平坦 air–Si 界面。
它冻结复数 Fresnel 振幅、界面功率、上下区域的入射/反射/透射相位，
并分别保存 E 与代码采用的归一化 H 向量。

## 参数说明

角度输入是从表面量起的 grazing angle；代码显式使用
`theta_from_normal = 90° - grazing`。10° 是 primary，1°、5° 只用于轻量
入口 smoke。正式运行对每个 MPI 固定 48 项：Fixture A 16、Fixture B 的 10°
primary 16、Fixture B 的 1°/5° h5 smoke 16。MPI1/2/4 合计 144 项，不是 192。

仓库中 `expected.json`、`schema.json` 与 `analytic_oracles.json` 仍保留早期 192 行
planner 枚举，其中包含不会启动 PDE 的 scope/not-run 行；该 planning 行数不是正式 PDE 次数，
也不应与上述 144 次 measured PDE 相加。

## PyCharm

在仓库根目录建立 Python unittest 配置，模块填
`src.test.test_44_task033_fixture_oracles`。该配置只运行轻量解析与 schema
测试，不需要 MPI，也不运行 PDE。需要检查 runner 时，建立 Python Module
配置 `benchmarks.run_task033_case090_matrix`，参数使用 `--output` 指向临时路径。

MPI1/2/4 PDE 资格化不能由普通 PyCharm 单进程 Run 代替；正式运行应通过
现有 Docker complex128 环境和 `mpiexec` 外部工具执行，并生成独立 clean-source
evidence。

## CLI 或测试

```text
python -m unittest -v src.test.test_44_task033_fixture_oracles
python -m benchmarks.run_task033_case090_matrix --output benchmarks/cases/090_high_order_3d_floquet_hcurl/records/analytic_oracles.json
```

要求核心 Gate 时：

```text
python -m benchmarks.run_task033_case090_matrix --core-gate-record <clean-core-gate.json> --require-core-gate-pass
```

核心记录必须含 40 位 clean source SHA、64 位 evidence SHA-256、全部五个数值
Gate、p1–4×MPI1/2/4 的 12 个唯一组合、稀疏存储证明、无 global boundary
allgather、无 boundary-size dense square，以及 p1/p2 ordinary regression。
缺一项时 runner 返回 2；即使全通过也只把计划标为 `eligible_not_run`。

## 代码路径与理论

入口是 [`../../run_task033_case090_matrix.py`](../../run_task033_case090_matrix.py)，
解析构造与双层校验在
[`../../../src/validation/task033_high_order_floquet_fixtures.py`](../../../src/validation/task033_high_order_floquet_fixtures.py)，
轻量回归在
[`../../../src/test/test_44_task033_fixture_oracles.py`](../../../src/test/test_44_task033_fixture_oracles.py)。
完整阶段顺序、数值阈值与停止条件见
[`../../../docs/task033_high_order_floquet_hybrid_hp_adaptivity/task.md`](../../../docs/task033_high_order_floquet_hybrid_hp_adaptivity/task.md)。

场约定为 `exp(i k·r)` 与 `exp(-i omega t)`。P 偏振在入射、反射和透射
方向分别使用局部 `k-hat × S` 电场基，所以标量 `r_p` 的符号必须连同局部
基解释。对吸收介质，P 的法向功率因子按该基使用
`Re(conj(n) cos(theta_t))`；不能套用 S 的表达式。

## 当前证据

[`records/analytic_oracles.json`](records/analytic_oracles.json) 是确定性轻量记录。
所有非输入 libm 浮点在 JSON 边界统一到 13 位有效数字，避免 Windows host 与
Linux Docker 因最后一个 ULP 不同而破坏 exact record equality，同时仍比最严
oracle 一致性容差保留更细的有效数字。正式代数 Gate 使用 PDE 原始测量值，
不对 Gate observed 值做这项 JSON oracle 舍入。

记录通过手写语义校验和真实 Draft 2020-12 `jsonschema` 校验；嵌套对象均拒绝
未知字段。每个 Fresnel oracle 含上方同一点的入射、反射及合场 E/H，和下方
透射 E/H；每个分量都能由保存的 complex amplitude、phase 和 basis 重构。

当前记录的身份固定为：

```text
status = not_run
is_pde_run = false
is_solver_pass = false
is_physical_qualification_record = false
```

## 结果解释

解析 air–air 检查应给出 `r=0`、`t=1`。当前复数 Si oracle 在 1°、5°、10°
和 S/P 下保存复振幅与界面通量闭合；`T_into_substrate_at_interface` 表示穿过
`z=0` 的向下功率，不是半无限衬底内部的有限体积吸收 A。

tracked planner 本身仍不把 `eligible_not_run` 改写成 pass，也不从解析系数推断
p3/p4 有限元精度。2026-07-17 的结论来自独立 external-watchdog PDE aggregate，
不是从 planner 身份升级而来。

## 限制

上述正式接受条件已由 ignored campaign aggregate 满足：两个 mesh、p1–4、
MPI1/2/4、S/P、10° primary 与 1°/5° smoke 均有真实 PDE 记录，DoF/NNZ、
时间、simultaneous RSS、误差和核心 Gate 也已记录。轻量 stage summary 跟踪其 SHA，
但不把 heavy artifact 提交 Git。

p4 在 Case090 解析小夹具的 36 个 p-refinement 对照中均有正精度收益；这不代表
p4 在目标光栅、Hybrid 或任意工程问题上必然优于 p3。ordinary default 保持不变。
