# Task001 测试汇总

最终改动后的验证结果：

| 验证 | 结果 |
|---|---|
| Task000/001 + condensation + Task035c + Case095/096 targeted suite | 68 passed, 4 skipped |
| Task000 environment scripts | 3 passed |
| order extraction targeted subset | 5 passed（包含在 68 中；含 lossy flag 与显式零功率语义） |
| 真实 0.5° lossy record R/T consistency | exact match |
| Case110 compact checker generation | pass；42 artifacts = 37 pass + 5 failed |
| Case110 `--check-records` | pass；selected HF rank 2, rho -0.147932, cond 1.220835 |
| M6 五点 watchdog | 5 completed，return code 0，zero swap |
| MPI2 ABI | ranks 0/1 均 complex128 / int32 / DOLFINx 0.10.0.post2 |
| compileall | pass |
| `git diff --check` | pass |
| Ruff | unavailable in qualified `.venv`；未宣称通过 |

主要 suite 命令：

```text
python -m pytest -q \
  src/test/test_surrogate_task000_forward_data.py \
  src/test/test_surrogate_task001_foundation.py \
  src/test/test_114_task035b_cell_static_condensation.py \
  src/test/test_115_task035b_assembly_time_condensation.py \
  src/test/test_179_task035b_hybrid_static_condensation.py \
  src/test/test_181_task035c_p6_h10_runner_gates.py \
  src/test/test_182_task035c_channel_resource_checker.py \
  src/test/test_case095_compact_evidence_contract.py \
  src/test/test_case096_compact_evidence_contract.py
```

4 个 skip 为 suite 中已有的条件性 skip，没有隐藏失败。compact checker 对每个 raw
`execution.json`/`solver_record.json` 重新计算 SHA-256，拒绝 baseline 混源，并逐字比较 tracked
records；37 个 measured pass 的 source、solver gates、zero swap 与 cleanup aggregate gates 均为 true。
