# Next Decision

## 推荐决策

1. 接受 task010 的 production candidate：`iter_fgmres_mumps_blr_eps1e-5`。
2. 当前本机不再硬推 p=2/h=1.5；它已经在 KSP setup 阶段被 signal 9 kill。
3. 工作站第一任务应跑 p=2/h=1.5、eps=1e-5；若通过，再跑 h=1。
4. `eps=1e-4` 作为备选 profile；`eps=1e-3` 不作为主路线。
5. shifted/positive minimal P 不作为 production solver，只保留为 HX/AMS 和 block preconditioner 的基础设施。

## task011 建议

优先级 A：工作站 MUMPS-BLR 验证与 compression ratio 采集。

优先级 B：完整 H(curl) AMS/Hiptmair-Xu auxiliary-space 预条件器设计。

优先级 C：FE/aux block Schur 结构化预条件器。
