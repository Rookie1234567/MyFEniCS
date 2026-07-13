# 选择性整合执行日志

## 分支基线

| 项目 | 值 |
|---|---|
| base | `master@0465b5f` |
| branch | `codex/20260712-task28-stage-consolidation` |
| Task28 task commits | `e14c802`, `d0f0b76` |
| whole research branch merge | 否 |

Windows 初次创建 worktree 时遇到长路径限制，设置仓库本地 `core.longpaths=true` 后成功创建干净 worktree。主工作树中的用户未提交文件与 `papers/` 未触碰。

## 执行表

| 来源 | 动作 | 结果 |
|---|---|---|
| Task021-Task027 核心文档 | 选择性归档 task/review/summary/gate/merge/next/response | 58 份核心文件进入当前分支，raw_runs不复制 |
| Task026 `condensed_dtn.py` | 抽取并保留Task027生命周期修正 | 集成为稳定模块 |
| Task027 `spectral_schwarz.py` | 只抽取fixed coarse和physical slab部分 | 新建 `physical_slab_two_level.py` |
| Task027 research runner | 不复制 | 用无任务脚本依赖的benchmark runner重写 |
| Task021/023 target assembly | 最小抽取 | 新建 `stage4_runtime.py` |
| spectral/GenEO/HPDDM | 排除 | 仅在历史文档中保留负证据 |
| ordinary direct entrypoints | 不修改 | 默认行为保持不变 |

## 重构结果

成功 profile 不再依赖 Task020-Task026 的研究 runner 链。稳定模块之间只通过 PETSc Mat/Vec、配置和 RuntimeStage4System 传递数据。完整研究分支没有 merge 或 cherry-pick。
