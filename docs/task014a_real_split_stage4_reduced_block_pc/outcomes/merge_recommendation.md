# Merge Recommendation

## 判断

```text
merge_code: no
merge_docs_only: yes / optional
```

## reason

本轮实验代码完成了 isolated qualification：

| 项目 | 结果 |
|---|---|
| Stage4 real split 等价性 | 通过 |
| normal-incidence real-mode MPC 系数兼容 | 通过 |
| MPC 后 same-H1 AMS 数据构造 | 通过 |
| FE-AMS + aux identity | 可运行 |
| p1 h5 主 case 收敛表现 | 未达到通过门槛 |
| p2 h5 optional | 未运行 |
| official R/T/A | 未输出 |

因此当前代码还不应进入 production solver。它是研究脚本，不是正式 Stage4 求解路径。

## minimal_files_to_merge

如果只合并文档，可合并：

```text
docs/task014a_real_split_stage4_reduced_block_pc/outcomes/
notes/theory/maxwell_iterative_preconditioners_task012.md
```

## files_to_keep_on_research_branch

```text
src/studies/run_stage4_real_split_block_pc.py
src/constraints/floquet_3d.py
```

其中 `floquet_3d.py` 的改动是 real-mode normal-incidence MPC 兼容层；它有价值，但仍建议等下一轮确认是否纳入正式代码。

## files_to_drop

暂无必须删除的文本文件。`raw_runs/` 中的 `.npz/.h5/.xdmf` 二进制中间件已删除，只保留轻量 metadata、progress 和 JSON 结果。后续若进入大矩阵，仍应避免提交 matrix dumps。

## risks_if_merged

| 风险 | 说明 |
|---|---|
| 用户误以为 production solver 已完成 | 实际只是 qualification runner |
| real-mode MPC 兼容层使用范围有限 | 只允许纯实 Floquet phase；oblique complex phase 会显式报错 |
| 当前 FE-AMS profile 太弱 | default100 auto 只改善约 1.60x，不能作为正式求解器 |
| 没有 R/T/A | 未收敛时按规则不输出物理量 |

## recommended_next_branch_or_same_branch

```text
继续当前研究分支或新开 task015 分支；
下一步不进入 master，不进入 full p2 h2。
```
