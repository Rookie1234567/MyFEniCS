# Task038-extra 参考边界：只读线性代数来源

## 来源与用途

Task038-extra 只作为静态架构和负结果边界参考，不是 Task40 的可直接迁移实现。审计读取了 origin/codex/20260820-task38-extra-full3d-iterative-0p7nm 中的 fullspace_local_spectral*.py、相关 runner，以及 N2 local-factor record/diagnostic。没有 cherry-pick、整文件复制、代码执行或数值重跑。

Task038-extra 的可复用概念是：把相同数值类的局部复数块按 canonical descriptor 分组，使用 packed complex128 factor，保持 deterministic owner routing、owner-local rows、orientation/Floquet metadata、packed solve 和 round-trip residual。它还展示了必须显式验证 owner/partition/hash/生命周期，而不是用全局复制的数据结构自证。

## N2 证据摘要

| 项目 | hash-bound / measured value | 边界 |
|---|---|---|
| N2 record | docs/task038_extra_full3d_iterative_0p7nm/outcomes/records/n2_local_factor_la_v2.json | read-only reference |
| matrix class digest | 0c6b9830423f8baf83b6714ac178c724b63af1359d01b3ca5badd1d40c070a67 | imported class identity |
| rows | 882 | not Task40 local-row target |
| factorization residual | 8.158904706122267e-16 | linear algebra diagnostic |
| condition estimate | 57576704.11589122 | warns about conditioning |
| packed round-trip relative error | 0 | storage/solve round-trip |
| max pairwise solution difference | 1.135334055192972e-12 | source comparison |
| individual residuals | S0 1.0426e-11; S1 9.3162e-12; S2 2.5449e-11; S3 6.6729e-12 | diagnostic values, not Task40 Gate |
| process-tree peak | 1487814656 B | historical reference only |
| swap | 0 B | historical reference only |

N2 was classified CONTROLLED_STOP_LA1_MARKER_REGISTRATION / NOT_QUALIFIED because the marker path rejected linear_algebra_diagnostic with ValueError: unknown N2 marker: linear_algebra_diagnostic. LA2, fresh N2, and physics were not run. The small residuals and packed round-trip therefore do not constitute a Task40 production qualification.

## Migration boundary

Task40 may re-derive the following ideas in the appropriate src/solvers module:

- exact-class identity and packed complex128 factor storage;
- deterministic owner routing and owner-consistent partition of rows;
- orientation/Floquet metadata as part of the row identity;
- local solve residuals and factor lifecycle as independent evidence.

Task40 must not import the Task038-extra benchmark runner as a numerical core, copy its task-numbered orchestration, reuse its raw factor or N2 result, or infer scalability from its N2 residuals. The Task040 side impedance/transmission module must use the frozen Task040 physics and provide its own tiny complex-block oracle and serial/MPI2/MPI4 identity tests.

## Self-repair and formal boundary

An implementation defect may be repaired only locally, with the original root/evidence retained and a focused regression. A real Gate failure must stop the dependent Task40 sequence with its measured residual, rho, factor inventory, resource and swap values. No sign, orientation, source, threshold, hard column, or partition rule may be changed to turn a failure into a pass.

T40-0 therefore records Task038-extra as research-only architecture evidence. It does not authorize T40-1/T40-2 code, Level A/B formal work, top/full Hybrid work, 0.7 nm work, or any heavy run by itself.
