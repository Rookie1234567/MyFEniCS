# Structured-background / LOR Codex handoff

本文件用于 Codex 在独立 worktree中验证本并行分支，不影响正在执行的 Task040 Review V6。

## 1. 分支

```bash
git fetch origin chatgpt/20260827-task40-parallel-floquet-envelope-hcurl
git worktree add \
  ../MyFEniCS-parallel-methods \
  origin/chatgpt/20260827-task40-parallel-floquet-envelope-hcurl
cd ../MyFEniCS-parallel-methods
```

## 2. 先读

```text
docs/task040_parallel_floquet_envelope_hcurl/alternative_methods_portfolio.md
docs/task040_parallel_floquet_envelope_hcurl/structured_background_fft_hcurl.md
docs/task040_parallel_floquet_envelope_hcurl/low_order_refined_hcurl.md
docs/task040_parallel_floquet_envelope_hcurl/feasibility_reassessment.md
```

## 3. 轻量测试

```bash
python -m pytest -q \
  src/test/test_318_task040_parallel_floquet_envelope.py \
  src/test/test_319_task040_parallel_background_hcurl.py

python -m compileall \
  src/solvers/floquet_envelope_hcurl.py \
  src/solvers/floquet_background_hcurl.py
```

本提交在隔离 NumPy环境中对 test319得到：

```text
6 passed
```

项目 qualified environment仍需重跑。

## 4. A1第一步

先实现：

```text
src/studies/run_floquet_background_hcurl_smoke.py
```

只做 fully-periodic homogeneous DOLFINx tiny case：

```text
ordinary Nedelec A action
vs
NumPy/MatShell background action
```

必须验证：

```text
Bloch frequency order
phase once
3-component symbol sign
MatShell repeat/linearity
complex128 true residual
```

## 5. A1第二步

实现 x/y FFT + z-discrete prototype：

```text
small structured hexa box
periodic x/y
open or impedance z
constant then z-layered background
```

每个 `(m,n)`只允许 bounded 1D z solve。禁止用 fully periodic 3D FFT结果替代 open-z Gate。

## 6. A2准备

只做设计与 tiny local basis tests，暂不实现完整 p6 campaign：

```text
fixed LOR cell topology
edge/face orientation
commuting transfer
MPC/Floquet compatibility
```

## 7. 停止条件

```text
A1 S2 flat/layered无8x residual improvement
A1 S3 reduced grating无4x improvement
LOR L2无h/p robustness
```

触发后保留负结果，不扫描 shift/background/AMG菜单。

## 8. 共享边界

可 selective cherry-pick到 Task040 的只有经过独立验证的：

```text
Bloch FFT frequency/key mapping
Maxwell symbol sign tests
FFT working-set estimator
future x/y transform/scatter helper
LOR local basis/transfer helper
```

不得 cherry-pick：

```text
ordinary default changes
unqualified carrier solver
fully periodic oracle as open-z production PC
research docs as merge approval
```
