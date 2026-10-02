# V24续行记录：账户接口及执行审批已恢复

2026-10-02T14:07Z之后实际只读主机核验通过：新候选核CPU15、PSI full avg10=0、原系统/邻增长余量和磁盘Gate通过。周额度用尽时允许使用现有余额；明确禁止使用重置卡，未调用重置功能。以下认证阻塞是早先真实历史，保留原始失败；本批现继续原Review V21队列，原heavy-stop15:34:23.502588Z、deadline16:04:23.502588Z保持。当前真实数值仍未运行，后续来源与计数由正式run绑定。

# V24：固定八块局部求解与粗层配对的实现／停止证据

| 项目 | 实际状态 | 证据 |
|---|---|---|
| 固定模型 | 0.7nm、384hex/p3/q15、三维缺口、完整40端口；原物理不变 | source_inventory_v24.json |
| 唯一实现 source | 370b7bbe2455448b320ca4272eb62950e4715ecc；运行前已 clean 提交 | source_inventory_v24.json |
| 小模型／实际 dat 接线 | 最终28 passed，两个已消费历史用例 deselected | test_results_v24.json |
| 6个新 one-run 入口 | 均 validate valid，未假装已正式执行 | run_index_v24.json |
| 容量 | 全树规划5709615024 B≤8GiB；A+LU1354430592 B≤2GiB | local_capacity_v24.json |
| 首次队列 | CPU准入失败，无数值 actor；队列 code0 不表示资格 | qualification_and_dispatch_v24.json |
| 重试 | 自动审批服务认证403，命令未执行；网页工具同时报token_expired401 | approval_block_v24.json |
| 真实主块／因子／D_L | 数量0；真实配对、rcond、重载、组合Gate均 NOT_RUN | block_action/local_factor_safety/local_reload/composite_overlap_v24.json |
| LW／LCW／LZ／LCZ | 各0周期；原方程、场与功率没有新值 | candidate_comparison_v24.csv |
| 唯一VERIFY | 未执行，未读取REF7，完整资格未评估 | field_checks_v24.json |
| Git交付 | 实现已提交；本次审批故障后的回应／记录为本地待提交，未推送 | 最终receipt |

本次实现让残差先经过八个固定几何组中的完整局部解，再比较是否追加既有低阶作用像校正。它改变求解器每步寻找修正的方式，原有限元方程及跨块耦合保持。可能收益是改善目前只靠标量 fine 作用难以处理的局部方向；代价是八块稠密 LU、三角解、粗矩阵读取及额外原算子作用。现在没有正式 micro 数据，不能评价收益。

## 固定定义和独立审核

```math
A_b=K_b-C_b H_{hat}^{-1}F_b=E_b\bar S E_b^H,
\quad Lr=\sum_b E_b^H A_b^{-1}E_b r,
\quad LCr=Lr+TR^{-1}U^H(r-\bar S Lr).
```

每块保留原 cell Schur、共享与 Floquet贡献。局部人工边界只用于PC，不作为新物理边界。无 global fine K/A、正规方程、旧p4逆、shift/ILU/drop或自适应精化。新 `D_L=U^H Dop T` 必须通过固定小SVD及组合恒等式；旧 UᴴT 通过不替代它。新二维反例与右PC恢复小测试已通过，真实Gate尚未运行。

局部规格为8块、complex128、LAPACK部分选主元LU。部署执行后必须披露 LOCAL8_DENSE_LU_PRESENT；LC另外复用GLOBAL_TALL_IMAGE_QR_PRESENT。当前真实因子没有构造，不能填写实际因子hash／rcond。单元、端口和内部特解仍按原方程恢复；参考数据只允许冻结后的VERIFY，当前未读。

## 几何与容量

V15原 canonical entity map 只作几何来源；不读取其特征、权重或解。八盒切面x=0/y=0/z=0.525，行数2913/2676/2289/2076/2439/2220/1863/1668，共18144行、2448完整实体。完整实体高阶矩不拆组，slave不增加。完整map及T/U/R成员验证留给正式SETUP；本记录引用冻结文件hash，未把计划当作新现场核验。

一套局部矩阵载荷677215296 B，一套LU同量，两套合1354430592 B，pivot上界145152 B。额外工作区746594352 B；原packet、像矩阵、Krylov、临时副本与全部对象重叠计入，保守同时规划5709615024 B。这是derived容量，实际SETUP RSS未知。

## 失败、费用与边界

首个小回归在只读pivot被现场SciPy f2py GETRS临时修改时SIGSEGV，监督完整清场。最小修复只增加私有整数pivot工作区，未复制大型LU或修改安装栈。第二个根因是整块D_L为零时舍入残量在1×1相对比值上可呈满秩；另加整块运算分辨率判据，不修改1e-12阈值，不截秩。最终28 passed；失败证据和修复2/4、780秒保守编辑上界均保留。详细界限见deadline_repair_v24.json。

已监督辅助、失败测试及首次准入合计43.5801978582s，其中正式数值wall=0。最大顺序监督区间的采样同时树峰156880896 B，ownswap/VRAM/OOC0，全部观测后代清理。这不是完整编辑期间峰，也不是真实八块部署峰。历史 formal 下界75124.91759302444s仍保留，旧辅助和暖链 per-solution 精确拆账unknown。所有成本shared-workstation，不宣称无争用加速。

从首次实时时钟冻结的start12:04:23.502588Z、heavy-stop15:34:23.502588Z和deadline16:04:23.502588Z保持。自动审批403使受控启动未执行；认证恢复也不得刷新本窗口。后续commit/push依赖同一不可用服务，尚未绕过或尝试其他写Git路径。

## 未运行与唯一下一建议

四路线均NOT_RUN。没有原残差、总/散射E/H/curl、selected复场、40通道、R/T/A/A_volume或单通道功率新结论；没有通过点、神经增量或目标规模资格。旧V22/V23负结果和原始记录不改写。本批不是固定八块的数值负结果。

唯一下一建议：恢复客户端认证后，在原窗口仍有效且fresh资源准入通过时，执行已提交、已validate的六入口原队列。窗口耗尽则如实收口未运行项，等待下一review授权新窗口；不改数值规格或扩大范围。

[回应](../response_v24.md)、[分流](records/qualification_and_dispatch_v24.json)、[来源](records/source_inventory_v24.json)、[费用](records/resource_costs_v24.json)、[原始审批故障](records/approval_block_v24.json)。GitHub视觉NOT_VERIFIED；本地Markdown结构检查不替代页面显示。
