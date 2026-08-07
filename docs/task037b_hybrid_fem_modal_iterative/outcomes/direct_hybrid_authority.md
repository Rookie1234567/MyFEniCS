# Task037b H1 direct Hybrid authority

## 结论

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
