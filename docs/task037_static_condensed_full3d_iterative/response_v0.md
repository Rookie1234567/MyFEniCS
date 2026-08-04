# Task037 response_v0

本文回应 Task037 的最终受控阶段。本文内容的 parent 是
`3abe278600aac6c63d81e876f9198e976c5505e9`；文档自身的提交 SHA 由提交报告给出，
不在可变文档中制造自引用 hash。

## 1. branch、source 与环境

执行分支为 `codex/20260803-task37-matrix-free-iterative-development`，parent
source clean SHA 为 `3abe278600aac6c63d81e876f9198e976c5505e9`，工作树在文档提交
前 clean。资格化环境使用项目 `.venv`、PETSc `complex128/int32`，MPI/PETSc/
DOLFINx 为同一 Linux ABI。ordinary defaults 未改变。

## 2. direct authority

F0 是当前源码上的唯一 p6/h10/S/MPI8 direct authority，source
`03f4fa02aece62bb2f193c01616177bffff0aa51`。reported/full true residual 为
`2.8094057923e-11`，12/12 powers、12/12 boundary amplitudes、R/T/A 和 energy
closure 通过；process-tree peak `15.2550010681 GiB`，wall `370.18 s`。详见
[direct_authority.md](direct_authority.md) 和 tracked F0 record。

## 3. assembled operator 与 recovery

静态凝聚先在 cell-local 层消去 interior unknowns，再以 active trace 加 80 个
auxiliary rows 组成 51272-row global system；recovery 将 trace 解恢复为 173802 个
full FE entries。F3 assembled FGMRES 使用 right, unpreconditioned FGMRES，restart
90、rtol `1e-6`、16 slabs、75D coarse、ILU(0) factor-only。

## 4. trace support 与 subdomain

F2 的 trace-aware partition 用 physical z-support 选择 16 个 overlap `0.25` slabs，
union 覆盖 `51192` active rows，auxiliary rows 不进入 subdomains。F3/F5b 的
partition、coarse rank `75/75`、16 ILU 和 no-global-factor inventory 均由 tracked
records 保存；不把 raw row numbers 当作跨 partition identity。

## 5. 20/100/200 screens

| screen | endpoint residual | decision evidence | peak |
|---:|---:|---|---:|
| 20 | `0.0302833465991175` | negative max-it 20；RTA not run | `13.2211914063 GiB` |
| 100 | `0.000608485581260` | last-40 ratio `0.1852104694` | `12.9641036987 GiB` |
| 200 | `3.5885919793e-5` | predicted `323` it / `473.764 s` | `12.9706878662 GiB` |

三项均为 fixed-candidate screen-only evidence，不是 official convergence。

## 6. full solve、向量、通道与物理量

F3 assembled full 与 F5b 均为 337 iterations，reported、condensed true、full
augmented true 均约 `9.8166e-7`，full-FE 也低于 `1e-6`；official result、RTA、
12/12 powers、12/12 boundary amplitudes 通过。F3 的 `R_total/T_total/A_balance`
为 `0.0007628816329 / 0.6027016326 / 0.3965354857`，F5b 为
`0.0007628816329 / 0.6027016326 / 0.3965354857`；F5b energy closure
`-5.3943261e-10`。

Task 7.1 raw indexwise vector Gate 仍失败：相对 direct active `1.4210359558`、
recovered FE `1.4121310623`，限值 `1e-5`。F5b 与 F3 的对应差约 `1.55e-14` 和
`1.42e-14`，只支持 ownership-order inference，不能替代 direct Gate。
12-channel 明细只保留在 [matrix_free_report.md](matrix_free_report.md)。

## 7. assembled 与 matrix-free action

F5a 证明 cell-local Schur action 与 assembled fine action 的相对误差不超过
`1e-11`。F5b 使用 profile
`assembled_setup_then_static_local_schur_matrix_free_solve`，fine-action error
`9.2309237020e-16`；先 assembled setup、再在 outer KSP 前释放 `F`，并非
never-materialized。F5b 的 global direct factor count 为 0、global Schur 未 materialize。

## 8. MPI identity

F5a 组件层已做 serial/MPI2/MPI4 owner/scatter/action tests；formal authority 和
F3/F5b full solve 只做 MPI8。MPI4 formal full candidate `not_run`，不能把组件 MPI
证据写成 final MPI4/8 identity。

## 9. simultaneous memory 与 wall

| path | RSS authority | worker PSS / USS | wall |
|---|---:|---:|---:|
| F0 direct | `15.2550010681 GiB` | `13254.321 / 13047.027 MiB` | `370.18 s` |
| F3 assembled | `13.6522331238 GiB` | `11980.911 / 11776.828 MiB` | `410.546 s` |
| F5b released | `13.6580085754 GiB` | `12058.898 / 11854.363 MiB` | `396.603 s` |

全部 formal full runs swap 为 0；F5b warning 触发但 14 GiB termination 未触发。F5b
比 direct 只减少约 `1.597 GiB`、约 `10.5%`，没有达到 `10.30 GiB` resource-positive
门槛。因此本轮迭代法没有达到显著节省内存目标。

## 10. tests

唯一 full suite 的 parent source 是 `237e9abd2043fd5ec424de4d9f224cfd771bf8d9`：
`828 passed, 42 skipped, 2 failed, 0 errors`，pytest `1297.70 s`、shell
`1298.58 s`、exit 1。两个旧合同由 `3abe2786` 的 targeted test26=`14 passed`、
test53=`3 passed` 收口；没有第二次 full suite，也不能把原始 exit 1 改写成 PASS。
完整测试边界、Case098 恢复证据和 format baseline debt 见
[test_summary.md](test_summary.md)。文档提交后不再跑 pytest。

## 11. changed files、line counts 与 commits

相对 `origin/master...3abe278600aac6c63d81e876f9198e976c5505e9`，Task37 共
`38 files, 6216 insertions, 147 deletions`：

| group | files | insertions / deletions |
|---|---:|---:|
| production core `src/solvers` | 8 | `1157 / 75` |
| runner/watchdog | 2 | `547 / 69` |
| tests `src/test` | 12 | `1437 / 3` |
| case/evidence `benchmarks/cases` | 9 | `1362 / 0` |
| docs `docs/task037...` | 7 | `1713 / 0` |

关键提交包括 F0 `03f4fa02`、F2/F3 `815f3f31`/`72e241c9`/`f35169cd`、F5a
`fa331d0f`、F5b lifecycle `b7a4c362`/`c986b583`/`5e02eda9`、F5b outcome
`237e9abd` 和测试合同 `3abe2786`。本阶段只新增本文件、`summary.md` 与
`test_summary.md`，不修改既有报告、records 或源码。

## 12. final classification

最终分类为 `PARTIAL_WITH_CONTROLLED_NEGATIVES`：solver residual status pass，
physical observables status pass，12/12 + 12/12 channel status pass；但 raw vector
indexwise Gate fail、resource status negative，故 combined Task37 numerical status
为 `not_pass`。F4、F5c、F6 均 `not_run`。

## 13. unresolved 与 Task037b 边界

下一步若另立任务，应先做峰值对象生命周期归因，再评估真正 no-global-F 和 scalable
auxiliary multigrid；Task037b 只建议，不启动。Hybrid、hp、0.7 nm、F4/F5c/F6 均不在
本轮范围。不建议 merge-to-master；等待 ChatGPT review，不自动合并。
