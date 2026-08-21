# V9-2：三组两层 supernode side preconditioner

## 结论先行

V9-2 在同一个 5 nm、p6/h4、M480、MPI8 bottom component 中，固定三组
`[0,1]`、`[2,3]`、`[4,5]`，只评估 `SN2-J` 和标准三块对称 Gauss–Seidel
(`SN2-SGS`)。三个 MUMPS factor 均成功构造；construction resource 与 lifecycle 释放通过，retained
明确为 `not_run`；但两种 action
对五个非退化 frozen source 都产生非有限输出，因此没有稳定的 preferred method，也没有
进入 retained apply。这个结果是 fixed two-layer supernode baseline 的
`controlled_numerical_negative`，不是已经证明的通用 factor API bug。

| 项目 | 实测/裁决 |
|---|---|
| 正式分类 | `V9_2_FIXED_TWO_LAYER_SUPERNODE_CONTROLLED_NUMERICAL_INSTABILITY` |
| worker / parent | worker `component_stability_failed`；parent `worker_nonzero`、exit `3`；parent termination `null`、warning `false` |
| 评估顺序 | `SN2-J → SN2-SGS`，同一组三 factors，candidate 之间清理临时对象 |
| five mandatory probes | 两种方法均 `finite=false`；`r_F`、repeat、linearity 均为非有限，均未通过 |
| physical RHS | 输入范数为 `0`，relative residual 定义退化，`mandatory=false`；但 action output 同样非有限：SN2-J=`Inf`、SN2-SGS=`NaN`，两者 `finite=false` |
| construction / overall | `24494911488 B = 22.812664031982422 GiB <=45 GiB`；overall 同峰值 |
| retained | `not_run / not_available`；无稳定 preferred，不是 `30 GiB` 失败值 |
| swap | `0` |
| wall | parent 约 `473.941922 s`；worker marker construction end 约 `473.122750 s` |
| factor lifecycle | ready `3` → final `0`；full-side/global/nested `0/0/0` |
| packet / QEP | selected packet `false`；QEP `0`；exact holdout spool 仅用于 frozen holdout 并已释放 |

## 五个 probe 的逐方法结果

这里的 `r_F` 是用原始有限元局部算子 `F` 重新计算的 true residual，而不是把
reference solution 误当成 residual。正式数值条件要求 finite、repeat/linearity
`<=1e-10`，mandatory true residual `<=1e-2`；modal/external 还报告更严的
preferred `<=1e-3`。SN2-J 的 action 输出为 `Inf`，SN2-SGS 的 action 输出为
`NaN`；因此标准 JSON record 用 `null` 表示不可持久化的数值，并用
`raw_status=nonfinite` 保留事实。

| method | positive | negative | external | random773 | random779 | stability |
|---|---|---|---|---|---|---|
| SN2-J | NaN/Inf | NaN/Inf | NaN/Inf | NaN/Inf | NaN/Inf | `finite=false` |
| SN2-SGS | NaN | NaN | NaN | NaN | NaN | `finite=false` |

两行的五个 mandatory label 都是非退化输入；因此不能把 `r_F` 写成零、也不能把
`NaN` 忽略后继续选择候选。两方法的 Gate 摘要如下：

| method | method interval（worker markers） | apply count | factor solves | worst mandatory `r_F` | repeat / linearity | Gate |
|---|---:|---:|---:|---:|---|---|
| SN2-J | `6.183576241 s` | 18 | 54 | `null`（非有限） | nonfinite / nonfinite | fail |
| SN2-SGS | `23.778006799 s` | 18 | 90 | `null`（非有限） | nonfinite / nonfinite | fail |

`method interval` 只用于候选证据，不替代整体 construction 或 retained 区间。两种方法
共享 `factor_set_build_count=1` 和同一组三个 two-layer factors；`SN2-SGS` 使用标准公式：

```math
S_{SGS}=(B+U)^{-1}B(B+L)^{-1}.
```

## 为什么这是数值不稳定而不是资源停止

父 watchdog 的完整 process-tree 样本记录了 `22.812664031982422 GiB`，远低于本路线
`45 GiB` absolute hard stop，swap 也是零。三个 sparse MUMPS supernode factor 的构造、
ownership、coverage 和最终清理均完成；没有 traceback、MPI ownership 错误或 factor setup
异常。真正失败点是 apply 后五个非退化输入都变成非有限值。V8 单层 factor-only 路径曾能产生
finite 输出，但这不能证明固定两层 supernode 的局部块在本次 h4 条件下同样稳定。

因此本轮不尝试 shift、damping、ILU 扫描、额外 sweep 或参数调优；这些都不在 V9 冻结范围内。
也不把 `worker_nonzero` 误读为资源终止：它只是父 launcher 看到 worker 数值失败后的 transport
分类，raw `component_stability_failed` 才是数值权威。

## 生命周期与身份

三组 supernode rows 为 `49140 / 41580 / 41580`，互斥且完整覆盖 `132300` 个 global rows；
cross-lower 和 cross-upper 各为 `2`。两候选严格串行，candidate 临时对象之间完成 cleanup；
components、system、sweep、spool 最终释放，factor inventory 为 `3→0`。由于没有 stable
preferred method，`retained_apply_state_ready` 不会出现，`retained_state_release` 只记录最终
释放，不形成 retained resource pass。

本次 route identity 由 schema/profile/method/source SHA 确定：

```text
schema    = task039.v9.h4.layer_supernode.bottom.v1
profile   = task039.v9.h4.layer_supernode.bottom.v1
method    = task039_v9_h4_layer_supernode_bottom
source    = 266a1acc0eb7a4515815e34414f89e183c15e9ef
```

复用的 frozen exact-bottom holdout 绑定 producer source
`7e5d9b57a10b1093f0cb062eaf7bc12797c47e1f`、catalog SHA256
`a2a7fb6fb01df4f795d31ff94f6ac6adf957ac4fe4a5c1a8d05176e3d64c0384`、8 个 producer ranks、
6 个 labels 和 96 个 response artifacts。compact record 还绑定本次 13 个 raw 文件的 SHA256；
record 路径为
[task039_v9_supernode_side_preconditioner_v1.json](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v9_supernode_side_preconditioner_v1.json)。
raw 目录是 ignored local evidence：

```text
results/task039_v9_h4_layer_supernode_bottom_mpi8_266a1acc/
```

## 未运行项和通俗解释

V9-3 bottom/top direct full-side FGMRES、V9-4 ranks 16/32/64、10 modal samples、top、both-side、
full formal、recovery、RTA、field export 和 0.7 nm PDE 均为 `not_run`。原因是 V9-2 没有产生
唯一稳定的 action；`not_run` 不是这些阶段的数值失败。

所谓 supernode，是把相邻两层合成一个较大的稀疏块再求解。它的目标是减少层间往返，同时
保留比完整 side factor 更小的对象。此次实验说明这三个块在资源上可构造和释放，但把输入
送入 `SN2-J` 或 `SN2-SGS` 后就出现 `Inf/NaN`，所以现在只能说“construction 峰值在限值内且清理完成，
但 retained 未运行；这组 action 数值不稳定”，
不能说它已经改善了 h4 的物理残差。
