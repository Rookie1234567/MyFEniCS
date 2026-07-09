# Next Decision

## Decision

Task016 应专攻：

```text
dominant zero-order Rayleigh/Floquet mode 的 FE+aux lifted coarse correction
```

## Why

| evidence | meaning |
|---|---|
| FE-AMS 后 aux residual fraction = 0.999 | FE local inverse 已不是第一瓶颈 |
| top,(0,0),y 占 aux residual 约 100% | 慢方向是低维 modal/global direction |
| aux exact / aux diag / aux-space modal 均无改善 | 只处理 auxiliary coordinate 不够 |
| Schur_diag 变差到 4.427e-1 | diagonal FE inverse 不能代表 coupled Schur |

## Proposed Task016 Implementation

1. 只取 dominant zero-order aux mode 开始：`top,(0,0),y`。
2. 构造 FE trace/volume lifted vector，与 aux coordinate 组成 coarse basis `Z`。
3. 使用 `Z^T A Z` 或 complex Hermitian counterpart 做低维 exact coarse correction。
4. 对比 default100 p=1 h=5 的 true residual；只有达到 10x 或 `<=1e-6` 才进入 p=2 h=5。
5. 若单 mode 有效，再扩展到 top/bottom zero-order x/y 共 4 个 modes。

## Stop Rule

如果 lifted zero-order correction 仍不能把 default100 residual 降到 `1e-2` 以下，则暂停 real-split AMS 主线，重新评估 FE block proxy 与完整 indefinite Maxwell preconditioner。
