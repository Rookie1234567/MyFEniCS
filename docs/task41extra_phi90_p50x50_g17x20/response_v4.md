# Task41extra Review V4 执行回应：volume-only 归因接线完成，完整作用门仍未闭合

本回应处理 Review V4 的保存数据复核、volume-only 提取与受限几何归因。V3 的原始 carrier、两列 recovery 通过和 two-input full-action 数值失败均保留。V4 沿用已批准的 16 GiB 原始证据配额、固定窗口和资源/数值合同，没有修改 cap、门限或 T0；未重跑 carrier、端口遍历、q、factor 或 PDE。

V4 修复了保存 checker 的三处读取/状态问题：只读 mmap 的 LU pivots 在传入 SciPy 前复制为自有、可写的 `int32`；`raw_cell_diagnostic` 固定和 `initial_storage/action/residual` 对照，step 3 另行核验；joint action 为 FAIL 时仍读取原数组、重算并输出完整诊断，而不是提前抛异常。工作站 SciPy 1.18.1 的 2×2 子进程复现了只读 pivot 返回 `-11`，显式可写副本通过；该小复现解释 pivot 所有权边界，不冒充原大 checker 的原生崩溃栈。后续受监督 saved-audit 实际完成，报告保留“数据完整、recovery PASS、joint action FAIL”的分列状态。

## 当前判定

V4 的保存数据 checker 已完整结束，重新确认 141 个原始数组完整、recovery 见证通过，并如实重现完整 action 失败。两 cell 诊断显示，现有体积凝聚缓存使用平移后的 canonical cell coordinates；native 体积作用按 mesh actual coordinates 计算。对一个主导 active row，两条路径给出不同的剩余项，实际坐标结果更接近零，但仍非零。证据支持“几何坐标计算路径会影响这个选中行”的解释；它不能证明全域根因已闭合，也没有证明一个生产修复能通过原门。

| 检查 | 实测 | 判定 |
|---|---:|---|
| 保存数据审核 | `audit_completed=true`、`data_integrity=true`、`recovery_passed=true` | checker 这条保存数据路径完成 |
| 原 two-input full action，top / mode 16030 | `3.042118678294192e-10` | FAIL，原限值 `1e-11` |
| 原 two-input full action，bottom / mode 48090 | `6.391893878204816e-10` | FAIL，原限值 `1e-11` |
| saved-audit 重算结果 | `joint_action_passed=false`、`official_result=false` | V3 数值负结果保留；不能签发 official result |
| 原 full-action 误差分块 | top trace L2 `6.770178089430243e-7` / port `0`；bottom trace L2 `1.4225036541037616e-6` / port `0`；原分母 `2225.481253487629` / `2225.4807123031883` | 两列差异都落在 trace rows；port 比较精确为零。分块重算的 trace/原分母为 `3.0421186782950706e-10` / `6.391893878206601e-10`，与原 worker 门值保留各自末位精度 |
| V4 两 cell 几何诊断 | canonical 行值重现旧 d；actual 行值较小但非零 | 局部归因证据，不是全域资格 |
| 200q / factor / KSP / FGMRES / full field / A6 / R/T/A | 未运行 | 依赖的完整 action 门仍未关闭 |

本轮不是截止或资源门停止。运行和诊断本身完成，但完整作用数值门仍不合格，因此依赖该门的后续求解保持停止。

## 身份和证据

| 对象 | 身份 |
|---|---|
| 执行分支 / V4 consumer source | `task41extra_phi90_p50x50_g17x20` / `02523b3d5a49d30d71caa8e7f8a9b9405a78fa33` |
| V3 donor source / manifest | `afbe91e5947ed18fb74d7105097e129c1b8b4cc7` / `f55ac594382f40662954e19521ef9922d805abc64459cc7812877b12ec618465` |
| V3 donor contract / V4 volume consumer contract | `9e312f86cdd6b15fff9015faf4fb7dce19043fa3798a3f35cf2e57f79149713c` / `9012ffc0e80fac30f2aa1307d266366e7607ebcd11b9e0e2278bb213514e4bcd` |
| volume-only consumer source / selected-geometry consumer source | `d883c1f3381b4f3d6100022097d615846564673c` / `02523b3d5a49d30d71caa8e7f8a9b9405a78fa33` |
| V4 selected-geometry contract | `8e041fc0fae6da0bab5855043e9ebe5678facad6bb319d0e0bc3ac5c08c89453` |
| 固定窗口 | SHA-256 `68e6d8dfcccc9dee98bc161730957dc76f70a9e2dea2ee78455b66c9d8b37c38`；T0 和截止未重置 |
| V4 volume-only report | `results/task41extra_phi90_p50x50_g17x20/task41_b0_v4_volume_only_d883c1f_20261019T232138Z/task41_p0_v4_volume_only_attribution.json`；SHA-256 `09e96eb8c9d52b4cf0c29570fd8df3c1f820bc208104d91edd102978dfc9c4d5` |
| V4 geometry-pair attempt / service | `results/task41extra_phi90_p50x50_g17x20/task41_b0_v4_geometry_pair_02523b3d_attempt1` / `myfenics-case-20261020T004902-2286705.service` |
| Service invocation / terminal state | `03c854728dee48c49b66080f87545d5f` / inactive, `Result=success`, `ExecMainStatus=0` |

### 保存数据 checker

required checker 读取原有 141 个 NPY，没有重建 carrier，也没有重跑 64,120 个端口作用。报告为 `task41_p0_b0_saved_evidence_audit.json`，SHA-256 `427af9ffb5f41a129250a513eaa908c13efe79ac10d2bbf5468d1a69fa0113b8`。它重算出的数据完整性与 recovery 为通过，joint action 仍为失败，官方结果仍为 false。V4 更早一次 saved-audit 父段耗时 `70.426974745 s`，对应 report SHA `a2f540fb9778c038a2129a0f2119689fd832dc044e2a933ab2a45518ac37f94d`；两次审核报告分别保留，不能把后者写成原始 PDE 通过。

### volume-only 提取和几何对照

第一份 V4 volume-only report 状态为 `COMPLETED`，提取了三个 canonical local classes 及所需 cell 映射，落盘 `1,299,043,104 B`。它只处理体积局部块/映射，不扫描 surface modes、不构建全局 q factor。源报告 SHA 和依赖身份见上表。service 父时间为 `1,638.8259056420065 s`；worker 子阶段 `1,571.1404369487427 s`、worker watchdog `1,577.555109324865 s`、required checker watchdog `59.97374047804624 s` 均属于父服务内的计时，不能再加到父时间上。worker watchdog process-tree RSS 峰 `13,237,129,216 B`、该服务 task-cgroup memory 峰 `8,655,577,088 B`；checker watchdog process-tree RSS 峰 `3,948,949,504 B`。两个 watchdog 的 process-tree VmSwap 峰和 task-cgroup swap 峰均为 0 B，后代均清场。worker 期间工作站宿主全局 swapin 增加 5 页，但这是宿主范围读数，不能归因给本任务；PSS 未采样。资源账见 V4 compact。

后续 geometry-pair service 只对选出的 cells 26762、26897 比较 actual 与 canonical 坐标下的 K/G/J/L，再用相同 LU 消元重建 R/T/S 和一条原失败主导行。geometry report `task41_p0_v4_geometry_pair_probe.json` SHA-256 为 `a47eb7a8795b5af542c23ae45915588d89c962d1af1bb8360b8a9d42f1e7c031`；42 个数组共 `49,929,712 B`。worker 子阶段 `235.81072491174564 s`，worker watchdog `238.70088267000392 s`，service 父时间 `305.99965768121183 s`；required checker watchdog `66.03434501821175 s` 是该父服务的子项。geometry worker 与 checker 的 process-tree RSS 峰值分别为 `1,513,431,040 B` 与 `3,949,363,200 B`，共享该服务 task-cgroup 峰 `1,411,362,816 B` 的统计域，不可把 RSS 与 cgroup 值相加。两份 watchdog 的 task swap 峰均为 0 B、工作站宿主 global swap delta 为零，后代均清场。两份主要 service 父段 `1,638.8259056420065 s` 与 `305.99965768121183 s` 合计 `1,944.8255633232183 s`；再加此前 saved-audit service 父段 `70.426974745 s`，仅为目前有回执的三个父段之和。此合计不是完整 V4 工程或固定窗口成本；其他准备和未采时段保持 UNKNOWN，saved-only 诊断另计。

## 选中行结果与解释边界

production class key 为 `(cell_tag, widths, permutation)`。坐标生成会把每个轴对齐 cell 的 lower corner 平移到零点，并按既定容差规范化端点，因此平移但形状相同的 cells 可以复用矩阵。cells 26762 和 26897 共享 key `(1, 5.5, 0.25, 10.0, 0)` 及已保存 class `24b409051aa4cc54`。

canonical 路径下重建的 K/G/J/L 与保存 class逐项完全相等；fresh T/S 也和保存 T/S 完全相等。局部恒等式 `K R + G`、`T K + J` 和 `S - (L + J R)` 的相对 Frobenius 误差分别为约 `6.66e-16`、`4.35e-15` 和 `0`。因此保存的 canonical 凝聚结果和此处的相同 LU 消元相符。

对同一对 cells，实际 mesh coordinates 下对应 K/G/J/L 并非 bitwise 相等，彼此相对 Frobenius 差处于约 `9.37e-16` 至 `1.22e-15`：K `9.37018986530826e-16`、G `1.2158454571576914e-15`、J `1.1995469277913385e-15`、L `1.062722764991635e-15`。actual 与 canonical 消元得到的 T 相对差约 `8.45e-14`、`9.24e-14`，S 相对差约 `3.96e-14`。actual 与 canonical 路径在此选中行上给出不同结果；这些两格结果支持局部几何坐标计算路径可能相关，但没有证明唯一根因，也不足以描述全网格其他差异行。

同一 active row `5458716` 的两列行残差 `q = S t - (b_t + T b_i)` 如下。原 d 和 canonical 值近乎相同，而 actual 值更接近零：

| 输入列 | V4 saved-data replay 的旧路径 d | canonical 两 cell q | actual 两 cell q | actual q 范数 / 原完整列分母 | actual 与旧 d 的差范数 / 原分母 |
|---|---|---|---|---:|---:|
| top / mode 16030 | `[-3.4907687851415403e-9, -2.1869142052821644e-9]` | `[-3.4907687851415403e-9, -2.190552184089256e-9]` | `[5.25527954486904e-10, 2.978545188270232e-10]` | `6.040670040093789e-10` / `2225.4812534876287` (`2.714320792694724e-13`) | `4.7227867952154345e-9 / 2225.4812534876287` (`2.1221418009314578e-12`) |
| bottom / mode 48090 | `[4.776666173711419e-9, -7.07223080098629e-9]` | `[4.773028194904327e-9, -7.07223080098629e-9]` | `[-5.238689482212067e-10, 9.022187441587448e-10]` | `1.043282002730698e-9` / `2225.480712303188` (`4.687895055495618e-13`) | `9.575359947641924e-9 / 2225.480712303188` (`4.302602981327222e-12`) |

这是一个全局 active row 上两格贡献的 saved-only 诊断。actual q 不为零；而且即使该单行除以原完整列分母后低于 `1e-11`，也不能代替 5,752,120 个 joint rows 的完整向量范数。因此它没有关闭原 global gate，也不能用于直接修改 saved d。

已保存状态表也包含 recovery 的 j0 与 j3。用原分母，整个 full-defect 相对值 top 为 `3.0423570546e-10` / `3.0423658212e-10`，bottom 为 `6.3932192773e-10` / `6.3925529015e-10`。两格局部和没有覆盖这些完整缺陷；例如 top j0 的两格和为 `[-6.2216e-10, -3.9103e-10]`，相对 saved target 尚差 `[2.8926e-9, 1.6582e-9]`。针对两格实际块补入 `delta_t` 与 `sum(E^H T delta_i)` 后，局部保存态恒等式的 relative closure residual 为 top j0/j3 `8.29e-14 / 5.83e-14`、bottom `1.45e-13 / 1.33e-13`；extended accumulation 后分别约 `5.13e-14 / 5.13e-14`、`1.31e-13 / 1.31e-13`。这说明这两格代数分解可复算，并指出未检查 cells 仍有贡献；它不等同于全体 cells 上的恒等式闭合或原 full-action 门通过。完整 j0/j3 逐项值在两个 saved-only JSON 中保留，见 compact。

修正后的离线脚本 `task41_p0_v4_local_elimination_diagnostic.py` SHA-256 为 `a57b8f10251d5e921ab2bc41e0a584aca5e6f18c3c797e606690f3cd503e1110`；输出 `task41_p0_v4_local_elimination_diagnostic.json` SHA-256 为 `27eb82d1e51fd62b2b80e74fe5129f7be0512c35f95d092c967aeca6f90216ae`。它只读已有 arrays，准确地只加一次全局 `b_t`，用原 complex128 LU 公式，无 mesh/carrier rebuild、端口遍历、recovery refinement、阈值变化或 global q factor。它运行 `5.046073629986495 s`；该一次性离线运行没有 RSS 采样，峰值记为 UNKNOWN。

第一次错误诊断的 JSON 仍保留，SHA-256 为 `b9dd5bf9b5dd906fa3dcd7485e11190101067fe2f552caed92f9e96f5046a955`。它把已组装的全局 `b_t` 错误地对每个 cell 重复扣除，因此结果无效；修正版已将 `b_t` 只扣一次。错误文件不参与任何科学结论，不删除、不覆盖。

这三份 V4 saved-only diagnostics 分别为：`task41_p0_v4_saved_data_diagnostic_20261020T000104Z.json`（11.880770959891379 s，SHA `72eaf681115929258f0e1a3aaa76073b2d7e4be94679ee68d34cc4b34069a8ae`，脚本 SHA `453e8eb1cea6ba60f3f296fe2039082452d5dc3adc5940bc4f50f00713f87f69`）；`task41_p0_v4_native_local_decomposition_20261020T000440Z.json`（2.6438243738375604 s，SHA `69e7e640c66c7ba5e84fd82b65b3929cf571de08bfcdbd1d39ed4164e947ce45`，脚本 SHA `99c3d3a03505eac5a27276e645edfe65fd7cdbfe1914522e877e2fcdd60125e7`）；以及本节前述 5.046073629986495 s 的 geometry-pair saved-only elimination。前两份也没有 RSS 采样；其准备成本若未落入计时边界仍记 UNKNOWN。

## 几何缓存共享可行性与下一步

如果把 exact actual coordinates 加入 class key，这两个同一 canonical class 的平移 cells 就会被分开。现有报告仅存三个 canonical classes 和本次两格的 geometry records，没有保存全 28,000 cells 的 actual-coordinate key 清单；因此 actual-coordinate 下独立 key 数尚未测得，不能写成“28,000 个实际类别”或假设缓存不再共享。

作最坏上界估算，单一 class 的 T、R、S、LU 和 pivots 约占 `12,448,584 B` payload。若每个 cell 都需要独立缓存，则 28,000 份约为 `348,560,352,000 B`（约 `324.6 GiB`），约为三份 canonical class 缓存的 `9,333` 倍，并伴随 28,000 次局部 factorization/solve。这只是上界推算，非实际独立 key 数、实测内存或成本许可。现在不能依据两格结果选择“每 cell 缓存”作为安全生产修复。

下一最小步骤应先冻结一个使 production volume operator 与 independent native volume action 使用一致局部几何语义的候选接口，再在复用的 volume evidence 和两列原 RHS 上验证；必须保留独立积分/作用实现、class identity、原 denominator 和 `1e-11` 全向量门。现有证据还不能证明 canonicalization、exact-coordinate cache 或仅 checker 改动中的任一方案可通过全局门。若候选需要遍历更多 cells，只能按合同做 volume-only/RHS 资格，不重复 surface scan；不生成 full q、factor 或 PDE。

## 时间、测试与后续状态

本轮沿用 Review V4 原固定窗口和合同哈希，没有重置 T0 或变更 16 GiB 原始证据配额、内存门、swap 门或数学阈值。Task41 专用 fixed-window loader 与只读 `read_campaign_state` API 在 `2026-10-20T01:23:41.166876Z` 读得账本序号 `37870`、尾记录累计 `70,262.391444 s`、投影累计 `72,034.077685 s`，数值剩余 `13,165.92231481 s`、收口剩余 `1,200 s`、总剩余 `14,365.92231481 s`；window SHA 为 `68e6d8df…`。当时数值截止和总截止均未到；本轮依赖 full-action gate 未闭合而停止下游，不是窗口或资源门停止。两个 service 父段和先前 saved-audit 父段是有计量回执的片段，不代表完整 V4 工程或固定窗口累计成本；其他准备/未采时间仍为 UNKNOWN。保存数据离线诊断另计 `5.046073629986495 s`，RSS 未测。准确依赖、产物哈希和阶段成本在 [V4 compact](outcomes/b0_v4_volume_only_attribution_20261020.json) 与 [run index](outcomes/run_index.json)。

冻结 source `02523b3d5a49d30d71caa8e7f8a9b9405a78fa33` 的三份直接相关测试文件由主控以资格化本机 WSL activation 验证：`source scripts/activate_myfenics_wsl.sh` 后确认 marker、仓库 `.venv`、PETSc complex128/int32 和 Linux ABI，再运行 `python -m pytest -q src/test/test_task41_v4_volume_only_audit.py src/test/test_task41_v4_selected_volume_audit_cells.py src/test/test_task41_p0_saved_output_continuation.py`，`26 passed in 1.20 s`。这只是本机小 fixture，不代表工作站 ABI 或新数值资格。

本次文档收口后运行 `src/test/test_26_documentation_contract.py`、`src/test/test_183_development_model_registry_markdown.py`、`src/test/test_development_model_registry_contract.py`，`21 passed in 0.08 s`。compact JSON、两类误差比值重算、source/window身份、Markdown 表格列数及 `git diff --check` 也通过。完整 pytest、Ruff 和 PDE 未在本次文档收口中运行。历史 V3 action failure、V3 checker 的原始错误记录与首个错误 `b_t` 诊断均继续作为负证据保留。
