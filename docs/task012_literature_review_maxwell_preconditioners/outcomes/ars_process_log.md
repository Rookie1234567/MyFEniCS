# ARS 过程记录

## 使用方式

本轮按任务书要求使用 `$academic-research-suite`，并只采用 deep-research 路线中的以下能力：

```text
literature review
systematic review
research question refinement / solution scoping
evidence synthesis
fact checking / source verification
```

Codex 当前会话中没有单独可调用的 ARS agent tool；因此按 `academic-research-suite` 的 Codex adapter 说明，以内联方式执行 deep-research workflow。未调用外部模型，未上传私有材料。

## 研究范围

研究问题收敛为：

```text
在 DOLFINx/PETSc Nedelec H(curl) 3D time-harmonic Maxwell、
complex refractive index、Floquet x/y 周期边界、
z-top/z-bottom Fourier-DtN auxiliary modal port、
80 deg 斜入射和 official R/T/A 后处理口径下，
下一步最值得实现的低内存迭代器与预条件器是什么？
```

## ARS 阶段映射

| ARS 阶段 | 本轮执行内容 | 输出文件 |
|---|---|---|
| Research question refinement | 把“找可用迭代求解器”约束到 complex indefinite H(curl) Maxwell + Floquet/DtN + low memory | `summary.md` |
| Bibliography | 检索 AMS/HX、shifted Maxwell、DDM、biperiodic DtN、RCWA、deflation、matrix-free、BLR/H-matrix | `search_queries.md`, `literature_table.csv`, `references.bib` |
| Source verification | 区分官方文档、arXiv、期刊页、项目本地结果；标注阅读状态 | `annotated_bibliography.md` |
| Evidence synthesis | 把文献与 task008-task011 数值结果交叉综合 | `summary.md`, `recommended_routes.md`, `method_scorecard.csv` |
| Devil's advocate | 检查是否把 Helmholtz 结论硬套到 Maxwell、是否夸大 AMS smoke、是否过度声称 Rayleigh deflation | `recommended_routes.md`, `implementation_feasibility.md` |

## 纳入与排除标准

纳入：

- time-harmonic Maxwell、H(curl)、Nedelec、edge elements。
- auxiliary-space / Hiptmair-Xu / hypre AMS。
- shifted/absorbing Maxwell 或 shifted Laplacian 与 Maxwell 关系。
- domain decomposition / optimized Schwarz / sweeping 中与 Maxwell 或 high-frequency Helmholtz 强相关的内容。
- periodic grating、biperiodic structure、DtN、Rayleigh/Floquet modal、RCWA/Fourier modal。
- low-rank/BLR/H-matrix fallback。

排除或降权：

- 纯 Poisson/elliptic AMG 文献，除非说明 H(curl) 辅助空间关系。
- 纯 Helmholtz 结论，除非明确标注与 Maxwell 的差异。
- abstract-only 且未能与本项目已有实验互相支持的强结论。

## 质量边界

- `human_read_status=read_key_sections` 的来源可以作为主要依据。
- `abstract_only` 的来源只用于提示方向或补充背景，不作为强结论。
- 本轮没有访问 Web of Science 的完整元数据导出；使用 arXiv、官方文档、DOI/期刊页、项目本地文档交叉核验。
- 文献调研输出不是论文综述，而是下一轮 solver 设计依据。
