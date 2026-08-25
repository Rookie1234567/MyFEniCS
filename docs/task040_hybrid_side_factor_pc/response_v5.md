# Task040 Review V4 执行响应（V4-1 收口）

## 结论

V4-1 是一个有效的受控身份负结论（`controlled_identity_negative`），不是一次数值
失败：

```text
classification = EXACT_AUTHORITY_NOT_COMPATIBLE_WITH_CURRENT_BARE_F
failure         = canonical_source_binding
failure_code    = CANONICAL_SOURCE_ROW_BINDING_UNAVAILABLE
evidence_valid  = true
checker_pass    = true
gate_pass       = false
```

通俗地说，检查器确认了文件、分片、哈希和生产者身份，但冻结的 exact spool 没有一张
“旧文件中的第几行对应当前裸算子 `F` 的哪个物理自由度”的地图。这张地图就是
canonical source-row bridge。没有它，不能把旧 PETSc global row 直接搬到当前系统；因此
流程在构造 system、`F`、interface mass、Vec、factor、QEP 和 PDE 之前停止。

这项证据不证明 exact vectors 数值错误，不证明 bare-F residual 失败，也不判断 trace、
dual、projection、lift、preconditioner、full Hybrid 或 0.7 nm scalability。V4-2 至 V4-10
均由 V4-1 identity gate 阻止。compact record 保持不变，其 SHA256 为
`5ededd4bb9acfb9e4e3a403a410cecb37fb1490e7bf6056ca4644c7bfda7c36a`：

[V4-1 compact record](../../benchmarks/cases/104_5nm_hybrid_side_factor_pc/records/task040_v4_1_exact_authority_compatibility_v1.json)

## Authority 与哈希

| 身份 | 值 |
|---|---|
| branch | `codex/20260822-task040-hybrid-side-factor-pc` |
| formal source | `9f3d6e39cb607125a773b35d9a2a9f7459c7f2dc` |
| checker source | `4b70adfb6707464aaed4309ece5bca179dd60b57` |
| frozen authority source | `112ac4913a531ae5c5aab941ac88f005a95b9dc4` |
| spool producer source | `7e5d9b57a10b1093f0cb062eaf7bc12797c47e1f` |
| input SHA256 | `4e60924b5997e3ca99e324ea14779f9014efc6a1304a9aa11de9c808353f1811` |
| physical model SHA256 | `8391d46139646440d869aa43abe6a68bc921fc1972a10030c64be81dffdd527c` |
| selected manifest SHA256 | `2dddaf7a6f8f045adabd840970952517d76305c7c0e03c71258642d856c13067` |
| probe manifest SHA256 | `7a03b2cf80fe5081d1fe1248b9d4c79f3ef4e955a8014e905c2f2ca82797baad` |
| selected identity SHA256 | `cfd5704b48bff980fa2d819f4deee9a59bb9a3db39bc24a70c53f42f067d39e9` |
| spool catalog SHA256 | `a2a7fb6fb01df4f795d31ff94f6ac6adf957ac4fe4a5c1a8d05176e3d64c0384` |
| resolved config SHA256 | `f965c38abea08bee0ff83a6603e336ca4823deb932af7064aed3c571f8f63883` |
| checker artifact SHA256 | `71ab1274b3b236679ff19b403875b0109f6f3e3c1bb1f02e2642ee69d44f97d8` |
| formal raw file count | 6 |
| spool JSON file count | 96 |
| checker read files | 105；无 NPY 数值文件 |
| checker result | `rc=0`，`37/37 checks`，全部 true |

五个冻结 exact-output identity 逐项如下：

| label | exact-output identity SHA256 |
|---|---|
| `modal_traction_positive` | `3100fd4f186ba720ef8ef030e4fc45749d6726927e420102884d71016b0fe8cb` |
| `modal_traction_negative` | `a7a42879e64d78e3de3f956747806b628f01fa482bece281a8b20bda1bf065e4` |
| `external_dtn_coupling` | `f0f1c970644aebe13a7fe94806205f83c02c5ea90554ccc2987bd5720d7c37f8` |
| `fixed_random_repeat_0` | `5322aabafa153d073e635fd80aa1f729f7e1c9c98dab2032ef3f2a67d6860baa` |
| `fixed_random_repeat_1` | `51429f3bd4db63c6cb870d10b7e6f757ac82255fa8871bb4af9d8449eeaa2c93` |

formal root 只有：
`results/task040_v4_1_exact_authority_compatibility_mpi8_9f3d6e39`。
原始 JSON/JSONL/stdout 的 SHA256 为：

| raw 文件 | SHA256 |
|---|---|
| `worker/run_summary.json` | `ace70fc037df8dfb7acb3e2653392f594ea74951077c6b60ec51cc15641a08cb` |
| `watchdog_summary.json` | `f035b5d7fa28e2bdac8696fd4aa98586eaf2952b17a9c513de9e90f352c718a0` |
| `memory_stage_markers.raw.jsonl` | `61b8de92162eefa9be80fcf58a4baf2db5afcb3049251fb12d9f48431c323ba3` |
| `memory_stages.jsonl` | `2d7fd70f82f870cd93f2d6d15d2b4d1517ec09beae6e88542085839e89f74485` |
| `process_tree_samples.jsonl` | `6d527b367eaa19a610a2eb601bba1e8abaaa79e9dca86e6d9d955ca0dd051827` |
| `worker_stdout.txt` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |

## Identity gate

检查器从 raw 字段和冻结 probe authority 独立重算，未把 run summary 预填的
classification/pass 当作结论。identity checks 恰为以下 11 项：

| identity check | 结果 |
|---|---|
| input SHA256 | true |
| physical model SHA256 | true |
| frozen branch | true |
| freeze source | true |
| selected manifest | true |
| resolved config | true |
| packet manifest | true |
| spool catalog | true |
| spool producer source | true（5 labels × 2 roles，每项 8/8） |
| exact-output metadata | true（五个冻结 identity） |
| canonical source binding | **false** |

唯一失败项是 `canonical_source_binding`。缺失项恰为五个 label 的 RHS 和 exact output：

1. `modal_traction_positive:rhs`
2. `modal_traction_positive:exact_output`
3. `modal_traction_negative:rhs`
4. `modal_traction_negative:exact_output`
5. `external_dtn_coupling:rhs`
6. `external_dtn_coupling:exact_output`
7. `fixed_random_repeat_0:rhs`
8. `fixed_random_repeat_0:exact_output`
9. `fixed_random_repeat_1:rhs`
10. `fixed_random_repeat_1:exact_output`

canonical binding 的附加事实是：`descriptor_available=false`、`descriptor_complete=false`、
`bridge_qualified=false`、`pass=false`；array metadata/hash 已验证，formal runner 对 NPY
只做 mmap/hash 校验，`formal_array_hash_validation_only=true`，没有构造 numeric vectors、
没有保留 values，checker 没有 numeric NPY read，`raw_global_row_remap_used=false` 且被禁止。

## 为什么不能做 raw-row remap

旧 exact spool MPI8 的 ownership 是：

```text
[0,15582], [15582,32868], [32868,49596], [49596,64416],
[64416,80712], [80712,96834], [96834,115074], [115074,132300]
```

当前构造布局不同（例如当前前两段为 `[0,17118]`、`[17118,33948]`）。旧 writer 保存了
local array、ownership、global/local size、dtype、array hash、metadata hash 和
source identity，但没有保存每一行的 canonical physical key，也没有保存 raw row 到该 key
的映射。旧进程在同一布局内写入和重载，所以旧测试通过并不能证明跨布局搬运合法。

因此，“文件 hash 正确”只说明读到的是原来的文件，不说明第 15582 行在新布局仍代表同一个
物理自由度。没有 source-row/key bridge，就无法把旧 RHS 或 exact output 重构为当前 active
row 顺序；凭 global size 相同或 packet 数量相同宣称兼容，会把不同数学未知量误认为同一行。

## Residual 与下游门

formal 没有构造 bare `F`，所以五个 bare-F residual 都是 `observed=null`、
`status=not_run_by_identity_gate`，阈值仍是 `<=1e-9`，不是失败数值。解释性的
`A_side=(F-C H^{-1}D)` residual 也完全未运行；`reports_count=0`，
`numerical_gate_pass=null`。不能写入旧失效尝试中的大 residual，也不能把 explanatory
operator 当作 bare `F`。

raw downstream map 的十项均为 `not_run_by_gate`：

```text
projection, lift, trace, dual, response, fgmres, coarse,
level_b, full_hybrid, h3
```

Review V4 的细分状态为 `not_run_by_v4_1_identity_gate`：projection、dual、bare-F residual、
A_side explanatory residual、trace、lift、V4-2、V4-3、V4-4、V4-5、V4-6、V4-7、V4-8、
V4-9、V4-10、basis/rank/selection、true residual checkpoints、train/holdout。没有生成
rank、basis、selection、训练集或 holdout。

## 构造、factor、QEP 与 PDE inventory

| 项目 | 观察值 |
|---|---:|
| system created | false |
| explicit bare-F created | false |
| interface masses built | false |
| RHS vectors loaded | 0 |
| exact-output vectors loaded | 0 |
| `exact_output_vectors_loaded` | 0 |
| `full_side_exact_factor_count` | 0 |
| `global_direct_factor_count` | 0 |
| `cross_section_group_factor_count` | 0 |
| `reduced_dense_factor_count` | 0 |
| `factor_objects_created` | 0 |
| QEP calls | 0 |
| PDE solve | `not_run` |

这些零值是身份门早停后的生命周期事实，不是“已经构造后释放”的数值结果。

## Watchdog 与 runner 资源口径

两种资源口径必须分开：

| 口径 | 结果 |
|---|---|
| watchdog worker | MPI8、每 rank 1 thread、rc0、natural exit、process group/worker exited、无 SIGKILL |
| watchdog samples | 20/20 authoritative；最后 process sample `9.697888669999884 s` |
| watchdog memory | process-tree peak `1764352000 B = 1.643180847167969 GiB` |
| watchdog swap | `swap_bytes=0`，dedicated cgroup swap `0`，status readable |
| runner resource authority | `status=not_run_by_identity_gate`、sample count `0`、readability/swap fields 为 `null` |

watchdog 证明的是轻量 metadata preflight 进程的外部资源采样；runner 没有进入 system/F，
所以 runner resource authority 没有 solver sample。这不是 accuracy、full-workflow 或
Pareto 结果，也不能与 direct/full workflow 做节省比例比较。

## 历史无效尝试隔离

以下两个 root 保留作审计历史，但不属于 formal authority：

| root | source | 分类 | 边界 |
|---|---|---|---|
| `results/task040_v4_1_exact_authority_compatibility_mpi8_a64d33e6` | `a64d33e6fd01a3f23d27fb326b9b2efa694142f3` | `implementation_failure` | 按 raw global row 跨不同 ownership remap；其 residual 不得引用，也不得作为 formal 结论 |
| `results/task040_v4_1_exact_authority_compatibility_mpi8_1c68da98` | `1c68da98e0cde6676e3e2f81ae67a424befae062` | `incomplete_superseded` | 被监督终止的未完成实现尝试，不得作为 formal 结论 |

当前正式结论只来自 `9f3d6e39` root 的 raw evidence 和独立 checker。旧 root 的残差既不能
证明 bare-F incompatibility，也不能替代 canonical identity gate。

## V4-2 至 V4-10、production 与 0.7 nm 边界

V4-2 current-Petrov/metric-best/exact trace 与 3D group lift、V4-3/4/5 response pilot 和
long-Krylov、V4-6 fresh process packet-independent rebuild、V4-7 bounded patch/Level B、
V4-8 bottom/top/both/full Hybrid、V4-9/V4-10 h3/p6 与 0.7 nm 均为
`not_run_by_v4_1_identity_gate`。没有新的 DoF、R/T/A、field、rank、residual、factor、
RSS、wall、memory scaling 或 production qualification。

因此本轮不宣称 production side inverse，不宣称 0.7 nm 可行或不可行，也不宣称 continuum
convergence。下一次若要进入后续 Gate，必须先在禁止重建 full-side exact factor 的前提下
取得与 source SHA、旧 layout 和每个 active row 绑定的 canonical source-row map，并由
独立 identity/reconstruction 证据证明可逆、覆盖、Floquet consistency 和 round-trip。

## 测试与检查

| 项目 | 结果 |
|---|---|
| test313 serial | `12 passed` |
| test313 MPI2 | `12 tests per rank passed` |
| test313 MPI4 | `12 tests per rank passed`；仅 pytest temp cleanup warning |
| test314 | `22 passed` |
| Ruff | passed |
| compileall | passed |
| git diff --check | passed |
| documentation contract + repository principles | `source scripts/activate_myfenics_wsl.sh && python -m pytest -q src/test/test_26_documentation_contract.py src/test/test_24_repository_work_principles.py`；`20 passed, 1 failed`；唯一失败是既有 Case104 numbered-case registration gap，未修改测试 |
| V4-1 independent checker | `rc=0`，`37/37 checks`，`evidence_valid=true`，`checker_pass=true`，`gate_pass=false` |
| formal MPI8 | controlled metadata preflight stop；未构造 solver/PDE |
| full repository pytest | `not_run` |
| CI | 未声称 CI 通过 |

测试证据只支持当前 raw checker 和 identity-stop 合同，不扩大为 numerical/PDE 证据。

## Selective merge 依赖组

本轮只收口文档和已批准的 checker/compact evidence；merge approval 仍为 **NO**。

| 依赖组 | 本轮状态、数值行为与依赖 | fresh PDE evidence / 合入顺序 |
|---|---|---|
| production numerical/core | 未改变；没有新的 bare-F、QEP、PDE 或 production 数值 | 无 fresh PDE evidence；不得以本轮结论合入 production numerical/core |
| reusable runner/watchdog | 本轮只引用既有 metadata preflight 资源口径；没有扩大 runner/watchdog 改动 | watchdog raw 已有独立证据；若未来改 runner，需单独 focused regression 后再审 |
| checker/benchmark | V4-1 独立 raw checker 已提交，绑定 checker source `4b70adfb...`；不调用 solver、不读 numeric NPY | checker rc0/37 checks；可作为 checker/benchmark 组候选，仍需监督审查 |
| compact evidence/docs | compact record 不变，SHA `5ededd4b...`；本轮更新指定 16 个 outcomes/summary 文档并新增本响应 | 无 PDE；先审阅文档和 evidence 链，再决定是否纳入 evidence/docs |
| research-only | 两个旧 invalid roots 仅作历史审计，不提升为结论 | 不合入 production；保留 raw evidence 供审计 |
| do-not-merge | raw global-row remap 路线、a64 residual、1c68 未完成路线、任何未运行的后续算法结论 | 明确不合入；不得通过隐藏死代码或旧 residual 改写 V4 结论 |

## 证据入口

- compact record：[task040_v4_1_exact_authority_compatibility_v1.json](../../benchmarks/cases/104_5nm_hybrid_side_factor_pc/records/task040_v4_1_exact_authority_compatibility_v1.json)
- 独立 checker artifact：[checker_recomputed_after_4b70adfb.json](../../results/task040_v4_1_exact_authority_compatibility_mpi8_9f3d6e39/checker_recomputed_after_4b70adfb.json)
- formal raw root：`results/task040_v4_1_exact_authority_compatibility_mpi8_9f3d6e39`
- frozen exact spool：`results/task039_v5_h4_mumps_blr_side_component_mpi8_7e5d9b57_1e3/numerical_output`
- tracked probe manifest：[task040_v1_2_probe_manifest_v1.json](../../benchmarks/cases/104_5nm_hybrid_side_factor_pc/records/task040_v1_2_probe_manifest_v1.json)
