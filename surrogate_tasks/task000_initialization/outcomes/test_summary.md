# Task000 测试总结

## Final checks

| 检查 | 结果 |
|---|---|
| Bash syntax：7 个 Task000 shell/hook scripts | PASS |
| Python `compileall -q src/forward_data` | PASS |
| Task000 + main preset + Case095/096 targeted pytest | `39 passed in 1.79s` |
| Case095 compact authority checker | PASS；19/19 record hashes |
| serial ABI / project MPC linkage / MUMPS | PASS |
| minimal complex FFCx JIT | PASS；2 x 2 / 4 NNZ |
| MPI2 common ABI + MUMPS + PEP | PASS |
| Linux CLI final dry-run | PASS |
| one 13.5 nm development FEM smoke | PASS |
| Windows PowerShell `Parser.ParseInput` | PASS |
| Git guard positive/negative simulations | PASS |
| `git diff --check` | PASS |

最终 pytest 命令只运行 pure-Python/contract tests，不启动 p6/h10 或其他重型 PDE。

## Preserved development failures and corrections

| 现象 | 分类 | 修正/结论 |
|---|---|---|
| system script `EXIT_CODE=141` | script pipeline bug | `awk` 不再 early-exit under pipefail |
| MPC Python metadata rejects license string | pinned build-tool incompatibility | scikit-build-core 0.11.1 (PEP 639 support) |
| first JIT form arity error | probe bug | use complex-safe `inner(u,v)`; JIT PASS |
| first development run missing PyVista | environment dependency gap | install fixed FEniCS PPA PyVista/Ubuntu VTK |
| first completed smoke marked physics fail | adapter field-selection bug | select authoritative auxiliary-DtN metrics and actual reduced residual |
| initial PowerShell file parser | WSL UNC access limitation | parse read-only Base64 text with `ParseInput`; PASS |

失败证据没有被写成成功，也没有以重跑 p6/h10、放宽 residual/physics Gate 或使用
swap 的方式绕过。

## Numerical smoke evidence

- residual `2.977956804883729e-14 <= 1e-8`;
- `R + T + A_balance` 与 1 的差小于 `1e-15`；
- `|A_volume - A_balance| = 2.50e-16 <= 1e-5`；
- child peak RSS 341,716 KiB；GNU time swaps 0；
- result identity为 `development_smoke_pass`，source dirty 被明确记录，未宣称 formal。
