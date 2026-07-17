# Task033 阶段性回复 V1

## 范围调整

2026-07-17，用户决定缩小 Task33：保留 p3/p4 高阶扩展与 Hybrid/直接 3D FEM
对比总结，自适应及其后续优化延期。正在运行的完整 campaign 已安全终止，遗留 Docker
容器已停止。停止原因是范围调整，不是 OOM、崩溃或 Case090/QEP 运行失败。

## 已完成并保留

1. clean source `6613f94b91ebc77eb50e74086475c67df46236f6` 上的高阶实现、测试与正式计算；
2. Case090：MPI1/2/4 各 48、合计 144 个直接 3D PDE，p3/p4 核心 Gate 全过；
3. QEP：MPI1 36/36 分片通过，其中 p3/p4 为 18/18；
4. Task032 p2/h5、p2/h3 Hybrid 与 full3D 的同阶同网格对比；
5. 负结果：QEP aggregate 未资格化、p1/h5 modal capacity、p3/p4 Hybrid reference 缺口。

## 计算暂停的准确位置

完整 campaign 的进度依次是：

1. Case090 MPI1/2/4 已全部结束：每组 48，总计 144；
2. QEP MPI1 36/36 已结束；MPI2/4 两个 timeout-negative 已结束；
3. Hybrid uniform `p1/h5` 的 M80/M120/M160 已结束并生成 funnel；
4. Hybrid uniform `p1/h3` 的 M80、M120 已结束；
5. `p1/h3/M160` 已运行到 `middle_plane_reconstruction`，此时收到范围调整并终止；
6. p2/p3 uniform、anchors、graded/adaptive、buffer 与 aggregates 尚未开始。

终止的 `p1/h3/M160` 没有完整 solver record、watchdog summary 或 funnel aggregate，
不会作为正式数据引用。Docker 计算容器已停止。

## 主要结论

- p3/p4 双 Floquet 直接 3D FEM 扩展成立，保持稀疏分布式约束与 MPI 一致性；
- p4 在解析 fixture 上有明显精度收益，但 DoF、NNZ 和时间代价显著增加；
- p3/p4 QEP 单项数值链成立；全局 aggregate 仍受低阶趋势/跟踪和 p4 一项 overlap Gate 限制；
- Hybrid p2 M160 在 h5/h3 将行数降低 68.62%/65.35%，NNZ 降低 59.14%/59.68%，
  最大 R/T/A 差为 `2.07e-6`/`2.63e-6`；
- 目标光栅没有 p3/p4 同阶 full3D reference，所以没有跨阶冒充高阶 Hybrid 等价性。

## 延期项

uniform p/h 全矩阵、graded/adaptive h、equal-accuracy、variable-p/hp zoning、interface
buffer、1 TiB/0.7 nm 推演以及完整 21-role formal closure 均标为
`deferred_by_user_scope`。原 `task.md` 和 `formal_evidence_manifest_NOT_RUN.json`
保留不改，未来可从这里恢复。

## 后续是否需要补算

就当前交付而言，不需要。p3/p4 直接 3D 高阶能力与 p2 Hybrid/full3D 对比已有足够证据。

若要把结论升级为“p3 Hybrid 与同阶 full3D 等价”，最小补算为：

1. p3/h5 目标光栅 direct full3D reference；
2. p3/h5 Hybrid M80/M120/M160 漏斗；
3. p3/h5 augmented-vs-Schur-minimal anchor；
4. 同阶 R/T/A、interface E/H、选定平面 E/H 与资源对比。

p4 目标光栅只建议在 p3 通过且资源预测允许后再做。QEP aggregate 则应先用现有数据
诊断 branch tracking；只有修改算法后才需要复算，先复测失败组合，最终正式聚合再跑 36 项。
自适应工作不建议现在恢复。

如果以后恢复原 Task33 完整 campaign，应选择一种干净方式：要么在独立 worktree
checkout `6613f94...` 复用现有 step markers，要么在新 SHA 上接受 Case090/QEP 的完整重跑；
不要把两个 source SHA 的正式证据混成一个 manifest。

## 请求复审

请重点核对三条边界：

1. Case090 是每 MPI 48、总计 144，不是 192；
2. QEP MPI2/4 的 1 秒 timeout-negative 不是正向资格；
3. Task032 p2 Hybrid/full3D 对照不能被写成 Task33 p3/p4 同阶对照。
