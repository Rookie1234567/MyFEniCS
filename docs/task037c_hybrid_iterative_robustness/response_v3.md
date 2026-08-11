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
- `test_251_task037c_full3d_watchdog_contract.py` 与
  `test_252_task037c_hybrid_direct_contract.py`；它们未合入本次
  integration master；
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

本节是当时的 pre-documentation 快照；最终执行结果见 §7。

数值证据仍绑定 source anchor `f82cfe1186ded74e19b5bc8ebb374b6401d46d0a`
及其 raw artifact SHA。后续 integration commit 只改变合入组织和测试/文档
载体；若数值核心再发生变化，旧 authority 必须失效并重新资格化。

## 6. canonical worktree 规则

canonical repo 中旧 Task37 worktree 的用户修改保持原样，未被
checkout、stash、stage、reset、clean 或覆盖。最终发布前必须从 canonical
registered worktree 完成 fetch、remote branch 核对、完整测试与普通推送；
独立临时 clone 不作为最终分支权威。分支名必须逐字符匹配任务书，并在
preflight 中检查近似冲突。

## 7. 最终化证据（full pytest 与唯一 clean-SHA anchor）

### 7.1 三层数值 provenance

最终数值结论分三层保存：

| 层 | 证据 | 结论边界 |
|---|---|---|
| 当前 integration clean-SHA own Gate | `ec11350e51ab5cbc0397dbeef8098334b8ad74bb` 上唯一 phi=0、MPI8、M120、exact one-cell traction、two-pass anchor | 五项 residual、traction、recovery、RTA、orders、canonical、selected fields、identity、release 与 swap 全通过；这是当前 SHA 的 fresh own anchor |
| 数值依赖身份 | 下列10个 numerical blob 与 f2d7719 数值父 SHA逐字节相同 | 证明 integration 只重组已审算法；不把不同 SHA 的结果伪装成同 SHA comparator |
| 既有 f2d authority | f2d7719 的 direct/Full3D compact records 与 checker 证据 | 继续保留其正式 direct/Full3D 结论；本 anchor 未另造 cross-SHA formal comparison |

10-file blob identity（当前 integration SHA 与 f2d numerical parent 的 SHA256
相同）：

| file | SHA256 |
|---|---|
| `benchmarks/run_task037b_hybrid_iterative.py` | `2f6fc607115be24b1d548f2535977e87b30e48ca33849aeb30e678908482cad2` |
| `benchmarks/run_task037b_hybrid_iterative_watchdog.py` | `b2cc910e2f6727fc9d7586ec21ace9f42faa2c3d1b0ea3b506ba7f9543e516c1` |
| `benchmarks/task037c_robustness.py` | `310bfd2b06980f99b540d242d9396710fdb8e1bd340e6bd8db53ff80b33d8898` |
| `src/coupling/hybrid_one_cell_exact_traction.py` | `fcccd14d973340ebd6469c42fba25b9bff5ff48a03f87a44a209a27471875e87` |
| `src/coupling/hybrid_one_cell_exact_traction_builder.py` | `7e8e43a62c202ad2bddba7653807d5c3f90e36843d345f8fed48e07bb3df5f11` |
| `src/coupling/hybrid_internal_modes.py` | `5fa0fff08f170ca2d324e3ff55e516c9c552fa54d213b071781f943d4c433661` |
| `src/modes/stable_propagation.py` | `852877d4b18be5321f6c440728faa649867d18489fa89d328af1372796890af3` |
| `src/solvers/hybrid_local_dtn_woodbury.py` | `97be8a1f376ab2e715fc8b5ced3b283cebb37ba6e49b6cb6655b22e31a7c8cf1` |
| `src/solvers/hybrid_static_field_recovery.py` | `4b1d5a7ae89637d6f4ad6f7d3bd14952407c4f93298d19f9accab83c1920c753` |
| `src/solvers/one_cell_trace_schur.py` | `c6aa6b2cb999ff60ca065d3785300c4f9e178ac0cd2ecf33d1a51abdd972f620` |

### 7.2 测试与静态 Gate

| Gate | 实测结果 |
|---|---|
| 唯一 full repository pytest | `python -m pytest -q`；exit 0；955 passed、48 skipped；1405.55 s |
| full pytest log | `/tmp/task037c_r7_full_pytest_ec11350e.log`；1165 bytes；SHA256 `55062ac5e2a4eae158fbacf299df8a5b4ad2bc7157dd426c4565702b950ff880` |
| 实际 integration focused 集合 | 122 passed in 12.28 s |
| Case102 更新后的轻量命令 | 80 passed in 5.17 s；未引用 251/252 |
| MPI2 lightweight real fixture | 每 rank 2 passed in 2.34 s |
| MPI4 lightweight real fixture | 每 rank 2 passed in 5.49 s |
| Ruff check | 全部 changed Python passed |
| Ruff format | 其余19个 changed Python passed；两个 inherited baseline exception 保持 base=fail、after=fail |
| compileall / diff-check | passed |

`outcomes/test_summary.md` 中的 251/252 命令只属于 source research branch
的历史记录，不表示当前 integration master 提供这些文件；Case102 的
`test_command.txt` 已改为当前实际存在的集合。

### 7.3 唯一 MPI8 anchor

绝对路径：
`/home/Projects/MyFEniCS/benchmarks/artifacts/task037c/integration_ec11350e/anchor_phi0_m120_two_pass`

| field | measured |
|---|---:|
| model / phi / M / MPI | `full3d_one_cell_exact_schur` / 0° / M120 / 8 |
| source | `ec11350e51ab5cbc0397dbeef8098334b8ad74bb` |
| iterations / reason | 1771 / 2 |
| reported / global / bottom / top / modal residual | 3.061687968e-9 / 3.061685500e-9 / 4.880148491e-9 / 2.428263992e-9 / 2.638224713e-15 |
| exact traction bottom / top | 4.880148491e-9 / 2.428263992e-9 |
| R / T / A / A_volume / closure | 0.365625786729 / 0.012990632358 / 0.621383580913 / 0.621383576625 / -4.287146194e-9 |
| orders / mode identity | 80 unique orders; bottom/top 40/40 |
| modal build logical/raw | bottom/top 480/960 each |
| direct factors / nested KSP | 0/0; false |
| operator / release | matrix-free; recovery, lifecycle and final release pass |
| process-tree peak / stage / swap | 6559.023 MiB / setup / 0 |
| watchdog / online SHA256 | `8c3e715686a3076df6715136928dc877a816682cf3c7a1c3b199046e54ed0a32` / `8e08d00971144b7f24a4581f3b33f0941cbcde034be2e9078f443eae68406dec` |

watchdog status 是 `watchdog_pass_awaiting_offline_checker`，own numerical Gate
与资源进程组 Gate 已通过；MPI8 6144 MiB preferred 未通过，分类为
`resource_unqualified`，不是数值失败。没有为该 anchor 伪造 Full3D/direct
同 SHA comparator。

### 7.4 分支协调实证表

| 项目 | 实证 |
|---|---|
| 根因 | Task37b/c 曾在独立 temporary clone 推进，canonical clone 未及时 fetch/建立 local tracking ref；同时存在含/不含数字0的 `task037b` 近似分支名 |
| legacy 旧名 | `98046b7297b5de23d121b60898afe9e9007abc6e` 是 active `00293d95419f0435407c04bc5312ed1e61e20415` 的 strict ancestor；left/right unique=0/55，无旧名独有提交 |
| archive ref | `codex/archive/20260807-task037b-legacy-checkpoint` @ `98046b7297b5de23d121b60898afe9e9007abc6e`；local/remote/upstream 同 SHA，ahead/behind=0/0 |
| active refs | Task37b @ `00293d95419f0435407c04bc5312ed1e61e20415`、Task37c @ `f82cfe1186ded74e19b5bc8ebb374b6401d46d0a`；两者各自 local/remote/upstream 均 0/0 |
| canonical master | 初始 local master `f8fab5`，比 origin/master 落后28；发布边界是最终 docs-only child 的 fast-forward SHA |
| 用户 dirty | canonical 旧 Task37 的 `static_modal_coarse_gate.py` 与 `test_251_task037_e1_modal_basis_gate.py` 全程原样保留，未 checkout/stash/stage/reset/clean |

### 7.5 发布边界

本节记录的是最终 docs/case finalization 的父级 code/test anchor
`ec11350e`。随后只允许一个 docs/case-only finalization commit；该提交
不改变 numerical code/config/threshold，因此不重跑 full pytest 或 PDE。最终
提交完整 SHA、普通 fast-forward push、canonical fetch/prune、master 与
active/archive refs 的 0/0 身份在执行回报中给出，不把文档自身的 SHA
自引用写入本文。
