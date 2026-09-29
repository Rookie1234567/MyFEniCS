# V31 选择性交接清单：正式结果未完成

本清单记录 V31 组件候选和唯一正式运行的实际边界。工作站迁移未获授权；自然序布局没有完整场资格，因此不能作为默认方案或已验证生产改动推广。

| 依赖组 | 内容 | 数值行为 / 证据 | 当前裁决 |
|---|---|---|---|
| production numerical/core | V31 H6 积分点自然序内部布局，来源于 `src/solvers/fullspace_n1e_sum_factor.py`、`fullspace_partial_assembly.py`、`physical_light_setup.py` 及显式 profile 接线 | 组件等价与短操作配对通过；完整残差检查只到 i112（普通迭代日志至 i113），残差 `2.714e-6`，没有 final/release/physical Gate | 保留在执行分支供 review；未取得完整场资格，不改 ordinary default、不向工作站推广 |
| reusable runner/watchdog | 既有 `scripts/run_case_in_user_service.sh` 与 physical-memory-pressure watchdog | 服务正确清理后代、记录整树 RSS；此次 operator 手动 stop 被如实分类 `USER_CONTROLLED_STOP` | 没有新通用 runner；不迁移本机运行结论 |
| checker/benchmark | `benchmarks/task39extra_v25_dynamic_checker.py` 支持版本化 backend/profile 检查 | 完整 checker 需要 worker final summary；中止运行缺少该文件，故 checker 未运行。另有 i112 residual NPZ 五项范数复核 | 不声称正式 dynamic checker PASS；工具实现留在当前分支，待 review |
| compact evidence/docs | V31 outcome、response、compact/checker records、run index 与本清单 | 所有状态包括 `USER_CONTROLLED_STOP`、未通过 residual 和 operator mistake 均保留 | 可供主控 review；与数值资格分开 |
| research-only | 固定形状矩阵乘法、局部批处理、流式端口路线 | 未采用或完整场未测；无生产性能资格 | 不提升为默认或工作站路线 |
| do-not-merge / do-not-promote | 对 V31 宣称完整离散通过、端到端提速、物理结果通过或跨机器可迁移；任何 master merge | R4 未完成；没有 R/T/A 或 final field | 不合并、不推广；需新的 review/用户授权后再决定 |

R3 的六组 H6 配对数据支持组件级候选，但不能外推为整场节省。watchdog RSS 峰值只比既有 V29 数值低约 2.1 MB，且本场中止，不能据此宣称内存收益。正式 run 身份、时间口径、资源误停说明及所有文件 SHA 见 [V31 outcome](projection_layout_v31.md) 与 [compact record](records/projection_layout_v31_compact.json)。
