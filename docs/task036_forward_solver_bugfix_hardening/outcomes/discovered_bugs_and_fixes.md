# Task036 V2 discovered bugs and fixes

## 1. V2 启动时的已知状态

完整 B01–B11 before/after 见 `bug_port_matrix.md` 和 `fix_report.md`。V2 启动时，
与全域扫描直接相关的开放项只有：

| ID | 现象 | 当前状态 | V2 处置 |
|---|---|---|---|
| V2-B01 | Hybrid-P 调用处仍把 `modal_rank_sufficient=False` 写死 | raw shard 已改为 `pending_actual_M_convergence`；aggregate analyzer pending | 用同点相邻 M 的真实响应、interface、dual、biorthogonality 和 projection 判定 |
| V2-B02 | one-shot repair 只联合最坏的一对 blocks，误差会移动到另一组 | code fixed；PDE regression pending | 一次规划全部同方向、近 beta、超 overlap 的 connected components；全部预检 size/condition 后批量 joint inverse，再检查完整 row norm |
| V2-B03 | P 在 M120 下 interface/modal rank 不足，接近 full rank 时历史 energy 仍失败 | unresolved mechanism | 按失败簇运行 M120→240→480→full-rank，先区分 truncation、coupling 与 ledger |
| V2-B04 | 正式 Hybrid watchdog 不支持 p5 或动态 phi/height/width/Ny4，可能误绑定中心几何 reference | code fixed；PDE regression pending | 新增显式 Task036 opt-in；outer/worker 双重绑定 raw Full3D source、hash、p/h/MPI/S-P/角度/几何/topology/backend/projection |

## 2. full-suite 收口

V2 开始前的 full-repository pytest 已经结束：

```text
803 passed, 41 skipped, 3 failed in 2935.37 s
```

三个 failure 都不是数值 PDE failure：

1. B08 后的旧 telemetry 文案断言；
2. clean worktree 没有 checkout-local `.venv` 链接导致 ABI 路径误判；
3. numerical-blob checker 漏登记 QEP explicit residual helper。

前后两个由 `5231282f21e799c62b3a10ac1ccb1a8226935dc6` 最小修正，中间一项在
正确链接同一资格化 `.venv` 的 clean worktree 中通过。最终定向回归为 `59 passed`，
没有重跑 PDE，也没有虚写 full suite 零失败。

## 3. 新发现项

```text
V2-B04_port_gap_fixed_before_first_scan_PDE
```

后续每个真实失败必须在本文件记录：

- 首个复现配置和邻域；
- before 数值与冻结 Gate；
- 根因；
- 修改的通用算法；
- original、两个角度邻点、一个几何邻点、相反偏振 control 的 after；
- 是否仍需 M 漏斗或架构修改。
