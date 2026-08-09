# Task037b Review V6：牵引一致性对齐与 MPI8 资格结项

## 结论

V6 在与 V5 相同的冻结候选上完成了唯一一次正式 MPI8 数值运行：从零初值启动，没有 retry、warm start、continuation 或参数修改。线性、恢复、exact traction 与 own-physics/canonical Gate 均通过；由于 candidate online process-tree RSS 超过 6 GiB，本结果仍是 research-only：

`DOUBLE_APPROXIMATE_MPI8_TIGHT_LINEAR_AND_PHYSICS_PASS`

| 层次 | 结果 | 说明 |
|---|---|---|
| numerical | pass | iteration `792`，五项 postsolve residual 均 `<=5e-9` |
| recovery | pass | external q 与 bottom/top full-FE recovery 通过 |
| physics | pass | exact traction、interface E/H、energy、canonical 通过 |
| offline comparison | pass | 修复后的独立 checker `result.pass=true`、`failures=[]` |
| resource | `MPI8_RESOURCE_NEGATIVE` | candidate process-tree RSS `7.126468658447266 GiB > 6 GiB` |
| production | `not_qualified/research-only` | ordinary defaults unchanged；master merge 未授权 |

全部 raw 路径、SHA、checkpoint、生命周期和比较细节以 [V6 compact record](../../benchmarks/cases/101_hybrid_iterative_block_solver/records/task037b_v6_mpi8_traction_aligned_full_qualification_v1.json) 为主索引。

## 1. 身份与冻结配置

本轮 implementation 与 formal candidate source 均绑定 `ea132d8a31e5ccd6c45fb90bbb9b5f676cd78b0e`；candidate 正式 MPI8 run 恰为一次，zero initial，未使用 retry、warm start 或 continuation。H1 authority export 和 offline checker 都是独立进程，不属于 candidate 的在线内存口径。

| 项目 | 冻结值 |
|---|---|
| FE / modal discretization | p6/h10 / modal p6/h10 |
| wavelength / polarization / incidence | 13.5 nm / S / 10° |
| interfaces | 10 / 110 nm |
| modal count | requested M120 / candidate 240 |
| external DtN | 40 modes per side |
| MPI | 8 |
| outer operator | exact monolithic Hybrid operator |
| two-sided PC | fixed whole-endcap ILU(0) + 40-mode DtN Woodbury action |
| outer solver | right FGMRES，restart 90，max_it 1000，rtol `5e-9`，atol `0` |
| initial guess | zero |
| propagation / traction model | `full3d_uniform_cg` / `scalar_cg_discrete_derivative` |
| ordinary defaults | unchanged |

这里的“exact monolithic operator”表示外层迭代看到的是完整 Hybrid 线性算子；两侧 Woodbury action 只用于固定的 block-LDU 预条件器，不是另造一个 direct fallback。

## 2. 五项线性 Gate

最终 KSP reason 为 `2`，convergence iteration 为 `792`，threshold 为 `5e-9`。retained solution 上的 postsolve explicit audit 与 KSP reported scalar 分开保存，二者共同通过：

| residual | final value |
|---|---:|
| reported (`ksp.getResidualNorm()`) | `3.5780618848244904e-9` |
| global explicit | `3.5780621758560974e-9` |
| bottom explicit | `4.921856192471026e-9` |
| top explicit | `2.6635966837463555e-9` |
| modal explicit | `1.673064946867675e-15` |

history 共 `793` 行，连续覆盖 `0..792`，每个 iteration 一条 exact row；postsolve recomputation count 为 `1`，monitor 未重复施加 exact residual action。到达的审阅 checkpoint 为 `0,1,2,5,10,20,60,100,200,500,534,557,600,630,700,750,792`；`800/850/900/950/1000` 均为 `not_reached`，没有写入预测值。iteration `534` 的 bottom residual 为 `1.3641751862904296e-6`，decision 仍为 `ITERATING`。

## 3. Recovery 与 own physics

bottom/top external q identity relative residual 均为 `0.0`。full-FE recovery 逐侧通过：

| side | linear residual | interior relative | interior max |
|---|---:|---:|---:|
| bottom | `3.575993025427101e-9` | `1.963069419531454e-12` | `9.13998051238186e-13` |
| top | `4.2692816985701626e-9` | `2.008475074822439e-12` | `1.0800977776814194e-12` |

exact traction dual 为 bottom/top `4.82014143560811e-9 / 2.6635966837463555e-9`，均满足冻结 `1e-8` Gate。candidate energy 为：

| R | T | A | A_volume | R+T+A_volume | closure |
|---:|---:|---:|---:|---:|---:|
| `0.0007628816277264678` | `0.6027016338728362` | `0.39653548449943743` | `0.3965354850818476` | `1.0000000005824101` | `5.824101201312715e-10` |

canonical bottom/top 的 active-trace 与 full-FE 四个角色均通过；selected interface 与 middle E/H 也均通过。独立 checker 的 q、energy、canonical、selected-field 数值分别为：q bottom/top relative L2 `3.1552576669346807e-9 / 4.05930880463431e-9`；bottom/top/middle E/H relative L2 分别为 `3.6550912519981292e-9 / 1.960485560693665e-9`、`1.6077088754815805e-9 / 3.0693637907261264e-9`、`2.178645424601463e-9 / 2.2049249305064133e-9`。

## 4. Authority 链与独立比较

首次 H1 authority export 因 augmented active-trace 长度 `8464` 与 condensed active rows `8424` 不匹配而失败；该 raw summary、NPZ、stdout 仍保留。随后在 source `3c717d41cf1a8ad375e03db207cc2a0a231256d4` 的窄 wiring 修复后，独立 H1 export 成功并产生完整 modal、selected E/H、q 与 canonical payload。candidate 没有重跑。

首次 checker 输出 `pass=false` 也保留，原因属于 checker implementation/representation contract；在 checker source `a4477c2a3d6232434695d6295deee9f05a554c5c` 修复后只重跑 checker 一次，candidate/H1 PDE 均未重跑。

orders 共 `80/80` key/finite coverage，其中 `12` 个 significant、`68` 个 below-floor；significant power/amplitude 为 `12/12`。all-80 的近零通道误差只作 coverage diagnostic，不把小幅值的相对误差当作资格 Gate。最大 significant relative error 为 power `6.693275231450045e-7`、amplitude `5.300628623385173e-7`。

| 比较 | analytic identity | power | amplitude | 最大 power / amplitude error |
|---|---:|---:|---:|---:|
| iterative vs frozen Full3D | 12/12 | 12/12 | 12/12 | `1.5279966083647095e-10 / 4.140043436863321e-9` |
| direct-Hybrid vs frozen Full3D | 12/12 | 12/12 | 12/12 | `1.984856723424855e-12 / 2.0684155314519094e-12` |

H1 direct 仅作为 frozen M120 comparison authority；它不代表 mode-count convergence，也不代表 continuum convergence。pinned Full3D 对 modal、canonical、selected interface/middle fields 没有对应 numeric arrays，因此这些维度仍明确为 `not_available`，没有用 hash 或 pass label 冒充数组。

## 5. Modal amplitude 的表示语义

raw modal coefficient relative L2 为 `1.993317780985689`，必须保留为 diagnostic，绝不是 pass；magnitude relative L2 为 `1.3177050713514743e-9`。两个独立 QEP 若没有共享 basis fingerprint 或 transport 矩阵，逐项 coefficient 比较不具 gauge invariance：相位和近简并子空间的基底选择可以改变 coefficient，而不改变重建场。

因此本轮对 Review V6 字面 raw modal-amplitude 要求作透明的表示语义修正：modal qualification 的权威是坐标完全对齐、实际重建出的物理 E/H，raw coefficient mismatch 仍保留为 `diagnostic_not_comparable_independent_qep_gauge`。没有伪造 transport，也没有删除 `1.993317780985689`。

## 6. 生命周期与资源

postsolve audit、release-repeat 与最终 release 均通过。KSP/PC、两侧 ILU、两侧 W/K/LU、approx modal Schur 均按既定顺序释放；snapshot 保存后最终四项 destroy/release 均为 true，borrowed exact actions 可用，repeat relative difference 为 `0.0`。

| candidate online 指标 | 值 |
|---|---:|
| process-tree RSS peak | `7297.50390625 MiB = 7.126468658447266 GiB` |
| worker RSS / PSS / USS peak | `7282.8046875 / 5580.908203125 / 5306.3828125 MiB` |
| peak stage | `candidate_field_recovery` |
| swap | all-live readable rows observed zero；不扩大为 dedicated-cgroup Gate |
| resource classification | `MPI8_RESOURCE_NEGATIVE` |

H1 独立 export peak 为 `7.766315460205078 GiB`，checker RSS 为 `110.66796875 MiB`；二者均不并入 candidate online peak。candidate 阶段计时来自 immutable V6 raw：cross/QEP `0.9218149570515379s`、bases `53.62479058501776s`、action/coupling `212.48145506496076s`、setup `47.69138909096364s`、outer `129.57329463399947s`、total `469.0012320310343s`。

## 7. 测试与边界

已有证据为：preformal focused serial `29 passed`；MPI2 与 MPI4 指定 action/lifecycle 节点各 `5 passed/rank`；touched-file Ruff check、format-check、compileall、diff-check 通过；postprocessor correction 的 `test244` 为 `9 passed`，test59/test74 相关节点 `4 passed`；最终 checker 修复 Gate 中 test243 `12 passed`、test246 `12 passed`，两文件静态 Gate 通过。full pytest 与 CI 均为 `not_run`，不声称 CI 通过。

Review V6 至此闭环：数值、恢复、物理与独立比较事实均已绑定 compact 和 immutable raw。用户随后授权的持续内存优化属于下一独立研究阶段，不改写本 V6 事实，也不能把本结果冒充 production qualification。ordinary defaults unchanged；master merge 未授权。
