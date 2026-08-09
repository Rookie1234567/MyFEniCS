# Candidate H H1R2：单源 p6/h10 MPI1 全空间 action

本页记录 Review V4.2 唯一一次正式 H1R2 action-only run。这里的“全空间 action”是：对完整 p6 Nédélec 自由度输入，逐单元直接产生
`A_h = curl-curl - k0^2 * epsilon * mass` 的 residual；也就是 curl 项与带负号的频率-介电质量项组成的作用，不是 coercive `B_h`，也不是求解 PDE 或生成物理场。

## 1. 结论与冻结边界

| 项目 | 结果 | 说明 |
|---|---|---|
| H1R2 | `H1R2_PASS` | 只证明 frozen p6/h10、MPI1、单一 `seed_17037` 的 exact full-space action |
| PDE/KSP | 未运行 | 没有 time-harmonic solve、KSP 或收敛结论 |
| physical field/RTA | 未运行 | 没有 field recovery、官方 R/T/A |
| H2 | `locked` | 本结果不是 smoother 资格 |
| H1R3 | `locked_pending_review` | 仅具备提交下一轮 review 讨论的资格，不表示已经解锁 |
| G2 | `G2_FAIL` | 历史 LOR-HX 负结果保持不变 |
| G3 additive LOR-HX | `prohibited` | 不重开、不扫描 |
| old G4 sweep | `prohibited` | failed LOR-HX 后仍禁止 |
| old H1.2 | `CONTROLLED_STOP_TIMEOUT / NOT_QUALIFIED` | 历史受控停止不被改写 |
| ordinary default | unchanged | Candidate H 仍是显式研究路径 |

## 2. 身份与固定命令

| 项目 | 值 |
|---|---|
| branch | `codex/20260806-task37-iterative-extra-development` |
| measurement source SHA | `66ccb5891b7f6caac3ebfe08f72cf525c40f3fef` |
| implementation commit | `032fb7d812648d4c8b286babdf1cafe1ac70cd59` |
| runtime provenance commit | `66ccb5891b7f6caac3ebfe08f72cf525c40f3fef` |
| source start/end | 同一 SHA，均 clean |
| source | `seed_17037` |
| MPI | `1` |
| reference/candidate applies | `1 / 2` |
| global rows/constraints | `173802 / 9210` |
| command | `python -m benchmarks.run_task037_extra_candidate_h h1r2-watchdog --run-dir /home/shenjh/Projects/MyFEniCSx_task37_extra/benchmarks/artifacts/task037_extra_h1r2_v4_66ccb589_mpi1_20260809_run1` |

qualified 环境为 PETSc `complex128/int32`。当前仓库 `.venv` 解析到记录中的 `/home/shenjh/Projects/MyFEniCS-Surrogate/.venv` qualified shared target；这只是同一 Linux qualified symlink target，不是 Windows/ABI 混用或异常。

## 3. action 与数值 Gate

| 指标 | 实测值 | Gate |
|---|---:|---|
| reference first apply | `1.1653526849113405 s` | 记录值 |
| candidate apply 1 | `1.2354860971681774 s` | 记录值 |
| candidate apply 2 | `1.195433100918308 s` | 记录值 |
| candidate 2 / reference | `1.0258122853248122` | `<=2`，PASS |
| relative error | `2.7326039504560278e-17` | `<=1e-11`，PASS |
| finite/deterministic/repeat equal | `true / true / true` | PASS |
| canonical export | `true` | 仅在 numerical Gate 后执行；不计入 action timing |

第二次 candidate apply 仍远低于 `2 * reference`；canonical export 的文件写出不混入上述 action timing。

## 4. 时间与内存

| 指标 | 值 | 口径/结论 |
|---|---:|---|
| completion elapsed | `14.121019201120362 s` | watchdog completion |
| wall | `14.13039601710625 s` | 外层诊断 wall |
| live samples | `56` | worker 存活期间 |
| process-tree peak | `332636160 B = 0.30979156494140625 GiB` | live worker tree |
| swap | `0` | PASS |
| Review V4 `<=1.25 GiB` | `true` | 更严格的资格 authority，PASS |
| 用户 decimal `<2,000,000,000 B` | `true` | 更宽的用户目标，单独记录，PASS |

两个内存门槛不是同一个门槛：本次同时通过 Review V4 的 `1.25 GiB` authority 与用户的 decimal `<2,000,000,000 B` 目标。由于实测已明显低于二者，没有必要为这一单源 MPI1 结果继续做 `<2GB` 优化；不能把它外推成更大网格、其他 MPI 数或 PDE 结果。

## 5. retained payload 与禁止对象

retained numeric payload 的 component sum、local、global sum、global max 均为 `6151104 B`，约 `5.86614990234375 MiB = 0.005728662014007568 GiB`，低于 `0.50 GiB`。

| retained component | bytes |
|---|---:|
| coefficient function local array | `2780832` |
| output vector local storage | `2780832` |
| packed constants | `0` |
| slave indices | `36840` |
| owned slave indices | `36840` |
| flat slave indices | `36840` |
| master indices | `36840` |
| conjugated master coefficients | `147360` |
| constraint work | `147360` |
| owned slave work | `147360` |
| **sum and all retained totals** | **`6151104`** |

| 审计项 | 值 |
|---|---|
| dense cell tensor retained/materialized per apply | `0 / false` |
| global A / global constraint matrix / condensed Schur | `false / false / false` |
| factor count | `0` |
| KSP / DtN | `false / false` |
| cell metadata retained | `false` |
| ordinary default changed | `false` |
| per-apply packed temporary | `3556224 B`，apply 后释放，不计入 retained payload |

## 6. Canonical dual evidence

canonical dual packet 是把输出按物理实体 key 写出，用来绑定完整 reduced row 数；它不是另一个求解器或 global matrix。

| 项目 | 值 |
|---|---|
| export timing boundary | `canonical only-after-numeric-gate=true` |
| packet count | `164592 = 173802 - 9210` |
| duplicate count | `0` |
| manifest | `canonical/seed_17037/candidate_manifest.json` |
| manifest SHA256 | `1dfdcbfcd73010234dcdb7438eb3d869c9cbd07ed6981fc0ba5275c170faf139` |

## 7. Runtime provenance 与 compact checks

| 字段 | watchdog/worker |
|---|---|
| `_MYFENICS_WSL_QUALIFIED_ACTIVATION` | `1 / 1` |
| `sys.executable` | `/home/shenjh/Projects/MyFEniCS-Surrogate/.venv/bin/python`，相同 |
| `OMP_NUM_THREADS` | `1 / 1` |
| `OPENBLAS_NUM_THREADS` | `1 / 1` |
| `MKL_NUM_THREADS` | `1 / 1` |
| `NUMEXPR_NUM_THREADS` | `1 / 1` |
| identity match | `true` |

Compact checker record 为：[h1r2_single_source_action.json](../../../benchmarks/cases/101_task37_extra_development/records/h1r2_single_source_action.json)。

| compact evidence | 值 |
|---|---|
| record SHA256 | `3be688f6e0794b47fb7d77f3823cb2e69b78aefaec6ea31833d3a0421acab978` |
| record `evidence_sha256` | `eeb002ad7d4091aec4aaf34055379f2a8f3bc4c64a46b3dda11328f8b28d0513` |
| checker status/pass/problems | `pass / true / []` |
| all check groups | `true` |

Raw ignored directory：
`/home/shenjh/Projects/MyFEniCSx_task37_extra/benchmarks/artifacts/task037_extra_h1r2_v4_66ccb589_mpi1_20260809_run1`

| raw file | SHA256 |
|---|---|
| `run_summary.json` | `bcf220a7b62ce803387a71c6dd3cefed0447f6ada17234328106aa23b785114c` |
| `watchdog_summary.json` | `f8228385afc128aa3d2fd8a49398957da4d68d9eb6a634692748fe3a10ceae6a` |
| `watchdog_timeline.jsonl` | `61ffb299b4fd9a22bd65468e81bec8f28759295d6d8fea281ccdba2f4962a2a0` |
| `worker_stdout.txt` | `b83ac543bc909515c05b9a4109831d9d6b69a641caaada4f96f69592981988b9` |
| `canonical/seed_17037/candidate_manifest.json` | `1dfdcbfcd73010234dcdb7438eb3d869c9cbd07ed6981fc0ba5275c170faf139` |

## 8. 验证、未运行项与下一步

最终 focused suite 为 `36 passed`；compileall 与 `git diff --check` 通过；Ruff unavailable，未安装，不能写成 CI pass。正式 run 未触发 hard stop。

### 精确复现命令

以下命令均在 `source scripts/activate_myfenics_wsl.sh` 后执行；它们是本次已完成的记录命令，不表示需要再次运行：

```text
python -m pytest -q src/test/test_276_task037_extra_candidate_h_runner.py src/test/test_277_task037_extra_candidate_h_progress.py src/test/test_280_task037_extra_h1r2_mpc_rank_one_action.py src/test/test_281_task037_extra_h1r2_runner_contract.py src/test/test_282_task037_extra_h1r2_watchdog_checker.py
```

结果：`36 passed`。

```text
python -m compileall -q benchmarks/run_task037_extra_candidate_h.py src/test/test_282_task037_extra_h1r2_watchdog_checker.py
```

```text
python -m benchmarks.run_task037_extra_candidate_h h1r2-check --run-dir /home/shenjh/Projects/MyFEniCSx_task37_extra/benchmarks/artifacts/task037_extra_h1r2_v4_66ccb589_mpi1_20260809_run1 --output /home/shenjh/Projects/MyFEniCSx_task37_extra/benchmarks/cases/101_task37_extra_development/records/h1r2_single_source_action.json
```

本轮没有运行 MPI2、H2、H3、H4、full PDE、KSP、DtN、official field 或 official RTA。H1R2_PASS 只使“提交下一轮 review 讨论 H1R3”具备证据基础，不解锁 H1R3，也不解锁 H2。G2/G3/old G4 的冻结结论保持不变。
