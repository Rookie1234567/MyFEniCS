# Task43 执行规则

本目录与根 `AGENTS.md`、`docs/AGENTS.md` 一起使用。当前用户明确要求从合适的现存分支建立 Task43 并准备任务书；本次由 ChatGPT 创建远端分支和初始文档，是该具体授权下的操作，不修改仓库长期角色分工。

## 权威与范围

- 唯一执行分支为 `task43_hp_adaptivity`。源码基线固定为 `405e3aff42ac421a4c99315df1ed9b96941ecbe4`；不得改从 `master`、Task41 或 NN 分支另起同名项目。
- 先完整读本目录 `task.md`、`baseline_audit.md`、`codex_handoff.md`，再读任务书指定的旧 review/response 与需要迁移的源码。
- 本目录尚无新的 review 或 response。后续最新正式 review 优先于已被回应的旧阶段安排；不要把别的 Task 的最新 review 当成本任务执行授权。
- 本任务是新的研究范围，不是冒充完成 Task35e、Task40para、Task41 或 Task42 尚未关闭的 Gate。普通实现错误、格式错误、路径错误、局部资格化缺项应就地修复并继续。
- 科学决策和数值阈值在 `task.md` 维护；执行环境与实测结果写入 `outcomes/`。不要建立平行 addendum、重复 controller、campaign/receipt 平台或逐 case 复制 runner。

## 代码与证据

- 数值核心进入 `src/adaptivity/` 或相应 `src/solvers/`；runner 负责配置与记录，checker 读取原始数据重新判定。
- 旧代码仅迁移本任务必需的函数及最小依赖，保留新基线修复；不整分支 merge，也不整文件覆盖后续改动。
- 不通过伪造旧 `task035e_scope` 绕开 90k DoF 等旧预算。建立显式 Task43 profile，保留旧 profile 的行为和必要回归。
- p3 local hp、multilevel local h、变阶空间上的迭代求解都要分别验真；文件存在、能够装配、global p3 能跑不能替代这些证明。
- 失败场只作诊断；official R/T/A 必须来自通过完整 true residual Gate 的场。两网格差称为场差或误差估计，不称已知连续真误差。
- 测试围绕改变的数值路径与具体风险；按仓库测试金字塔执行，不因无关文档变更重复昂贵 PDE。

## 工作区与资源

- 优先复用 NN-V2 对应工作站项目，但先核实路径、worktree 注册、进程占用和未提交内容；禁止 `reset --hard`、`clean`、强推或无差别 stash 来腾目录。
- 不切换或修改其他活动任务工作区，不终止邻近任务。Task40/41 既有的并行授权不自动扩展为 Task43 重型并跑授权。
- 使用工作站已资格化的 complex128 ABI 栈；本任务不要求环境重装、另建 Codex 账号或更换客户端。
- 每次正式数值运行后更新本目录 outcomes 与 `docs/development_model_registry.md`；最终审查前完成 `docs/development_progress.md` 的实质回顾及 selective merge manifest。
- 大场、网格、矩阵、因子与完整日志进入 ignored artifact 目录；Git 只提交可复核的轻量证据。保留旧 NN 本地 artifact 的 provenance，不把新结果写回旧任务目录。
