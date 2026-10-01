# Task40extra dot 云端并行任务书

## 身份与目的

- owner：`dot`
- execution_branch：`task40extra_dot_parallel_cloud`
- parent_branch：`task40extra_0p7nm_engineering`
- branch_base_sha：`c786e87d03976a52f57d1e7f69a3c63f992afe90`
- execution：dot 自身云端 Linux/CPU 环境；环境资格以每份实际记录为准

依据用户明确授权新建此独占分支。只可修改此新分支及 dot 自己云端电脑中的文件和代码；不得修改其他 GitHub 分支、用户电脑、工作站或其他执行会话。本任务单独建立组件诊断范围，不接管父 Review V2 的笔记本正式 campaign。

## 首要工程目标与时间约束

用户首要目标是尽快得到约 2 TB 整机物理内存内可用的 0.7 nm 目标模型解，不能只优化装配时间而忽略完整求解和容量瓶颈。历史单次求解 48 小时目标暂记为继承背景，适用日期及当前承诺待澄清；不把它擅自当成本支线的新硬停止线。组件实验必须说明对完整流程哪个成本项有帮助、尚缺哪些证据；完整目标资格仍须另行具备正式环境与验证，不能由本支线局部测试授予。

## 要回答的问题

父任务已给出缩小 0.7 nm 模型的离散解，但真实边界截断、跨网格体积误差和目标规模容量仍有独立缺口。本支线用有界的组件实验辅助理解这些问题：先检查组件的输入、编号和数学作用，再报告速度、载荷和不适用边界。局部矩阵或端口测试只能证明该组件的行为，不能证明整个三维电磁场正确。

允许：只读检查冻结源码；有限 CPU 组件诊断；真实尺寸或明确标记的合成代数组件；准确几何/模式库存/局部矩阵机制检查；脚本与紧凑 JSON/CSV/Markdown 证据归档。计算前冻结对象、维数、输入、随机种子（如适用）、阈值、内存口径和停止条件。

排除：完整 G0/G1/目标尺度 PDE、全局生产因子、生产资格、continuum convergence、约 2 TB 可行性承诺；不降低父任务物理/残差/identity Gate，不把合成通道当真实物理模式，不切换 ordinary default，不开 PR 或 merge。

## 目录与证据合同

1. 可复用数值实现进入合适的 `src/` 模块并附测试；`benchmarks/` 只存参数化编排、checker、配置与轻量证据，不另藏数值核心。
2. 优先复用现有 runner；若新增诊断脚本，解释原入口为何不足，并将模型差异放在参数/config 中。
3. 每份结果记录完整 source SHA、源码取得方式和必要文件 SHA256、脚本/输入 SHA256、环境包版本与 ABI 可用性、命令、MPI/线程、时间/资源范围、退出状态和实际数值。
4. 使用 `measured`、`derived`、`predicted`、`not_run`、`failed`、`controlled_stop` 区分数据；缺失写 null 和原因。残差与 official-result identity 不适用时明确说明，不能填假通过。
5. 发布顺序为：冻结 source/脚本身份 → 运行与检查 → compact records → `outcomes/summary.md` 和 `response_vN.md`；阶段收口同步本分支的 `docs/development_progress.md`，正式/重型模型还需模型总账。
6. 不提交 secrets、venv、JIT/cache、矩阵/因子/完整场或大 raw 二进制。保留失败证据，重型 artifact 留 ignored 目录并记录 hash。

## 发布与审阅

仅 fast-forward 更新本独占分支，不强推、不重写历史。远端 connector 文档提交记录为 connector publication，不假称本地 canonical worktree 已验收。若以后使用本地 clone 推送，须按仓库规则验证 canonical clone/worktree、SHA、upstream 与 ahead/behind；无法验证则报告该 Gate。

每阶段报告完整远端 HEAD、changed files、测试和文档渲染状态。GitHub rendered view 未验证时保留明确缺口；文件提交成功不等于文档或数值 Gate 全通过。最终等待审阅，不操作其他分支。

## 后续协作（2026-10-01 用户补充）

Codex 正式任务进行时，dot 继续本分支有界云端并行工作；本批 V1 组件交付完成不代表目标模型问题结束。每轮 Pro 审查最多提交三次，优先一次完整证据包，只在必要时补充；三次内形成最终审查及执行说明。此处不授权修改其他分支或用户电脑。用户明确许可的指定 ChatGPT/Codex 对话转达由协调方管理，不扩大本分支代码写入范围。
