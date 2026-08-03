# Task004 Aggregate Level A qualification v4

完整 112 点 training-only OOF 已覆盖四个批准的局部候选和两种有限集成。
最佳 selection score 是 local RBF k24，但仍未通过完整 Level A；因此没有
创建 `ANGLE_AGGREGATE_MODEL_SELECTION_LOCK.json`。

详表与 hash-bound 结果见 `ANGLE_AGGREGATE_QUALIFICATION_CONTRACT_V4.json`。

| candidate | Aggregate Gate | supported-window-v3 | cross-fitted coverage | qualified |
|---|---|---|---|---|
| local RBF k24 | fail | fail | pass | no |
| local Matérn k24 | fail | pass | fail | no |
| local Matérn k32 | fail | pass | fail | no |
| degree-2 trend + local residual k24 | fail | fail | pass | no |
| latent median ensemble | fail | pass | fail | no |
| non-negative stack | fail | fail | fail | no |

这是假设固定的 full-domain 合同下的负结果，不是前向 FEM 失败；train112、
forward SHA 和 blind24 design 均保持不变。
