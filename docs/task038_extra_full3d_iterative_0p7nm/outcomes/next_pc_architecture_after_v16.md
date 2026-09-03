# V16 之后的 Z0 架构边界

## 先固定当前结论

W0 候选 `wave_aware_interface_schur_dd_v1` 已因接口 trace rank/count 与同时
存活容量无法由现有 authority 闭合而关闭，分类为
`W0_INTERFACE_RANK_CAPACITY_FAIL`，`eligible_for_W1=false`。因此 W1–W4
全部 `locked/not_run`；本文件只登记四个未来研究方向，不把任何一个方向写成
已通过的 PC，也不创建 W1–W4 outcome。

Q1.1 是同一 h50 mesh 的 p6/p3 physical action identity，Q1.2 是 p3/h50
physical inner；两者的 MPI1 资源证据已通过。Q2 是 p6/h10 checkpoint
correction，其 reproduction、inner contraction 和两种 rho 均失败。所以当前
p6/h10 MPI1 的过程树峰值小于 2 GB，只能说明已测窄 physical operator/inner
workflow 在该离散上满足资源线；official physics 尚未完成，0.7nm/2TiB 的
可扩展性也没有证据。数值边界见
[`physical_pcoarse_checkpoint_v16.md`](physical_pcoarse_checkpoint_v16.md)，容量
审计见 [`wave_aware_dd_preflight_v16.md`](wave_aware_dd_preflight_v16.md)。

## 四个候选方向

下表中的“先验/oracle”是未来启动前必须先做的小规模可证伪实验，不是本轮结果。

| 方向 | 要解决的具体 blocker 与数学机制 | 与已关闭路线的机制差异 | 内存风险 | 最小先验/oracle | 本轮不实施的原因 |
|---|---|---|---|---|---|
| **1. PML / complex-shifted sweeping + compressed interface responses** | 真实波动问题的局部逆不具备椭圆问题那样的稳定衰减；在子域边界加入吸收层或复移位，使局部传播响应可控，再用压缩的接口响应近似远场耦合。 | 不是 two-slab Robin 的固定两侧边界；不是 V15 的全局 32 模投影；压缩对象是由局部波传播产生的接口响应，而非把全场投影到全局低秩 basis。 | PML 会扩大局部网格和复数工作量；压缩误差、接口 rank 和每 rank response buffer 可能同时增长，需分别计量。 | 在中等波长的两/四子域模型上比较 exact local response 与压缩 response 的接口 Schur action、残差和 rank；同时记录单次 local solve 的 RSS。 | 尚无通过的接口 rank/误差/容量先验；W0 的 rank cap 已失败，不能先把 PML 或压缩率当作免费修复。 |
| **2. energy-minimizing H(curl) FETI-DP/BDDC on physical local operators** | 通过能量最小的 primal trace 约束和 dual interface correction，减少 H(curl) 子域之间的不一致，使局部物理 Maxwell 解在接口上协调。 | 与普通 GenEO/BDDC/HX 的通用标量或椭圆 coarse basis 不同，局部算子是 physical Maxwell operator；与旧 trace-harmonic/local-spectral 路线不同，约束由能量最小原则和显式 H(curl) 切向/梯度 trace 定义，而不是已有局部谱向量直接拼接。 | primal corner/edge/face 约束、dual multipliers 和局部 saddle-point 工作集会增加内存；全局 coarse solve 还可能重新引入 rank 与通信压力。 | 固定一个接口、少量切向 trace，验证 discrete curl-conforming continuity、energy-minimizing constraint 与 local Schur residual；先用小 dense oracle 核对，再测 owner-distributed storage。 | 需要新的约束/空间身份和独立 rank budget；W0 尚未闭合这些输入，当前没有授权改变 production PC。 |
| **3. matrix-free p-h MG + distributed wave coarse solve** | 用矩阵自由的 p/h 层次减少高阶物理算子的存储，并把剩余长波误差交给分布式 wave-aware coarse solve；目标是改善 Q2 所见的长程 residual stagnation。 | 保留 operator apply 而不建立 global physical AIJ、dense DtN 或 factor；不同于已经失败的 p3→p1 positive cycle，它的 coarse problem 明确承载波动传播；也不同于 V15 rank32 projection，coarse correction 不是一次全局固定投影。 | matrix-free 不等于零内存：每层 basis、restriction/prolongation、coarse Krylov vectors 和通信 buffers 仍同时存活；分布式 wave coarse solve 的 rank/response 可能超过 W0 上限。 | 用一个物理 block 的 exact action 对照 p/h coarse action，测长波 probe 的 contraction、coarse rank、每层 simultanous live set；先禁止全局 dense oracle 进入 production。 | Q2 已表明当前正 pMG correction 不收缩，但新的 wave coarse 机制尚未定义或验证；不能把“matrix-free”当作数值或资源通过。 |
| **4. intermediate-wavelength / reduced-geometry pilot hierarchy** | 先把波长、几何和子域数降到能完整审计的 pilot，隔离“物理波传播”与“0.7nm 全尺寸资源”两个问题，建立可重复的 hierarchy/trace rank 证据。 | 它是资格化实验路线，不是把 two-slab Robin、V15 projection 或普通 GenEO 换名为 production PC；pilot 必须保留 physical local operator、同一 H(curl) trace 和独立 source/provenance。 | 单次 pilot 风险最低，但缩小几何可能低估接口 rank、PML/粗空间通信和 full-scale memory；必须把缩小带来的不可外推项单独列出。 | 选一个中间波长与 reduced geometry，完成 exact-vs-approx interface action、有限个 probe 的 residual/identity、rank/bytes/cold-vs-solver 生命周期审计。 | 这是最适合先证伪的路线，但它不能直接宣称解决 0.7nm/2TiB；在 W0 关闭后，仍需先得到新的 review 授权和明确输入身份。 |

## 建议研究顺序

建议顺序为 **4 → 1 → 2 → 3**：先用 intermediate pilot 以最低资源确认长波/接口
rank 是否随几何变化而失控；若 blocker 确实是波传播，再用 PML/complex shift
建立可压缩的局部响应；随后评估物理能量最小的 FETI-DP/BDDC 约束；最后才把
matrix-free p-h 层次与分布式 wave coarse solve 组合起来。这个顺序只是风险
最小化的研究计划，不是候选通过或 W1 资格。

所有四项都必须重新定义 source、trace、rank、容量和生命周期，并由独立 checker
从 raw facts 判定；本轮不实现任何一个。现有 Q1/Q2 负结果、W0 rank/capacity
failure 和 official physics `not_run` 均保持不变。
