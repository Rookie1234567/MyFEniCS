# Task39extra V21：非可分 h10 缺口的双层凝聚鲁棒性结果

本报告记录 Review V21 的 A 场：冻结的非可分材料缺口、13.5 nm、Full3D、p6/h10、MPI1。单元凝聚的含义是先在每个有限元单元内消去内部未知量，只把相邻单元共享的 trace 和 80 个端口未知量交给外层迭代，最后再恢复完整三维场；它减少外层问题的规模，但需要保留局部缓存和一个准确的 p4 trace/端口因子。本场只验证这一固定方法在非可分材料分布上的行为，不证明任意三维几何或连续极限收敛。

## 1. 结论和正式身份

| 项目 | A / Z2_NOTCH_H10 |
|---|---|
| 结果 | `PASS`；`MATCHED_REFERENCE_PASS`；official result `true` |
| 模型 | 13.5 nm、Full3D、p6/h10、252 个六面体、MPI1、complex128/int32、80 个 DtN modes |
| profile | `physical_p6_trace_p4_condensed_robustness_v21` |
| 输入 | `input/task39extra/v21_z2_notch_h10.dat`；SHA256 `748e1d685e65447f3dce4effa2744cbb24d7ccedf08ed830f65f624553111e87` |
| 几何身份 | `v21_frozen_notch_h10`；8 个材料单元改变；geometry entity SHA256 `407159b0ac34d163acab5e2a7e9b2d8a1f5d8356c7bb9e7d8cff76c429e1924e` |
| solver source | `863ec3bcd7eead867795284db11fc39e758a6f08` |
| run root | `results/euv_grazing1_phi0/task39extra_v21_z2_notch_h10__full3d_iterative__mpi1__Mna/20260915T053102.148718Z` |
| service | `myfenics-case-20260915T053101-474183.service`；退出码 0；`Result=success`；进程树已清场 |
| 启动命令 | `bash scripts/run_case_in_user_service.sh input/task39extra/v21_z2_notch_h10.dat --v14-time-policy observe_only` |

本场是一次真实 PDE，checker 修复没有重跑 PDE。修复后的代码提交为 `f77393a1eccf0d117d837c8927dcc7aaf314d710`；修复只改变 V21 的 metadata/checker 兼容语义，V20 默认路径保持原行为。

## 2. 尺寸、残差和物理量

| 指标 | A 实测值 | Gate/解释 |
|---|---:|---|
| 外层迭代 | `146` | 真实零初值 FGMRES32 |
| worker terminal explicit true residual | `9.756517234801763e-7` | 通过 `1e-6` |
| independent A6（释放前） | `9.756517234802322e-7` | 通过 |
| independent A6（释放后） | `9.756517234802322e-7` | 与释放前相同，释放不改变结果 |
| field L2 relative | `7.179947262584934e-8` | 通过 `1e-4` |
| scaled-curl relative | `6.541279198551157e-8` | 通过 `1e-4` |
| p6 counts（full / active / interior / appended） | `173802 / 51192 / 113400 / 80` | live dimension identity |
| p4 counts（full / active / interior / appended） | `53084 / 21744 / 27216 / 80` | live dimension identity |
| retained outer rows | `51272` | p6 trace plus 80 ports |
| condensed matrix | `21824 × 21824`，`8184464` NNZ | exact p4 trace/port matrix |

正式 DtN port modal outputs 为：

| 物理量 | 数值 |
|---|---:|
| `R` | `0.3371205735636914` |
| `T` | `0.016288676112780145` |
| `A` | `0.6465907503235284` |
| `A_volume` | `0.6465908230964357` |
| `R00_s` | `0.3370796055078396` |
| `R00_p` | `6.227478652709841e-18` |
| `R00_total` | `0.3370796055078396` |
| `R+T` | `0.3534092496764715` |
| signed `A-A_volume` | `-7.277290725582475e-8` |
| `abs(A-A_volume)` | `7.277290725582475e-8` |
| signed `R+T+A_volume-1` | `7.277290725582475e-8` |
| `abs(R+T+A_volume-1)` | `7.277290725582475e-8` |

80 个通道的有限性、唯一阶次、模态振幅/功率、能量闭合、吸收一致性、E/H 场和 curl 后处理全部通过。官方 `R/T` 来自 `dtn_port_modal_amplitudes`；`A_volume` 来自材料体积上的 `Im(epsilon_r)|E|^2` 积分，不能把两个吸收数混写成同一个测量。与已绑定离散参考的最大 total-power 差为 `8.629595704690018e-8`，模态功率最大绝对差为 `1.58708358677373e-8`，均在 checker 限值内。

同一场还保存了 `BAL_H=147` 次、`H6=147` 次（均包含一次 setup call）和 `p4_mat_solve=294` 次调用。这些是 solver/PC 调用计数，不是外层迭代数；对应来源是 worker summary 的 `solver.actual_pc_counts_including_one_setup_call`。p4 后端分开记录 `factor_infog19` allocated upper `1463000000 B`、`factor_infog22` used upper `838000000 B`、matrix payload `232205060 B`、preallocated structural NNZ `11605888`、used matrix NNZ `8184464` 和 retained numeric cache `11327040 B`。p6 释放前的 unique NumPy cache payload 为 `183282224 B`，content identity 为 `c79e781afb4b866db0e38bcaafd92d80f8148c847e1de6bec594ebc4994db62e`。这些 backend/inventory 数字是独立账本，不能冒充同时进程树 RSS。

## 3. 资源峰值和时间口径

资源峰值是连续 watchdog 同时采样的 dedicated parent process tree，包含 compiler descendant；RSS/PSS 是整棵树的同时峰值，不能把各阶段相加。四个阶段窗口与全过程窗口有重叠，因此下表用于定位峰值来源，不是加总账。

| 阶段 | RSS 峰值 (B) | PSS 峰值 (B) | 峰值采样时刻距 workflow 起点 (s) | 样本数 |
|---|---:|---:|---:|---:|
| preparation before factor | `826789888` | `796558336` | `48.66945533701801` | `192` |
| factor / H6 / p6 cache setup | `2136825856` | `2106627072` | `235.08752146700863` | `725` |
| iteration / final residual | `2204024832` | `2173793280` | `1635.4865249750146` | `5392` |
| release / recovery / postprocess | `2297982976` | `2267706368` | `1646.631635007012` | `42` |
| full watchdog sampling window | `2297982976` | `2267706368` | `1646.631635007012` | `6351` |

同一资源 authority 还记录：inventory peak `2013567110 B`、workspace peak `423441224 B`、swap peak `0 B`、tree cap `8589934592 B`、reserve `4294967296 B`，source-clean、readability、reserve、workspace/tree cap、zero-swap 和 cleanup gates 均通过。inventory 和 workspace 是分开的账本，不能当作 RSS 的组成项直接相加。

上表的时间列只是“该阶段窗口中峰值样本出现时，距 workflow 起点经过了多久”；它不是该阶段持续时间，阶段窗口也不能相加。全过程 watchdog 采样窗口与 formal workflow ledger 的起止定义不同，因此 `1646.631635007012 s` 也不能替换下面的 full workflow monotonic。

时间也分开报告：

| 时间范围 | 数值 |
|---|---:|
| full workflow monotonic | `1648.8478095369937 s` |
| KSP solve monotonic | `1394.9292688659916 s` |
| formal ledger conservative billing | `1798.8260412538452 s` |
| UTC - monotonic observed discrepancy | `149.97472047501856 s` |

conservative billing 是保守计费/审计口径，不是 measured runtime；workflow、KSP 和 conservative billing 不相加，也不互相替代。

## 4. p6 cache 释放合同

V21 原始事件使用 label `v21_p6_local_caches`，释放了 `183282224 B`，与 reserve 完全相等；owner references cleared，释放发生在 final explicit residual 之后，最终 inventory used 为 `0 B`。checker 的 V20 helper 仍使用 `v20_p6_local_caches`，因此修复后的 checker 在内存中建立精确 label alias，并直接对原始事件检查 reserve/release 字节相等、owner 清理和释放顺序；原始 `v21_events.jsonl` 没有被改写。`z2_root_preserved_raw_and_negative_audit.json` 进一步核对原始 summary、events、final residual NPZ、manifest、ledger 和原始 failed checker copy 未被覆盖。

## 5. 原始 checker 负结果与修复语义

修复前的 checker copy 保留在：
`results/euv_grazing1_phi0/task39extra_v21_z2_notch_h10__full3d_iterative__mpi1__Mna/20260915T053102.148718Z/v21_checker_result.original_failed.json`，SHA256 为 `93a7a7663ad3df38a5cea75449d550d0cdcd29ee613feef54e42b7d0718d8f94`。它只失败两项：

1. `release_timeline`：原始 V21 label 被旧 V20 helper 按错误 label 解释；修复后保留 raw rows，helper 只接收 in-memory alias，并增加 V21 raw event 的严格直接检查。
2. `summary_schema`：历史 V14 `record.update` 覆盖了 V21 adapter 原本要写的 native schema。V21 wrapper 现在通过 opt-in 恢复 native schema；对已经完成且不可覆盖的 A 原始记录，checker 只在精确的 source SHA、stage、profile 和 observed schema 范围内应用历史兼容，并明确记录 `native_pass=false`，不把 raw V14 schema 改名为 V21 native schema。

当前 checker source SHA256 为 `acbad332f35ccf3302fb027335b93ed399941c2a937012c86f2cc51f3beabcb6`；current/recheck checker SHA256 均为 `149747de773e9cded62898195cc4b1e58d0714cf691e5b7b7c20316619590bce`，65/65 checks 通过，`errors=[]`，`evidence_valid=true`。修复测试的更正路径结果为 `49 passed`；没有用 `--no-verify` 绕过提交检查，也没有修改共享 hook/config。

## 6. B/C 范围边界

在 A compact 记录时：

| 场 | 状态 | 启动条件 |
|---|---|---|
| B / `Z3_ORIGINAL_H7P5` | `not_run` | A 的 residual/physics/resource Gate 已通过；需先完成 A evidence commit 和 B 的实际资源预审，再按原始 `v21_z3_original_h7p5.dat` 启动 |
| C / `Z4_NOTCH_H7P5` | `not_run` | 只有 B 的可适用求解/一致性 Gate 和资源预审通过后，才使用同一 h7.5 网格与冻结缺口启动 |

`not_run` 不是数值失败，也不能从 A 的 2.30 GB RSS 线性外推 h7.5 资源。B/C 不共享不同材料矩阵的 LU、不用前一场解初始化、不切换 PC、不暗中改用更粗网格。普通默认保持不变，V21 仍是有限的 13.5 nm research validation。

## 7. 机器可读证据

- [V21 compact](records/dual_condensed_robustness_v21_compact.json)
- `results/.../physical_dual_condensed_robustness_v21_summary.json`：原始 worker summary
- `results/.../v21_checker_result.json`：当前 65/65 checker
- `results/.../v21_checker_result.recheck.json`：独立 recheck
- `benchmarks/artifacts/task39extra/dual_condensed_robustness_v21/root_engineering/z2_root_metadata_recheck.json`
- `benchmarks/artifacts/task39extra/dual_condensed_robustness_v21/root_engineering/z2_root_preserved_raw_and_negative_audit.json`
- `benchmarks/artifacts/task39extra/dual_condensed_robustness_v21/root_engineering/z2_root_completed_result_audit.json`

大量场、矩阵、完整时间线和 raw event 保留在 ignored artifact；tracked compact 只保存审阅所需的 hash-bound identity、数值、资源口径和边界。
