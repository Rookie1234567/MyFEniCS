# p4 BLR tradeoff V17：T1 数值与内存 Gate 负结果

## 1. 状态摘要

本 outcome 记录 review V17 要求的 T1 control。BLR（块低秩）把消元因子中的部分数值块用低秩表示，目标是减少因子存储；它仍然需要全局因子分解和回代，不是 factor-free 迭代预条件器。

| 项目 | 结果 |
|---|---|
| T1 worker status | `finished`；wrapper `WORKER_FAILED`，exit `4` |
| 数值语义 | `T1_BLR_CONTROL_REJECTED` / `NUMERICAL_GATE_REJECTED` |
| Q：p4 quality | `false` |
| M：RSS memory | `false`；`R_peak=R_live=0.9455339995796705` |
| T5 decision | `T5_CLOSE` |
| fresh/replay | `1 / 0` |
| T2/T3/T4 | `not_run` |

`WORKER_FAILED` 是 worker 在数值控制拒绝后返回 exit 4 的通用包装标签；本场没有 OOM 或 MPI 失联。时间策略保持 `observe_only`，不启用时间否决。连续资源 Gate 通过，但资源通过不覆盖质量 Gate 失败。

## 2. 实验身份与比较边界

| 字段 | T1 candidate | Q1 accepted baseline |
|---|---|---|
| requested base SHA | `863c71d5133b137a888a587becb9cbe8ed2daca` | review 指定的完整 base |
| source SHA | `a1bc6b54e613ebf91c5c97ecddcc14555b084ee0` | T1 formal source |
| accepted Q1 source SHA | `6a8b273c383d5bd9da37d6630a48bd24d6a90cce` | Q1 已接受，复用其已存身份，本轮不重跑 |
| input | `v17_t1_blr_tradeoff.dat`；`6cb39581bb78572466f05cab0a49b8fd8705ff5e223aaf0d4c870da1751a37c7` | `v14_q1_full_direct` run |
| physical SHA | `9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f` | 同一物理模型身份 |
| formal model | 13.5 nm、Full3D、形式 p6/h10、80 DtN modes、MPI1、complex128/int32 | 同一比较族 |
| actual solve | p4 增广 control；一个 factor、每 RHS 一次 MatSolve | p4 direct accepted reference |
| run path | `results/euv_grazing1_phi0/task39extra_v17_t1_blr_tradeoff__full3d_iterative__mpi1__Mna/20260914T004735.607836Z` | `results/euv_grazing1_phi0/task39extra_v14_q1_full_direct__full3d_iterative__mpi1__Mna/20260913T115722.489252Z` |

形式模型仍写 p6/h10，但 T1 的数值控制只覆盖 p4 增广矩阵；不能从这个 control 推断 p6 outer residual 或完整 Maxwell 结果。

## 3. RHS 质量证据

本轮门槛为 `rho<=0.5`、field L2 `<=0.25`、scaled-curl `<=0.25`。`rho` 表示原始 A4 方程回代后剩余的不平衡，field L2 表示场的相对误差，scaled-curl 表示空间旋度相关的相对误差。

| RHS | rho | field L2 | scaled-curl | native identity relative | MatSolve delta | 质量 |
|---|---:|---:|---:|---:|---:|---|
| `A2R160_BAL_H_p4_01` | `4.78774161579983` | `0.6042973308874857` | `0.6037676857908261` | `2.097189693808333e-16` | `1` | failed |
| `A2R160_BAL_H_p4_02` | `0.1947573245406759` | `0.6822411297187286` | `0.6817077538074453` | `1.1217099246371649e-17` | `1` | failed |
| `LIGHT448_BAL_H_p4_09` | `6.063573601898471` | `0.6205385284813106` | `0.6201228657608676` | `1.4775796590641492e-16` | `1` | failed |

三份 packet 的原 A4 action/residual identity 均在 `1e-10` 限值内；真实 identity 相对误差范围为 `1.1217099246371649e-17–2.097189693808333e-16`。这证明保存的回代代数路径自洽，但不能代替 field quality。总体 `quality_pass=false`：`finite`、三 RHS 和 identity 通过，`rho`、field L2、scaled-curl 失败；`rho` 范围为 `0.1947573245406759–6.063573601898471`，场 L2 范围为 `0.6042973308874857–0.6822411297187286`。

## 4. BLR 存储与控制事实

| 原生字段/派生量 | 值 | 口径 |
|---|---:|---|
| BLR fronts | `33` | 原生统计 |
| BLR coverage | `49.0%` = fraction `0.49` | 不把百分比写成无单位的 `49` |
| `INFOG(29)` theoretical entries | `53,417,584` | 理论条目 |
| `INFOG(35)` effective entries | `48,706,124` | 有效条目 |
| `INFOG(9)` actual storage entries | `48,706,124` | 实际存储条目 |
| effective/theoretical ratio | `0.9117994554003042` | 派生；条目减少 `8.82005446%` |
| `RINFOG(3)` / `RINFOG(14)` | `39,449,025,878 / 29,823,939,778` | theoretical/effective operations |
| max front / delayed pivots | `1592 / 0` | 原生字段 |
| off-diagonal pivots / memory compress | `81 / 0` | 原生字段 |
| allocated / used upper | `1,623,000,000 / 1,351,000,000 B` | 后端工作数组，不是 RSS |

本场控制读回：`ICNTL(35)=2`、`ICNTL(37)=0`、`ICNTL(10)=0`、`ICNTL(36)=0`、`ICNTL(38)=600`，BLR `CNTL(7)=1e-3`；`ICNTL(39)` getter error 62，`ICNTL(49)` trace unsupported。complex128 未改变。压缩比只由 `INFOG/RINFOG` 原生字段计算，不由 `ICNTL(38)` 推断。

## 5. 四路对照、内存 Gate 与时间

| 口径 | 原 p4 LU / Q1 | 旧 BLR `tau=1e-5` | T1 BLR `tau=1e-3` | 条件 T2 `tau=1e-4` |
|---|---:|---:|---:|---:|
| full RSS peak | `2,825,973,760 B`（measured） | `2,741,243,904 B`（measured） | `2,672,054,272 B`（measured） | `not_run` |
| factor-live RSS peak | `2,825,973,760 B`（measured） | `2,741,243,904 B`（measured） | `2,672,054,272 B`（measured） | `not_run` |
| RSS ratio to Q1 | `1.0`（derived） | `0.9700174654134085`（derived） | `0.9455339995796705`（derived） | `not_run` |
| native factor entries | `53,417,584`（measured） | `53,040,280`（measured） | `48,706,124`（measured） | `not_run` |
| backend allocated upper | `2,343,000,000 B`（derived upper） | `1,693,000,000 B`（derived upper） | `1,623,000,000 B`（derived upper） | `not_run` |
| backend used upper | `1,382,000,000 B`（derived upper） | `1,420,000,000 B`（derived upper） | `1,351,000,000 B`（derived upper） | `not_run` |
| symbolic factor time | `0.2683213069976773 s`（measured） | `0.33692986499954714 s`（measured） | `0.38182590098585933 s`（measured） | `not_run` |
| numeric factor time | `18.488779414998135 s`（measured） | `19.946495771997434 s`（measured） | `16.59896270200261 s`（measured） | `not_run` |
| full workflow monotonic | `536.4680422439997 s`（measured） | `571.5147310050015 s`（measured） | `571.461267577004 s`（measured） | `not_run` |

Q1 是已接受的原 p4 LU；旧 `1e-5` 是 V16 历史 BLR control；T1 是本轮唯一新控制；T2 因 T1 的 M Gate 失败而未运行。allocated/used 是后端工作数组，entries 是原生因子条目，RSS 是完整 parent process-tree 驻留，不能互换。

T1 完整阶段边界由 [t1_phase_times.json](../../../benchmarks/artifacts/task39extra/p4_blr_tradeoff_v17/root_engineering/t1_phase_times.json) 派生；阶段互不重叠，不能再把子阶段或单 RHS 时间加回总数：

| T1 phase | derived seconds |
|---|---:|
| bootstrap / preflight | `0.784603432010 / 0.221127939993` |
| setup | `37.430056933998` |
| assembly | `494.343605749004` |
| factor | `17.080374910001` |
| three solves / three evaluations | `3.086461269995 / 15.065360085006` |
| cleanup | `3.449677256998` |
| full workflow | `571.461267577004` |

三个 RHS 的 MatSolve、native action/residual 检查、field metric、packet save 和 full RHS elapsed：

| RHS | MatSolve | native check/evaluation | field metric | packet save | full RHS elapsed |
|---|---:|---:|---:|---:|---:|
| `A2R160_BAL_H_p4_01` | `0.077390685998` | `0.946330134990` | `4.937293752009` | `0.032732592997` | `6.005135503001` |
| `A2R160_BAL_H_p4_02` | `0.072661585989` | `0.944144637004` | `4.945715775000` | `0.046568796999` | `6.013098786003` |
| `LIGHT448_BAL_H_p4_09` | `0.075998251006` | `0.951696522999` | `5.006521974996` | `0.031142690001` | `6.067275527996` |

M 规则为 `R_peak<=0.90`，或 `R_live<=0.80 且 R_peak<=1.05`。T1 的两个 RSS ratio 均不满足，因此 `memory_pass=false`。这是独立于矩阵内容哈希和 slave-zero 证据缺口的负结果。

时间方面，T1 full workflow monotonic 为 `571.461267577004 s`；conservative run-summary budget 为 `626.1982250330033 s`；V17 ledger settled 为 `626.1990331012247 s`。MUMPS symbolic/numeric 为 `0.38182590098585933 / 16.59896270200261 s`。资源记录有 `2224` full samples 与 `70` live samples；RSS/PSS、tree/inventory/workspace/host reserve、zero swap、descendant cleanup 和 clean-source-after 全部通过。时间策略是 `observe_only`、`time_gate_evaluated=false`，只记录观察值，不启用时间否决；记录区间未触发 `14400 s` 上限。

旧账本与工程时间单列：V14 settled `4082.128437647174 s`；V16 `review_v16_p4_blr` settled `625.736658980034 s`、reserved `14400 s`、`unique_bug_replay_count=0`；旧 V14 ledger SHA `1e3b9c01745fef72f7a794b23e5077508fd65b3951485131d8b639043bd4ecb3` 和历史 `600 s` policy debit 只读保留，旧未独立测得 elapsed 仍为 `unknown`。V17 新 batch settled `626.1990331012247 s`，不改写旧账。唯一已有记录的前期工程 UTC span 为 `2026-09-13T23:38:28.248257Z–2026-09-14T00:46:41.889278Z`，由 T0 existing-evidence 与 T1 launch-preflight 创建时间派生，约 `4093.6410205364227 s`；其中含重叠 root/Luna 工作与等待，不是 monotonic/CPU，不并入 PDE ledger。T1 开始前更早准备和 T1 后文档审核未独立计时，保持 `unknown`。

相关最终验证为 `final_evidence_tests_v17.log`：**137 passed in 1.23s**，compileall/diff 通过；T1 launch preflight、input validate 为 `PASS/valid`；本轮没有单独 dry-run 证据，不将 dry-run 写成已通过；final checker v2 exit `0`；tiny MUMPS fixed smoke 通过控制/一次 solve 检查。Ruff、full repository pytest 和 CI 未声称通过。

## 6. 证据合同与身份说明

### 6.1 slave-zero

checker 使用严格的 `np.all(x_storage[slave_indices] == 0)`。T1 三个 RHS 都为 `solution_slave_zero=false`，每个有 `4` 个非零 slave entries（slave count `4124`）；最大绝对值分别为 `1.1944835754278534e-18`、`2.5375811041732586e-19`、`2.8203945422370365e-18`，相对范数分别为 `1.755971158596816e-20`、`4.0619426974113303e-20`、`2.293194807761172e-20`。这是已有坐标格式/存储尾项，不能用未经批准的容差改判，也不能用约 `1e-18` 尾项解释 `0.6` 量级的场失败。它使 `all_rhs_evidence=false`，但不是本轮根因；M Gate 已独立失败。

### 6.2 矩阵维度与内容哈希

当前 checker 把两类证据分开：`fe_rows`、`port_rows`、`augmented_rows`、`allocated_nnz` 和 `preallocated_nnz` 全部匹配，所以 `matrix_dimensions_match=true`；但当前和 Q1 都没有全局 p4 CSR 数值内容字节哈希：

```json
{
  "matrix_dimensions_match": true,
  "matrix_content_hash_available": false,
  "current_content_sha256": null,
  "baseline_content_sha256": null,
  "content_hash_comparable": false
}
```

输入/reference/g/map/source/mode hashes 和三个冻结向量的 `fresh_A4y_relative_to_saved=0.0` 仍是有效证据，但 finite-vector operator action 不等于完整矩阵内容相等。当前及 V16 packet 的 `standard_full` / `assembly_time_static_condensed` 是既有同离散表示差异，不作为新的 operator error。

checker 的 candidate matrix-content gate 只检查新候选是否提供自身 hash；Q1 已接受，不因其历史记录缺 hash 而要求重建基线。本轮 T1 自身缺 hash，因此该 gate 为 false。

## 7. 未运行项与 T5 决定

`T2/T3/T4`、p6 outer、E/H、R/T/A、`A_volume`、80 modes、衍射、守恒、非可分 case、refinement、5 nm/0.7 nm 外推和新的 epsilon sweep 均为 `not_run`。不把“未运行”写成算法失败，也不把 p4 control 写成完整 Maxwell 通过。

决定：`T5_CLOSE`，关闭这个固定 BLR 阈值/配置；保留负结果、raw factor fields、RHS packets、资源和 checker evidence，ordinary solver default 不变。BLR 家族没有被本场 universal disproval；若未来重开，必须由新任务给出独立的完整质量和内存证据。

## 8. 证据索引

| 证据 | 路径 | SHA256 |
|---|---|---|
| root audit | `benchmarks/artifacts/task39extra/p4_blr_tradeoff_v17/root_engineering/t1_root_audit.json` | `5ce16cf81a2be39647089a51ca2b2d0bc647660a1162273134aef4a33104690c` |
| final checker v2 | `benchmarks/artifacts/task39extra/p4_blr_tradeoff_v17/root_engineering/t1_checker_final_v2.json` | `63327177a9b9cacf6b5f40dfb28df9b8071b207a8079011c37516de2b8616b4f` |
| final checker old snapshot | `benchmarks/artifacts/task39extra/p4_blr_tradeoff_v17/root_engineering/t1_checker_final.json` | `0a547297acf2ec3181ea5a375f5babbbedbb3aa8267676dba81883409b1f8a56` |
| initial checker snapshot | `benchmarks/artifacts/task39extra/p4_blr_tradeoff_v17/root_engineering/t1_checker_initial.json` | `707925b3a70318a0369fa229f03293a9592a99eb24208e3d943fab3b334b3bcc` |
| T1 summary | `results/euv_grazing1_phi0/task39extra_v17_t1_blr_tradeoff__full3d_iterative__mpi1__Mna/20260914T004735.607836Z/physical_p4_blr_v17_summary.json` | summary hash `330f2549283e971d6136b687da61526646bf86abc90fd1b651986a4a9441a5b1` |
| run manifest | `results/euv_grazing1_phi0/task39extra_v17_t1_blr_tradeoff__full3d_iterative__mpi1__Mna/20260914T004735.607836Z/run_manifest.json` | `37f206dd4f2cbfc2c87c12e978b00534a9997af1bdb9b43bd82d3b38ac8cb1ef` |
| run summary | `results/euv_grazing1_phi0/task39extra_v17_t1_blr_tradeoff__full3d_iterative__mpi1__Mna/20260914T004735.607836Z/run_summary.json` | `42eaf4135090a2b3dfbb8c7abb568ab262e45850a464fdcbf290c941c0116cf7` |
| parent resources | `results/euv_grazing1_phi0/task39extra_v17_t1_blr_tradeoff__full3d_iterative__mpi1__Mna/20260914T004735.607836Z/watchdog/resources.jsonl` | `9b4d367195fcb4d23d9b676a5e1fb433b1e01ffcad1c70d94f39c70317a4b5ca` |
| event stream | `results/euv_grazing1_phi0/task39extra_v17_t1_blr_tradeoff__full3d_iterative__mpi1__Mna/20260914T004735.607836Z/v17_events.jsonl` | `856e92fc3f4961a36b60ee1d034963746d31f6d30d2cfd36ecd4c4fd4e910644` |
| worker resources | `results/euv_grazing1_phi0/task39extra_v17_t1_blr_tradeoff__full3d_iterative__mpi1__Mna/20260914T004735.607836Z/v17_worker_resources.jsonl` | `5cecee7a76aed9b8581b6bcf5775b62f40f847b30d077c94eff41f49a5fbed77` |
| final evidence tests | `benchmarks/artifacts/task39extra/p4_blr_tradeoff_v17/root_engineering/final_evidence_tests_v17.log` | `6fb46b927b7cc999b2d5ea4f0b02d73886a33d7297f2d25c3b0971149fee1ffb` |

相关 compact/decision、run index 和 V18 selective-merge boundary 见同目录记录。

三份逐 RHS packet JSON/NPZ、原输入与参考、g/output hashes、每次控制读回和实际 ABI 见 compact 的 `rhs_packet_index` 与 `raw_backend_evidence`；全局矩阵内容hash仍为缺失，没有补造。旧 V14 的额外3.1 s保守allowance继续保留，并与600 s未知实耗政策占用分列。
