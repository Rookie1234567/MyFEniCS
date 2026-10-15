# matched108 几何对照准备与矩阵捕获阶段报告

日期：2026-10-15 UTC。范围：`6×2×9`、108 单元、fine p6 / coarse p4 的映射、raw 输入和原装配矩阵捕获；本阶段没有新 solve。

## 结论与目的

为继续查明旧 108 单元上 BAL_H 停滞的原因，本阶段准备一个新的三维网格对照。它已完成实际自由度映射、31 类 raw 输入登记及原装配矩阵 A 和右端 b 的捕获。捕获阶段在原 AS 6 GiB、进程树 RSS 8 GiB 限制内结束。此进展只消除了当前准备环节的资源阻碍，尚未证明 BAL_H 收敛、物理场合格或新方法有效。

旧 `18×2×3` 改为 `6×2×9`，x、z 两个方向同时变化；既定物理模型及波长 0.7 nm 不变。fine p6 表示待求解的高阶空间，coarse p4 表示辅助低阶空间。此处不能把新旧网格描述为“只改变 z”。

## 已完成内容与实测成本

映射负责确认未知量的实际编号和数量；raw 是装配前可复用的单元张量输入；capture 只把原装配得到的 A、b 保存下来，尚未求出场。下表 wall 是每个监督进程从开始到清理结束的时间，RSS 是同一时刻进程树内存采样峰值，不是对象体积之和，也不是连续测得的完整峰值。

| 阶段 | 状态与范围 | 监督 wall 秒 measured | 采样树峰 RSS 字节 measured | 采样数 |
| --- | --- | ---: | ---: | ---: |
| 实际映射 | p6/p4 实际枚举完成；未装配 | 7.036920143 | 562855936 | 25 |
| raw 第一批 | 保留 14 类旧种子，新建 12 类；26/31 完成 | 462.107199464 | 119328768 | 1835 |
| raw 第二批 | 补齐 3 类 fine 与 2 类 p4；31/31 完成 | 130.506557346 | 121913344 | 516 |
| 原装配 capture | A、b 已捕获；零 solve | 63.952559519 | 2479579136 | 251 |
| 本次四段合计 | derived；不含工程准备、独审等待和旧失败 | 663.603236472 | 不可相加 | 2627 |

地图阶段另有内部 RSS 快照 563773440 B，高于外部采样峰；二者口径分别保留。四段均 exit 0、清理确认、无残余进程。新建 17 类 raw 的 kernel 时间分别为 455.952601111 s 和 123.500440818 s，共 579.453041929 s；capture 内部 runtime 为 62.597173667 s。这些都是监督 wall 内的嵌套时间，不再加到 663.603236472 s 上。工程准备、审查和历史失败成本并非零；本报告没有完整端到端日历耗时。`phase4_execution_ledger_v90.json` 是尚未纳入本次 capture 的旧快照，不能冒充已更新的全项目总账。

## 维数和输入资格

| 指标 | fine p6 measured | coarse p4 measured |
| --- | ---: | ---: |
| 完整独立 FE 自由度，不含 80 辅助行 | 70848 | 21120 |
| 凝聚后的 trace 行 | 22248 | 9456 |
| trace 加 80 辅助行 | 22328 | 9536 |
| 本路径 raw 几何类 | 25 exact | 6 rounded |
| 加单元朝向后的类 | 36 exact | 12 rounded |

凝聚是在局部处理单元内部未知量后，把边界未知量保留到全局系统；因此 FE 自由度与最终 A 的行数不是同一指标。exact 与 rounded 是各自原生产路径的几何键规则；类数相同不等于缓存身份相同。

31 类中，14 类保留已有精确上下文种子，17 类为新输入（15 fine、2 p4）。新输入的结论限于同一已资格化编译 C kernel 的来源绑定、有限值和类型/文件身份；没有声称对每个新输入分别完成 O0 等价性验证，也没有据此授予 solver 资格。

## 捕获结果与清理

- A：22328 行，17304176 个非零项，小于实际结构上界 20776096；CSR 与 b 文件合计 347289474 B。
- 原 compiler prefix 调用 13 次、12 个不同 binary；native raw cache 命中 25 次；新 kernel 调用、cold/JIT fallback 均为 0。两组调用计数不同，不能混写为“13 次 raw 命中”。
- 未创建 KSP/PC，没有全局 factor、solve、完整 FE residual、场恢复或 official R/T/A。
- 终态四个 PETSc handle 均为 0，36 类局部因子/恢复引用已清空。原 result 中 `borrowed_owner_cleanup_pending=true` 是保留的中途字段；最终 `owner_cleanup` 与监督清理确认具有终态证据。没有据此宣称 allocator 已归还全部内存。
- 独立 capture 终审通过：4 个 CSR/b 文件的全文件、raw、typed SHA 及 NPY 头均已流式独核；finite 与全部 stored-entry 的结构包含性来自已审 producer 的完整检查，审计没有重新计算这些全数据检查或重新装配。251 个资源采样、33 次 admission 和 5 次 fresh AS 检查通过，全部 regular 产物为 348939164 B。

## 为什么资源结论发生变化

旧 all108 静态加和预测为 6909487720 B，超过 6 GiB AS。这表明那份充分上界不能放行，不能推出该实际装配不可能执行。实际映射确认 fine 为 25 raw / 36 oriented，与已有成功 132 路径的类数相同；沿用其原始对象生命周期与各阶段 fresh 资源检查，避免把不同生命周期粗略叠加成一次峰值。实际类库存重估的静态加和为 5796605032 B，它仍只是预测；真正放行由各原调用点的新快照决定。

| 原阶段 Gate | fresh VmSize 字节 measured | 后续命名预算字节 predicted | ELF 字节 | safety 字节 | prospective AS 字节 derived |
| --- | ---: | ---: | ---: | ---: | ---: |
| 原装配前 | 1081966592 | 3101231648 | 413421600 | 268435456 | 4865055296 |
| capture 导出前 | 2619641856 | 2013516328 | 413421600 | 268435456 | 5315015240 |

两者均小于 6442450944 B；全部五个 fresh AS 检查通过。AS 6 GiB、树 RSS 8 GiB、零 swap 等原硬限制均未提高，未从实测内存中任意扣减重叠，也未把本次 capture 通过外推为后续 p4 因子、BAL_H 或完整 solve 可行。

## 下一步与仍未解决的问题

本报告的截止边界为 capture 结束并独审；后续 solver 仅做 source 准备，未数值运行。拟定配置为 zero start、restart 32、refine always、最多 200 步，仍须独立 source、输入身份及 fresh resource 准入。旧 132/旧 108 的 zero-start 运行使用 refine never；因此未来新结果与它们不是严格单变量比较。若要归因于网格差异，须进一步匹配其余求解设置。

BAL_H 失效原因尚未被本阶段解决。完整原 FE residual、identity、物理场接受与收敛 Gate 均未获得新通过证据；此前 fixed8 A/B 的负结果保持原判，见[前次报告提交](https://github.com/Rookie1234567/MyFEniCS/commit/499b5eb67c69afdb598cee5a540b80f396ea7772)。

## 证据与发布边界

详细标量及每份小证据的 SHA256 见[配套 JSON](matched108_preparation_capture_20261015.json)。主要独审身份：

- map：`5c0be940e7b083a4b656166ef151725f25f8d11dea7f272c5643005646bf85ef`
- raw 第一批：`b4d95cf9779b28760bfcfc75239a7867abd6f355a14d01490fb4f26f8db7311a`
- raw 完成：`0d0928078b0a7ad3a53c197194c05d2f508b2df228f53da66eac14a103e7fc10`
- 资源重估：`81aa4f632ad2738278a0a40c02f1770414ed030e7420adb32cab70125d775517`
- capture 终审：`9e6f449d1f7e3ab3348577ff523c4b2bd45e4ecb23b1da0aaf766b48aa693606`

仅发布本中文 Markdown 与小 scalar JSON，不发布代码、数组、矩阵、因子或归档。此为 connector report-only publication；不声称 canonical 工作树、ABI、CI 或 GitHub rendered-view Gate 已通过。发布前检查 JSON、表格列数、报告范围和 SHA；远端提交及两份文件读回另记发布回执。
