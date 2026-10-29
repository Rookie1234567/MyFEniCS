# Task41extra Response V19：两单元 native rank-1 来源已绑定，科学问题仍未判定

**结果分类：V19_SELECTED_NATIVE_RANK1_AUDIT_COMPLETED；AUDIT_COMPLETED_DATA_COMPLETE。** 本轮只在 cells 7873、8014 和原 known 两列上，重放 native rank-1 的 curl/material-mass 贡献、原序 scatter/MPC/ghost 与分量合并，并由只读 checker 复核。原始目标行和两格的 900 个内部行在两列上均与保存的 native volume RHS 逐位相同。三段复数误差账在 Decimal 80 位与 100 位都闭合。

闭合只说明这组有限证据可复核。local/rank-1 项 A−Q 是主要差值来源，assembly/order 项 Q−b_replay 较小；这不能单独判定旧局部矩阵或新 native rank-1 核哪一方有误。历史 producer kernel identity 仍为 UNKNOWN，因此本结果不是历史 action 的 bitwise replay，也没有解锁 full owner 或 official result。

## 1. 固定身份与实际范围

| 项目 | 记录 |
|---|---|
| 执行分支 / 本轮 frozen source | task41extra_phi90_p50x50_g17x20 / 12718ec898588eb94a7cd0f9d747dd21f8da9231 |
| B0 输入 | b0_p6_07nm_iterative.dat；SHA-256 a0c45d0475bd2b41d2d19589831086468a62f39fdca5b74734b62751df1485c1 |
| 真实合同 | execution_contract_source_12718ec898588eb94a7cd0f9d747dd21f8da9231_v19_selected_native_rank1_6h.json；SHA-256 41dfb466225b878de873422d2881aa71cd5aba3b81bc6ad0de73aac29e64d6e0 |
| 固定窗口 | SHA-256 c73baa18cf2bdc599e45d5fa19592ffccdb4680907c7145fdd9d031c54945350；T0 2026-10-29T06:58:54.288229236Z |
| 唯一目标 | active row 1,622,464 → original full-storage row 5,218,672；cells 7,873、8,014；两列；curl、material_mass |
| 服务终态 | myfenics-case-20261029T080936-3792255.service；invocation 725c548de9bc4a4cb56a2cebe4d1d5ef；systemd Result=success，exit 0，后代清场 |
| ABI receipt | SHA-256 1c4277c83a0ac6daf02197086264b9e5b337caee1b33d7cc1dd22a7dfcefe57d；正式服务 preflight 绑定 complex128、int32、MPI 1 |

所选 target/internal 行均不触及 MPC slave/master；本次 MPI1 记录的 ghost rows 为 0，因此这里没有把非平凡 MPC 或 ghost 行行为外推到其他行。

工作区的 source commit 12718ec 对 worker/cache-hit 身份路径和 checker 接线作了窄修复。真实 FFCx 缓存命中返回 Form.code=(None, None)；实现只接受这个精确 sentinel，并继续要求 compiled module 与非空 FFCx C source 可哈希。partial-None、缺源、空源、module 路径不匹配或 hash 缺失仍拒绝。历史 attempt 04 的原错误与回执保留，未把 guard 放宽为任意 None。

## 2. Native 绑定与三段有符号分解

Checker 状态为 BOUND_SELECTED_TARGET_AND_900_INTERNAL_ROWS，原因 EXACT_SELECTED_ROWS_MATCH；两列目标行和两格各 450 个内部行均 bitwise match 保存的 volume RHS。b_alpha 的 binary64 复数值两列均为 [0, 0]。历史 producer 的 FFCx/kernel identity 未被 V3 pinned closeout 记录，checker 正确分类为 RECONSTRUCTED_SELECTED_NATIVE_ACTION_NOT_HISTORICAL_BITWISE_REPLAY。

下表各复数写成 [实部, 虚部]。A−Q 是候选存储矩阵作用与新抓取 native rank-1 贡献和之间的差；Q−b_replay 记录原序 scatter/MPC/ghost/最终 curl 与 mass 合并造成的变化；b_replay−b_saved 是对旧 native volume RHS 的绑定差。

| 列 | A−Q：local/rank-1 | Q−b_replay：assembly/order | b_replay−b_saved：binding | Decimal 80 位闭合 | Decimal 100 位闭合 |
|---:|---|---|---|---|---|
| 0 | [+2.7183207090801107677763301170e-10, −3.1643893574485829931823898593e-11] | [+3.63797880709171295166015625e-12, −9.094947017729282379150390625e-12] | [0, 0] | [0E-74, 0E-74] | [0E-94, 0E-94] |
| 1 | [+2.5650630363420706811378149907e-10, +5.4366414181602215355526602340e-10] | [−1.818989403545856475830078125e-11, +7.2759576141834259033203125e-12] | [0, 0] | [0E-74, 0E-74] | [0E-94, 0E-94] |

80/100 位是把保存的 binary64 操作数按十进制精度重算的诊断闭合，不是生产精度，也不表示原生算子绝对精确。不能把不同有符号分量的范数比例相加成“原因百分比”。

目标原行上每个 cell/component 的有符号 native rank-1 贡献如下；表格中的数值为便于阅读而截断显示；精确保存值以 checker 报告及 compact JSON 为准：

| 列 | Cell | curl [实部, 虚部] | material_mass [实部, 虚部] |
|---:|---:|---|---|
| 0 | 7873 | [37215.5375901565930689685046673, 23412.0243978308026271406561136] | [−194899.1459236452355980873107910, −122615.7645997557410737499594688] |
| 0 | 8014 | [11782.3770956239713996183127165, 7256.01935802765001426450908184] | [−20205.9013714610191527754068375, −12444.7453879041368054458871484] |
| 1 | 7873 | [−51019.0507824825835996307432652, 74431.0751803131861379370093346] | [267182.5272475340170785784721375, −389798.2918472904711961746215820] |
| 1 | 8014 | [−16308.7348332202345773112028837, 23564.75419124794279923662543297] | [27967.0573550179251469671726227, −40411.8027429220383055508136749] |

在两 cell 精确项和到原序 scatter 的分解中，列 0 的 curl 差为 [3.63797880709171295166e-12, 0]、material_mass 为 [0, −9.09494701772928237915e-12]，最终分量合并差为 0；列 1 的 curl 差为 [−3.63797880709171295166e-12, 7.27595761418342590332e-12]、material_mass 为 [0, 0]，最终 curl/mass 合并差为 [−1.45519152283668518066e-11, 0]。这些小项比 A−Q 小，但不证明 A 或 Q 哪一个更正确。

## 3. 解释、历史失败与下一缺项

目前证据把主要差值定位在 assembly 之前的 A−Q local/rank-1 段；Q−b_replay 可量化原始积分项到原序散射和分量合并的差。不能据此认定 actual_qmetric_blocked_gram 或 native kernel 是错误方，也不能断言这是唯一根因。下一步应在同一 cells 7873/8014、同一实际积分列表和原始两列 known RHS 上，取得原始 FFCx rank-2 local action（curl/material_mass；每格的 rank-2 local matrices可供两列 RHS 复用），或保存足以定位 rank-1 积分阶段的关键中间量。它用来区分已存局部矩阵作用与 rank-1 积分求值；本包没有生成该证据，也没有 LU/GETRS。

原始全域 action 的最新 FAIL 数值仍来自 V15：两列约 5.7625744836e-11、1.2123684644e-10，对 1e-11 门限失败。本次 checker 的 original_action_source 字段字面写着“inherited V9 full-action result”，这是历史标签；V19 review §1 所引用的最新全域值来自 V15。保留原 checker 字节，不据此重跑或改写 checker。

四次服务尝试失败的原始证据均保留：072200 因 IntegralType 导入失败（parent worker supervise 4.305215 s）；073009 因 V16/V3 vector-index 常量导入错误（4.155510 s）；073557 因 known-field layout 检查误判（13.811376 s）；074947 因未识别合法 Form.code cache-hit sentinel 失败（85.490359 s）。另有两项更早的工程事件：一次 prepare 因 legacy 与 named-instance 参数互斥而在写入前拒绝；service `myfenics-case-20261029T070552-3773295.service` 的内层 `set -u` shell 因 `task41_v19_checker_only` 未初始化而退出。两者均未启动科学 worker，单独耗时均为 UNKNOWN。最终 080936 服务完成。完整来源、错误日志 hash、费用和服务回执见 [attempt index](outcomes/v19_closeout/attempt_index.json) 与 [evidence index](outcomes/v19_closeout/evidence_index.json)。

## 4. 服务、资源、窗口与测试

| 口径 | 结果 | 说明 |
|---|---:|---|
| 最终 systemd service parent | 约 109.385499 s | receipt start UTC 样本至 systemd terminal journal 记录的时间差；不是 child 阶段相加 |
| window 对最终服务及 closeout 计费 | 109.112458 s | ledger sequence 108 entry 至 sequence 204 closeout |
| worker / checker parent supervise | 95.248628 / 12.461595 s | service 内部阶段，不与父时相加 |
| watchdog worker / checker | 95.060705 / 12.086510 s | 嵌套子阶段，不与父时或相互重复相加 |
| worker / checker sampled process-tree RSS peak | 4,010,008,576 / 226,971,648 B | 两阶段分别采样 |
| 专用 unit cgroup memory peak | 3,522,281,472 B | 同一 unit 跨 worker/checker 的累计峰；不是checker独占峰，也不能与 tree RSS 相加 |
| 专用 unit task swap peak | 0 B | gate enforced；全局 pswpin/out 在各阶段的 delta 均为 0 页，但不归因到单个任务 |
| PSS / 后代 | 未采样 / 已清场 | PSS disabled by profile；终态无子进程 |
| V19 新科学证据 / 账本快照累计值 | 608,262 B；账本 seq204 服务收口快照 4,352.710821 s（08:11:26.999012Z），文档收口 seq205 快照 5,727.804737 s（08:34:22.092927537Z） | 字节数低于 16 MiB；两个累计时间均为注明时刻的账本快照，包含此前准备、失败尝试和收口，不是本服务独占时长或最终 campaign 成本 |

固定窗口为 21,600 s 总量、20,400 s 数值截止、1,200 s 收口保留。账本 seq204 在 2026-10-29T08:11:26.999012Z 的服务收口快照为 4,352.710821 s；seq205 在 08:34:22.092927537Z 记录文档收口后累计 5,727.804737 s。后续发布成本尚未记账，因此两个数值都是带时间戳的快照，不是最终 campaign 成本，也不用于报告当前剩余额度。V19 结果在数值门限前完成本地诊断，没有触发时间 Gate。资源限制分属不同口径：计划工作集上界 17,179,869,184 B（16 GiB）不是实测峰值；累计 raw artifact 上限也是 16 GiB，但它是另一项累计写入限制；专用 task cgroup memory cap 为 1,649,267,441,664 B（1.5 TiB），`MemorySwapMax=0`。8 个 NPZ term archive 合计 529,744 B。服务收口回执的写后磁盘检查为 `POST_WRITE_CHECKED`：本次 invocation 1,864,510 B、窗口输出树 3,008,821 B、保守窗口输出树 91,688,351 B、已记录累计 raw artifact 15,603,033,504 B、V18 compact 累计 evidence 15,694,682,876 B、当前可用空间 1,974,225,555,456 B（底线 2,147,483,648 B）。这些是不同统计范围，不能彼此相加替代回执定义。

主控在最终冻结 source 的资格化环境对 V19 native-rank1 与 checker 两个定向测试文件执行 28 passed / 4.18 s。此前 23 passed / 5 failed 的测试记录及原因保留在 preparation history；最后加入可哈希 module fixture 后才得到 28 项全过。本轮包含 mesh/form 准备及 8 次所选 native rank-1 kernel 抽取并保存诊断项；没有完整 FE/PDE 求解、全域 action 或 full owner。

## 5. 资格边界

本包只证明所选两格/两列的现有 native rank-1 产品能被保存、重新读取、绑定至覆盖行并完成独立有符号归因。没有运行新的 rank-2 kernel、factorization、GETRS、完整 native action、full owner、200q、恢复、FGMRES、完整场、独立 A6 或 official R/T/A；official_result=false、scientific_qualified=false、full_owner_unlocked=false，ordinary default 未改变。

详细数值与输入输出哈希见 [V19 compact](outcomes/v19_closeout/v19_selected_native_rank1_compact.json)、[evidence index](outcomes/v19_closeout/evidence_index.json)、[attempt index](outcomes/v19_closeout/attempt_index.json) 和 [outcomes summary](outcomes/summary.md)。科学源码已由主控冻结并推送，source SHA 为 `12718ec898588eb94a7cd0f9d747dd21f8da9231`。本执行者未提交或推送结果文档；文档由主控集中审阅和收口。
