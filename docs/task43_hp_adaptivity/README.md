# Task43：面向三维 Maxwell 的自适应 h/p 网格

| 项目 | 本轮权威 |
|---|---|
| 执行分支 | `task43_hp_adaptivity` |
| 建立日期 | 2026-10-22 |
| 源码基线 | `task40para_phi90_mesh_modes_direct@405e3aff42ac421a4c99315df1ed9b96941ecbe4` |
| 当前状态 | `TASK_DEFINED / NUMERICAL_WORK_NOT_RUN` |
| 第一目标 | 在新 phi90、50×50 nm 周期、17×20 nm 光栅模型上，建立实际求解验真的局部 h/p 闭环 |
| 第一验证波长 | 13.5 nm；小规模 direct 作数值核验 |
| 后续方向 | 自适应空间的迭代接线；通过前置条件后做一个 0.7 nm 缩比 pilot |

**本任务研究怎样用合适的局部单元尺寸 h 和局部多项式阶次 p 达到所需精度，并核算完整代价。** h 加密把单元变小，适合难以用一个光滑多项式表示的局部结构；p 加密提高单元内部的表达能力，可能更适合光滑区域。两者都会改变全局方程和求解器的成本，必须实际求解才能确认收益。

## 阅读入口

1. [task.md](task.md)：科学问题、模型、阶段、接受规则和验收合同。
2. [AGENTS.md](AGENTS.md)：本目录执行规则；任务书与工作站实施之间的边界。
3. [baseline_audit.md](baseline_audit.md)：主线判定、两条 NN 路线、旧 hp 与 dot 的固定 SHA 证据。
4. [codex_handoff.md](codex_handoff.md)：工作站接入与可直接交给 Codex 的指令。
5. [branch_provenance.json](branch_provenance.json)：建分支来源与尚未运行状态。

## 与其他研究线的关系

- `task40para` 是本次新几何、直接解和方向网格对照的基线。
- `task41extra_phi90_p50x50_g17x20` 继续代表 0.7 nm 迭代求解研究；不与 Task43 整分支合并。
- `task42_neural_coarse_inverse` 与 `task42extra_feinn_5nm` 的当前研究可暂停投入；本次建立 Task43 不删除或改写它们的远端历史。
- 旧 Task35d/e 数值核心按函数与依赖选择性复用；dot 的新 hp 报告是设计证据，其中未同步的外部源码不冒充可直接继承的实现。

本次提交只建立任务与审计文档，没有运行 PDE，没有完成新的 h/p 资格化，也没有修改 ordinary solver defaults。实际结果由 Codex 写入本目录 `outcomes/` 与 `response_v1.md`，并同步仓库模型总账。
