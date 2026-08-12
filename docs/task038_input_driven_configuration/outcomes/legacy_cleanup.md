# Task38 T9：legacy cleanup 与当前入口收敛

## 1. 范围与身份

本记录保留 T9 阶段的 pre-commit evidence。T8 source SHA 为
`7f57f7a7dab45c7c8cae67bf0f5271db110aa339`；T9 审计基线为该 SHA。T9 四提交与
T9 分支状态见 §7。本轮只删除已由全仓调用图证明不可达的旧副本，
并把当前导航改成显式 `.dat` 入口；不运行 PDE/MPI，不改求解器数学或 retained
research/history replay。

## 2. 已删除的不可达旧副本

| 删除路径 | 当前调用图证据 | 替代入口 | 满足 §15.4 的理由 |
|---|---|---|---|
| `src/runners/run_3d_airbox_old.py` | `rg` 在当前 `src/`、`src/test/`、`benchmarks/`、`scripts/` 无外部引用；仅旧模块组内部互引 | [`run_3d_cases.py`](../../../src/runners/run_3d_cases.py) 与当前 Stage adapter | 不可达、无当前 replay caller；Git 历史可回看 |
| `src/solvers/solve_airbox_maxwell_3d_old.py` | 仅被被删旧 airbox/common 组引用 | 当前 Stage1 solver/common flow | 不可达旧实现，不是 current solver |
| `src/solvers/solve_maxwell_3d_common_old.py` | 仅被被删旧 stage-2/stage-4 组引用 | 当前 `common_3d_*` flow | 不可达旧公共副本 |
| `src/solvers/solve_maxwell_3d_stage_2_no_grating_old.py` | 无当前调用者 | Stage2 current runners/adapters | 不可达旧 Stage2 副本 |
| `src/solvers/solve_maxwell_3d_stage_4_grating_old.py` | 无当前调用者；Case021/030/080 使用 retained/current runner | retained preset 与现有 Stage4 solver | 不可达旧 Stage4 副本 |

删除的是一组互相引用、没有当前入口的历史代码副本；当前 adapter 仍调用现有
runner/solver，因此不会改变求解流程。

## 3. 保留的 research/history preset 与调用者

| preset | 保留理由与调用者 |
|---|---|
| `3d_stage4b_demo_direct_h5` | retained `PRESETS_3D`/`PresetInfo`；Stage4 demo replay；`test_27`/`test_267` 合同，demo h5 另由 `test_13` 覆盖 |
| `3d_stage4b_demo_direct_h3` | retained Stage4 demo replay；`test_27`/`test_267` 合同 |
| `3d_stage4b_demo_mumps_ooc` | Case030 的 OOC research/replay 身份；`test_27`/`test_267` 合同 |
| `3d_stage4b_demo_mumps_blr` | Case030 的 BLR research/replay 身份；`test_27`/`test_267` 合同 |
| `3d_target_grating_direct_h5` | Case021 与 Case080 target replay；`test_27`/`test_267` 合同 |
| `3d_target_grating_direct_h3` | Case021 与 Case080 target replay；`test_27`/`test_267` 合同 |

这些 preset 继续由 `Stage4GratingInputs3D`、`target_stage4_config`、
`PresetInfo` 和原 parser 支持；`Stage4GratingInputs3D` 另受 `test_178` 保护。
没有被放入普通 public dat mapping，也没有改变数值、资源 profile 或 replay 行为。

## 4. 明确未删除项

| 项目 | 处置 |
|---|---|
| `src/runners/run_cases.py`、`run_3d_cases.py` | 保留为 internal/research compatibility 与当前 adapter 复用入口 |
| `port-order-count` 及相关端口逻辑 | 保留；仍有 2D/历史端口测试和 solver 语义依赖 |
| Task37/Task37c runner、authority、compact records | 保留为已审研究证据和 current adapter 依赖 |
| 其他 `*_old`、benchmark replay、历史 tests/reports | 未证明不可达，不删除 |
| retained preset、Stage4 factory、solver/common 数值模块 | 不属于本轮重复旧模块删除范围 |

## 5. 当前文档迁移边界

当前 quick-start、参数地图和 2D walkthrough 的普通用户路径改为
`scripts/run_case.py <case.dat>` → `load_and_resolve` → Task38 adapter →
现有 runner/solver。11 个 migrated dat 和 MPI identity 由输入文件决定；普通
入口不再教用户修改 ACTIVE、Python dataclass 或给 public dat 追加
`--results-root`/物理 override。

当前导航仍保留六项显式 research/history replay
和资源警告。五个较长旧教程只增加当前入口 banner，正文作为历史资料保留；旧
task/report/test 文档没有批量改写。

## 6. T9 Gate（历史 pre-commit 记录）

实际结果：focused documentation/preset suite 为 **295 passed、2 skipped**；Ruff
check、T9 阶段规定的定向 Ruff format check、compileall、`check_benchmarks --no-write`（302/302）、
JSON parse、98 条 Markdown 相对链接和 `git diff --check` 均通过。一次并行启动
曾触发 PMIx segfault，但没有有效测试结果；随后改为串行 qualified activation
后通过。T9 阶段未运行 PDE、MPI formal 或 full pytest；T10 最终 full Gate
已在 `test_summary.md` 与 `summary.md` 记录。本节仍是 T9 阶段快照，最终提交
状态见 §7。
T9 的定向 format 结果不等同于 T10 扩大审计：T10 对 base..de2e 的 30 个 A/C/M
Python 文件复核为 27 个通过、3 个 base/current 均不合格，按 accepted inherited
formatting qualification 记录，详见 `test_summary.md`。

## 7. T10 回填的 T9 四提交与最终身份

| 顺序 | commit | 内容 |
|---|---|---|
| A | `56d9c6b4a58842effd86fccf2b69ba99f1e02bd9` | retire direct `src.main` runner facade |
| B | `815d7b653062d0dfcdbc9caef28b7b0bbc3b4202` | remove unreachable legacy 3D modules |
| C | `2378718d41ca8aa5ae8885fe8d961cb5febbb650` | migrate current guides to dat inputs |
| D | `de2e1880fa90a442996ada58ea321c774752a5ca` | record legacy cleanup |

T9 最终 HEAD、local tracking ref、remote branch 均为
`de2e1880fa90a442996ada58ea321c774752a5ca`，ahead/behind=`0/0`，worktree clean。
这四个提交未触碰 canonical Task37 worktree，也未合并或推送 master。并行 PMIx
尝试的 segfault 仍是无有效结果的诊断事实；串行 qualified pure Gate 的
295 passed/2 skipped 与 302/302 benchmark check 才是 T9 Gate 结果。T10 的
full Gate 另见 `test_summary.md`，不由 T9 阶段记录代替。
