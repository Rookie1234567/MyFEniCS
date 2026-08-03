# Task004 M4A/M4B/M4C test summary

已执行：

- surrogate CPU venv 下 `py_compile`（angle dataset/models/pipeline/api、Case125 checker）；
- `git diff --check`；
- Case125 independent checker：`pass`，96/96 raw exact coverage、hash、shape/dtype、身份和所有 forward Gate 通过；
- response-blind mask-topology coverage：24 validation signatures 全部被 train96 覆盖，5 个 CV fold 的 test signatures 均有 training-side support；
- 4 个 frozen local spatial windows：每个 8 点，hash 与 training tuple 绑定；
- training-only 5-fold CV，GP warnings 未静默丢弃并写入 fold metadata；
- API fail-closed guard 的静态检查：缺少 model lock/qualification 时拒绝公开加载。

本轮未运行：Task003 Round3/validation、任何 Task004 blind-validation FEM、主动学习 FEM、PCE/GP 之外训练、angle DOE、Fisher、geometry sensitivity、inversion。由于 training Gate 未通过，不生成 `ANGLE_MODEL_SELECTION_LOCK.json`、`ANGLE_MODEL_QUALIFICATION.json` 或 blind24 package。
