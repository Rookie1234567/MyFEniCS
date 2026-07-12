# REVIEW REPORT V1 20260710：Task024 engineering iterative solver fast track

## 1. 审查状态

```text
review_status = provisional_fail
primary_blocker = remote reproducibility
merge_code = no
merge_docs = conditional
production_default_change = no
```

Task024 提供了有价值的低内存运行证据：目标模型 p=2 h=2 和 h=1.5 均完成了 FE-response / reduced outer 计算，报告峰值 RSS 分别约 4.47 GB 和 8.57 GB。但当前远程分支无法从已提交代码复现这些结果，因此本报告暂不批准代码合并，也不接受“Task024 已形成可复现工程求解器”的结论。

---

## 2. 可以暂时接受的证据

在不考虑远程复现问题时，现有 outcomes 支持以下暂定判断：

```text
1. Task023 的 h=5 PETSc FE-response + Schur + official R/T/A 闭环仍成立。
2. Task024 证明百万级 p=2 FE 系统可以在 14 GB 内完成数据导出和低内存迭代原型运行。
3. h=2 与 h=1.5 的 dominant DtN mode / FE-response 路线可以产生非零残差下降。
4. full p2 AMS/HX hierarchy 在当前 14 GB 配额下进入资源边界。
5. 当前 p1 root SPLU coarse correction 性价比为负，删除后内存明显下降。
6. 向量化 CSR 导出是值得保留的工程改进候选。
```

但这些结论都必须在完整远程代码可复现后重新确认。

---

## 3. 第一阻塞项：远程 runner 不完整

Task024 文档声称：

```text
src/studies/run_task024_engineering_iterative_solver.py
```

包含：

```text
real-split AMS/GMG funnel
native PETSc MatNest
manual right-preconditioned FGMRES
strict m=1 outer residual
vectorized CSR export
MPI collective fix
```

但当前远程文件只包含 imports、少量常量和目录定义，没有上述核心实现、CLI、main entry、FGMRES、导出器、AMS/GMG 或 residual reconstruction 代码。

因此现状是：

```text
outcomes exist
full producing source does not exist remotely
```

这属于严重可复现性缺陷。Codex 必须先解决这一问题，不得继续新增算法结果掩盖代码缺失。

---

## 4. Codex 必须完成的远程代码修复

### 4.1 提交完整实现

必须将实际生成 Task024 outcomes 的完整代码提交到当前执行分支，包括：

```text
manual right-preconditioned FGMRES
PETSc MatNest real-split construction
complex 2x2 weighted Jacobi apply
particular FE solve
selected FE-response solve
m=1 reduced outer least-squares correction
full true residual reconstruction
MPI-safe collective calls
vectorized CSR exporter
AMS/HX and GMG-lite experiment paths
h=2 / h=1.5 run entry points
```

如果核心实现分散在其他本地文件中，必须一并提交并在 runner 中显式 import。禁止依赖未提交的本地脚本、临时 notebook 或手工修改容器文件。

### 4.2 基础可执行检查

远程代码提交后必须通过：

```text
python -m py_compile <all Task024 source files>
python -m src.studies.run_task024_engineering_iterative_solver --help
```

并记录完整命令、容器镜像、complex mode、MPI ranks 和工作目录。

### 4.3 干净环境复现

必须从干净 checkout 或新容器执行至少三个最小复现实验：

```text
A. h=5 small/short manual FGMRES smoke
B. h=2 20-step response + m=1 outer residual
C. vectorized CSR export equivalence on h=5 MPI=4
```

不得复用旧 results 中的 NPZ、CSR、response cache 或 residual 文件，除非命令明确标记为 cache-replay test。

每次运行必须把以下内容写入 metadata：

```text
git commit SHA
Docker image
MPI ranks
PETSc scalar type
command line
input cache hashes, if any
output file hashes
```

---

## 5. 第二阻塞项：minimum gate 的基线定义不充分

Task024 报告 h=2：

```text
true outer residual = 0.15859
improvement_vs_zero = 6.31x
```

这里的 improvement 是相对零解残差 1.0，而不是相对已有迭代 baseline。

Task022 已有 h=2 baseline：

```text
GCROT/Jacobi, 20 history points
true residual = 0.163120
```

因此 Task024 的 `0.15859` 相对该 baseline 仅约 `1.029x`，改善约 2.8%。它不能按“6.31x”解释为求解器突破。

Codex 必须新增同预算、同残差定义的基线表：

```text
zero solution residual
particular FE-only residual
Task022 GCROT/Jacobi baseline
Task024 manual FGMRES without selected response
Task024 manual FGMRES + m=1 response
```

至少比较：

```text
same mesh
same MPI ranks
same wall-time budget or same matvec count
same true residual definition
same initial guess policy
```

在完成该对照前，Task024 h=2/h=1.5 应标记为：

```text
low-memory scalability evidence
not solver breakthrough
```

---

## 6. 第三阻塞项：manual FGMRES 正确性验证

Task024 使用手工实现的 right-preconditioned FGMRES。该实现是关键新代码，必须单独验证。

Codex 必须提供：

```text
1. 小型复数矩阵上与 SciPy/PETSc FGMRES 或 GMRES 的解和 residual 对照。
2. h=5 FE block 上，相同 preconditioner、相同步数下与 PETSc KSP 的 residual history 对照。
3. Arnoldi orthogonality error。
4. Hessenberg least-squares residual 与显式 true residual 的差异。
5. right-preconditioning reconstruction x = x0 + Z y 的单元测试。
6. MPI=1/4 residual consistency。
```

必须确认所有 rank 都参与 `Vec.norm`、dot 和 reduction，避免再次出现 rank0-only collective deadlock。

---

## 7. 第四阻塞项：残差和“求解器”含义必须区分

当前 Task024 的最终结果不是完整 80-aux outer Krylov solve，而是：

```text
particular FE approximation
+ one selected response column
+ one complex least-squares coefficient
```

即：

```math
x(\alpha)=\begin{bmatrix}y\\0\end{bmatrix}
+\alpha\begin{bmatrix}q_j\\e_j\end{bmatrix}.
```

因此它应称为：

```text
m=1 reduced FE-response approximation
```

而不是完整工程迭代求解器。

Codex 必须在 summary、gate、ranking 和 README 中统一使用准确名称，并区分：

```text
FE response cancellation
zero-solution one-shot residual
particular FE residual
selected outer true residual
full 80-aux iterative residual
```

未收敛配置不得输出 official R/T/A。

---

## 8. 向量化 CSR 导出审查要求

向量化导出让 h=1.5 从失败变为可完成，是有价值的改进，但合并前必须提供：

```text
1. h=5 MPI=1/4 旧导出与新导出的逐数组等价测试。
2. indptr 单调性、indices 范围、nnz 一致性测试。
3. FE/aux entry filtering 数量守恒。
4. complex values 完整保留。
5. h=2/h=1.5 不依赖 rank 顺序的重构测试。
6. peak RSS 和 wall time 对比。
```

该导出器建议独立成可测试函数，不应只藏在 Task024 runner 内。

---

## 9. AMS/HX、GMG-lite 与算法结论

现有证据支持：

```text
full p2 AMS/HX: current 14 GB workstation resource boundary
p1 root SPLU coarse: current formulation negative value
native MatNest + block Jacobi: low-memory but weak FE inverse
```

但不能扩大解释为：

```text
all AMS/HX routes fail
all GMG routes fail
coarse spaces are useless
```

Task024 只测试了特定 full-p2 AMS hierarchy 和简化 p-coarsening/root-SPLU coarse correction，不等价于完整 COMSOL-style h-GMG。

当前下一步可以快速测试 m=2/4 response cache，但只有在远程复现修复完成后进行。

---

## 10. 修复后的重新判定 Gate

### Reproducibility gate

必须全部通过：

```text
complete remote source present
py_compile pass
--help pass
clean-container smoke pass
h=5 export equivalence pass
h=2 20-step result reproduced within tolerance
commit SHA recorded in outcomes
```

### Algorithm gate

不再用相对零解的 improvement 作为主要成功指标。

建议：

```text
minimum signal: residual at least 2x better than equal-budget existing baseline
strong: true residual <= 0.1 and meaningfully better than equal-budget baseline
production-like: true residual <= 1e-6 plus official R/T/A
```

若 m=2/4 相对 m=1 改善小于 10%，停止增加 auxiliary modes，转向更强 FE inner solve。

---

## 11. Merge recommendation V1

```text
Task024 docs/outcomes: retain on research branch
Task024 source code: no merge until reproducibility gate passes
vectorized CSR exporter: eligible only after isolated tests
manual FGMRES: research-only until correctness tests pass
h=2/h=1.5 profile: not production, not default
h=5 Task023 opt-in profile: unchanged
```

---

## 12. Codex 下一次提交必须回答

```text
1. 完整 Task024 runner 和依赖是否已提交？
2. 哪个 commit 能从干净 checkout 复现 outcomes？
3. h=2 20-step residual 是否能从零缓存复现？
4. manual FGMRES 是否与 PETSc/SciPy 对照通过？
5. improvement 相对 equal-budget baseline 是多少，而不是相对零解多少？
6. 向量化 CSR 导出测试是否全部通过？
7. 哪些 Task024 结论需要因基线修正而降级？
```

---

## 13. 最终 V1 结论

Task024 展示了重要的低内存基础设施进展，并提供了 h=2/h=1.5 可运行证据；但当前远程仓库缺少实际生成这些结果的完整核心代码，且“6.31x improvement”使用零解作为基线，容易高估算法效果。因此本轮审查暂不通过。Codex 的下一步不是继续扩展 m=2/4，而是先补齐完整远程实现、干净环境复现、manual FGMRES 正确性测试和同预算 baseline。完成这些修复后，再生成 `review_report_v2` 重新判断 Task024 的科学与工程价值。
