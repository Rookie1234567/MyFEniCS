# Parallel Research Task：Floquet-carrier envelope H(curl)

## 0. 身份

```text
task_kind          = PARALLEL_DISCRETIZATION_RESEARCH
branch             = chatgpt/20260827-task40-parallel-floquet-envelope-hcurl
base_sha           = 860141710514ee46bcaaccaaf21155f2308faa5d
creation_authority = user explicit instruction on 2026-08-27
relationship       = parallel to Task040 Review V6
merge_approval     = NO
production_default = unchanged
```

该分支不替代 Task040，也不向 Codex 正在执行的 Task040 分支写入文件。

## 1. Blocker

本任务消除的 blocker 是：

> 即使 factor-free/matrix-free solver把每个自由度的内存显著降低，0.7 nm 下朴素
> `h proportional to lambda` 的三维自由度仍可能按 `lambda^-3` 增长，2 TB 预算未必足够。

## 2. 研究问题

```text
Q1:
    carrier phase extraction是否与Nedelec H(curl)和double Floquet严格兼容？

Q2:
    多个physical Floquet carriers能否在coarse envelope mesh上复现快速振荡场？

Q3:
    对matched accuracy，能否相对ordinary Nedelec显著减少active unknowns？

Q4:
    carrier count、quadrature和block coupling是否仍满足0.7 nm内存合同？
```

## 3. 允许修改

```text
新增research-only shifted-curl/carrier algebra
新增UFL form helper
新增focused unit tests
新增opt-in manufactured/flat/layered runner
复用canonical Floquet/DtN metadata
复用matrix-free/local-service infrastructure
```

## 4. 禁止

```text
修改master或Task040执行分支
改变ordinary defaults
把carrier helper从public solver API默认导出
未经E1/E2直接运行重型5 nm或0.7 nm
把低rank/低DoF预测写成measured
用raw global row跨MPI身份
materialize全部carrier block或dense port W
```

## 5. 执行顺序

```text
E0 pure algebra
E1 one-carrier manufactured equivalence
E2 two-carrier MatNest equivalence
E3 5 nm flat/layered matched-accuracy DoF test
E4 5 nm non-separable 3D
E5 intermediate wavelength reduced pilot
E6 0.7 nm reduced non-separable pilot
```

只有前一 Gate 通过才进入下一 PDE 阶段。

## 6. 成功层级

```text
REFERENCE_ALGEBRA_PASS
    E0通过

CARRIER_FORM_EQUIVALENCE_PASS
    E1/E2通过

5NM_DOF_REDUCTION_SIGNAL
    matched physical error
    and active unknown reduction >=4x

5NM_NONSEPARABLE_PASS
    full residual/physics通过
    and memory lower thanordinary matched-accuracy route

0P7NM_DISCRETIZATION_CANDIDATE
    reduced 0.7 nm pass
    matrix-free/streaming/no-replication contracts pass
    capacity prediction high envelope <=1.5 TiB
```

## 7. 证据要求

```text
branch/HEAD/worktree
input/physical/source hashes
carrier canonical list/hash
Bloch and Gram audit
matrix action equivalence
true residual
R/T/A/E/H where applicable
ordinary/envelope unknown and byte ledger
quadrature and block count
MPI ownership and replication inventory
measured/derived/predicted/not_run labels
```

## 8. 当前状态

```text
E0 NumPy reference = pass in isolated environment
repository complex ABI test = not_run
E1 onward = not_run
```

下一执行入口见 [codex_handoff.md](codex_handoff.md)。
