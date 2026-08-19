# Task039 Review V6：继承审计

本文是 V6-0 的 docs-only inherited audit。它只读取 V5 的 compact record、既有 raw
索引、packet/spool 元数据和当前源码；没有启动 V6-1、PDE、MPI、QEP 或 heavy run。本轮
新增文件写入前的工作树为 clean；本文本身造成的 dirty 状态不代表任何 formal preflight。

## 1. Git 身份与继承关系

| 字段 | 实测值 | 口径 |
| --- | --- | --- |
| branch | `codex/20260812-task39-5nm-hybrid-0p7nm-feasibility` | 当前本地分支 |
| reviewed HEAD | `6694530f4e38bfa3f563eaa66cddc5268009e6dc` | Review V6 §0 指定的继承基线 |
| current review HEAD | `60be7a615e0d23beee459063032b38c39e4a61bd` | 当前 local `HEAD` |
| upstream | `origin/codex/20260812-task39-5nm-hybrid-0p7nm-feasibility` at `60be7a615e0d23beee459063032b38c39e4a61bd` | 当前 tracking ref |
| ahead / behind | `0 / 0` | `git rev-list --left-right --count HEAD...@{u}` |
| initial worktree | `clean` | 本文创建前的 `git status --short` |
| relation | `60be7a61` 是 reviewed HEAD 的一个后继 docs-only review-plan commit | `6694530f...` 是其祖先；未见 V6-0 前的代码漂移 |

审计读取了根 `AGENTS.md`、`docs/AGENTS.md`、仓库工作原则、docs README、Task39
`task.md`、[Review V6](../review_report_v6.md)、[V5 response](../response_v6.md)、
V5 outcomes/records，以及 factor-only、modal Schur/Krylov、streaming-W 和 spool 相关
源码。没有更深的 Task39 `AGENTS.md`。

## 2. V5 response 与 compact record 身份

以下是当前文件内容的 SHA256；这是 evidence identity，不是对 raw 数值重新计算的替代。

| 文件 | SHA256 | 用途 |
| --- | --- | --- |
| `response_v6.md` | `3ff4de49c7a1358d1be86da81552b2351b9814fb662d3c5f0801e31cf54bf62b` | V5 整轮回应 |
| `task039_v5_h4_exact_side_memory_attribution_v1.json` | `6caf6804f5c71ce9fe30b303d553d0dc5004a7f618bf328b633adebf6343c5f7` | V5-2 h4 setup attribution |
| `task039_v5_h5_current_hybrid_direct_sidecar_v1.json` | `ecb3825eee7ffa858e6c7c837cd4d4c06e4cfaa6aeac258230b83647013ccdc9` | V5-S h5 sidecar |
| `task039_v5_factor_light_side_inverse_v1.json` | `fd8e6603acefcc6bedddd0cdbbf08980c85549f0012f91b8b19ab2d41410b510` | 两个 BLR profile |
| `task039_v5_fixed_budget_side_krylov_component_v1.json` | `37f2ddd39b5b23493910a2e2cc513ed95699738d62a6a40b6c748f937b940280` | budget-32 bottom component |
| `task039_v5_streaming_woodbury_component_v1.json` | `9c16a981dcd8abdcf994a3ed7c5bcd5248e915f05d91309b9fa80f6e706c5e09` | retained/streaming-W synthetic component |
| `task039_v5_v4_h4_modal_schur_sampled_columns_v1.json` | `5a704374cbd67205185df53599c82af02589f5f8f4b8e1dd8b11f6199f5f51e1` | V5-4 sampled-column contract |

相应路径均位于
[`case 103 records`](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/)。

## 3. 继承的 h4 内存基线

| 路径 | measured 结果 | 解释 |
| --- | ---: | --- |
| Hybrid direct h4 | `93.377006531 GiB` | matched direct process-tree RSS reference；own numerical/physics pass |
| V4 exact-side iterative h4 | `104.334560394 GiB` | 1 outer iteration；numerical/physics pass，但 resource regression |
| V5-2 exact-side setup-only | `85.376991272 GiB` | 15-marker setup peak；不是 full solve，也没有把 object bytes 当 RSS |

V5-2 的专用 marker/ledger raw 位于
[`h4 attribution record`](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v5_h4_exact_side_memory_attribution_v1.json)。
上述三项是不同生命周期范围：V5-2 没有 outer solve、recovery、R/T/A 或 field，因此
不能把 `85.376991272 GiB` 叫作完整 iterative peak。

## 4. V5 代码身份与 ordinary default 边界

| 阶段 | 精确源码/实现身份 | 继承结论 |
| --- | --- | --- |
| V5-2 setup telemetry | `2ba0c44dfbd7c43547bf2769d013f6a92f4809f1` | 15-marker exact-side setup attribution |
| V5-3 factor-only | `61d3b06f38eea3131d3e5f7a7b82577ace5a9f1f`；`ResearchExactFactorInverse` / `ResearchExactSideLuAction` / `HybridLocalDtnWoodburyOracle` | PETSc factor handle 可代替 KSP/原矩阵的显式 opt-in |
| V5-4 single Schur / GMRES10 | `2eab55d70e4bd4f7473c908c88dcfa18e1c94e9b`；`hybrid_fem_modal_block_ldu.py` | sampled single-build 与 fixed-PC GMRES10 仅显式 opt-in；默认 FGMRES90 |
| V5-5 streaming-W action | action `9ca332bfa11bce92866ee20e38fc858cf480e6f6`；component runner `76d374f89452623ed59b525d3a24c0a7348c7d57` | synthetic batch 8/16/32；不构成 h4 RSS 资格 |
| BLR family | formal sources `2f1e65812f25b91cc22f5bd01debe7bd77790c08` 与 `7e5d9b57a10b1093f0cb062eaf7bc12797c47e1f` | 两个且仅两个冻结 profile 均 resource-negative，family closed |
| fixed-budget family | formal source `ff89f07bc26aecbab6f60f06408c3ab364e9c5f4` | budget 32 bottom numerical-negative controlled stop |

这些实现都保留 `ordinary_defaults_unchanged`/默认路径合同：factor-only、streaming-W、
sampled Schur 和 GMRES10 不是普通 caller 的默认行为。V6 不得把 research opt-in 提升为
production default，也不得重开第三个 BLR、generic budget/ILU scan 或 h5 rerun。

## 5. Existing bottom exact-response spool

| 项目 | 只读核验结果 |
| --- | --- |
| root | `results/task039_v5_h4_mumps_blr_side_component_mpi8_7e5d9b57_1e3/numerical_output/v5_blr_reference_spool` |
| availability | `available`；8 个 producer rank 目录 `rank0000`–`rank0007` |
| vector artifacts | `96 .npy` = 6 labels × 8 ranks × (`rhs` + `exact_output`) |
| metadata artifacts | `96 .json`，每个含 `array_sha256`、`metadata_payload_sha256_excluding_self`、dtype、global/local size、ownership range、role |
| root file inventory | `198` files；另含 memory/marker/sample/mesh 辅助文件，不把它们算作 response vectors |
| packet manifest | `manifest.json` SHA256 `2dddaf7a6f8f045adabd840970952517d76305c7c0e03c71258642d856c13067` |
| packet identity | `identity.json` SHA256 `b3bb870fe6fa17cb262b6161f7317cc1950944755c9270d4628dd5c79e950690`；canonical identity SHA `cfd5704b48bff980fa2d819f4deee9a59bb9a3db39bc24a70c53f42f067d39e9` |
| producer identity | metadata outer `source_sha=7e5d9b57a10b1093f0cb062eaf7bc12797c47e1f`；packet inner source `eaad0f942f014b65474ac57e3d5e561316489f20` |

六个 label 的 source-bound global identity hash如下；rank-local `local_sha256` 按 ownership
不同，不能跨 rank 直接相等。

| label | RHS global SHA256 | exact-output global SHA256 | probe语义 |
| --- | --- | --- | --- |
| `physical_side_rhs` | `280c00e1df3df3d2c07d5cd8bf1766a0860a1b895e1dff3e059ac99dd2e4bbae` | `af2a2ab51645d9ecc9ced26021d5c9f63145a14e6a828a92a15ee3944f02f96d` | `degenerate_uninformative=true` |
| `modal_traction_positive` | `fbb08a8c70a92505f8146b52ef046d568d745f2caf948fbd63eadcdb48295413` | `3100fd4f186ba720ef8ef030e4fc45749d6726927e420102884d71016b0fe8cb` | mandatory holdout |
| `modal_traction_negative` | `b9eaee3ee19c1f269eb0498250ae5660fef6d75918942a080d9d319a53618a70` | `a7a42879e64d78e3de3f956747806b628f01fa482bece281a8b20bda1bf065e4` | mandatory holdout |
| `external_dtn_coupling` | `27dcd213b93c08657247b27edd97525b474a425422fef533a7b3a8e701554b1d` | `f0f1c970644aebe13a7fe94806205f83c02c5ea90554ccc2987bd5720d7c37f8` | mandatory holdout |
| `fixed_random_repeat_0` | `5fdd169ff2bb3ee10c3546332c9f81be0f9c4125a1fdc3c82c48538cc1ae3f6e` | `5322aabafa153d073e635fd80aa1f729f7e1c9c98dab2032ef3f2a67d6860baa` | mandatory holdout |
| `fixed_random_repeat_1` | `bdd51ab7843f1560a6866de738a312cfbd89a01d9eabe794f3e12abbf3097b63` | `51429f3bd4db63c6cb870d10b7e6f757ac82255fa8871bb4af9d8449eeaa2c93` | mandatory holdout |

RHS 与 exact output 的配对权威是同一 `label`/`role`、packet identity、global coverage、
ownership metadata 和各自 array hash；历史 exact-output metadata 只有 label，不能伪称它含有
与 RHS 相同的完整 `probe_metadata`。这些 response 是 offline oracle/validation input，
不是 V6 candidate 的在线生产内存优势；exact factor 的生成成本不能从 V6 capacity 中静默
删除，也不能在 candidate setup interval 中重建或长期保留。

## 6. qualified activation 与资源快照

本轮在 qualified activation 中完成轻量只读 probe；`MPI.COMM_WORLD.size=1` 仅是 probe 进程，
没有启动 MPI job。

| 项目 | measured snapshot |
| --- | --- |
| activation | `_MYFENICS_WSL_QUALIFIED_ACTIVATION=1` |
| Python | `/home/Projects/MyFEniCS/.venv/bin/python` |
| PETSc | `ScalarType=numpy.complex128`；`IntType=numpy.int32`；PETSc `3.19.6` |
| MPI | mpi4py from `/usr/lib/python3/dist-packages/mpi4py`；Open MPI `4.1.6` |
| SLEPc / DOLFINx | `/usr/lib/slepcdir/slepc3.19/.../slepc4py`；`/usr/lib/petscdir/petsc3.19/.../dolfinx` |
| thread vars | `OMP_NUM_THREADS=1`、`OPENBLAS_NUM_THREADS=1`、`MKL_NUM_THREADS=1`、`PETSC_OPTIONS` unset |
| memory | `MemAvailable=234859192 kB = 223.979179382 GiB` |
| swap | `SwapTotal=33554432 kB`、`SwapFree=33554432 kB`；used `0` |
| disk | `/home/Projects/MyFEniCS` filesystem free `820088246272 B = 763.766696930 GiB` |

这是当前 docs-only probe 的环境快照，不是 V6 heavy 的资源许可。正式运行仍必须重新
资格化 ABI、source、packet、swap、disk 和并发状态。

## 7. V6 冻结目标与禁止项

matched h4 direct 是 `93.377006531 GiB`。V6 half-memory target、setup advancement line 和
outer-ready reserve 固定为：

```math
B_{\mathrm{half}} = 0.5\times93.377006531
                  = 46.688503266\ \mathrm{GiB},
\qquad
B_{\mathrm{setup}} = 42.019652939\ \mathrm{GiB},
\qquad
B_{\mathrm{outer\mbox{-}ready}} = 35.0\ \mathrm{GiB}.
```

`46.688503266 GiB` 是完整 h4 iterative 的正式资源线；`42.019652939 GiB` 是 setup-only
前置线，为 outer/recovery/lifecycle 留余量；`35 GiB` 只约束 outer KSP ready 边界。任何
低于 direct 但高于 half-memory 的结果只能记录为 progress，不能写成 V6 strategic pass。

V6 冻结：5 nm / 1° grazing / `phi=0` / S / p6/h4 / M480 / MPI8、同一 Hybrid 方程与
direct identity；Full3D 新 heavy、完整 0.7 nm PDE、第三 BLR profile、generic fixed-budget
或 ILU scan、h5 sidecar rerun、master 写入、new branch/worktree 和 ordinary default 改动
均 forbidden。V6-1 setup-only、side component 和尚未进入 outer 的阶段默认最多 6h，不能使用
8h 延长；8h 只在 review 规定的 full outer iterative 条件全部满足时才有一次资格。

## 8. V6 顺序与训练/holdout 隔离

执行顺序冻结为：

1. V6-0 inherited audit（本文）；
2. 一次 fresh h4/M480/MPI8 post-compaction exact-side setup-only，测 V5-3/4 的 factor-only、
   single-Schur、固定 PC/lifecycle 是否真的降低 process-tree RSS；
3. 只有 setup 同时满足 `42.019652939 GiB`、outer-ready `35 GiB`、swap=0 和全部 lifecycle
   Gate，V6 已条件允许且最多运行一次 full exact-side formal；若任一 setup Gate 失败，
   full exact-side forbidden，exact-side 只能保留为 oracle；
4. 随后才可能进入 port/modal-aware two-level side PC 的 bottom-first component，再按
   bottom Gate 决定 top/both-side；z-layer 和 matrix-free channel 仅在各自前置条件满足时
   条件执行；不自动进入 0.7 nm PDE。

训练与验证的边界不可破坏：

| 数据 | V6 角色 |
| --- | --- |
| 预先冻结的 physical/modal/external source sketches | training；必须 hash-bound，只能用于 coarse basis 构造 |
| 未参与 basis 构造的固定 holdout probes | validation；只能在候选外部验证，不能事后挑列 |
| 本审计中的 exact-response spool | oracle/validation；不得作为 candidate 在线生产对象或 RSS saving |
| formal candidate 的 process-tree RSS | 必须由 fresh run measured，不能由 object bytes、单 rank cleanup 或 synthetic `ru_maxrss` 推导 |

因此当前状态是 `V6-0_INHERITED_AUDIT_COMPLETE`，不是 V6 numerical/resource qualification。
下一步仅是主审批准后的 V6-1；本轮没有修改 Python/config/test，也没有运行 PDE/MPI/QEP/heavy。

## 9. 证据入口

- [Review V6](../review_report_v6.md)
- [V5 response](../response_v6.md)
- [V5 h4 memory attribution](v5_h4_exact_side_memory_attribution.md)
- [V5 exact-side compaction](v5_exact_side_compaction.md)
- [V5 streaming-W](v5_streaming_woodbury.md)
- [V5 BLR/factor-light record](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v5_factor_light_side_inverse_v1.json)
- [V5 fixed-budget record](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v5_fixed_budget_side_krylov_component_v1.json)
- [V5 streaming-W record](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v5_streaming_woodbury_component_v1.json)
