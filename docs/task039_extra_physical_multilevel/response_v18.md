# Task39extra Response V18：T1 p4 BLR 固定配置关闭

## 结论

本轮只运行了 T1：在已接受的 Q1 直接因子基线旁，测试一个显式 opt-in 的 p4 BLR（块低秩）因子配置。BLR 试图用低秩块近似消元因子中的部分数值，以减少存储；它仍是全局因子分解，不是无因子迭代预条件器。

T1 的正式结论是 `T1_BLR_CONTROL_REJECTED`，最终行动为 `T5_CLOSE`：质量筛选和内存 Gate 均未通过，因此关闭这个固定阈值配置，不启动 T2/T3/T4，也不推荐下一个 epsilon。外层 `run_summary` 的 `WORKER_FAILED` / exit 4 是数值 Gate 拒绝后的包装状态，不是 OOM、超时或 MPI 崩溃。

| 必答问题 | 正式结论 | 证据与边界 |
|---|---|---|
| 三个 RHS 是否满足质量线 | **不满足** | `rho`、field L2 和 scaled-curl 的失败项见下表；原 A4 恒等式相对误差范围为 `1.1217099246371649e-17–2.097189693808333e-16`，说明一次 MatSolve 的代数证据保存完整，但不等于质量通过。 |
| 实际压缩了什么 | factor 条目从理论 `53,417,584` 变为实测 `48,706,124` | native effective/theoretical ratio `0.9117994554003042`，即条目数少 `8.82005446%`；BLR fronts `33`，BLR-front coverage 为 `49.0%`（fraction `0.49`）。 |
| RSS 内存是否满足 M Gate | **不满足** | `R_peak=R_live=0.9455339995796705`；任务线要求 `R_peak<=0.90`，或 `R_live<=0.80` 且 `R_peak<=1.05`。 |
| 是否因资源异常停止 | 否 | 连续 parent process-tree 资源检查、zero swap 和 descendant cleanup 通过；时间策略为 `observe_only`，`time_gate_evaluated=false`，没有启用时间否决。 |
| 是否进入完整 p6 / 物理结果 | 否，`not_run` | 没有 p6 outer solve、E/H、R/T/A、`A_volume`、80 模式、衍射或守恒结果。 |

因此本轮是一个有明确负结果的 p4 control 证据，而不是“BLR 家族全部无效”的结论。它关闭的是这个固定配置的适用路线。

## 1. 身份与运行范围

| 项目 | 值 |
|---|---|
| 分支 / requested base / formal source | `task39extra` / `863c71d5133b137a888a587becb9cbe8ed2daca9` / `a1bc6b54e613ebf91c5c97ecddcc14555b084ee0` |
| accepted Q1 source | `6a8b273c383d5bd9da37d6630a48bd24d6a90cce`；已接受的原 p4 LU 基线，不在本轮重跑 |
| 模型 | 13.5 nm、原始 Full3D、形式 p6/h10、252 cells、80 DtN modes、MPI1、线程1、PETSc scalar `complex128`、integer `int32` |
| 正式矩阵范围 | p4 增广控制矩阵；本轮没有 p6 outer solve |
| input | `input/task39extra/v17_t1_blr_tradeoff.dat`；SHA `6cb39581bb78572466f05cab0a49b8fd8705ff5e223aaf0d4c870da1751a37c7` |
| resolved config | SHA `dbf63b41985fdee5d9e33dbec5f026d2369d25f08d533ca8438101d590098e2f` |
| physical model | SHA `9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f` |
| T1 run | `results/euv_grazing1_phi0/task39extra_v17_t1_blr_tradeoff__full3d_iterative__mpi1__Mna/20260914T004735.607836Z` |
| Q1 accepted baseline | `results/euv_grazing1_phi0/task39extra_v14_q1_full_direct__full3d_iterative__mpi1__Mna/20260913T115722.489252Z` |
| run count | fresh T1 `1`；replay `0`；T2/T3/T4 `0` |

T1 使用一个 BLR factor 完成三个固定 RHS 的各一次 MatSolve；三个 RHS packet 和原 A4 action/residual 证据均保留。没有 refinement、第二次 solve 或把不完整的场提升为 official result。

## 2. 三个 RHS 的质量 Gate

`rho` 是 BLR 回代向原始 A4 算子的相对残差；field L2 是整体电场相对误差；scaled-curl 是空间变化（旋度）的相对误差。三者都越接近零越好。本轮 checker 使用 `rho<=0.5`、field L2/scaled-curl `<=0.25`。

| RHS | rho（限值 .5） | field L2（限值 .25） | scaled-curl（限值 .25） | 原 A4 identity | MatSolve 次数 | 质量结论 |
|---|---:|---:|---:|---:|---:|---|
| `A2R160_BAL_H_p4_01` | `4.78774161579983` | `0.6042973308874857` | `0.6037676857908261` | `2.097189693808333e-16` | `1` | failed |
| `A2R160_BAL_H_p4_02` | `0.1947573245406759` | `0.6822411297187286` | `0.6817077538074453` | `1.1217099246371649e-17` | `1` | failed（rho 单项通过，但两项场指标失败） |
| `LIGHT448_BAL_H_p4_09` | `6.063573601898471` | `0.6205385284813106` | `0.6201228657608676` | `1.4775796590641492e-16` | `1` | failed |

checker 的质量状态为 `quality_pass=false`；`finite`、`three_rhs` 和原 A4 residual identity 通过，但 `rho`、field L2、scaled-curl 的总体 Gate 失败。identity 的真实范围为 `1.1217099246371649e-17–2.097189693808333e-16`；`rho` 范围为 `0.1947573245406759–6.063573601898471`，场 L2 范围为 `0.6042973308874857–0.6822411297187286`，不能用前者抵消后者。

## 3. BLR 控制与实际存储

BLR 阈值是 `CNTL(7)=1e-3`，`ICNTL(35)=2` 表示启用该后端的 BLR 存储路径；`ICNTL(10)=0` 表示每个 RHS 没有后端内部迭代改进。以下均来自 MUMPS 原生字段或明确读回，不从 `ICNTL(38)` 推断压缩比例。

| 字段 | 实测值 | 说明 |
|---|---:|---|
| BLR fronts | `33` | 统计中参与 BLR 的 fronts 数 |
| BLR-front coverage | `49.0%`（fraction `0.49`） | 百分比与 fraction 明确区分 |
| `INFOG(29)` theoretical entries | `53,417,584` | 理论因子条目 |
| `INFOG(35)` effective entries | `48,706,124` | 有效 BLR 因子条目 |
| `INFOG(9)` actual storage entries | `48,706,124` | 实际存储条目；与 effective 字段一致 |
| effective / theoretical | `0.9117994554003042` | 由上述两个原生字段派生，条目减少 `8.82005446%` |
| theoretical / effective operations | `39,449,025,878 / 29,823,939,778` | `RINFOG(3)` / `RINFOG(14)`；不是条目数 |
| max front / off-diagonal pivots | `1592 / 81` | 原生统计 |
| delayed pivots / memory compress | `0 / 0` | 原生统计，不把它们解释成质量保证 |
| allocated / used upper | `1,623,000,000 / 1,351,000,000 B` | 后端工作数组口径，不等同于进程树 RSS |

关键控制读回为 `ICNTL(35)=2`、`ICNTL(37)=0`、`ICNTL(10)=0`、`ICNTL(36)=0`、`ICNTL(38)=600`；`ICNTL(39)` getter 返回 error 62，`ICNTL(49)` 在 trace 中 unsupported。complex128 保持不变。后端控制生效只说明控制到达本机接口，不说明质量或 p6 资格通过。

## 4. 内存、时间与资源

| 口径 | 原 p4 LU / Q1 | 旧 BLR `tau=1e-5` | T1 BLR `tau=1e-3` | 条件 T2 `tau=1e-4` |
|---|---:|---:|---:|---:|
| full process-tree RSS peak | `2,825,973,760 B`（measured） | `2,741,243,904 B`（measured） | `2,672,054,272 B`（measured） | `not_run` |
| factor-live RSS peak | `2,825,973,760 B`（measured） | `2,741,243,904 B`（measured） | `2,672,054,272 B`（measured） | `not_run` |
| RSS ratio to Q1 | `1.0`（derived） | `0.9700174654134085`（derived） | `0.9455339995796705`（derived） | `not_run` |
| native factor entries | `53,417,584`（measured） | `53,040,280`（measured） | `48,706,124`（measured） | `not_run` |
| backend allocated upper | `2,343,000,000 B`（derived upper） | `1,693,000,000 B`（derived upper） | `1,623,000,000 B`（derived upper） | `not_run` |
| backend used upper | `1,382,000,000 B`（derived upper） | `1,420,000,000 B`（derived upper） | `1,351,000,000 B`（derived upper） | `not_run` |
| symbolic factor time | `0.2683213069976773 s`（measured） | `0.33692986499954714 s`（measured） | `0.38182590098585933 s`（measured） | `not_run` |
| numeric factor time | `18.488779414998135 s`（measured） | `19.946495771997434 s`（measured） | `16.59896270200261 s`（measured） | `not_run` |
| full workflow monotonic | `536.4680422439997 s`（measured） | `571.5147310050015 s`（measured） | `571.461267577004 s`（measured） | `not_run` |

Q1 是已接受的原 p4 LU；旧 `1e-5` 是 V16 历史 BLR control；T1 是本轮唯一新控制；T2 没有因为 T1 的 M Gate 失败而运行。RSS/PSS 是完整 parent process-tree 口径，allocated/used 是后端工作数组口径，entries 是原生因子条目，三者不互换。

T1 的阶段时间由 [t1_phase_times.json](../../benchmarks/artifacts/task39extra/p4_blr_tradeoff_v17/root_engineering/t1_phase_times.json) 根据 worker monotonic phase starts 和完整 parent workflow 派生；这些区间互不重叠，不能再把子阶段或单 RHS 时间加回总数。

| T1 phase（derived boundary interval） | seconds |
|---|---:|
| bootstrap | `0.784603432010` |
| preflight | `0.221127939993` |
| setup | `37.430056933998` |
| assembly | `494.343605749004` |
| factor | `17.080374910001` |
| three solves | `3.086461269995` |
| three evaluations | `15.065360085006` |
| cleanup | `3.449677256998` |
| full workflow | `571.461267577004` |

三个 RHS 的 MatSolve、native action/residual 检查、field metric、packet save 和完整 RHS elapsed 分开如下；`native evaluation` 含 native action/residual identity 复核，`elapsed` 还包括保存。

| RHS | MatSolve | native check/evaluation | field metric | packet save | full RHS elapsed |
|---|---:|---:|---:|---:|---:|
| `A2R160_BAL_H_p4_01` | `0.077390685998` | `0.946330134990` | `4.937293752009` | `0.032732592997` | `6.005135503001` |
| `A2R160_BAL_H_p4_02` | `0.072661585989` | `0.944144637004` | `4.945715775000` | `0.046568796999` | `6.013098786003` |
| `LIGHT448_BAL_H_p4_09` | `0.075998251006` | `0.951696522999` | `5.006521974996` | `0.031142690001` | `6.067275527996` |

M Gate 的失败独立于两个证据缺口：`R_peak` 高于 `0.90`，且 `R_live` 也高于 `0.80`。因此即使补齐矩阵内容哈希或坐标格式证据，也不会改变本轮不启动后续路线的决定。

时间记录保持不同口径：full workflow monotonic 为 `571.461267577004 s`，run-summary 基于多个时钟的保守预算 为 `626.1982250330033 s`，V17 结算 ledger settled 为 `626.1990331012247 s`；不能把这些数字相加。MUMPS symbolic/numeric 记录为 `0.38182590098585933 / 16.59896270200261 s`。`time_policy=observe_only` 且 `time_gate_evaluated=false`，因此时间只作记录，未启用时间否决；`14400 s` 仅是保留的参考时长。

连续 parent process-tree 资源证据为 `2224` 个 full samples、`70` 个 live samples；RSS/PSS 可读、tree cap、resident inventory cap、workspace cap、host reserve、zero swap、descendants cleared 和 clean source after 均通过。时间字段保留 `observe_only`，不称为时间 Gate 通过。当前 job swap/global swap delta 为 `0/0`。资源 Gate 通过不等同于 solver quality pass。

旧账本与工程时间保持独立：V14 settled `4082.128437647174 s`；V16 `review_v16_p4_blr` settled `625.736658980034 s`、reserved `14400 s`，旧 V14 ledger SHA 为 `1e3b9c01745fef72f7a794b23e5077508fd65b3951485131d8b639043bd4ecb3`；历史 `600 s` policy debit 是不可返还的 reference-only 占用，旧未独立测得 elapsed 仍为 `unknown`。本轮 V17 是新 batch，settled `626.1990331012247 s`，不覆盖旧账。唯一已有记录的前期工程 UTC span 单列、不并入 PDE ledger：`2026-09-13T23:38:28.248257Z–2026-09-14T00:46:41.889278Z`，由 `t0_existing_evidence.created_unix` 到 `t1_launch_preflight.created_unix` 派生，约 `4093.6410205364227 s`；其中含重叠的 root/Luna 工作与等待，不是 monotonic/CPU。T1 开始前更早准备和 T1 后文档审核没有独立计时，均保持 `unknown`，不把正式计算重复记为工程时间。

最终相关验证：[final_evidence_tests_v17.log](../../benchmarks/artifacts/task39extra/p4_blr_tradeoff_v17/root_engineering/final_evidence_tests_v17.log) 为 **137 passed in 1.23s**，compileall/diff 通过；T1 launch preflight 和 input validate 为 `PASS/valid`；[t1_checker_final_v2.json](../../benchmarks/artifacts/task39extra/p4_blr_tradeoff_v17/root_engineering/t1_checker_final_v2.json) 独立 checker 返回 exit `0`；tiny MUMPS fixed smoke 记录控制/一次 solve 通过。本轮没有单独的 dry-run 证据，不将 dry-run 写成已通过。Ruff、full repository pytest 和 CI 未声称通过。

## 5. 证据缺口与身份边界

### 5.1 严格 slave-zero

checker 按现有合同使用严格相等式 `np.all(x_storage[slave_indices] == 0)`，没有新增未经授权的容差。三个 RHS 都是 `solution_slave_zero=false`，每个有 `4` 个非零 slave storage entries（slave count `4124`）；最大绝对值分别为 `1.1944835754278534e-18`、`2.5375811041732586e-19`、`2.8203945422370365e-18`，相对范数分别为 `1.755971158596816e-20`、`4.0619426974113303e-20`、`2.293194807761172e-20`。

这些是坐标格式/存储契约层面的微小 roundoff gap，不是造成 `rho=4.79/0.19/6.06` 和场指标失败的物理原因。它们使 `all_rhs_evidence=false`，但不改变已经独立成立的 M Gate 失败。

### 5.2 矩阵维度与矩阵内容

当前与 Q1 的 `fe_rows`、`port_rows`、`augmented_rows`、`allocated_nnz` 和 `preallocated_nnz` 均匹配：`matrix_dimensions_match=true`。这只说明维度/预分配结构一致，不称为矩阵数值内容 identity。

当前和历史 Q1 都没有全局 p4 CSR 数值内容字节哈希：

```text
matrix_dimensions_match       = true
matrix_content_hash_available = false
current_content_sha256         = null
baseline_content_sha256        = null
content_hash_comparable        = false
```

输入、reference、g/map、source 和 mode hashes 仍然存在；针对三个冻结向量的 `fresh_A4y_relative_to_saved=0.0` 是有限向量上的 operator-action 复核，不是完整矩阵字节相等证明。当前和 V16 packet 中 `standard_full` 与 `assembly_time_static_condensed` 的显式 `identity_difference` 是同一离散的表示/装配后端差异，已作为既有身份元数据处理，不作为本轮新的 operator error。

checker 的 matrix content gate 只要求新候选自身提供 `matrix.matrix_content_sha256`；Q1 已接受，不因历史 baseline 缺此字段而添加重建条件。本轮 T1 自身也没有该字段，所以该 gate 仍为 false。

## 6. 未运行项与最终行动

以下项目均为 `not_run`，不能写成失败或通过：

- T2/T3/T4，以及任何 p6 outer solve；
- 完整 E/H 场、R/T/A、`A_volume`、零级/高阶衍射和守恒；
- 非可分三维 case、refinement、5 nm/0.7 nm 外推；
- 新 epsilon、BLR 阈值 sweep 或为补齐 metadata 的 replay。

最终 action 是 `T5_CLOSE`：关闭固定 `physical_p4_blr_tradeoff_v17` 路线，保留本轮 p4 negative/control evidence，ordinary solver default 不变。BLR 家族若未来重新研究，必须由新任务重新定义完整质量与内存资格线，不能把本轮 p4 结果升级成 universal claim。

## 7. 证据入口

- [T1 root audit](../../benchmarks/artifacts/task39extra/p4_blr_tradeoff_v17/root_engineering/t1_root_audit.json)
- [T1 final checker v2](../../benchmarks/artifacts/task39extra/p4_blr_tradeoff_v17/root_engineering/t1_checker_final_v2.json)
- [T1 final checker（旧快照，保留）](../../benchmarks/artifacts/task39extra/p4_blr_tradeoff_v17/root_engineering/t1_checker_final.json)
- [T1 initial checker（保留的历史快照）](../../benchmarks/artifacts/task39extra/p4_blr_tradeoff_v17/root_engineering/t1_checker_initial.json)
- [T1 physical summary](../../results/euv_grazing1_phi0/task39extra_v17_t1_blr_tradeoff__full3d_iterative__mpi1__Mna/20260914T004735.607836Z/physical_p4_blr_v17_summary.json)
- [T1 run summary](../../results/euv_grazing1_phi0/task39extra_v17_t1_blr_tradeoff__full3d_iterative__mpi1__Mna/20260914T004735.607836Z/run_summary.json)
- [T1 worker log](../../results/euv_grazing1_phi0/task39extra_v17_t1_blr_tradeoff__full3d_iterative__mpi1__Mna/20260914T004735.607836Z/watchdog/worker.log)
- [compact record](outcomes/records/p4_blr_tradeoff_v17_compact.json)；[decision record](outcomes/records/p4_blr_tradeoff_v17_decision.json)；[run index](outcomes/records/run_index.json)
- [selective merge manifest V18](outcomes/selective_merge_manifest_v18.md)

三份逐 RHS packet JSON/NPZ、原输入与参考、g/output hashes、每次控制读回和实际 ABI 见 compact 的 `rhs_packet_index` 与 `raw_backend_evidence`；全局矩阵内容hash仍为缺失，没有补造。旧 V14 的额外3.1 s保守allowance继续保留，并与600 s未知实耗政策占用分列。

最终文档与Markdown合同本地测试 **20 passed**；证据见[文档测试日志](../../benchmarks/artifacts/task39extra/p4_blr_tradeoff_v17/root_engineering/final_documentation_tests_v17.log)。与137项直接相关测试分列，不称为全仓pytest或CI。
