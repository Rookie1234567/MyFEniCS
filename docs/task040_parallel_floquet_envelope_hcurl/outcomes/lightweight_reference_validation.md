# 轻量参考代数验证

## 1. 执行环境

```text
execution scope = isolated pure-Python/NumPy reference
Python          = 3.13.5
NumPy           = 2.3.5
repository ABI  = not loaded
DOLFINx/PETSc   = not loaded
MPI             = not run
```

## 2. 已运行检查

等价测试文件内容对应：

```text
src/test/test_318_task040_parallel_floquet_envelope.py
```

结果：

```text
6 passed in 0.05 s
python -m py_compile = pass
```

覆盖：

| 检查 | 结果 |
|---|---|
| direct/reciprocal lattice duality | pass |
| Bloch multiplier for reciprocal shifts | pass |
| shifted-curl product rule | pass |
| complex evanescent test-carrier conjugation | pass |
| real-coefficient block Hermitian symmetry | pass |
| duplicate carrier rank/pruning | pass |
| `5 -> 1` 与 `5 -> 0.7` 朴素缩放 helper | pass |

## 3. 这些结果证明什么

只证明：

```text
纯代数公式和NumPy reference helper一致
carrier phase使用test kappa共轭
Floquet reciprocal order不会改变Bloch multiplier
deterministic duplicate pruning按预期工作
Python语法有效
```

## 4. 这些结果不证明什么

尚未证明：

```text
UFL complex form可以在项目ABI编译
Nedelec/MPC orientation正确
periodic envelope phase=1接线正确
PETSc block action正确
physical DtN carrier mapping正确
PDE收敛
DoF reduction
内存收益
5 nm或0.7 nm物理正确
```

Codex 本地第一步应运行仓库内 focused test和 E1 UFL smoke，而不是直接启动 heavy case。
