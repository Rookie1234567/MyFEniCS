# V30 工作站引导型笔记本完整场结果

## 模型与身份

本场用于检查 V30 的显式笔记本 profile 是否在不改变原方程、网格和外层求解 Gate 的条件下通过完整离散求解。profile 以逐项台账引导未来可能的工作站复核；它本身不构成工作站迁移批准。

| 项目 | 本场记录 |
|---|---|
| profile / run id | physical_p6_trace_workstation_guided_v30 / task39extra_v30_workstation_guided_original_h7p5_v1 |
| 输入与配置 | original、13.5 nm、1° grazing、azimuth 0、s 偏振；p6/h7.5、粗层 p4；990 cells，轴向 [9,5,22]；Full3D、80 个有序 DtN mode；MPI1、mpi1_omp1_blas1_v26 |
| source / input / physical model SHA256 | 254f0cf78f950246655dc86af9409139b9a97680 / ba2c0745221a017d71f606325c20e98a3a57611887929fe55c18180f308f544b / 0875aaf070d88732b09ead8c55a7d4c28dd75f9b329e90f35fea984a0b7464e6 |
| resolved config SHA256 | 6912022c6d8a9c58c6ad63b5a18eea85d2b50223f72efd255ba009433f814adc |
| 几何与模式身份 | entity SHA 539460eec567dd89bb75cab8c72926c337be40fc5cfab54765f56117ee0ae5ba；frozen axis-plan SHA b5bab6aae4668be60aacbb49265b4c875def42e2620256cd168d8c26207dc157；有序模式 SHA dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2 |
| 执行身份 | systemd user service myfenics-case-20260928T143048-1005019.service；InvocationID 556a78e1eca549f7a53082faf57ecf88；exit 0，后代已清空 |

V30 对角优化让 p6 预条件器用实际 affine 几何度量计算正对角；对角是控制预条件器缩放的轻量权重，错误度量会改变预条件器但不应改变物理方程。本轮采用路径在舍入精度内复现 V29 对角，并通过完整场回归。其他局部候选只有满足代数 Gate 且有实际收益时才接入；L3/L4 的性能负结果因此保留在研究记录中，没有升为正式默认。

## 求解、场与物理结果

| 指标 | 实测值 / 判定 |
|---|---|
| worker 状态 | Q4_ORIGINAL_AUTHORITY_LIMITED_PASS；126 iterations；TRUE_RESIDUAL_PASS |
| 完整最终 / 释放后显式真残差 | 9.283162411158622e-7 / 9.283162411158622e-7，门槛 1e-6；两份独立 packet 重算一致 |
| 全 FE 同离散 L2 / scaled-curl 相对差 | 1.4028635388466484e-14 / 3.3312391899680165e-14，限值 1e-4 |
| 同坐标 E / H / 界面切向 E / H 相对差 | 1.4636905245251295e-14 / 5.966308861980466e-14 / 1.0970606150437768e-14 / 1.430675144001785e-13 |
| 有序 mode / 传播 mode 数 | 80 / 78；mode amplitude relative L2 1.9013904912668762e-14 |
| R / T / A_balance | 0.36509755369518077 / 0.013016803348172736 / 0.6218856429566464 |
| A_volume（grating + substrate） | 0.6218856421420169（0.6135111751821957 + 0.008374466959821227） |
| 零级反射 | R00_s=0.365060862881605；R00_p=4.812903003419231e-23；R00_total=0.365060862881605 |
| 能量与吸收闭合 | R+T+A_volume-1=-8.14629586010085e-10；A_balance-A_volume=8.146294749877825e-10；分区体吸收之和差值为 0 |
| 对 V29 的最大逐模态 power 绝对差 | 8.570921750106208e-14（code units）；R/T ratio 差亦远低于 review 限值 |

正式 worker 的 field-reference checkpoints 0/32/64/96/126 全部仍是 NOT_ATTEMPTED，authority=MATCHED_REFERENCE_NOT_AVAILABLE。上表 FE 与坐标场结果来自独立的 V30-vs-V29 离线核验；checker 没有启动 PDE、算子、因子或 KSP，也没有回写 worker checkpoint。

## 时间与资源

| 口径 | V30 | V29 同离散基线 | 变化 |
|---|---:|---:|---:|
| full workflow monotonic | 2532.759 s | 2422.426 s | 慢 110.333 s（4.555%） |
| conservative realtime | 2762.545 s | 2643.635 s | 慢 118.911 s（4.498%） |
| setup monotonic | 626.931 s | 533.755 s | 慢 93.176 s（17.457%） |
| pure KSP | 1854.603 s | 1837.175 s | 慢 17.428 s（0.949%） |
| watchdog 进程树 RSS 峰值 | 8,044,191,744 B | 7,326,449,664 B | 多 717,742,080 B（约 9.8%） |

watchdog 完成、leader exit 0、9,955 个样本、所有 descendants 清空。RSS 是专用 subreaper 父进程及后代的同时 RSS 采样峰值；worker RSS 为 7,518,617,600 B。PSS disabled by profile，峰值 null，不能写作 0。观察到 swap 峰值 0，但 swap_policy=observe_only 且 swap_gate_enforced=false。这些计时桶包含不同阶段，不能把组件累计桶相加为 wall time；V30 是单次配对观察，不构成因果解释。

## 独立 checker 与未完成事项

V30 独立 raw checker 分类为 PASS_WITH_AUTHORITY_LIMITATION。旧 task39extra_v25_dynamic_checker.py 对 V30 raw summary 返回 DYNAMIC_FAIL，唯一失败 gate 为静态 backend_identity；其 BAL_H/p4、真残差、native A4 和 first-Arnoldi gates 为 true。旧 checker 规定的是 V25 A6/H6 backend 与线程合同，和 V30 review-selected profile 不同。原 FAIL 与详细字段保留，不据此改写 V30 的独立结果，也不称旧 checker 已通过。

未运行/未声称：full repository pytest、Ruff、MPI2/4、CI；新的 5 nm/2 nm/0.7 nm PDE；工作站迁移；master merge。V30 仍为 FORMAL_RUN_COMPLETE_PENDING_MAIN_REVIEW，普通默认不变。原始 field、matrix、factor、timeline 和运行日志继续留在 ignored artifact 目录。

机器证据入口：[compact](records/workstation_guided_local_v30_compact.json)、[components](records/workstation_guided_local_v30_components.json)、[checker](records/workstation_guided_local_v30_checker.json)、[selection](records/workstation_guided_local_v30_selection.json)、[monitor policy](records/workstation_guided_local_v30_monitor_policy.json)、[run index](records/run_index.json)。
