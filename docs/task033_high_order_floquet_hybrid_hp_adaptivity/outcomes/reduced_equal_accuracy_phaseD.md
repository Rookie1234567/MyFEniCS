# Task033 Phase D1：精简固定阶次等精度研究

## 结论

Review V5 批准的减缩矩阵已经按停止规则完成：

```text
p3/h10 = negative_not_equal_accuracy
p3/h7.5 = fixed_p_equal_accuracy_clear_success_with_qualifications
selected candidate = p3/h7.5
Task33 reduced scope = complete after F0
whole original Task33 = partial by explicit scope transfer
```

`p3/h10` 先运行并在精度 Gate 上失败，因此才解锁 `p3/h7.5`。没有运行
`M240`、`p3/h3`、任何 p4 target、adaptive 或 0.7 nm PDE。所有新 PDE 都是
MPI4、单一重型任务串行运行、外部 watchdog、零 swap。

比较参考是已有 `p3/h5` direct 离散解。它是当前最佳可用离散参考，不是连续解，
也没有证明网格收敛。所谓“等精度”只表示候选相对该 provisional reference 的同一组
误差指标不劣于复用的 `p2/h3` baseline。

## Direct full3D 结果

| candidate | DoF | true residual | memory | time | R / T / A |
|---|---:|---:|---:|---:|---|
| p3/h10 | 23,073 | `1.349e-11` | 1.980 GiB | 22.390 s | 0.0553985 / 0.4060679 / 0.5385336 |
| p3/h7.5 | 63,747 | `6.449e-12` | 3.667 GiB | 44.487 s | 0.00309073 / 0.59116086 / 0.40574841 |

两条 full3D solve 都通过装配 Gate、残差 Gate 和零 swap Gate。`p3/h7.5`
的 full3D 峰值高于预测上界 2.463 GiB，但仍远低于现场受控终止线；预测只用于
launch planning，实测值是结果权威。

## 对 provisional p3/h5 的物理误差

| metric | p2/h3 baseline | p3/h10 | p3/h7.5 | p3/h7.5 不劣于 baseline |
|---|---:|---:|---:|---|
| \|ΔR\| | 0.003523 | 0.054308 | 0.002001 | 是 |
| \|ΔT\| | 0.016969 | 0.194555 | 0.009462 | 是 |
| \|ΔA\| | 0.013446 | 0.140246 | 0.007461 | 是 |
| \|ΔAvol\| | 0.013446 | 0.140246 | 0.007461 | 是 |
| 五平面 max E relative L2 | 0.496254 | 2.345675 | 0.286621 | 是 |
| 五平面 max H relative L2 | 0.499354 | 2.330375 | 0.290470 | 是 |
| 接口 max Et relative L2 | 0.496254 | 2.055220 | 0.286621 | 是 |
| 接口 max Ht relative L2 | 0.456215 | 1.654070 | 0.272020 | 是 |
| significant-order power max/rms | 0.765156 / 0.350882 | 0.999786 / 0.684339 | 0.649135 / 0.293093 | 是 |
| significant-order amplitude max/rms | 0.724457 / 0.400581 | 1.868806 / 1.062421 | 0.554958 / 0.324776 | 是 |

`p3/h10` 除线性残差外，全部等精度比较项都比 `p2/h3` 差，所以它是明确的
accuracy negative；低内存和短时间不能抵消物理误差。`p3/h7.5` 的全部同口径物理
指标均优于 `p2/h3`，因此通过 Review V5 的第一半判据。

## Hybrid M 漏斗与 full3D 闭合

| candidate | M | formal | memory | time | max plane E/H relative L2 |
|---|---:|---|---:|---:|---:|
| p3/h10 | 120 | fail | 1.467 GiB | 47.517 s | `9.079e-4 / 1.242e-3` |
| p3/h10 | 160 | fail | 1.661 GiB | 66.942 s | `9.079e-4 / 1.242e-3` |
| p3/h7.5 | 120 | pass | 1.985 GiB | 63.269 s | `8.737e-5 / 3.500e-4` |
| p3/h7.5 | 160 | pass | 2.008 GiB | 74.908 s | `8.737e-5 / 3.500e-4` |

`p3/h10` 的两个 Hybrid shard 只有 sampled interface H-t Gate 超过 1%，其余代数、
残差、R/T/A、体吸收和中间平面 Gate 均通过。M120 到 M160 基本不变，所以该失败
不是 modal truncation 不足，也不触发 M240；更重要的是 direct 解本身已经不满足
等精度要求。

`p3/h7.5` 的 M120、M160 全部 16 个 Gate 通过。M120→M160 的 R/T/A 差约为
机器精度，significant-order amplitude 最大相对变化为 `1.405e-10`，因此 M160
足够且 M240 没有数值必要。M160 相对同网格 full3D 的 R/T/A 绝对差不超过
`1.264e-6`。

## 等精度资源比较

资源正结论使用 `p2/h3 Hybrid M160` 与 `p3/h7.5 Hybrid M160` 的同口径
Schur-minimal 路径。FE DoF 不含每端 40 个外部 Fourier-DtN auxiliary；
local-system rows 含这些 aux；total rows 再含 320 个内部模态未知量。
factor-inventory NNZ 是 bottom/top MUMPS local factor inventory 的总和，不是
assembled system NNZ，也不与旧文档中的最终全局稀疏系统 NNZ 混用。

| metric | p2/h3 M160 | p3/h7.5 M160 | baseline / candidate | 分类 |
|---|---:|---:|---:|---|
| local FE DoF | 68,396 | 26,598 | 2.571x | clear success |
| local-system rows | 68,476 | 26,678 | 2.567x | clear success |
| total rows | 68,796 | 26,998 | 2.548x | clear success |
| factor-inventory NNZ | 60,672,040 | 17,057,414 | 3.557x | engineering target |
| memory authority | 3.224 GiB | 2.008 GiB | 1.606x | useful positive |
| wall time | 99.686 s | 74.908 s | 1.331x | useful positive |

六项资源指标全部降低，同时所有规定物理误差不劣于 `p2/h3`。因此本轮可以给出
Review V6 将正式分类冻结为
`fixed_p_equal_accuracy_clear_success_with_qualifications`：它是当前尺度、固定 p、
provisional discrete reference 下的工程正信号，不是 p3 普遍优于 p2 的定理，也不是
连续解误差或 0.7 nm 可行性证明。

## 跨记录执行语义与预测偏差

资源比较使用冻结镜像 `myfenics-stage4:task28`，digest
`sha256:08c61b2cde742442b0031437dbc5160db979494587e6b6364f7935beb29dd76d`，
MPI4、`modal-schur-memory-minimal`、零 swap，并且一次只运行一个重型 case。
内存权威定义为 simultaneous live MPI worker RSS sum 与 container cgroup current
的最大值。p2/h3 clean SHA `793354af...` 与 p3/h7.5 clean SHA `7a7db587...`
不同，已由 source compatibility audit 明确接受；wall time 只能作指示性实测比较。

原 launch 模型的 `p3/h10` 上界 1.947 GiB 对应实际 1.980 GiB；
`p3/h7.5` 上界 2.463 GiB 对应实际 3.667 GiB。预测仍可作为受 watchdog 保护的
launch guard，但不是 measurement。该旧高阶模型在重新校准前不得用于 1 TiB /
0.7 nm 投影。

## 证据

- 聚合记录：
  `benchmarks/cases/091_hybrid_hp_adaptivity_feasibility/records/stage5_equal_accuracy/reduced_equal_accuracy_summary.json`
- p3/h10 descriptor：`records/stage5_equal_accuracy/full3d_reference_p3_h10.json`
- p3/h7.5 descriptor：`records/stage5_equal_accuracy/full3d_reference_p3_h7p5.json`
- D1 source-split audit：
  `records/stage5_equal_accuracy/d1_source_compatibility_audit.json`
- 聚合 payload SHA256：
  `b942b9471271c00778011ad3a282e8ff04617bebf84e3215c414a7c560b6aac1`

重型 mesh、field、NPZ、matrix、factor、timeline 和 log 继续位于 gitignored
`benchmarks/artifacts/`；tracked 聚合记录保存其路径、SHA256、关键数值和判定。
