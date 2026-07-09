# REVIEW REPORT 20260707：Task012 Maxwell 周期光栅低内存迭代求解器文献调研与路线设计

## 1. 审查对象

审查分支：

```text
codex/20260707-literature-review-maxwell-preconditioners
```

任务目录：

```text
docs/task012_literature_review_maxwell_preconditioners/
```

重点阅读文件：

```text
outcomes/summary.md
outcomes/literature_table.csv
outcomes/method_scorecard.csv
outcomes/recommended_routes.md
outcomes/physics_custom_preconditioner_ideas.md
outcomes/implementation_feasibility.md
outcomes/next_task_proposal.md
outcomes/annotated_bibliography.md
notes/theory/maxwell_iterative_preconditioners_task012.md
```

本轮是 literature review / route-design 任务，不审查新 solver 代码正确性。

---

## 2. 总体结论

Task012 通过。它完成了本轮最需要的工作：停止继续盲目添加 PETSc profiles，把 task008-task011 的本地数值证据和 Maxwell/H(curl) 迭代求解器文献放在一起，给出下一步路线排序。

本报告建议合并 task012 文档成果，但要注意两点：

```text
1. task012 给出的 Task013 推荐不能理解为“AMS/HX 已经可用”；
2. Task013 应被定义为 qualification / go-no-go 任务，而不是 production solver 实现任务。
```

如果 Task013 最终失败，没有得到有效收敛或内存改善，则建议不合并复杂 solver 代码，只保留必要的结论记录或直接丢弃实验分支，避免主线代码复杂化。

---

## 3. 文献调研质量审查

Task012 的调研覆盖了主要相关方向：

```text
1. H(curl) auxiliary-space / Hiptmair-Xu / hypre AMS；
2. shifted Maxwell / complex shifted Laplacian；
3. domain decomposition / optimized Schwarz / sweeping；
4. Rayleigh/Floquet modal deflation 与 DtN-aware block preconditioner；
5. matrix-free high-order Maxwell；
6. BLR / H-matrix fallback；
7. RCWA/Fourier modal / layered-background approximate inverse。
```

`literature_table.csv` 不只是罗列标题，还包含 method family、matrix type、discretization、boundary condition、reported size、memory、iterations、relevance、risk 和 human_read_status。这个结构符合 task012 要求。

较强相关文献包括：

```text
Fressart2025：time-harmonic Maxwell 并行求解器比较，涵盖 HX/AMS、RAS、BLR；
HiptmairXu2007 与 KolevVassilevski2009：H(curl) auxiliary-space / AMS 理论和实现基础；
hypre AMS 与 PETSc PCHYPRE 文档：工程接口依据；
Bonazzoli2017 与 Beuchler2021：high-frequency Maxwell、real/imag block、DDM/block PC；
Jiang2018：biperiodic Maxwell DtN 与 Rayleigh/Floquet modal boundary；
Li1996 / RCWA 相关文献：layered-background approximate inverse 的长期启发。
```

这些文献与本项目直接同构程度不同，文档中基本保持了诚实区分，没有把 Helmholtz 或 RCWA 结论直接等同于本项目的 H(curl) Maxwell + Floquet + DtN auxiliary 系统。

---

## 4. 路线排序审查

`method_scorecard.csv` 给出的优先级为：

```text
1. real-split AMS/HX + low-order or p-coarsened auxiliary；
2. Rayleigh/Floquet modal deflation；
3. DtN-aware FE/aux block preconditioner；
4. layered-background / RCWA-like approximate inverse；
5. matrix-free A + physics preconditioner；
6. shifted Maxwell + AMS or two-level DD；
7. two-level DDM / optimized Schwarz / sweeping；
8. BLR / H-matrix fallback；
reject: Jacobi/ASM/ILU/local LU/GAMG/BoomerAMG black-box profiles。
```

这个排序总体合理。

需要强调的是：

```text
real-split AMS/HX 排第一，不是因为它已经证明低内存可靠，而是因为它是最小工程闭环：task011 real FE-only AMS 有正信号，complex AMS 直接路径失败，所以 real-split 是最自然的 qualification。
```

Rayleigh/Floquet modal deflation 和 DtN-aware block PC 更贴合本项目的周期光栅物理，但实现入口更不确定，所以排在 Task014/Task015 更合理。

---

## 5. 对 Task013 推荐的审查

Task012 推荐：

```text
Task013：real-split AMS/HX block preconditioner minimal prototype
```

这个方向可以继续，但必须收窄任务语义：

```text
Task013 = qualification / go-no-go test
不是 production low-memory solver task。
```

Task013 应先回答：

```text
1. complex matrix -> real block system 的数学一致性是否正确；
2. real AMS/HX 能否作为 blockdiag PC 稳定 apply；
3. true residual 是否明显优于 Jacobi-Krylov；
4. p=2 的 AMS auxiliary hierarchy 内存是否可控；
5. low-order / p-coarsened auxiliary 是否能缓解 p=2 内存压力。
```

只有在小算例和 reduced Stage 4 顺利后，才允许进入完整 Stage 4 `p=2 h=2`；只有 `p=2 h=2` 成功且内存低于 direct/BLR，才允许尝试 `p=2 h=1.5` stress/breakthrough test。

---

## 6. 需要防止的误读

### 6.1 不要把 FE-only smoke 等同于 Stage 4 solver

Task011 的 real AMS 正结果来自 FE-only positive Maxwell block，不含完整 Floquet MPC、DtN auxiliary、complex material cross coupling 和 official R/T/A。Task012 已经意识到这一点。后续所有报告仍必须保持这个边界。

### 6.2 不要把 RCWA-like approximate inverse 提前实现

RCWA / layered-background approximate inverse 是长期高潜力路线，但当前用户暂不希望引入半解析解。Task013 不应包含 RCWA 实现。

### 6.3 不要把 matrix-free 当成收敛方案

matrix-free 只能减少 A 的存储，不改善不定 Maxwell 的谱。必须等物理 PC 有收敛信号后，再作为内存优化层接入。

### 6.4 不要把 BLR 当最终答案

BLR 已经是可信 fallback，但内存下降有限，不应作为最终低内存迭代路线。

---

## 7. 合并建议

Task012 文档成果建议合并，因为它是纯调研/路线设计，能给后续任务提供决策依据。

但对 Task013 以及之后的代码分支，建议采用 gated merge policy：

```text
1. 若 Task013 只产生复杂代码但没有收敛或内存改善，不合并 solver 代码；
2. 若 Task013 失败但产生有价值的负结果，可只提交精简 review/outcomes 文档，或单独保存在实验分支；
3. 若 Task013 成功证明 p=2 h=5/reduced Stage 4 显著优于 Jacobi，且 p=2 h=2 full Stage 4 有可解释结果，才考虑合并最小必要代码；
4. 合并前必须清理实验脚本、调试输出和临时 profiles，避免主线膨胀。
```

这个策略与用户当前目标一致：主线保留可信结果，不把失败的复杂实验代码强行并入。

---

## 8. 下一步任务建议

建议将下一步任务写为：

```text
Task013：real-split AMS/HX qualification with full Stage 4 gated breakthrough test
```

核心分阶段：

```text
Stage A：FE-only real block equivalence and AMS smoke；
Stage B：p=2 h=5 FE-only AMS/HX qualification and memory audit；
Stage C：low-order / p-coarsened auxiliary memory test；
Stage D：reduced Stage 4 p=1/h=5 or p=2/h=5 diagnostic；
Stage E：full Stage 4 p=2 h=2 only after A-D pass；
Stage F：full Stage 4 p=2 h=1.5 breakthrough test only after h=2 pass。
```

明确不包括：

```text
RCWA-like inverse；
Rayleigh/Floquet modal deflation full implementation；
matrix-free Stage 4 MatShell；
large p=2 h=1.0 run；
new black-box PETSc profile sweep。
```

---

## 9. 最终结论

```text
task012 通过；
建议合并文档成果；
推荐 Task013 继续 real-split AMS/HX，但必须作为 qualification / go-no-go 任务；
小算例成功后可加入 full Stage 4 p=2 h=2 和 p=2 h=1.5 的 gated breakthrough test；
若 Task013 没有有效结果，建议不合并复杂 solver 代码，以免主线过度复杂。
```
