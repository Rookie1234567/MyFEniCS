# V2-A1 interface-Schur packet producer

## 结论

V2-A1 的唯一正式 producer 已在冻结的 MPI8 配置下自然退出，并由修复后的独立 checker
确认 packet 完整。它建立的是一个 hash-bound 的离散接口诊断/oracle packet：也就是把人工
截面上的精确接口信息保存下来，供后续 fresh consumer 审查。它不是可扩展的 side inverse，
不是完整 Hybrid workflow 的结果，也不是 V2-B consumer 的数值通过。

| 项目 | 实际结果 |
|---|---|
| producer source SHA | `942c43881e4162085348c48b09c79fbbdac18cd9` |
| checker-fix SHA | `bd70ab98009de2a2b45561793be6418a6a9bfcc8` |
| formal root | `results/task040_v2_interface_packet_producer_mpi8_942c4388` |
| MPI / threads | `8 / 1` |
| watchdog | `natural_exit`, `return_code=0` |
| process-sample wall | `1202.5501016210765 s` |
| peak RSS | `30,823,858,176 B = 28.706954956054688 GiB` |
| preferred资源线 | `<=45 GiB`，pass |
| absolute hard stop | `55 GiB`，未触发 |
| swap / status | `0 B / all_status_readable=true` |
| A2 fallback | `not_run_not_needed` |

这里的 RSS 是 watchdog 统一进程树口径；PSS/USS 没有记录，不能从 RSS 推算。28.7069 GiB
是本 producer 组件的峰值，不是完整 workflow saving tier。

## 冻结身份

| 身份 | 值 |
|---|---|
| input | `input/official/task039/5nm_p6h4_v4_1deg_hybrid_iterative_m480_mpi8.dat` |
| input SHA256 | `4e60924b5997e3ca99e324ea14779f9014efc6a1304a9aa11de9c808353f1811` |
| physical model SHA256 | `8391d46139646440d869aa43abe6a68bc921fc1972a10030c64be81dffdd527c` |
| selected packet manifest SHA256 | `2dddaf7a6f8f045adabd840970952517d76305c7c0e03c71258642d856c13067` |
| V1-2 probe manifest SHA256 | `7a03b2cf80fe5081d1fe1248b9d4c79f3ef4e955a8014e905c2f2ca82797baad` |
| exact-spool catalog SHA256 | `a2a7fb6fb01df4f795d31ff94f6ac6adf957ac4fe4a5c1a8d05176e3d64c0384` |
| lower resolved mode metadata | `dde523dc62c73f7bd50953958fde42d42d0cfd5756c16329b16915e13c4742da` |
| lower legacy opaque beta identity | `a58a3c6bc335bb5ae7f6b929a7abce4c193dedb27b115f17304091afb353318c` |
| upper mode-key / beta SHA256 | `089d6abfac9f482e7f6001988b9d1c12b1721c09a86749cdefcbfc4f22e82673` / `aee266f602bf704ffbc3d7551be661b05e1663f84205012bfe26c8fd5983f6c9` |

QEP calls 为 `0`，PDE solve、FGMRES 和 V1-3 均为 `not_run`。五个 frozen exact-output
identity 已逐项写入 compact record，未用 RHS 冒充 physical trace。

## Packet 内容与接口尺寸

packet manifest SHA256 为
`19de50f3cdb32766bf6f13fc55c9ac498b21a9a00ddc261768d7d55b7c9da8b0`。目录共 34 个文件、
653,804,117 B，其中 24 个是 8 个 rank × 3 个 group 的 owner-row shard，另外 9 个是小型
Gram/projected 矩阵，最后 1 个是 manifest。

| group | 全局 Gamma row 数 | modal span | Gram rank | Gram condition |
|---|---:|---:|---:|---:|
| group0 | 7,560 | 296 | 296 | 187.9352369709664 |
| group1 | 15,120 | 776 | 776 | 1,075,856.58741676 |
| group2 | 7,560 | 480 | 480 | 113,913.61949721041 |

独立 checker 复核了 15 条 physical reports、8 条 interface reports、8 条 middle-cross
reports，其中 complement 为 4 条。所有报告和小矩阵有限；`max_projected_exact_relative`
为 `1.0281892054707484`，这里只是 producer diagnostic scalar，不能当作 V2-B 的
side-transmission Gate，也不能据此判定 mechanism 通过或失败。

三组 canonical row-to-owner mapping hash 已由 compact record 保存并绑定。

producer 的离散 Schur 关系仍是：

```math
S_\Gamma=A_{\Gamma\Gamma}-A_{\Gamma I}A_{II}^{-1}A_{I\Gamma}.
```

生命周期证据为 exact oracle factor `3 -> 0`，simultaneous factor maximum 为 3；
full-side、global direct、nested KSP 均为 `0/0/0`。manifest 和 checker 同时确认：

- `dense_schur_materialization=false`；
- `basis_global_replicated=false`；
- `numeric_allgather=false`；
- `fe_numeric_allgather=false`。

因此 packet 保存的是 owner-row 的 finalized U/V 与小矩阵，不是每个 rank 的完整 FE basis。

## 首次 checker implementation failure 与修复

producer 本身已自然退出并完成 packet；首次 checker 失败是 checker/schema 接线问题。真实
producer 的 physical report schema 没有 `finite` marker，但其明确的 norm、relative 字段和
六个 complex contractions 全部 finite。旧 checker 把 physical/interface report 统一要求为
`finite=true`，因而在未进入任何 V2-B 数值判断前错误退出。

该失败现场仍保留在 formal root：首次空输出
`checker_recomputed.json` 的 SHA256 为
`e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`。修复仅让 checker 对
physical report 检查真实存在的 finite 数值字段和 contraction pair；interface/middle 的
既有 `finite=true` 合同保持不变。修复后 test306 在 serial、MPI2、MPI4 均为 `6/6 passed`，
fresh checker 返回 `0`，输出文件
`checker_recomputed_after_fix.json` SHA256 为
`3af14190afd9b8e84a2529bf63f2bda348d465d0d47bba166c3682a0b2b32536`，所有独立 checks
通过。这个问题是 checker implementation failure，不是 producer、接口数学或算法负结果。

## 证据索引与边界

精确 compact record 见
[task040_v2_interface_schur_packet_producer_v1.json](../../../benchmarks/cases/104_5nm_hybrid_side_factor_pc/records/task040_v2_interface_schur_packet_producer_v1.json)。
formal root、shards、watchdog、markers、process samples 和两次 checker 输出仍在 ignored
`results/` 中，未提交 raw。

V2-A1 只证明了 packet 可以在 preferred 45 GiB 内完成并通过独立身份/完整性审计；它没有
证明 fresh consumer 的 remap、projected transmission、FGMRES 或完整 Hybrid。V2-B 仍为
`pending`，历史 V1 resource stop 也保持原分类，不被本次 producer 结果覆盖。
