# boundary-plane p2 组件资格冻结

**状态：PASS_COMPONENT_ONLY。** 本次完成同 Gauss、full MPC、全部 532 模式的系数、DtN action、实际 recovery、RHS 坐标及输出低层组件资格。没有 PDE solve，没有官方 R/T/A；p4/p6/目标及默认生产资格不由本组件授予。

| 身份/范围 | 已测量或冻结值 | 证据 |
|---|---|---|
| canonical source | `a0546264ae1bcc51e2aeedcac33585f4ffc04025`，run 前后 clean | `source_receipt_a054626.json` |
| 配置 | 80 cells，p2，λ0.7nm，phi5，固定 manual m±9/n±3，532 个有序身份；随机种子4053202，五个 full-MPC 独立 FE 状态含 interiors | actual test + `oracle_record.json` |
| 数值表示 | 显式 `dtn_phase_gauge="boundary_plane"`；default `global_z` 不变 | `build_same_mesh_physical_action` |
| quadrature | degree19，100个quad facet Gauss点；4 primary/8参数化literal oracle编译表、nodes/weights和实际loaded C绑定 | raw oracle compiled identities |
| generator / assembly / context | physical `4ace13f4…50c951`；assembly `6f3985de…7a820`；context `2ae0fe4a…630714` | 完整hash在receipt |

## 测量与算子区分

| 指标 | measured | 门/口径 |
|---|---:|---|
| 原空 C / D 被恢复 | 172 / 174 | 新 C / D 零支持均0；每个模式保存 raw coefficient 与两阶段 cutoff ledger |
| 最大 raw C / D 等价差 | 4.1297e−14 / 4.1300e−14 | 未截断 global/s 与直接 centered forms；≤1e−10 |
| 最大 raw H / per-mode FE action 差 | 1.6733e−16 / 4.4452e−14 | ≤1e−10 |
| 新stored相对raw的最大完整DOF rank-one loss上界 | 1.3678e−13 | 每模式系数范数证书；≤1e−10 |
| 五状态累计 raw / centered action 差 | 1.1873e−15 | sampled action；不称累计operator norm证书 |
| 五状态新stored / raw action差 | 3.2698e−15 | sampled action |
| 五状态旧clipped / 新stored action变化 | 0.0308226 | 刻意承认stored operator改变；没有旧clipped数值相同声明 |
| 实际 production recovery | 全532×5，old stored/new stored/raw oracle均通过 | 全vector与逐entry operation-scale gate≤1e−10；raw数值未额外归档 |
| RHS / output components | 完整physical RHS、incident、任意非零port RHS回环及五状态输出检查通过 | arbitrary fields仅组件一致性；官方结果False |

centered UFL phase直接求值在原两阶段 sparsification 之前；两个 floor 仍为 `max(1e-30,1e-13*max)`。预cutoff系数通过可表示的phase坐标等价验证。对已被clip的旧 carrier 做可逆缩放不能恢复zeros；本次是在更稳定坐标重建同积分公式，得到**不同的stored numerical operator**。原H使用 `area*electric_tangential_norm_sq`，不能误认凝聚Hhat同样对角。

## 输出负门及窄修正

| attempt | source | 分类/证据 |
|---|---|---|
| 1 | `8960b71e…a889` | FAILED_API，缓存Form.code为(None,None)；保留失败，修复实际loaded module同名C文件定位 |
| 2 | `aad8f46a…ed63` | FAILED_OUTPUT_COMPONENT_GATE；系数/action先前断言通过但不能称完整pass |
| 3 | `74df81b8…4848` | 同输出failure；`PARTIAL_COMPONENT_EVIDENCE`与完整controlled-stop packet在断言前保存 |
| 4 | `a0546264…4025` | PASS_COMPONENT_ONLY；完整test1 passed/6.96s |

failure模式15 top(−8,−3,p)在数学reactive零功率中产生plane9.3652e−17，而legacy signed负roundoff被clip为0。原 `unit_power==0` 不是证明。经独立source review的窄修正只在严格lossless、real tangential k、outgoing pure-imaginary nonzero kz、Maxwell dispersion及非共轭transversality成立时，要求**实际plane/global两场** raw signed Poynting均落在明示gamma_n machine-epsilon传播界内。有限面积/scale/bound及normal-range运算受检。仅此证书绕开严格positive→zero guard；原1e−10差门、amplitude/field representability gates不变。坏transversality、传播与lossy真实power-underflow negatives已通过。

## 资源、证据与移交

| 运行 | measured whole-tree peak RSS | wall / swap / cleanup |
|---|---:|---|
| eight small tests + ABI | 325484544 B | 5.9288s；swap0；descendants cleared；8passed/1deselected |
| 532-mode complete component | 327430144 B | 10.3655s；swap0；descendants cleared |
| 新carrier named unique backing | 6135040 B | staging释放前；不是RSS/peak，不含sorting/JIT/MPC/allocator/identity临时量 |

两run均外部subreaper supervision，cap1.5GiB/600s/zeroSwap/MPI1/maththreads1。512MiB named-payload bound是独立声明，不加到RSS；sampling不是cgroup硬峰保证。warm JIT/cache下测量，不作冷启动或目标速度结论。

- `component_qualification_a054626.json`：完整身份、命令、supervisor、ABI/原始artifact hashes、failed attempts及测量
- `source_receipt_a054626.json`：源码与activation/probe、外部监督脚本hash
- ignored raw：`benchmarks/artifacts/task40extra_dot_parallel_cloud/boundary_plane_532_mpc_attempt4/`；oracle ledger和partial checkpoint分别保留，后者仍明确partial
- 未资格：centered p2 full original PDE residual/official observables、full default regression、p4/p6、MPI multi-rank、目标规模/2TB/48h、workstation portability/restart及target global amplitude underflow

下一步由modal worker独立计划centered p2 dense/sparse/full3D reference/notch qualification。旧clipped denseauthority只保留历史对照，不能作为新centered算子相等要求。当前组件不启动该PDE阶段。本报告现已归档；GitHub实际渲染另行检查。该组件资格不授予同分支后续centered PDE候选的运行资格。
