# V3 side inverse oracles

本页记录 V3 中用于判断 side inverse 强度和内存边界的研究型实验。side inverse 是
对 bottom/top 局部端口方程的近似或精确求解动作；它只负责帮助全局 Hybrid 外层减少
残差，不能单独证明完整场的物理结果。

## 为什么需要 exact-side oracle

前面的 ILU(0)+动态 DtN Woodbury 和 ILU(1)+同一 Woodbury 都是便宜的近似动作，但
side survey 已显示它们无法把固定探针的收缩比压到 Review V3 的候选阈值。为了区分
“side inverse 不够准确”和“全局接线/外层算法错误”，V3-11 暂时对 bottom/top 各做
一次 exact sparse factor，并把它们放进 block-LDU 右侧动作。这样得到的是一个很强的
数值参照，不是要把 exact factor 永久放进 ordinary default。

exact-side-LU 的通俗含义是：对每个 side 的稀疏局部矩阵做一次直接分解，之后每次应用
时用该分解直接解局部方程；动态 DtN Woodbury 再补上外部模态耦合。因为局部逆很强，
V3-11 的 global outer 在零初值下只需 1 iteration，五项 residual 为
`2.1012097178118034e-10`（reported）、`2.101215469783556e-10`（global）、
`9.069753750374526e-12`（bottom）、`1.9504812155317952e-10`（top）和
`4.337217395416258e-11`（modal）。这解释了“为什么 1 步收敛”，但不等于 production
PC：exact factor 的内存/构造成本和跨模型可复用性尚未经过 ordinary contract。

## V3-11 measured evidence

| 项目 | 结果 |
| --- | --- |
| model / source | 5 nm、1°、phi=0、S、p6/h5、M480、MPI8；source `a6e3f6965e84b9e4594942d4ef372f1eff475e36` |
| classification | `USER_AUTHORIZED_EXPERIMENTAL_HYBRIDIZED_DIRECT_SIDE_CANDIDATE_D`，`research_only=true` |
| outer | 1 iteration，reason `2`；matrix repeat `1.88538277676491e-12 <= 1e-10`；LU repeat `0 <= 1e-13` |
| physics | R/T/A/A_volume `0.7397405130785104 / 0.00021574916967245767 / 0.26004373775181716 / 0.2600443738593008`；traction、projection、Hybrid-direct checker pass |
| external modes | exact 600 keys；bottom/top `296/304` |
| resource | peak `53634355200 bytes = 51149.70703125 MiB = 49.95088577270508 GiB`，swap `0` |

相对同物理 1° Hybrid direct `87064.125 MiB` 节省
`35914.41796875 MiB = 41.250535704287%`；相对 Full3D direct `96151.16796875 MiB`
节省 `45001.4609375 MiB = 46.802822979879%`。两次 heap cleanup 的 before/after
证据、factor cleanup 后 `0/0/0`、以及 direct reference 未加载事实见
[V3-11 compact record](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v3_11_candidate_d_inter_side_cleanup_formal_v1.json)。

Full3D 的严格逐通道幅度比较仍是 diagnostic-only；它的 secondary checker 不会否决
Hybrid-direct authority。V3-11 通过的是这个用户授权研究 oracle 的 numerical/physics/resource
边界，不是 `Hybrid iterative production qualified`。Candidate E 的结果见下节；本页没有
宣称 P4 或 production success。

## Candidate E：固定残差误差子空间 side-capacity

Candidate E 不使用 exact LU，而是在现有 ILU(0)+动态 DtN Woodbury 动作上增加一个固定的
线性误差校正。它用 8 个预先冻结且不与验证向量重叠的 global-index seed，经过 16 层
block-Arnoldi/MGS 建立误差子空间；训练阶段不使用 physical RHS、direct residual 或
validation probes。这个实验回答“固定低秩误差子空间是否足以补足便宜 side action”，
不等同于完整 global solve。

| 项目 | bottom | top |
| --- | ---: | ---: |
| retained rank / layers | `32 / 16` | `32 / 16` |
| R condition | `12.404244482859818` | `11.33900546651523` |
| QR reconstruction / Q orthogonality | `3.4844e-16 / 3.9968e-15` | `3.5224e-16 / 2.8866e-15` |
| median / worst rho | `6.767346265947249 / 7.752279149310453` | `9.429046770914342 / 10.4485053168248` |
| Gate `median<=0.1, worst<=0.3` | fail | fail |

bottom 的零 physical side RHS 被明确排除，不把零向量的 `rho=0` 混入统计；两侧其余
验证向量均完成且 finite。两侧 base ILU factor 各为 `1`，local/global direct factor
为 `0/0`，同时 live base factor 为 `2`，清理后为 `0`。Candidate E 因此正式分类为
`USER_AUTHORIZED_CANDIDATE_E_NUMERICAL_NEGATIVE`，不是 implementation failure，也不是
resource failure。它比 C1 的 contraction 明显好，但仍远差于 Candidate B 32-step 的
约 `0.9486/0.9618`（bottom）和 `0.9699/0.9792`（top），不进入 global outer，也不
扫描 seed、rank 或 depth。

资源口径必须分开：全过程 process-tree peak 为
`53583581184 bytes = 51101.28515625 MiB = 49.90359878540039 GiB`，发生在
`post_coupling_heap_cleanup` 前的 internal-coupling setup transient；Candidate-E
side-online 区间 peak 为 `17618.02734375 MiB`，swap=`0`。前者低于 `69651.3 MiB`
只说明本次 side-capacity 资源子Gate通过，不能替代 production Hybrid iterative 的
全过程资格。

本次为重建 `x*` 和 direct-solution-side-residual 读取了 hash-bound direct payload，但
没有物化 independent reference、global KSP、recovery 或 field/RTA。compact record：
[`task039_v3_8_candidate_e_side_capacity_formal_v1.json`](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v3_8_candidate_e_side_capacity_formal_v1.json)。
