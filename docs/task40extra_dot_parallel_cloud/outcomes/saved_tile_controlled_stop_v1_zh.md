# 保存数据投影重放：600 秒受控停止

本次优化验证未完成，不能称加速成功。冻结源码 c81e286 只对已保存的 17c 配对算例做稀疏投影重放，没有 FE、JIT、新因子或 PDE 运行。原 17c 配对全 q 逆及 399 项检查通过的结论保持其原源码与证据身份，本次未把该资格转移给修改后的投影实现。

监督在 600 秒触发 PERFORMANCE_CONTROLLED_STOP，终态耗时 601.272 秒，进程树 RSS 峰值 337,399,808 B，swap 为0，所有子进程已清理。117 项源码/代数测试通过不替代完整数值重放。

| 已完成 twist0 比较 | 投影 tile | 精确结构跳过 tile | owned 上界 B |
|---|---:|---:|---:|
| (0,0) | 2,255 | 112,270 | 26,374,924 |
| (0,2) | 2,878 | 119,282 | 26,786,764 |
| (2,0) | 2,878 | 119,282 | 26,705,780 |

三组各自保留509条有序recipe，完整CSR字节hash与冻结目标相同；全部条目的Frobenius与最大项误差为0，门限仍为1e-11。交叉块按两个对角尺度分别检查。128 MiB owned Gate 仅约束明确列出的自有数组，不能冒充树 RSS。结构跳过数说明避免了空tile投影，不等于整体提速。

其余五组及相同条件的旧/新耗时对照未完成；没有完整八组优化资格、加速倍数或日志节省结论。最后事件停在新的CSR合并阶段，保留35,668条事件及资源日志。下一步先利用已保存日志定位支持发现、合并和记录的成本，再决定是否值得修正；本记录不批准自动增加时间或重跑。

失败包1,502,553 B已存Library并从新目录取回，13成员全部hash通过；完整恢复ID及SHA在[保存回执](records/saved_tile_controlled_stop_v1/library_receipt.json)。[精简记录](records/saved_tile_controlled_stop_v1/compact.json)、[逐字保留的部分结果](records/saved_tile_controlled_stop_v1/partial_result.json)与[源码审阅](records/saved_tile_controlled_stop_v1/independent_source_review.json)保留实际成本、计数、源码和限制。原尺寸/AUTO/物理精度/2 TB/48小时均未由本次验证。
