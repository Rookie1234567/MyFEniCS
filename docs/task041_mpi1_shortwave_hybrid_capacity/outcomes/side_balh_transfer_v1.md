# Task41 BAL_H 对照合同（v1）

BAL_H 用侧区的平衡响应近似替代昂贵的侧区精确逆。它只改变预条件器对侧区响应的求法，不改变原始全局矩阵、右端项或正式物理量的定义；`exact` 结果仍是右侧参照，`candidate` 结果在左侧。比较器只读取已完成运行留下的原始文件，独立重算门槛，不把记录中的 `pass` 字段当作证据。

## 冻结的数值口径

- `R/T/A_balance/A_volume` 的绝对差上限为 `1e-8`。
- 选定平面上的 E、H 使用相同 key 的 L2 差，分母为 `max(norm(candidate), norm(exact), 1e-30)`，相对上限为 `1e-6`；同时记录绝对 L2、最大绝对差和单位（E 为 V/m，H 为 A/m）。不做相位拟合。
- bottom/top 的 `active_trace` 与 `full_fe` 四组 canonical owner-shard 使用分母 `max(norm(exact), numpy.finfo(float).tiny)`，相对上限为 `1e-5`，并保留绝对 L2 和最大绝对差。空的 owner shard 不能单独证明完整向量存在；manifest 的 count、非空 shard 和唯一 key 必须一致。
- 每个外部 channel 都列出两边的 raw power、complex amplitude、绝对差、相对差和 significant 标记。任一边的 power 达到 `1e-8` 时，power 与 amplitude 的相对上限为 `1e-6`；分母分别是两边 power 或两边 amplitude 绝对值与 `1e-30` 的最大值。低于显著性线的 channel 仍保留为诊断。
- normal flux 定义为 `0.5 Re((E cross conj(H))_z)`，按各 plane 汇总；相对 L2 分母为 `max(norm(candidate), norm(exact), 1e-30)`，上限为 `1e-4`。
- 方法自身的 reported/global/bottom/top/modal explicit residual 上限为 `5e-9`；projection 与每侧 exact traction 上限为 `1e-8`，external-q identity 上限为 `1e-10`。`abs(A_balance-A_volume)` 与 `abs(R+T+A_volume-1)` 上限均为 `1e-5`。只有通过自身 residual gate 的场才有资格成为 official field identity。

## 资源和耗时口径

比较器使用 `public_root/numerical_output/log/memory_stages.jsonl` 的 raw samples，以及同一 public invocation 的 supervisor summary。峰值主口径是 public Python launcher 及其全部后代的 process-tree RSS；可读的 PSS/USS 作为附列指标，缺测保持 `None`。job swap 必须为零，global swap 的既有基线与本次 used、pswpin、pswpout 增量分开检查；共享 cgroup 历史不能冒充本任务峰值。384 GiB reserve、profile hard cap 和 phase/batch wall limit 以当前四个 Task041 profile 的冻结合同为准，不能信任被篡改的结果内限值。

candidate 复用同一轮 exact 已核验的 producer packet 时，producer 不计入 candidate 当前 invocation 的实测耗时；比较器同时展示 candidate/exact 的真实 supervisor wall、各自 phase-sum，以及由共同 producer phase 加 consumer phase 得到的 derived workflow 时间。共同 workflow 内存峰值按 `max(common producer peak, consumer peak)` 逐项计算，并给出 bytes、GiB、百分比和原始来源。完整数值都有时差值标为 `measured_difference`、可信性留给后续审查（`credible_saving: null`）；缺采样或口径不足才标 `RESOURCE_COMPARISON_INCONCLUSIVE`。H2 不预设节省门槛，H3 才裁决是否有可信正节省。

## 身份和证据边界

consumer 与 producer 的 source、input、resolved、physical identity 分开保存；producer packet 的 raw identity、manifest hash、external-mode count/key hash、physical contract 和 cross-section partition 必须真实绑定。consumer 的 `input_original.dat` 与 `resolved_config.json` 按实际字节重新取 hash。网格 payload 固定验证 `E/H=(5,20,40,3)`、`x=40`、`y=20`、`z=(10,30,60,90,110)`，`modal_amplitudes` 长度为 `2*mode_count`，两侧 q 长度取实际 external inventory。

原始 residual 或 traction 失败即使没有生成后续 authority/grid/canonical 文件，也应保留已经写出的数值量和限值，并与“参考证据不完整”分开分类。负 physics writer 使用 `physics.traction.bottom/top.relative_dual`；成功 authority 使用 `relative_residual`。这两种结构都按当前 writer 读取，不添加旧 schema 别名链。

当前仅完成比较器、writer-bound fixture 和合同文档；H2/H3、正式 producer/PDE、MPI8 数值准入和可信内存节省尚未运行或通过。首版 comparator 的路径/字段读取问题属于本轮工程审查修复记录，不记为数值 gate 失败。
