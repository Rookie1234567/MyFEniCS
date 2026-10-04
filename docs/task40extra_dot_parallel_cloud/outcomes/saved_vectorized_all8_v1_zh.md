# 保存数据的八组投影与四项同条件比较通过

本次 d6ae70a 的向量化行合并实现完成全部八组保存数据投影：所有系数差为0，CSR指纹逐字节等于原17c目标。四个c81标量/新实现同条件小样本也逐字节一致。这是同80单元、p4、manual532的保存数据投影资格；没有新FE、JIT、分解、完整逆或PDE运行，原17c完整配对逆的资格仍绑定原源码。

监督总耗时231.886秒，全部八组重放224.787秒，进程树RSS峰值352,264,192 B，swap0，清理通过。投影owned峰值27,957,560 B，小于128 MiB门限；借用数据、Python和native工作区仍由整树资源门分别约束。行选择、索引转换和有限性检查的临时数组在分配前计入预算，保留原标量回退路径。

| 同条件单recipe / 初始状态 | c81 add秒 | 新add秒 | 单次观察比值 |
|---|---:|---:|---:|
| volume/cell/0 / 空 | 0.7035 | 0.1064 | 6.61 |
| volume/cell/0 / 合成已有CSR | 1.1119 | 0.1455 | 7.64 |
| direct/C/port/2 / 空 | 0.2804 | 0.0579 | 4.84 |
| direct/C/port/2 / 合成已有CSR | 0.5975 | 0.0751 | 7.95 |

上述比较关闭profiler，保持相同callback、JSON编码、tile128和owned预算；执行顺序固定先旧后新，可能受热缓存影响，每项只有一次观察。合成seed只是成本控制，不是实际累计算子。比值不是通用加速率，也不能用完整旧live setup约2066秒除以本次saved replay224.787秒声称端到端提速。

八组全部recipe/顺序/标签、四对角及四交叉比较仍保持1e-11门限；本次是更强的零差与CSR指纹相同结果。183项集成测试和3项driver测试通过，原600秒受控停止及四项成本诊断完整保留。该结论不补写早期失败，也未取消原目标门。

日志仍有138,020条事件、91,505,813 B；匹配样本的新日志也多于旧实现，不能称日志优化完成。完整包4,388,484 B、15成员已保存Library并新目录核hash通过；[保存回执](records/saved_vectorized_all8_v1/library_receipt.json)提供恢复身份。完整[八组结果](records/saved_vectorized_all8_v1/all8_replay.json)、[同条件四项](records/saved_vectorized_all8_v1/matched_four_cases.json)、[精简记录](records/saved_vectorized_all8_v1/compact.json)及[独立源码审阅](records/saved_vectorized_all8_v1/independent_source_review.json)保留实际计数、费用和限制。下一步接入live流程前仍需按其源身份重新资格化；原尺寸/AUTO/物理精度/2TB/48小时没有由本次证明。
