# Task037-extra G2.5 D3b response：真实 slab14 LOR-HX build-only

## 结论

本轮只从唯一原始 run 目录固化 D3b 证据，没有实现 D3c、没有运行新的 PDE、没有
提交或推送。`build-only` 的含义是“只检查能否把对象按合同构建并盘点”，不是把
这个对象用于一次预条件器作用，也不是收敛结果。

| 范围 | 状态 | 边界 |
|---|---|---|
| 真实 p6/slab14 LOR-HX build | `pass_build_only` | hierarchy、factor/storage、material 与生命周期字段通过 raw qualification |
| retained-payload memory signal | `FAIL` | HX hierarchy 比同口径 trace-ILU 大很多；不能称 memory positive |
| G2.6 one/two V-cycle contraction | `not_run` | 1V/2V apply、rho、apply time 均未测 |
| G3 | `not_started_and_prohibited` | 本轮禁止进入 |
| overall G2 | `not_claimed` | 未有 contraction，因此不作整体 G2 分类 |

## 方法的通俗解释

固定 low-storage V-cycle 是一个局部近似逆：细层用便宜的 Jacobi 修正，中间通过标量
H1 梯度和向量 H1 辅助空间搬运误差，层级逐步变粗，最后只在很小的最粗层保存精确因子。
它希望用低阶局部结构代替 p6 trace 大 ILU；代价是要保留转移矩阵、H1 层级和最粗层
因子，并承担较长的 setup。D3b 只验证“这些对象能否构建”，没有执行 V-cycle，所以
不能声称它有效或能降低外层残差。

## 运行身份与 solver 边界

| 项目 | raw 值 |
|---|---|
| source SHA | `c7c7a26c1946a9244845c6423872e5fe69095289` |
| scope | p6/h10/S、MPI1、screen20、M2c never-materialized、M3a overlap0.125 partition |
| run directory | `benchmarks/artifacts/101_task37_extra_development/g2_slab14_lor_hx_build_mpi1_screen20_c7c7a26` |
| flags | identity=true；LOR transfer=true；LOR-HX=true；factor-inventory=false；G0=false |
| watchdog | `task037_extra_g2_slab14_lor_hx_oracle_pass_build_only`；return `0`；failures `[]`；no swap |
| solver | 固定 20 步 `DIVERGED_MAX_IT(-3)` |
| true / reported residual | `0.04474243612765` / `0.04474243612765121` |
| official result / RTA | `false / false`；postprocess skipped |
| materialization | global A=false；global F=false；exact outer unchanged |

原始 `watchdog_summary.command` 是精确记录的 worker command，并由其
`parent_launch_descriptor.json` 绑定。raw 没有单独保存 parent shell command，故不从
worker command 反推或伪造另一条 parent command。

精确的 raw worker command 为：

~~~text
mpiexec -n 1 /home/shenjh/Projects/MyFEniCS-Surrogate/.venv/bin/python -m benchmarks.run_task033_full3d_watchdog --worker --degree 6 --h-nm 10.0 --polarization-kind s --run-kind full-solve --mpi-size 1 --profile default --stage4-full3d-assembly-backend assembly_time_static_condensed --run-dir benchmarks/artifacts/101_task37_extra_development/g2_slab14_lor_hx_build_mpi1_screen20_c7c7a26 --task035c-p6-h10-gate --task035c-p6-preflight-authority benchmarks/cases/095_high_order_local_hp_resource_envelope/records/global_hexa_p1_p6_h10_p6_assembly_time_condensed_independent_mpi8.json --task035c-p6-preflight-sha256 96ac3949efc236393d4c2dbc6e1fa334ad5ccb0e9796bdeba13fbe0515577dd8 --verified-clean-sha c7c7a26c1946a9244845c6423872e5fe69095289 --task037-f3-screen 20 --task037-m2c-never-materialized --task037-m3a-overlap0125-partition --task037-extra-g2-slab14-identity --task037-extra-g2-slab14-lor-transfer --task037-extra-g2-slab14-lor-hx-oracle --parent-launch-descriptor /home/shenjh/Projects/MyFEniCSx_task37_extra/benchmarks/artifacts/101_task37_extra_development/g2_slab14_lor_hx_build_mpi1_screen20_c7c7a26/parent_launch_descriptor.json --parent-launch-descriptor-sha256 fcb9e4e6a18ddf9ca1c049c361b0fee393c4eb5eeb05f055c4cdb6d40d09daa7
~~~

## identity 与 material

| 字段 | 值 |
|---|---:|
| primary / owner / parents | `14 / 0 / 54` |
| full / interior / trace rows | `32724 / 24300 / 8424` |
| active LOR rows | `36288` |
| parent ID hash | `ac7e3532a1ecf55826a25a99b1f5197fb7c9952a084bf88f4ca15bad79511023` |
| physical edge hash | `69b351698907f0067b09cf14c0f889d1566a86d1bcfec78d7a48121659635054` |
| active edge hash | `a359da92b3a781ff447f5bf81ce7dc845c1be022464948526ee489874c77010a` |
| identity gate | `pass` |
| iter20 owner-local `r=b-Ax` norm2 | `0.42723143961943305` |
| iter20 residual SHA256 | `3aa610ed9bbb63047188b64d21d5dcab04184ffc6316196458e99aab520bb195` |
| G2.2 three deterministic vectors | identity Gate pass；最大相对误差 `2.978578754981666e-15` |
| transfer deterministic/adjoint | finite、deterministic；adjoint error `1.5008209190777043e-14` |

## HX build audit

| 字段 | 值 |
|---|---:|
| physical model | affine volume proxy only；没有 DtN surface proxy |
| curl coefficient | `(1.0, 0.0)` |
| present material tags | `1, 3` |
| mass coefficient tag 1 | `(-0.2166168318483261, 0.0)` |
| mass coefficient tag 3 | `(-0.21618408969570307, -0.0007905090610040143)` |
| shift semantics | `diag <- diag - 1j*0.1*max(abs(diag), 1e-12*max(abs(diag)))`；`literal_p6_shift_galerkin=false` |
| zero interior trace lift | `true` |
| factor count / coarsest-only | `2 / true` |
| fine p6 trace/full factors | `0 / 0` |
| fine-intermediate / large-LOR factors | `0 / 0` |
| HX 完成后 retained parent topologies / persistent RHS | `false / false` |
| global dense | `false` |
| build seconds | `571.4551421470242` |

transfer retained payload 为 `18735740 B`，D2c hierarchy payload 为
`3109473612 B`，合计 retained numeric payload lower bound 为
`3128209352 B = 2983.2929153442383 MiB = 2.9133719876408577 GiB`。该口径只计
T/Tᴴ/E/Eᴴ、packing/reference CSR、H1 hierarchy、inverse diagonal 和最粗层因子数组，
不计 Python object、PETSc allocator、置换或其他运行时开销；不能把它直接当进程 RSS。

## memory signal

同口径 current trace-ILU baseline 为 `122023588 B`，任务要求的 `0.60` threshold 为
`73214152.8 B`。

| comparison | value |
|---|---:|
| HX / trace baseline | `25.63610366874313` |
| HX / 0.60 threshold | `42.72683944790521` |
| memory signal | `FAIL` |

这只说明 build-only hierarchy 没有达到最低存储目标；不作整体 G2 分类。
contraction 未运行，整体 G2 仍为 `not_claimed`。

## resources 与 lifecycle

| authority | value |
|---|---:|
| whole-run process-tree RSS | `7964.97265625 MiB = 7.778293609619141 GiB` |
| worker RSS / PSS / USS | `7951.1875 / 7899.833984375 / 7855.32421875 MB` |
| worker/process-tree swap | `0 / 0 MB` |
| transfer build interval process-tree max | `1186.52734375 MiB` |
| HX build interval process-tree max | `5528.63671875 MiB` |
| sample count / poll | `3250 / 0.25 s` |
| run elapsed | `832.8251509650145 s` |
| historical container cgroup peak | `13279.546875 MB`；不是本次 authority |

`stage_peaks[g2_lor_hx_build_ready]` 的 process-tree max 为 `7923.4296875 MB`，但该
区间延续到后续 existing trace-factor setup，不能称 HX build/ready 峰值。有效 build
峰值以 `stage_peaks[g2_lor_hx_build_started]` 的 `5528.63671875 MiB` 为准。四个
required lifecycle stage 均存在：transfer started/ready 与 HX started/ready。

## contraction 与前次 launch

| quantity | 1V | 2V |
|---|---|---|
| apply count | `not_run` | `not_run` |
| rho | `not_run` | `not_run` |
| apply time | `not_run` | `not_run` |

第一次 launch 在 PDE 前误用根目录空 `.git` 挂载，tracked-authority pre-PDE 检查失败；
没有创建 run directory，也没有开始数值工作。这不是数值 retry。成功 run 使用同一 shell
显式设置 `.git-codex` 的 `GIT_DIR` 与 `GIT_WORK_TREE`；首次受控失败保留在 compact
provenance 中。

## raw evidence

compact record：
`benchmarks/cases/101_task37_extra_development/records/g2_slab14_lor_hx_build.json`

| raw 文件 | SHA256 |
|---|---|
| `watchdog_summary.json` | `d1f470e42914752e490d363a7107f1bf1b2d593f94e10f4d81d80ccf88d3bb1a` |
| `run_summary.json` | `4486e1fead530bcd5b859183269adb2dfde5353a6592f556b02ebc3c8134f6af` |
| `task037_f3_core_audit.json` | `b6b12fa31c48d863431bb72e26a7a84a51f8c237d26ee2347b382cab30e7ba67` |
| `progress_3d.jsonl` | `0a9b4345646ae3bf1cdc6681f4f6786a454b0f2f666394e9913d6b20e57ddd34` |
| `task037_f3_residual_history.jsonl` | `75f0bc3ebec3648b60fdfc55daa9afd036b81cf6d5fe0ef1f7051a83e0f24940` |
| `memory_timeline.csv` | `71be2609b821897d81f275786d00c08180c68b6a2202625cbf72d0e2810c2722` |
| `parent_launch_descriptor.json` | `fcb9e4e6a18ddf9ca1c049c361b0fee393c4eb5eeb05f055c4cdb6d40d09daa7` |
| `worker_stdout.txt` | `5a7b9cbe88dfef87a463a421d395a7e3e59f4d258f8172a32c49caee120d4bd8` |
| `solver_log.txt` | `5a7b9cbe88dfef87a463a421d395a7e3e59f4d258f8172a32c49caee120d4bd8` |
| `NO_OFFICIAL_FIELD_OUTPUT.txt` | `e11465d92e416af3e4321c581b7291b7d4df5c932b425541f9b0114e259d3f38` |
| `mesh_3d.h5` | `71c17d7e60beb920922bcaabc178078959ec48d5ec257aaabe42d14c64102a3b` |
| `mesh_3d.xdmf` | `e40e1b05f3269101fe93e96416481f14bcaa64fb1df5f030381c747b484b9864` |
| `mesh_3d_partition_note.txt` | `0a3e481d76798fa867ac1151dee5b3899920e623606faf36f175ee670c9ed974` |

### 本轮停止边界

G2.5 仅记录 `pass_build_only`；G2.6 contraction、G3 和 official field/RTA 均未运行。
本 response 不声称 G2 overall pass、minimum contraction、full solve 或 production
promotion。
