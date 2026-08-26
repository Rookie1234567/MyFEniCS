# Codex 本地验证与继续开发说明

## 1. 获取独立分支

```bash
git fetch origin chatgpt/20260827-task40-parallel-floquet-envelope-hcurl
git worktree add \
  ../MyFEniCS-floquet-envelope \
  origin/chatgpt/20260827-task40-parallel-floquet-envelope-hcurl
cd ../MyFEniCS-floquet-envelope
```

本分支不得 merge/rebase 到 Codex 正在执行的 Task040 worktree。需要共享代码时，只允许在
结果审阅后按文件/提交 selective cherry-pick。

## 2. 第一轮轻量检查

在仓库资格化 complex128 环境中运行：

```bash
python -m pytest -q \
  src/test/test_318_task040_parallel_floquet_envelope.py

python -m compileall \
  src/solvers/floquet_envelope_hcurl.py \
  src/test/test_318_task040_parallel_floquet_envelope.py

ruff check \
  src/solvers/floquet_envelope_hcurl.py \
  src/test/test_318_task040_parallel_floquet_envelope.py
```

如 UFL complex常量或 `ufl.cross` API 与当前版本不兼容，只做最小 helper修复并增加一个
direct regression，不修改数学定义。

## 3. E1：单 carrier UFL smoke

实现一个新的 opt-in research runner，不修改 ordinary defaults：

```text
recommended path:
    src/studies/run_floquet_envelope_hcurl_smoke.py
```

固定 manufactured case：

```text
periodic rectangular box
homogeneous complex epsilon
one Bloch-compatible carrier
periodic envelope MPC phase=1
known Nedelec envelope
```

必须同时组装：

```text
ordinary field E
carrier envelope u
```

检查：

```text
reconstructed E action error <=1e-10
RHS transformation error     <=1e-10
solution error               <=1e-9
true residual                <=1e-9
```

不要一开始接 physical DtN、M480 或完整 5 nm。

## 4. E2：双 carrier MatNest

固定两个解析 plane waves：

```text
carrier 0 = incident/Bloch order
carrier 1 = one reciprocal-lattice shifted order
```

要求：

```text
2x2 carrier MatNest
cross blocks assembled from exact phase difference
MatNest action equals direct reconstructed weak action
carrier Gram after pruning condition <=1e10
```

大 carrier block不得同时 materialize到 monolithic AIJ，除 tiny oracle 外。

## 5. E3：5 nm flat/layered authority

E1/E2通过后，使用 Task39/Task40相同 5 nm input identity构造不含复杂内部结构的 flat 或
layered authority。carrier family只运行：

```text
C0 incident only
C1 zero-order partners
C2 all propagating orders
```

每个 family记录：

```text
carrier count
envelope DoF
total scalar/complex unknowns
quadrature cost
matrix-free bytes
Krylov live vectors
true residual
R/T/A
selected E/H
```

继续到 non-separable 3D 的最低 Gate：

```text
matched physical error
and total active unknowns <= ordinary matched-accuracy unknowns / 4
```

若没有该信号，不得通过增加几十个carrier追逐结果。

## 6. 与 Task040 Review V6 的交汇点

可共享的通用组件：

```text
canonical Floquet order/key mapping
full-spectrum FFT/streaming transform
physical DtN beta and TE/TM normalization
matrix-free H(curl) local service
bounded patch ownership
resource watchdog
```

不应共享：

```text
old 776 response packet
full-cross-section exact factors
Task040 failed Route C basis
production defaults
```

若 Task040 V6 full-spectrum sweep先成功，carrier envelope可以使用其完整接口频谱作为
carrier selection authority；若本分支 E3先成功，V6可把 carrier envelopes用于group local
service或Full3D handoff。

## 7. 必须保存的证据

```text
source SHA
branch/upstream/worktree
Python/PETSc/DOLFINx/Basix ABI
complex128/int type
carrier list and canonical hashes
Bloch multiplier audit
Gram singular values and selected subset
ordinary vs envelope action/residual
DoF and bytes ledger
quadrature degree
MPI ownership/replication inventory
```

## 8. 停止条件

```text
E1等价性无法建立
phase被MPC重复施加
E2 carrier block显著病态且pruning无效
E3没有至少4x unknown reduction
carrier/block quadrature成本超过ordinary route
```

遇到这些 Gate 后停止 PDE扩展并提交真实负结果；不要直接跳到 0.7 nm。

## 9. 当前边界

本分支是 research preparation。没有 ChatGPT review 和用户授权时：

```text
no master merge
no Task040 branch write
no ordinary solver default
no full target 0.7 nm
no production claim
```
