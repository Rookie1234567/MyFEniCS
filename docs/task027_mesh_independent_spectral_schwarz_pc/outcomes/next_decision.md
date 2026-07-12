# 下一步决策

## 已解决

- MPI4 `h=2` 显式真残差小于 `1e-6`；
- MPI4 `h=2` 含 R/T/A 峰值总 RSS 小于 14 GB；
- official R/T/A 与体吸收能量闭合；
- 同一 MPI4 算法规则在 h=5/h=3/h=2 全部收敛；
- 实际终止迭代比 `1.8167 <= 2`；
- 完整物理 slab 不再按 rank 重复切成 64 个 fragment 因子；
- MPI1/MPI2 owner、scatter、空 rank 和重复 apply 回归通过。

## 尚未解决

- R/T/A 的物理网格收敛；
- operator-adaptive spectral coarse 的有效构造；
- 优选 `<=12 GB` 内存目标；当前 h=2 为 12.958 GB；
- 两步平滑每个外层 PC 约需 3 次一层 apply，仍可优化成本；
- 参数变化下的角度、波长、材料鲁棒性尚未做独立 qualification。

## 后续建议

1. 保留当前 MPI4 profile 作为 workstation production candidate，后续独立复跑 `rtol=8e-7` 形成更宽安全余量。
2. 做角度/波长/材料变化的同规则 qualification，每个最终场继续保留显式真残差和 official energy closure。
3. 若优化吞吐，优先把两步平滑的 3 次一层 apply 降到 2 次，保持当前物理 slab 和 coarse 规则不变做单变量对照。
4. 若继续研究谱方法，必须重新设计能捕获非正规 DtN 慢误差的局部问题，不再重复本轮 energy tau/cap 扫描。

## 当前停止条件

Task027 的实际 MPI4 求解目标已经闭环。未开始下一个任务，也不在本分支合并 master。
