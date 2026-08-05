# Candidate F F0：p4 容量 oracle implementation Gate 失败

## 结论

Candidate F F0 的目标是做一个小规模容量实验：把同一 exact-sequence 的 p6 trace action 通过真实 p4→p6 与 p2→p4 transfer 投影到局部 p4 空间，并只用一次临时 dense complex128 LU 估计容量。它不是 production solver，也没有进入 F1、MPI8 或 PDE。

本轮分类为：

```text
F0_IMPLEMENTATION_GATE_FAILED_PETSC_INDEX_DTYPE
```

这不是 `P4_INTERMEDIATE_SPACE_NOT_EFFECTIVE`：high/mixed improvement 数值 Gate 尚未执行。

## 身份与既有边界

| 项目 | 结果 |
|---|---|
| tested tracked HEAD | `2cea3b986303d1553e062f206da452e8f609642b` |
| branch | `codex/20260803-task37-matrix-free-iterative-development` |
| worktree | 测试时 dirty；四个实现/测试文件为 unqualified research draft |
| ABI | qualified activation；项目 `.venv`；PETSc `complex128/int32`；同一 Linux 栈 |
| ordinary defaults | unchanged；本轮没有改普通路径语义 |
| previous partial-condensation result | `CONTROLLED_NEGATIVE_NUMERICAL_AT_R7B2B1_COMPLEMENT_GATE` |

四个实现文件的 SHA256 是本次 dirty carrier 的精确身份：

| 文件 | SHA256 |
|---|---|
| `static_factor_free_slab_pc.py` | `f1fe04903d29d4ee95ecd624165c15e383edd8e494ccb77e46fdef855a69e5b4` |
| `static_trace_auxiliary.py` | `9b9ee24a571dc1de0e51e626b1dca2b675173d611ca93620b56126e7dfc5d650` |
| `static_p4_capacity_oracle.py` | `94a3079dfcd3a6a5a8e4299b24e4252818da8b50cdb28d0b700aef88db6e2271` |
| `test_246_task037_p4_capacity_oracle.py` | `dda2a0684128af0e9735b171eba6f80a8abb151487a7610c4b3fc0c15979ddda` |

## Static 与 serial 证据

最终静态 Gate 全部通过：Ruff check、Ruff format-check、四文件 compileall、`git diff --check`。最初 format-check 的不一致只是机械排版，已单独修正，不是数值 Gate。

唯一 pytest 命令是在同一 qualified shell 中执行：

```text
/usr/bin/time -v python -m pytest -q -s -x \
  src/test/test_246_task037_p4_capacity_oracle.py::test_f0_degree_pairs_preserve_floquet_orientation_identity \
  src/test/test_246_task037_p4_capacity_oracle.py::test_f0_p4_capacity_oracle_and_d0_comparison
```

| 结果 | 值 |
|---|---:|
| exit | `1` |
| pytest summary | `1 passed, 1 failed` |
| wall | `18.65 s` |
| MaxRSS | `287000 kB` |
| swap | `0` |

第一项真实 degree-pair Floquet/orientation 测试通过：

| 指标 | measured |
|---|---:|
| P24→P46 composition error | `3.512063090206927e-15` |
| P24 interpolation error | `8.326653945790752e-16` |
| P46 interpolation error | `6.595217588690049e-15` |
| P24 adjoint error | `1.1106734086056049e-15` |
| P46 adjoint error | `2.6080775955612308e-15` |
| nonzero orientation counts | P24/P46 = `21/21` |
| Floquet phase x | `0.8541859931542107-0.5199675846619236j` |
| Floquet phase y | `0.818001826003227+0.5752156227497531j` |

## 唯一失败与未执行 Gate

第二项 capacity test 在 oracle 构造前失败，原因是 PETSc 的索引 ABI 是 int32，而测试传入了 numpy int64：

```text
TypeError: Cannot cast array data from dtype('int64') to dtype('int32') according to the rule 'safe'
```

位置为 `src/test/test_246_task037_p4_capacity_oracle.py:113`，调用
`diagonal.getValues(p6_rows)`。潜在最小修复只是把该索引对齐到
`PETSc.IntType`；本轮没有实施，也没有重跑。

因此以下数据均为 `not_run_by_implementation_gate`：

| 项目 | 状态 |
|---|---|
| projected-action error | not run |
| B4 closure | not run |
| F rho / improvement | not run |
| p4 rows / matrix NNZ / factor NNZ / LU payload / bytes | not run |
| high/mixed `>=1.5` Gate | not run；不得写成 `P4_INTERMEDIATE_SPACE_NOT_EFFECTIVE` |
| F1、MPI8 screen20/100/200、PDE | `not_run_by_f0_gate` |

F0 的设计库存仍要求 p6 retained matrix/factor/NNZ 为 `0/0/0`；由于失败发生在 capacity oracle 创建前，本轮没有新的 capacity inventory 数值。MaxRSS 只代表这个 serial test 进程，不代表 p4 容量或正式 PDE 内存。

## Candidate D 冻结对照

Candidate D 没有重跑，仍是既有冻结负结果：p2 factor count=`2`、factor NNZ=`4608`、p6 matrix/factor/NNZ=`0/0/0`。

| source | rho_B4 | rho_D0 | improvement |
|---|---:|---:|---:|
| low | 0.24599945418880295 | 0.2540230551088513 | 0.9684138870126958 |
| high | 0.24651896436171644 | 0.26531876351572775 | 0.929142594723057 |
| mixed | 0.24612971921817314 | 0.2715867504171219 | 0.9062655628087525 |

F0 不调参、不改阈值、不改变 source/shift/steps，也不重跑。四个实现/测试文件属于 unqualified research draft，不能 selective merge 或称为 production-qualified。
