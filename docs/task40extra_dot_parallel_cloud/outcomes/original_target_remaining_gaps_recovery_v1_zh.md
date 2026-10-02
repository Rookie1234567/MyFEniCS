# 原尺寸全三维交付：恢复后剩余缺口

2026-10-02 UTC。当前已持久保存的是组件源码和纯代数证据；实际 FEniCS/PETSc 接线 **NOT_RUN**，完整工作站运行包尚未完成。没有数值作业在运行，官方包源访问仍阻塞。旧 raw artifacts 未恢复，最后一个旧 checker 结果为 **UNKNOWN**。

## 用户目标与当前证据

目标是原始 50×25×140 nm、17 nm 宽/120 nm 高 Si 规则线光栅，λ=0.7 nm；首先 regular baseline，同时保留真实非可分三维 notch 能力。全部 y 自由度、所有 q 分支和物理 DtN aliases 都必须保留；内部两单元参考逆不能替代原始全三维方程与 true residual。

预算是整机 decimal 2,000,000,000,000 B、端到端 172800 s、swap=0；包含系统、JIT、网格/装配、所有并存因子、outer vectors、恢复与要求的输出。当前云端校准不授予该预算下的原尺寸资格。

[已发布恢复检查点](recovery_retained_h_checkpoint_v1.md)保存 27 个纯 NumPy 控制和 4 个带明确 stub 的工厂元数据检查。它们不能证明实际 Maxwell/MPC/FFCx/PETSc 接线。[V15](../response_v15.md)与[校准比较](calibration_comparison_v15_zh.md)保存旧环境的 scaled p4/manual532 历史结果；X/XZ 是旧两单元 notch，Y 是同体积、周期 y 移位后的新三单元 notch，不能当作相同场的跨网格对照。原始 raw 数据丢失不改变历史标签，也不能支持新 ABI 资格。

## 最短后续顺序

1. 获得被允许访问的官方 complex FE/PETSc 包源后，记录并资格化实际 ABI、整数宽度、MPI/BLAS、FFCx/JIT 与模块加载路径
2. 构建自包含 fresh full3D fixture；在同一 live carrier 上重做同 Gauss/完整 MPC、原始 H/Di/XiB、任意内部与非零端口 RHS、恢复、原始残差和必要输出；材料量级负控制单独保留
3. 资格化[公共 PETSc 因子接口](public_petsc_factor_backend_plan_v1_zh.md)，再接全部实际 q 块。公开 PC.setUp 合并 symbolic/numeric，单独 Python analysis 准入尚不具备
4. 重新测量完整参考 setup、C/D、因子 fill、outer/恢复向量、同时内存与所有阶段时间。不能沿用旧云端每 q 的 policy allowance 作为容量预测
5. 原尺寸 AUTO 先做精确库存和结构/表示账本，再选择能否准入的工作站 pilot；精度、端口收敛、目标光学尺寸和更强 notch 的外层收敛仍须实测
6. 冻结可安装环境、commit/config、单命令入口、fail-fast 日志、检查点/重启和持久 raw evidence 位置后，才交付大型作业候选

## 已知表示节省与尚未计清的峰值

[已归档原尺寸库存](records/full_size_port_inventory_v1.json)的历史 AUTO 规划值为 32060 通道，必须由 fresh 完整 keys/digest 再确认。complex128 对角 H 的载荷为 512960 B；密集 H 方阵为 16445497600 B。这个差异只证明原始 H 的表示成本，不能推出整机容量或求解时间。

实际峰值仍须计入：C/D 稀疏行和值、AUTO 面求积工作缓冲/编译开销（历史 max_order=142 时 p4 名义6241点、p6名义6561点，实际 Gauss 尚待 fresh 核验）、局部恢复与 orientation 模板、每 twist 的缓存、所有 q 稀疏 LU 及其 workspace、原始 full3D action、FGMRES/恢复/输出向量、I/O 与进程树。索引、NNZ、CSR indptr 和后端一基转换均需在 allocation/narrowing 前核验；PETSc int64 不能单独证明 MUMPS full64。

求积计划来源为 [已恢复的 degree 公式](../../../src/solvers/dtn_port_3d.py#L1610)：max(10,2p+max_order+6)。名义点数不是当前编译器的实测结果。

参考逆/表示改变不授予物理精度。主任务与本分支的 phi、p、port 集合及参考平面需按完整接口核对；不能直接把 phi0/p6/M2=340 与 phi5/p4/manual532 的复振幅比较，也不能为接口对齐删除模式。弱微小 notch 的 3–4 步历史迭代不能外推至原尺寸或强扰动。

[可执行的纯测试与实际资格合同](portable_retained_h_qualification_contract_v1_zh.md)给出目前能复现的两条命令。新 FE 命令尚未冻结，安装与数学运行待解阻；此时有用的独立工作是这些已完成方案的文档交付，继续数学接线需要实际运行时。
