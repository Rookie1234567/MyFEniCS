# Task37c 选择性合入与分支协调记录

## 1. 目的与身份

本文件记录 Task37c 从独立执行 worktree 合入 canonical MyFEniCS 的选择性清单，
不改写既有数值结论，也不把研究扩展提升为 production-qualified。

- canonical base：`origin/master` = `ee779be42004d555f9aba21bf54f8ca8d3287ff4`
- source research branch：`codex/20260810-task37c-hybrid-iterative-robustness`
- source evidence/code anchor：`f82cfe1186ded74e19b5bc8ebb374b6401d46d0a`
- integration worktree：`/tmp/myfenics-task37c-selective-integration-20260811`
- integration branch：`codex/20260811-task37c-selective-integration`
- pre-documentation code HEAD：`8c1102cd`

`response_v1.md` 保持 source 字节身份不变，SHA256 为
`ec123a14bea5509bfb5698af1d9f176a8f3f1037fa30f4bb5250e7ca457f35e6`。

## 2. 已选择的提交与依赖顺序

1. `c5754726` — `docs(repo): require canonical task worktree tracking`
2. `769da770` — `feat(task037c): integrate exact one-cell traction oracle`
3. `cb628aef` — `feat(task037c): integrate fixed two-pass hybrid correction`
4. `f2827d7e` — `fix(task037c): preserve dynamic Woodbury mode count`
5. `8c1102cd` — `bench(task037c): integrate explicit robustness qualification`

这些提交均为独立提交；没有 amend、rebase、whole-branch merge 或 bulk cherry-pick。

## 3. 选择性合入清单

### 可复用数值核心

- exact one-cell H(curl) traction column oracle、endpoint lift、congruent
  entity transfer 与 row identity；
- `full3d_one_cell_exact_schur` 的显式 opt-in coupling/recovery 路径；
- fixed two-pass side residual correction：
  第二次只计算固定的 `P(r-A P r)`，不引入 nested KSP、第三次 pass 或新 PC；
- Task37c profile、MPI/phi/M 参数透传、动态 40/42 external Woodbury mode
  合同；
- ordinary Task37b/Frozen M10 默认路径仍保持 scalar、单次 fixed action 和原参数。

### checker、case 与证据

- `benchmarks/task037c_comparator.py` 只读取 hash-bound records，不求解；
- Case102 的 README/config/schema/expected/test command；
- 两份 compact records：MPI8 three-way qualification、MPI1 identity/resource；
- Task37c 全部 outcomes、`response_v1.md`、`response_v2.md`；
- 本次 `response_v3.md` 记录分支协调，不在文件中自引用尚未生成的自身提交 SHA。

## 4. 明确排除

本次选择性合入没有带入：

- Task37c Full3D/direct 专项 heavy qualification machinery；
- `run_task033_full3d_watchdog.py` 的大段历史变更；
- raw mesh/field/matrix/factor/timeline artifacts；
- M200、额外角度或偏振、0.7nm、Task36/Task35 无关 campaign；
- ProjectedTwoPortSchur、capacity/POD、channel adjoint、新 PC 或 fallback
  框架；
- 任何 production-qualified 声明。

## 5. 测试与证据边界

截至 pre-documentation code HEAD，C1/C2/C3 的 focused tests、动态
40/42 Woodbury 合同、C3 runner/profile 合同、Ruff、format、compileall 和
`git diff --check` 已通过。C4 的 checker、Case102 JSON 和 documentation
contract 会在最终文档提交前继续执行；最终 full repository pytest 只能在
所有代码/测试合同完成后运行一次。

数值证据仍绑定 source anchor `f82cfe1186ded74e19b5bc8ebb374b6401d46d0a`
及其 raw artifact SHA。后续 integration commit 只改变合入组织和测试/文档
载体；若数值核心再发生变化，旧 authority 必须失效并重新资格化。

## 6. canonical worktree 规则

canonical repo 中旧 Task37 worktree 的用户修改保持原样，未被
checkout、stash、stage、reset、clean 或覆盖。最终发布前必须从 canonical
registered worktree 完成 fetch、remote branch 核对、完整测试与普通推送；
独立临时 clone 不作为最终分支权威。分支名必须逐字符匹配任务书，并在
preflight 中检查近似冲突。
