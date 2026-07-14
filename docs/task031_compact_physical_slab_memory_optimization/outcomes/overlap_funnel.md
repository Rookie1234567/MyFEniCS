# Overlap / slab 漏斗

16 slabs 的 overlap0.125 相比 overlap0.25 把 h5 factor rows 从 71,344 降到 58,720（-17.69%），factor nnz 从 7,046,752 降到 5,666,368（-19.59%）。200-step residual 从 `8.612e-4` 变为 `1.107e-3`，worker peak 只下降约 2.32%，因此是“较小 factor、较慢收敛”的 weak positive。

20 slabs overlap0.125 的 factor nnz 和 RSS 都高于 16 slabs，residual 也更差，故停止。最终只将 16/0.125 与 matrix-free/lifecycle 正交组合，并用 h5/h3/h2 full solve 验证，不把 screen 的小 RSS 差单独称为成功。
