# M4d 高阶 element-trace patch 负证据

## 范围与身份

本记录绑定 source SHA `c0dc7a2c048d0ec06377749d3cf45b70a11fc342`、分支
`codex/20260803-task37-matrix-free-iterative-development`，使用 serial
p6/h50 tiny hexa fixture。实验在 dirty worktree 中进行，是 research-only
一次性 oracle：不是 PDE 运行、不是 production 接线，也不是资源资格化。

“收缩”均定义为
`||b - A M^{-1} b|| / ||b||`，其中 test237 的三类 RHS 均由同一个完整
condensed fine shell 对解向量 `x` 计算 `b=A_full x`。因此下表不能与不同
source/归一化口径的旧表混称。

## 两种一次性 baseline 口径

早先的 M4d-0 core diagnostic 使用 test236 诊断中的 source/归一化口径；
test237 后来改为明确的 `b=fine_shell.mult(x)`。数值不同是口径差异，分别保留。

### M4d-0 core diagnostic

| source | diagonal-only | beta=0.1 p2/modal | composite cycle 1 | composite cycle 2 |
|---|---:|---:|---:|---:|
| low | 0.2790868541 | 0.1006298624 | 0.2467971445 | 0.1234824850 |
| high | 0.2775463188 | 0.9262838848 | 0.2331722474 | 0.1153041298 |
| mixed | 0.2824623347 | 0.8520524314 | 0.2356622439 | 0.1186050435 |

### test237 corrected source semantics

| source | diagonal-p2-diagonal baseline | p2/modal-only |
|---|---:|---:|
| low | 0.1961929475 | 0.0982160128 |
| high | 0.2048698733 | 0.9576772827 |
| mixed | 0.1860884161 | 0.9160994576 |

## Full local patch oracle

| source | naive single-cell patch-only | naive patch-p2-patch | assembled `R_i A_schur R_i^H` patch-only | assembled restriction patch-p2-patch | assembled restriction coarse-first |
|---|---:|---:|---:|---:|---:|
| low | 4.0407869192 | 13.4984981374 | 0.3442914627 | 0.4491016115 | 0.0357524462 |
| high | 4.0000523533 | 22.7523866379 | 0.3366781686 | 0.3635951004 | 0.3392686906 |
| mixed | 3.9806742622 | 21.8254557384 | 0.3312713709 | 0.2381479800 | 0.3248531398 |

这里的 `A_schur` 仅指 assembled retained-Schur 体贡献，不包含 synthetic
DtN low-rank 项。naive patch 直接使用单 cell contribution；assembled
restriction oracle 使用同一 cell row set 的 `R_i A_schur R_i^H`。

## p2 high-order complement oracle

对每个 collapse 后的 cell row set `I`，对 `P[I,:]` 做固定 `rcond=1e-12`
SVD，取 `Q_high` 的正交补，并只在该补空间中解局部 patch。

| source | single-cell high patch-only | single-cell high coarse-first | exact restriction high patch-only | exact restriction high coarse-first |
|---|---:|---:|---:|---:|
| low | 2.0928456701 | 0.2099900836 | 0.6112874307 | 0.0609393472 |
| high | 3.5979751109 | 3.4799723085 | 0.3126732317 | 0.3429758789 |
| mixed | 3.4730293999 | 3.3272779398 | 0.3425301728 | 0.3283889806 |

所有 30 个 patch 的 geometry audit 相同：`n_rows=432`、
`rank(P_I)=48`、`high_dim=384`；最大
`||Q_high^H P_I||` 为 `4.88e-15`。共覆盖 `6372` 个 active rows，固定
beta shift scale 为 `9.5111895711`。单 cell contribution 与
`R_i A_schur R_i^H` 的最大 absolute 差为 `7.2934209254`，relative 差为
`0.7745108288`。

## 结论与边界

完整 element patch 和真正的 high-order complement patch 都没有使 high、
mixed source 达到至少 2 倍 contraction improvement；因此两类 oracle 均未过
M4d efficacy Gate。该路线受控停止，不扩展 MPI incident-cell 通信，不做
damping/参数扫描，不做 face/edge patch，也不启动 PDE。

失败实验收口后未保留任何 M4d production 或 test 实现；本文件是唯一保留的
compact negative evidence。
