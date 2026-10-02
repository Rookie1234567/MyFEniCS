# 执行环境重建后的源码恢复检查点

2026-10-02 21:04 UTC 附近，云执行器更换。原计算目录和独立 complex FEniCS 环境不再可读；最后启动的 saved-only checker 结果未知。这里保存新恢复的源码和新代数检查，不能代替丢失的原始计算证据。

远端 V15 `de14d2a28333348a0f3eefc8d4471dcdafbddb37`、树 `846fe8a974fcbbabbd21a64e32fbbef737af850d` 是恢复基线。其已发布小规模全三维结果仍作为历史记录保留。未推送的旧 Git 对象、原始矩阵和最后 checker 的完成状态没有被重建。

## 本次代码

- 两个完整模块 `y_orbit_two_cell_block_audit.py` 和 `y_orbit_quotient_condensed.py` 的恢复字节与之前记录的源码 SHA256 相同；这只验证源码恢复
- `retained_port_block_layout.py` 和 P6 接线是明确标记的新、未取得有限元资格的重建代码
- 默认仍选择原 dense 路径；研究选项保存原始 H 的显式表示，借用每个非空单元的 Di、XiB，按 Hhat·α = H·α + Σ scatter(Di·(XiB·gather(α))) 运算，不先生成单元端口方阵
- 原始 H 的逆仍用于原方程恢复，不能用 Hhat 的逆替代。全部提供的单元、空单元、模式键和数值均进入身份记录
- 缺省 Hlocal 保持 None；研究路径遇到非零 Hlocal 明确停止。它尚未实现旧草案中的一般 Hlocal fallback
- 载体工厂在读取端口数组前检查整数宽度，并将显式 H 的所有键和值绑定到载体。新接口不减少全三维自由度或模式

## 新检查的范围

新运行时为 Python 3.12.14、NumPy 2.3.5、SciPy 1.17.0。旧 PETSc/DOLFINx/MPC/MPICH 栈和 ABI 收据不存在。

27 个纯 NumPy 单元测试通过：材料量级的复数非 Hermitian 修正由独立 Vii/Bi 稠密控制组构造，检查符号、投影、原始 H 与 Hhat 的区别、借用所有权、空单元、遗漏和错误共轭。另有 4 个生产工厂元数据分支测试通过；其中 PETSc.IntType 和最后 action 构造器明确使用元数据 stub，不能据此宣称 PETSc 或有限元接线通过。两份测试也在源码子集的干净路径覆盖中通过，总测试子进程峰值约 36.2 MB。

原 RHS、内部场恢复、B/D 和体积公式的多个方法与 V15 的 AST 相同；改动的表示和工厂分支经过独立源码审查。源码审查不是数值资格。此前测试 harness 的 lineno 错误及修复保留在记录中。

## 可复现与未完成事项

在仓库根目录，可分别运行 `python src/test/test_retained_port_block_layout.py` 和 `python src/test/test_reconstructed_p6_source_metadata.py`，只需 NumPy 和 Python 标准库。固定原始 H 模块身份由测试核验。

实际 FEniCS/PETSc 接线、原始全三维残差、所有端口输出、正则参考与非可分 notch 求解均需在新 runtime 资格后重新运行。当前官方软件源的 shell 访问受阻，没有修改网络或系统 MPI。没有继承旧 ABI、伪造旧 PASS 或重新生成丢失原始证据。

目标 50×25×140 nm、λ=0.7 nm、2×10¹² B 整机内存、172800 s 全流程仍未资格化；原尺寸 AUTO 的 C/D 存储、6241 点面求积/编译成本、稀疏因子填充和物理精度仍是独立问题。
