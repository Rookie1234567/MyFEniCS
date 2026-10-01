# Response V2：真实三维p4数据已可用，完整目标未解决

本批在本独占云端分支完成真实G0 p4装配/导出：336 cells，29,072 rows、10,912,592 NNZ、80真实DtN端口；原CSR采用complex128/int32，载荷218,368,132 B。完整RHS、局部恢复与MPC/端口映射均保存并独立核验。全过程同时树RSS峰1,199,104,000 B、136.742秒、零swap；未建立全局因子、未解完整场、无official R/T/A。

保留两次真实dependency collection失败、一次历史mode-hash Gate失败以及危险private-FFI fixture的NOT_RUN_ABI_INCOMPATIBLE分类。新模式manifest冻结自己的hash，并与已有独立M0审计逐key/向量比较，实际差为0；没有冒称等于无法取得raw的历史PDE hash。通过的新云端资格是独立stack上的实际小型测试，不是历史ABI通过。

最新最终目标是完整三维、原尺寸50×25×140 nm、无缺口规则基线、0.7 nm、约2 TB/≤48小时；未来三维缺口能力仍必须保留，不交付二维/2.5D替代。72小时研究窗口截至2026-10-04 10:07:14 UTC。本小G0只有真实全局算子数据价值，目标能力仍unknown。

下一步先准备公共backend的complex128 reference-factor和完整恢复后原A4≤1e-10残差控制；它通过后才考虑64精度。factor尚未启动，不重复已有BLR扫描，不修改ordinary default、其他分支或用户电脑。

详见[本批结果和边界](outcomes/real_p4_probe_preparation_v2.md)、[compact证据](outcomes/records/real_p4_probe_preparation_v2.json)与[范围补充](phase2_real_p4_probe.md)。只有本分支的local agent-authored commits，远端push由协调方审计后执行；没有PR/merge。全库/CI及GitHub视觉渲染没有完成。
