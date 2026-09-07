# S6 精确对角优化：组件证据与阶段标记

为取得对角项，旧实现先计算每单元全部 882×882 耦合，这成为 setup 的主要局部成本。新实现直接在同一积分点计算受约束基函数的能量，省去无用耦合；代价是参考基函数/旋度表和逐单元临时数组。支持范围限于本任务的 Q1 affine hex、N1curl、scalar DG0 正实系数，不改变物理、积分规则、S6 层级、seed 或平滑器。

先按原方向变换处理基函数，再按复杂 Floquet MPC 系数组合属于同一 target 的所有 raw rows，最后取能量，得到相同 `diag(C^H A_cell C)`；不能只对 raw diagonal 乘系数平方，否则会漏交叉项。积分规则由本机 FFCx 对原形式的分析及原 quadrature helper 导出，实测为 degree=15/default、512 点。没有 dense 单元库存、近似对角或容差类别合并。

| 证据类别 | 结果与边界 |
|---|---|
| measured：旧正式运行 | `USER_CONTROLLED_STOP`；parent 5946.249557011994 s，完整 workflow 5946.465141321009 s；同期进程树 RSS peak 1582481408 B，swap 0；最后进入 fine physical setup，outer 未开始 |
| derived：旧 S6 跨度 | 从 positive_s6_started 到 fine_physical_started 为 5916.818793114 s；不是 7200 s 超时，也不是 p4 数值失败 |
| measured：两单元热点 | cell 0/7 dense kernel 22.728753/22.660344 s；方向处理与 MPC 对角累加为毫秒级 |
| predicted：旧 kernel 全网格 | 两单元均值乘 252 得 5719.026247 s；同材料两个样本，不覆盖全部类别，不是完整 setup 实测 |
| not_run | 优化后完整 S6、原始 outer PDE、正式残差与 R/T/A 均尚未运行 |

原 p6/h10 三个单元逐一与未修改的 dense oracle 对照，只保留逐单元临时数组：

| 单元 / 比较理由 | 旧局部秒 measured | 新局部秒 measured | relative error measured |
|---|---:|---:|---:|
| 0：普通单元 | 24.388574 | 0.067173 | 2.293545e-15 |
| 7：非零 orientation、84 slaves | 27.712906 | 0.094662 | 2.557512e-15 |
| 3：另一材料 | 29.065944 | 0.060190 | 2.235792e-15 |

三个误差均小于 1e-11，结果 finite；新基表准备 0.722039 s。三单元 watchdog 总计 114.878032 s（预算 300 s），RSS peak 1479536640 B，包含旧参考和冷编译，不能称为新算法单独内存峰值。局部速度不代表 measured full setup 加速。

p3 assembled-MPC 对照 serial 相对误差 2.288469e-15，MPI2 为 2.287400e-15。测试覆盖复 multi-master 交叉项、非平凡基变换、真实非零 orientation、repeat/finite/input/slave/ghost。首次 MPI2 因测试把非 ghosted AIJ reference 做 ghostUpdate 而报 PETSc error 62；仅修正 reference 布局，新目录重跑每 rank 2 passed，失败日志保留。生产 ghost 处理未改。

最终加入阶段 callback 后，test333/356/357 共 **17 passed（4.65 s）**，parent 6.172200 s，RSS peak 192581632 B。所有相关 watchdog 的 swap peak 与全局换页增量为零，清场通过。此前已按核心 hash 绑定的三单元/MPI2 证据没有因 callback 修改而重跑。compileall、diff-check 和本记录 JSON/hash/Markdown 结构检查通过；未运行 full repository pytest 或 CI。

`stage_callback=None` 为默认，旧调用不产生 marker。Task39extra 传入已有 flush marker，记录 p6 action、diagonal、p3 assembly、p1 assembly、transfer/cycle 初始化的开始和完成；异常时不写虚假 complete。不改变计算顺序。旧 diagonal oracle 和默认路径保留。

本证据属于 **development dirty-source 组件验证**，基于 HEAD `39448e6a0e5705ad2c40b4bf7733ce2249e35a84`，不是 clean-SHA formal PASS。源码逐文件 hash、所有相关原始阶段/单元数据、worker log、parent summary、resource timeline 的路径与 SHA256 见 [结构化证据](records/setup_diagonal_optimization.json)。主要 artifact 根为 `benchmarks/artifacts/task39extra/quadrature_diagonal_39448e6/` 与 `benchmarks/artifacts/task39extra/setup_diagnostic_39448e6_20260907/`；旧正式证据仍在原 results 根。大型日志和缓存保持 ignored。

本阶段仅为优化与可观察性闭环，不是 A5 结项。下一个正式运行必须使用审核后的 clean SHA 和新 artifact root，并继续遵守整机余量与现有动态内存预算；没有把历史 2 GB 参考指标改作本任务硬线。
