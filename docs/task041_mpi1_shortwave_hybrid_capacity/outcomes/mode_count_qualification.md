# 模态数资格

3 nm p6/h3 的 M800 与 M1200 都完成了 candidate consumer solve 和 recovery mechanics，但 own physics negative，因此没有 qualified M：

| M | residual Gate | own physics | authority |
|---:|---|---|---|
| 800 | 五项均 <5e-9 | abs(A_balance-A_volume)=1.9160032445286745e-5 > 1e-5 | measured_candidate_physics_negative |
| 1200 | 五项均 <5e-9 | abs(A_balance-A_volume)=1.8704745773062692e-5 > 1e-5 | measured_candidate_physics_negative |

M800→M1200 的 R/T/A/A_volume scalar absolute difference 为 4.726312532454813e-7 / 1.275602950843622e-6 / 8.029716976054591e-7 / 1.2582583698850236e-6。这不是 convergence pair：task.md 要求每个 M 先独立通过 residual、physics、channels、E/H 和 canonical Gate。

所以 minimum_qualified_M=NA；M1600 的 final reason 是 NOT_RUN_DUE_TO_3NM_M800_AND_M1200_OWN_PHYSICS_GATE：没有 valid own-pass M pair，按 task.md §12.2 true Gate 未释放。M1200 是后来明确授权的一次 controlled continuation，不能被写成未运行。
