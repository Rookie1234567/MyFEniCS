# Task037-extra Response V13：W17A 正式负结果与二维方向诊断

本文件是 W17A 的增量收口；`response_v12.md` 保持冻结，W8–W16B 的历史负结果和原始证据不改写。W17A 仍是 action-only 诊断：它只生成候选修正方向并用物理 action 检查方向质量，没有运行完整时谐 PDE、KSP、场恢复或 official R/T/A。

## 一页结论

| 路线 | 固定方法 | 真实结果 | 结论 |
|---|---|---|---|
| W14A | global coercive B0 内层两次，再做 physical action | rho `0.8943645606070599`；peak `1,158,553,600 B`；swap `0` | action/resource 通过；不是 PDE/RTA |
| W14B | physical fixed-4 correction | rho `0.8943645606070647 → 0.869374076266045 → 0.8681485457234316`；inner4 `0.01751006766159766 > 0.01` | `W14B_FIXED4_CORRECTION_FAIL`；W14C locked |
| W15A | W14B checkpoint1 residual 的 restarted rank-one correction | inner `0.00499608724120203`；local/cumulative rho `0.9993168124994211 / 0.8937535419182971` | `W15A_RESTART1_NUMERIC_FAIL`；W15B locked |
| W16A | beta=1 shifted volume-only fixed20 inner，再做 physical rank-one | inner `0.061153888358888554 > 0.01`；rho `0.8806019129260008` | inner Gate 失败；W16B 仅作为后续候选 |
| W16R | W16A z20 初值再追加 fixed20，累计40步 | inner `0.008234328428613968`；rho `0.8814092210776835`；peak `1,398,456,320 B` | action-only 通过，解锁 W16B screen；不是 PDE |
| W16B | 两次 outer-2 screen，每个 outer PC 都 fresh zero20+restart20 | rho1 `0.8814092210776882`；rho2 `0.8796856414991869`；peak `1,557,839,872 B` | rho2 高于 `sqrt(0.75)=0.8660254037844386`；数值 Gate 失败 |
| W17A | beta=1 shifted volume + 同一 matrix-free DtN80，fixed40，两次重复 | cycle20 `0.21437006185665625`；cycle40 `0.12567225369307264`；physical rho `0.8917790380896942`；peak `1,524,117,504 B` | `W17A_GLOBAL_PHYSICAL_SHIFTED_NUMERIC_FAIL`；W17B locked |

## W17A 正式运行

W17A 唯一正式运行自然完成，没有超时、RSS 终止、swap 或编译器子进程问题。worker 返回 RC1，表示预声明的数值 Gate 未通过；watchdog 本身正常完成，独立 checker 返回 RC1 并给出同一个数值分类。这不是执行失败或资源失败。

W17A 的两个固定 40 步内层重复得到相同结果：cycle20 true residual 为 `0.21437006185665625`，cycle40/final true residual 为 `0.12567225369307264`，二者都超过 `<=1e-2` 的硬门。两次 z 和 p 的数组 hash exact 相同，relative difference 为 `0`；physical rank-one rho 两次均为 `0.8917790380896942`，超过 `<=0.85`。normal closure 为 `0`，projection orthogonality 为 `6.533554203970653e-17`。

独立 checker 的所有正式 checks 中，除 `worker_action_gate` 外均通过；worker checks 只有 `inner_residual` 和 `measurements` 为 false。实际 action 账本为：

```text
global_auxiliary/global_shifted/local_pc/local_exact/shifted_total
    = 86 / 86 / 80 / 80 / 166
auxiliary_DtN/physical_volume/physical_DtN/total_DtN
    = 86 / 2 / 2 / 88
```

prediction 为 `1,701,623,030 B`（derived，不是实测）；正式 process-tree peak 为 `1,524,117,504 B`，swap 为 `0`，compiler descendants 为空，termination 为 null，drain 已完成，17/17 个 marker 均存在，worker wall 约 `892.264 s`。因此资源证据通过，但不能把 action-only 内存结果写成 PDE 内存通过。

本轮唯一结构变化及对照支持的主要根因边界/推断是：W17A 把共享 DtN80 加入了 auxiliary operator，但 local PC 仍然是 shifted volume-only。辅助算子和局部预条件器对边界/modal 子空间的处理不一致；inner residual 没有降到资格门，physical 方向也没有改善到 `0.85`。这不是尚未完成 modal decomposition 的数学证明，因此不以增加步数掩盖失败，W17B 不运行。

正式证据保持原样：

- raw summary SHA：`7cfe7e7f176b3332b9a4fb52e62d58ba71b75eca04c990d558c4819f3b32f9bb`；
- watchdog summary SHA：`57221408de7e0673e7865833f83c85b3cf11ddc4e7c30adb2318df7b47ad8d42`；
- 现有正式 compact file SHA：`37a67d5e2a7c55a5548357f073b740801742691b72cc405f6b2355f22bc5dd92`；
- 现有 compact embedded evidence SHA：`a72b174a8984c9cec44137ff08b921aa89e937b4d5cc269e3d528492f84cf983`。

## W16B + W17A 的固定二维离线诊断

这一步只读取已经保存的 W7 residual、W16B checkpoint NPY 和 W17A z/p NPY，没有生成新的物理 action，也没有运行 KSP/PDE。对冻结 W7 residual `r`，令 `P=[A_W16B, p_W17A]`，使用：

```math
\alpha=(p^H r)/(p^H p),\qquad
\rho=\lVert r-\alpha p\rVert_2/\lVert r\rVert_2,
```

以及二维最小二乘：

```math
G=P^HP,\qquad h=P^Hr,\qquad c=G^{-1}h,
\qquad \rho_{2D}=\lVert r-Pc\rVert_2/\lVert r\rVert_2.
```

| 诊断 | 结果 |
|---|---:|
| W16B final physical image rank-one rho（dense offline 重算） | `0.8796856414991874` |
| W16B 正式 raw 记录 rho / dense offline 重算差 | `0.8796856414991869 / 0.8796856414991874`；绝对差 `<1e-15` |
| W17A physical image rank-one rho | `0.8917790380896956` |
| 二维 span rho | `0.8781945094815413` |
| 冻结 blockwise normal-equation closure | `3.750159823210426e-15` |
| 本次 dense linear-system closure | `1.2724784801792792e-16` |
| `cond(P)` | `15.48530644048902` |
| normalized column alignment absolute value | `0.9657478231415315` |
| 相对 W16B 的绝对改善 | `0.0014911320176460574`（约 `0.1695%`） |
| 离线解锁门 | `rho_2D <= 0.85`，结果为 false |

Gram 矩阵是 Hermitian，奇异值为 `2.965754250593583` 和 `0.1915205399383705`，rank 为 2；`h` 和复系数也已写入 derived compact。W16B final residual 与 W17A p 的 normalized complex correlation 为 `-0.001940770575712231 + 0.01497673023226018i`，绝对值 `0.015101954803185132`。表中的 W16B `0.8796856414991874` 是本次 dense-vdot 离线重算；正式 raw/compact 记录的 blockwise scalar 是 `0.8796856414991869`，二者绝对差小于 `1e-15`，只反映浮点累加/运算顺序。两种口径都支持同一负结论：W17A 虽提供了独立方向，但在已保存的 W16B+W17A 二维空间中只把 rho 从约 `0.87969` 降到 `0.87819`，仍明显高于 `0.85`；W16B+W17A span lane 关闭，不 formalize，也不解锁 W17B。

W16B residual 范数 `r0/r1/r2` 为 `1.6023954272 / 1.4123661053 / 1.4096042493`；第二步只下降约 `0.19555%`。要让后两步达到旧 outer4 门 `rho4<=0.75`，剩余累计因子必须不超过 `0.8525772897`，等效每步至少下降约 `7.6649%`；按当前第二步趋势，rho4 约为 `0.8762485870`。这进一步支持不盲跑 outer4。

完整 derived 记录为 [`m6b_w17a_w16b_span_diagnostic_v1.json`](../../benchmarks/cases/101_task37_extra_development/records/m6b_w17a_w16b_span_diagnostic_v1.json)。它标记为 `derived/offline_diagnostic/not_PDE/not_action_run`，绑定每个输入的路径、file SHA、array SHA、shape、dtype、finite，以及 W16B/W17A 正式 summary 和 compact 的身份；当前文件 SHA 为 `cd21be1be0ee5c1847501e9ba10b520ad7254b81bbb71663ea25920b9c78c827`，embedded evidence SHA 为 `b9e25a9a1ef198694d95dc88d5eb761a548aedd143399dd0482d2066c890978d`；它不是新的 formal Gate。

## 未运行项与后续边界

full time-harmonic PDE、official field/RTA、direct-authority physics comparison 和最终 `<2,000,000,000 B` PDE process-tree 测量仍为 `not_run`。action-only 的 finite、repeat、资源或峰值结果都不能替代这些证据。

用户已明确授权在 Gate 不放宽、物理定义不改变、不过度防御性开发的前提下，针对具体失败继续研究；这不等于自动批准 W17B 或任意新的 heavy run。当前 W17B 因 W17A 数值 Gate 失败而保持 locked。
