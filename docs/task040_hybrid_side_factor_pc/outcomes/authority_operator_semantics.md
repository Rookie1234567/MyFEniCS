# V5-1 operator semantics audit

## 当前状态

`completed_with_route_c_followup`。本审计只确认 source/operator 的含义和证据绑定，不把静态
审计本身当成 bare-`F` 数值资格。正式 Route C 的独立 checker 结论为
`VALID_NEGATIVE_ROUTE_C_NO_SIGNAL_RESOURCE_AUTHORITY_GAP`；下游统一为
`not_run_by_route_c_no_signal_and_resource_authority_gate`。

## old 与 current 的区别

这里的“operator semantics”回答的是：一个 RHS 和一个解究竟是给哪个算子用的。旧 spool
来自带外部耦合的 side action；current Route C 则只把显式 current bare `F` 作为求解算子，
外部 RHS 只构造生成该 RHS 所需的最小表面分量。

| 项目 | frozen old authority | current V5 path | 证据 |
|---|---|---|---|
| action/operator | `ResearchExactSideLuAction`，Woodbury-associated；不是已证明的 bare `F` authority | `explicit_current_bare_F` | `worker/operator_semantics_audit.json`、`worker/run_summary.json` |
| modal `+/-` RHS | `setup.coupling.bottom.positive_traction/negative_traction` columns 281/283；`full3d_one_cell_exact_schur` | 同一 frozen full3d one-cell source definition 的 current-layout selected columns；未用 scalar-CG 替代 | audit `old_rhs_source_definitions` / `current_rhs_source_definitions` |
| external RHS | old pre-action `components.C` column | `current_external_minimal_surface_components`；traction coefficients，未物化完整 C/D/H | audit 与 `external_dtn_coupling` inventory |
| random RHS | old owner-row formula | current canonical active-trace formula | audit source definitions |
| QEP / physical DtN | old history may be associated with side construction | `qep_calls=0`；physical DtN、Woodbury、C/D/H 均未构造 | system-ready marker、run summary |
| runtime qualification | old raw values不跨布局重用 | 仍需 primal identity、RHS repeat、lifecycle、bare-F true residual；本次 Route C 不消费 exact packet | audit `runtime_qualification_required=true` |

V5 的一次最小 source identity 修复是：保留 frozen `full3d_one_cell_exact_schur`，只生成
selected positive/negative columns 281/283；一次 one-cell source factor 生命周期先完成并销毁，
再进入 bare-F factor/consumer 顺序。该修复没有把旧 side action、Woodbury inverse 或
physical `C-D-H-W-K` 变成 current solver。formal Route C 最终没有建立 full-side exact factor。

## 证据身份

| 字段 | 值 |
|---|---|
| formal source | `b5b765ef02d52a877184b14fb8d72ad16a0432f8` |
| operator audit schema | `task040.v5.operator_semantics_audit.v1` |
| audit raw file | `results/task040_v5_route_c_online_long_fgmres_mpi8_b5b765ef_retry1/worker/operator_semantics_audit.json` |
| audit file SHA256 | `e7bfe8258dc359bd1fd58e31d3237e5dde6eebc47dc31985493faf378b0f5a91` |
| current core evidence | `src/solvers/hybrid_bare_f_authority.py::run_current_bare_f_authority`，raw file SHA `c468392a50d671a2cb2bbddc9d4d55400bb2de17554ddf772b2f549071fee24a` |
| one-cell source evidence | `src/coupling/hybrid_one_cell_exact_traction_builder.py::build_exact_one_cell_selected_traction_columns`，raw file SHA `1bfda326a1b149cf572adee2f45676cbfbf2869cfb59e3bf6dcc222dde3c3c59` |
| old action evidence | `src/solvers/hybrid_local_dtn_woodbury.py::ResearchExactSideLuAction`，raw file SHA `45e42557482f0b4e1ce6068b6c9fb19762708b4ec0f4579eb90a3731f5f7285e` |

`modal_source_identity.pass=true` 和静态路径通过只表示 source definition 与证据路径已经
绑定；它不能替代 runtime factor lifecycle 或 numerical residual。Route C 的实际 Gate 由
独立 raw checker 重算，且只采样 external 与 `fixed_random_repeat_0`。

## 边界

旧 raw global row 不作为 current input；旧 side action/exact spool 也没有成为 Route C 的
运行时依赖。V5-2 的 fresh bare-F exact authority 因授权的 21600 s factor-construction
窗口耗尽而 resource-blocked，未生成可供 consumer 使用的 exact packet。因此 exact trace/lift、
bounded online reconstruction 和 production side inverse 均不成立。
