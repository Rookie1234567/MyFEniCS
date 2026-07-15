# Task032 负结果与修复记录

1. M20 未做方向过滤时，宽 target slice 把反向/增长分支混入正向基。修复为先求
   2M candidates，再按 Poynting/被动衰减分支选定方向；不足 M 时 fail closed。
2. 第一版 M120 场重构为每个模态创建 mixed/Et/Ez/H Function 和 scatter graph，
   触及 MPICH context ID 上限。改为四个共享 scratch 后 M120/M160 通过。
3. h3 Stage-4 基础 z 轴不含 10/110 nm，最初按“必须已有平面”失败。正确修复是
   在 local z axis 插入冻结接口，不移动物理分区，不使用 9/111 nm 近似。
4. M20->M40 的 total delta 最高约 `2.25e-5`，证明 M6 表面平台不足以终止漏斗。
   继续 M80/120/160 后才取得强收敛。
5. memory-minimal 在 h5 为 1.680 GiB，高于 Schur-fast 1.649 GiB；重复因子化和
   allocator RSS 高水位抵消了对象释放。该路径未被静默包装成 h5 优化。
6. Schur-fast 在 h3 为 3.974 GiB，高于 augmented 3.869 GiB；两个局部 LU 的
   总填充不必小于单体 LU。只有顺序 factor 的 memory-minimal 降到 3.215 GiB。
7. 两种 h2 预测都未通过 4/5 GiB Gate，因此 h2 没有运行，强成功分类不成立。

以上失败均归入 implementation/performance、modal classification、truncation 或
direct factor memory 类；没有为通过结果修改材料、几何、衍射级或端口定义。
