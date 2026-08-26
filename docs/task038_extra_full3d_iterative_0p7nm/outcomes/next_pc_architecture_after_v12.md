# Review V12 之后的 PC 架构比较

## 结论边界

Review V12 的 Route A 已因 global adjoint Gate 关闭；Route B 只取得 `STRUCTURALLY_QUALIFIED` 的结构/setup 资格，R4.3 random 在 7000 步受控停止；C1 因跨 MPI physical-canonical identity Gate 关闭，C2 因 `h3star→h1star` owner-packet work Gate 关闭。当前没有 qualified multilevel PC。本文只比较下一轮可能的架构，不实现、不选择，也不把任何一条路线写成已通过。

这里的“粗空间”是用少量全局未知量表示跨子区域的长距离误差；它能减少迭代器反复传递同一类误差，但粗空间越大，通信、存储和求解成本越高。下一轮必须先在小型 H(curl) 案例上证明切向连续性、伴随和跨 MPI 身份，再讨论 p6/h10。

## 历史边界

新候选不能重命名或重分类旧实现。Task025 的 ordinary BDDC 在 h5 50 步约为 `0.3549`，adaptive BDDC setup 约 10 分钟且约 `12.78 GB`；见 [`Task025 summary`](../../task025_parameter_robust_multilevel_hcurl_pc/outcomes/summary.md)。Task027 的 PCHPDDM/energy-GenEO 在 h5 100 步约为 `0.2187`，见 [`Task027 summary`](../../task027_mesh_independent_spectral_schwarz_pc/outcomes/summary.md)。这些是旧实现的负结果；V12 列出的三种架构在数学对象、全局 coarse 边界或内存生命周期上必须明确不同，并应另立任务验证。

## 三条候选路线

| 候选 | 直接解决的 blocker | 预计保留对象与不确定性 | 全局 coarse 边界 | 最小验证案例 |
| --- | --- | --- | --- | --- |
| energy-minimizing BDDC/FETI-DP for H(curl) | 用子域界面上的能量最小延拓替代当前 nested edge transfer，直接处理 `h3star→h1star` 的接口 work 失配 | 子域局部矩阵/约束、界面 primal 或 dual 变量、分布式 coarse operator；内存取决于界面 DoF、约束数量和局部因子，当前没有精确预测 | coarse 维度应随界面与约束增长，不能按全体 volume DoF 复制；必须说明局部因子是否常驻 | p3/h50 两子域 MPI1/MPI2；验证 H(curl) 切向 trace、能量最小性、P/P^H、canonical identity 和 true residual |
| GenEO/adaptive domain-decomposition coarse spaces | 从局部广义特征向量中捕获材料跳变、周期边界或长尾误差，避免手工指定不适用的 nested 节点 | 局部特征向量、其限制/延拓、粗矩阵和正交化工作区；不确定性是满足固定物理阈值所需的 mode 数和跨 MPI 粗空间布局，不能预先冒充内存结果 | 粗空间只能由冻结的物理/谱准则产生，并受明确 rank 与内存上限约束；禁止按参数扫描挑最好结果 | 非均匀 p2/p3 H(curl) 小网格 MPI1/MPI2；三种材料角色、周期 phase-once、局部 eigen residual、粗校正 work 和 10000 步 true residual |
| matrix-free p-h multigrid with distributed algebraic coarse correction | 保留精确 matrix-free fine action，同时用同一物理 mesh 上的 p/h 层或分布式代数粗校正，绕开非嵌套 p-level LOR 网格 | fine action、受限局部 transfer、smoother work、分布式 sparse/algebraic coarse payload；不确定性是粗校正规模、setup 生命周期和跨 partition 的通信量，不能用 global dense transfer 掩盖 | 禁止 global high-order AIJ、global dense transfer 和 FE-sized numeric allgather；coarse payload 必须随可解释的界面/层级规模增长 | 同一 hexa mesh 的 p6/p3/p1 或固定 h6/h3star/h1star 对照；独立 P/P^H、Galerkin/rediscretized energy、MPI1/MPI2 canonical identity，再做小型 true-residual smoke |

## 比较与下一步门槛

BDDC/FETI-DP 的优势是接口约束有明确能量含义，风险是局部子域因子和界面 coarse solve 可能成为新的内存主项。GenEO 更能适应材料和几何变化，风险是 eigenvector 数量和粗空间通信难以在没有实测前可靠外推。matrix-free p-h 路线最接近现有精确 action，但必须重新定义分布式代数粗校正，不能把已关闭的 nested LOR transfer 换个名字继续使用。

三条路线都应先通过同一组不可放宽的证据：complex128、finite、P/P^H work、linearity、repeat、input unchanged、Floquet phase exactly once、MPI1/MPI2 physical canonical identity，以及小案例的 true residual。任一候选若需要降低 tolerance、平均不一致的 shared row、复制 global matrix 或扫描参数才能通过，应立即关闭该候选。

当前状态是 `selected_hierarchy=NONE`。p6/h10 positive、physical Maxwell、official R/T/A 和 0.7 nm/2 TiB capacity 均未运行；本文不为它们提供预测数字。原 C2 诊断与历史负结果见 [`interlevel_route_selection_v1.md`](interlevel_route_selection_v1.md) 和 [`nested_lor_edge_hmg_c2_mpi1_diagnostic_v1.json`](records/nested_lor_edge_hmg_c2_mpi1_diagnostic_v1.json)。
