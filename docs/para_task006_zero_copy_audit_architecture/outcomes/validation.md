# Task006 validation

| 检查 | 结果 |
|---|---|
| complete `src/test` | **218 passed, 12 skipped** |
| MPI2 borrowed/proxy qualification hook | 每 rank **3 passed** |
| MPI4 borrowed/proxy qualification hook | 每 rank **3 passed** |
| Task006 Ruff scope | **All checks passed** |
| compileall | **PASS** |
| `git diff --check` | **PASS** |
| Case095 heavy artifact ignore | **PASS**, `.gitignore:58` |

正式数值证据：

| 阶段 | clean SHA | 结果 |
|---|---|---|
| P0 baseline | `9822bc5d84375bf1cd3039aec7ca1e849413c0ed` | numeric/RTA/memory/no-swap PASS |
| P1 borrowed action | `0b20f2554a9cc0526efa893f941174fb81918472` | 16/16、64 probes、`<=1e-12` PASS |
| P2 Q0 calibration | `ac039bd` | expected Gate failure；12/12 unusable |

P2 worker 的非零退出码是“没有 usable selected family”的显式返回。它完整写出
calibration record，不是异常退出、OOM、deadlock 或卡住。
