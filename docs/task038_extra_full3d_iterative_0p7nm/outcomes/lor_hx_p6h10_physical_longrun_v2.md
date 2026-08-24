# P4 p6/h10 physical MPI1：未运行

| 字段 | 事实 |
|---|---|
| status | `not_run_by_gate` |
| 直接上游 Gate | P1 p3/h50 MPI1/random 在固定 cap 失败 |
| V9 授权边界 | physical workflow 与 official recovery 是条件授权，但因 P1 前置 Gate 失败未运行 |
| 实际范围 | 没有 exact volume+streaming DtN solve、release-before-recovery、E/H、R/T/A 或 energy closure |
| 资源 | 没有 `<2 GB` 完整 process-tree/cgroup authority，也没有 swap/physics result |

因此没有任何 official physics 数值可报告；完整 0.7 nm PDE 仍禁止。
