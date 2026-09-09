# 13.5 nm 原生复现与性能诊断

| 运行 | 原因 / Gate | 结果 | source / evidence |
|---|---|---|---|
| R1 attempt1 | p4 LU 后旧固定 mode 字节哈希校验失败 | 未进入 outer；不是数值失败 | `492cd519da07a8790980f9f2f21cbef24bed1643`；[记录](records/r1_attempt1.json) |
| R1 attempt2（迁移 retry1） | 首段 1800 s 先到，62 步 true=0.019433158954790204 >0.01；仅一个32步检查点，趋势证据不足 | `SCREEN_BUDGET_NO_QUALIFIED_PROGRESS`；性能受控负结果 | `b2e132a7b1f1078eb3359c87a336123b3c7dfbdd`；[记录](records/r1_attempt2.json) |
| R2 / S5 / S3 / S2 / G | 前置复现未通过 | `NOT_RUN_BY_PREVIOUS_GATE` | [索引](records/run_index.json) |

R1 attempt2 的 A/b/PC 仍是原 V5 BAL_H + accurate global p4 LU。p6 storage/independent rows 为173802/164592，p4 storage/independent rows为53084/48960，增广53164行、NNZ24730144、factor NNZ53417584，252个hexahedral单元、80通道。124次p4原残差全部通过，最差4.893382586118271e-11 ≤1e-10，修正次数0；fine未达到1e-6，不存在official场、R/T/A/A_volume或匹配参考通过结论。

筛选在一次PC/外迭代返回后的安全检查点执行：1834.519 s作出停止决定，末次显式残差1840.087 s，含残差数组保存和释放前记录的solve阶段1845.755 s。没有把1800 s改大；这些差额是安全检查粒度，完整记录保留。只创建/求解/销毁一个KSP，restart32、max2048、zero start。

## 逐阶段时间与内存（attempt2，measured）

下表wall为相邻marker区间，RSS为区间内同时存活的parent、MPI、compiler、worker整树之和的采样峰值，单位GiB=2^30 B。marker名代表区间起点，不能把“complete”后的区间误读成该操作的纯计时。未单独标记的操作不强行拆分；各阶段峰值不能相加。零样本短区间在JSON记null，不能写0内存。

| marker区间 | wall / s | 同期整树RSS峰值 / GiB | 样本数 |
|---|---:|---:|---:|
| `shared_mesh_spaces_started` | 2.333 | 0.379 | 7 |
| `h6_original_setup_started` | 150.675 | 1.227 | 433 |
| `fine_physical_started` | 78.389 | 1.337 | 222 |
| `native_physical_started` | 26.739 | 0.978 | 75 |
| `owner_transfer_started` | 12.635 | 0.861 | 37 |
| `reference_volume_compile_started` | 25.544 | 1.626 | 70 |
| `reference_metadata` | 1.286 | 1.149 | 4 |
| `reference_volume_pattern` | 1818.610 | 1.395 | 4968 |
| `reference_volume_complete` | 1.068 | 1.646 | 2 |
| `reference_symbolic_started` | 1.125 | 1.857 | 3 |
| `reference_numeric_preflight` | 8.069 | 2.788 | 21 |
| `setup_vector_identity_started` | 9.628 | 2.857 | 25 |
| `setup_vector_identity_complete` | 9.596 | 3.163 | 25 |

整次workflow为3997.651 s，整树峰值3395833856 B（3.163 GiB），10676个样本、不可读样本0，最大相邻样本间隔0.466 s；最小有效可用内存1990113640448 B，高于reserve324465062092 B；job及系统swap使用/换入换出增量均0。CPU worker23、parent9。代码/输入/实际动态库/命令及前后clean source证据保留在原始run_manifest和compact中。整个watchdog的`WORKER_FAILED`是worker对筛选负结果返回非零的通用退出分类，数值层具体原因为screen，不是崩溃或OOM。

每PC的中位时间：两次fine A_structure 10.953 s、两次C校正9.436 s、H6 smoother1.319 s；完整外步约29.6 s，额外fine action和定期true检查另占时间。与旧曲线共有的第32步，native/WSL完整true分别0.07312259253871085/0.07312259253902377，绝对差3.1292e-13；第12/24/44/56步仅将当前reported与旧explicit作辅助对照，未冒充完整场资格。旧第32步约348.8 s，本机956.6 s；迭代进展相近，单位步骤耗时显著变长。

## 生命周期与对象口径

本次已保存末次解/残差数组，随后释放KSP、p4 factor/matrix及辅助stack，才进入checker；负结果不做official recovery。释放前RSS3078672384 B，释放后3074478080 B，只下降4194304 B。销毁调用完成不等于allocator立即向OS归还页；现有证据不能证明具体哪些页仍被allocator或其他活对象持有，也不能称为内存泄漏已定位。进程最终全部退出，watchdog验证descendants_cleared=true，隔壁8个原MPI进程仍位于CPU0–7。

单个p6 complex128向量为2780832 B、约65个FGMRES基向量载荷180754080 B；p4因子按NNZ×16仅值载荷854681344 B。这些是derived载荷，不含索引、工作区、wrapper和allocator，不当成实测对象峰值。JIT、DtN、矩阵和传输目前只有同时存活阶段账，无法从RSS差精确分摊。没有已通过的完整recovery峰值，后续必须补测。

## 身份迁移与既有失败

用户提供`task39extra`提交`72a0f58899dc5d98aa4c170edffb573ed50067c7`的native_handoff_v1。逐文件大小/hash通过；只读提取材料，未merge或cherry-pick代码。历史mode原件86377 B，SHA为`dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2`，本机实际SHA为`d4380495d912f97f6d303a85756bb9b252a1117bad229b559f0ac8140e745fbb`。12个浮点字段末位差、最大相对差1.8786939359547627e-16，离散字段/数量/顺序完全相同。现按原1e-10逐字段比较、分别保留两端字节hash；在装配前验证，未改写历史hash。见[bridge](records/native_mode_bridge.json)、[receipt](records/handoff_receipt.json)。

attempt1 workflow2731.775 s、p4装配2301.507 s、峰值2.787 GiB、6075资源样本、swap0。其监督器曾与worker争用CPU8，后迁到CPU9；worker依用户要求迁到CPU23。运行中干预单独记录，不能与之后固定绑定的冷启动当严格受控A/B。一次禁用NumPy部分CPU分派诊断产生另一个hash40b02a...，不是正式native身份，不混入bridge。

## 变慢原因与已实现的局部修复

| 证据 / 改动 | 实测诊断结果 | 解释和边界 |
|---|---|---|
| CPU23实际约3.57–3.60GHz，fp_assist=0 | 工作核心没有重现CPU2的1GHz限频 | 不把整机2TiB容量等同于单核速度；未改变电源/风扇/MSR |
| 原p4采样99.75%落在FFCx单元积分 | 汇编存在4800 B跨行步进和寄存器spill | 同一份C、同一CPU的对照支持内核访问顺序是可修复瓶颈 |
| 仅O3/native编译原p4循环 | 1.18倍左右；不足以解决装配慢 | 原/WSL均O2、x86-64 generic，不能称为少了原本启用的O3 |
| p4把独立矩阵元素循环改为按行遍历，严格浮点AVX512编译 | 两积分×三几何6项逐位相同，3.55–3.61倍；真实单元CSR装配6.935→1.929 s | 保持每个Aij求和顺序；不是新离散或新PC；252单元约8.2分钟只是预测 |
| 合并curl的12个独立系数循环 | 原生成C对照：p6 21.066→10.572 ms/单元，p4 3.979→2.833 ms，逐位相同 | 每系数仍按原ic顺序相加；真实p4/p6 action测试也逐位通过；不代替完整solve |
| 直接给所有action加512-bit编译参数 | p4 curl曾退化到0.60倍 | 已拒绝该方案，不把更宽向量一概视为更快 |
| native PSS降为约5 s；worker安全检查不读PSS | 整树采样0.075–0.113→0.032–0.038 s | RSS/swap仍每轮采样；未采PSS为null且显式标记，安全Gate不变 |

FFCx hook仅作用本进程、当前单线程native配置、明确的p4/p6张量形状；退出即恢复，不修改系统FFCx文件或隔壁环境。新cache key含专用macro，防止读取旧生成实现。原数学、积分metadata、复数精度、PC与所有Gate不变。源码已实现的优化尚无新的完整R1证据，不能声称已恢复笔记本整次速度。所有诊断、被拒绝方案和hash见[kernel evidence](records/kernel_performance.json)。旧笔记本当前CPU探测为i7-13620H，不补齐旧运行时频率证据；两端总性能差尚不能完全分摊给硬件代际、编译或共享带宽。

任务书§11明确规定fine未在screen/solve预算内通过时停止主阶梯，不能当bug重新抽签。当前保持该负结果；性能修复可审阅，但额外正式R1重试需要用户对该停止约束的明确例外授权。未启动R2、条件reference或短波，未绕过Gate。
