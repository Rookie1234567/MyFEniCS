# Factor deduplication 结果

对 16 个 slab factor 使用精确结构/数值 SHA-256 fingerprint。h5、h3、h2 的 `unique_factor_classes` 均为 16，`exact_duplicate_factor_count=0`。几何周期或材料相似不等于离散 factor 完全相同；MPI owner 分布与边界/overlap 也会改变具体矩阵。

任务书只允许 exact hash match 或 action error `<=1e-13` 的共享，第一版禁止近似复用。因此本 lane 的可靠结论是“无可共享 factor”，不实现 refcount/dedup pool，也不尝试按材料标签近似合并。负结果进入 Case070 与 checker，防止后续重复尝试同一假设。
