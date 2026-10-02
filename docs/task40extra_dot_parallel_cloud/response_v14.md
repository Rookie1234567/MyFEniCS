# Response V14：XZ fresh worker 与 saved checker 成功证据

**XZ attempt3 actual worker 与独立 saved-only checker 均 PASS**，同一 clean 源 `ae6034fa13b4af62263409822fec1c6c4ba4a150`。研究点 p4、phi5、mesh **6×4×7**，实际 global/local **168/84/84 cells**，完整 **18144 interiors、33024 independent rows**，固定 manual **532 modes**；8组源输出均532、有限且可表示。这个结论对应既定相同光学几何的网格校准点。[worker summary](outcomes/records/direct_XZ_v14/compact_record.json) · [checker summary](outcomes/records/direct_XZ_v14/compact_record.json)

本次在已通过X点的同一小型三维结构上进一步加密z方向网格，检查按周期方向分块求逆、精确消去与恢复单元内部未知量的流程能否继续工作。每次误差检查仍回到完整原三维方程；四个分块因子同时保留，其装配与保存证据带来额外成本。原始artifact链接在本页指向记录其路径与哈希的compact，完整数组不进入Git。

| 证据 | 监督耗时 | 同时进程树 RSS 峰值 | 终态 |
|---|---:|---:|---|
| fresh PDE worker | 2392.338773393 s | 1,669,115,904 B | COMPLETED / exit0 |
| saved-only independent checker | 754.005582511 s | 1,594,347,520 B | COMPLETED / exit0 |

两者 swap0、identity coverage complete、子进程清除。worker与checker分别按显式 **3GiB/4500s** 研究 cap 监督；checker不重新运行FE/JIT/factor/PDE。

checker `gate_pass=true`，**358 direct +33519 raw +49 operator +56169 shared =90095 passing entries**，完整原始 inverse/FGMRES/residual/recovery/all532 output qualification。成功 schema 自然没有 `evidence_valid` 字段，本包不增加该字段；entry counts也不当作全局unique-label count。worker report SHA `dfd38293d2a56afb57afed2c2bbc6d7fbf11756da3fb8d4e59ca1169f99165a7`，checker SHA `44cab5a51dd4a1063bfe509bef114cfbf3ffc10b720b3c6bca83dde5f3ddfd05`；actual checker的report hash与独立launch receipt绑定一致，source bridge是same-head exact identity。[launch receipt](outcomes/records/direct_XZ_v14/compact_record.json)

四个q因子行数 **3796/3872/3872/3872**，保存CSR payload总计 **73,801,544 B**；factor setup **6.217330755 s** 包含controls与evidence I/O，不能称为纯LU或per-PC时间，也不能由CSR推出factor fill或whole RSS。按 root 已提取、绑定 report 的scalar摘要：notch迭代 generic/interior/physical/notch_supported **4/4/4/5**，最大true原始残差约 **7.60336e-11**，最大notch残差约 **4.58254e-12**，physical nonzero-q约 **8.95626e-5**。physical sampled PC defect约 **0.0134233**，`PC_defect_is_norm_bound=false`；这是weak two-cell notch样本。[compact record](outcomes/records/direct_XZ_v14/compact_record.json)

自动checker曾在fresh memory-admission阶段失败：`fresh dynamic/host envelope cannot support requested cap plus128MiB reserve`，**SUPERVISION_FAILED**、supervisor receipt null。原失败保留；精确failed host envelope未保存，不能补造其cap/shortfall/RSS/time。之后独立checker fresh launch cap **3,800,719,360 B**，足以支持requested cap+reserve **3,355,443,200 B**，获得独立完整监督与PASS；没有重跑PDE。[原 admission failure](outcomes/records/direct_XZ_v14/compact_record.json)

原 [XZ attempt1 failure](outcomes/records/direct_XZ_v14/compact_record.json)、[attempt2 failure](outcomes/records/direct_XZ_v14/compact_record.json) 与 [attempt2 saved-proof补充](outcomes/records/direct_XZ_v14/compact_record.json) 全部保持历史分类/字节，哈希复核不变。旧pending snapshot保持原文，由此V14记录实际后续结果。

X/XZ支持同光学尺寸、fixed manual532的离散mesh校准。它没有证明目标几何精度、electrical/optical size扩大、AUTO32060、原目标尺寸收敛、强缺陷普遍性能或用户2TB/48h目标容量；ordinary defaults也没有改变。本包使用小JSON、source/ABI/hash linkage与selected checker scalar metadata；不解码数组、不扫描events/resources、不数值重跑。**最新pair独立metadata linkage review与publication由root后续安排**；精确绑定见 [manifest](outcomes/records/direct_XZ_v14/manifest.json)。
