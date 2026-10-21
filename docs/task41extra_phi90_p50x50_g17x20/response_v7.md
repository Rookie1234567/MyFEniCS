# Task41extra Review V7 执行回应：Bα归因修正与保存证据复核

日期：2026-10-21（Asia/Singapore）
分支：task41extra_phi90_p50x50_g17x20
consumer source：184822fa7ec5cd2af33a6ff39b5c6e7e5641cab6
consumer contract SHA-256：c4240948e717f763675327e28ccc0edc94e43cdfc81a781c7a2bc25231615474
结论：保存数据审核完成；归因公式遗漏已由实际复数向量确认；完整作用和候选初始恢复仍未通过原数值门，official_result=false。

## 执行范围和身份

本轮遵循Review V7的saved-only范围，读取既有V6候选与历史donor保存数据；未重建28,000键候选、未扫描carrier、未重跑有限元或factor，也未运行200q、KSP/FGMRES、完整场、A6或R/T/A。旧报告和数组保持原样，V7另存结果。

V6候选producer source为210fbbf271faa14c62ac30153b80332d0e645982，producer合同SHA-256为9fe53c21e155e8ce1a74aaf0451658262f57e128a67d38922ba5948d91433172。历史donor source为afbe91e5947ed18fb74d7105097e129c1b8b4cc7；输入SHA-256为a0c45d0475bd2b41d2d19589831086468a62f39fdca5b74734b62751df1485c1；固定窗口SHA-256为ea6b38c3bc791ace068c75188a562023cae197f7016f110b0b86970891c46c8d。

保存审核报告路径为results/task41extra_phi90_p50x50_g17x20/task41_b0_v7_saved_attribution_184822fa_20261021T023918Z_attempt1/task41_p0_b0_saved_evidence_audit.json，68,891 B，SHA-256 8ffa70f89eccbf05ec8f4dfded584686de8db8e5c125c35f5e72d697759c1426。status=COMPLETE，audit_completed、data_integrity和raw_evidence_retained为true；这代表审核及文件完整性检查完成，不代表科学门通过。

## Bα遗漏：旧198量级闭合来自漏减端口项

旧完整式以native full RHS减native volume action，却没有减Bα。审核将保存的原Bα向量按active映射只映射一次，并比较整个复数向量。旧闭合L2为列0的198.1806169837082、列1的198.15785920015628。旧闭合减去实际active Bα后，与修正完整闭合的向量差约1.13e-14 L2。因此旧198量级主要来自该公式遗漏。

这项诊断没有把Bα从原p6与reduced-RHS差向量中扣除，也没有改变原action向量。修正闭合仍为对应d向量的5.66%至10.76%，不足以可靠识别d的主导来源，也不能宣称科学作用通过。

## 四组修正闭合

下表同时列出完整式和体积式。冻结分母D沿用原定义；相对d表示闭合范数与对应d范数之比，只展示剩余闭合规模，不是新的通过门。

| 列 / donor状态 | 完整式 L2 | 完整式 / D | 完整式 / d | 体积式 L2 | 体积式 / D | 体积式 / d |
|---|---:|---:|---:|---:|---:|---:|
| 列0 / j0 | 4.1145860220002625e-08 | 1.848852249621133e-11 | 10.7596447% | 4.114586021593275e-08 | 1.848852249438257e-11 | 10.7596440% |
| 列0 / j3 | 2.168621678652181e-08 | 9.744506610665259e-12 | 5.6709469% | 2.1686216782089815e-08 | 9.744506608673782e-12 | 5.6709465% |
| 列1 / j0 | 8.640671724938034e-08 | 3.8826091267246497e-11 | 10.7312136% | 8.640671725461464e-08 | 3.882609126959849e-11 | 10.7312145% |
| 列1 / j3 | 4.559526019572616e-08 | 2.0487825368991332e-11 | 5.6626671% | 4.559526019906995e-08 | 2.0487825370493834e-11 | 5.6626676% |

epsilon_rhs=f-b-Bα的L2为列0 1.9838432520779475e-10、列1 4.5807759675738086e-11，没有强行设成零。volume/full的d加RHS拆分差分别为3.443052727611797e-14和3.687097276593462e-14。保存reduce_r_volume与raw trace加T_r_i的四组L2差为1.61e-22、4.65e-24、3.40e-22、9.79e-24，交叉检查一致；但同列j0和j3得到的d_hat仍相差3.992795315768375e-08、8.380520829133848e-08，剩余差异未归因。

## 原科学门与状态身份

| 检查项 | 列0 | 列1 | 限值和结论 |
|---|---:|---:|---|
| 保存full-action绝对L2 | 3.824090978625035e-07 | 8.051905483782545e-07 | 绝对范数仅供量级参考；见下一行相对门 |
| 保存full-action / 冻结D | 1.7183209126709868e-10 | 3.6180522433957604e-10 | 均超过1e-11 |
| V6候选初始恢复forward相对误差 | 1.981377497384616e-11 | 1.979023053583157e-11 | 均超过1e-11；额外同LU修正0次 |
| V6候选native volume residual相对误差 | 1.4373046679706224e-15 | 1.436540888080939e-15 | 小于原1e-10 residual门 |

最大full-action误差行为active trace index 4,766,937。候选forward恢复未通过，native residual很小不能替代forward门。历史donor经三次同LU修正的恢复通过证据属于不同状态，不能转给V6初始候选。审核报告顶层recovery字段属于历史donor；V6候选子项仍为ACTUAL_COORDINATES_INSUFFICIENT。

## P3局部证据与全域缺口

V7只复核现有V6报告里的八个same-input代表键，没有新增数值重算。报告记录raw/oriented tensors、K/G/J/L及R/T/S同输入比较通过；最大相对差约为raw/oriented 1.925763e-15、R 8.726871992808957e-13、T 6.821847465821295e-14、S 1.047234456910219e-14。这些局部键不能代表最大误差行的incident cells。

现有证据没有将active trace index 4,766,937映射到所有incident cell及actual geometry key/permutation，也没有对应逐cell局部块和扩展映射。Q_s只有全域聚合，不能唯一拆回Tδ_i、E_S t_c和−E_Tu_i。本轮不从旧两格见证外推新主导行，不重扫carrier或重建全域映射。继续精确归因至少需要：

1. row 4,766,937到所有incident cell ID及actual geometry key/permutation的hash-bound映射。
2. 每个incident cell原始interior/trace row map、active_ids和MPC/trace扩展CSR。
3. 身份一致的candidate/reference K/G/J/L与R/T/S局部块，或原始局部张量和精确保存位置。
4. 每列、donor j0/j3各自的局部interior state/residual，以及trace E^H扩展/组装数据，以分别形成Tδ_i、E_S t_c和−E_Tu_i。

一次只读探索误以连续切片拆分882张量，与原R/T/S布局不符，已标记INVALID_LAYOUT_ATTEMPT，结果不用于科学归因；未保存该探索的独立raw，耗时UNKNOWN。

旧两格cell 26762/26897的字段S_minus_L_plus_JR值为0，但符号合同不清。若含义是S−(L+JR)，它不等于V7所需E_S=S−L−TG（R/T有限精度误差下两者不同）。不能用这个0宣称E_S=0或已完成E_S分解。最大误差行已从旧局部证据的5,458,716变为4,766,937，旧行不能代替目标行。

## 原始数组、资源和窗口账目

V7保存四组full/volume闭合差，共8个complex128数组；每个文件91,008,128 B，payload合计728,064,000 B，含头部的数组文件实际字节合计728,065,024 B；整个输出根目录实际占728,133,915 B。数组SHA-256列于outcomes/b0_v7_saved_attribution_20261021.json。本轮累计证据14,622,146,704 B，16 GiB配额余2,557,722,480 B，磁盘高于2 GiB保留底线。

服务回执位于attempt1.service/task41_p0_service_receipt.json，208,118 B，SHA-256 d384f8935501601ec48d7522e76d0cdef0e62b9051599bea11225336d9b8ecfb。V7 service task41-v7-saved-audit-184822fa-20261021T023918z正常完成，父计时250.1106050624512 s。required-checker watchdog为COMPLETED、退出码0、后代清理完成且无剩余PID；子计时200.4840597989969 s，workflow时钟200.48515146919567 s / 1140 s预算，通过。父计时包含子计时，不重复相加。

进程树同时RSS峰值9,049,808,896 B；专用job cgroup memory峰值1,801,805,824 B、结束current 830,488,576 B、cap 1,649,267,441,664 B。进程树和cgroup swap峰值均0；宿主全局pswpin/pswpout变化均0页；PSS按profile未采样，保持null。RSS与cgroup范围不同，分别记录，不相加。

固定窗口T0为2026-10-20T10:21:59.261754681Z，数值截止2026-10-21T10:01:59.261754681Z，总截止2026-10-21T10:21:59.261754681Z。账本sequence 25976（2026-10-21T02:43:30.736292140Z）累计计费58,891.482073122505 s，数值余额26,308.5179268775 s，总余额27,508.5179268775 s。service入账累计58,641.570849532 s，父时长已包含于账本，watchdog子时不重复计费。

## 测试、结论和后续边界

执行者首轮定向测试记录10 passed、48 deselected、0.94 s。主控在同一冻结源码、资格化WSL activation下仅重验这10项，结果10 passed、48 deselected、1.13 s；不是工作站PDE或CI。原始命令、实际执行目录和日志路径见compact tests，日志SHA-256为3b36563d720a44cfdf0571940f63900a595adc5d5a7fb795cf52b5e799a88b6b。该轻量复验为工程成本，不重复加到saved-service父时；其他准备/编辑总成本UNKNOWN。文档收口另做compact JSON解析、保存文件字节与SHA核对、链接检查和git diff --check；没有重跑昂贵科学数据、全仓pytest、Ruff或PDE。

本轮确认归因式漏减Bα并量化修正后的剩余闭合，但没有定位全域d差异根因。原full-action两列和V6候选初始恢复仍失败，official_result=false、qualification_passed=false。下一步先由主控冻结如何取得上述最小incident-row映射及局部证据，再决定是否需要新的受监督数值工作；不把归因闭合当作action通过，也不自动启动200q、factor、KSP/FGMRES或完整场。
