# Response V32：Review V29 / V31 投影布局收口

## 最终状态

H6 自然序布局候选通过组件代数核对和短操作配对，但唯一正式运行在 i112 完整残差检查后被我手动停止（普通迭代日志记录到 i113），最后完整显式原 A6 残差为 `2.713995416229632e-6`，高于 `1e-6`。没有最终释放后残差、场或 R/T/A，所以不能写成正式求解通过，也不能写成求解失败。

停止原因是我的错误：我把 cgroup `memory.current` 的 8 GiB 数值误认成 Review V29 硬停止线。Review V29 实际要求沿既有 physical-memory-pressure 动态 cap 运行，并明确说 V29/V30 的 RSS 成绩不是停止线。记录的启动 cap 为 `13,358,809,088 B`，正式 watchdog 整树 RSS 峰值为 `7,324,389,376 B`；停止前 cgroup current/peak 为 `8,602,890,240/8,603,148,288 B`，但它与整树 RSS 是不同口径，且并未触及实际启动 cap。原始服务摘要如实标记 `USER_CONTROLLED_STOP`。这是 Codex 的误停，不归类为资源停止或 solver negative；我为此负责并已在 outcome 中明确记录。

Review V29 只允许一场 fresh formal PDE；这次场已启动并中断，未获授权进行第二次尝试。任何继续求解都需要新的明确授权。

## R1–R5 对应

| 阶段 | 完成事实 | 状态 |
|---|---|---|
| R1 资源复审 | V30 RSS 账本与首次 instrumentation 失败按原样保存；归因有限，不扩大诊断 | `PARTIALLY_ATTRIBUTED` |
| R2 动态重审 | V30 版本化 checker 通过有限动态账本复审；旧 V25 `backend_identity` FAIL 和 worker 五个 `NOT_ATTEMPTED` checkpoint 保留 | `DYNAMIC_PASS_EVIDENCE_LIMITED`；旧 FAIL 保留 |
| R3 候选 | H6 自然序组件等价通过；两个保存向量的中位收益分别约 6.2% 和 18.0%，6/6 配对胜出；固定矩阵乘法关闭 | 选择自然序，仍需完整场资格 |
| R4 正式场 | V31 输入、源码和 ABI 身份正确；完整残差检查至 i112、迭代日志至 i113 后由 Codex 错误触发 user-service stop | `USER_CONTROLLED_STOP`，完整 Gate 未完成 |
| R5 独立收口 | 对 i112 保存残差包重算五个向量范数，均与记录完全一致；缺少终态 worker summary，完整动态 checker 未运行；更新报告、总账与推送 | checkpoint 核验完成；端到端 checker/正式结果不具备 |

## 测试和检查

- 正式运行前针对性测试：`63 passed, 1 skipped in 29.84 s`；动态 checker 单测：`17 passed in 0.13 s`。它们是在正式运行前完成，不能替代未完成的 PDE Gate。
- 相关源码 `compileall`、输入 validate-only 和 dry-run、qualified WSL ABI preflight 均通过。Ruff 在资格环境中未安装；full repository pytest、MPI2/4、CI 未运行/未声称。
- i112 residual NPZ 离线范数复核：原 A6、端口闭合、内部残差、原生恒等式、Schur 端口恒等式五项重算值与保存标量的差均为 0。
- 最终文档改动后没有重跑 pytest；只做 JSON 解析、哈希复核和 `git diff --check`。

## 交付身份

运行源码 SHA=`baeb0b3a7e74e3b77705e70918772d1dcacb9639`；输入 SHA=`b19bf2d6a0a5f7a45a9910e3d3f25b1e3a896daa2205e78327be8f169cc9c7d0`；物理模型 SHA=`0875aaf070d88732b09ead8c55a7d4c28dd75f9b329e90f35fea984a0b7464e6`。完整数值和资源边界见 [V31 outcome](outcomes/projection_layout_v31.md)，本地测试状态见 [test summary](outcomes/test_summary.md)。选择性交接清单明确哪些项仍未资格化，见 [V31 handoff](outcomes/selective_workstation_handoff_v31.md)。

所有工作仍在 `task39extra` 执行分支；普通默认未变、工作站未迁移、`master` 未合并。此次收口提交推送到 `origin/task39extra`，等待主控 review。
