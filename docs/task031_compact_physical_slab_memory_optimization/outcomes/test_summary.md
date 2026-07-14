# Task031 测试总结

## 实现提交前验证

- Ruff：通过；
- `compileall`：通过；
- exact condensation + physical slab：serial、MPI2、MPI4 通过；
- matrix-free fine action：assembled action 相对误差 `<1e-15`，MPC slave unit rows 已覆盖；
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
