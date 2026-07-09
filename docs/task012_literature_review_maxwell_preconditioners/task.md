# CODEX TASK 20260707：Maxwell 周期光栅低内存迭代求解器文献调研与路线设计

## 0. 任务定位

本任务暂不继续实现新的求解器代码。目标是使用 `$academic-research-suite` 做聚焦型文献综述、系统综述和研究问题解决方案收敛，并结合 task008-task011 的已有结果，提出下一阶段最值得投入的求解器/预条件器路线。

当前分支：

```text
codex/20260707-low-memory-ams-hx-iterative-solver
```

建议下一轮分支名：

```text
codex/20260707-literature-review-maxwell-preconditioners
```

本任务目录：

```text
docs/task012_literature_review_maxwell_preconditioners/
├── task.md
├── outcomes/
└── review_report.md
```

本任务是 research / design task。除非发现文档索引小错误，否则不要改 solver 代码。

---

## 1. Academic Research Suite 使用方式

Codex 已安装 `academic-research-suite`。执行本任务时必须显式使用：

```text
Use $academic-research-suite
```

只使用其中的 deep-research 能力：

```text
literature review
systematic review
research question refinement / solution scoping
evidence synthesis
fact checking / source verification
```

不需要论文写作、审稿模拟、投稿回复、完整 research-to-paper pipeline、实验设计、实验执行、统计解释或可重复性实验方案。

推荐启动提示：

```text
Use $academic-research-suite.

Goal: perform a focused literature review and solution scoping for low-memory iterative solvers and preconditioners for complex indefinite 3D time-harmonic Maxwell equations in periodic grating scattering.

Mode: deep-research only. Use literature review, systematic review, and research-question solution scoping. Do not draft a paper. Do not create experiment protocols. Stop after evidence-based solver-route recommendations.

Current problem: DOLFINx/PETSc Nedelec H(curl) FEM, complex refractive index, non-Hermitian indefinite system, x/y Floquet periodic boundaries, z-top/z-bottom DtN/Fourier port with auxiliary modal unknowns, high oblique incidence, official R/T/A from DtN modal amplitudes and volume absorption.

Output needed: literature table, method scorecard, recommended solver/preconditioner routes, physics-custom preconditioner ideas, implementation feasibility, and next minimal task proposal.
```

如果 ARS 自动路由到非 deep-research 流程，重新收窄 prompt 到：

```text
deep-research only; literature review / systematic review / solution scoping only; stop before experiments or manuscript drafting.
```

---

## 2. 背景

项目目前已经完成：

```text
1. direct LU / MUMPS 可作为 official reference，但内存不可扩展；
2. MUMPS-BLR 可在 p=2 h=2 上收敛并复现 R/T/A，但仍属于压缩直接法，内存下降有限；
3. Jacobi / ASM / ILU / local LU / GAMG / FieldSplit 等黑盒 PETSc profiles 没有 production candidate；
4. 低内存 Jacobi-Krylov profiles 内存较低，但 p=2 h=5/h=4 均不收敛；
5. real-valued FE-only hypre AMS/HX 可收敛，但 p=2 h=4 已有明显内存压力；
6. complex hypre AMS 直接路径在当前环境会崩溃；
7. FE-only matrix-free matvec 与 assembled matvec 已验证一致，但尚未接入 Stage 4 MPC / DtN auxiliary / real split。
```

因此下一步不继续盲目调参，而是先从文献中判断哪些方向适合本项目。

---

## 3. 本项目问题定义

文献调研必须围绕本项目的具体物理和数值结构：

```text
3D time-harmonic Maxwell
complex-valued field
complex refractive index / absorption
non-Hermitian and indefinite system
Nedelec H(curl) finite element
periodic grating unit cell
x/y Floquet periodic boundary conditions
z-top/z-bottom DtN / Fourier port boundary
Stage 4 auxiliary modal unknowns
high oblique incidence theta_from_z = 80 deg
small EUV wavelength lambda0 = 13.5 nm
official R/T/A from DtN port modal amplitudes and volume absorption
```

当前 direct reference 主点：

```text
p=2 h=2 nm
R_direct = 0.0013429328462348958
T_direct = 0.5992132294442478
A_direct = 0.3994438377095067
```

调研时必须考虑：complex indefinite Maxwell、H(curl) Nedelec、Floquet periodic + DtN/Rayleigh modal boundary、低内存潜力、DOLFINx/PETSc/hypre/MUMPS 可实现性，以及 R/T/A 可信度。

---

## 4. 必须阅读的已有项目文档

```text
docs/task008_70nm_official_convergence_benchmark/review_report.md
docs/task009_iterative_solver_profile_screening/review_report.md
docs/task010_shifted_maxwell_preconditioner/review_report.md
docs/task011_low_memory_ams_hx_iterative_solver/outcomes/summary.md
docs/task011_low_memory_ams_hx_iterative_solver/outcomes/profile_ranking.md
docs/task011_low_memory_ams_hx_iterative_solver/outcomes/next_decision.md
docs/task011_low_memory_ams_hx_iterative_solver/outcomes/ams_hx_smoke_notes.md
docs/task011_low_memory_ams_hx_iterative_solver/outcomes/matrix_free_matvec_feasibility.md
notes/reference/current_version_boundaries.md
```

必须把已有结果作为约束，不要推荐已经被本项目排除的简单组合。

---

## 5. 文献检索方向

系统检索并总结以下方向：

### 5.1 H(curl) auxiliary-space / Hiptmair-Xu / AMS

关键词：`Hiptmair Xu preconditioner Maxwell`, `hypre AMS time-harmonic Maxwell`, `auxiliary space preconditioner H(curl)`, `Nedelec finite element Maxwell preconditioner`, `complex Maxwell real split AMS`。

重点回答：AMS/HX 对 indefinite time-harmonic Maxwell 是否有效；complex Maxwell 如何处理；高阶 Nedelec 的 auxiliary space 如何构造；AMS 内存瓶颈在哪里；是否有 p-coarsening / low-order auxiliary preconditioner。

### 5.2 shifted Laplacian / shifted Maxwell / CSL

关键词：`complex shifted Laplacian Maxwell preconditioner`, `shifted Maxwell preconditioner Helmholtz Maxwell`, `indefinite Maxwell Krylov preconditioner`。

重点回答：shifted operator 对高频 Maxwell 是否有效；shift 参数如何选；inner solver 用 multigrid、ILU、AMS 还是 DDM；本项目 minimal shifted P + ASM/ILU 失败是否符合文献；是否有 shifted + AMS / shifted + multilevel 组合。

### 5.3 domain decomposition / sweeping / optimized Schwarz

关键词：`domain decomposition time harmonic Maxwell preconditioner`, `sweeping preconditioner Maxwell Helmholtz`, `optimized Schwarz Maxwell equations`, `PML sweeping preconditioner periodic Maxwell`。

重点回答：one-level ASM/RAS 为什么容易失败；two-level coarse space 是否必要；coarse space 如何构造；sweeping/PML preconditioner 是否适合周期光栅单胞；实现复杂度是否超出当前阶段。

### 5.4 modal / Rayleigh / DtN-aware / diffraction-specific preconditioners

关键词：`Rayleigh mode preconditioner diffraction grating`, `DtN preconditioner Maxwell periodic grating`, `Fourier modal preconditioner finite element Maxwell grating`, `hybrid FEM RCWA preconditioner`, `transparent boundary condition preconditioner Helmholtz Maxwell`。

重点回答：是否有 Rayleigh/Floquet mode coarse space 或 deflation；是否有 FEM + RCWA / Fourier modal hybrid preconditioner；是否有 layered background Green's function / transfer matrix preconditioner；是否应显式处理 propagating / near-cutoff diffraction orders；如何结合本项目 DtN auxiliary modal unknowns。

### 5.5 low-rank / deflation / recycling Krylov

关键词：`deflation preconditioner Helmholtz Maxwell plane wave coarse space`, `Krylov recycling Maxwell frequency sweep`, `low rank correction preconditioner diffraction`, `coarse space plane wave Helmholtz preconditioner`。

重点回答：deflation/coarse correction 是否适合少数传播模态主导的问题；能否用已有 Rayleigh modes 构造 Z space；能否用上一频率/上一角度/上一参数解做 recycling；是否适合后续反演。

### 5.6 matrix-free / high-order finite element Maxwell

关键词：`matrix-free Maxwell Nedelec high order finite element`, `sum factorization Hcurl Maxwell solver`, `matrix-free Krylov Maxwell preconditioner`。

重点回答：matrix-free 对内存下降的实际幅度；需要什么预条件器配合；高阶 Nedelec tensor-product 优势是否适合 hexahedron p=2；与本项目 UFL action smoke test 的关系。

### 5.7 compressed direct / BLR / H-matrix fallback

关键词：`MUMPS BLR Maxwell preconditioner`, `H-matrix Maxwell finite element solver`, `hierarchical matrix Helmholtz Maxwell preconditioner`。

重点回答：BLR/H-matrix 是否只是中短期 fallback；为什么本项目 BLR 收敛但内存下降有限；是否有比 MUMPS-BLR 更适合 wave problem 的 H-matrix/HSS/HODLR 方案。

---

## 6. 输出要求

必须输出：

```text
docs/task012_literature_review_maxwell_preconditioners/outcomes/
├── summary.md
├── ars_process_log.md
├── search_queries.md
├── literature_table.csv
├── method_scorecard.csv
├── recommended_routes.md
├── annotated_bibliography.md
├── physics_custom_preconditioner_ideas.md
├── implementation_feasibility.md
├── next_task_proposal.md
├── references.bib
└── changed_files.md
```

不要下载或提交大型 PDF。可以记录 DOI、arXiv、publisher URL。

### literature_table.csv 字段

```text
id,title,authors,year,venue_or_arxiv,url_or_doi,problem_type,method_family,krylov_method,preconditioner,matrix_type_complex_or_real,finite_element_or_discretization,boundary_condition_type,periodic_or_not,high_frequency_or_not,reported_problem_size,reported_memory,reported_iterations,reported_accuracy_metric,implementation_library,relevance_to_this_project,risk_or_limitation,human_read_status
```

`human_read_status` 可取：`abstract_only`, `skimmed`, `read_key_sections`, `full_read`。不得把 `abstract_only` 文献作为强结论依据。

### method_scorecard.csv 字段

```text
method_family,expected_convergence_potential_1_to_5,expected_memory_potential_1_to_5,implementation_difficulty_1_to_5,fit_to_periodic_grating_physics_1_to_5,fit_to_DOLFINx_PETSc_stack_1_to_5,risk_level_1_to_5,recommended_priority,evidence_strength,reason
```

评分必须结合 task009-task011 结果。

---

## 7. summary.md 必须回答

1. 文献中最接近本项目问题的求解路线是什么？
2. 哪些方向已经被本项目实验间接否定或降低优先级？
3. AMS/HX 是否仍值得继续？如何避免内存问题和 complex hypre 崩溃？
4. 是否有文献支持 real/imag split + real AMS？
5. 是否有文献支持 Rayleigh/Floquet mode coarse space、DtN-aware preconditioner 或 FEM-RCWA hybrid preconditioner？
6. shifted Maxwell / shifted Laplacian 是否值得重新做？需要和什么 inner solver 结合？
7. DDM / sweeping 是否适合当前周期光栅单胞？
8. matrix-free 应作为主线还是内存优化层？
9. 是否应暂时停止求解器实现，优先做降阶/等效/RCWA/FEM hybrid？
10. 下一步最推荐的 1-3 个任务是什么？

---

## 8. physics_custom_preconditioner_ideas.md 要求

至少提出三个定制化预条件器想法，并写出：

```text
idea_name
literature_basis
physics_basis
matrix_or_block_form
how_to_apply_preconditioner
expected_memory_cost
expected_convergence_benefit
implementation_steps
risks
minimal_smoke_test
success_criterion
```

至少覆盖：Rayleigh/Floquet modal deflation、DtN-aware FE/aux block preconditioner、layered-background / RCWA-like approximate inverse、low-order or p-coarsened H(curl) auxiliary preconditioner、real-split AMS/HX block preconditioner、matrix-free operator + physics preconditioner。

---

## 9. next_task_proposal.md 要求

最后必须提出下一轮最小可执行任务，而不是泛泛建议：

```text
Recommended next task: Task013 ...
Why this one first:
Inputs needed:
Implementation scope:
Test cases:
Success criteria:
Stop criteria:
Expected time/risk:
```

如果文献调研认为不应继续实现求解器，也要明确提出替代路线，例如 RCWA/FEM hybrid benchmark、reduced-order surrogate、parameter sweep with BLR fallback 或 mesh/model simplification。

---

## 10. 禁止事项

```text
1. 不要继续新增求解器 profile 并跑大算例；
2. 不要在没有文献依据的情况下继续硬推 real-split AMS；
3. 不要只罗列论文标题，必须结合本项目结果做判断；
4. 不要把 general Helmholtz 结论直接套到 H(curl) Maxwell，除非解释差异；
5. 不要把未验证或未读过的文献写成已确认结论；
6. 不要输出论文大纲、摘要、投稿计划、审稿模拟、实验计划或统计分析方案。
```

---

## 11. 最终预期

本任务完成后，我们应获得一份研究路线图，回答：

```text
在周期光栅 3D Maxwell + Floquet + DtN port + complex Nedelec FEM 问题上，
下一步最值得投入的是哪一种或哪几种求解器/预条件器路线，
哪些路线应暂停，
每条路线的文献依据、实现难度、内存前景和最小验证实验是什么。
```
