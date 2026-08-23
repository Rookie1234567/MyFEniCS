# V8 M1：memory-first small

| 项目 | 状态 |
|---|---|
| 运行状态 | NOT_RUN_BY_M0_HARD_STOP |
| 原因 | M0 已发现 transfer/MPC/owner algebra mismatch，V8 §12 禁止继续 |
| 实测内存 / swap | 无；不得从 M0 小诊断外推 |
| 证据 | lor_hx_mpi2_root_cause.md |

本文件不构成 memory budget、2GB qualification 或 small positive pass。
