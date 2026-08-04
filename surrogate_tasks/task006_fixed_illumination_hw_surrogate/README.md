# Task006：固定三照明的高度/宽度结构代理

## 状态

```text
status = ready_after_task005_metadata_closeout
execution_branch = codex/only-one-13p5nm-surrogate-inversion
predecessor = Task005 Review V2
purpose = build a validated 2D h/w forward surrogate at fixed selected illuminations
formal inversion = not authorized in first execution
arbitrary-angle surrogate = forbidden
blind geometry FEM = forbidden before training-only review
```

## 固定物理与照明

```text
wavelength_nm = 13.5
incident_polarization = S
height_nm in [115,125]
width_nm in [16,18]

A05 = grazing 2°, azimuth 0°
A07 = grazing 2°, azimuth 90°
A09 = grazing 4°, azimuth 60°

forward_solver_sha = fdf961545f217d620e22800f2704ae9913a6d270
forward_model = Full3D static uniform N1curl p5/h10/Ny4
mesh = (6,4,14)
MUMPS ICNTL(14) = 40
MPI2 / thread1
observable = task002.fixed-n0-orders.v3
```

## 输入与输出

输入：

```text
(height_nm, width_nm)
```

输出分成两个互不重复的生产合同：

```text
S0 aggregate:
    A05/A07/A09 的 R_total, T_total, A_balance

S1 robust order-total:
    Task005 M1 冻结的可测 fixed-order total powers
```

M2 弱通道仅作诊断。不得在一个正式 likelihood 中同时重复计入 aggregate 与其 order-total 总和。

## 第一轮执行范围

```text
M0  Task005最终metadata closeout；冻结Task006几何设计与复用合同
M1  建立37个training geometries的三照明数据
M2  training-only surrogate comparison、grouped CV和synthetic recovery
STOP for review
```

第一轮明确禁止：

```text
12个blind geometry FEM
geometry active learning
正式Bayesian inversion
实验数据拟合
连续角度输入
P偏振、波长、材料或更多结构参数扩展
```

完整执行合同见 `task.md`。
