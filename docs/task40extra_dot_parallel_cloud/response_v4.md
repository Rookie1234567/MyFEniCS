# Response V4：全分支复用审计与同一次工作站启动准备

本轮只读核对历史，避免重做已经验证或失败的方案，没有新增数值实验。35个当前分支完整树索引；4773个去重代码/正文blob、104291461B全部核验并自动检索，缺失0。专题选定文件另有精读/章节读；不能称全库逐字读完。

| 结论 | 证据及实际边界 | 下一步 |
|---|---|---|
| Task040准确离散全谐波背景逆已有tiny资格 | S2d serial/MPI2残差1.6039e-14/2.1440e-14；非formal物理结果 | 我们只扩展y-only、异质x-z、完整内部RHS与532别名，复用既有凝聚/maps |
| 当前phi5已关闭小p2非零y-wrap缺口 | 真实三维notch原残差1.2852e-13/7.1414e-12 | 高阶、跨ABI、目标尺度仍缺，不能再写全部非零Bloch未测 |
| 端口缩放和对角H已有实现 | 旧340-mode缩放残差通过，但功率/幅值6/12、7/12；fullspace已有对角H | 新缺口限retained接线与同Gauss全DOF tensor-face资格 |
| p4/神经旧路线需保留负历史 | 宏Schur/BLR、固定rank128替代逆、FEINN/GN等已有对应限制 | 不重开同对象参数扫描；不将某路线失败推广到整个方法族 |
| 主线P0–P7仍由本机campaign承担 | main固定c786e87d的ReviewV2、最新response/records高于旧总览 | 自主只读检查远端新push/增量，不依赖用户手动转述 |

与MyFEniCSx_task37_extra准备同一次大型验证，截止2026-10-04 10:07:14 UTC形成workstation-ready材料，由用户执行大运行。当前不保证原尺寸0.7nm的2TB/48h资格；工作站实际ABI、资源、field/checkpoint中断恢复仍需Gate。已有checkpoint为solution-only，并非factor/Krylov全状态恢复。

[完整简明审计](outcomes/repository_reuse_audit_v1.md)；[SHA/path/阅读覆盖](outcomes/records/repository_audit_coverage_v1.json)。未复制104MB正文、原始场或缓存到Git。历史状态保留；production/default无变化；仅compact evidence/docs更新。检查为JSON解析、路径身份、Markdown表格/链接及git diff --check；本轮未跑PDE、full pytest、MPI、CI，GitHub视觉渲染尚未验证，文档渲染Gate保持未完成。
