# 对 `review_report_v4.md` 后续执行与 p3/p4 结果的回复

## 总体处置

review v4 的证据修复与 Phase C1 assembly-only 均已完成。其后用户明确扩大了资源授权：
p3/h5 可在受控看门狗下使用 swap 后备；若实际零 swap 且内存低于 10 GiB，则允许进入
p4/h5。执行没有改写 review v4 当时的 Gate，而是把“审阅时的预测否决”和“之后用户
授权的新实测”并列保留。

最终状态：

```text
p3/h5 full3D direct = PASS, 7.781 GiB, cgroup swap 0
p3/h5 same-degree Hybrid/full3D numerical closure = PASS
p4 four-mode matched trace MPI1/MPI4 = PASS
p4/h5 assembly-only = CONTROLLED MEMORY STOP, no OOM, no factorization
p4 target full3D/Hybrid solve = NOT LAUNCHED BY CANDIDATE-SPECIFIC MEMORY GATES
adaptivity = DEFERRED BY USER SCOPE
```

## 对 review v4 项目的逐项回复

| 要求 | 处理 | 结果 |
|---|---|---|
| aggregator 只接受精确 `measured_shard_pass` | exact equality；M80/M120/M160 负测试 | pass |
| 提升 interface/QEP/容量实测指标 | 已进入 tracked `phaseC_summary.json` | pass |
| p3/h5 assembly-only 校准 | 145,943 rows、35,566,727 NNZ；4.148 GiB | pass |
| 未经 Gate 不得自动 full solve | review Gate 原样保留；后续 full solve 由用户明确授权 | preserved |
| p4 前先补四模态迹 | `[4,5,6,7]` 四维块；MPI1/MPI4 | pass |
| 不得把 Hybrid 低内存覆盖 full3D Gate | p3/p4 direct 与 Hybrid 均独立判定 | pass |
| 不启动自适应 | 未启动 | pass |

## p3 同阶闭合

p3 direct 使用 commit `bd828f24...` 产生固定 NPZ，Hybrid 闭合使用 clean commit
`95921ab76...` 并校验 NPZ SHA
`4986d7e355e3afd27ad1a34acbb2faeec5a72279036b002fcf24940e0a8113a3`。

| 指标 | 结果 |
|---|---:|
| direct true residual | `5.442e-12` |
| Hybrid true residual | `2.343e-12` |
| 最大 R/T/A 绝对差 | `1.214e-7` |
| 体吸收绝对差 | `1.214e-7` |
| 五截面最大 E 相对 L2 | `1.100e-5` |
| 五截面最大 H 相对 L2 | `1.098e-4` |
| direct / Hybrid memory authority | 7.781 / 2.618 GiB |
| direct / Hybrid cgroup swap | 0 / 0 |

16 项 Hybrid 物理与代数 Gate 全过。该结论是同一 p/h 离散的数值一致性；
`grid_converged=false` 仍保留，因此不宣称连续解或 h 收敛。

## p4 四模态与目标资源结论

四模态记录实际请求 8 个 QEP 模态并选择近简并组 `[4,5,6,7]`。MPI1/MPI4 的
Gram 均为 4/4 满秩，round-trip 为 `2.434e-15 / 8.967e-16`，最大 beta assignment
差 `5.226e-13`，principal/block invariant 通过。

smoke 阶段发现 raw Gram 谱在 MPI 允许的块内基底旋转下不是不变量。没有放宽
Petrov、残差或 beta 阈值；聚合器改为复算满秩、精确块身份、Petrov round-trip、
block normalization 与 principal-angle invariant。raw Gram 差仍保留为诊断。

p3 前置条件满足后，p4 assembly-only 合法进入。它得到 339,892 DoF 与
155,205,040 base NNZ；增广复制/插入后外部内存权威值达到 12.616 GiB，超过
11.9 GiB controlled line，进程被 SIGTERM 安全终止，OOM=false，factorization
stage 未出现。虽然 cgroup swap 为零，`pswpout` 增加 4 页，所以 formal
`no_swap=false` 按 fail-closed 保留。

这足以否决本机上的 p4 direct factorization。p4 Hybrid M160 也被独立资源矩阵的
37.038 GiB 中心与 42.594 GiB 上界否决。因此没有为了形式完整而强跑或伪造 p4
target 解。

## 当前边界

- p3/h5 whole Phase C 的数值缺口已关闭，等待新证据的独立复审；
- p4 高阶 Floquet/QEP/四模态 trace 组件已通过，但 target solve 没有通过资源 Gate；
- p3/h3、adaptive、graded、buffer、variable-p/hp 与 1 TiB 推演继续延期；
- 完整原 Task33 21-role manifest 仍为 `NOT_RUN`，不因本次阶段闭合而伪装完成。
