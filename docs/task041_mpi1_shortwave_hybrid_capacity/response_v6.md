# Task041 Response V6：BAL-H 几何谓词修复与 D1e 重跑准备

## 1. 本轮结论

D1d 的失败不是内存、swap、MPI 或数值收敛失败，而是 top side 的几何构造实现错误：对带有较大绝对坐标的 Q1 单元直接计算 Jacobian 的绝对坐标差，浮点抵消被错误判为非 affine，触发 `BAL_H requires affine geometry`。

修复已在提交 `8ad30732a2753b902f5722c6e7c7647365ab0744` 实现并推送。几何导数的两条使用路径现在都先减去首节点坐标再做 contraction；原有 `128*eps*scale` affine 判据、有限值检查和正 determinant 门保持不变。因此该修复只改变平移不变性/舍入判定，不改变物理模型、离散参数或正几何约束。

## 2. 验证与身份

- native ABI：`float64` real、`complex128` PETSc scalar、`int32` PETSc index、数学线程为 1。
- serial targeted test：3 passed；MPI2 targeted test：每 rank 3 passed。
- `ruff check`、`compileall`、`git diff --check`：通过；`ruff format --check` 仍报告既有未格式化文件，本轮未做格式化重写。
- 修复源码 SHA256：`physical_balanced_positive_kernel.py` = `cdab7a45621bb6c750f832a448fd99d78d3243cac44c84ab755cb697b50bcbb7`；测试 = `56e3c1d2ea04171fcf60d8e87bd072fc9aa68c9d0e79dc7096677bcdbae6fd9e`。
- 复现脚本已重建并保存，SHA256 = `d676fd3d53ff6a802386b273b41121a88f81155aa1f824f9cfc8475f5cd52a50`；旧 D1d 的 source SHA `0ede1df5...` 证据不跨源复用。

证据索引为 `d1e_evidence_index.json`；它明确区分 session-only 测试输出与已落盘文件，不伪造 raw log。旧 D1d 运行和失败证据保留，尚无 solver pass 结论。

## 3. D1e 重跑边界

D1e 固定为 2 nm / p6 / h1.5 / M1200 / MPI8 / CPU 1--8 / 每 rank 数学线程 1，使用当前 source identity 和新的 fresh QEP producer；不复用旧 source 的 packet，不伪造 source identity。新配置继续引用旧 D1c compute-wall ledger，但不覆盖旧 D1d 记录。

内存合同保留 hard `1759218604442 B`，warning `1539316278886 B` 仅 advisory，实际 MemAvailable reserve `412316860416 B`；job swap、new global swap、pswp、numerical、identity 和时间门均由既有监督路径检查。CPU23 邻项目为受保护的独立作业，实测 worker `402163` 与父 `402153` 均限定在 CPU23、`VmSwap=0`，不停止、不改绑、不计入 Task041。

截至本版文档提交时，D1e 尚未 dispatch，fresh QEP 尚未启动，因而没有新的 solver pass、run summary 或生产结论。完成文档提交/推送后，还必须重新绑定最终 source SHA、做一次最终 fresh preflight，并按批准的精确 systemd argv 只启动一次。

## 4. 交付状态

本版只记录修复、验证、身份和重跑边界；旧历史与负结果不改写。D1e 的最终状态以新 unit 的 invocation、public runroot、MPI8 rank 证据、QEP manifest、资源峰值和 solver/数值 gate 为准；systemd 接受本身不等于成功。
