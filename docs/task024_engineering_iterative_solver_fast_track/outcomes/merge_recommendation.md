# 合并建议

| 内容 | 建议 | 原因 |
|---|---|---|
| Task024 修正文档与小体积 CSV/JSON | yes | 结论已按基线降级，复现证据完整 |
| 独立向量化 CSR 导出函数 | yes | 单元测试及 h=5 MPI=1/4 旧/新逐数组等价通过 |
| CSR 流式审计器 | yes | 支持复杂值、entry 守恒和 rank packet 顺序检查 |
| manual FGMRES runner | research-only | 正确性通过，但尚未达到算法/production gate |
| h=5 ordinary default | no change | 继续使用 Task023 opt-in 工程闭环 |
| h=2/h=1.5 ordinary default | no | 仅低内存可扩展性证据 |
| full p2 AMS/HX / root p1 SPLU 默认配置 | no | 本任务特定实现处于资源边界或负收益 |
| `results/` 大文件 | no | 保持 `.gitignore`，仅本地留存 |

复现基础设施可以合并；h=2/h=1.5 的 m=1 profile 不得以“求解器突破”名义进入普通 solver API。
