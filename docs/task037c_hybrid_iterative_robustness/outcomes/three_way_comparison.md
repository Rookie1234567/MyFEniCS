# Task037c 三路比较与 controlled diagnostics

## 比较规则

Full3D/direct/iterative 的比较必须先绑定 source SHA、record SHA、方位角、方法和 mode keys。
R/T/A/A_volume 使用任务书规定的绝对误差；显著通道只选择两侧最大 power 不小于 `1e-8` 的
通道，并使用 relative delta `<=1e-4`。因此低功率通道的 relative 失败不能被总量通过掩盖。
复数 amplitude 的跨 phi 镜像比较不在本轮作为 Gate；同 phi 的正式 comparator 才使用共同外部
Fourier identity。raw QEP coefficient 不是 gauge-invariant 证据。

## 九份 R3 comparator

| phi | 比较 | comparator path | SHA256 | pass | 关键结果 |
|---:|---|---|---|---|---|
| 0° | M120 vs M160 | [`compare_phi_0_m120_m160_6555663.json`](</home/Projects/MyFEniCS/benchmarks/artifacts/task037c/r3/compare_phi_0_m120_m160_6555663.json>) | `8c59180a4e80c77d7d992d6e178dfa008caec1e36327e3abd13dc812045978f4` | true | 12/12 significant；R/T/A绝对差通过 |
| 0° | M120 vs Full3D | [`compare_phi_0_m120_full3d_6555663.json`](</home/Projects/MyFEniCS/benchmarks/artifacts/task037c/r3/compare_phi_0_m120_full3d_6555663.json>) | `bd035b44c9e0fce4eab335ec66795f554be7bd7ce0abb6c57eb0a042a476e6ef` | true | 12/12；最大 order relative 约`1.49e-9` |
| 0° | M160 vs Full3D | [`compare_phi_0_m160_full3d_6555663.json`](</home/Projects/MyFEniCS/benchmarks/artifacts/task037c/r3/compare_phi_0_m160_full3d_6555663.json>) | `8d9cdbc8032408ccecac57a17f4d8291fdb1e32996b55c2475f116fe3712d5d9` | true | 12/12；最大 order relative 约`6.93e-10` |
| -5° | M120 vs M160 | [`compare_phi_m5_m120_m160_6555663.json`](</home/Projects/MyFEniCS/benchmarks/artifacts/task037c/r3/compare_phi_m5_m120_m160_6555663.json>) | `89d18db8604537c9a4df7d8ed67211d32b68697de4bf3a6c9324a6d5229490dd` | true | 23/23；最大 order relative约`7.03e-7` |
| -5° | M120 vs Full3D | [`compare_phi_m5_m120_full3d_6555663.json`](</home/Projects/MyFEniCS/benchmarks/artifacts/task037c/r3/compare_phi_m5_m120_full3d_6555663.json>) | `f2e2c10b20f917d835b5532c2ad03cda54bb25fafa70fbb114d58a9e1e8235c0` | false | 11/23 failed；max `2.4023028e-3` |
| -5° | M160 vs Full3D | [`compare_phi_m5_m160_full3d_6555663.json`](</home/Projects/MyFEniCS/benchmarks/artifacts/task037c/r3/compare_phi_m5_m160_full3d_6555663.json>) | `3c445cb5c8f5a81305d030c240025db7fd6e477efa936fd995270a1dfda853e7` | false | 11/23 failed；max `2.4016014e-3` |
| +5° | M120 vs M160 | [`compare_phi_p5_m120_m160_6555663.json`](</home/Projects/MyFEniCS/benchmarks/artifacts/task037c/r3/compare_phi_p5_m120_m160_6555663.json>) | `2e7c1f10db58a674e780e0fc072f2d5c8c55d37270811dc44a9aba6674015b69` | true | 23/23；最大 order relative约`7.37e-7` |
| +5° | M120 vs Full3D | [`compare_phi_p5_m120_full3d_6555663.json`](</home/Projects/MyFEniCS/benchmarks/artifacts/task037c/r3/compare_phi_p5_m120_full3d_6555663.json>) | `18c5f651e48281942640e7f0190eabd9986b683f83e49ef67da0175e5c246722` | false | 11/23 failed；max `2.4022709e-3` |
| +5° | M160 vs Full3D | [`compare_phi_p5_m160_full3d_6555663.json`](</home/Projects/MyFEniCS/benchmarks/artifacts/task037c/r3/compare_phi_p5_m160_full3d_6555663.json>) | `fdac373488495137bdac857d8803a3a816e6e16cdaba2f9d0af5e143d7f11ccb` | false | 11/23 failed；max `2.4015353e-3` |

## 失败的物理范围

失败 key 在两个非零 phi 下呈镜像结构，主要是低 power 的 p/s order，例如
`(bottom,-2,0,p)`、`(top,-2,0,p)`、`(bottom,-7,0,p)` 和对应 side。四份失败记录的
R/T/A/A_volume、closure、coordinates、interface E/H 和 middle-plane E/H 均通过；失败只在
显著 order power relative Gate。absolute 差约 `9e-12`--`7.4e-11`，所以这是小的绝对误差被
`1e-8` 显著性下限放大后的可见鲁棒性差异，不是总能量失配。

R3 的直接路径审计确认：

- S basis 随 phi 旋转，Floquet `kx/ky` 与方向 audit 一致；
- external mode keys 从正式枚举器逐 side 生成，-5°/+5° 各为42，未裁成40；
- local auxiliary index、beta branch、Poynting/power export 和 Full3D order keys可重算；
- scalar CG traction 链和 q identity 均通过；
- M120 到 M160 的失败通道最大变化约 `7.37e-7`，远低于 `1e-4`，不支持“模态数量不足”解释。

因此本轮分类为 direct Hybrid 模型/traction 与低功率通道的非零方位角鲁棒性负结果，
不是 comparator bug，也不是 modal truncation 负结果。

## 两份 controlled iterative comparator

两次诊断均在 linear Gate失败后写出 `online_pass=false`，comparator按正式输入合同安全停止，
没有把“未比较”写成 numerical failure：

| phi | comparator | SHA256 | pass | 状态 |
|---:|---|---|---|---|
| -5° | [`compare_iterative_phi_m5_m160_vs_direct_6555663.json`](</home/Projects/MyFEniCS/benchmarks/artifacts/task037c/r4_diagnostic/compare_iterative_phi_m5_m160_vs_direct_6555663.json>) | `a58068d90180ecb73773aa8daebacb982644443be09835f3d097416ec10ad955` | false | `load:watchdog has failures`; numerical fields `not_run_due_linear_gate` |
| +5° | [`compare_iterative_phi_p5_m160_vs_direct_6555663.json`](</home/Projects/MyFEniCS/benchmarks/artifacts/task037c/r4_diagnostic/compare_iterative_phi_p5_m160_vs_direct_6555663.json>) | `a58068d90180ecb73773aa8daebacb982644443be09835f3d097416ec10ad955` | false | 同上 |

## 三路资格结论

正式 three-way 需要 Full3D direct、选定 M 的 Hybrid direct、Hybrid iterative 以及三组
pairwise comparison 全部通过。由于统一 M 未建立且正式 iterative 没有通过，R4/R5/R6
均为 `not_run_by_gate`；不能把两份 solver-vs-direct diagnostic升级为 three-way evidence。

## Final f2d7719 / 2dbf898 closeout

以下是用户授权 research extension 的新证据，不能与上文 `6555663` 的历史 negative
结果混写。final-f2d 的 direct M120/M160/Full3D 三角度九份 comparison 全部 `pass`，
所以该扩展选择 `M_robust=120`；三角度 iterative-vs-Full3D 与 iterative-vs-direct
也全部 `pass`。比较器仍使用冻结显著 order 和 observable Gate，没有放宽阈值。

### Final direct/M-selection comparisons：9/9 pass

| phi | comparison | output SHA256 | status |
|---:|---|---|---|
| 0° | M120-vs-M160 | `b0cdd12408a6f10d371e02fcf7395099b98c30d04eaeccc2d741c0156abdb044` | pass |
| 0° | M120-vs-Full3D | `80d3563c613d0cc6e4ce3e6c42c84a5a8af70cbc2093cfc078683b74415afb17` | pass |
| 0° | M160-vs-Full3D | `b1e807cdfeb68bcd649d76988053df3db38d8be1f71c70f63b4b27c5e1b72d4c` | pass |
| -5° | M120-vs-M160 | `91e90775b103db5fd3ff7928a8adce73836d811f84be25874d996de7b93ffd39` | pass |
| -5° | M120-vs-Full3D | `9ebb41d000125ad1c1f4ab94af99e65b3e9e55b4879019548458d4c8f68a67f2` | pass |
| -5° | M160-vs-Full3D | `477874707df5fe3e9a6360cedb64cd848da391d8b2142508c7638c212d2165c8` | pass |
| +5° | M120-vs-M160 | `b016d63052361ee1ee89ff689c376f5ebe7b151dbb2b4932b587743910362159` | pass |
| +5° | M120-vs-Full3D | `c8e015dffdbd3a9424d8f530572ac1dfdac2d5e92d4e422ddcfdae13b3010d1c` | pass |
| +5° | M160-vs-Full3D | `310d22edb1124b34f6663b0ec761e4c40df46cffb347e901fe58816ccffdca2a` | pass |

### Final iterative pairwise：6/6 pass

| phi | iterative-vs-Full3D SHA256 | iterative-vs-direct SHA256 | status |
|---:|---|---|---|
| 0° | `bb966f4ebc04bc56924173686f5eae45cb88913fd32d7209d7e33455c0a294f0` | `17d9fdf073f17daf9d179222e81de526cef5721abc504488cea57e34542adf8b` | pass / pass |
| -5° | `d8c658e83ac45efd332ff9d34491a9d51cab65b6f21198e9aaaddfe9903c3f12` | `a2f025c1d5388801c271db14851d346e069c75257c64bdf45df7d6aaa9033e3c` | pass / pass |
| +5° | `685d9f15c8258799ada4f6ed45645df6fe06c0bb05afe0cb82bc9763f03d259b` | `6c4a21ede5c9daeb609241cce2cb23cd379f8dd3a411a830833a60978429b8d9` | pass / pass |

### MPI1 identity 与镜像边界

final-f2d 的 MPI1-vs-MPI8 identity comparison 为 3/3 pass；输出 SHA256 依次为
`f56665b5340498b3dbc8f75a4625bea351224a770b333cf1ff76da065e98b987`、
`58b5d980c04de3a351faae969979f63ce2478b08cf7eea966a13cd7189c99542`、
`61b962395952798e7110f7c0a7c4237ec596f8cd735a407a6f8f66905661492b`。
镜像审计确认冻结标量材料与 y 周期几何对称，Full3D、direct M120、iterative M120
的 power-only mirror 均 3/3 `pass`；三组复振幅均为 `not_run_without_phase_map`。

完整 raw path 与 source/input SHA 绑定见
[MPI8 compact record](../../../benchmarks/cases/102_hybrid_iterative_robustness/records/task037c_mpi8_three_way_qualification_v1.json)
和 [MPI1 compact record](../../../benchmarks/cases/102_hybrid_iterative_robustness/records/task037c_mpi1_identity_and_resource_v1.json)。
忽略目录 raw 文件使用反引号路径，不生成不可访问的 `/home/...` Markdown 链接。
