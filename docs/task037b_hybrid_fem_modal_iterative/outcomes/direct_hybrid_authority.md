# Task037b H1 direct Hybrid authority

## 首次 formal（3f72ef3）

H1 的唯一 MPI8 formal 在生成 Hybrid 解之前停止。停止点是 mode classification（模式分类）：程序先求横截面模态，再按传播常数和耦合关系把接近的模态分成块；这一步用于确定后续界面方程的模态基底，还没有组装或求解当前 Hybrid 线性系统。因此本结果不是 Hybrid 物理负结果，也不是 H1 数值 Gate 失败，而是当前源码 direct authority 尚未建立的 inherited correctness regression。

| 项目 | 实测结论 |
|---|---|
| H1 状态 | failed_before_solve / controlled_stop |
| formal return code | 1 |
| classification | inherited correctness regression |
| current clean source | 3f72ef3eb4f3002246802af30ef7bca6b0080888 |
| ordinary defaults | unchanged |
| H1 入口 | explicit opt-in，仅由 task037b-h1-gate 启用 |
| 是否生成 Hybrid 解 | 否 |
| 是否判定 H1 数值 Gate | 否，所需数值尚未生成 |

## 身份与 preflight

| 项目 | 值 |
|---|---|
| branch | codex/20260807-task37b-hybrid-iterative-development |
| HEAD/upstream | 3f72ef3eb4f3002246802af30ef7bca6b0080888 |
| ahead/behind | 0/0 |
| worktree | clean |
| qualified activation | _MYFENICS_WSL_QUALIFIED_ACTIVATION=1 |
| Python | /home/Projects/MyFEniCS/.venv/bin/python |
| PETSc | complex128 / int32 |
| ABI | petsc4py、slepc4py、DOLFINx、mpi4py 同一 Linux 栈 |
| Full3D pinned record | /home/Projects/MyFEniCS/benchmarks/artifacts/task035c_hybrid_channel_memory/p6_h10_full_static_mpi8_244b62e.json |
| Full3D record SHA256 | b8b428476cdeb4b80495f4a8b1c89e3bb2f67c682c695fc72bb59dbbbd94b4e3 |
| historical preflight authority SHA256 | 96ac3949efc236393d4c2dbc6e1fa334ad5ccb0e9796bdeba13fbe0515577dd8 |
| pinned reference gate | pass；reference source=244b62e1fb4f299a468363cf90a2dd548dc34ff6；current source=3f72ef3eb4f3002246802af30ef7bca6b0080888 |
| run directory before launch | absent |
| other heavy worker before launch | none observed |

## 唯一 formal command

实际执行的是下列 qualified parent command；没有增加外层 timeout 或第二实例：

~~~bash

python -m benchmarks.run_task033_memory_watchdog --target hybrid --case-label task037b_h1_direct_hybrid_p6_h10_m120_augmented_mpi8 --degree 6 --h-nm 10 --modal-degree 6 --modal-h-nm 10 --mpi-size 8 --requested-modes 120 --candidate-modes 240 --solver-path augmented --comparison-solver-path fast --stage4-full3d-assembly-backend assembly_time_static_condensed --bottom-interface-nm 10 --top-interface-nm 110 --incident-grazing-deg 10 --polarization-kind s --internal-propagation-model full3d_uniform_cg --internal-traction-model scalar_cg_discrete_derivative --full3d-reference /home/Projects/MyFEniCS/benchmarks/artifacts/task035c_hybrid_channel_memory/p6_h10_full_static_mpi8_244b62e.json --full3d-reference-sha256 b8b428476cdeb4b80495f4a8b1c89e3bb2f67c682c695fc72bb59dbbbd94b4e3 --task037b-h1-gate --task035c-p6-preflight-authority benchmarks/cases/095_high_order_local_hp_resource_envelope/records/global_hexa_p1_p6_h10_p6_assembly_time_condensed_independent_mpi8.json --task035c-p6-preflight-sha256 96ac3949efc236393d4c2dbc6e1fa334ad5ccb0e9796bdeba13fbe0515577dd8 --verified-clean-sha 3f72ef3eb4f3002246802af30ef7bca6b0080888 --warning-gib 12 --terminate-gib 16 --timeout-seconds 1800 --poll-interval 0.25 --run-dir benchmarks/artifacts/task037b/h1_direct_authority_3f72ef3_mpi8 --summary-output benchmarks/artifacts/task037b/h1_direct_authority_3f72ef3_mpi8.json --container-image myfenics-stage4:task28 --container-digest sha256:08c61b2cde742442b0031437dbc5160db979494587e6b6364f7935beb29dd76d --host-environment-id WSL2-Ubuntu-24.04

~~~

## 精确异常

| 字段 | 实际值 | 含义 |
|---|---:|---|
| exception | NearDegenerateBlockPartitionSplitError | 近简并模态块被判定为跨分组切分 |
| indices | [50, 52] | 触发检查的模态索引 |
| group_ids | [17, 18] | 两个相邻分组 |
| relative beta distance | 1.580086e-06 | 两模态传播常数的相对距离 |
| identity row norm | 1.024637e-06 | 联合归一化后的行误差 |
| identity max entry | 6.572908e-07 | 恒等性偏差的最大单项 |
| cross-block max | 6.572908e-07 | 跨块耦合最大项 |
| limit | 1.000000e-06 | 当前冻结的分组检查限值 |

异常位置是 src/modes/mode_classification.py 的 build_biorthogonal_mode_basis。MPI8 的各 rank 均在同一检查处退出；没有进入 block solve、recovery、RTA 或 Hybrid field postprocess。

## 未观测字段

下表中的 not_observed 表示程序在停止点尚未生成，不代表数值为零。

| 类别 | H1 字段 | 状态 |
|---|---|---|
| H1 telemetry | rows、hashes、RTA wall、recovery wall | not_observed |
| residual | combined、bottom/top FE、modal equation | not_observed |
| fields | interface E/H、selected middle-plane E/H | not_observed |
| physical Gate | 12/12 powers、12/12 amplitudes、R/T/A、A_volume closure | not_run |
| storage | rows、block shapes、matrix NNZ、factor NNZ、inventory | not_observed |
| official result | Hybrid official result | not_run |

## 证据入口

生成文件位于 Git ignored artifact 目录；它们不会提交到 Git。tracked docs 只保存以下 hash-bound 引用。

| 证据 | 相对路径 | SHA256 |
|---|---|---|
| watchdog summary | ../../../benchmarks/artifacts/task037b/h1_direct_authority_3f72ef3_mpi8.json | 2e03dd105665de6a7ad9d796de7dad7117cf803483d0ad4de8da6dd2480b246b |
| worker stdout / traceback | ../../../benchmarks/artifacts/task037b/h1_direct_authority_3f72ef3_mpi8/worker_stdout.txt | eb03b75b5fba69bcf8e0304903d95b98286ac2756916749180cde99d851fe28e |
| memory timeline | ../../../benchmarks/artifacts/task037b/h1_direct_authority_3f72ef3_mpi8/memory_timeline.csv | 79ed75dfd7b57fbbc20f9ff0e73749fbfa52ce1d694c2760d6ddf82239418259 |
| memory stages | ../../../benchmarks/artifacts/task037b/h1_direct_authority_3f72ef3_mpi8/memory_stages.jsonl | 4e35d04896a04d1640438afa0b8241af0a765a3c093b238b464ad7a1dae4193e |

## Post-fix recovery（2990f357）

首次 failed-before-solve 证据完整保留在上文。提交 `2990f357f7dec23b1713bd0088bdc43c3ce6f5bc` 的最小修复针对 near-degenerate grouping：原分组使用单项 cross-entry 判据，而最终 partition audit 使用整行 infinity norm；本次累计 row norm 超过 `1e-6`、单项仍低于 `1e-6`，因此修复为让 audit 识别该近简并候选并进入既有 joint inverse。只修改 `src/modes/mode_classification.py` 与 `src/test/test_hybrid_interface_audits.py`，保留 `1e-6`、fail-closed、ordinary defaults，未加入 fallback、retry 或参数放宽。

| 项目 | post-fix 实测结论 |
|---|---|
| clean source | 2990f357f7dec23b1713bd0088bdc43c3ce6f5bc |
| formal return code / status | 0 / measured_shard_pass |
| numeric_pass / formal_pass | true / true |
| task.md §9 H1 contract | pass；12+12 离线 frozen-reference 与 pairwise Gate 均通过 |
| true relative residual | 1.4476013948489319e-12 |
| ordinary defaults | unchanged；H1 仍为 explicit opt-in |
| runner legacy qualification labels | physical_qualified=false、official_record=false、mode_count_converged=false；均为 wider-M funnel 旧语义，不是 §9 Gate |

### 规模、残差与物理量

| 项目 | 值 |
|---|---:|
| bottom/top active FE rows | 8424 / 8424 |
| bottom/top external auxiliary rows | 40 / 40 |
| modal / monolithic rows | 240 / 17168 |
| A bottom/top shape | 8464×8464 / 8464×8464 |
| H modal shape | 240×240 |
| monolithic shape | 17168×17168 |
| bottom/top matrix NNZ | 6156616 / 6156616 |
| monolithic matrix NNZ | 13275040 |
| raw MUMPS factor inventory | 38228288；corrected factor field未记录 |
| bottom/top linear residual | 2.217517714438115e-12 / 2.756875606005327e-12 |
| bottom/top reduced trace residual | 7.612207925033064e-12 / 1.7450617129678293e-11 |
| bottom/top eliminated_cell_interior_residual_norm | 1.4416873713070796e-11 / 1.835950866149264e-11 |
| bottom/top eliminated_cell_interior_residual_max_abs | 8.079363541737419e-13 / 1.1215848498085163e-12 |
| interface E projection | 8.689613737899368e-14 / 1.3711486801729823e-13；combined 1.1803680423250176e-13 |
| interface FE modal traction | 1.3956291020194492e-12 / 1.1849798723729077e-12 |
| R / T / A_volume | 0.0007628814751371221 / 0.6027016339839382 / 0.39653548469640243 |
| R+T+A_volume / closure error | 1.0000000001554779 / 1.5547785281455617e-10 |

Full3D trace/modal oracle 的 bottom/top E/H 相对误差分别为 `7.52052133793954e-8 / 1.2196894714705457e-6` 与 `8.170263279994799e-8 / 1.240069510894507e-6`；三个内部 middle planes（30/60/90 nm）的最大 E/H 相对误差为 `1.304018552352566e-11 / 4.168950680099725e-6`，均保持 runner 已记录的 physical field Gate pass。

### Frozen reference 12+12 Gate

authority 是 tracked `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/significant_channel_reference_v1.json`，SHA256 为 `83b7bcfeb510b849aea391d86f306072ead0232781598ea1232617e2535293e3`。通道身份为 `(side,m,n,polarization)`，振幅字段为 `outgoing_amplitude_at_boundary`；下表的 limit 是 reference 每通道 `unchanged_v0_acceptance_gate` 原值。

| channel | current/ref power | abs error / limit | current/ref boundary amplitude | abs error / limit | result |
|---|---|---:|---|---:|---|
| T(-7,0)_s | 2.362010448901861e-6 / 2.362010449239990e-6 | 3.381292e-16 / 2.158694e-9 | (9.812210507731e-4,-8.723749949e-5) / (9.812210508339e-4,-8.723749960195e-5) | 1.277111e-13 / 1.216565e-5 | P/P |
| T(-5,0)_s | 2.119208255831642e-7 / 2.119208257204448e-7 | 1.372806e-16 / 3.891273e-10 | (1.340326965309e-4,1.470057842678e-4) / (1.340326966068e-4,1.470057842858e-4) | 7.800241e-14 / 1.280646e-6 | P/P |
| T(-4,0)_s | 4.372888972120204e-7 / 4.372888972066230e-7 | 5.397347e-18 / 5.251003e-10 | (-2.621322075341e-4,8.743226903351e-5) / (-2.621322075309e-4,8.743226903754e-5) | 5.104668e-15 / 2.541658e-6 | P/P |
| T(-2,0)_s | 2.959841395285020e-6 / 2.959841395129147e-6 | 1.558731e-16 / 4.650806e-9 | (-6.970027805954e-4,2.979420806841e-4) / (-6.970027805581e-4,2.979420807207e-4) | 5.224063e-14 / 4.580806e-6 | P/P |
| T(-1,0)_s | 2.178167398509359e-5 / 2.178167398554683e-5 | 4.532473e-16 / 1.114414e-7 | (2.091013385256e-3,-1.023379862885e-3) / (2.091013385303e-3,-1.023379862844e-3) | 6.223770e-14 / 1.272899e-5 | P/P |
| T(0,0)_s | 0.602673872344789 / 0.602673872346967 | 2.177813e-12 / 2.175766e-4 | (0.631378703346,0.473020981039) / (0.631378703348,0.473020981038) | 2.089616e-12 / 6.779629e-3 | P/P |
| R(-7,0)_s | 6.263542426012344e-7 / 6.263542422224734e-7 | 3.787611e-16 / 1.249444e-9 | (-5.052091113880e-4,-2.608886193815e-5) / (-5.052091112471e-4,-2.608886170068e-5) | 2.761221e-13 / 7.995039e-7 | P/P |
| R(-5,0)_s | 7.457300538949118e-8 / 7.457300536770515e-8 | 2.178603e-17 / 1.194302e-9 | (-9.817807923183e-5,-6.535503242083e-5) / (-9.817807918591e-5,-6.535503245872e-5) | 5.953338e-14 / 1.113206e-6 | P/P |
| R(-4,0)_s | 2.675239609830161e-7 / 2.675239609673209e-7 | 1.569520e-17 / 1.086492e-9 | (2.102233361219e-4,-4.973043616949e-5) / (2.102233361252e-4,-4.973043612808e-5) | 4.153442e-14 / 1.881525e-6 | P/P |
| R(-2,0)_s | 1.477690850523827e-6 / 1.477690851302920e-6 | 7.790931e-16 / 1.242282e-9 | (4.942316169510e-4,-2.055157696619e-4) / (4.942316170615e-4,-2.055157697636e-4) | 1.501808e-13 / 3.186491e-6 | P/P |
| R(-1,0)_s | 6.669309653443721e-6 / 6.669309654252199e-6 | 8.084777e-16 / 5.111835e-8 | (-1.032707715899e-3,7.678339216509e-4) / (-1.032707715920e-3,7.678339217534e-4) | 1.046628e-13 / 7.413384e-6 | P/P |
| R(0,0)_s | 7.537612200733977e-4 / 7.537612200675036e-4 | 5.894048e-15 / 3.195287e-5 | (-2.525230435382e-2,1.077415170190e-2) / (-2.525230435360e-2,1.077415170215e-2) | 3.307132e-13 / 8.330266e-4 | P/P |

Aggregate frozen-reference result: `channel_count=12`, power `12/12`, complex amplitude `12/12`, `pass=true`。

### Full3D pairwise aggregate

历史 Full3D authority 为 `/home/Projects/MyFEniCS/benchmarks/artifacts/task035c_hybrid_channel_memory/p6_h10_full_static_mpi8_244b62e.json`，SHA256 为 `b8b428476cdeb4b80495f4a8b1c89e3bb2f67c682c695fc72bb59dbbbd94b4e3`。现有 `compare_models` 的 `full_static__vs__hybrid_static_m120` relative-1e-3 结果为：power `12/12`、complex amplitude `12/12`、最大 power relative error `6.51037642788911e-10`、最大 amplitude relative error `6.667955305244103e-10`、limit `1e-3`、`pass=true`。

### Post-fix 资源与 hash-bound 证据

worker timing total 为 `314.0315530579537 s`，timeline 最后可读 elapsed 为 `316.6363581159385 s`；bottom/top streaming recovery 为 `4.041541184997186 / 3.7041287679458037 s`，顺序总计 `7.74566995294299 s`。process-tree RSS peak 为 `7934.6484375 MiB`，worker RSS/PSS/USS 分别为 `7926.7109375 / 6186.951171875 / 5912.7421875 MiB`，swap 为 `0`。首次失败的 `2.58538818359375 GiB` 峰值仍保留在 resource ledger，并明确不是成功 solve 峰值。

| 证据 | ignored artifact 路径 | SHA256 |
|---|---|---|
| post-fix summary | ../../../benchmarks/artifacts/task037b/h1_direct_authority_postfix_2990f35_mpi8.json | e22aa1edfeab331d5a8be13ca085e029d5446a4fdf300a5787a00688ef700db2 |
| solver record | ../../../benchmarks/artifacts/task037b/h1_direct_authority_postfix_2990f35_mpi8/solver_record.json | 290fc25c119bbf641b8f0277ed5f9a101bc11a4df898c9133509f53c56dd4a1c |
| stdout | ../../../benchmarks/artifacts/task037b/h1_direct_authority_postfix_2990f35_mpi8/worker_stdout.txt | 35cdb0831b96aca83c727ac36a17939e289ddf6588f07d97b5ca4ed3ef924f71 |
| timeline | ../../../benchmarks/artifacts/task037b/h1_direct_authority_postfix_2990f35_mpi8/memory_timeline.csv | 26aee5647d93d4d5e9657b6a00f63fed98ffb83347506fb7bc8ed82bbbbbb9a6 |
| memory stages | ../../../benchmarks/artifacts/task037b/h1_direct_authority_postfix_2990f35_mpi8/memory_stages.jsonl | a30d7cd52385f5940ac23b90297e85bb7f23dab64e6964f640c3aed3e096dab5 |

上述 artifacts 均为 Git ignored；tracked docs 只保存 hash-bound 引用，不将 raw 输出纳入提交。
