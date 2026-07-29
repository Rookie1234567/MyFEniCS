# Task002 M0--M2A 结果总览

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
