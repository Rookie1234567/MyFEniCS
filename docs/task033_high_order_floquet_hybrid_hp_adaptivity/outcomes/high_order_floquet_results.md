# Task033 高阶 3D Floquet 结果

## 1. Planned fixture matrix

| Fixture | degree | MPI ranks | polarization / angle | 当前状态 | 数据身份 | 证据 |
|---|---|---:|---|---|---|---|
| A: 10 nm air box | p1–p4 | 1, 2, 4 | at least one analytic S and P case | not_run | not_run | Case090 record pending |
| B: 10 nm air–Si plane interface | p1–p4 | 1 first; selected 2/4 | S/P at 10°; 1°/5° smoke | not_run | not_run | Case090 record pending |

## 2. Algebra and topology Gates

| Metric | Gate | Unit / baseline | 当前结果 | 数据身份 | 证据 |
|---|---:|---|---|---|---|
| constraint round-trip relative error | `<=1e-12` | relative | not_run | not_run | pending |
| Bloch trace mismatch | `<=1e-11` | relative | not_run | not_run | pending |
| reduced/full action error | `<=1e-11` | relative | not_run | not_run | pending |
| full true residual | `<=1e-10` | relative | not_run | not_run | pending |
| MPI result difference | `<=1e-10` | relative to MPI1 | not_run | not_run | pending |
| dense boundary square formed | `false` | boolean | not_run | not_run | pending |
| full boundary DoF/field gather | `false` | boolean | not_run | not_run | pending |

## 3. Performance and cache fields

| degree | periodic DoF | slave/master | transform NNZ | NNZ/constrained DoF | topology build | phase-only update | peak RSS | cache hit/miss | communication | 状态 |
|---:|---:|---|---:|---:|---:|---:|---:|---|---|---|
| p1 | not_run | not_run | not_run | not_run | not_run | not_run | not_run | not_run | not_run | not_run |
| p2 | not_run | not_run | not_run | not_run | not_run | not_run | not_run | not_run | not_run | not_run |
| p3 | not_run | not_run | not_run | not_run | not_run | not_run | not_run | not_run | not_run | not_run |
| p4 | not_run | not_run | not_run | not_run | not_run | not_run | not_run | not_run | not_run | not_run |

Times will be recorded in seconds, RSS in GiB and communication in bytes. No fixture has
been executed yet.

