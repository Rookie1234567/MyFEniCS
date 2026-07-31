# Task002 结果总览

## M4E 更新（Review V7）

Case119 已完成 Ny4 production rebaseline。切向 projection 合同修复后，全体实际
power-carrying S/P auxiliary/direct 最大差异为 `9.11e-14–1.09e-12`，通过
`1e-10` Gate。唯一 production route 为 Full3D static uniform N1curl p5/h10/MPI2，
axis counts `(6,4,14)`，clean baseline 为
`10e3356ba8364286a452077f71d7e3b92ea24cd5`。

增强 canary 全部通过；新 campaign 完成 96/96 training 与 16/16 frozen validation，
112 条正式样本全部 measured-pass、zero swap、cleanup complete。Ny4-only compact
dataset 与 exact-design checker 通过，Case119 checker 6/6 pass。Case117 保持不可变，
Ny3 56 个 pass 未复用。未开始 surrogate training、validation scoring、angle DOE 或
inversion。详见 `m4e_ny4_production.md`、`m4e_dataset_report.md` 与 `response_v8.md`。

## M4D 更新（Review V6）

Case118 已确认 Case117 index 40 的根因是 Ny=3 导致的 n=0/n=-3 离散
Bragg/trace alias。Ny=3 总泄漏为 `1.2312e-6`，Ny=4 降至 `3.2783e-25`；
actual bottom-S trace overlap 从 `0.3630` 降至 `2.68e-16`。q=21/31/39/47
结果完全不变，排除 surface quadrature 欠积分。35 个 M4D PDE 全部 zero swap、
cleanup complete，Case118 checker 12/12 通过。

Route A Ny=4 得到支持，但 production mesh 尚未修改，M4 仍停止。独立 q63
projection 同时发现 outgoing-P auxiliary/direct amplitude 不一致（最大 `5.25e-3`），
等待 Review V7 disposition。详见 `m4_y_alias_diagnosis.md` 与 `response_v7.md`。

## M2B 更新

Review V2 Required M2B 已完成，详见 `m2_solver_domain_qualification.md` 与
`solver_routing_map.md`。独立 p/h reference 证明 p4/h10 欠分辨；Hybrid p5 与 same-p Full3D
p5 一致，axial A/B 与真实双 Floquet probes 排除了 axial mapping 和约束错误作为大分支跳变根因。

中心几何 Hybrid p4 80-angle map 为 39 pass / 41 fail；p6 的 45° near-degenerate mode block
拆分仍触发 biorthogonality Gate。当前冻结 Route 4（暂停 Hybrid，候选 Full3D static hierarchy），
但 Full3D p4/h7.5 尚无 80-angle domain qualification，因此 M3 继续关闭并等待 Review V3。

M2B clean PDE baseline 为 `673c66ddee116e683a21b7ea8a90dc158cac2069`。

## M2A 历史结论

Task002 状态仍为 `controlled_stop_at_M2`。Review V1 要求的 Case113、独立 Full3D
p4/h10、p4 M80/120/160/240、p5 M120、p6 M120、完整 energy ledger、13 点 LF stencil、
四点 HF diagnostic subset 和 cutoff v2 均已完成。

M2A clean PDE baseline 为 `a0b9ae0e457b74876eb39346885d53e940ab1584`。Case112 的
9 个原始样本保持不变。LF stencil 为 4 pass + 9 fail；p4 的能量失败对 M 不敏感。独立
Full3D 与 p4 外响应一致，但 p5/p6 跳入另一响应分支，因此当前固定 LF4/HF p6 组合没有
建立可信的 multi-fidelity p-convergence。

cutoff v2 证明 0.5° 的小 beta 是 incident m0 grazing，不是非零衍射级 crossing。失败与
conical 中间方位角关联。LF4 不能作为全角域统一 low fidelity，M2 Gate 未通过。

M3--M10 全部 `not_run`：没有 49 点正式 campaign、四维 bulk、surrogate training、angle
DOE、P/Hybrid-P 或正式反演。
