# Krylov 与 PC 合法性比较

Task031 不能直接用普通 GMRES 替换 FGMRES。Task030 的两步 local GMRES smoother 根据输入自适应选择系数，实测 PC linearity error `2.374308e-2`，远高于 `1e-11`，runner 因而 fail closed。TFQMR/BiCGStab 等固定线性 PC 方法同样不进入正式漏斗。

固定两步 Richardson 把误差降到 `3.611e-15` 且 determinism=0，但 h5 200 步 residual 停在 0.7703，证明“线性合法”不等于“有足够平滑能力”。因此最终配置保留 FGMRES90。

restart50 把 h5 200-step worker peak 从 1.693619 降到 1.661560 GiB（-1.89%），但 residual 与时间都变差，按 `<3%` 停止规则拒绝。Krylov payload 模型确实下降，但未转化成足够的 full-process peak 收益。
