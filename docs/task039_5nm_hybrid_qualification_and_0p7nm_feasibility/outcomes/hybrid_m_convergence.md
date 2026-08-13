# Task39 T5：Hybrid direct M 收敛与停止边界

## 结论

本页记录 5 nm、p6/h10、S 偏振、grazing=10°（等价 theta=80°）、MPI8 的四个
Hybrid direct 候选。`M` 是每个传播方向保留的内部 QEP 模态数；它不是外部
DtN 通道数，四路都绑定同一份 604 个唯一动态外部 key。

`M_robust_h10=not_established`，最终分类为
`5NM_HYBRID_MODEL_NOT_ESTABLISHED_BY_M960_AT_P6H10`。本阶段不是 production
qualification，也不允许把 M480 称为 Full3D-validated。完整 compact evidence
见 [T5 record](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_t5_hybrid_direct_m_convergence_v1.json)。

静态凝聚（static condensation）是在组装阶段先消去单元内部自由度，只保留界面未知量；
它缩小全局系统，但仍需恢复体内场。直接法（direct method）通过稀疏因子分解一次性
求解压缩线性系统。canonical export 把 active-trace/full-FE 解向量按固定角色写成
manifest 与 shard，供独立比较，不是新的物理量。RSS 是进程驻留内存，PSS 按共享页
分摊，USS 是进程树独占页；三者是独立峰值，不能拼成同一时刻的内存向量。

## 四个正式候选

| M | formal raw root（repo-relative） | own Gate | R / T / A_volume / closure | 判定 |
| ---: | --- | --- | --- | --- |
| 120 | `results/task039_5nm_hybrid_direct_m120/task039_5nm_hybrid_direct_p6h10_m120_mpi8__hybrid_direct__mpi8__M120/20260813T005834.536219Z` | fail：sampled interface E bottom/top=0.0072988274/0.1268666971，限值=0.005 | 0.9110898819 / 0.0002093911 / 0.0887101777 / 9.4507501531e-06 | 不进入相邻资格比较 |
| 240 | `results/task039_5nm_hybrid_direct_m240/task039_5nm_hybrid_direct_p6h10_m240_mpi8__hybrid_direct__mpi8__M240/20260813T011125.988474Z` | fail：top E=0.0066259299>0.005；bottom=0.0016408964 | 0.9095051960 / 0.0008680630 / 0.0896271623 / 4.2122312216e-07 | 改善但未形成 Gate |
| 480 | `results/task039_5nm_hybrid_direct_m480/task039_5nm_hybrid_direct_p6h10_m480_mpi8__hybrid_direct__mpi8__M480/20260813T033657.601004Z` | pass：residual/traction/projection/closure；proxy 仅诊断 | 0.9094973680 / 0.0008705857 / 0.0896331911 / 1.1447940786e-06 | Full3D H diagnostic fail |
| 960 | `results/task039_5nm_hybrid_direct_m960/task039_5nm_hybrid_direct_p6h10_m960_mpi8__hybrid_direct__mpi8__M960/20260813T042015.744006Z` | fail before solution：outer=3，carrier=4，rank=6 | R/T/A/场/canonical=`not_available` | 上限仍未建立 |

四路 source/input/resolved/physical SHA 与 raw 文件 SHA，以及前三路的 selected
payload SHA，均在 record 中逐 M 绑定。M120/M240/M480 payload shape 均为
`[z,y,x,component]=[5,20,40,3]`，z=`[10,30,60,90,110]`；M960 在形成 solution
前失败，selected E/H 为 `not_run`。

## QEP 与 own Gate 关键数值

| M | positive candidate/selected/groups | negative candidate/selected/groups | true residual | exact traction bottom/top | projection | sampled E bottom/top |
| ---: | --- | --- | ---: | --- | ---: | --- |
| 120 | 240/120/74 | 240/120/74 | 1.8233748636e-11 | 2.9812088974e-12 / 1.8162678335e-11 | 1.9011818251e-11 | 0.0072988274 / 0.1268666971 |
| 240 | 480/240/146 | 480/240/146 | 1.0675101578e-11 | 1.4259693760e-12 / 1.0626548353e-11 | 5.6948651135e-12 | 0.0016408964 / 0.0066259299 |
| 480 | 960/480/298 | 960/480/298 | 8.9806001686e-12 | 4.2171865486e-12 / 8.9332530141e-12 | 9.1142696234e-12 | 4.5676199e-06 / 1.1155462e-05 |
| 960 | 1960/960/577 reported | 1961/960/577 not side-split | not formed | not_run | not_run | not_run |

120、240、480 的动态 inventory 均为 604，bottom/top=300/304，S/P=150/150 与
152/152，propagating=604，nonpropagating=0，Rayleigh warning=0。M960 只到达
canonical trace authority，不能把“QEP 已交付”写成已生成 diffraction output。

## selected E/H measured payload

下表是各 Hybrid payload 在五个 z 平面的最大绝对值，不能替代 Full3D 相对 L2 比较。

| M | quantity | z=10 | z=30 | z=60 | z=90 | z=110 |
| ---: | --- | ---: | ---: | ---: | ---: | ---: |
| 120 | max abs(E) | 0.0150352816 | 0.0145937659 | 0.0209072344 | 0.0746676610 | 0.4236918297 |
| 120 | max abs(H) | 3.7717768e-05 | 3.8525857e-05 | 4.9807219e-05 | 2.2236582e-04 | 1.1833337e-03 |
| 240 | max abs(E) | 0.0304265840 | 0.0295401782 | 0.0364134913 | 0.0887905078 | 0.4169640813 |
| 240 | max abs(H) | 6.9447811e-05 | 7.0445904e-05 | 8.4850576e-05 | 2.4640349e-04 | 1.2222871e-03 |
| 480 | max abs(E) | 0.0307006827 | 0.0293653515 | 0.0352348589 | 0.0888029206 | 0.4179379259 |
| 480 | max abs(H) | 6.8649373e-05 | 7.0941549e-05 | 8.4422582e-05 | 2.4597586e-04 | 1.2220194e-03 |
| 960 | max abs(E/H) | not_run | not_run | not_run | not_run | not_run |

## M480 对 T3 Full3D direct 的 diagnostic

checker 输出为 `/tmp/task039_t5_m480_identity_formal_tight_qep.json`，SHA256 为
`4ac919e01c7e965719807d0a54e6e8a06117f2d0a2d8ca711944ae6f31b68fda`。其角色固定为
`diagnostic_against_direct_authority`，`production_validation_allowed=false`，
`blocked_by=T4_5NM_FULL3D_ITERATIVE_NUMERICAL_NEGATIVE_AT_P6H10`。

| 项目 | 实测 | Gate |
| --- | ---: | --- |
| physical model / coordinates / mode keys | exact / exact / exact | pass |
| significant orders | 33 | max power rel=3.0499573683e-08；amplitude rel=2.2165649830e-08，pass |
| selected E overall relative L2 | 5.4759121552e-06 | pass |
| selected H, z=10 | 0.06166882988225369 | fail，interface limit=0.01 |
| selected H, z=30 | 0.06046024718794985 | report only |
| selected H, z=60 | 0.05995873633961302 | fail，middle limit=0.005 |
| selected H, z=90 | 0.026506778819889037 | report only |
| selected H, z=110 | 0.004498565559704994 | report only |

R/T/A/A_volume、closure、604 key set 与 significant-order comparison 均通过该
diagnostic 的相应限值；H 的两项失败使整体分类为 `HYBRID_DIRECT_DIAGNOSTIC_FAIL`。
由于 T4 Full3D iterative 是正式数值负结果，即使 diagnostic 全通过也不能生成
Full3D-validated 或 production-qualified 结论。

## M960 停止与 T6 边界

M960 的 positive/negative QEP 分别交付 960 个模态（candidate=1960/1961，raw
reported group count=577），随后在 canonicalized negative trace authority 处
失败：`raw_relative_error=1.678e-11 > 1e-12`，`representation_relative_error=1.008e-14`。
它没有进入 direct solve、recovery、official R/T/A 或 checker；这是冻结数值 authority
的 negative result，不改写成实现错误，也不放宽 Gate。

§8 要求先建立 `M=M_robust_h10`；§13.4 虽允许一次 M960 iterative-vs-direct
diagnostic，但必须有合法的 M960 direct observable/reference。本次 reference 不存在，
因此 T6 必须 `not_run`，不能拿 M480 冒充 M960。

## 资源与时间边界

| M | outer wall (s) | process-tree RSS (MiB) | PSS (MiB) | USS (MiB) | swap (MiB) | smaps attempted/complete |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 120 | 432.931447 | 8929.0625 | 7154.639648 | 6870.980469 | 0 | 1443/1439 |
| 240 | 815.862600 | 10999.851563 | 9222.426758 | 8938.285156 | 0 | 2642/2640 |
| 480 | 1468.884482 | 22798.082031 | 21039.913086 | 20758.953125 | 0 | 4368/4365 |
| 960 | 4812.858962 | 22536.339844 | 21407.276367 | 21222.859375 | 0 | 12594/12592 |

四次资源均为 measured、swap=0，未触发 warning/termination；RSS/PSS/USS 是独立
per-metric simultaneous process-tree peaks，不能与 solver-rank 历史上界混称。M960
的较大资源占用不构成数值通过。

## 证据边界

早期 M120 work-directory configuration failure，以及 M480 的 near-degenerate
partition/canonical precision 失败 raw 均保留在 ignored results；本页与 record 不覆盖
它们。没有新增 M、没有放宽 QEP/traction/field Gate，也没有启动 T6/T9。
