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
