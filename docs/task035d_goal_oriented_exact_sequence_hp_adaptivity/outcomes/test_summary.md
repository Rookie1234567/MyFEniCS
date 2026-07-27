# Task035d Test Summary

## 1. 环境

```text
workspace = /home/Projects/MyFEniCS
activation = source scripts/activate_myfenics_wsl.sh
python = /home/Projects/MyFEniCS/.venv/bin/python
PETSc.ScalarType = numpy.complex128
PETSc.IntType = numpy.int32
formal_MPI = 8
ordinary_default = unchanged
```

所有 Git、Python、MPI、PETSc、DOLFINx 与测试命令都在同一个 WSL Bash
环境中执行。没有使用 Windows Python、Git、MPI 或 Windows 仓库副本。

## 2. 测试金字塔

| Scope | Command | Result |
|---|---|---|
| left-grating lane closure contract | `python -m pytest -q src/test/test_218_task035d_left_grating_top_hp_candidate.py` | `3 passed` |
| left-grating launch/solver/checker + Case097 contracts | test193/test194/test217/test218 + Case097 contracts | `39 passed` |
| development registry contract | checker + pytest contract | pass；`1 passed` |
| Task035d focused serial | all `test_*task035d*.py` + Case097 contracts | `215 passed, 13 skipped` in `1308.33 s` |
| Task035d MPI2 components | 14 periodic/hanging/PETSc/adjoint/DWR files | `80 passed, 10 skipped` in `1340.79 s` |
| Task035d MPI8 representative | selector、compiled local-h、unit adjoint、selective trace | each of 8 ranks: `16 passed, 4 skipped` in about `357.6 s` |
| affected Hybrid + documentation targeted | Task032/033/035b Hybrid + documentation | Hybrid group pass；documentation `14 passed` |
| full repository final | `python -m pytest -q` | `837 passed, 41 skipped` in `1761.55 s` |
| Case097 compact authority | generator `--mode check` | pass；2 records |
| registry standalone checker | `check_development_model_registry.py` | pass；39 Task sections / 76 evidence paths |
| Ruff | `python -m ruff check src benchmarks` | pass |
| compileall | `python -m compileall -q src benchmarks` | pass |
| JSON | nonignored, non-artifact repository JSON parse | 998 files pass |
| whitespace | `git diff --check` | pass |

## 3. 正式 PDE 与 independent checker

最终 left-grating PDE 绑定 clean numerical source
`333cb7e437906c78c95c94788abb76e2f263bc80`：

| Gate | Result |
|---|---|
| MPI | 8 |
| watchdog | pass |
| exact-sequence / hanging / Floquet / ownership | pass |
| true residual | `3.267074937e-11 <= 1e-9` |
| zero swap | pass |
| resource Gate | pass；preferred 40% peak reduction pass |
| significant powers | `4/12`，fail |
| significant complex amplitudes | `6/12`，fail |
| R00/R/T/Aclosure | pass |
| Avolume / energy closure | pass |
| interface field | pass |
| volume field | max-point fail |
| final classification | controlled negative |

raw watchdog SHA256：

```text
7d4c7a1efa0068c7a6c478ad4cef4b88fdfa1f5acbd10532d4c2794a356f7165
```

full/compact checker SHA256：

```text
1b9dd3cdb931f5fe69da5a0a567ff278a47416f7082d47cef2e0b5e4109e2492
d6e03061465b29ce4e958bfd6ac7972f245130fdf66de197541caed09e8e4225
```

## 4. PDE 重跑说明

文档收口、lane-closure JSON 和合同测试不改变 numerical kernel，因此不会
重跑已绑定 clean SHA 的重型 PDE。任务规则要求昂贵 Gate 只有相关 numerical
blob、mesh、material、plan 或 checker input 发生变化时才重新资格化。

全库第一次运行发现一个历史 Hybrid API 组合缺陷：

```text
_combine_owned_entries(..., *, comm)
```

helper 已要求 collective communicator，但
`src/solvers/hybrid_local_dtn.py` 的两个调用点漏传 `comm`。修复为显式
`comm=comm` 后，Task032/033/035b Hybrid targeted suite 与全库回归通过。
该路径不被本轮 Task035d Full3D candidate 调用，所以不改变其 solver
summary、field、DtN orders 或 checker input；没有理由重跑 Task035d 重型
PDE。Task035c 的历史 formal records 仍绑定其原 numerical SHA，本分支没有
把新源码冒充为对历史 Hybrid PDE 的重资格化。

第一次 full repository 还发现 Case097 未加入 documentation contract 的
active-research case 集合。补充 Case097 专属 config assertions 后，文档合同
`14 passed`。

## 5. Final closeout

```text
Task035d focused serial = 215 passed, 13 skipped
Task035d MPI2 = 80 passed, 10 skipped
Task035d MPI8 = 16 passed, 4 skipped per rank
affected Hybrid targeted = pass
documentation contract = 14 passed
full repository = 837 passed, 41 skipped
Case097 / registry / Ruff / compileall / JSON / diff-check = pass
heavy PDE rerun after documentation closeout = no
ordinary default changed = false
```
