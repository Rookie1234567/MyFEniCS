# Task006 Review Report V3：暂停 blind residual 重资格化并移交 Schneider-style objective-GP benchmark

## 1. 用户决策与正式状态

用户决定暂不继续 Task006 M3R 的两个 residual 失败点重资格化。本报告不否定 Review V2 的判断，也不改写任何既有证据；仅冻结当前状态并授权一个独立的新 benchmark。

```text
Task006 training qualification          = passed and locked
Task006 model lock                      = immutable, unchanged
blind FEM attempted                     = 36 / 36
blind measured_pass                     = 34
blind failed residual gate              = 2
complete blind geometries               = 11 / 12
Task006 final blind qualification       = incomplete / not determined
M3R residual retries                    = paused by user
formal inversion                        = not authorized
```

必须保留且不得修改：

```text
TASK006_MODEL_SELECTION_LOCK.json
TASK006_BLIND_FAILURE_REPORT.json
Case141 campaign / checker / original run directories
train37 immutable dataset
34 measured-pass blind records
2 original failed formal records
```

Task006 不得被表述为“代理已通过”或“代理已失败”。准确状态是：

```text
paused_blind_forward_incomplete
```

## 2. 暂停边界

在新的明确授权前，不得：

- 重跑 `117.5,17.25/A07` 或 `117.5,17.25/A09`；
- 放宽 `true residual <= 1e-9`；
- 修改模型锁、候选模型、S0/S1 合同或噪声合同；
- 将 34 条成功 blind 记录并入 train37 后重新调参；
- 以 11/12 恢复结果宣称完整 blind 通过；
- 开始 Task006 正式 Bayesian inversion。

## 3. 对新 benchmark 的数据授权

批准建立独立 Task007，研究 Schneider et al. 风格的 objective-GP Bayesian optimization。Task007 不训练多输出 Maxwell 前向代理，而是对每一组给定 synthetic measurement 单独学习标量目标函数：

\[
F(h,w\mid y_M)=\frac12\bigl(y_M-y(h,w)\bigr)^T\Gamma^{-1}
\bigl(y_M-y(h,w)\bigr)+\Phi_{\rm prior}(h,w).
\]

Task007 可只读复用：

```text
Task006 train37 的 37 个完整三照明 response tuples
Case141 中 11 个三照明完整的 blind geometries
```

`(117.5,17.25)` 因缺少 A07/A09，不得进入完整三照明 replay benchmark。

这些 Case141 记录在 Task007 中只能称为：

```text
external replay targets
```

不得重新称为 Task006 未泄漏 blind validation，也不得改变 Task006 的状态。

## 4. 移交结论

Task006 保持冻结。下一项工作转入：

```text
surrogate_tasks/task007_schneider_objective_gp_benchmark/
```

Task007 首轮应完全基于已有数据完成 objective construction、Gaussian-process regression、expected-improvement replay 和方法比较；不运行新的 FEM，不恢复连续角度代理，不修改 Task006 模型锁。
