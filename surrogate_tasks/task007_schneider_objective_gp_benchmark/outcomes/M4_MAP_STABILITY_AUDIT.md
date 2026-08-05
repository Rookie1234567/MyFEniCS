# M4A independent oracle-MAP stability audit

使用 Differential Evolution 加 bounded L-BFGS-B polish，未调用 M3 的 grid+multistart MAP 函数。所有 48 个组合均与原 MAP 在 objective 和坐标 Gate 内一致。

| quantity | result | Gate |
|---|---:|---|
| target/contract/noise rows | 48 | 48 required |
| objective Gate pass | 48/48 | abs diff <= 1e-6 max(1,F) |
| coordinate Gate pass | 48/48 | dh <= 0.02 nm, dw <= 0.005 nm |
| combined Gate pass | 48/48 | all required |
| objective-equivalent coordinate mismatches | 0 | report, do not collapse |

Evidence is companion-only; M3 MAP and traces are unchanged.
