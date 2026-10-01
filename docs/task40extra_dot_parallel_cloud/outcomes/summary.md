# dot 云端并行研究：阶段记录

## 当前阶段：脚手架建立，实验成绩待单独核验发布

| 对象 | 当前状态 | 数据身份与单位 | 基线与证据 |
|---|---|---|---|
| 独占分支/范围 | 已建立 | 文档身份；无数值单位 | [provenance](../branch_provenance.json) |
| CPU 组件实验 | 本脚手架尚未归档结果 | not_run（指本表未认证任何运行），数值 null | 后续实际 run record；不推断实验通过 |
| 完整 PDE / official R/T/A | 本支线排除 | not_run；无 official result | [task](../task.md) |
| 生产/截断/连续极限/2 TB 资格 | 未授予 | not_run / unknown | 不由局部诊断外推 |

本表是发布时点的结构性占位，不能解读为云端没有任何正在进行的独立工作。后续每项结果以实际运行时间、环境和 hash-bound 证据替换占位，并保留失败和未执行项。

## 交付与审查状态

| 检查或依赖组 | 当前状态 | 下一步 |
|---|---|---|
| Markdown 源码结构 | 简单标题/列表/四列表格，无独立公式 | 远端回读并检查 rendered view |
| GitHub rendered view | 尚未验证 | 如无法访问，保留缺口，不冒称通过 |
| pytest / MPI / Ruff / CI | 未运行；本次无数值源码变更 | 后续对应实验按相关范围验证 |
| compact evidence/docs | 仅范围与身份脚手架 | 接收可复核结果后追加 |
| production core / reusable runner | 本阶段无改动 | 不升级默认 |
| research-only / do-not-merge | 全支线保持研究用途；不整体合并 | 等待独立审阅 |

阶段收口将给出完整结果矩阵、实际值/阈值、资源口径、changed files、测试、局限和下一步；没有测量前不预填“提速”或“通过”。
