# Selective local solver 漏斗

只把两个边界 slab 改为 Jacobi 可把 stored factor nnz 从 7,046,752 降到 6,345,796（-9.95%），但 worker RSS 仅下降约 0.64%，200-step residual 从 `8.612e-4` 恶化到 `1.178e-2`（约 13.7x）。收益没有抵消收敛损失，因此 Lane F 停止。

固定 Richardson 通过 PC 线性/确定性证书，但 residual 0.7703 表明它不能替代 adaptive local GMRES。最终没有 selective solver 进入 h3/h2，正式 candidate 的 16 个 slab 全部保留 ILU0。
