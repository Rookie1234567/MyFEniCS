# Task034 测试汇总（Review V4 candidate）

本轮只修改离线聚合、tracked compact fixture、机器可读结果、治理/能力文档、selective-merge 边界和测试；没有修改 Maxwell/Floquet/QEP/DtN/Hybrid 数值核心，因此未重跑已接受的重型 PDE。

## 最终 Gate

| Gate | command / scope | result |
|---|---|---|
| ABI | activate-myfenics + `/tmp/print_myfenics_abi.py` | `numpy.complex128`；PETSc 3.19.6；DOLFINx 0.10.0.post2；SLEPc 3.19.2 |
| governance/docs/hermetic targeted | test24 + test26 + test86 | 28 passed |
| Task034 suite | test73–test86 | 107 passed |
| no-artifact aggregation | test86 | 8 passed；临时 root 无 `benchmarks/artifacts`；JSON/CSV byte-identical |
| full repository | `pytest -q` in activated complex ABI | 503 passed，18 skipped，244.89 s |
| Ruff | changed aggregation/governance/doc tests | pass |
| compileall | `python -m compileall -q benchmarks src` | pass |
| whitespace | `git diff --check` | pass |
| Task035 Markdown | CommonMark + table parser | 42 `$$` delimiters；5 tables；15 unique DOI targets；pass |

## Review V4 新覆盖

- fixture 自带 generator version、field sources、40 个 artifact SHA-256、source SHA 与相对 evidence path；普通 build 不打开 artifact。
- no-artifact clean root 可确定性重建 tracked JSON/CSV；关键 schema 字段缺失 fail closed。
- `factor_nnz` 只表示 measured direct-factor `matrix_nnz_used`；Hybrid/无 inventory 为 null。
- p4/h3 Full3D 锁定 `3035.1390509350167 s` 和 `80.53771209716797 GiB`。
- 40 行 authority audit 记录唯一旧漂移行及两字段决策。
- governance protection 强制 same-task-branch review flow 与 final merge authorization。
- adaptive mesh/runner/compression/test group 保持 `research_only_do_not_merge_yet`。
- Task035 只做 planning/Markdown QA，未运行 code/PDE。

## 受控异常

DOI resolver 的额外在线 probe 因工具权限审批超时终止；WSL 内没有残留 `curl` 进程。15 个 DOI target 已由 Markdown parser 完整解析并通过格式/唯一性检查，但不把本轮在线可达性写成通过。
