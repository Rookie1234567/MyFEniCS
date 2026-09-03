# V17 M0：机制预审与 Oracle A/B 合同

本文件是 V17 实施前的轻量冻结记录，不是正式 PDE 或 solver 结果。当前源码身份为
`be67787d1237e8676b33f91f28c7b0ffcb3fe06a`，分支为
`codex/20260820-task38-extra-full3d-iterative-0p7nm`；输入、物理模型和 80-mode
清单的 SHA 分别为 `819fc99caea2dbc8ea22546917fbe3898c822a955d079b4582c4a27e34ebba41`、
`9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f` 和
`dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2`。

## 已冻结的边界

V16 Q1.1/Q1.2 是已接受的 identity/小型 inner evidence，Q2
`Q2_PHYSICAL_PCOARSE_REFERENCE_NUMERICAL_GATE_FAIL` 和 W0
`W0_INTERFACE_RANK_CAPACITY_FAIL` 保持原样；official physics、Q3–Q6 与 W1–W4
仍未运行。V17 不增加 Q2 inner steps，不改 restart、shift、smoother 或 p-level，
也不重新开启 Robin/PML/Schwarz/interface-Schur 路线。

迁移前当前分支没有可直接采用的 disk-backed module；本回合新增的实现只保留必要的
通用诊断接口。历史可读参考为 commit
`ab34d3b1b327fece576448984320e185af32b7eb` 的
`src/solvers/disk_backed_flexible_gmres.py`；它只支持 `max_steps<=200`，并把
12 个 full-vector buffer 写入 audit，故这里只迁移“通用诊断组件”的思想，不迁移
旧 runner、campaign 或 evidence。可复用的当前 API 是
`build_p6_same_mesh_setup`、`build_same_mesh_physical_action`、
`read_solution_checkpoint`、`run_restart20_cycles`、owner-local `P63` transfer 和
已资格化 positive pMG；它们分别保留 mesh/MPC、精确 physical action、checkpoint
authority、restart-20 生命周期、分布式 transfer 与冻结的 local inverse 语义。

## Oracle A：精确 p3 coarse-span

A1、A2、A3 是同一 parent 下顺序退出的三个 heavy child：A1 从只读
`checkpoint-1000` 重建 `A6/b6`，写 `r6` 与 `r3=P63^H r6`；A2 只构造与
matrix-free A3 相同的 p3 `A3`，先做一次 MUMPS symbolic analysis，再在预测峰值低于
硬线时做唯一 numeric factor/solve；A3 在 A2 完全销毁后计算
`e6=P63 e3`、`r6_new=r6-A6 e6` 和 `r3_new=P63^H r6_new`。固定公式为：

```text
A3 e3 = r3,    rho_ref = ||r6_new|| / ||r6||,
rho3 = ||r3_new|| / ||r3||.
```

默认不启用 static condensation；若后续代码证明现有 exact condensation 可直接复用，
才记录 `static_condensation_used=true`，否则以完整 p3 assembled diagnostic matrix
为准，不创建 production LU/PC。MUMPS raw `INFOG/RINFOG` 必须原样保存；analysis-only
阶段不调用 numeric factor 或 solve。阈值在 formal 前冻结为 p3 explicit true residual
`<=1e-10`、`rho3<=1e-6`、`rho_ref<=0.70`。

Oracle A 的 process-tree warning/hard 为 `10,000,000,000`/
`12,000,000,000 B`，swap 必须为零；A2 factor 仅在预测峰值严格低于 hard line 时运行。
三个 child 的完整源码、checkpoint、canonical key 和 input identity 相同，A2 factor
在 A3 启动前释放。任何路径、缓存、ABI、生命周期或 provenance 错误是工程重试项；
实际 residual/rho/resource Gate 才能停止该 oracle。

## Oracle B：同源的 restart 与 unrestarted 对照

B 从同一 checkpoint、同一 `A6` matrix-free physical action 和同一 positive pMG 出发，
只比较 500 个 continuation steps：reference 是 right `GMRES(20)`，对照是一次不重启
的 right flexible GMRES。两者都每 20 步用 exact action 计算 true residual；reference 的
residual replacement 只属于它自己的 restart cycle，unrestarted Arnoldi recurrence
不能在 20 步处清空或替换。

`V[0..500]` 与 `Z[0..499]` 放在两个 exclusive positional raw files 中。每列写完后按
固定 20 列 cadence `fdatasync`，basis 不使用 mmap，也不保留 Python/PETSc full-vector
list；MGS 对每个新方向固定做两遍，旧 `V` 每次只读一列，solution 重建逐列流式读
`Z`。disk Arnoldi algorithmic full-vector window 固定上限为 8，并在 raw audit 中记录
实际生命周期计数；这不是对 PETSc/bundle 内部所有向量的总内存声明。完整 process 的
同时峰值由 process-tree RSS `<2,000,000,000 B` 实测 Gate 约束。小型 Hessenberg 在
RAM，full basis 只在 ignored scratch；formal 前 free disk 必须至少 10 GB，swap=0。

正交缺陷和 explicit true residual 对 Arnoldi residual 的相对闭合阈值在此冻结为
`1e-8`，不会看到 formal 曲线后调参。两条曲线的独立 checker 由 raw norms 重算，
只使用固定分类：`R_unrestarted(500)/R_GMRES20(500)<=0.1` 为 strong，`<=0.5`
为 weak-only，其余为 no-contraction；未达到 `1e-6` 本身不构成 B 失败。

## M0 状态

本回合只完成代码接口、纯 focused qualification 和 compact provenance 文档；A1/A2/A3、
GMRES20-500、unrestarted-500、PDE、official recovery 均为 `not_run`。后续 runner 只
负责 fresh root、七组 cold staging、逐 child watchdog、marker 和 raw file；checker 只
读 raw、重算 norms/hashes/relative 与 0.1/0.5 分类。该 preflight 不授予任何数值或
资源 PASS。
