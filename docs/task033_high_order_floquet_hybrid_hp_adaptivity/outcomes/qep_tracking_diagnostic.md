# Task033 Phase A：QEP tracking 诊断与闭合

## 1. 结论

Phase A 已闭合：

- p3 patterned tracking 保持通过；
- p4 原 `0.484436658879` 单模 overlap 失败被严格识别为四维近简并子空间内的基底旋转，
  p4 block/subspace tracking 通过；
- p2 h5→h3 的 `0.260868635757` beta drift 是真实粗网格谱漂移，仍按冻结阈值失败；
- p1 的解析误差、谱支集合和传播方向均不稳定，仍为低阶诊断负结果；
- p3/p4 h3 的 MPI1/2/4 数值身份通过；
- 普通 p2 Task032 QEP/模式分类回归通过。

因此，高阶 QEP 组件的阶次状态为：

```text
p1 = not_qualified
p2 = not_qualified for Task033 patterned h5→h3 trend
p3 = qualified
p4 = qualified by basis-invariant block/subspace tracking
legacy all-degree aggregate = qep_component_aggregate_not_qualified
```

保留 legacy all-degree aggregate 的负状态，是因为它仍要求 p1/p2/p3/p4 同时通过；这不再阻塞
p3，也不再把 p4 的块内基旋转误写成物理失败。

## 2. 数据与源码身份

| 对象 | 身份 |
|---|---|
| 原 36 个 MPI1 measured shards | `6613f94b91ebc77eb50e74086475c67df46236f6` |
| block/subspace tracking 与复测源码 | `bb830ba5dd74ced30475402bd6bc6d3c1856c630` |
| Docker image | `myfenics-stage4:task28` / `sha256:08c61b2...76d` |
| Case090 canonical evidence | `fe7825b90e6e5a2f84d66f2ba7305d38e4d87676a677382f19e50ee37c862718` |

算法修改只发生在 aggregate/qualification 层；QEP 矩阵装配、求解、左右特征向量、公共
Fourier fingerprint 的测量方法均未变化。因此，审阅指定的 p1/p2/p4 MPI1 最小矩阵使用原
measured compact inputs 做精确离线重放，没有重复求解相同 PDE。新增 PDE 仅为审阅明确要求的
p3/p4 h3 MPI2/4 正向身份测试。

## 3. 算法

原单模 Hungarian assignment 保留不变，阈值仍为：

```text
single-mode symmetric left/right Fourier overlap >= 0.5
relative beta drift <= 0.25
```

对 shard 已测得的 `near_degenerate_groups`，新增基底无关的块跟踪：

1. 在相同公共 Fourier probe 字典上，分别对 right fingerprints 和 left fingerprints 构造
   正交子空间基；
2. 用 SVD 计算 right/right 与 left/left 子空间的 principal cosines；
3. 取两侧最小 principal cosine 的几何平均作为 symmetric block overlap；
4. 同时要求块大小相同、左右 fingerprint 满秩、传播方向兼容、块中心 beta drift `<=0.25`；
5. 只有当所有低单模 overlap 都落在完整通过的近简并块内时，才允许以
   `near_degenerate_block_subspace` 解释基旋转。

block overlap 门槛仍为 `0.5`，没有放宽原 Gate。真实 beta 漂移、块维数变化、秩亏或方向变化
均继续失败关闭。

## 4. p4 h5→h3 诊断

失败附近是同一个四维近简并块 `[4,5,6,7]`。

| h/nm | 最大右残差 | 最大左残差 | 四维块 beta 中心 |
|---:|---:|---:|---|
| 5 | `1.32144e-14` | `2.48937e-14` | `0.206456854490 + 0.000651840310j` |
| 3 | `8.86635e-16` | `1.71492e-15` | `0.206457022002 + 0.000651839998j` |

| 指标 | 结果 | Gate |
|---|---:|---:|
| modes 4↔5 最小单模 overlap | `0.484436658879` | `0.5` |
| 四维块中心 beta drift | `8.11363e-7` | `0.25` |
| 四维块最小 symmetric principal cosine | `0.999999999999851` | `0.5` |
| h5 / h3 相对外部谱间距 | `0.0437091 / 0.0437030` | diagnostic |
| right/left 子空间秩 | `4/4`、`4/4` | full rank |

beta 几乎不动、左右残差很小、四维子空间几乎完全相同，而单个基向量发生旋转。因此分类为
`near_degenerate_basis_rotation_resolved=true`，不是 sorting error、错误放宽阈值或真实子空间漂移。

## 5. p1 与 p2 解释

### p1

air 的解析 beta 相对误差为
`0.543705 → 0.664734 → 0.908817`，lossy homogeneous 为
`0.571713 → 0.697992 → 0.952071`；误差随 h 细化反而增大。

patterned h5→h3 的最小 overlap 约 `1.02e-12`、最大 beta drift `1.20599`，并出现 backward
分支在 h3 候选集合中消失；h3→h2.5 也有约 `1.11763` 的最大 drift。部分二维块的子空间仍相似，
但对应块中心移动约 `30.5%`，且整体块数量/方向不闭合。因此 p1 是低阶分支容量与筛选稳定性问题，
不是简单排序错误；按审阅意见只保留 regression/diagnostic 身份。

### p2

p2 h5→h3 的 modes 0/1 单模 overlap 分别为 `0.999947`、`0.998961`，说明配对本身稳定；
但 beta drift 分别为 `0.260868521`、`0.260868636`。对应二维块最小 principal cosine
`0.999047`，块中心 drift 仍为 `0.260868579`。因此这是粗 h5 离散造成的真实谱位置漂移，
不能由 block tracking 消除，也没有把阈值从 `0.25` 放宽。

p2 h3→h2.5 已通过，最大 drift `0.0269291`。Task032 普通 p2 QEP/模式分类 13 个回归测试通过，
所以该 Task033 patterned 趋势负结果不代表普通 p2 路径回归。

## 6. p3/p4 MPI1/2/4 身份

新增正式正向运行均在 clean source `bb830ba...`、14 GiB container limit、无 swap、900 s
watchdog 下完成。

| degree | MPI | formal pass | 相对 MPI1 最小 overlap | 最大 beta drift | memory authority peak |
|---:|---:|---|---:|---:|---:|
| 3 | 2 | pass | `0.904811335466` | `3.81218e-13` | `0.610775 GiB` |
| 3 | 4 | pass | `0.873000954105` | `4.47319e-13` | `1.042454 GiB` |
| 4 | 2 | pass | `0.750120151492` | `1.43471e-12` | `0.777660 GiB` |
| 4 | 4 | pass | `0.615322049779` | `2.14815e-12` | `1.245392 GiB` |

四项均满足 shard 数值 Gate、source Gate、Case090 reuse Gate、memory authority、no-swap 与 timeout
Gate。之前两个 1 秒 timeout-negative 仍只作为合同测试，不再被用来代替正向 MPI 资格。

## 7. Case090 不重跑的理由

审阅要求“高阶数值行为未变化时不得重跑 Case090”。为同时保持 fail-closed source provenance，
watchdog 新增了严格的非数值后继提交复用审计：

- Case090 source 必须是当前 source 的祖先；
- diff 只允许文档、测试、QEP aggregate qualification 与 watchdog gate 文件；
- `run_task033_qep_matrix.py`、QEP measurement、3D/QEP 装配或求解器等任何数值文件变化都会拒绝复用。

本轮审计的 `disallowed_changed_paths=[]`，故复用 Case090；没有为形式上的新 SHA 重跑 144 个
直接 3D PDE。

## 8. Phase A Gate

| Gate | 结论 |
|---|---|
| 左右残差与双正交 | pass |
| p4 block/subspace tracking | pass |
| p3/p4 selected MPI1/2/4 identity | pass |
| ordinary p2 Task032 regression | pass |
| p1 diagnostic | fail-closed，不阻塞 p3/p4 |
| p2 Task033 h5→h3 trend | fail-closed，不伪装通过 |

Phase A 判定：`PASS_FOR_P3_AND_P4_COMPONENTS`。下一阶段应按审阅报告进入 Phase B 的 matched-trace
小型组件记录；不得恢复完整 36/48/144 项重复 campaign，也不得提前进入自适应阶段。
