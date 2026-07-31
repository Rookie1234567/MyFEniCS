# Task036 exact Cauchy / port-operator / failing-channel sensitivity audit

## 1. 结论先行

本审计完成了 Review V5 接口内移负结果之后的根因分离，但**没有运行新的 Full3D 或
Hybrid forward PDE，也没有实现 actual enrichment candidate**。

| 审计问题 | 结论 | 数据身份 |
|---|---|---|
| M120 electric trace 是否足够 | 中间平面很好，10/110 nm 端点仍有约 `1e-6` 量级缺口 | measured, frozen Full3D replay |
| M120 joint Cauchy 是否足够 | 不足；traction 缺口比 electric 缺口明显更大 | measured, exact one-cell weak conormal |
| left/right port pair 是否退化 | 否；白化后的 inf-sup 最小奇异值为 `0.9999803` | measured |
| M120 中间传播算子是否错误 | 不支持；40/60/100 nm 上与 exact FE selected operator 只差约 `2e-11` | measured |
| 16 个失败通道是否由少量共同方向主导 | 否；达到 95% 方向能量需要 16/16 个方向 | measured, algebraic adjoint |
| 唯一冻结的 enrichment family | `transfer_optimal_port_modes` | decision |
| production qualification | fail，仍为 research-only | decision |

通俗地说，当前 Hybrid 的“中间传播器”在它已经保留的 120 个正向和 120 个反向模态中
工作正确；问题是靠近上下端部的真实场还含有这组模态没有表示好的**电场与磁场联合边界
信息**。只看切向电场会低估这个缺口，磁牵引（Maxwell 弱式中与 `n x H` 成比例的离散
边界量）才暴露了更明显的误差。因此下一步不应继续移动接口或扩大 global M，而应从短端部
buffer 的 exact discrete transfer operator 中提取少量最有效的 joint-Cauchy port modes。

## 2. 身份、范围和方法

| 项目 | 值 |
|---|---|
| numerical source | `c8725e9eedc8a558719008f8762bc79eca48fbb7` |
| frozen Full3D / one-cell oracle source | `c70ad32e3cb741f382e2cc901e056ae1ea0ba284` |
| environment | WSL Ubuntu 24.04, PETSc `complex128/int32` |
| MPI | 8 |
| audit runtime | `134.992 s` |
| new Full3D/Hybrid forward solve | `false` |
| actual enriched candidate | `not_run` |
| ordinary default | unchanged |

本审计复用了 A004-S 的 frozen Full3D 场和已经资格化的一层 10 nm one-cell 离散算子，执行
以下五步：

1. 在 `z=10,30,40,80,90,110 nm` 提取 exact tangential `E` 和离散 weak conormal；后者
   是 Maxwell 弱式中的边界通量，物理上与 `n x H` 成比例，不是对点值 `H` 的采样。
2. 用同一 M120 right/left port pair 分别拟合 electric、traction 和两者联合的 Cauchy 数据。
3. 将 one-cell interior 精确 Schur 消元后，以稳定的 projected star product 组合成
   40/60/100 nm port action；全程只解 240 阶小系统，没有形成 2400 阶稠密接口平方矩阵。
4. 在 actual Full3D traces、selected R/W coordinates 和固定 test-space complement 上比较
   exact FE operator 与当前 Hybrid modal operator。
5. 对 old/I1/I2 持续失败的 16 个通道各求一个局部代数 adjoint，检查其接口灵敏度是否能
   由少量共同方向表示。

## 3. Exact trace 与离散 `n x H`

下表中的 electric residual 是 frozen Full3D tangential trace 到 M120 electric space 的相对
最佳逼近误差。conormal norm 是相邻 one-cell 从各自 outward-normal 弱式得到的离散边界量
范数；其完整数组和 SHA-256 保存在 raw NPZ 中。

| z, nm | electric projection residual | lower-cell right conormal norm | upper-cell left conormal norm |
|---:|---:|---:|---:|
| 10 | `3.514657e-6` | — | `1.377444e-1` |
| 30 | `2.881133e-9` | `1.690007e-1` | `1.690007e-1` |
| 40 | `8.852121e-11` | `1.894700e-1` | `1.894700e-1` |
| 80 | `3.717966e-10` | `3.205683e-1` | `3.205683e-1` |
| 90 | `8.687625e-9` | `3.694642e-1` | `3.694642e-1` |
| 110 | `5.224931e-6` | `4.937261e-1` | — |

左右 conormal norm 的相等只能证明量级一致，不能直接按 active-row 下标相加；左右端面使用
不同编号和 orientation。共同 Petrov 坐标中的正确内部通量连续性为：

| z, nm | selected Petrov outward-flux cancellation residual |
|---:|---:|
| 20 | `5.731155e-5` |
| 30 | `1.680891e-6` |
| 40 | `4.521839e-8` |
| 50 | `1.190862e-8` |
| 60 | `5.723689e-9` |
| 70 | `1.206690e-8` |
| 80 | `2.836628e-7` |
| 90 | `7.255060e-6` |
| 100 | `2.000710e-4` |

中心区域达到约 `1e-8` 至 `1e-9`，越接近两端越差。这与“中间传播健康、端部联合 Cauchy
空间不完整”的解释一致。

## 4. M120 Cauchy best approximation

| 拟合量 | retained rank | aggregate relative | max cell relative | 最大误差位置 |
|---|---:|---:|---:|---|
| tangential electric | 240 | `1.099844e-6` | `2.072564e-6` | `100–110 nm` cell |
| magnetic/traction | 240 | `2.364065e-5` | `4.609620e-5` | `100–110 nm` cell |
| joint Cauchy | 240 | `1.677328e-5` | `3.214277e-5` | `100–110 nm` cell |

traction aggregate residual 是 electric 的约 21.5 倍。两端 cell 的 joint residual 分别为
`1.477075e-5`（10–20 nm）和 `3.214277e-5`（100–110 nm），而中心 cell 已下降到
`1e-10` 左右。结论不是“电场 trace 完全错误”，而是 **E-only port qualification 不足以
证明 Maxwell Cauchy closure**。

## 5. Port pair conditioning

| 指标 | 值 | 解释 |
|---|---:|---|
| right self-Gram condition | `3.117939e4` | raw coordinates 有尺度差异 |
| left self-Gram condition | `4.226209e4` | raw coordinates 有尺度差异 |
| raw left/right pair condition | `2.987804e3` | 不能直接作为物理稳定性结论 |
| whitened pair condition | `1.00001975` | 基底不变量，接近理想值 1 |
| inf-sup smallest singular value | `0.99998025` | 没有接近零的 coupling direction |
| largest singular value | `1.00000000` | 稳定 |

因此问题不是 right/left port pair 的物理 Gram 退化。raw condition 较大来自坐标尺度，白化
以后 pairing 几乎等距。

## 6. Exact FE port operator 与当前 modal operator

one-cell authority 有 10,755 个 full rows、4,440 个 active rows、左右各 1,200 个 active
trace rows、2,040 个 axial-interior rows和 1,987,800 个 matrix NNZ。row hash 与 frozen
oracle 完全一致，且 `dense_interface_square_formed=false`。

| middle | exact FE vs modal selected operator | exact projected trace vs modal | actual Full3D selected trace vs modal | fixed-coordinate test complement | max star pivot cond |
|---:|---:|---:|---:|---:|---:|
| 40 nm | `1.593747e-11` | `2.876616e-10` | `2.593052e-9` | `0.949043` | `8.552388e3` |
| 60 nm | `1.749079e-11` | `1.296325e-10` | `4.884751e-8` | `0.949067` | `8.552388e3` |
| 100 nm | `1.951491e-11` | `1.627597e-10` | `2.851172e-5` | `0.949119` | `8.552388e3` |

每次 star-product solve 的相对残差不高于 `1.76e-16`。第一列说明：在 selected M120
R/W space 内，当前 scalar-CG modal core 与 exact FE port action 已经一致到约 `2e-11`；
没有证据支持继续修改 core propagation。

`0.949` 只是在固定 independent-row Euclidean 坐标中的 test-space complement diagnostic；
它依赖坐标尺度，**不得解释为 94.9% 的物理能量缺失**。有物理意义的信号是 actual selected
trace 的差异随 40→100 nm 从 `2.59e-9` 增长到 `2.85e-5`，以及 joint Cauchy endpoint
residual 同时处于 `1e-5` 量级。

## 7. 16 个持续失败通道的 adjoint sensitivity

16/16 个局部 Hermitian adjoint 的相对残差均不高于 `1.776730e-12`。灵敏度使用代数上正确
的 `D z`（selected M120 Petrov coordinates），没有把 adjoint 当成 primal field 强行恢复。

| 指标 | 值 |
|---|---:|
| first direction energy fraction | `0.063915` |
| first two directions energy fraction | `0.127827` |
| rank for 90% | 15 |
| rank for 95% | 16 |
| rank for 99% | 16 |
| zero sensitivity rows | 0 |

因此 16 个输出并不由两三个共同 residual directions 主导。若直接选择 failing-channel adjoint
modes，几乎会变成“每个失败输出增加一个专用模式”，可迁移性和压缩效率都差。

局部 fixed-trace prediction 与 old-Hybrid minus Full3D 的 16 通道 actual delta 的向量相对
误差为 `0.999467`，绝对 cosine 为 `0.491456`。所以本 adjoint 审计只获得方向结构 credit，
不获得逐通道定量预测或完整因果 closure；报告没有用它追认任何 candidate。

## 8. 一个被撤销的 raw diagnostic

raw `audit.json` 中字段
`exact_cauchy.all_internal_conormal_cancellation_relative` 使用左右端面各自的 1,200 维
active-row 顺序直接相加，得到约 `1.37` 的值。左右 row map 不同，该运算没有物理意义，
现正式标记为 **withdrawn**。

替代值是第 3 节列出的共同 selected Petrov 坐标重放结果。它从原 coordinate-matched
`projected_one_cell_blocks.npz` 和 `exact_petrov_plane_coefficients.npz` 离线重算，未重跑 PDE。
runner 也已改为今后只输出这个 side-specific Petrov diagnostic。

另一个需要保留的数值边界是：near-degenerate QEP basis 可在等价子空间中旋转和重新定相，
所以 live/frozen coefficient coordinate 差为 `3.12e-2`、projected block coordinate 差为
`3.78e-1`，不能跨 basis 混用坐标数组；但 reciprocal negative map 的相对差仅
`2.47e-14`。本审计的物理比较全部在同一个 live basis 或原 frozen coordinate-matched pair
中完成。

## 9. 冻结的唯一 port enrichment

本轮只提出一个后续 family：

```text
transfer_optimal_port_modes
```

选择理由：

1. selected M120 core operator 已通过约 `2e-11` 的 exact FE 对照，没必要改传播算法；
2. 端点 joint-Cauchy/traction 残差明确，而普通 E-trace enrichment 已被前一阶段关闭；
3. 16 个 output-adjoint directions 基本满秩，不适合逐通道加模式；
4. transfer-optimal modes 可以从短 buffer 的 exact discrete port operator 中，按 joint
   trace/traction 传输重要性提取共同模式，并只在两端局部存在、随后 Schur 凝聚；
5. 目标仍是恢复 `10/110 nm` 接口，让 M120 core 跨越完整 100 nm，而不是扩大 3D endcap。

`cauchy_complete_discrete_bloch_correctors` 和 `failing_channel_adjoint_modes` 没有同时实施。
本轮也没有实现 transfer-optimal modes，因此尚不存在可用于 forward PDE 的“成功修正”。
只有后续实现通过 exact fixture、joint-Cauchy projection、row-map/orientation 和资源 preflight
后，才有理由运行一次 A004-S actual PDE；单纯修正文档/diagnostic 不触发重跑。

## 10. 时长和证据

| phase | seconds |
|---|---:|
| one-cell assembly + interior factor | `20.987` |
| QEP projection + endpoint lifts | `26.323` |
| live selected port action | `1.834` |
| exact Cauchy action, 10 cells | `0.061` |
| directional Cauchy basis | `1.439` |
| local operator + coupling reassembly | `71.796` |
| bottom eight adjoints | `3.304` |
| top eight adjoints | `3.321` |
| total | `134.992` |

| evidence | path / SHA-256 |
|---|---|
| raw audit | `benchmarks/artifacts/task036/c8725e9eedc8a558719008f8762bc79eca48fbb7/review_v5_cauchy_port_audit/audit.json` / `f2c1bd8fa6e88a00b8696ad88c97a5a74d37fd57330420923eee418127787998` |
| exact Cauchy raw NPZ | sibling `work/exact_cauchy_traces.npz` / `d271b32013def15540e86da33bdf27a832cb331c5e4b8d0292b4f7645640fe35` |
| 16-channel adjoint raw NPZ | sibling `work/persistent_channel_interface_adjoints.npz` / `09bca971d5c503f61b361e2862861bfa5497e9f413bb571dfbe1b684f3829683` |
| tracked compact | [`../../../benchmarks/cases/099_strong_trace_hybrid_fixture/records/a004_exact_cauchy_port_audit_v1.json`](../../../benchmarks/cases/099_strong_trace_hybrid_fixture/records/a004_exact_cauchy_port_audit_v1.json) |

最终状态：

```text
exact_Cauchy_audit = complete
selected_M120_core_operator = qualified_inside_selected_space
endpoint_joint_Cauchy = incomplete
few_common_failing_channel_directions = false
frozen_next_family = transfer_optimal_port_modes
actual_candidate = not_implemented / not_run
Hybrid production = fail
ordinary default = unchanged
master merge = not_authorized
```
