# C1c：紧凑端口表示与全部 y 周期块的完整三维逆验证

本次已通过 worker、独立保存数据检查器和 Library 完整取回验证。在同一缩小几何的 80 单元 p4 算例中，两组实际局部单元缓存保留了全部内部自由度及固定的 532 个物理模式；四个周期块共同提供规则原算子的逆，并用于完整三维缺口原算子的右预条件迭代。

这一步改变存储和线性代数组织。最终方程残差、恢复后的场和模式输出仍在完整三维原算子上检查。它没有证明原尺寸、完整 AUTO 模式集合、目标精度或整机 2 TB / 48 小时可行性。

| 项目 | 实测或通过结果 |
|---|---|
| 源码 | 本地 clean `17c0a656`；tree `c48eed05`；完整身份见紧凑记录 |
| 网格与自由度 | full80 / local40×2；p4；原独立自由度 15,872，内部自由度 8,640 |
| 物理模式 | 原有序 532；局部 sector 为 228 / 304；全部原索引恰好一次 |
| 四块规模 | 1,884 / 1,960 / 1,960 / 1,960 |
| 四块与新鲜 C1b 对照 | 相对 Frobenius 最大 `7.6099244e-16`，最大元素相对误差最大 `1.2633343e-15`，门限 `1e-11` |
| 四个局部跨分支方向 | 对各自两个对角块范数的泄漏最大 `2.4634398e-16`，门限 `1e-11` |
| 全部预因子 Gate | 四块、四跨方向、原模式分区、字面系数/真实 MPC、完整局部 RHS / recovery 均在首个 q LU 前通过 |
| 四个 q 因子 | 全部保留；setup `0.46135 s`；重复、线性与原块真残差通过 |
| 完整原规则算子 | 四类负载；最大真残差 `6.6834162e-12` |
| 完整原缺口算子 | 同一明确的两单元缺口；四类负载；最大真残差 `7.9671203e-12` |
| 缺口迭代次数 | generic / interior_only / physical / notch_supported 为 4 / 4 / 3 / 4 |
| 恢复与输出 | 任意全部内部 RHS、非零端口 RHS、MPC slave-zero、恢复场；八组 532 模式振幅 / E / H / 功率诊断及必要 global 输出全部通过 |
| 缓存生命周期 | 两组 live 缓存保留到全部 PC apply 结束；数值摘要前后相同；27 次完整 recovery、108 次 q solve；无每次 apply 重建 |
| worker | `2,086.832 s`；完整进程树峰值 `656,293,888 B`；swap0、子进程清理通过 |
| 独立检查器 | 399 检查全通过；`29.931 s`；峰值 `427,638,784 B`；swap0、清理通过 |

四个 q 因子的输入 CSR 有完整相同维度、非零数和新鲜 C1b 对照。实际块并未把物理模式或内部多项式通道删掉。存储中的原 H 是小型对角表示，Hhat 的修正保持为 Di / XiB 因子；没有常驻 Hhat 方阵，也没有候选 full-Ny S / F / Q。保存的 C1b fullQ 只用于验证映射。

两组实际内部数值缓存分别为 28,901,952 B；独立端口 backing 分别为 4,812,896 / 6,300,688 B。这些命名 payload 不是 RSS，跨分类有重叠，不能直接相加当作峰值。原 worker 顶层便捷 cache 字段为 null；紧凑记录从实际嵌套 inventory 提取数值，没有改写原报告。

主要成本在 setup：四个对角块与四个跨方向全部投影约耗时 2,066 s，随后因子与完整原方程检查约 17 s。当前 bounded accumulator 仍遍历全部输出 tile，才发现其中很多 tile 没有支持；逐次 admission 和每模式 provenance 也产生大量重复 JSON。这是下一步原 32k 模式路线需要解决的具体工程瓶颈。当前成本不能外推为原尺寸成本。

独立检查器从保存的原始数组重算完整稀疏投影、局部 LU RHS / recovery、原 C / D / H 方程、恢复场和每模式输出。体积分作用是保存的实际 live FFCx 权威向量，检查器没有另做独立 FFCx 装配；完整 3,968-column 映射和 live 缓存生命周期仍明确是 producer 控制。四个跨方向是每个局部 twist 内的两方向，没有声称重新完成全 16 对 full-Ny 扫描。输出是边界诊断，未提升为正式目标 R/T/A。

全部原始数据已经持久化。primitive 数值 payload 为 229,239,168 B，保持在 512 MiB 科学 Gate 内。完整 packet 因 JSON 与 journals 达到 1,714,777,634 B；旧 1 GiB 打包保护停止被保存，随后仅获得 2 GiB 的完整证据保存例外。没有改变数值 Gate、删除文件或压缩精度。ZIP 实际 181,347,965 B，6 parts；新空目录取回后 4,754 文件及 4,199 NPY 的所有字节、shape、dtype、numeric hash 均通过。最终检查器 packet 的 13 个成员也完整取回通过。

原始 worker recovery index：`libfile_60d8198784848191b6df98edc928d187`。最终检查器：`libfile_6cc685d92a688191944d130638f0df20`。小型 Git 证据索引和完整 SHA 见[紧凑记录](records/paired_C1c_allq/paired_C1c_compact.json)、[worker Library 索引](records/paired_C1c_allq/worker_library_index.json)、[检查器保存回执](records/paired_C1c_allq/checker_library_receipt.json)及[源码独立审阅](records/paired_C1c_allq/source_review_receipt.json)。

测试和失败记录保留：最终 185 targeted tests + 50 subtests 通过；曾出现的四个测试 fixture 放置错误、clean-source 空字符串 schema 错误、历史 AST harness 对已集成 baseline 的假设错误和 1 GiB 打包停止没有被改写为科学失败或科学通过。本次完整费用还包括 source/review、先前 C1a / C1b、运行环境、checkpoint 和失败成本；表中的 worker 时长不是 48 小时目标的全部成本。

下一步先在此次完整保存的八个 recipe / CSR 上验证精确结构 tile 支持跳过和可逆 journal 表示，保留相同 `1e-11` 比较门限及 128 MiB owned projection Gate，以同一 instrumentation 测量前后耗时与日志字节。通过后再进入公开 backend / AUTO setup 成本探针；原尺寸 factor fill、外层向量、6241 点面 Gauss 缓冲、C / D 存储、全模式收敛和物理精度仍是待关闭的 Gate。
