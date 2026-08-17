# V3 最终 h5 Hybrid iterative fixed-case 结果

## 一句话结论

这次运行把一个明确的 h5 case 跑通了：全局仍是 matrix-free Hybrid 矩阵，外层用右
FGMRES；bottom 和 top 各有一个局部 exact-side 稀疏直接因子，并在局部动作中补上动态
DtN Woodbury 耦合。它不是把整个 Hybrid 矩阵做全局直接分解，也不是把这个 case 的
配置提升为所有模型的默认 production PC。

worker checkpoint 原样保留了 pending_parent_resource_gate。本页的最终分类是从 worker
数值、生命周期、recovery/physics 与 parent process-tree RSS/swap 证据独立合并得到的：

TASK039_V3_CASE_QUALIFIED_EXPLICIT_OPT_IN_HYBRID_ITERATIVE_EXACT_SIDE_PASS

其中 general_production=false，ordinary defaults unchanged。这个分类只适用于
5 nm、1°、phi=0、S、p6/h5、M480、MPI8 的显式 opt-in case。

## 方法和为什么只需 1 次外层迭代

bottom/top 的局部 exact-side 因子直接解决各自端口方程；动态 DtN Woodbury 处理外部
模态耦合；外层面对的是完整的 exact monolithic matrix-free Hybrid operator。由于这两个
局部逆在本 case 上已经非常接近真实 side inverse，右 FGMRES 的第一次更新就把全局、
bottom、top 和 modal 残差同时压到限值以内。这是“局部预条件动作很强”的实测解释，
不是“全局矩阵被直接分解”的意思。

outer=1 也不表示总成本只有一次局部解：raw side diagnostics 记录 bottom/top
action_apply_count 为 1922/1922，local_direct_solve_count 为 2218/2226（其中包含
Woodbury/modal Schur 构造等局部工作），formal elapsed 为 4888.064315 s。准确的
解释是用较多 setup 和局部直接解换取较低 outer iteration 与较低峰值内存，时间代价
不可忽略；1 iteration 不能宣传成高速。

| 量 | 实测值 | Gate |
| --- | ---: | --- |
| outer iterations / reason | 1 / 2 | reason > 0，<=4000 |
| reported residual | 1.889629917504017e-10 | <=5e-9 |
| global residual | 1.8896319646868032e-10 | <=5e-9 |
| bottom / top residual | 1.52870527709288e-11 / 1.7545984733553013e-10 | <=5e-9 |
| modal residual | 3.374854317881879e-11 | <=5e-9 |
| matrix repeat / LU repeat | 4.4034688168209445e-12 / 0 | <=1e-10 / <=1e-13 |
| projection | 3.374854345267127e-11 | <=1e-8 |
| exact traction, bottom/top | 1.52870527709288e-11 / 1.7545984733553013e-10 | <=1e-8 |

## 物理与通道边界

recovery 完成，Hybrid-direct integrated checker 是本轮 primary authority 并通过。实测
物理量为：

| R | T | A balance | A volume | closure |
| ---: | ---: | ---: | ---: | ---: |
| 0.7397405130788051 | 0.00021574916967427902 | 0.2600437377515207 | 0.2600443738595666 | 6.361080457928381e-7 |

### Hybrid iterative 与同物理 Hybrid direct totals

| observable | iterative | Hybrid direct | absolute delta | integrated Gate |
| --- | ---: | ---: | ---: | --- |
| R_total | 0.7397405130788051 | 0.7397405130770115 | 1.7935652962819404e-12 | pass |
| T_total | 0.00021574916967427902 | 0.00021574916967525152 | 9.725022436651853e-16 | pass |
| A_balance | 0.2600437377515207 | 0.26004373775331324 | 1.7925660955597778e-12 | pass |
| A_volume | 0.2600443738595666 | 0.2600443738591794 | 3.8719027983802334e-13 | pass |

外部模式 key set 为 600 个且 exact；bottom/top 动态外部模式分别是 296/304。selected
E/H 的 relative L2 为 1.9876971434199388e-11 / 1.9808943154711087e-11，
absolute L2 为 1.1260056625672672e-10 / 2.986453081219064e-13，均通过既有 Gate。
external q 的 frozen recovery contract 要求 bottom/top external_q.pass；本 raw checkpoint
只持久化 recovery_pass=true，没有单独的 external_q scalar。因此 compact evidence 将
其记录为 actual=not_separately_persisted、status=pass_via_recovery_contract，不能把
它解释成一个已保存的数值或 authority checker scalar。

Full3D secondary checker 不参与本轮 primary Gate。其 strict per-channel complex amplitude
比较已实测但未通过：primary_channel_pass=false、weak_channel_pass=false、
full_channel_pass=false，而 power_weighted_pass=true；修复仍 deferred/pending。它是
nonblocking diagnostic，不否决已经通过的 Hybrid-direct integrated authority，也不能被
隐藏。h4 只保留此前的 Full3D 补充参考，本阶段没有继续 h3/h4。

## 与既有正式结果的比较

| 路径 | 峰值 process-tree RSS | elapsed | 数值/物理状态 | matched baseline / saving |
| --- | ---: | ---: | --- | ---: |
| Full3D direct p6/h5 | 96151.16796875 MiB | not_available | direct reference；h4 为补充边界 | not_applicable |
| Hybrid direct p6/h5 M480 | 87064.125 MiB | not_available | 1° direct baseline | not_applicable |
| 旧 ILU0 Hybrid iterative（10°历史 case） | 83155.31640625 MiB | 17187.881117 s | 6000 / DIVERGED_MAX_IT，数值负结果 | 10° Hybrid direct 86744.54296875 MiB / 4.1376972771%；不与本次1°跨物理比较 |
| 本次 exact-side explicit opt-in（1°） | 51019.37890625 MiB = 49.8236122131 GiB | 4888.064315 s | 1 iteration；numerical/physics/resource pass | 1° Hybrid direct 87064.125 MiB / 41.4002278% |

本次峰值相对 Hybrid direct 节省 36044.74609375 MiB / 41.4002278%，相对 Full3D
direct 节省 45131.7890625 MiB / 46.9383680%。正式 RSS 目标为 69651.3 MiB，本次
余量 18631.92109375 MiB；swap 为 0。

## 生命周期与证据边界

bottom interface cleanup 的 before/after/released 为
11490.2734375 / 1498.44921875 / 10030.1953125 MiB；post-coupling cleanup 为
11393.8515625 / 1434.22265625 / 10087.90625 MiB。candidate-D explicit components
cleanup 为 5410.84375 / 1449.83984375 / 4159.3046875 MiB。三处均记录了真实
collective completion。

正式路径没有加载 direct reference payload，也没有运行 identity reference materialization。
清理前 inventory 显示 bottom/top direct factor 1/1、global factor 0、local preonly
KSP 2、nested iterative KSP 0；恢复前释放 components 和 factors 后，最终 ledger
显示 bottom/top/global 0/0/0。

modal Schur 的 raw checkpoint 是 result.destroy 前快照，因此其中
modal_schur.destroyed=false 和 action_modal_schur_released=false 只表示快照时序，
不是最终仍存活的证据。代码路径先由 result.destroy() 调用
release_deferred_action_modal_schur()，再销毁 context；最终 ledger 和 cleanup 后 RSS
下降也支持它已释放。raw checkpoint 没有独立的 post-cleanup modal 字段，所以这里明确
保留证据边界，不把不存在的字段补写成实测值。

## 资格边界

这是一个用户授权的、case-specific explicit opt-in：global matrix-free Hybrid FGMRES
配合两个 local exact-side direct factors。它证明了本 case 的收敛、物理和资源组合，
但没有证明该局部因子在任意网格、M、材料、角度或 MPI 下可复用。它也没有把 ordinary
ILU0/two-pass defaults 改掉。因此不能把本结果写成普适 production PC qualification、
P4，或 TASK039_V3_1DEG_HYBRID_ITERATIVE_POSITIVE。

compact record：
[task039_v3_h5_exact_side_case_qualification_v1.json](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v3_h5_exact_side_case_qualification_v1.json)

原始 worker checkpoint、parent run summary 和 process-tree/marker/ledger 文件均保留在
ignored run root；compact record 只保存 hash-bound、可复核的派生证据。
