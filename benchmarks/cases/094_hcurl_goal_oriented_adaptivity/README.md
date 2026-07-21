# Case094：H(curl) goal-oriented adaptivity（staging）

## 当前身份

```text
status = phase_a_in_progress
canonical = false
production_qualified = false
pde_run = false
phase_b_or_later_results = not_available
```

Case094 当前只是 Task035 Phase A staging case，用于保存环境、Task034 baseline 与
artifact descriptor 的可移植绑定。它不是冻结 benchmark，不包含 estimator、adaptive
cycle、p4 主线或生产结果。

## 当前证据

- `records/base_manifest.json`：tracked、clean-checkout hermetic 的 Phase A base binding；
- `records/phase_a_regression_failure.json`：首次旧 numbered-case 合同失败历史，永久保留；
- ignored 环境与 Task034 artifacts 只由路径和 SHA-256 descriptor 绑定。

## Checker

从仓库根目录执行：

```bash
source .venv/bin/activate-myfenics
python -m benchmarks.task035_case094
```

该命令只运行 hermetic Phase A checker，不读取 ignored artifacts、不启动 MPI、不组装
PDE。需要本机人工复核 ignored artifact 时必须显式使用 `--verify-artifacts`；该模式
不是 `test_command.txt` 的普通入口。

## 可用与不可用结果

当前可用：环境/base descriptor、Task034 compact reference binding、首次失败历史。
当前不可用：Phase B estimator fixtures、Phase C bake-off、adaptive cycles、p4/Hybrid
adaptive results、robust common mesh 和任何 production qualification。

## 升级条件

只有 Task035 Phase B–K 按任务书完成相应 fixture、mesh、数值和资源 Gate，并在 Phase K
冻结完整 Case094 benchmark 后，才能：

1. 从 `STAGING_OR_IN_PROGRESS_CASES` 移入 `QUALIFIED_OR_FROZEN_CASES`；
2. 将 `canonical` 或 `production_qualified` 改为 true；
3. 启用正式 case 的 22 项参数表、全部章节、record/run/test 合同；
4. 宣称 Phase B 或后续 measured results 可用。

升级前不得把本 staging scaffold 冒充 canonical Case094。
