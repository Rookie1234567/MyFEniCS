# Task41 P0 Review V13 收口：两cell误差账与目标行复核

## 结论

保存包上的8组逐操作误差账和4条目标行复核已由 attempt10 独立只读 checker 复核完成。旧全域 full-action 门仍失败：两列相对误差分别为 2.6749770637124364e-10、5.613598120039757e-10，高于冻结门限 1e-11。该诊断不是新 PDE 运行，也不产生 official result 或 scientific qualification。

本轮没有验证任何生产修复，但支持一个有界的下一步研究提案：检查 hcurl_assembly_time_condensation.py::project_internal_rhs_same_lu 的同 LU RHS 残差校正路径。保存的有符号归因显示，以 A_rb=Σ_c(−λ_cᴴr_b,c) 表示 RHS 残差投影时，norm(d−A_rb)/norm(d) 为 5.13% / 1.70%；末端 J/scatter 差相对 d 为 1.58% / 2.43%。这是局部解释的剩余比例，不是通过门限。它们支持优先研究残差校正，而不是宣称 GETRS 有缺陷或已找到全域修复。八组 e_b/e_delta 误差账、有限的两cell覆盖和原 full-action FAIL 均保留。该提案本轮未实施，也不授权新计算。

## 八组误差账

eta_hat 列按完整 saved_eta_hat 复向量计算 max_k abs(eta_hat[k])；最大单项和 unexplained 项按主报告保存的 max_abs 字段另列。余差范围为 4.106e-13 至 1.476e-12；dominant term 不是 eta_hat。

| cell | column | state | 最大项 | max_abs_eta_hat | largest_term_max_abs_reported | unexplained_max_abs |
|---:|---:|---|---|---:|---:|---:|
| 360 | 0 | j0 | e_delta | 6.5211548012e-10 | 7.6227117153e-10 | 4.1059735569e-13 |
| 360 | 0 | j3 | e_delta | 8.3460869735e-10 | 7.1626533315e-10 | 4.4208605631e-13 |
| 446 | 0 | j0 | e_delta | 1.1403516361e-9 | 8.8090391646e-10 | 6.7070263105e-13 |
| 446 | 0 | j3 | e_b | 1.1274675611e-9 | 8.4836984260e-10 | 6.9876346811e-13 |
| 360 | 1 | j0 | e_b | 1.6697222607e-9 | 1.5039947934e-9 | 1.2714910629e-12 |
| 360 | 1 | j3 | e_delta | 2.1496778069e-9 | 1.8686813837e-9 | 1.1296523850e-12 |
| 446 | 1 | j0 | e_b | 3.2808555014e-9 | 2.4624020693e-9 | 1.4762784351e-12 |
| 446 | 1 | j3 | e_b | 2.2796634991e-9 | 2.4624020693e-9 | 1.3927922802e-12 |

## 四条目标行的有符号复数结果

复数对按 [实部, 虚部] 排列。g_eval 由保存的 b_t 加两格项重建；d 差是独立行复核值减原保存 d。它们保留符号，不以范数替代。

| column/state | g_eval | d_eval | d_eval − saved d |
|---|---|---|---|
| 0 / j0 | 4.7766661737e-9 − 5.6388671510e-11i | −4.7815188078e-9 + 5.3645044374e-11i | −6.6698273799e-11 + 3.9093129145e-11i |
| 0 / j3 | 4.7766661737e-9 − 5.6388671510e-11i | −4.7782488065e-9 + 5.8684219519e-11i | −6.3428272499e-11 + 4.4132304291e-11i |
| 1 / j0 | 0.7819962682 + 0.03249313718i | 3.5596505272e-9 − 9.7498483371e-9i | −5.8958440851e-11 − 2.3243663118e-10i |
| 1 / j3 | 0.7819962682 + 0.03249313718i | 3.5494215475e-9 − 9.7582951795e-9i | −6.9187420567e-11 − 2.4088347349e-10i |

辅助的 cell 投影差显示 cell 446 在两列分别为 [−4.6049146718e-9, −1.2317880049e-10] 与 [3.7505198947e-9, −9.2098293436e-9]；cell 360 分别为 [−9.3223206932e-12, 3.2516567217e-10] 与 [−7.8928508174e-10, 3.5055336411e-10]。这些是投影后的诊断分量，不等同于某个已确认的生产错误。C_S t 的全432向量宽算术差在六组中为0；cell360/column1的j0、j3两组 max_abs 为 8.348057249230113334e-15（index 211，值 −8.338815749020511703e-15 − 3.92698026874249706e-16i），虽然选中目标行投影为0。目标行投影为0不代表全向量差为0；这也不能单独证明完整散射作用通过。

## 唯一有界研究提案

令 A_rb=Σ_c(−λ_cᴴr_b,c)，保存归因中的剩余范数比定义为 norm(d−A_rb)/norm(d)，两列分别为 5.13% / 1.70%。这表示该分解后仍剩余的比例，不是 RHS 残差项本身的贡献百分比。保存的有符号组合 Σ−λᴴr_b 为：

| column | real | imaginary |
|---:|---:|---:|
| 0 | −4.9564304983e-9 | +4.3504314536e-12 |
| 1 | +3.4478912707e-9 | −9.5434045200e-9 |

末端 J/scatter 诊断比例为 1.58% / 2.43%；第二列的 2.43% 大于 1.70% 的剩余范数比，因此不能笼统说末端项在两列都较小。公式、分母和保存复数值见 compact 及原报告。

唯一下一研究靶点是 hcurl_assembly_time_condensation.py::project_internal_rhs_same_lu 的同 LU RHS 残差校正路径。保存的有符号归因支持优先研究这一窄路径；它不证明 GETRS 实现有缺陷，也不构成全域修复或通过。提案未实施，未改生产数值核心；任何实现和数值复验需另行冻结范围。

## 序列化缺陷与数值结论分开

旧主报告的 cell-order g-term 字段在四条 global row 中用了 tuple/array repr，checker 将其单独标为 SERIALIZATION_DEFECT_CELL_VALUE_TUPLE_ARRAY_REPR。attempt07 原报告字节保持不变；绑定的原始组数据允许独立恢复 cell 360/446 的有符号值。attempt10 的检查器完成了该字段的独立记账，未把序列化问题改写成科学 PASS，也未将其作为 full-action FAIL 的根因。

## 计算、资源与固定窗口

| 项目 | 记录 | 口径 |
|---|---:|---|
| attempt07 primary analysis | 23.331 s；两次 GETRS 合计 0.0196566465 s | 23.331 s 是整段 primary analysis；GETRS 是其中子段，不是总耗时 |
| attempt07 service | 37.221870233 s parent；nested watchdog 27.335549845 s | service receipt 为 failed_raw_evidence_retained；其 watchdog worker completed/exit 0；两个状态分别保留 |
| attempt07 memory | tree RSS peak 674,791,424 B；cgroup peak 505,257,984 B | PSS 未采样；task swap 0 |
| attempt08 service | 34.980933937 s parent；nested watchdog 14.539023727 s，worker exit 2 | failed_raw_evidence_retained；tree RSS peak 705,208,320 B；cgroup peak UNKNOWN_NOT_RECORDED |
| attempt09 service | 31.620030194 s parent；nested watchdog 10.730579071 s，worker exit 2 | failed_raw_evidence_retained；tree RSS peak 714,338,304 B；cgroup peak UNKNOWN_NOT_RECORDED |
| attempt10 service / checker | 17.004897 s parent；nested watchdog 8.958905 s | completed read-only；GETRS=0，复用已保存的两个 lambda 包 |
| attempt10 memory / swap | tree RSS / cgroup peak 569,810,944 / 533,737,472 B；task swap 0，cgroup swap max=0 | PSS 未采样 |

attempt10 receipt 同时记录 numerical_work_started=false 与 diagnostic_numerical_work_started=true；独立 checker 的明确计数是 GETRS=0、复用已保存的两个 lambda 包，因此 attempt10 没有新增回代，只完成 independent read-only closeout。工程等待与行政文档收口用时没有单独可靠计时，记 UNKNOWN_NOT_MEASURED。固定窗口总截止为 2026-10-24T05:12:47Z；本次文档保存发生在窗口外，不把窗口余额当作当前余额，也不刷新 T0。

调用过程中的负记录保留在本 response：prepare 首次因 legacy/named-instance 参数冲突而在写入前拒绝；从 shell 直接调用 run-service 分别被固定环境与 cgroup gate 拦下，未产出 attempt10 checker 文件；误把 user-service wrapper 的 --help 当作只读帮助调用，启动了临时单元 myfenics-case-20261024T050608-1783485.service 并以 status 2 / INVALIDARGUMENT 退出，没有正式数值工作。随后按标准 wrapper 和冻结合同启动的 attempt10 才产生上表所列只读结果。

## 身份、验证与未运行项

本轮冻结源 HEAD 为 af953ef38ba2f95a2e443e131dece20c17af8c1e；合同 SHA-256 为 1cd4fb9f9b3c57069d78bb5bc3c260ccf7de3ab9ca37dab30ac53c0ae81f8a68；窗口 SHA-256 为 4fc153c4e0526a21eb01aa3d6e5c774af7c74a849a3461b676e7ffdf214debc6。定向 fixture 结果为 2 passed / 42 deselected / 1.78 s；测试运行时完整 source SHA 与原始日志哈希未单独保存，故不声称它们已绑定到该 HEAD。文档收口没有重跑 pytest、Ruff、PDE 或 CI；只执行文档与证据完整性检查。

全域 action 复验、生产补丁、candidate recovery、200q、factor、KSP/FGMRES、完整场、A6 与 official R/T/A 都是 NOT_RUN。证据入口见 [V13 compact](outcomes/b0_v13_saved_diagnostic_closeout_20261024.json)、[文件哈希索引](outcomes/v13_closeout/evidence_index.json) 和[两份既有台账索引](outcomes/v13_closeout/timing_and_adjoint_ledgers.json)。
