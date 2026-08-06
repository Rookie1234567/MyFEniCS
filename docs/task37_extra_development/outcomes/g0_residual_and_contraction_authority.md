# G0 residual 与 contraction authority

## 结论摘要

本文件记录唯一一次 Case101 运行和随后对局部 contraction 语义的轻量修正。这里的“残差”是把当前近似解代回离散方程后剩下的误差负荷；本轮记录的是 condensed active-trace dual/load residual r=b-Ax，不是物理场系数。这里的“一次 contraction”只把同一个残差送入一次修正并计算 rho=||r-Az||/||r||，用于比较一个固定修正动作，不等于外层 FGMRES 的收敛率。

| 项目 | 本轮 authority |
|---|---|
| 运行 | 唯一 M3a、MPI1、screen20；p6/h10/S、overlap 0.125、partition interpolation |
| source | 568f1ac189f98227541722b1de66cd7804e0cc80 |
| watchdog | task037_m3a_overlap0125_partition_screen_pass；failures=[]；return code 0 |
| solver | 20 步达到 DIVERGED_MAX_IT (-3)，external_solver_not_converged |
| official RTA / postprocess | false / skipped；没有官方场输出 |
| 全局矩阵身份 | global A 和 F 均未物化；没有 global direct factor |
| 结论边界 | 仅支持进入一块 slab 的 full-space identity 准备/验证（G2.2） |

watchdog pass 是身份、因子清单、有限 residual 和资源安全 screen 的通过，不是求解器收敛或物理结果通过。历史 B2/full 结果没有在本轮重跑。

## residual snapshot 身份

snapshot 载荷按 active-row global ID 升序排列；rank ownership 不属于 identity。这个结论只保证本次 canonical global-row identity，不宣称重新编号或重新分区后的 numbering invariant。两份 snapshot 都有 51192 个 active rows。

| iteration | true residual | manifest file SHA256 | canonical SHA256 | rank shard SHA256 |
|---:|---:|---|---|---|
| 0 | 1.0 | cbb62dad67b29e911e9391a802c21b7c6c7947156b0f3b7f6419f5604f2ac6b0 | f9440f315522999d87db815b9e619eaa826b5eae052e8403aef9c04bcfc1af7e | 7adea21b5b1d9106e92685f013df103f027faf7b9c21d207832e5c6802bfa93d |
| 20 | 0.04474243612765 | ed53c09adb33297099839922177b9267875ee65e2adc2fbd8bfd0c96de611f5b | cb9fa32dd8c3c26db69a9d5a62577d66225eefb5e39a8bfdf6efb8c76e614ee6 | 4b22bde2440127eec23cce791b2a67db3736c8cb5a18e273f19aff0a5ba62e98 |

core true-residual samples are iter0=1.0、iter10=0.14446444295860594、iter20=0.04474243612765。iter10 只在 core scalar history 中采样，本轮 snapshot callback 明确只写 {0,20}；不能把 iter10 scalar 当作 raw vector。

## 资源、因子与正式 audit

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
| M3A iter100 / late raw vector | not_available |
| B4 iter20 / 100 / 200 raw vector | not_available |

没有使用 scalar residual 伪造任何缺失 vector。当前只具备一块 slab full-space identity 的实现/验证准备；尚未具备全局 candidate、minimum contraction、full solve 或 production promotion 的依据。

## evidence index

compact record：benchmarks/cases/101_task37_extra_development/records/g0_authority.json。

ignored raw evidence 位于 benchmarks/artifacts/101_task37_extra_development/，并由 compact record 绑定 watchdog、run summary、core audit、memory timeline、progress、stdout 和 residual history 的 SHA256。官方场输出缺失由 NO_OFFICIAL_FIELD_OUTPUT.txt 记录；没有生成 official RTA。
