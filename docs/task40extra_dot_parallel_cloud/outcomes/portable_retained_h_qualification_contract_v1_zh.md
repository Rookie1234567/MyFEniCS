# 恢复后最小可移交资格合同

状态：源码与纯代数检查点已发布于 [112dcae23d](recovery_retained_h_checkpoint_v1.md)；新 FEniCS/PETSc 数学接线未运行。此合同不宣称原尺寸任务可在 2 TB / 48 h 内完成。

## 现在能复现的检查

在本分支仓库根目录，先设置数学库线程为 1，再运行：

```sh
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 python src/test/test_retained_port_block_layout.py
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 python src/test/test_reconstructed_p6_source_metadata.py
```

第一条是 27 个纯 NumPy 借用/表示/材料量级复数修正控制；第二条是 4 个生产工厂元数据分支检查。第二条明确使用 PETSc 整数类型和最终 action 构造器的 stub；它不证明 PETSc、MPC、FFCx 或 Maxwell 方程通过。Python 标准库和 NumPy 足够，不需要 pytest。测试绑定已恢复的原始 H 模块源码 SHA。

新运行时实际为 Python 3.12.14、NumPy 2.3.5、SciPy 1.17.0；DOLFINx、MPC、PETSc、Basix、UFL、FFCx 缺失。官方安装授权已有，但当前 shell 无法访问官方包源；没有修改安全/网络设置或用户机器。

## 实际数学运行前必须满足

1. 记录实际 Python、NumPy/SciPy、DOLFINx/Basix/UFL/FFCx、dolfinx_mpc、PETSc/petsc4py、MPI/BLAS 和编译器版本及加载路径；MPI1、complex128、线程1、swap0。旧云端版本是优先重建参考，不能把版本号或旧收据当作新 ABI PASS
2. 确认 PETSc.IntType 和 factor backend 的索引/NNZ/offset 宽度；在任何 narrowing、CSR 导入或 factor 创建前拒绝溢出。PETSc int64 不等于 MUMPS full64
3. 使用 fresh source commit/config/完整模式键和 digest。物理生成器身份、局部网格/面积/扭转相位/装配身份分开；不得读取已经丢失的 snapshot 文件，也不得复用旧 checker 的 PASS
4. 采用自包含的小型实际全三维 fixture，重新建立体积 action、同 Gauss/完整 MPC 的独立端口证据和单元缓存。保留全部 y 分支、内部自由度、物理 alias 和 γₙ；不投影到 n=0
5. 将原始 H 的显式表示和 Di/XiB action 与同一 fresh fixture 的旧 dense 路径比较；检查任意内部 RHS、非零端口 RHS、完整恢复、slave-zero、原始方程残差和所有要求的端口输出。材料量级负控制独立保存，不能修改物理 PDE 值来制造敏感性
6. 新公共 PETSc backend 先做实际 complex 非 Hermitian 单块资格，再接实际 q 块和完整 regular/notch 原方程。公共 PC.setUp 组合 symbolic/numeric，不能伪造两阶段 Python 准入；禁止旧 ctypes 路径
7. 全流程 supervisor 在 import/JIT/装配前启动，保存实际进程树或 cgroup、同时驻留因子/缓存/向量、wall-clock、swap 和失败/清理记录。大型原始证据的持久保存位置先落实，再批准昂贵计算

实际 FE 命令尚未冻结：新依赖不可用、自包含 fresh fixture 接线尚未资格化。上述纯测试命令是当前可执行合同；不能把旧 snapshot-backed benchmark 命令交给干净机器当作可执行方案。

## 原尺寸可行性仍缺什么

- 用户目标为原始 50×25×140 nm、17 nm 宽/120 nm 高 Si 线光栅、λ=0.7 nm；先 regular baseline，同时保留完整三维 notch 能力
- 原尺寸 θ=89°、φ=0 的 AUTO 物理库存历史规划值为 32060 个通道。需要 fresh 完整 keys/digest 确认；云端 φ=5°、p4/manual532 的资格不能直接替代主任务 φ=0°、p6/M2=340 的接口
- 用 complex128 显式对角保存 32060 个 H 值约 0.513 MB，而完整方阵为 16.445 GB。这是确定的表示成本差异；C/D、面求积工作缓冲/FFCx 编译、恢复缓存和各 q 稀疏因子仍可能主导内存。对历史 max_order=142，已恢复的求积公式给 p4 degree156/p6 degree160；名义张量 Gauss 分别为79²=6241/81²=6561点，实际 compiled nodes/weights 仍须 fresh 核验
- 两单元局部参考构造避免全 Ny 的候选 S/F/Q；原始三维 outer operator 与全部模式仍保留。原尺寸稀疏 fill、setup/回代时间、外层迭代和所需精度没有足够实测，不能从弱微小 notch 的 3–4 步外推
- 2×10¹² B 是整机预算，172800 s 包括 JIT、build、装配、factor、迭代、恢复和要求的输出；不能只计 factor 或把阶段峰值相加作为同时峰值
- 本分支的目标物理精度仍未资格化；主任务精度证据需按其最新冻结记录另行判断。参考逆架构与表示节省不能替代 mesh/order/port/场定义的精度资格

当前交付是可审查的组件源码、可重复的纯代数控制和明确的实际运行前置条件；完整工作站一键数学运行包仍待 fresh runtime 与自包含 FE 资格。

依据：[恢复检查点](recovery_retained_h_checkpoint_v1.md)、[V15 校准限制](../response_v15.md)、[新运行时清单](records/recovery_retained_h_v1/new_executor_inventory.json)。本文是前置条件合同，不是已通过的实际 FE 运行计划。
