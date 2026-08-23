# V3-0 联合接口路线继承审计

## 状态

本页是 V3-0 的 docs-only 继承审计。V3-1 及以后尚未运行；本页不构成数值通过、生产资格或
0.7 nm 资格。当前提交只绑定已经完成的 V2 证据，不修改任何 V2 raw artifact。

## 分支、审查与环境身份

| 项目 | 值 | 证据/口径 |
|---|---|---|
| 分支 | `codex/20260822-task40-hybrid-side-factor-pc` | 当前 worktree |
| HEAD / upstream | `4db54f179aa6327ee26d96a9e848a12fd52aa208` / 同 SHA | fast-forward 后核对 |
| ahead/behind | `0/0` | `git rev-list --left-right --count` |
| worktree | clean | 未修改、无 nonignored untracked |
| review V3 SHA256 | `e613214912a3d2404f18e51c75235f29414d5d0733ba1d6f4b8d7e6b72d0632e` | `review_report_v3.md` |
| qualified activation | `_MYFENICS_WSL_QUALIFIED_ACTIVATION=1` | V3-0 preflight |
| Python / scalar / PETSc IntType | repo `.venv` / `complex128` / `int32` | 同一 Linux ABI 栈 |
| 物理身份 | 5 nm / 1° grazing / phi=0 / S / p6h4 / M480 / MPI8 / threads=1 | V2/V3 冻结 |

Task40 目录没有独立 `README.md`、更深层 `AGENTS.md` 或补充任务书；本轮以根规则、
`task.md` 和 `review_report_v3.md` 为权威。Case104 documentation-contract 的 numbered-case
whitelist 缺口是既有 active-case registration gap，本轮只记录，不修改测试架构。

## V2 继承证据

| 证据 | 结果 |
|---|---|
| producer source | `942c43881e4162085348c48b09c79fbbdac18cd9` |
| consumer numerical source | `40b25d3281d9ce1707f6069607bfdbbf6a3ab48d` |
| consumer telemetry/checker fix | `0919ed2fa3bd1541f543057721fff84fa110f3d4` |
| packet manifest | `19de50f3cdb32766bf6f13fc55c9ac498b21a9a00ddc261768d7d55b7c9da8b0` |
| input SHA256 | `4e60924b5997e3ca99e324ea14779f9014efc6a1304a9aa11de9c808353f1811` |
| physical SHA256 | `8391d46139646440d869aa43abe6a68bc921fc1972a10030c64be81dffdd527c` |
| selected manifest SHA256 | `2dddaf7a6f8f045adabd840970952517d76305c7c0e03c71258642d856c13067` |
| V1-2 probe manifest SHA256 | `7a03b2cf80fe5081d1fe1248b9d4c79f3ef4e955a8014e905c2f2ca82797baad` |
| exact-spool catalog SHA256 | `a2a7fb6fb01df4f795d31ff94f6ac6adf957ac4fe4a5c1a8d05176e3d64c0384` |
| producer compact record SHA256 | `1b271f694621b9c8781712e835af6ce3c675ded578764ffefbec736fcf228da9` |
| consumer compact record SHA256 | `d08e8fe8559384284bcd5f2c160ceb81e8a67104f4378705fcf4b3f836d3bc7a` |

V2 producer 是 diagnostic/oracle authority：峰值 `28.706954956 GiB`，packet 完整，exact
oracle lifecycle `3 -> 0`。V2 consumer 峰值为 `32.453453064 GiB`，remap、identity、
implementation subset 和 cleanup 通过；五个非零 source 的 `r16` 均为 `0.99365–0.99647`，
conditional 32 未授权，分类为：

```text
THREE_GROUP_MODE_SUBSPACE_OR_SWEEP_INSUFFICIENT
```

producer/consumer 峰值是独立 component 进程数据，不能相加为完整 workflow saving。继承的
完整 workflow 基线仍为 direct `93.377006531 GiB` 和 exact-side iterative
`80.025856018 GiB`。

## V3 冻结和边界

继续冻结：物理、材料、几何、Floquet、p6/h4、M480、lower 296、upper 480、selected mode
keys/beta/normalization、bare `F`、physical DtN、global Hybrid operator、recovery/physics
checker、MPI8/threads1。V3 只允许改变人工接口信息的组合方式：从三个 independent projected
inverse + sweep 转为一个 lower/upper 联合 reduced interface solve。

联合 776 维系统只属于 mechanism oracle。最终 candidate 仍必须满足 bounded coarse rank、
无 full-side/full-cross-section factor、`max_local_rows <=1024`、无 FE numeric allgather、
无每 rank 完整 basis replica 和近线性 PC resident growth。

禁止：改变 mode count/span、调 beta/sign/damping/sweep/restart/tolerance、改变分区或新建
coarse family、重跑/修改 QEP/M/physical DtN/global Hybrid、重跑旧 direct/exact-side
authority、运行完整 0.7 nm PDE、修改 ordinary defaults、写 master/Task039。

## V3 阶段状态

| 阶段 | 当前状态 | 本次是否运行 |
|---|---|---:|
| V3-0 inherited audit | `docs_completed_pending_review` | 否（仅只读 preflight） |
| V3-1 packet-only coupled algebra | `pending_conditional_not_run` | 否 |
| V3-2 full-span mechanism oracle | `pending_conditional_not_run` | 否 |
| V3-3 bounded-rank coupled coarse | `pending_conditional_not_run` | 否 |
| V3-4 packet-independent production | `pending_conditional_not_run` | 否 |
| V3-5 bounded local patch Level B | `pending_conditional_not_run` | 否 |
| V3-6 bottom/top/both/full Hybrid | `pending_conditional_not_run` | 否 |
| V3-7 h3 scalability probe | `pending_conditional_not_run` | 否 |
| V3-8 evidence/response | `pending_closeout` | 否 |

V3-0 的可交付物只包括本页及同一批 V3 outcome 占位/边界说明。没有 V3-1 numerical claim。
