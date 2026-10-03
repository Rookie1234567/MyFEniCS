# 恢复环境后的 C1 候选源码

本次保存一个可以在干净源码上重新生成证据的候选入口。当前仅完成源码审查和 79 项元数据/NumPy 合约测试；实际有限元、JIT、p6 组件及 p4 求解均为 **NOT_RUN**。测试通过不代表有限元资格。

基线为远端 `77520e2d9e3e6e1ef45b7693bd45ea5be621afe1`，对应树 `8abc60305f2c9d1b9b7b023c5491b252f7f510ae`。恢复后的本地初始提交为 `130dcbae2c5a3423117d100e420a55a772b3a620`，树相同，旧本地提交图和原始数值数据没有恢复。

## 两项资格各自成立

1. **p6 组件**：同一完整三维 80 单元网格、532 个手动物理端口和同一个实际载体，比较原有稠密 H/Hhat 与恢复后的紧凑表示。保留全部 36,000 个内点自由度、非零端口 RHS、完整缩聚/恢复、实际 MPC 场以及制造解的原方程残差。独立检查器从保存的原始单元张量重新计算。物理 DiXiB 可能很小，另设具有实质非零耦合的代数负控；不改动物理算子的数值来制造敏感性。
2. **p4 链**：先绑定同一新源码/环境下通过独立检查的 p6 组件，再运行原有稠密 H/Hhat 端口表示和完整 Ny 参考组装的四个 y 块及完整原始三维 regular/notch 检查。保留全部 8,640 个内点 RHS、四种载荷及全部 532 个模式输出。FE/缩聚及 q 矩阵使用现有稀疏路径，不创建完整 p4 稠密全局 FE 矩阵，也不声称做了全局 p4 direct 对照。这项资格不证明紧凑 p4 quotient 或 p6 全局迭代链。

两项均使用原来的缩放 7/135 几何、lambda0=0.7、phi=5、manual M=9/N=3 和原来的两单元 notch。不是原始 50×25×140 nm 的大模型验证。

## 保持的数值门槛

- p6 action/recovery：1e-11；原方程残差：1e-10；独立纯代数恒等式：1e-12
- p4 保留已有 symmetry、每块泄漏、真实原方程残差、恢复、模式和必要输出门槛
- 近零输出另加固定补充检查：参考归一化幅值≤1e-8 时，绝对归一化误差≤1e-12；不替代上述任何门槛
- E/幅值和原生缩放 H 以非零入射 E0 归一化；原生面通量以 nm² 面积乘 |E0|² 归一化，不声称是 SI 安培/米或瓦特
- 保存的只读 LU pivot 先检查范围并制作私有、可写的 int32 副本

## 运行及存储前提

新官方隔离环境当前仅通过导入、complex128/int32/MPI1 公共 API 检查。激活脚本使用进程内 UCX_TLS=self 和单线程；不修改 HOME、网络、安全设置或系统 MPI。冷 JIT 在监督器内执行，实际单元类别数量在分配缓存前计数并进入资源门槛。

候选研究上限为每个 worker/checker **3 GiB、4500 s、zero swap、MPI1、单线程**。启动前需满足已有动态物理内存余量策略，并再容纳声明上限和 128 MiB 证据余量。p4 四个因子的额外总策略预算仍是 512 MiB；未知 LU fill 不等于已保证的内存上限。未压缩原始数组的导出预算为 512 MiB，实际类别较多时会受控停止，未假设压缩比或最终上传大小。

首次 imports-only dry admission 曾被 ABI 文件哈希门槛阻止：UCX 的 stdout 诊断混入了脚本捕获的哈希字符串。收据实际字节未变。修正把导入断言和独立 stdlib 哈希计算分开，诊断保留，导入失败明确返回失败；两个 shell 回归用模拟解释器检查该边界，不称作 MPI/FE 资格。该失败摘要保存在同目录记录中。

实际 C1 运行仍等待父任务数值 admission 和原始证据持久保存方案获准。完整归档需要包含原始数组、成员形状/类型/哈希清单、输入/源码/环境/监督器及独立检查器收据，随后从持久存储下载到新的空目录并逐项复核。完成该步骤之前，局部 worker/checker PASS 不称作持久完整资格。

## 固定入口

源码冻结后，把 EXACT_LOCAL_HEAD 替换为实际本地提交；恢复图与远端提交的对应关系单独记录。

```bash
source scripts/task40extra_cloud_recovery/activate_fresh_cloud_complex.sh
python -m benchmarks.run_y_orbit_sparse_probe --dry-admission --fresh-fixture-c1 p6-component --degree 6 --auxiliary-gauge positive-h --dtn-phase-gauge boundary_plane --live-component-oracle --research-memory-gib 3 --research-wall-seconds 4500 --expected-head EXACT_LOCAL_HEAD
```

获准后第一项入口采用相同参数，把 dry-admission 改为 run，并指定新的 own-branch ignored artifact 目录。独立保存数据检查入口为 `benchmarks.check_y_orbit_sparse_probe`，同样指定精确 checker HEAD。第二项采用 `--fresh-fixture-c1 p4-chain --degree 4`，另外指定新 p6 的 `--component-report` 及确切 SHA256。不能用文件名相邻关系替代哈希绑定，也不能用缺失的旧原始证据授权。

相关源码：[p6 组件](../../../src/solvers/fresh_c1_p6_component.py)、[p6 独立检查器](../../../benchmarks/check_fresh_c1_p6_component.py)、[监督入口](../../../benchmarks/run_y_orbit_sparse_probe.py)、[固定合约](../../../src/solvers/fresh_c1_contract.py)、[测试收据](records/fresh_c1_source_v1/targeted_contract_tests.json)。

公开 PETSc 后端及 AUTO 成本探针仍在后续 C2；本次没有原始大模型运行资格，也未解决主任务仍未达到 1% 的物理精度问题。
