# Task39 Review V3 response v4：h5 fixed-case qualification

## 1. 结论与分类

本轮只收口已经完成的 5 nm、1° grazing、phi=0、S、p6/h5、M480、MPI8 formal
case。推荐的派生分类是：

TASK039_V3_CASE_QUALIFIED_EXPLICIT_OPT_IN_HYBRID_ITERATIVE_EXACT_SIDE_PASS

这里的“qualified”只表示这个固定输入和显式 opt-in 路径同时通过数值、物理、生命周期
与 process-tree RSS Gate。它不是普适 production PC，也不是
TASK039_V3_1DEG_HYBRID_ITERATIVE_POSITIVE，更不是 P4 已经对所有模型完成资格化。

worker checkpoint 保持原样，仍是 attempted 且 final_qualification_status 为
pending_parent_resource_gate。compact record 没有修改 raw，而是独立引用 worker
checkpoint 和 parent run_summary，再合并 worker numerical/inventory/cleanup/recovery
证据与 parent resource authority 得出最终分类。

## 2. 2D reference 与 3D discretization

既有 2D 结果只承担角度、极化、材料和端口归一化的参考作用；它不是本次 3D h5
observable authority。h4 只保留已经完成的 Full3D 补充参考，本阶段没有继续 h3、h4
或 2D 高阶扩展。

本轮 3D case 固定 p6/h5、M480、MPI8，并绑定 input、resolved config、physical model
和 producer source SHA。external key set 为 600 个 exact；dynamic external modes 为
bottom 296、top 304。compact record 保存这些身份及 raw artifact SHA256，原始 timeline
仍在 ignored run root。

## 3. Hybrid integrated physics

全局求解对象是 exact monolithic matrix-free Hybrid operator。right FGMRES 使用
restart 90、hard max_it 4000、zero initial guess；只在两个 local side 上使用 exact
sparse direct factor，并用动态 DtN Woodbury处理端口外部模态。它不是 global Hybrid
direct factorization。

outer 只用了 1 次迭代，reason 为 2。reported/global/bottom/top/modal residual 为：

| reported | global | bottom | top | modal |
| ---: | ---: | ---: | ---: | ---: |
| 1.889629917504017e-10 | 1.8896319646868032e-10 | 1.52870527709288e-11 | 1.7545984733553013e-10 | 3.374854317881879e-11 |

五项均不超过 5e-9；matrix repeat 为 4.4034688168209445e-12，不超过 1e-10，
LU repeat 为 0，不超过 1e-13；projection 为 3.374854345267127e-11。bottom/top
exact traction relative residual 为 1.52870527709288e-11 /
1.7545984733553013e-10，均不超过 1e-8。

recovery 和 primary Hybrid-direct integrated checker 均通过。R/T/A/A_volume/closure
为：

| R | T | A balance | A volume | closure |
| ---: | ---: | ---: | ---: | ---: |
| 0.7397405130788051 | 0.00021574916967427902 | 0.2600437377515207 | 0.2600443738595666 | 6.361080457928381e-7 |

frozen recovery contract 要求 bottom/top external_q.pass，但 raw checkpoint 没有单独
持久化 external_q scalar，只保存 recovery_pass=true。因此 external q 在 compact evidence
中是 actual=not_separately_persisted、status=pass_via_recovery_contract；这不是一个
被 authority checker 单独提供的数值。selected E/H 的 relative L2 为
1.9876971434199388e-11 / 1.9808943154711087e-11，absolute L2 为
1.1260056625672672e-10 / 2.986453081219064e-13。

## 4. Strict channel diagnostic

Full3D secondary checker 没有成为本轮 primary Gate。strict per-channel complex amplitude
比较已实测但未通过：primary_channel_pass=false、weak_channel_pass=false、
full_channel_pass=false；power_weighted_pass=true，修复仍 deferred/pending。它是
nonblocking diagnostic，不否决已通过的 Hybrid-direct integrated authority，也不能被
写成隐藏的 strict channel pass。600 external keys 的集合身份和 power-weighted primary
checker 是本轮可裁决的 authority。

## 5. Block-LDU exact-side oracle

“exact-side”是指只对 bottom/top 两个局部端口矩阵各做一次稀疏直接分解，再把这两个
局部解嵌入 block-LDU 的右侧动作。动态 DtN Woodbury处理外部模态；全局 Hybrid operator
仍以 matrix-free 方式施加。局部逆足够准确，所以第一次 FGMRES 更新已经达到五项
residual Gate；这说明局部 inverse 的数值强度，不等于一套跨 case 的 production solver。

outer=1 不等于总成本只有一次局部解：raw side diagnostics 记录 bottom/top
action_apply_count 为 1922/1922，local_direct_solve_count 为 2218/2226（包含
Woodbury/modal Schur 构造等局部工作），formal elapsed 为 4888.064315 s。这里是用较多
setup 和局部直接解换取较低 outer iteration 与较低峰值内存，时间代价不可忽略，不能把
1 iteration 宣传成高速。

清理前 bottom/top direct factors 为 1/1，global factor 为 0；local preonly KSP 为 2，
nested iterative KSP 为 0。solution snapshot 在 cleanup 前交给 recovery，之后 factors、
explicit components、W/K/LU/modal Schur 临时量按生命周期合同释放；最终 ledger 显示
bottom/top/global factor 为 0/0/0。

modal Schur 需要保留证据边界：checkpoint 的 inventory 是 result.destroy 前快照，
所以其中 modal_schur.destroyed=false 和 action_modal_schur_released=false 不是最终
仍存活的断言。代码路径在 finally 中先由 result.destroy 调用
release_deferred_action_modal_schur，再销毁 context；最终 ledger 和 cleanup 后 RSS
下降提供释放佐证。raw checkpoint 没有单独的 post-cleanup modal 字段，因此本 response
不补写不存在的字段，也不把它升级为数值 blocker。

## 6. DQ1 fixed-case qualification

本次是 explicit opt-in 的 case qualification，scope 是
task039_v3_p6h5_m480_1deg_s。ordinary defaults unchanged，general_production=false。
它的 process-tree RSS peak 为 53497696256 bytes =
51019.37890625 MiB = 49.8236122131 GiB，swap=0；资源线是 69651.3 MiB，余量为
18631.92109375 MiB。

相对 1° Hybrid direct 87064.125 MiB，节省 36044.74609375 MiB / 41.4002278%；
相对 Full3D direct 96151.16796875 MiB，节省 45131.7890625 MiB / 46.9383680%。
峰值 UTC 为 2026-08-16T23:23:40.886481+00:00，位于
post_coupling_heap_cleanup 前的 setup/internal-coupling tail；邻近 process-tree
samples 先升至 53496946688 bytes，随后立即降至 39370313728 bytes，故不是 watchdog
退出假峰。

bottom interface cleanup、post-coupling cleanup、explicit-components cleanup 的
before/after/released MiB 分别为：

| boundary | before | after | released |
| --- | ---: | ---: | ---: |
| bottom interface | 11490.2734375 | 1498.44921875 | 10030.1953125 |
| post coupling | 11393.8515625 | 1434.22265625 | 10087.90625 |
| explicit components | 5410.84375 | 1449.83984375 | 4159.3046875 |

正式 worker exit 为 0，elapsed 为 4888.064315 s。PSS/USS 在本 compact evidence 中
not_measured，未用 RSS 代替它们。

## 7. Production PC qualification boundary

历史 B、C、C1、D research oracle 和 E numerical negative 均保留。当前 DQ1 只对固定
case 的 explicit route 负责，不改变 ordinary ILU0/two-pass，不声明任意 mesh、M、材料、
角度或 MPI 的复用性，也不把它标成 Review V3 production PC P4。

旧 10° ILU0 Hybrid iterative 记录的峰值是 83155.31640625 MiB，匹配的 10° Hybrid
direct baseline 是 86744.54296875 MiB，节省 4.1376972771%；它与本次 1° case 不做
跨物理比较。1° Hybrid direct baseline 为 87064.125 MiB，本次 DQ1 节省 41.4002278%。

## 8. 证据索引与未运行项

主 compact record 为
[task039_v3_h5_exact_side_case_qualification_v1.json](../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v3_h5_exact_side_case_qualification_v1.json)。
raw worker checkpoint、parent run_summary、process_tree_samples、memory_stages、
raw markers 和 object ledger 仍保留在 ignored run root。

本 turn 只完成 JSON/document/diff 轻量收口；没有修改 Python、输入、测试或 schema，
没有运行新的 PDE、MPI heavy 或 full pytest。h3/h4 新运行、Candidate E 后续扫描、
全局 direct factor 和普适 production 扩展均未运行。
