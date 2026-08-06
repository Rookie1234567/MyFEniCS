# Task037-extra G0 response v1

## 本轮范围

G0 现在有两个互补证据：唯一一次 opt-in G0 screen20，以及同机唯一一次 ordinary
M3a MPI1 full baseline。本轮没有开始 G1，也没有再次运行 PDE。screen 用于检查
M3a identity、factor inventory、residual trajectory 和安全资源；full 才完成收敛、
official postprocess 与 R/T/A。

| 证据 | source | solver | official/RTA | process-tree RSS |
|---|---|---|---|---:|
| screen20 | `568f1ac189f98227541722b1de66cd7804e0cc80` | 20 步 `DIVERGED_MAX_IT (-3)` | false / 未产生 | `6.259979248046875 GiB` |
| ordinary full | `77d39cbe461204f9e095fb6596ad5b617279d302` | 352 步 `CONVERGED_RTOL` | true / true | `4.767307281494141 GiB` |

screen 的较高峰值受 opt-in diagnostics 和采样生命周期影响；后续 ordinary full 的
`4.767307281494141 GiB` 才是 full 资源分母。二者不是同口径回归，不能直接比较成
性能结论。

## 对五个 G0 问题的回答

| 问题 | 回答 |
|---|---|
| 1. 是否复现 M3a MPI1 identity 和安全内存范围？ | 是。screen20 watchdog pass 且 swap=0；ordinary full 也以 watchdog pass 完成，process-tree RSS=`4.767307281494141 GiB`，低于 10/14 GiB 线。full source SHA 为 `77d39cbe461204f9e095fb6596ad5b617279d302`。 |
| 2. residual snapshot 能否按 canonical global row identity 导出？ | 能，但仅 screen20 的 opt-in observer 实际保留 iter0/20 raw snapshot，各 51192 rows，按 ascending active-row global ID；rank ownership 不参与 identity。full ordinary 没启用 observer，因此没有 iter100/late raw vector。 |
| 3. hardest/control slab 是什么？ | 在 screen20 iter20 contraction 切片中，slab14 是最大 local residual 的 primary；slab5 是 central repeated-factor slabs 的 lower-median control，slab2 是 upper-median comparator。slab14 的 ILU ablation 为负，而最大正 damage 是 slab13，因此不构造单一 universal ranking。 |
| 4. current trace ILU 与 B4 GMRES(4) 差多少？ | screen20 iter20 的 global ILU rho=`1.3887891254775173`，B4 partition-weighted rho=`0.7836817168192864`，相差约 `0.6051074086582309`。这是一次 stationary apply contraction oracle，不是外层 FGMRES 收敛结论。full ordinary 未启用 contraction diagnostics。 |
| 5. 是否具备进入 one-slab full-space identity 的前置条件？ | 仅支持进入一块 slab full-space identity 实现/验证准备（G2.2）；不支持全局 candidate、minimum contraction、full-space solve 或 production promotion。 |

## ordinary full baseline

| 指标 | 值 |
|---|---:|
| iterations / wall | `352` / `829.6772821329068 s` |
| reported relative residual | `9.97361250944977e-07` |
| condensed true residual | `9.973612508154941e-07` |
| full augmented true residual | `9.973612508154941e-07` |
| explicit full-FE true residual | `9.973612808764094e-07` |
| primary R / T / A | `0.0007628808460340567 / 0.6027016359436813 / 0.39653548321028464` |
| A_volume total | `0.39653548322357507` |
| R+T+A_volume / closure error | `1.0000000000132905 / 1.3290479827787749e-11` |
| factor rows / stored factor NNZ | `127656 / 91415952` |
| worker RSS/PSS/USS | `4687.421875 / 4636.3837890625 / 4592.12890625 MB` |
| swap | `0` |

global A/F 和 global direct factor 均未物化。full canonical active-trace/full-FE manifest
SHA 分别为 `6fd0c8db99649189f409f52851e4a43de28ea19e473de4aa0d3d31705a9d44e9` 与
`dcac07477a863ac1a56051f930cb09f32759dd1596b0e46bbb5a9e03adca7a10`；它们保留历史
M3a 的 canonical global-row identity 和 ordering。

## 12+12 channel 状态

full command 没有调用 Task035d significant-channel CLI gate，故 direct CLI 状态仍为
`not_invoked/null`。新增的窄 checker 从冻结 authority 和当前 raw 重新读取每个
`(side,m,n,polarization)`，top 映射 R、bottom 映射 T，使用
`reference_role=direct_authority_embedded_in_historical_m3a_record`，把 current 的
`power_ratio` 和 `outgoing_amplitude_at_boundary` 与同一 authority 行的
`direct_power` 和 `direct_boundary_amplitude` 比较，重新计算绝对功率差与复幅
Euclidean 差。

| 项目 | 结果 |
|---|---:|
| authority SHA | `43c749aa9f25282308c607de73a890acbabaf9af1e5f366a0c9eb5aee10f6019` |
| current raw SHA | `6238bc19b06952f5ea0a009ab59eaafc847dc50b5f0efc869584e6bb3cbc9caa` |
| unique labels / exact current matches | `12 / 12` |
| recomputed power | `12/12` |
| recomputed complex amplitude | `12/12` |
| status | `posthoc_recomputed_12_of_12` |
| report SHA | `9bd4f586eeaa21f573491c7b83277c4c1958e8c907c747a861d564c4234ec828` |

这是对当前 raw 的后验重算通过，不改写为“CLI Gate invoked”，也不改变历史 authority。

## 负结果、未运行项与证据

- screen20 solver 的 `DIVERGED_MAX_IT (-3)` 不是收敛或 official RTA；full ordinary 的
  `CONVERGED_RTOL` 与 official RTA 是另一条独立 authority。
- B2 i2500、M3A iter100/late、B4 iter20/100/200 raw vectors 均为
  `not_available/pending`；full 没有启用 snapshot observer，未用 final solution 或
  scalar history 冒充 vector。
- 没有运行第二次 PDE、B2-2500、独立 B4 campaign、G1/G2 full-space/LOR-HX 或 G3。

compact authority：[g0_authority.json](/home/shenjh/Projects/MyFEniCSx_task37_extra/benchmarks/cases/101_task37_extra_development/records/g0_authority.json)。

post-hoc report：[g0_m3a_mpi1_full_channels.json](/home/shenjh/Projects/MyFEniCSx_task37_extra/benchmarks/cases/101_task37_extra_development/records/g0_m3a_mpi1_full_channels.json)。

ignored full raw directory：`/home/shenjh/Projects/MyFEniCSx_task37_extra/benchmarks/artifacts/101_task37_extra_development/g0_m3a_mpi1_full_77d39cbe`。
