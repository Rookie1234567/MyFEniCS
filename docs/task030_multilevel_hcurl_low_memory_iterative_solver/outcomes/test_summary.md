# 测试摘要

最终状态：Review V1 P0 回归通过；没有重跑 h5/h3/h2 重型算例。

## 静态与合同

- Ruff format/check：Review V1 修改的 benchmark checker 通过；
- Python `compileall`：通过；
- repository/documentation/preset/benchmark/Task30 retrospective：32/32；
- benchmark checker `--no-write` 与 normal：203/203；
- normal checker 连续生成稳定：summary SHA-256 `6beb18d01ac06aad8c5a22ac2ede23ed596b6b47fa5deaac9f254c081656e185`，Gate report SHA-256 `fbecda5b5c6f93fb25c66a992a5987af2c7f57193328a790782069aa2f7e3f2d`；
- tracked JSON 757 个与 benchmark CSV 354 个 parse：通过；
- UTF-8 读取审计：通过；
- `git diff --check`：无 whitespace error，仅 Windows CRLF 提示。

## DOLFINx 容器回归

- serial focused（Task026 condensation + Task027 physical slab + Task030 H(curl)）：23/23；
- MPI-2 focused：每个 rank 23/23；
- MPI-4 focused：每个 rank 23/23；
- full `src/test` discovery：157 tests passed，10 skipped。

MPI-4 首轮 focused test 暴露了“子域数少于 rank 数时空 owner 调用 PETSc collective 次数不一致”的自旋问题。修复仅在 owner 数不均时插入空索引占位，使所有 rank 同步调用；16 slabs/MPI4 每 rank 4 个子域的正式数值路径不变。精确复现、完整 Task23 及所有 MPI1/2/4 回归均已通过。

Review V1 更正后再次运行相同 focused matrix 和 full discovery，结果保持不变；Case060 新增 Gate 还实际验证三份 source artifact SHA-256。用户本地 `papers/` 和 Task023 raw runs 未进入测试或提交范围。
