# 首A后的内存预算与精确检查点

## 为什么调整

首A已完成装配，但在**数值分解之前**被保守预测拦住：原策略把MUMPS in-core估计再乘2。不是机器真的用掉9 GB，也不是求解失败。完整失败和成本见[原记录摘要](outcomes/first_A_admission.json)，不会被后续结果覆盖。

[MUMPS 5.8.2用户手册§5.11](https://mumps-solver.org/doc/userguide_5.8.2.pdf)说明，INFOG(16)已经使用当前ICNTL(14)的workspace余量；INFOG(26)对应out-of-core，不能给当前ICNTL(22)=0的in-core路径放行。ICNTL(23)限制MUMPS内部workspace，不等于整个进程的内存限制。当前版本与[PETSc v3.25.6转换源码](https://raw.githubusercontent.com/petsc/petsc/v3.25.6/src/mat/impls/aij/mpi/mumps/impl/imumps.c)已独立对照。

## 新的、仍然保守的分账

保持ICNTL(22)=0、ICNTL(14)=100、ICNTL(35)=0。临时符号对象释放后，重新测进程树live和系统available，扣除：

- PETSc转换保守预算 `24 × stored_nnz` 字节，连可能的复数值复制也计入；
- 256 MiB其它新增开销；
- **独立512 MiB安全余量**；
- 16 MiB额外未承诺观测余量，避免两次相邻观测的小波动消耗所有空间；
- 系统available至少保留1 GiB。

余量以十进制MB向下取整，作为ICNTL(23)；若小于实际INFOG(16)，仍拒绝。随后再执行完整现场stage gate。原A观测的纯算术回放得到4538 MB，超过4388 MB最低估计；这只是预算算术，不是数值因子已通过。内部空间不足时的MUMPS错误保留为可恢复失败，不自动重试放大上限。外部进程树、available、磁盘与零swap监测全部保留，应用采样不是OS硬配额。

## 检查点不改变物理

新增功能仅在六层路径显式启用：

1. 每个原始单元张量完成后，保存完整complex128数组和精确身份，再读回校验。身份绑定实际材料、波数、canonical坐标位模式、编译形式/规则/算术源码、编译器与runtime；不同厚度导致不同实际宽度时不能误复用。
2. 缓存的是**施加方向变换之前**的局部体积分。无PML、常材料、轴对齐仿射单元的体积分平移不变且不依赖入射/Bloch相位；方向变换、MPC、RHS及端口相位仍每次新建。没有缓存局部LU或全局因子，也没有借旧解。
3. 每个raw类及方向化Schur类实时记录进度、cold/hit计数与时间。当前首A没有raw检查点，因此不能假称能从它的内存恢复。
4. 数值因子准入前保存稀疏 `condensed_A.petsc` / `condensed_b.petsc`。它们是trace+aux **凝聚系统**，不是未凝聚原FE算子。完整二进制逐行与live A精确比较，b逐值比较；文件SHA和canonical row SHA都保存。没有构造稠密全局矩阵。
5. 有限磁盘先预算，未完成条目保留并硬拒，不吞损坏、不覆写已提交数据。缓存读取、写入、末hash都计入总成本。

无论cold或warm，**原完整UFL作用、未截断C/D/J残差、材料体吸收和后续物理稳定性资格都不能跳过**。19项缓存软件正负控不等于实际FE张量资格；当前小native prefix和下一A各自单独记录。

## 实际小前缀与普通类型修复

真实 p1 单元检查点前缀 v1 因配置中的 `mu_r=1+0j` 被误转 float 而受控失败（5.023 s）；原失败保留。修复为显式有限、虚部为零且实部为1后，v2 用真实原 kernel 冷计算/精确 warm 命中且逐位相同，2×2 稀疏 A/b 每行回读通过：5.024 s、315,805,696 B，正常清理。另有19缓存软件正负控与8预算/μ控制通过。该结果只关闭实现接口，**不是 p6 或六层物理通过**；见[紧凑软件证据](outcomes/checkpoint_budget_software.json)。

## A_v2后的JIT预测校准

单例全流程已经独立通过：1428.157635 s、树采样峰6,597,210,112 B。完整采样中非owner后代峰2,409,811,968 B，原残差阶段后代峰2,373,857,280 B；采样未存argv，只能结合JIT事件说明关联，不能虚构每进程类型。原256MiB rank1预留低于该观察；下一例提升至 `ceil_64MiB(2,409,811,968 + 256MiB) = 2560MiB`，仍另加原vector预算和独立512MiB余量、实时available/树上限联门。不是放宽门，不是未来RSS上界。两常量外源码逐字不变，原A不重算，见[等价证书](outcomes/resource_only_equivalence_v1.json)。
