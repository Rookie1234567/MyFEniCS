# M2c never-materialized screen-20

## 结论

本次是唯一一次 M2c p6/h10、13.5 nm、S、MPI8、20-step screen。结论为：

**架构 Gate pass、数值早期下降可信、resource negative。**

这不是 production-qualified 结果，也不授权新的 PDE、M3 或 M4 运行。

## 身份与命令

| 项目 | 值 |
|---|---|
| source / branch | `a9a141f1bc55f8fe3f70587681f8d23eba9bc474` / `codex/20260803-task37-matrix-free-iterative-development` |
| geometry | p6 / h10 / 13.5 nm / theta normal 80° / phi 0° / S |
| backend / MPI | `assembly_time_static_condensed` / 8 |
| profile | `never_materialized_owner_local` |
| artifact | `benchmarks/artifacts/cases/100_static_condensed_full3d_iterative/m2c_never_materialized_screen20_p6_h10_mpi8_a9a141f1` |
| authority | `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/global_hexa_p1_p6_h10_p6_assembly_time_condensed_independent_mpi8.json`；SHA256 `96ac3949efc236393d4c2dbc6e1fa334ad5ccb0e9796bdeba13fbe0515577dd8` |

实际命令沿用冻结的 Task033 watchdog，只增加
`--task037-f3-screen 20 --task037-m2c-never-materialized`，并使用
warning/termination `10/14 GiB`、timeout `1800 s`。

## no-global 生命周期证据

runtime nested audit 记录：

- `cell_static_condensation.action_only_setup=true`；
- `global_A_materialized=false`、`global_F_materialized=false`；
- `base_matrix_was_never_allocated=true`、`full_global_matrix_allocated=false`；
- partition `matrix_materialized=false`，16 个 owner-local slabs；
- 16 个 factor-only ILU factors，14 个 unique factor classes，factor NNZ `103,336,560`；
- assembly order `two_color`，smoother 为 2-step GMRES，coarse dimension 75；
- `global_direct_factor_count=0`、`global_schur_matrix_materialized=false`。

trace preallocation、插入和最终 assembled matrix assembly 均为
`not_run_action_only`。这些是 nested runtime/core 证据；watchdog 修正前的三个
summary Gate false 是 checker 读取错误层级造成的，不是重新求解得到的证据。

## 残差与 F3 对照

| iteration | M2c reported / condensed true | F3 assembled condensed true |
|---:|---:|---:|
| 0 | 1.0000000000 / 1.0000000000 | 1.0000000000 |
| 10 | 0.1212492053 / 0.1212492053 | 0.1132017979 |
| 20 | 0.0341112948 / 0.0341112948 | 0.0302833466 |

M2c 残差确实下降，但 20 步仍为 `DIVERGED_MAX_IT (-3)`，没有达到正式
`1e-6` residual Gate。reported、condensed 和 full-augmented residual 最终均约
`0.0341112948`。因此 official RTA 为 `not_run`，没有 official field output。

## 资源、节省比例与耗时

| 项目 | M2c observed |
|---|---:|
| process-tree RSS authority | `12474.01171875 MiB = 12.1816520691 GiB` |
| worker RSS / PSS / USS | `12459.3828125 / 11163.41796875 / 10968.12890625 MiB` |
| swap | `0 MiB` |
| resource Gate | `negative`：`12.1816520691 > 10.30 GiB` |
| core setup / solve / recovery | `138.1064 / 14.8450 / 0.0276 s` |
| stage4 assembly+solve / whole wall | `251.7166 / 261.4332 s` |

与既有 authority 对照，M2c 相对 F0 的 process-tree memory authority
`15.2550010681 GiB` 节省约 `20.15%`，相对 F3 的 `13.6522331238 GiB`
节省约 `10.77%`；但仍高于 `10.30 GiB`，不能称资源 Gate 通过。

## checker 重评与证据边界

原始 watchdog 结果为 `task037_m2c_never_materialized_screen_not_pass`。
离线使用修正后的判定器读取同一 `run_summary.json`、`task037_f3_core_audit.json`
和 resource authority 后，`action_only_setup`、summary A/F=false 三项变为 true；
最终仍因 `memory_authority_gib=12.1816520691` 保持 `not_pass`。原始 raw
evidence 未修改。

记录的证据 hash：

- solver summary：`7572ee7fcff05bb2671ed6e451f95b8770500e111d01f68df338dc46d060f474`
- progress：`edd9f5444cef15c81c5490fe6248c4fbbf8995e46f69423c6a85c8075c0eec52`
- memory timeline：`e9eb344c6df35f26e1729f0f11e53faa298158523a78506e72dcaced35defe7d`
- worker stdout：`7464f98d78c55262f6dcc799befea00409d23937bb1defe35ac90d66333fd796`

本 screen 只证明当前架构路径的 setup/lifecycle 与早期残差下降事实；它不证明
20 步收敛、低于 10.30 GiB，也不证明 production-scale 或 0.7 nm 可用。
