# Task004：固定中心几何的二维角度代理

## 状态

```text
status = closed_controlled_negative
execution_branch = codex/only-one-13p5nm-surrogate-inversion
predecessor = Task003 Review V3
purpose = arbitrary in-domain angle-response prediction at one fixed geometry
formal_angle_DOE = not authorized in Task004; requires a separate reviewed task
formal_inversion = forbidden
blind_validation = intentionally_not_run (0/24)
model_lock = absent
closeout_authority = review_report_v8.md
```

## 固定物理与数值身份

```text
height_nm = 120.0
width_x_nm = 17.0
wavelength_nm = 13.5
incident_polarization = S
forward_model = Full3D static
finite_element = uniform N1curl p5
mesh_family = h10, (Nx,Ny,Nz)=(6,4,14)
solver = assembly-time static condensation
MPI = 2
threads_per_rank = 1
observable = task002.fixed-n0-orders.v3
```

## 输入范围

```text
grazing_deg in [0.5, 10.0]
azimuth_deg in [0.0, 90.0]
```

## 目标接口

```text
AngleSurrogate.predict(grazing_deg, azimuth_deg)
    -> R_total, T_total, A_balance
    -> fixed-order outgoing S/P powers
    -> analytic power-carrying mask
    -> predictive uncertainty
    -> domain / cutoff / nearest-data diagnostics
```

该代理仅在固定中心几何下预测角度响应。它用于检验二维角度平面是否可被可靠代理、绘制连续响应图并识别困难区域；它本身不等于高度/宽度反演，也不能在没有 `dy/dh`、`dy/dw` 的情况下正式给出 Fisher 最优角度。

## 数据边界

- Case115 的旧 80-angle map 属于 Ny3 历史离散，只能用于采样设计和差异诊断，不能进入正式训练/验证数组；
- Task003 的 Ny4 数据同时变化 `h,w`，不能删除几何列后冒充二维角度数据；
- Task003 原 16 个 frozen validation 继续封存；
- Task004 必须建立新的 Ny4-only dataset ID、source SHA、design hash、split hash 和 checker。

## 模型边界

首轮只比较有限候选：

```text
baseline_1 = structured-grid interpolation / local RBF
baseline_2 = low-order tensor Chebyshev trend
primary = Matérn-5/2 ARD exact GP
conditional_fallback = analytic propagation-region local GP
```

不得开展神经网络或无边界 model zoo。

## 首轮规模

```text
training = 96 angles
    80 structured angles
    16 cutoff / low-grazing enrichment angles
blind_validation = 24 independent angles
candidate_pool = 4096 angles
active_learning_round1_budget = at most 16 new FEM angles
```

正式四元组在本任务中退化为固定 `(h,w)` 加二维角度，但所有数据记录仍必须完整保存固定几何和求解器身份。

## 主要交付

```text
src/surrogate/angle/
benchmarks/cases/123_task004_nominal_geometry_angle_surrogate/
surrogate_tasks/task004_nominal_geometry_angle_surrogate/
    outcomes/design.md
    outcomes/dataset_report.md
    outcomes/model_selection.md
    outcomes/blind_validation.md
    outcomes/angle_maps.md
    outcomes/test_summary.md
    response_v1.md
```

## 停止边界

Task004 首轮完成后停止等待 ChatGPT 审阅。不得自行开始：

- 高度/宽度灵敏度代理；
- Fisher 角度排名；
- 结构参数反演；
- P 偏振入射代理；
- 波长或材料参数扩展。

## 最终关闭状态

Task004 已依据 `review_report_v8.md` 关闭为
`closed_controlled_negative`。`train112`、Case124–Case130 和全部负结果证据
继续保留；它们不得被删除、覆盖或静默改写。

Case130 checker 的 `status=pass` 只表示独立证据 checker 和 fail-closed 流程
正确，不等于代理模型资格通过。M4I 两个允许的 predictor 均未通过冻结点精度
Gate，因此：

```text
full-domain model lock = absent
selective model lock = absent
order model lock = absent
blind24 FEM = intentionally_not_run
```

Task004 关闭后不得运行新的 FEM、训练、阈值调整、blind validation 或第二轮
active learning。没有新的任务书和审阅，不得开始 Task005 FEM。详细身份与证据
入口见 `TASK004_FINAL_STATUS.json` 和
`TASK004_CONTROLLED_NEGATIVE_CLOSEOUT.md`。
