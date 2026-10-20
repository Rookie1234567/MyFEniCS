# Task41extra Review V6 回应：28,000 格候选完成，完整两列作用仍未过门

**结论：V6 的 `actual_qmetric_blocked_gram` 候选确实把 28,000 个实际几何键全部构建出来，并完成八个局部代表键筛查；但最终两列 p6/native 完整作用误差分别为 `1.718320912676268e-10` 与 `3.6180522433931414e-10`，均高于原 `1e-11` 限值。因此 full-action gate 失败，`official_result=false`，依 Review V6 明确停止，不进入 200q、factor、KSP/FGMRES 或完整场。**

| 审核问题 | 实测答案 | 资格边界 |
|---|---|---|
| 候选做了什么 | 每个单元仍按真实 mesh coordinates 求几何因子；共享与单元位置无关的参考基函数表，再用分块矩阵乘法生成完整局部张量 | 减少重复逐项运算，保留 `mesh_actual_exact` 的坐标身份；不是新物理模型，也不恢复 canonical 共享 |
| 局部张量及 R/T/S | 八个代表键全部通过 `1e-11` 局部门；最大 raw/oriented 相对 Frobenius 差分别为 `1.925763134488738e-15` / `1.925763134488735e-15`；R/T/S 最大差为 `8.726871992808957e-13` / `6.821847465821295e-14` / `1.047234456910219e-14` | 局部资格通过不等于两列全域作用通过 |
| 构建成本 | 28,000 键 evaluator 计时合计 `19,641.249084575567 s`，均值 `0.7014731815919845 s/key`，单键最大 `5.322032446041703 s`；完整 owner `24,777.34818448685 s`，worker `28,381.330578941852 s`，service 父段 `28,555.90928376885 s` | 各值属于不同计时边界；worker/owner 是 service 流程内阶段，不相加成总成本 |
| 两列完整作用 | 按冻结 D0/D1 分母，top=`1.7183209126709868e-10`，bottom=`3.6180522433957604e-10` | 两列都高于 `1e-11`，明确 FAIL；完整差向量绝对 L2 为 `3.824090978625035e-7` / `8.051905483782545e-7` |
| 候选恢复 | forward=`1.981377497384616e-11` / `1.979023053583157e-11`；native volume residual=`1.4373046679706224e-15` / `1.436540888080939e-15` | forward 门 `1e-11` 未过，native residual 门 `1e-10` 通过；本候选恢复只测到初次状态，实际额外修正数为 0，不能说三次精化已耗尽 |
| 资源 | 构建阶段进程树 RSS 峰 `367,708,164,096 B`、task cgroup 峰 `366,622,593,024 B`、task swap `0 B`；宿主全局计数增加 31 个 swap-in 页和 58 个 swap-out 页 | RSS、cgroup 与宿主全局计数分开列示；宿主页计数不能归到本任务，也不能称整机零 swap |
| 后续数值能力 | `global_volume_matrix_materialized=false`；未运行 200q、准确因子、KSP/FGMRES、完整场、独立 A6、R/T/A 或 `A_volume` | 这些项目均为 `NOT_RUN`，不构成完整 0.7 nm 模型资格 |

## 模型与方法

对象仍是 Task41 B0：50×50 nm 周期单胞、居中 17×20×120 nm 的 Si 主体与 10 nm 显式 Si 基底，方位 90°、掠角 1°、S 偏振，p6、10×200×14 网格；共 28,000 个六面体单元、64,120 个端口模式（包括传播模与倏逝模）和 200 个 q 分支。此任务的 57 个空端口 q 仍需要有限元参考，不因没有端口而删除。

V6 只替换局部张量的生成方式。通俗地说，旧路径对每个单元反复做较慢的逐项计算；候选把共同的参考基函数数据只准备一次，每个单元仍根据自己的实际坐标计算几何，再把主要乘加组织成有界矩阵块。这能提高构建速度，但会改变浮点求和次序，也不能保证全域作用误差变小；所以局部张量必须先和原 FFCx 结果比较，最终仍由原来的完整两列门裁决。

候选生产身份为 source `210fbbf271faa14c62ac30153b80332d0e645982`，生产合同 SHA-256 `9fe53c21e155e8ce1a74aaf0451658262f57e128a67d38922ba5948d91433172`。它复用了 donor source `afbe91e5947ed18fb74d7105097e129c1b8b4cc7` 的 141 个原数组，没有复制 donor 数组；其 V3 recovery PASS 是 donor 的历史结果，不能移到 V6 候选上。V6 保存审核 consumer/source `89e1e42114870ba1db752dfaf6d893ad13f923d6`，consumer 合同 SHA-256 `0201a5d2f4918c6f1d7d9385ef97cd9c50173287d1ae4be52d336462281cee11`。

本轮固定窗口未重置：T0=`2026-10-20T10:21:59.261754681Z`，数值 cutoff=`2026-10-21T10:01:59.261754681Z`，总 deadline=`2026-10-21T10:21:59.261754681Z`，窗口 SHA-256=`ea6b38c3bc791ace068c75188a562023cae197f7016f110b0b86970891c46c8d`。没有刷新窗口或改动 16 GiB 证据上限、资源上限、数值阈值或 ordinary solver default。

## 局部筛查与构建成本

局部筛查覆盖 8 个冻结代表键，几何坐标按原始字节身份比较；raw/oriented 张量、K/G/J/L、R/T/S 均通过 `1e-11`。上述表给出各类 8 键最大相对差。局部消元缺陷仅作诊断，不新增门，也不替代全域 action 门。

完整 evaluator 对 28,000 个 actual key 的计时汇总为 `19,641.249084575567 s`（平均 `0.7014731815919845 s/key`，最大单键 `5.322032446041703 s`）。逐阶段合计记录为 geometry `134.55400196043774 s`、Gram `16,807.707907172386 s`、pack `955.8795079700649 s`、scatter `1,206.9749432522804 s`、release `5.699226659256965 s`；这些是候选 evaluator 的 stage accounting。候选完整 owner 为 `24,777.34818448685 s`，worker 为 `28,381.330578941852 s`，受监督 service 父段为 `28,555.90928376885 s`；这些父/子或不同边界不重复相加。必要 preparation 计时为 `17.59478507982567 s`，按原报告保留其自身计时字段，不把它再叠加到上述父段。

构建候选记录 174 个持久化数组，声明载荷合计 `4,514,199,336 B`。已有 donor 的 141 个数组共 `9,379,882,344 B`，以只读方式复用。owner audit 早期阶段记录的 raw-evidence counter 为新增 `49,825,832 B`、累计 `9,429,708,176 B`；这是该阶段的证据计数，不是整个固定窗口或完整科学产物总账。它与最终 174 个数组的 payload 是不同字段/口径，不能互相替代或相加推断。数组级文件名、尺寸、dtype、shape 和 SHA-256 已放入 [V6 原始哈希索引](outcomes/b0_v6_actual_qmetric_hash_index_20261021.json)。

构建阶段同时进程树 RSS 峰值 `367,708,164,096 B`，专用 task cgroup 峰值 `366,622,593,024 B`，任务 tree/cgroup swap 均为 0。Linux 宿主全局 swap 计数在此服务窗口内增加 `31` 页 swap-in、`58` 页 swap-out，不能归因到任务。原始 watchdog 字段沿用 `host_global_*` 命名；这不是 WSL 全局 swap 结论。RSS、cgroup 与宿主累计计数为不同口径；不得把 RSS 和 cgroup 相加，也不得写成宿主零 swap。PSS 未采样。

## 完整作用、恢复与归因

最终 checker 重开并重算 action、recovery、attribution 所需数组，使用的冻结分母为 top `2225.481253487629`、bottom `2225.4807123031883`，误差门限仍为 `1e-11`：

| 列 | 完整差向量 absolute L2 | 冻结分母 | 相对误差 | 门限 | 结果 |
|---|---:|---:|---:|---:|---|
| top / column 0 | `3.824090978625035e-7` | `2225.481253487629` | `1.7183209126709868e-10` | `1e-11` | FAIL |
| bottom / column 1 | `8.051905483782545e-7` | `2225.4807123031883` | `3.6180522433957604e-10` | `1e-11` | FAIL |

动态分母的重算相对误差分别为 `1.718320912676268e-10` 和 `3.6180522433931414e-10`，同样失败；最大误差项位于 row `4,766,937`。端口输出是经身份核验后原样继承，没有在本候选中改写。

候选恢复同样需要单独报告：forward 相对差两列都略高于 `1e-11`；native volume residual 两列约 `1.44e-15`，满足 `1e-10`。生产路径在这份候选记录中只做初次恢复、未执行额外 same-LU 修正，所以应写作“0 次额外修正，初次状态失败”，不能写“最多三次修正已耗尽”。

旧 V3 donor 的保存恢复通过了三次同 LU 修正，但该 PASS 只属于 donor source `afbe91e...`。它和 V6 candidate 的恢复失败是两份不同数据身份。旧 V3 完整 action 误差 `3.042118678294192e-10` / `6.391893878204816e-10` 也作为历史结果保留，不能替代 V6 的最终 candidate checker 数值。

候选归因闭合差约 `198.18` / `198.16`，相对冻结分母约 `0.0890506791` / `0.0890404748`；记录分类是 `DIAGNOSTIC_ONLY`。这说明这份代数分解还没有闭合到候选全域两列门，不能据此断言舍入误差或其他单一机制已被证实为根因。归因中的 `j0/j3` 是保存 donor 状态标记，不表示 V6 候选完成了额外恢复精化。

## 独立 checker 与失败尝试

最终 saved-only checker 运行于 attempt4：service `myfenics-case-task41-v6-saved-audit-89e1e421-20261020t214246z.service`。checker 返回 `COMPLETE`，`audit_completed=true`、`data_integrity=true`；受监督 service 对全部 174 条数组记录内容重算 SHA，checker 重开并重算 action/recovery/attribution 所需数组，分类与报告一致。但 `qualification_passed=false`、`joint_action_passed=false`、候选通过为 false、`official_result=false`。这是审核完整的数值负结果，不是 checker 崩溃。该服务只读取现有保存结果，不重建 FE/LU，不运行 PDE。

服务用时 `180.8804526119493 s`，required checker watchdog 子段 `131.0202877856791 s`，watchdog classification `COMPLETED`、leader exit `0`、无剩余 child PID，task cgroup swap `0 B`。进程树 RSS 峰为 `5,770,784,768 B`；receipt 报告的 dedicated-job cgroup memory peak 为 `829,353,984 B`。两种采样范围数值差异明显，故分别引用且不互换、不相加；PSS 未采样。该 checker watchdog 记录的 Linux 宿主全局 swap-in/out 增量均为 0 页，原始字段名沿用 `host_global_*`，不表示 WSL 全局或任务归因。

| attempt | 原始结果 | 处理与证据边界 |
|---|---|---|
| saved audit attempt1，source `2489d75bd12231306c6a79d4b61051efdc10b429` | checker `NameError`：冻结分母常量名拼写错误；worker exit 1，service `156.40364084905013 s`，watchdog `107.13874439802021 s` | 保留原始 service receipt、watchdog 和 worker log SHA；只读候选数组未改 |
| saved audit attempt2，source `6757a5b8a33f93982f0d60c8fd1b52bbadeaf624` | launcher 收到多余 positional DAT，拒绝“exactly its contracted DAT path”；未进入数值 worker/checker | 入口失败保留为负记录；独立服务费用/原始 receipt SHA 未在当前轻量索引中形成，计时记 UNKNOWN，不补造 |
| saved audit attempt3，同一 source `6757a5b8a33f93982f0d60c8fd1b52bbadeaf624` | checker 报 `V5 global attribution receipt is missing or malformed`；worker exit 2，service `165.87995505379513 s`，watchdog `116.92266370588914 s` | 实际 producer 把已验证 evaluator 身份放在父 `identity_audit`，而嵌套归因对象未复制这两个身份字段；最小 checker 修复后仍保留 attempt3 原件 |
| saved audit attempt4，source `89e1e42114870ba1db752dfaf6d893ad13f923d6` | required checker 完成、candidate numerical FAIL | 仅 saved-data checker readback；receipt、report、watchdog 和 worker log 均在 hash index 中 |

attempt1–3 是普通 checker/入口错误，attempt4 才是最终数值审核回执。worker summary 记录 attempt1、3、4 均已清空后代；run index 另列 tree RSS、dedicated cgroup memory、task swap 与 remaining child PID。attempt2 在 launcher 入口被拒绝，没有可核对的 service receipt 或服务成本，保留为 `UNKNOWN`。

V6 候选构建前的 attempt1–9 也保留在 compact、run index 与哈希索引。现有轻量 service inventory 找到 attempt2–7、9 的原始 receipt 和 volume-only watchdog summary；这些运行均未构建候选，candidate checker 未运行，不能当作数值失败。attempt1 与 attempt8 的 receipt 在该清单中为 `NOT_FOUND`，source、成本和路径均保持未知，不用后续 source 推填。

| 候选 attempt | source SHA | service / watchdog 秒 | 已保存结论 |
|---:|---|---:|---|
| 1 | `UNKNOWN` | `UNKNOWN` / `UNKNOWN` | receipt `NOT_FOUND`；候选状态未知 |
| 2 | `e9dd78510aaa1507bd58d197d894baf2c6b17e37` | `4.493292410` / `3.377668551` | worker failed，未构建候选；checker 未运行 |
| 3 | `ff5d8b49e84a3076dc470fde2754aac49d1cdf13` | `4.580216045` / `3.445320235` | worker failed，未构建候选；checker 未运行 |
| 4 | `0087d6a4741555dd9a70b582630f6f7d5aa0713f` | `101.601698398` / `100.438910202` | worker failed，未构建候选；checker 未运行 |
| 5 | `48da059d21f6241f5d81e73cebeb32325f27a871` | `121.046304643` / `119.942770440` | worker failed，未构建候选；checker 未运行 |
| 6 | `d4e7595adf34bb407e31ffa01354f1bb8418e36c` | `136.722420173` / `135.650949925` | worker failed，未构建候选；checker 未运行 |
| 7 | `e58835fe4c6bd8587cec1ad1555e3450a2d0b631` | `190.867544968` / `189.515662505` | worker failed，未构建候选；checker 未运行 |
| 8 | `UNKNOWN` | `UNKNOWN` / `UNKNOWN` | receipt `NOT_FOUND`；候选状态未知 |
| 9 | `10d542d176afa10a5a55a73fa4d26b2e845c9fad` | `146.231336050` / `145.031898460` | worker failed，未构建候选；checker 未运行 |

每次已找到的 attempt 1–9 receipt、watchdog 路径、字节数和 SHA-256 均在 [V6 hash index](outcomes/b0_v6_actual_qmetric_hash_index_20261021.json)；完整时间与内存/清场字段见 [run index](outcomes/run_index.json)。已知、互不重叠的 service-parent 成本为：科学候选 attempt2–7、9 加 attempt10 共 `29,261.4520964548 s`；saved-audit attempt1、3、4 共 `503.16404851479456 s`；合计 `29,764.616144969594 s`。候选 attempt1、8 与 saved-audit attempt2 的服务成本仍 `UNKNOWN`。嵌套 watchdog 秒数不再加到 service parent。主控冻结 checker 的两处读取修复后，相关定向测试为 `14 passed, 22 deselected in 1.12 s`；科学生产源与数值门未改。修复没有重跑候选构建或 FE/PDE。

## 未运行项与下一步

根据 V6 full-action FAIL，200q、准确因子、KSP/FGMRES、完整 0.7 nm 场、独立 A6、R/T/A、`A_volume`、最终网格/模式精度、整机 2 TB / 48 h 冷流程资格均未运行或未资格化。不能将局部速度收益或 checker 完成升级成 production default、full-field 或 official result。本轮不重建 7 小时 owner、不增加精化次数、不改窗口或 cap。V6 候选 attempt1–9 的回执/缺失状态与 known service parent 总账保存在 compact、hash index 和 run index；更早 V3/V4/V5 原记录保持原样。失败门与未运行项等待下一份主控/审阅指令。

## 证据入口

- [V6 紧凑结果](outcomes/b0_v6_actual_qmetric_full_action_failed_20261021.json)
- [V6 原始哈希索引（含174项数组清单）](outcomes/b0_v6_actual_qmetric_hash_index_20261021.json)
- [Task41 汇总](outcomes/summary.md)、[定向测试记录](outcomes/test_summary.md)、[run index](outcomes/run_index.json)
- 构建原始候选报告（工作站保存路径；SHA-256 见哈希索引）：`/home/fenics/Projects/laptop_share/results/task41extra_phi90_p50x50_g17x20/task41_b0_v6_actual_qmetric_210fbbf2_20261020T124053Z_attempt10/task41_p0_v6_actual_qmetric_candidate.json`
- 最终 saved-only audit：`/home/fenics/Projects/laptop_share/results/task41extra_phi90_p50x50_g17x20/task41_b0_v6_saved_candidate_audit_89e1e421_20261020T214246Z_attempt4/task41_p0_b0_saved_evidence_audit.json`
- V6 权威附件：`archive/review_report_v6_chat_attachment_20261020.md`，SHA-256 `b0b680648d0581593cf72fa5a8d75527eabaf2b9caf02105867c00f03c4ac8b9`。
