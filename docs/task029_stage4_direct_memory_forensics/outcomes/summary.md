# Task029 当前总结

## 最新状态

Task028 已合并并通过 master release check；Task29 已从 merge commit `2f9e56d2edddb801780504f681b2ff295d993e02` 建立独立分支。主任务书、COMSOL 强制补充、COMSOL 参考报告和 Task28 最终闭环均已阅读。Commit A `8401b44` 已加入可开关的外部采样、阶段 checkpoint、PETSc matrix/factor inventory 和 raw MUMPS API 遥测；物理配置、direct profile 与 ordinary default 未改变。尚未运行 h5/h3，h2 保持锁定。

## 环境边界

容器镜像为 `myfenics-stage4:task28@sha256:08c61b2cde742442b0031437dbc5160db979494587e6b6364f7935beb29dd76d`。WSL 可见内存约 13.65 GiB，cgroup 未另设硬上限。当前主机只有 16 GB 级物理内存，因此 h3 前必须确认无交换压力，h2 仅可在任务书全部解锁 Gate 满足时运行。

## 比较原则

主比较只使用同一 FEniCS target 的 Task28 baseline 与 Task29 candidate。COMSOL 的 22.989 GB direct 与 8.992–13.376 GB GMG 结果只作为另一机器、自由四面体、P 偏振、零级端口的定性架构参考，不能作为 FEniCS 的时间、RTA 或每 DoF 效率基准。

详见 [COMSOL 比较边界](comsol_reference_comparability.md)。

## Stage A 验证

Docker 完整轻量回归为 123 passed / 10 skipped，Benchmark checker 为 149/149；ruff、compileall 与文档合同均通过。基线前审计还确认 Task28 原生命周期会让 KSP/factor、system Mat、RHS 和 solution Vec 在 postprocess 期间继续被引用；Commit A 没有提前释放这些对象，避免把基线测低。
