# 单个紧凑 quotient 块已通过并持久保存

2026-10-04，独立云分支在 C1a/C1b 已闭合基础上，完成真实 local40/twist0/q0 紧凑 prefactor。worker、独立检查器以及完整 Library 新目录取回均通过；这是单个块的资格，其他块、完整 quotient 逆和原尺寸目标仍未通过。

- 保留4,320个本地内点、228个偶数 n 扇区模式、全部509项贡献；q0矩阵为1884维。完整全局532物理manifest保留，但本项没有对全部532 quotient给出通过结论
- q0 对本次 C1b完整Ny参考的 Frobenius相对差7.6099e-16、最大项相对差9.8955e-16，原1e-11门槛保持
- 实际local primary/literal同Gauss、原始系数及两个mask门通过。两条本地分支均保留；q0/q2各3968列的native映射是worker控制，尚未将q2算子作为本项通过块
- 完整本地内点/非零port RHS、恢复、slave-zero、live原始FE/port残差通过。检查器独立重建贡献/投影、carrier和缓存RHS/恢复；体积作用仍以保存的live FFCx为authority，没有独立重跑FFCx
- 常驻Hhat为0。原始H以对角保存，Di/XiB先以因子投影；只使用继承的cell-interior LU，没有global/q因子或PDE求解

worker287.630秒、树RSS475,521,024 B；checker6.547秒、307,527,680 B，swap均0且子进程清理完成。投影owned allowance128MiB/tile128是额外对象上限，不是整棵树内存。整树上限3GiB/1800秒。

完整worker包62,002,183 B，2部分重新拼接，2,132文件/1,887 NPY全部hash、shape、dtype、numeric hash通过。未压缩459,907,760 B中数值73,127,404 B；重复逐tile资源/JSON日志开销很大，全部保留，没有裁剪以制造通过。worker恢复索引为libfile_dff163270f648191adbd2e0288a8dd9d；最终checker包libfile_1ec7d3bda3a48191b1b1dd5cc855f80e的11成员全部取回通过。

源码39c50524/tree77189d94仅增加4个文件，保护的数值/配置字节未改。121项测试与10子测试通过；一个旧测试对不可获得旧helper的baf SHA硬编码断言失败并明确排除，实际848a helper与已资格C1b相同，新live原始形式检查绑定其真实字节。没有声明旧/新helper等价。

下一道门应是两扇区live all-q/cross/完整逆：全4块与C1b及双对角泄漏先通过，再准入4因子，最后完整三维regular/notch载荷和输出。当前冻结CSR及恢复记录没有public完整cache restore，不能把CSR-only当作恢复/逆资格。精确结构空行的提前跳过可降低日志开销，但必须保留全部label、532manifest和数值门，先审阅测试再执行。

[小型完整记录](records/selected_C1c_q0/selected_C1c_compact.json)保存全部结论、资源和Library恢复索引。原始50×25×140nm、0.7nm、2e12B/172800秒及场/功率精度尚未验证。
