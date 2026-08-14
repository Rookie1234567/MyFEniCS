# Task39 Review V2：V2-0 继承与身份审计

本页只完成 Review V2 §3 的 inherited/docs audit。它不改写首轮负结果，不改变
solver、输入、普通默认值或已有 compact record，也不解锁任何正式 PDE。本页的
`V2_0_INHERITED_AUDIT_COMPLETE` 只表示身份和边界审计完成；下一步仅解锁
`V2-1` readiness。

## 1. 当前身份

| 项目 | 审计值 |
| --- | --- |
| branch | `codex/20260812-task39-5nm-hybrid-0p7nm-feasibility` |
| local HEAD | `bd3f322bafda24f043d0dfe8369c9ca67097484d` |
| remote upstream | `bd3f322bafda24f043d0dfe8369c9ca67097484d` |
| ahead / behind | `0 / 0` |
| worktree | clean |
| base master | `438caf150439343ee7c4c58ad7e02a3da812a23c`；未修改 |
| authority | [Review V2](../review_report_v2.md)；本页仅回应其 §3 |
| audit status | `V2_0_INHERITED_AUDIT_COMPLETE` |

本页创建前已用非交互 `git fetch origin --prune` 核对远端；没有 merge、rebase、
force push、分支或 worktree 操作。本页是 V2-0 唯一拟新增文件。

## 2. 继承 compact records 与 SHA

下表中的 SHA 是当前 tracked compact JSON 文件的 SHA256；每个 record 内仍保留
其 source/input/resolved/physical identity 和 ignored raw artifact SHA。raw、field、
matrix、factor 和 timeline 不被复制到 Git。

| 角色 | compact record | 文件 SHA256 | 继承结论 |
| --- | --- | --- | --- |
| Full3D p6/h10 T3 | [task039_t3_full3d_direct_mpi8_v1.json](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_t3_full3d_direct_mpi8_v1.json) | `96eab270e8f55804cd1596215c327185754a39453dfda57fe56bf59199ef5460` | own direct/capacity authority；仅 stress anchor |
| Full3D p6/h7.5 E2 | [task039_e2_h7p5_full3d_direct_result_v1.json](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_e2_h7p5_full3d_direct_result_v1.json) | `2f58f0e6aa225543acf2b2a7c189073e54dfe96736bfe66beb7ce51be9dea678` | own direct pass；不是单独的 grid authority |
| Full3D p6/h6 E3 | [task039_e3_h6_full3d_direct_result_v1.json](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_e3_h6_full3d_direct_result_v1.json) | `9d9ca31321dcacbc9ea9f40e814bf3e5f78de13bde85c33ea868dc353c7d3f8a` | own direct pass；best available discrete only |
| Hybrid direct M120/M240/M480/M960 T5 | [task039_t5_hybrid_direct_m_convergence_v1.json](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_t5_hybrid_direct_m_convergence_v1.json) | `9cab06e12a6958a7f187560f93f205c787b760d77ccfa9d808d1d5811f189165` | M480 own pass；M_robust_h10 not established；首轮 M960 pre-solution negative 保留 |
| Hybrid direct M960 E7 | [task039_e7_m960_direct_result_v1.json](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_e7_m960_direct_result_v1.json) | `3f879d292137cde013d438db1227ece72cc8e6a283a5dfe0c533eb2f9d7ad427` | own online Gate pass；`official_record=false` 仍表示 model/M qualification 未建立 |
| Full3D p6/h5 E4 preflight | [task039_e4_h5_full3d_direct_preflight_v1.json](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_e4_h5_full3d_direct_preflight_v1.json) | `fa57ed07c540b9f98334e565d3cc1f3153d39a897a2992367c2b745439ad6054` | 历史 `not_run_by_resource_policy`；V2 重新按 integer/resource readiness 审计 |

T3 的已解析物理身份为 5 nm、p6/h10、S、grazing=10°、phi=0°、MPI8、604 keys，
physical SHA 为
`db52c70d667caa726e2b2e04b646402415a377fa7bbcef42c87ffc816b9b2a7a`；其 source/input/
resolved SHA 仍以 T3 record 为准。h7.5/h6 的 mesh-dependent physical SHA 差异不被
解释为物理合同漂移；E5 已记录 `physics_except_mesh_exact=true`。各 record 的完整
身份字段不以本页的摘要替代。

## 3. h10 降级规则

从 Review V2 起，h10 的唯一新身份是：

```text
historical_underresolved_stress_anchor_only
```

| 禁止用途 | h10 状态 |
| --- | --- |
| Full3D 5 nm reference candidate | 禁止；`h/λ = 10/5 = 2` 的 fixed-grid stress 不代表离散收敛 |
| Hybrid 5 nm physical validation authority | 禁止；M480/M960 h10 只保留既有 diagnostic/solver evidence |
| 5 nm accuracy-qualified result | 禁止；h7.5/h6 对照已显示主体物理差异，弱通道也未建立完整收敛 |
| 0.7 nm mesh-scaling anchor | 禁止；0.7 nm 只能使用已审计的 derived component envelope，不能从 h10 精度外推 |

h10 历史 raw、T3/T4/T5 compact records 和原有负分类全部保留；本页不删除、不改写、
不重新解释这些结果。

## 4. 机器容量与运行时边界

### 4.1 已有机器身份

| 项目 | 值 | 口径 |
| --- | ---: | --- |
| physical memory | `256 GiB` | 任务书主机身份 |
| selected WSL MemTotal | `228.0657501220703 GiB` | 已测 selected limit |
| selected finite limit | `228.0657501220703 GiB` | V2 readiness 必须重新确认有效 |
| historical T3–T5 effective hard | `205.2591751098633 GiB` | `min(220, 0.90 × selected)`；仅历史合同派生值 |
| SwapTotal | `32 GiB` | 当前使用量为 0；不是无 swap 容量 |
| formal swap rule | `any use = immediate termination` | 所有 V2 heavy run 继承 |

### 4.2 Review 原合同与用户覆盖

Review V2 §4.3 对 h5 Full3D、§6.2 对 h5 Hybrid direct 原文规定：

```text
warning process-tree RSS = 170 GiB
hard-stop process-tree RSS = 195 GiB
any swap use = immediate termination
poll interval <= 0.25 s
timeout = existing h5 dat contract, at least 6 h
```

用户随后明确覆盖运行时绝对上界。该覆盖只作为本轮后续运行的执行口径，不回写或
弱化 Review 原文：

| 运行层级 | 实际策略 | 语义 |
| --- | ---: | --- |
| warning | `170 GiB` | Review 原 warning |
| critical checkpoint | `195 GiB` | Review 原 hard 数值；不自动终止，进入最高频 `<=0.25 s` 采样，并标记为被用户覆盖 |
| absolute termination | `224000000000 bytes` | 用户明确的 SI 字节绝对终止上界 |
| absolute termination (display) | `208.6162567138672 GiB` | 仅为 bytes/2^30 的展示值；机器字段保留整数 bytes |
| swap | 任意使用即终止 | 不因低于内存阈值而豁免 |

```math
\frac{224000000000\ \mathrm{bytes}}{2^{30}}
=
208.6162567138672\ \mathrm{GiB}.
```

因此 `195 GiB` 是 critical checkpoint 而不是本轮自动 termination；预测峰值高于
`195 GiB` 不再单凭预测值阻止启动。它仍必须被记录为预测，并不得绕过以下 readiness
条件：

| V2 readiness Gate | 要求 |
| --- | --- |
| selected memory | `MemAvailable >= 200 GiB`，且 selected finite limit 有效 |
| integer ABI | PETSc/MUMPS integer width 风险已审计，无已知不可恢复 overflow |
| disk | free `>=20 GiB` |
| input | validate-only 与 dry-run pass；冻结 dat 身份不变 |
| external inventory | exact 604 keys |
| concurrency | 同时只能有一个 heavy job |
| source/worktree | 指定分支、clean、source identity 可绑定 |
| swap | 使用量为 0 |

上述是 `user-overrides-review` 的执行口径：Review 原文的 170/195 仍作为审查基线
保留，用户覆盖只改变 critical-to-termination 的动作，不改变物理、solver、输入、
ordinary defaults 或证据分类。

## 5. V2-0 范围、停止和解锁

本轮仅完成 inherited/docs identity audit。V2-0 不启动 mesh、assembly、factor、solve、
field reconstruction、M480 Hybrid direct 或 iterative，也不读取 ignored raw 来补造新
数值结论。

V2 后续漏斗严格为：

```text
V2-0  inherited audit and h10 demotion       <- current docs-only stage
V2-1  h5 Full3D direct readiness / ABI/resource/integer audit
V2-2  one formal h5 Full3D direct MPI8 run
V2-3  h6-vs-h5 two-tier convergence
V2-4  h5 Hybrid direct M480 readiness/telemetry
V2-5  one formal h5 Hybrid direct M480 MPI8 run
V2-6  same-grid comparison and memory attribution
V2-7  conditional h5 Hybrid iterative M480 MPI8
V2-8  final comparison and response_v3
```

当前只解锁 `V2-1 readiness`，不解锁 V2-2 或任何后续 heavy run。以下情况在未来
readiness 或 formal run 中必须停止并保留真实证据：

- 任意 swap 使用、absolute RSS 达到 `224000000000 bytes`、launcher/MPI failure、
  MUMPS integer-width 风险或 numeric factor failure；
- input identity、604 keys、ABI、disk、selected-memory、clean/source Gate 任一失败；
- 资源或数值失败不得通过 OOC/BLR、替代 direct solver、降低精度、调 M、改 PC、
  改接口、增加 M 或静默 fallback 修复；
- 不得并发 heavy job、不得启动 M960/M>480 新运行、不得运行 Hybrid iterative MPI1、
  不得运行 h4/h3、完整 0.7 nm PDE 或 neural/learned factor 路线。

V2-1 之后的每个阶段须独立保留 compact evidence，并按用户授权提交推送；本页不
预写任何 h5 数值结果或后续分类。

## 6. 当前拟改文件与结论

| 文件 | V2-0 动作 |
| --- | --- |
| `docs/task039_5nm_hybrid_qualification_and_0p7nm_feasibility/outcomes/review_v2_inherited_audit.md` | 本页；唯一新增 docs-only evidence |
| Python、input、config/schema、tests、records、solver | 不修改 |
| `master`、其他 branch/worktree | 不触碰 |

结论：`V2_0_INHERITED_AUDIT_COMPLETE`。本页只建立可审计的继承身份、h10 降级和
用户覆盖后的运行时边界；它不代表 h5 已通过 readiness，更不代表任何 h5 formal
solve 已启动或通过。
