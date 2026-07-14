# Task031 测试总结

## 实现提交前验证

- Ruff：通过；
- `compileall`：通过；
- exact condensation + physical slab：serial、MPI2、MPI4 通过；
- assembled-F-free public form action：assembled action 相对误差 `<1e-15`，MPC slave unit rows 已覆盖；
- no-double-destroy / `require_f` / `release_f` lifecycle：通过；
- full unit：165 passed，10 skipped；
- benchmark checker：203/203 passed；
- diff check：通过。

## 文档/Case070 收口后的最终验证

```text
ruff = pass
compileall = pass
focused Task031 + documentation contracts = 18 passed
full unit = 172 passed, 10 skipped
MPI1 condensation + physical-slab = 19 passed
MPI2 condensation + physical-slab = 19 passed on each of 2 ranks
MPI4 condensation + physical-slab = 19 passed on each of 4 ranks
benchmark checker = 258/258 passed
JSON/CSV parse = pass
diff check = pass
tracked tree after final commit = pass (only pre-existing user-local untracked directories remain)
```

第一次 MPI smoke 使用旧简称 `test_22_condensation/test_23_physical_slab`，只产生 module-not-found 命令错误，未执行数值测试；更正为真实模块 `test_22_condensed_dtn/test_23_physical_slab_two_level` 后 MPI1/2/4 全通过。该命令失误不隐藏，也不计为代码回归。

正式 h5/h3/h2 数值 run 已全部从 tracked-source-clean implementation SHA `45a0fc6e...` 完成，不能由后续文档提交重写 provenance。

## Review V1 文档加固验证

```text
master sync = origin/master b7e0d14 merged; planning documents preserved
focused documentation + Task031 contracts = 21 passed
full unit in myfenics-stage4:task28 = 175 passed, 10 skipped
benchmark checker = 258/258 passed (--no-write)
Task31 JSON/CSV parse = 14 JSON + 4 CSV passed
Task31 wrapper --help = pass
Ruff = pass
compileall = pass
diff check = pass
formal h5/h3/h2 rerun = not required by Review V1 / not performed
tracked tree after final commit = pass (only pre-existing user-local untracked directories remain)
```

本轮唯一 Python 行为变化是 Task31 sampler wrapper 的 `certify_pc` 默认从 true 改为 false，使报告给出的 FGMRES 推荐命令不会错误强制固定线性认证；底层 worker 对所有非 FGMRES outer KSP 仍自动 certification 并 fail closed。三份正式 lightweight record 的 worker command 均未传 `--certify-pc`，核心 solver 数值路径未修改，因此保留 clean SHA 的正式 run provenance。
