# Task006：固定三照明的高度/宽度结构代理

## 状态

```text
status = training_only_m2_complete_review_pending
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

## 当前 M2 结果与停止边界

M0、M1 和 M2 已完成。37 个 training geometry 的 111 条三照明记录由
79 个新的、逐一串行运行的 FEM 结果和 32 条 exact reuse 记录组成；12 个
blind geometry 没有读取或运行。M2 使用 geometry-grouped 五折 CV，只在
`.venv-surrogate-cpu` 中进行 CPU 训练，不依赖 CUDA。

训练候选中 Matérn-5/2 ARD exact GP 的 training-only Gate 通过，并按冻结
selection score 被选为当前候选；degree-2 orthogonal-trend + GP residual
也通过，但分数较差。Legendre degree 2/3/4 与 local RBF 没有同时满足
精度和不确定度 Gate。S0 aggregate 使用 log-ratio composition，S1 使用
side-total 加冻结 m=0 primary channel fraction，两个合同独立评分。

held-out synthetic h/w recovery 的全部 37 个外层测试点也通过收敛与误差
Gate（p95 height `0.000677341 nm`、p95 width `0.000137901 nm`，最大误差
分别 `0.000986796 nm` 和 `0.000217014 nm`，rejected `0`）。这些是
training-only synthetic 诊断，不是 blind validation 或实验误差证明。

当前仍是 `training_candidate_review_pending`：不创建正式 model lock，
不运行 12 个 blind FEM，不做主动加点、正式反演或 Task007。证据见
`outcomes/TRAIN37_MODEL_COMPARISON.json`、`TRAIN37_OOF_PREDICTIONS.json`、
`TRAIN37_UNCERTAINTY.json`、`TRAIN37_SYNTHETIC_RECOVERY.json` 和
`TRAINING_MODEL_SELECTION_CANDIDATE.json`。
