# 下一步决策

## 当前顺序

1. ChatGPT 审查 `response_v2.md`、五层文档、13 个 benchmark 和 87 项 Gate。
2. 用户本地拉取并检查提交。
3. 只有用户明确同意后，才把本分支合并到 `master`。
4. Task028 合并决定前，不启动 Task029 或新求解器研究。

## 最终审查重点

| 优先级 | 项目 |
|---|---|
| P0 | 有耗 complex `beta` 传播判定和实际端口面功率公式 |
| P0 | official auxiliary / trace / A_volume 与 diagnostic probe 身份 |
| P0 | 15 个 preset 的安全默认和真实 parser contract |
| P0 | h3/h2 actual source 与 canonical rerun provenance 分离 |
| P0 | 13 个 benchmark 是否准确声明“证明/不证明” |
| P1 | 五层文档交叉链接是否足以让新用户从运行进入理论和代码 |
| P1 | 87/87 Gate 对物理模型、KSP、coarse、RSS 和 commit relation 的覆盖 |
| P1 | `qualified_local_image` 限定是否充分诚实 |

## 后续研究候选

未来重新开启研究时，优先做固定 profile 的物理网格收敛和角度/波长/材料小范围鲁棒性矩阵，再讨论 h=1.5、near-Rayleigh 和更强 multilevel H(curl) 方法。不要恢复无 Gate 的盲目参数扫描。
