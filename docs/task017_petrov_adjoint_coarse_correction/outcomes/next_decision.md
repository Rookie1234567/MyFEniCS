# Next Decision

## 决策

不要暂停整个 real-split AMS 主线，但要暂停 Petrov/adjoint W 和 right-only lifted correction 的微调。

下一步只值得继续一条窄路线：

```text
true-FE sampled Schur / selected-mode FE response correction
```

## 为什么不是全线暂停

Task017 找到了 Task016 没有的正信号：

| 方法 | default100 residual | improvement |
|---|---:|---:|
| baseline FE-AMS + aux identity | `2.146555954e-2` | `1.0x` |
| right-only P_FE lift | `2.146459669e-2` | `1.000045x` |
| true-FE sampled lift top_bottom_y one-shot | `3.688783940e-3` | `5.819x` |

这说明 dominant zero-order modal direction 本身有价值，失败点主要在 FE lift 近似和 KSP 集成方式。

## 为什么不能进 p=2

Stage D KSP 失败：

```text
true-FE lift right PC residual = 2.354987702e-2
baseline residual              = 2.146555954e-2
```

one-shot 成功但 right-preconditioned additive PC 变差，说明不能把 one-shot correction 直接当作当前 KSP PC。

## 建议的 Task018

建议下一轮任务只做：

1. 把 true-FE sampled correction 作为 initial correction / residual correction，而不是 right additive PC。
2. 尝试 recycled/augmented GMRES：把 `Z_true_fe` 作为 Krylov augmentation space。
3. 对 selected FE RHS 做更稳的求解：SciPy GMRES 更严格容差、shifted FE solve、或 1-2 RHS 的 guarded direct/BLR。
4. 只在 default100 p=1 h=5 上做 gate，不进 p=2。

## 暂停项

```text
Petrov W_aux_residual / W_AZ / W_adjoint_diag / W_adjoint_pfe
right-only pfe_lift / diag_lift
top-only correction
p=2 h=5
full 708-mode Schur
```
