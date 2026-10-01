# 原始端口 H：独立组件资格与后续设计

## 先回答实际问题

目前完整三维端口把每个出射模式的归一化放在独立对角项上。原始 H 的作用和求解只需逐项乘、除。但 p6 retained 适配器先创建稠密方阵，随后反复调用通用稠密求解，既浪费存储也做无必要工作。本候选保持全部模式、全部三维场自由度及复数非 Hermitian 语义，只改变这个矩阵的表示。不能把它称为二维或 2.5D 等效模型。

实际 50×25nm、0.7nm、继承 1° 掠入射/Si 参数的原生成器得到 32,060 modes，其中 31,488 个 n≠0。M0 的自动包络为 (142,35)，实际 m=-142..0、n=-35..35。每份 complex128 方阵形状载荷 16,445,497,600B，而复数对角向量 512,960B。此处不代表端口截断已合格，也不是目标模型 RSS/时间预测。

真实保存 G0 p4 数据只有 80 modes。B/D 各 42,624 项、1,536 个唯一行，全部在 active trace 上；Bi/Di/XiB 均无数组。端口 carrier 合计 1,704,960B，CSR 端口 H 只有 80 个非零对角项。该 G0 的主要载荷是 CSR 与局部缓存，本候选针对未来规模增长。

## 数学边界

- `DiagonalOriginalPortBlock` 从每个 carrier 的 `normalization_h` 和完整有序 mode key 创建 M 项 complex128 向量。复数 H 不取实部，不合并模式，不更改 B/D、beta、极化或 MPC
- `solve(rhs)` 对每个 RHS 做 M 次复数除法；`apply(rhs)` 做 M 次复数乘法。允许任意复数向量或多 RHS。没有 dense factor，没有隐式方阵 materialization
- `DenseOriginalPortBlock` 仅为显式声明的真正非对角原 H 保留通用 fallback。必须给 reason 与分配上限；不以数值阈值判断“近似对角”
- Hhat 与原 H 不同。Hhat=H+sum(Di XiB)，桥和严格残差仍解原 H。研究组件 `CachedCondensedPortBlock` 借用已缓存 Di/XiB，作用为 Di@(XiB@alpha)，不形成 mode² 更新、不增加局部 LU 求解；不替代原 H solve
- 这不是重复旧 L4 streaming：旧路径额外解每个局部 LU，真实 apply 慢 65.48%、只省 1,784,832B unique-owner payload。本设计仍用 cached XiB，只改变原 H 和端口 Schur 块表示。Hhat factored action 的时间必须另测，不能因数学相同自动采用

## 必须接线的源位置（当前 canonical 未改）

| 源文件位置 | 现有要求 | 后续最小适配 |
|---|---|---|
| p6_cell_condensed_action.py:1384–1388 | carrier 构造 `np.zeros((M,M))`，填 H 对角 | 直接构造 O(M) original-H，不先建 dense |
| 同文件:379–398 | `_H_p` full copy，Hlocal 合并 | 原 H 表示对象；Hlocal 非对角时明确 generic fallback，不忽略 |
| 同文件:410–415 | `_Hhat=_H_p.copy()` 后加 Di@XiB | Hhat action 借用 cached Di/XiB；不能保留隐藏全矩阵 |
| 同文件:594–618 | H_p/Hhat 属性返回 full copy | 生产只用 action/solve/arrays；小 oracle 采用有 byte gate 的显式 materialization |
| 同文件:729–757 | 数组 inventory/hash | 按表示版本、ordered keys、真实 diagonal/borrowed factors 建身份与 owner ledger，不能假称旧 dense bytes hash 相同 |
| 同文件:884、910、1161、1241、1289 | dense matvec/残差尺度 | 调用对应 original-H 或 Hhat action，保持原 operation-scale 定义 |
| 同文件:970–977 | `np.linalg.solve(_H_p, rhs)` 每次分解 | original-H exact solve；generic fallback 显式保留 |
| 同文件:1477、1482、1504 | BAL_H bridge/严格 identity | 保留 original-H solve，绝不能换 Hhat |
| physical_retained_outer_adapter.py:239–240 | ledger 直接枚举 `_H_p/_Hhat` | 枚举 block.numeric_arrays，borrowed backing 只计一次 |
| test_task39extra_v19_* | 使用 H_p/Hhat 做 small dense oracle/污染测试 | 用显式 bounded oracle/表示 corruption 测试，保留旧 generic 非 Hermitian 资格 |

完整仓库检索没有发现生产外部调用 `action.H_p/Hhat`；目前 public full-matrix 消费者为 small algebra oracle tests。不能只替换 solve 而保留构造、Hhat、accessor 和 ledger 的 dense 路径。

## 已完成的有限组件资格

| 检查 | 实际结果 | 身份与边界 |
|---|---|---|
| corrected actual80mode、任意复数80×5/单列/零 RHS | solve 与 action 相对差均0 | measured；实际 FullspaceDtnModeFunctional、全 ordered keys 和数组 hash；仅原 H |
| NaN/Inf、shape、order/H identity、generic non-Hermitian fallback | 20/20 targeted tests pass；pytest0.50s | measured；source ac4d7859b2cae78897c23672c3929490f0415677 |
| actual H numeric storage | 1,280B，对照 complex128 dense oracle102,400B | measured named array bytes；不是 process RSS |
| Hhat 借用 cached Di/XiB | synthetic non-Hermitian multiRHS 相对差9.142689337463832e-17 | algebraic supplement；未授予 actual p6 Hhat/recovery/原 A 资格 |
| 独立 watchdog | 2.0146735129983426s；同时树RSS196,882,432B；swap0；所有后代清场 | measured；1.5GiB/600s cap；单一云端 complex128/int32 ABI；MPI1/BLAS1 |
| 第一次尝试 | 20pass；但 actual dense oracle 未强制 complex128，保存为 float64-H/complex-RHS 有限证据 | 已纠正一行 dtype 并提交后 fresh rerun，旧证据不覆盖 |

数值核心模块为 `src/solvers/original_port_blocks.py`；测试为 `src/test/test_original_port_blocks.py`。component receipt 与完整 scan/inventory 见 records。原 production p6 文件没有接线或改变；普通 default 不变。本测量没有 p2/p4/p6 PDE，也没有全局 factor、32,060² materialization、目标解、目标端口截断或 2TB/48h 资格。这里的20pass包含真实80mode H及明确标记的代数/负测例，不是20个 PDE。

后续真正接线前，需要 actual p2/p4/p6 凝聚 fixture 的完整 action/RHS/recovery/原 A 及 cached Hhat 性能检查。Hhat factored apply 比 dense small Hhat 快与否尚未测量，不能称目标提速。操作数证据只有原 H 每 RHS 的 M 次复数乘/除，和 Hhat 不新增 LU solve。

测试/资格实际环境：云端 DOLFINx/Basix0.10.0、petsc4py3.25.6、PETSc complex128/int32；与用户 WSL 历史 ABI 分开。Ruff/tool absence、全库pytest/CI和GitHub rendered view均未完成，不伪造通过。新增 named payload512MiB与 whole-tree1.5GiB cap 分开，不能混加。

## 后续 Fourier 面作用

优先完成原 H 后，再将 Basix `coefficient_matrix` 在 z=0/1 限制为两切向 tensor polynomial map，使用相同 production Gauss 点/权重做 x/y 一维 Fourier 矩表。每个任意三维边界场先经实际 Tt orientation 和 MPC 展开，再作 x/y 矩阵收缩；牵引反作用经对应 T orientation 与 C^H。矩形 tensor-grid 的 x/y 可以非均匀，非均匀时不用 FFT。共享的是积分矩表，不是物理场或材料的 y 不变性。

保持原模式清单、复 beta、有限 z plane phase、极化、投影分母和非 Hermitian B/D。首个实际 3D p2 fixture 用 3×2×2 cells、非均匀 x/y、G0 periods 和 manual (7,1) 全 180 modes，任意复数填所有独立三维 DOF，必要时逐列检查整个算子。再升 p4/p6。原组件的 1e-13 sparse cutoff 不是 tensor identity，必须比较 native coefficients 和 full original action，不能静默改 mask。

现有 `fullspace_n1e_sum_factor.py` 已提供 canonical N1E coefficient→tensor Legendre 机制，`fullspace_partial_assembly.py:466–513` 给真实 Tt/T gather/scatter；当前没有 Fourier face integration 路径。体积和未来三维缺口不受该边界表示改变；不规则 port mesh 使用原完整 3D carrier fallback。
