# G0 residual 与 contraction authority

本文件记录 G0 的 screen20 authority、同机 ordinary full baseline，以及在 full raw
输出上的一次 post-hoc 12+12 channel 重算。残差是把当前近似解代回离散方程后剩下的
误差负荷；本轮记录的是 condensed active-trace dual/load residual r=b-Ax，不是物理
场系数。“一次 contraction”只把同一个残差送入一次修正并计算
rho=||r-Az||/||r||，用于比较一个固定修正动作，不等于外层 FGMRES 的收敛率。

## screen20 authority

screen20 是 G0 的 opt-in 诊断运行；它只用于 identity、factor inventory、有限 residual 和资源安全检查，不代表 full solver 或 physical result 通过。

| 项目 | 本轮 authority |
|---|---|
| 运行 | 唯一 M3a、MPI1、screen20；p6/h10/S、overlap 0.125、partition interpolation |
| source | 568f1ac189f98227541722b1de66cd7804e0cc80 |
| watchdog | task037_m3a_overlap0125_partition_screen_pass；failures=[]；return code 0 |
| solver | 20 步达到 DIVERGED_MAX_IT (-3)，external_solver_not_converged |
| official RTA / postprocess | false / skipped；没有官方场输出 |
| 全局矩阵身份 | global A 和 F 均未物化；没有 global direct factor |
| 结论边界 | 仅支持进入一块 slab 的 full-space identity 准备/验证（G2.2） |

watchdog pass 是身份、因子清单、有限 residual 和资源安全 screen 的通过，不是求解器收敛或物理结果通过。该 screen 未产生 official RTA；B2-2500、独立 B4 campaign 和其他 full 候选没有在本轮重跑。

## ordinary full baseline authority

这是唯一一次同机 M3a MPI1 ordinary full baseline；运行时没有启用 G0 snapshot observer 或 contraction diagnostics，因此它测量的是冻结的普通 M3a action。solver 在 352 iterations 以 `CONVERGED_RTOL` 完成，随后产生 official postprocess 与 R/T/A。

| 项目 | full authority |
|---|---|
| source / run | `77d39cbe461204f9e095fb6596ad5b617279d302` / `g0_m3a_mpi1_full_77d39cbe` |
| watchdog | `task037_m3a_overlap0125_partition_full_pass`；return code 0；failures=[]；zero swap |
| solver | 352 iterations；`CONVERGED_RTOL`；postprocess 未跳过 |
| residual | reported `9.97361250944977e-07`；condensed true `9.973612508154941e-07`；full-augmented true `9.973612508154941e-07`；explicit full-FE true `9.973612808764094e-07` |
| official / RTA | `official_result=true`；external RTA Gate=`true`；residual limit=`1e-6` |
| rows | full FE 173802；active trace 51192；active condensed/augmented 51272 |
| global matrix identity | global A/F 未物化；global direct factor count=0 |
| wall baseline | `829.6772821329068 s` |

full primary port R/T/A 为 `0.0007628808460340567 / 0.6027016359436813 /
0.39653548321028464`；volume absorption 为
`A_volume_total=0.39653548322357507`，其中 grating/substrate 分别为
`0.33247666554710664 / 0.06405881767646841`。`R+T+A_volume=`
`1.0000000000132905`，port-volume closure error 为
`1.3290479827787749e-11`。

full factor 与 timing authority：stored factor NNZ=`91415952`，factor rows=`127656`，
16 个 local ILU、7 个 unique factor classes、9 个 exact duplicates；core setup/solve/
recovery/total=`73.39472350699361 / 610.5539820300182 / 0.08534819900523871 /
684.0969637440285 s`，stage4 assembly+solve=`800.1124806989683 s`，postprocess=
`26.84212387003936 s`。

full resource authority 为 process-tree RSS=`4.767307281494141 GiB`
(`4881.72265625 MB`)，worker RSS/PSS/USS=`4687.421875 / 4636.3837890625 /
4592.12890625 MB`，swap=`0`。后续工程分母固定为 `4.767307281494141 GiB`；其
0.75、half、stretch 参考线分别为 `3.5754804611206055 / 2.3836536407470703 /
2.0 GiB`。wall 参考线为 baseline=`829.6772821329068 s`、preferred 2x=
`1659.3545642658136 s`、maximum 4x=`3318.709128531627 s`。

screen 的 `6.259979248046875 GiB` 峰值包含 opt-in diagnostics 与采样生命周期，
ordinary full 的 `4.767307281494141 GiB` 才是后续 full resource denominator；两者
不是同口径回归，不能直接比较成性能结论。container cgroup historical peak
`13279.546875 MB` 在两次记录中都不是 formal authority。

## full canonical 与 12+12 post-hoc checker

full active-trace manifest SHA=`6fd0c8db99649189f409f52851e4a43de28ea19e473de4aa0d3d31705a9d44e9`，
full-FE manifest SHA=`dcac07477a863ac1a56051f930cb09f32759dd1596b0e46bbb5a9e03adca7a10`。
两者均为 complex128、canonical key digest 为 `sha256(canonical-key-json-v1)`，
保留与历史 M3a 相同的 canonical global-row identity 与 ordering；这里绑定的是本次
run-specific manifest hash，不把不同 run 的文件 SHA 混称为同一文件。

本次 full command 没有启用 Task035d significant-channel CLI gate，故该 CLI 状态仍为
`not_invoked/null`。新增 checker 从冻结 authority
`task37_m3a_overlap0125_partition_full_v1.json`（SHA
`43c749aa9f25282308c607de73a890acbabaf9af1e5f366a0c9eb5aee10f6019`）与当前 raw
`dtn_port_diffraction_orders_3d.json`（SHA
`6238bc19b06952f5ea0a009ab59eaafc847dc50b5f0efc869584e6bb3cbc9caa`）重新读取数值，
reference role 是 `direct_authority_embedded_in_historical_m3a_record`：每个 current 值
与同一 authority 行的 `direct_power`/`direct_boundary_amplitude` 比较，使用冻结的
power/amplitude tolerance；没有使用旧 `power_pass`/`amplitude_pass` 或旧 diff 字段。
结果为：

| post-hoc 项目 | 结果 |
|---|---:|
| unique frozen labels / matched current rows | 12 / 12 |
| recomputed power | 12/12 |
| recomputed complex amplitude | 12/12 |
| overall status | `posthoc_recomputed_12_of_12` |
| report SHA256 | `9bd4f586eeaa21f573491c7b83277c4c1958e8c907c747a861d564c4234ec828` |

这表示当前 raw 的后验重算通过，不把它改写成“CLI Gate invoked”。

## residual snapshot 身份

snapshot 载荷按 active-row global ID 升序排列；rank ownership 不属于 identity。这个结论只保证本次 canonical global-row identity，不宣称重新编号或重新分区后的 numbering invariant。两份 snapshot 都有 51192 个 active rows。

| iteration | true residual | manifest file SHA256 | canonical SHA256 | rank shard SHA256 |
|---:|---:|---|---|---|
| 0 | 1.0 | cbb62dad67b29e911e9391a802c21b7c6c7947156b0f3b7f6419f5604f2ac6b0 | f9440f315522999d87db815b9e619eaa826b5eae052e8403aef9c04bcfc1af7e | 7adea21b5b1d9106e92685f013df103f027faf7b9c21d207832e5c6802bfa93d |
| 20 | 0.04474243612765 | ed53c09adb33297099839922177b9267875ee65e2adc2fbd8bfd0c96de611f5b | cb9fa32dd8c3c26db69a9d5a62577d66225eefb5e39a8bfdf6efb8c76e614ee6 | 4b22bde2440127eec23cce791b2a67db3736c8cb5a18e273f19aff0a5ba62e98 |

core true-residual samples are iter0=1.0、iter10=0.14446444295860594、iter20=0.04474243612765。iter10 只在 core scalar history 中采样，本轮 snapshot callback 明确只写 {0,20}；不能把 iter10 scalar 当作 raw vector。

## screen20 资源、因子与正式 audit

| 指标 | 值与口径 |
|---|---|
| watchdog warning / terminate | 10 / 14 GiB |
| process-tree RSS authority peak | 6.259979248046875 GiB（6410.21875 MB） |
| worker RSS / PSS / USS | 5112.47265625 / 5061.1181640625 / 5016.58984375 MB |
| process-tree swap / worker smaps swap | 0 / 0 MB |
| container cgroup historical peak | 13279.546875 MB，不是本次 formal memory authority |
| 历史 4.600486755 GiB | 仅是不同采样/路径的背景，不能称同口径回归或 full baseline |
| stored factor NNZ | 91,415,952；factor rows 127,656 |
| global direct factor / global A / global F | 0 / false / false |

diagnostic 前冻结的正式 audit 为 operator apply 140、coarse apply 20、smoother apply 120、stored factor NNZ 91,415,952；diagnostic wall time 为 34.65908507502172 s，没有把 diagnostic action 计入正式 audit。

## contraction authority

global rho 使用 exact condensed active-trace operator A_t。局部 rho 使用 shifted local Schur action，且不加 partition weight；只有 global B4 使用 partition weights。以下数值都是同一个 residual 上的一次修正动作：

| residual iteration | current trace ILU | B4 partition-weighted | fixed two-step | full M3A two-level |
|---:|---:|---:|---:|---:|
| 0 | 2.445965881188012 | 0.9556993251952722 | 1.3728527291782708 | 1.1568847294563473 |
| 20 | 1.3887891254775173 | 0.7836817168192864 | 1.0634552099589953 | 1.175270315066409 |

iter20 的 primary/control 选择只用于可复现审阅切片，不是代码中的 universal selector：

| slab | 选择依据 | local residual norm | local ILU rho | local B4 rho | ILU ablation damage |
|---:|---|---:|---:|---:|---:|
| 14 primary | 最大 iter20 local residual | 0.4272314396194324 | 1.2604899530937426 | 0.7558186834062683 | -0.14960520299020064 |
| 5 control | central repeated-factor slabs 中的 lower-median residual | 0.16307530842059187 | 1.247711710628995 | 0.8512896925857695 | — |
| 2 comparator | upper-median comparator | 0.16414059813172402 | 1.1086268146222058 | 0.8675420337186592 | — |

去掉 slab14 的当前 ILU 修正后，global rho 反而改善 0.14960520299020064，所以它不是“最大 damage” slab。最大正 ablation damage 是 slab13，值为 +0.038332237714445494。这两个指标冲突，不能伪造一个单一 hardest ranking。

iter0 只有 slab14/15 有非零 local residual；其余 14 个 slab 的 local ILU/B4 rho 数学上未定义，compact authority 使用 null/not_applicable。原始 PDE artifact 产生于本次语义修正之前，曾把这 28 个值写成 0.0；该历史写法只保留在 provenance note，不能解释为完美收缩。

## pending 与下一步边界

| 项目 | 状态 |
|---|---|
| B2 i2500 raw vector | not_available_without_prohibitive_rerun |
| M3A iter100 / late raw vector | not_available；full run 未启用 snapshot observer |
| B4 iter20 / 100 / 200 raw vector | not_available |

没有使用 scalar residual 伪造任何缺失 vector。当前只具备一块 slab full-space identity 的实现/验证准备；尚未具备全局 candidate、minimum contraction、full solve 或 production promotion 的依据。

## evidence index

compact authority：[g0_authority.json](/home/shenjh/Projects/MyFEniCSx_task37_extra/benchmarks/cases/101_task37_extra_development/records/g0_authority.json)。

full 12+12 post-hoc report：[g0_m3a_mpi1_full_channels.json](/home/shenjh/Projects/MyFEniCSx_task37_extra/benchmarks/cases/101_task37_extra_development/records/g0_m3a_mpi1_full_channels.json)。

ignored raw evidence 位于 `/home/shenjh/Projects/MyFEniCSx_task37_extra/benchmarks/artifacts/101_task37_extra_development/`，并由 compact record 绑定 watchdog、run summary、core audit、memory timeline、progress、stdout、canonical manifests 和 channel report 的 SHA256。screen 没有 official 场输出；ordinary full 的 official RTA 只属于 full baseline。
