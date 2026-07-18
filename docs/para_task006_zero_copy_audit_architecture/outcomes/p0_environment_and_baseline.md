# P0 环境与 clean baseline

## Gate 结果

`P0 = PASS`。Task005 Review V1 的数据身份已修正；R4 checkpoint/dataset identity
校验通过；clean h5/MPI4 baseline、完整测试、diff check 和 heavy artifact ignore
均通过。允许进入 P1 borrowed exact action。

## Clean source

| 项目 | 值 |
|---|---|
| branch | `ChatGPT/20260715-para-task-neural-local-pc` |
| SHA | `9822bc5d84375bf1cd3039aec7ca1e849413c0ed` |
| tracked source | clean |
| branch operation | 无 |
| FEniCS | WSL complex wrapper |
| parallelism | MPI4；OMP/OpenBLAS/MKL/NumExpr = 1 |
| artifact | `benchmarks/artifacts/cases/095/p0_baseline_9822bc5/`，Git ignored |

## h5/MPI4 baseline

| 指标 | 结果 |
|---|---:|
| KSP reason | 2 |
| iterations | 852 |
| solve | 93.346950 s |
| total | 116.660973 s |
| condensed operator applies | 2,584 |
| one-level applies | 5,112 |
| reported residual | `9.980248143e-7` |
| condensed true residual | `9.980248132e-7` |
| full augmented residual | `9.980248132e-7` |
| R | `0.089021603380` |
| T | `0.442588273904` |
| A_volume | `0.468390120856` |
| closure | `-1.859745025e-9` |
| external simultaneous worker peak | 1.608242 GiB |
| swap in/out delta | 0 / 0 pages |
| numeric pass | true |

该 baseline 是 Task006 的 clean sanity/paired-memory reference，不冒充后续 shadow
paired result。

## Validation

| 检查 | 结果 |
|---|---|
| complete `src/test` | 209 passed, 12 skipped |
| Case095 targeted before commit | 13 passed |
| `git diff --check` | PASS |
| `git check-ignore benchmarks/artifacts/cases/095` | PASS |

首次 baseline 启动在 solver 前因错误的完整 SHA attestation fail closed；没有开始
计算或产生结果。改用 `git rev-parse HEAD` 返回的真实 SHA 后正式运行通过。
