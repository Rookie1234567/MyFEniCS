# Task032 负结果与修复记录

1. M20 未做方向过滤时，宽 target slice 把反向或增长分支混入正向基。修复为先求
   `2M` candidates，再按 Poynting 与被动衰减分支选择方向；不足 M 时 fail closed。
2. 第一版 M120 场重构为每个模态创建 mixed/Et/Ez/H Function 和 scatter graph，
   触及 MPICH context ID 上限。改为共享 scratch 后 M120/M160 通过。
3. h3 基础 z 轴不含 10/110 nm。正确修复是在 local z axis 插入冻结接口，
   不移动物理分区，也不使用 9/111 nm 近似。
4. M20->M40 的 total delta 最高约 `2.25e-5`，证明早期 M6 表面平台不能终止
   漏斗；继续到 M80/120/160 后才取得强收敛。
5. h5 三次正式路径测得 augmented/Schur-fast/Schur-minimal 为
   `1.865/1.755/1.698 GiB`。早期研究重复中 fast/minimal 的细小排序曾反转，
   所以不宣称 h5 两条 Schur 生命周期之间存在稳健优劣，只确认二者低于 augmented。
6. h3 Schur-fast 为 `3.998 GiB`，高于 augmented 的 `3.853 GiB`；两个同时存活的
   局部 LU 总填充并不必然小于单体 LU。只有顺序 factor 的 memory-minimal 降到
   `3.224 GiB`，相对 augmented 降低 `16.31%`。
7. 六条正式内存记录最初暴露 sampler 默认镜像摘要的一位录入错误。数值本身未受
   影响，但旧摘要未被升级为正式证据；脚本修复后从 clean SHA 重跑六条，记录中
   同时保存 source metadata 和实际镜像 ID。
8. 两种 h2 预测的中心与上界都未通过 4/5 GiB Gate，因此 h2 未运行，
   `hybrid_direct_strong_memory_success` 不成立。
9. 容器内全量 checker 曾在 Windows bind mount 的 `git status --short` 停滞；
   数值测试已完成，停止临时容器后同一 checker 在宿主约 13.2 s 完成。这是
   Windows 挂载上的 Git 性能问题，不是数值或并行死锁。

以上问题分别归入 implementation/performance、modal classification、truncation
或 direct factor memory。没有为通过结果修改材料、几何、衍射级、端口定义或
任务书阈值。
