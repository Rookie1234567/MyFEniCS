# Task003 Review Report V3：冻结四维全局代理基线，转入二维角度代理

## 1. 审阅结论

本轮批准保留 Task003 M3T、Round 2 的全部实现、有限元结果和负结果证据，但**不批准继续 Round 3，也不批准解封原 16 个 frozen-validation target**。

当前 Task003 的正式状态冻结为：

```text
status = paused_research_baseline_not_qualified
training_rows = 112
frozen_validation_rows = 16
selected_training_cv_candidate = G1_constant_gp:features=B:jitter=1e-08
MODEL_SELECTION_LOCK = absent
production_surrogate = not_qualified
Round3_FEM = not_authorized
frozen_validation_access = forbidden
angle_DOE = not_authorized
inversion = not_authorized
```

用户已明确调整研究路线：先建立一个只以入射角为变量的二维代理，测试在固定中心几何下对范围内任意角度的预测能力。因此批准新建：

```text
surrogate_tasks/task004_nominal_geometry_angle_surrogate/
```

Task004 是新的、独立的数据集与模型资格化任务，不得静默复用或改写 Task003 的训练/验证合同。

---

## 2. 本轮结果的客观含义

Round 2 又增加 8 个 Ny4/p5 Full3D 样本，全部 measured-pass；原 96 点测试行固定后，学习曲线为：

| 模型 | 训练点 | R NRMSE | T NRMSE | A NRMSE |
|---|---:|---:|---:|---:|
| G1 constant GP | 96 | 0.036934 | 0.013005 | 0.045047 |
| G1 constant GP | 104 | 0.018357 | 0.012899 | 0.025823 |
| G1 constant GP | 112 | 0.017376 | 0.019641 | 0.029793 |
| G2 degree-2 trend + residual GP | 96 | 0.042149 | 0.015890 | 0.051803 |
| G2 degree-2 trend + residual GP | 104 | 0.031387 | 0.014127 | 0.039407 |
| G2 degree-2 trend + residual GP | 112 | 0.028193 | 0.024360 | 0.042599 |

第一轮 96→104 对 R/A 有明显帮助，但第二轮 104→112 并未形成稳定、单调、全目标一致的改善：R 略有改善，T/A 反而恶化。标准 112 点 training-only CV 仍未通过 aggregate hard Gate。

因此现有证据只能支持：

1. 四维响应的全局趋势可以被 GP 学习；
2. 单一全局 stationary GP 在低掠射、cutoff 和普通平滑区域之间存在明显折中；
3. 仅凭 96/104/112 三个规模，不能可靠外推“再增加多少点必然通过”；
4. 不应继续以每轮 8 点的方式无条件追加 Round 3。

本轮负结果不能解释为“未来五六个结构参数无法代理”。它说明的是：当前同时把 `h,w,grazing,azimuth` 放入一个全域代理，并要求整个四维域都达到统一反演级误差，任务定义和模型结构不匹配。

---

## 3. 为什么先做二维角度代理

新任务固定：

```text
height_nm = 120.0
width_x_nm = 17.0
wavelength_nm = 13.5
incident_polarization = S
forward_model = Full3D static uniform N1curl p5/h10/Ny4
```

只学习：

```text
(grazing_deg, azimuth_deg)
    -> aggregate R/T/A
    -> fixed-order outgoing S/P powers
    -> predictive uncertainty
    -> analytic power-carrying mask / region status
```

这样做有四个目的：

1. 将输入维数从 4 降为 2，直接检验角度响应本身是否可被稳定插值；
2. 分离“角度引起的 cutoff/nonstationarity”与“几何参数维数”两个问题；
3. 在二维平面上画出可审计的响应、误差和不确定度热图；
4. 为后续建立角度灵敏度代理、局部 Fisher 排名和固定角度的结构参数代理提供基础。

必须注意：**固定几何的角度响应代理本身不能直接判断哪些角度最适合反演高度和宽度。** 真正的角度设计还需要 `dy/dh`、`dy/dw` 或等价 Jacobian/Fisher 信息。Task004 第一阶段只验证“任意角度响应预测”；灵敏度层必须在 Task004 通过后另行授权。

---

## 4. 旧数据的使用边界

### 4.1 Case115 的 80-angle map

Case115 曾完成中心几何的 p5/h10 80-angle map，但它生成于生产网格升级为 Ny4 之前，属于后续已 hard-quarantine 的旧 Ny3 离散身份。

因此：

```text
允许：用于历史趋势、采样设计和回归差异诊断
禁止：进入 Task004 正式训练或验证数组
```

### 4.2 Task003 的 Ny4 四维数据

Task003 数据确实来自当前 Ny4/p5 forward model，但其中 `h,w` 随样本变化。不得简单删除几何列后将所有样本当作角度训练数据，否则几何效应会成为未建模噪声。

现有记录中恰好满足 `(h,w)=(120,17)` 的点可以作为历史 anchor/对照；由于 Task004 必须绑定新的 clean implementation SHA 和独立 dataset identity，这些历史记录默认不进入正式 Task004 训练集，除非后续任务书明确建立了同 SHA、同 observable、同 mesh、同 source identity 的合法复用合同。

### 4.3 Task003 frozen validation

原 16 个 frozen validation 继续永久封存于 Task003，不得因新任务启动而读取或改作 Task004 validation。

---

## 5. 对 Task004 的授权边界

批准 Task004 执行：

1. 建立新的二维角度 design、dataset schema 和 checker；
2. 使用 Ny4/p5 production Full3D 从头生成固定中心几何数据；
3. 比较有限的二维代理候选；
4. 完成独立 blind validation；
5. 输出任意域内角度的预测、预测标准差和物理状态；
6. 生成 R/T/A 与主要衍射级的二维响应图、误差图和不确定度图。

禁止 Task004 自行执行：

```text
height/width inversion
formal Fisher angle ranking
P-incident surrogate
wavelength variation
geometry variation
Task003 frozen-validation access
Task003 Round3
neural-network/model-zoo sweep
Ny3 data mixing
```

---

## 6. Task003 的最终保留价值

Task003 不删除、不重写。它作为以下研究证据保留：

1. 96/104/112 四维全局代理学习曲线；
2. 两轮主动加点的正负效果；
3. aggregate composition、P2 sidewise power reconstruction 和 GP 优化实现；
4. 全局 stationary GP 跨多个物理区域时的局限；
5. 将来设计六维结构代理时避免重复相同错误的基线。

Task004 可复用 Task003 的通用 `src/surrogate/` 组件，但不得继承其模型锁、验证集或数据集身份。

---

## 7. Codex 下一步

Codex 应停止 Task003，并转入：

```text
surrogate_tasks/task004_nominal_geometry_angle_surrogate/
```

完整阅读该目录 `README.md` 与 `task.md` 后，从 M0 开始执行。Task004 首轮结束后提交规定的 outcomes、Case123 和 `response_v1.md`，然后停止等待审阅。
