# 仓库工作原则

<!-- REPOSITORY_WORK_PRINCIPLES_BEGIN -->

> **治理性约束：本节不得删除。**
>
> 本文档是 MyFEniCS 项目的长期协作与审查契约。任何修改必须经过用户明确同意，并由 ChatGPT 在对应任务分支中审查。不得在 README 精简、文档重构、分支整理或阶段合并中删除、弱化或绕过这些原则。

## 1. 任务开始前

1. 开始新一轮任务前，必须读取上一轮任务目录中的 `review_report*.md`、`response*.md`（若存在）或 `outcomes/summary.md`。
2. 同时读取本轮任务目录中的 `task.md`，不得只根据聊天摘要、旧 README 或任务名称执行。
3. 若上一轮存在未关闭的 Gate，必须先说明本轮是继续关闭该 Gate，还是明确建立新任务；不得静默跳过。

## 2. 分支与角色

4. **ChatGPT 不创建执行分支；执行分支由 Codex 创建。**
5. Codex 应从任务书指定的 base 创建独立执行分支；除任务书明确允许外，不得直接在 `master` 上开发。
6. ChatGPT 负责任务书、远程审查和 `review_report_vN.md`；Codex 负责实现、测试、运行和 `outcomes/`，并通过 `response_vN.md` 回应审查。
7. Codex 不得删除或改写 ChatGPT 已提交的 `task.md`、`review_report*.md`；需要纠正时，应新增 `response_vN.md` 并提交相应代码、测试和文档修正。

## 3. 结果与文档闭环

8. 完成工作后，必须把任务结果写入本轮任务目录的 `outcomes/`，至少包含 `summary.md`、Gate 决策、测试证据、changed files 和下一步判断。
9. 审查后，`review_report_vN.md` 必须保存在同一个任务目录；若审查要求修改，应在同一执行分支继续修正并提交 `response_vN.md`，无需因为普通审查修正重新开分支。
10. 普通运行产生的完整场、网格和日志默认保存在 `results/`；正式 benchmark 的重型 artifact 保存在 `benchmarks/artifacts/`。两者都不得作为大体积文件提交 Git。
11. Git 中只提交必要的轻量 JSON、CSV、Markdown、配置、compact residual history 和可复现元数据；矩阵、因子、OOC scratch、VTU/XDMF/HDF5、完整场数组和大型缓存必须忽略。

## 4. 合并与生产边界

12. **failed solver code 默认留在对应 research branch，不合并 production。** 文档、review、精简 outcomes 和理论笔记可以选择性合并。
13. 禁止整体合并大型 research branch；必须从 clean base 通过 `selective_merge_manifest` 抽取经过验证、可维护的最小组件。
14. ordinary solver default 不得静默改变。新的 direct、iterative、condensed 或 workstation profile 在完成审查前必须保持显式 opt-in。
15. 未通过最终 review 之前，不建议合并到 `master`；最终状态必须明确为 `pass`、`pass_with_qualifications` 或 `fail`。
16. 若审查后发现问题，可在同一任务分支持续修改和复审；只有新增物理功能、新求解算法、大规模参数研究、ordinary default 变更或超范围架构重写才拆分为新任务。

## 5. 数值可信度

17. solver 成功必须使用 full explicit true residual 判断，不能只使用 preconditioned/KSP residual、相对零解 improvement 或内部 projected residual。
18. official R/T/A 只能从通过 residual Gate 的场计算；probe-plane Fourier、sampled flux 和其他近似量只能标记为 diagnostic，除非独立任务重新证明其 official 资格。
19. direct/iterative、auxiliary/condensed、MPI1/MPI4 或缓存复用结果必须有明确等价性、R/T/A、能量闭合、内存和环境证据；不得把未运行项写成通过。
20. 失败结果同样必须保留准确结论，禁止把研究正信号包装成 production 能力，也禁止因后续文档精简而删除关键负结果边界。

## 6. 不可删除保护

- 根 `README.md` 与 `docs/README.md` 必须保留 `REPOSITORY_WORK_PRINCIPLES_BEGIN/END` 保护区及本文件链接。
- `src/test/test_24_repository_work_principles.py` 会检查保护标记和关键条款；删除或弱化这些原则应导致测试失败。
- 若确需修改原则，必须同时更新本文件、两个 README 保护区、保护测试和对应任务审查记录，并获得用户明确同意。

<!-- REPOSITORY_WORK_PRINCIPLES_END -->
