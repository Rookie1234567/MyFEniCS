# 下一决策

Task026 应只解决一个核心问题：在不超过 14 GB 的前提下，把 h=2 Q 列最大 residual 从 `0.541` 降到 `<0.1`。

优先顺序：Q 低秩压缩释放内存；response reuse/迭代更新；真正 low-order-refined H(curl) hierarchy；最后才考虑 h=1.5 或参数 sweep。
