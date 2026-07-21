# Task034 测试汇总（Response V5 final gate）

本轮只修改离线聚合、tracked compact fixture、机器可读结果、能力/路线文档、selective-merge 交付和测试；没有修改 Maxwell/Floquet/QEP/DtN/Hybrid 数值核心，因此未重跑已接受的重型 PDE。

## 最终 Gate

| Gate | command / scope | result |
|---|---|---|
| ABI | activate-myfenics | numpy.complex128；PETSc int32；petsc4py 3.19.6；DOLFINx 0.10.0.post2；SLEPc 3.19.2 |
| no-artifact aggregation | test86 | 10 passed；临时 root 无 benchmarks/artifacts；JSON/CSV byte-identical |
| governance/docs + Task034 | test24 + test26 + test73–test86 | 129 passed |
| manifest exact coverage | origin/master vs final staged tree | 170 manifest rows；168 changed；143 include；25 exclude；2 identical already-on-master |
| full repository | pytest -q in activated complex ABI | 505 passed，18 skipped，244.80 s |
| scoped Ruff | changed Review V4 Python files | pass |
| compileall | python -m compileall -q src benchmarks | pass |
| whitespace | staged + working git diff --check | pass |
| Task035 execution | planning package only | 未运行 Task035 code/PDE |

## Review V4 新覆盖

- 18 条 accepted Hybrid 记录逐条通过 artifact SHA-256 binding；elements 为 bottom/top 三轴 cell count 各自乘积之和。
- 全部 40 行中，任何 fe_dofs > 0 的 Full3D/Hybrid 行均不存在 elements == 0。
- fixture metadata 明确区分 reviewed one-time extraction、fixture schema 和不读 artifact 的 output aggregator。
- no-artifact clean root 可确定性重建 tracked JSON/CSV；关键 schema 字段缺失 fail closed。
- capability matrix 区分旧 p2/MPI4 iterative profile 与 Task034 Case093 p2/p3/p4、representative MPI。
- 当前路线文档不再冻结 Task036；后续任务按 scalable modal、low-memory Hybrid iterative、wavelength continuation 描述。
- manifest/changed-files exact checker 要求每个真实 changed path 恰好一行，额外 already-on-master 文件必须存在且内容一致。
- adaptive mesh/runner/compression/test group 保持 research_only_do_not_merge_yet。

## 说明

全仓 ruff check . 额外发现 15 条本轮未修改文件中的既有 lint debt（主要位于 diffraction_3d.py、full3d_reference.py 等）。Review V4 要求的 scoped Ruff 已通过；为避免越权修改数值核心，本轮未扩张范围修复这些历史问题。
