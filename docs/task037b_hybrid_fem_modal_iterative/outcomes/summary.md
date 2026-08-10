# Task037b 受控结项总览

## 一句话结论

原 H0-H5 历史保持不变：H5b local inverse 双侧资格化失败，按合同受控停止；此前 H1 的首次失败与 post-fix recovery 也继续保留。随后 Review V1/V2/V3/V4 受控研究中，V3 双侧 screen numerical pass 但 resource negative；V4 唯一 MPI8 full solve 为 controlled local-block numerical negative，resource 也未达到 `<=6 GiB`，official physics 全部 not_run，当前 awaiting review。

## H0-H10 矩阵

| 阶段 | 状态 | 说明 |
|---|---|---|
| H0 | pass | 继承基线和文档治理完成 |
| H1 | pass（post-fix；首次 failed_before_solve 历史保留） | task.md §9 H1 numerical contract 通过 |
| H2a | pass | assembled-block MatPython action identity |
| H2b | pass | Matrix-free local endcap exact action identity |
| H3 | pass | exact block-LDU iterative oracle；offline 12+12 已通过 |
| H4 | pass | exact Sₘ + bounded G-only diagnostic；不要求 12+12 |
| H5a | pass | bottom/top exact local reference 各 11/11；direct max=`2.107282966996484e-12 / 2.1971754846774315e-12`，action max=`2.0973803488508764e-12 / 2.1957548735380243e-12`；factors 顺序释放 |
| H5b | controlled negative | bottom `1/11`、top `0/11`；分类 `LOCAL_INVERSE_FAMILY_NEGATIVE` |
| H5c | not_run | H5b 数值 Gate 未过 |
| H6 | not_run_by_order | H5 双侧 local inverse 失败触发停止 |
| H7 | not_run_by_order | 同一 H5 stop |
| H8 | not_run_by_order | 同一 H5 stop |
| H9 | not_run_by_order | 同一 H5 stop |
| H10 | not_run_by_order | 同一 H5 stop |

## H1 首次停止点（3f72ef3）

mode classification 发生在横截面 QEP 求解之后、Hybrid block system 生成之前。它把传播常数接近的模态分成小组，并建立后续界面方程需要的双基底。当前检查发现索引 50 和 52 属于不同组，但误差量达到冻结分组检查的边界，于是 fail closed。

| 字段 | 实际值 |
|---|---:|
| exception | NearDegenerateBlockPartitionSplitError |
| indices | [50, 52] |
| group_ids | [17, 18] |
| relative beta distance | 1.580086e-06 |
| identity row norm | 1.024637e-06 |
| identity max/cross-block max | 6.572908e-07 |
| limit | 1.000000e-06 |
| formal return code | 1 |

这一步没有产生当前 Hybrid 的解，因此不能填写为 0 的量都应标作 not_observed 或 not_run。

## 当前源码与 authority

| 项目 | 值 |
|---|---|
| branch | codex/20260807-task37b-hybrid-iterative-development |
| clean source SHA | 3f72ef3eb4f3002246802af30ef7bca6b0080888 |
| Full3D historical record | /home/Projects/MyFEniCS/benchmarks/artifacts/task035c_hybrid_channel_memory/p6_h10_full_static_mpi8_244b62e.json |
| Full3D record SHA256 | b8b428476cdeb4b80495f4a8b1c89e3bb2f67c682c695fc72bb59dbbbd94b4e3 |
| historical preflight authority SHA256 | 96ac3949efc236393d4c2dbc6e1fa334ad5ccb0e9796bdeba13fbe0515577dd8 |
| pinned source | 244b62e1fb4f299a468363cf90a2dd548dc34ff6 |
| pinned gate | pass |
| ordinary defaults | unchanged |
| H1 mode | explicit opt-in |

## H1 结果边界

| 结果组 | 状态 |
|---|---|
| H1 telemetry | not_observed |
| combined/bottom/top FE/modal residual | not_observed |
| interface E/H 与 middle-plane E/H | not_observed |
| powers/amplitudes | not_run |
| R/T/A 与 A_volume closure | not_run |
| rows/block shapes/matrix NNZ/factor NNZ | not_observed |
| official Hybrid result | not_run |

## H1 post-fix recovery（2990f357）

post-fix formal return code 为 `0`，`formal_pass=true`，true relative residual 为 `1.4476013948489319e-12`。rows、block shapes、matrix/factor inventory、interface/middle-plane fields、R/T/A、A_volume closure、资源和 hash-bound 原始证据详见 [direct authority](direct_hybrid_authority.md) 与 [resource ledger](resource_ledger.md)。

| Gate | post-fix 结果 |
|---|---|
| true residual | `1.4476013948489319e-12`，pass |
| frozen-reference powers / boundary amplitudes | `12/12` / `12/12`，pass |
| Full3D pairwise relative-1e-3 powers / amplitudes | `12/12` / `12/12`，pass；最大相对误差分别 `6.51037642788911e-10` / `6.667955305244103e-10` |
| interface/middle-plane E/H | pass |
| R/T/A_volume closure | `1.0000000001554779`，error `1.5547785281455617e-10`，pass |
| swap | 0 |
| ordinary defaults | unchanged；H1 explicit opt-in |

runner 仍保留 `physical_qualified=false`、`official_record=false`、`mode_count_converged=false` 的 wider-M funnel 旧标签；它们不是 task.md §9 H1 Gate，也不改变本次 H1 task-specific contract pass。随后 H3 与 H4 已按顺序完成；H5 另行评估冻结 local inverse family。

## 资源

| 指标 | 实测值 |
|---|---:|
| wall | 约 49.54 s |
| RSS/process-tree peak | 2647.4375 MiB |
| authority peak | 2.58538818359375 GiB |
| PSS peak | 1761.02734375 MiB |
| USS peak | 1637.375 MiB |
| swap | 0 |
| memory warning/termination/timeout | false / false / false |

该峰值来自 classification 阶段 whole-job，不是成功 Hybrid 求解的资源预测。

raw JSON 字段名虽含 max_*_mb，但本文按 bytes/1024^2 统一换算并显示为 MiB；authority 峰值显示为 GiB。

## 统一验收与未运行边界（H1 停止点历史快照）

| 能力/验收 | 状态 |
|---|---|
| current-source direct numerical authority | failed_before_solve |
| iterative Hybrid | not_run_by_H1_gate |
| exact action / exact LDU | not_run_by_H1_gate |
| bottom/top local inverse | not_run_by_H1_gate |
| one-sided / double funnels | not_run_by_H1_gate |
| MPI/restart | not_run_by_H1_gate |
| 12+12 powers/amplitudes、channel/field、RTA | not_run_by_H1_gate |
| merge recommendation | do_not_merge_to_master / wait for review |

## 测试与证据

测试和资源细节分别见 [测试汇总](test_summary.md)、[direct authority](direct_hybrid_authority.md)、[资源账本](resource_ledger.md) 和 [changed files](changed_files.md)。raw artifact 位于 Git ignored 目录；tracked docs 只保存相对路径和 SHA，不提交原始输出。

## 下一步边界

首次失败阶段不修 solver、不放宽 1e-6、不扫描 M、角度或 p-h；post-fix 只实施已审查的最小 grouping/audit 修复并完成一次 H1 recovery。H2a、H2b、H3 与 H4 已通过；H5a/H5b 已完成，H5c、H6-H10 按停止规则未运行。

## H2a 当前边界

H2a 已完成 assembled bottom/top block 与 modal/coupling action 的 algebraic identity：
MPI1/2/4 的 deterministic probes、physical packed RHS、bottom-only/top-only/modal-only
probes、pack/split 和 ownership mapping 均通过。production global operator 是 MatPython，
没有 materialize global AIJ。

逐 probe relative error 与完整命令见 [block identity](block_operator_identity.md)。H3/H4 的 exact oracle 证据见 [exact block-LDU oracle](exact_block_ldu_oracle.md)。

## H2b Matrix-free local endcap exact action identity

H2b 将外部 auxiliary 从 Hybrid Krylov unknown 中排除：production 从构造开始使用
local-Schur action 和 matrix-free DtN action，test-only oracle 才使用 explicit-condensed
local blocks。它证明的是 local endcap 的代数 action、ownership、pack/split 与销毁顺序，
不是第一次 outer FGMRES、solver convergence 或资源资格化。

| 项目 | 结果 |
|---|---|
| H2b-L MPI1 | `1 passed`；bottom action/recovery/RHS `3.058e-16 / 4.352e-16 / 0`，top `3.730e-16 / 4.297e-16 / 6.993e-17`；Gate `<=1e-11` |
| H2b-G MPI1/2/4 | 每 rank `5 passed`；七 probes 四块合计最大分别 `2.942e-16 / 2.988e-16 / 3.539e-16`，均 `<=1e-11` |
| mapping/pack-split | 每个 MPI missing/extra/duplicates=`0/0/0`；bottom/top/modal=`0/0/0` |
| inventory | global A=false；bottom/top F=false；explicit external C/D=`0/0`；p6 direct factor count=`0`；Krylov auxiliary rows=`0` |
| 相关回归 | test224/test230/test231=`5 passed / 1 skipped`；import、Ruff、format、compileall、diff-check 全部 pass |

H2b-G 的每行数值是该 MPI 七个 probes 和 global/bottom/top/modal 四个输出块的总体最大值；
四块逐项均不超过对应 MPI 行的总体最大值。H3 与 H4 已完成；H5 结果见下节。

## H3/H4 exact oracle checkpoint

| 阶段 | formal/diagnostic 结果 | 核心数值 | 资源与边界 |
|---|---|---|---|
| H3 | formal、numeric、no-swap pass | outer=1；true global/bottom/top/modal=`2.892237294698294e-12 / 3.610918199454199e-12 / 2.0470485206121342e-12 / 9.879221339086588e-13`；offline 12+12=`12/12 + 12/12` | `507.2017102949321 s`；authority peak `9.585384368896484 GiB`；factors released |
| H4a | exact Sₘ pass | outer=1；true global/bottom/top/modal=`2.7239301070596716e-12 / 3.982460029685523e-12 / 1.7429945983458624e-12 / 1.001248228432052e-12` | H4 whole-job oracle peak `9.802722930908203 GiB`；swap=0 |
| H4b | bounded diagnostic complete | G-only outer=3、reason=-3；finite/evidence/factor lifecycle pass；不以残差大小判失败 | H4 不要求 12+12；H5 采用 approximate Sₘ 路径 |

## H5 frozen local inverse qualification

H5 评估的是冻结的双侧局部近似逆：把端部区域切成 x 方向 6 个有重叠的子块，用 partition-of-unity ASM 和 shifted ILU(0) 作为每次右 FGMRES 预条件器。它试图降低直接因子的内存，但必须用显式重新计算的 true residual 证明每个固定 RHS 真正被解到任务阈值。

| 阶段 | 状态 | 关键事实 |
|---|---|---|
| H5a direct reference | pass | bottom/top 各 11/11；bottom/top direct max=`2.107282966996484e-12 / 2.1971754846774315e-12`，action max=`2.0973803488508764e-12 / 2.1957548735380243e-12`；两侧 factor 均释放 |
| H5b local inverse | controlled negative | bottom `1/11`、top `0/11`；其余返回 `reason=-3`、`iterations=300`；最大 true residual `0.9422475005587448 / 0.9427702892133474` |
| H5b repeat | deterministic only | 两次解的 repeat relative error 为 `0`；这不等于收敛 |
| formal return | `2` | 22 个 RHS 完整记录后按数值 Gate 受控退出，不是 infrastructure failure |
| H5 classification | `LOCAL_INVERSE_FAMILY_NEGATIVE` | 只否定本轮冻结 local inverse family，不否定 Hybrid 模型、direct authority 或未经授权的其他算法家族 |
| H5 official R/T/A、field、12+12 | not_run | H5b 在这些后处理前已停止 |

资源、逐 RHS residual、fixed-apply 诊断、factor NNZ/载荷估算和证据 hash 见 `local_endcap_inverse_matrix.md`；该历史材料只保留在远程 Task37b 执行分支，不进入 master。H6 后续一侧替代与 H7-H10 funnel 均按停止规则未运行。

完整 residual、Sₘ/G feedback、operator inventory、factor before/after 和 hash-bound artifact 见 [exact block-LDU oracle](exact_block_ldu_oracle.md)。

## V1 R1–R5 最终研究结项

R1–R5 是 Review V1 的单一连续研究链，R5 source 为
2a2ef3d37514e4ab30d50209065af84c1dafd59b。冻结身份仍为 p6/h10、modal p6/h10、
M120/candidate240、MPI8、S、10°、10/110 nm、static-condensed、
full3d_uniform_cg/scalar_cg_discrete_derivative；两份 authority 未改变。

| 阶段 | 状态 | 证明了什么 |
|---|---|---|
| V1-R1 | pass | 真实 F/C/D/H action decomposition identity；6 probes/side，destroy 后 A 可用 |
| V1-R2 | controlled numerical negative | 六-slab F-only 不能资格化，说明仅排除 DtN correction 仍不足 |
| V1-R3 | controlled numerical negative | whole-endcap ILU(0) 比六 slab 改善，但 F-only 与 complete-A 均未过 1e-8 |
| V1-R4 | pass | exact F inverse + 40-mode Woodbury 与 exact A 一致；公式、符号和 ownership 正确 |
| V1-R5 | WHOLE_ENDCAP_ILU0_DTN_WOODBURY_NEGATIVE | PC 代数、确定性、K、数组有限性、lifecycle 和资源合法，但 21/21 非零 capacity 全部失败 |

R5 random residual 约 6.89e-3–9.56e-3，modal 约 4.87e-5–2.04e-4，top physical
约 8.19e-4。DtN correction 将 complete-A 结果拉回 whole-endcap F-only 的量级，但
ILU(0) fine-space 逼近仍比 1e-8 高约 4–6 个数量级。severe_negative=false 只表示
未触发预定义 severe 子标签；它既不满足 full，也不满足 borderline，所以按 Review §13
仍归 negative 并关闭本任务。该结论不表示 Hybrid 模型错误，也不表示 Woodbury 公式失败。

### 最终状态矩阵与边界

| 阶段 | 最终状态 |
|---|---|
| H0 | pass |
| H1 direct authority | pass |
| H2a / H2b | pass |
| H3 exact block-LDU | pass |
| H4a exact Sₘ | pass |
| H4b G-only | bounded diagnostic complete；non-stopping negative |
| H5a | pass |
| H5b | controlled negative；原六-slab candidate |
| H5c | not_run |
| H6–H10 | not_run；closed pending new review |
| V1-R5 official R/T/A、field、12+12 | not_run |
| ordinary defaults | unchanged |
| master merge | not authorized |

V1-R1–R5 的 compact hash-bound record 见
`../../../benchmarks/cases/101_hybrid_iterative_block_solver/records/task037b_v1_r1_r5_research_closeout_v1.json`；
逐 RHS 表与解释见 `local_endcap_inverse_matrix.md`。R5 raw artifact
仍在 Git ignored 目录，response_v1、原 H5b raw 数值和既有 review/task 文件均未改写。

R5 的 process-tree peak 为 6432.54296875 MiB（6.281780242919922 GiB），低于本轮
standalone 7.0 GiB threshold，swap=0；这只是独立资源 Gate，通过不等于 H9 或 production
resource qualification。Hybrid-P、低秩 direct Hybrid 与本 iterative candidate 均保持
research-only。

## Review V2 单侧 block-PC screen 结项

V2 继续回答一个窄问题：已经通过代数和生命周期审计的固定 DtN Woodbury action，作为
完整 Hybrid block-LDU 的近似局部逆，是否在最多 20 步外层 screen 中提供真实容量。
它不运行 official field、R/T/A 或 Full3D physical comparison；ordinary defaults 仍未改变。

| 运行 | 结果 | true residual | 关键资源 |
|---|---|---:|---:|
| V2-B bottom approximate / top exact | numeric pass | final=min=0.26797784324787316；last5 净下降 | process-tree 8164.375 MiB，7.9730224609375 GiB |
| V2-T top approximate / bottom exact | numeric negative | final=min=0.3518371324843258；严格高于 0.35，差 0.0018371324843258 | process-tree 8736.828125 MiB，8.532058715820312 GiB |

两份 raw record 的 contract/integration、callback、modal Schur、factor identity、online
apply、release、source/launch/resource authority、swap 和 no-orphan 均通过。V2-T 的
formal_record_pass=true 只表示实现、来源、资源监测和完整 raw record 已完成；不能把它
解释成 numerical pass。它的 worker_numerical_pass=false 与 status
task037b_v2_screen_numerical_negative 一致。

V2-B 的 fixed callback identity=0、linearity error=1.9458251250889472e-15、
determinism=0、repeat hash 一致、K rank=40/condition=3.033166890369435；V2-T 对应
为 0、1.9498727881145686e-15、0、hash 一致、rank=40/condition=4.162687539173754。
两份 modal Schur 均为 240×240、rank=240，condition 分别为 831.7366055154229 与
638.1064857343471，build apply bottom/top 均为 480/480。B 的 factor identity
bottom direct/ILU=0/1、top=1/0；T 反向为 1/0、0/1；online increments 两侧均为 40。

最终 classification=TOP_APPROXIMATE_SIDE_NEGATIVE。double 20/100/200、full solve、
official Hybrid field、R/T/A、external diffraction、12+12 和 Full3D physical comparison
均为 not_run_due_to_one_sided_gate 或 not_run。两侧 process-tree 峰值均高于 6 GiB
standalone resource-positive 线，因此没有 resource-qualified candidate；T 的峰值含
exact bottom direct factor，不能预测 double 峰值。

完整 residual history、PSS/USS 口径、raw artifact 路径与 SHA 见
`../../../benchmarks/cases/101_hybrid_iterative_block_solver/records/task037b_v2_block_pc_screen_v1.json`；
V2 单侧表见 `one_sided_replacement.md` 与 `double_iterative_funnel.md`。

## Review V3 双侧 fixed block-PC formal 结项

V3 研究的是把两个端盖都换成同一个固定、只做一次作用的近似 action，再用 exact
matrix-free Hybrid block operator 做外层迭代。这样可以直接观察“双侧不保留 direct factor”
是否仍有持续收缩，同时不把本轮 screen 冒充 official physics。

| 项目 | V3 结果 | 数据身份/边界 |
|---|---|---|
| source | `c7b6aa3ddaac4dbfb9f86aab8f59801330d63a16`，parent `9e01280...` | measured provenance |
| frozen case | p6/h10、modal p6/h10、13.5 nm、S、10°、10/110 nm、M120/candidate240、MPI8 | measured configuration |
| callback | identity=0、linearity约2e-15、determinism=0、repeat hash相同 | algebra pass |
| K / modal Schur | K rank=40，condition=3.0332/4.1627；modal 240×240、rank=240、condition=1845.7878710 | measured algebra |
| factor inventory | direct bottom/top=0/0；ILU=1/1；global direct=0；global A=false；F=false/false；explicit C/D=0/0 | measured lifecycle contract |
| 200-step screen | r20=0.47312934919147054；r60=0.11272071486850113；r100=0.022267181511852894；r200=0.0015751888272117643 | measured true residual |
| prediction | 120–200 共81点；q_fit=0.9734079564；predicted total=469 | derived from raw true history |
| numerical disposition | `DOUBLE_APPROXIMATE_200_STEP_PASS_AWAITING_FULL_REVIEW` | numerical pass |
| MPI8 resource | 6448.09375 MiB = 6.296966552734375 GiB | resource negative，超过6.0 GiB |
| engineering / stretch | false / false | 分别超过5.0 / 3.77 GiB |
| official physics | field、R/T/A、A_volume、orders、12+12、Full3D comparison | all not_run |

formal record、numeric contract 和 release 均通过；资源分类独立为 review required，不改写
numeric pass。停止原因是 Review V3 授权边界已完成、等待下一轮 review，不是算法失败。
V2-B/T 的 process-tree peak 分别为 7.9730224609375/8.532058715820312 GiB；V3 约低
21.0%/26.2%，但 V2 含一侧 direct factor，不能作等价性能外推。

V3 raw evidence 与完整 17 checkpoint 见
`../../../benchmarks/cases/101_hybrid_iterative_block_solver/records/task037b_v3_double_block_pc_screen_v1.json`。
Full3D authority SHA 为 `b8b428476cdeb4b80495f4a8b1c89e3bb2f67c682c695fc72bb59dbbbd94b4e3`，
preflight authority SHA 为 `96ac3949efc236393d4c2dbc6e1fa334ad5ccb0e9796bdeba13fbe0515577dd8`；
本轮只做 authority identity check，没有运行 Full3D comparison。V3 source、runner、watchdog、
candidate 与 compact docs 仍为 research-only，ordinary defaults unchanged，master merge
未获授权。

## Review V4 唯一 MPI8 full solve

V4 是在 source `eb1fc88483dd4d9cb5eabb071f8af0e87f91ba49` 上唯一运行一次的 full-solve lane。
它用固定的 whole-endcap ILU(0)+40-mode Woodbury action 做两侧局部预条件，并用 exact
matrix-free block operator 做 outer right FGMRES；固定 action 只意味着 callback 的线性操作
和生命周期被冻结，不意味着引入 nested local solver。ordinary defaults、V2/V3 flags 和历史
结果均未改变。

| 层次 | 结果 | 数据身份/边界 |
|---|---|---|
| formal run | exactly one；KSP reason=2，iteration=534 | measured raw solver record |
| numerical | negative | global/top/modal 通过；bottom=`1.3641751886101987e-6` 超过 `1e-6` |
| disposition | `FIXED_ILU0_WOODBURY_BLOCK_PC_FULL_NEGATIVE` | controlled local-block Gate miss，不称发散或平台 |
| process-tree RSS | `6440.1328125 MiB = 6.289192199707031 GiB` | resource negative，超过6 GiB |
| engineering / stretch | false / false | 分别超过5 / 3.77 GiB |
| official physics | field、recovery、R/T/A、orders、12+12、canonical、direct/Full3D | not_run |

### V4 checkpoint 与结构证据

| iteration | global | bottom | top | modal | PC apply | bottom/top action |
|---:|---:|---:|---:|---:|---:|---:|
| 20 | 0.4731293491910546 | 0.7915576229904723 | 0.4144951475878447 | 2.7011301558523683e-15 | 20 | 527 / 527 |
| 60 | 0.11272071486842282 | 0.2032001429319691 | 0.06665913881529464 | 2.5454113396942133e-15 | 60 | 607 / 607 |
| 100 | 0.022267181511820732 | 0.02427052205015629 | 0.01791884170341418 | 1.662848140283262e-15 | 100 | 687 / 687 |
| 200 | 0.0015751888272089055 | 0.0024392066956133935 | 0.0010989265634579726 | 1.0150435351696175e-15 | 200 | 887 / 887 |
| 534 | 9.832241902112744e-7 | 1.3641751886101987e-6 | 7.290772097898545e-7 | 1.2365161175289584e-15 | 534 | 1555 / 1555 |

global operator 为 Python matrix-free，global/bottom/top direct factor 为 `0/0/0`，两侧
ILU 为 `1/1`，global A/F 与 explicit C/D 均未 materialize。两侧 K rank=40，condition 为
`3.0331668903694333 / 4.162687539173756`；modal Schur 为 240×240、rank240、condition
`1160.2452412629682`，matrix/LU repeat error 为0，normal equations=false。online 每侧
apply 增量为 `1068=2*534`。完整 history 0–534 仍只在 hash-bound raw solver record 中保存。

### V4 resource、authority 与后处理边界

timeline 解析得到 worker PSS simultaneous sum peak=`5326.6474609375 MiB`
(`5.201804161071777 GiB`)，USS simultaneous sum peak=`5144.26171875 MiB`
(`5.023693084716797 GiB`)，二者峰值均位于 `v4_worker_cleanup_finished`，RSS 仍是
process-tree authority。PSS/USS 是8 rank同一采样的 smaps_rollup sums，不是累计对象体积；
峰值发生在 cleanup 后，可能反映 allocator high-water，而不是 live object inventory。

timeline/process-tree 观测 swap 均为0，但 all-live authority/swap readability=false、job
cgroup 非dedicated，所以正式 zero-swap/memory-authority Gate 未资格化；保留 raw
`no_swap=false` 与 `terminated_for_authority_unreadable=true`。worker 自然结束、未被
SIGKILL、process group 已退出。

bottom Gate 失败后 recovery、external auxiliary、field、R/T/A、A_volume、orders、12+12、
canonical、direct-Hybrid 与 Full3D comparison 均为 `not_run_dependency_gate`。H1 modal、
canonical、selected-fields 数值载荷不存在，独立 checker 对这些项写
`not_run_authority_payload_gap`，没有用 hash 或零值替代数组。checker exit=0 只表示
`evidence_integrity_pass=true`，不是完整 qualification pass；其 failure 为
`h1_authority_payload_gap`，offline wall=`0.05152548989281058 s`、ru_maxrss=
`35.13671875 MiB`，不并入 online RSS。

V4 raw/compact evidence 见 `../../../benchmarks/cases/101_hybrid_iterative_block_solver/records/task037b_v4_mpi8_full_qualification_v1.json`
和 [V4 full qualification](full_mpi8_qualification.md)。正式停止原因是授权边界完成并等待
review，不是自动开启重跑、调参或新算法家族。

## Review V5：同一 candidate 的多指标 full-solve 结项

V5 在 source `892f186b39c0eb89f1912640430fd79599d86318` 上只运行一次；它保留 V4 的
fixed-action 与 full-solve 数据流，新增的多指标 Gate 要求 reported/global/bottom/top/modal
五个残差同时达到 `<=1e-6`。V5 implementation checkpoint 为
`770e74513b4444f032adb7f61c5d350fb53d9458`，formal 后纯 postprocessor correction 为
`11c01d5268f1e0fc8eb307945179b540ccfcb2aa`；没有 retry、warm start、continuation 或参数修改。

| 结果层 | 精确结论 | 证据边界 |
|---|---|---|
| numerical | pass；KSP reason `2`，iteration `557` | 五个终值 `6.457740108721289e-7 / 6.45774010063497e-7 / 9.811891391712585e-7 / 4.5634977013685214e-7 / 1.3354878193519844e-15` |
| recovery | pass | q identity 与两侧 full-FE recovery 均通过 |
| own physics | fail_exact_traction_dual | bottom/top exact dual `9.609121539153052e-7 / 4.5634977013685214e-7`，限值 `1e-8` |
| overall | `MULTIMETRIC_LINEAR_PASS_RECOVERY_OR_PHYSICS_FAIL` | 不是 linear solver failure |
| resource | `MPI8_RESOURCE_NEGATIVE` | process-tree RSS `7.049583435058594 GiB > 6 GiB` |
| production | `not_qualified/research-only` | ordinary defaults unchanged，master merge 未授权 |

official `R/T/A`、`A_volume`、orders、field、12+12、canonical、direct-Hybrid 和 Full3D
comparison 全部 `not_run`。energy closure 是 diagnostic gate，不是 official output。H1 缺少
modal/canonical/selected-fields 数值 payload；conditional direct export 因 own physics
失败为 `not_run_dependency_gate`。

V5 compact evidence 见
`../../../benchmarks/cases/101_hybrid_iterative_block_solver/records/task037b_v5_mpi8_multimetric_full_qualification_v1.json`。完整 checkpoint、生命周期、资源口径、timing、raw SHA 和 parent/postprocessor
边界均以该 hash-bound record 及
[V5 full qualification](full_mpi8_qualification.md) 为准。

## Task37b V6 与 M1–M10 最终结论

本节只追加当前结项，不删除 V1–V5 的负结果、not_run 边界或历史资源口径。逐轮 commit、parent、改动文件、raw SHA 和 checker SHA 以 [memory optimization closeout compact](../../../benchmarks/cases/101_hybrid_iterative_block_solver/records/task037b_v6_memory_optimization_closeout_v1.json) 为唯一结构化索引。

| 范围 | 实施/实验 | 数值与物理 | process-tree RSS peak MiB | 资源结论 |
|---|---|---|---:|---|
| V6 original | traction-aligned tight candidate，唯一 MPI8 | pass | `7297.50390625` | negative |
| M1–M4 | cleanup、canonical side cleanup、streaming | 各自在线数值/物理 pass | `6188.55078125` → `6147.89453125` | M4 仍超 6 GiB |
| M5 | bounded trace expansion | pass；offline pass | `6128.7109375` | positive |
| M6 | compact full-field lookup | pass；offline pass | `6166.9921875` | negative；扩大 local+ghost 集合的代价 |
| M7–M9 | used/entity DoF、cell-major trace | pass；offline pass | `6144.15234375` → `6140.44140625` | positive但余量窄；M9 仅 `-0.40625 MiB` |
| M10 | own-physics pre-canonical release | pass；offline pass | `6018.57421875` | current best，positive |

### 当前最佳正式结论

| 层次 | 结论 | 数据身份/证据 |
|---|---|---|
| numerical / physics | `PASS` | M10 full explicit residual、recovery、traction、own physics、canonical、lifecycle |
| offline authority | `pass=true`，`failures=[]` | checker output SHA `feab4a65d5900c7afc9b7729aa9d80c8449a4ce3822c33c991f8c6baf36a3039` |
| resource | `MPI8_RESOURCE_POSITIVE` | measured process-tree RSS `6018.57421875 MiB`，低于 `6144 MiB` |
| final status | `DOUBLE_APPROXIMATE_MPI8_TIGHT_LINEAR_AND_PHYSICS_PASS_WITH_MPI8_RESOURCE_POSITIVE` | research-only |
| production boundary | ordinary defaults unchanged；master merge not authorized | measured scope boundary |

M10 是与原 V6 相同物理与算法合同下的内存生命周期优化，不是新的 solver/PC/physics。其 `792/2` 收敛、五项 residual、exact traction、R/T/A、`A_volume` 和 closure 均通过；M10 checker 的 80/80 orders、12 significant、canonical、坐标对齐 selected E/H、energy、iterative/direct vs frozen Full3D 12/12 均通过。raw modal coefficient 仍是独立 QEP gauge diagnostic，不改写为 pass；physical E/H reconstruction 是其资格权威。

### M11 决策、未运行项与合并边界

M11 只读审计选择 C（保持现有生命周期）。A 的已知 recovered payload 每侧约 `415776 bytes`，不足以建立至少 `64 MiB` 的可靠收益；B 会引入临时序列化、hash、reload 和 DOLFINx 重建。M11 implementation/formal 均 `not_run`。full pytest、CI、MPI reduction 也为 `not_run`。V6/M1–M10 仍是研究分支证据，不能冒充 production 或 continuum/mode-count/0.7 nm qualification。

完整资源阶段与七轮 cleanup 见 [resource ledger](resource_ledger.md)；M1–M10 改动依赖和 selective merge 边界见 [changed files](changed_files.md)；实际 focused tests 见 [test summary](test_summary.md)。
