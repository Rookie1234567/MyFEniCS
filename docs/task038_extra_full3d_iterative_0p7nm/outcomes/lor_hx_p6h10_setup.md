# V8 M2：p6/h10 setup

| 项目 | 状态 |
|---|---|
| 运行状态 | NOT_RUN_BY_M0_HARD_STOP |
| p6/h10 mesh、setup、retained closure | 未运行、无数据 |
| 2GB / swap Gate | 未验证 |
| 原因 | M0 hard stop 锁定 M1–M7 |

不得把 p2/h50 M0 的单进程 RSS 当作 p6/h10 setup 结果。详见 lor_hx_mpi2_root_cause.md。
