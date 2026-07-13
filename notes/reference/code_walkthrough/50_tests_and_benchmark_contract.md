# 测试与 Benchmark 契约

## 自动测试层

| 编号 | 主题 |
|---|---|
| 00-03 | 单位、平面波、PML tensor、Fresnel |
| 04-10 | 3D Stage1/2 PDE、Floquet、PML、Fresnel 组合 |
| 11-17 | diffraction、orientation、entrypoint、DtN、mesh、2D EUV、p2 trace |
| 18-19 | direct profiles 与 OOC cleanup |
| 20 | 2D lossy DtN 传播级与实际端口平面功率 |
| 22 | exact condensation |
| 23 | physical slab two-level/MPI/sm2 |
| 24 | 仓库工作原则 |
| 25 | benchmark manifest/record/Gate 基础契约 |
| 26 | 文档索引、链接、case 结构契约 |
| 27 | main preset/parser/default/iterative 隔离契约 |

测试号 21 仍为空缺，是历史任务清理结果；不为连续编号而塞入无意义测试。

## Benchmark 三层

| Level | 内容 | 成本 |
|---|---|---|
| 1 | compile、unit、2D zero contrast、3D Stage1 MPI2 | 轻量 |
| 2 | condensation、physical slab MPI4、checker | 轻量/中等 |
| 3 | target direct 与 workstation iterative | 重型 |

## case 文档契约

每个 `benchmarks/cases/NNN_*/README.md` 冻结：证明/不证明、物理、几何、材料、波长/角度/偏振、边界、FE/mesh、preset、参数表、精确命令、调用链、理论、solver、RTA、输出、Gate、结果、record、artifact、限制。

## checker

`check_benchmarks.evaluate` 从 manifest 载入 records 和 expected gates，检查身份、canonical config、物理模型、residual、KSP、coarse、RTA、direct/iterative 差、RSS、环境和 ordinary default。`--no-write` 不改变 report；普通写模式刷新 summary/report，此时 checkout dirty 只表示 checker 输出已被改写，不等于源 record 运行时 dirty。

## 运行策略

代码改动先 compile + focused tests，再 full unit/MPI，最后按风险决定 Level3。文档/metadata Task28 V2 不要求重跑 h=2；历史 record 可补 provenance/physical model，但不得篡改数值。
