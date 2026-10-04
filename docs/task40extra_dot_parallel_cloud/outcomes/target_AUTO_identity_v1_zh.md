# 原始尺寸 AUTO 端口清单已固定

本次在独立云分支以原始 50×25×140 nm 几何、λ=0.7 nm、θ=89°、φ=0°和 p6 配置调用原有 AUTO 生成器与物理清单函数。完整有序清单通过，尚未构造网格、编译表面形式或求解 PDE。

| 实测项目 | 结果 |
|---|---:|
| 全部模式 | 32,060 |
| top / bottom | 各 16,030 |
| 分类 | 全为 propagating；evanescent、near-cutoff 均为 0 |
| 最大绝对阶数 m / n | 142 / 35 |
| 由完整清单确定的 p6 表面求积 degree | 160 |
| 监督总耗时 | 8.306 s |
| 生成器与原始物理清单的 worker 区段 | 6.490 s |
| 采样进程树峰值 RSS | 495,730,688 B |
| swap / 后代清理 | 0 / 已清理 |

完整 indexed-key SHA256 为 `08d7464c448a75bd5f41986f726ae0f97484cc050891dcfaaa24efc5f2900899`；物理 manifest SHA256 为 `7dd07d7145c70759f53465b6ec11237a89effdf7d68a0df6423768858639c56e`。清单在原始标量 H 的计算之前保存，原始函数仍完成了全部有限正值检查。top 的 global-z log-magnitude 为 0，bottom 约为 −0.044751 至 −0.000388；该实际配置没有指数溢出。这个结论不能推广到另一个 evanescent 清单。

执行源为本地 `6dba8257`，tree `63313e3f`，发布提交另记。17 个集成 metadata/config/几何/API 测试与 12 个 reference 源/API/合成测试通过；独立审阅覆盖 metadata source/launcher，表面数值阶段仍单独待审。

完整 37,626,630 B 数据压缩为 4,893,317 B，保存到 Library，并从新目录取回核对全部 10 个 ZIP 成员。Library 身份 `libfile_01b478e1d1f48191bea7c9deea966423`、version 0；[精确读回凭据](records/target_AUTO_identity_v1/library_readback_receipt.json)和[紧凑结果](records/target_AUTO_identity_v1/compact.json)保留全部哈希与回收入口。

下一步仅测原始几何的一个 p6 top/x 形式及三个实际元组 `(0,0)`、`(-142,-5)`、`(-85,-35)` 的两种极化。primary degree160 的名义节点数为 6561，独立 +8/+16 求积名义节点数为 7225/7921；实际 compiled Gauss 与 public rule 身份待验证。18 个三维六面体是边界/编译夹具，不能作为精度合格网格。

表面阶段尚未运行。冷编译真实峰值、完整 C/D 构造与缓存、因子 fill、全 p6 反演、官方输出、网格与端口收敛，以及整机 2×10¹² B / 172800 s 目标均未得到资格。既有小尺度 p4/manual532 all-q 反演与保存矩阵优化资格保留原有范围。
