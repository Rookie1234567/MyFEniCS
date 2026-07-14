# Task032 入口

## 执行顺序

```text
1. 先将 Task031 按 review_report_v2.md 合入 master
2. 在 master 上运行轻量 contracts/checker
3. 记录 Task031 merge SHA
4. 保留旧本地目录为只读历史基线
5. 在 C:\Users\admin\Desktop\Code\fenics_v3_hybrid_FEM_modal 建立新的 clean clone
6. 从最新 origin/master 创建 codex/20260714-task32-hybrid-fem-modal-direct-baseline
7. 读取 task.md 和 Hybrid 理论笔记
8. 先完成本地迁移 Gate，再开始写 Hybrid solver code
```

## 文件

- [Task032 任务书](task.md)
- [项目服务需求与技术路线](../project_service_requirements_and_forward_model_roadmap.md)
- [第一阶段冻结范围](../project_service_requirements_phase1_scope.md)
- [Hybrid FEM–Modal 理论笔记](../../notes/theory/hybrid_fem_modal_domain_decomposition.md)
- [Task031 最终审阅](../task031_compact_physical_slab_memory_optimization/review_report_v2.md)

## 核心边界

```text
wavelength = 13.5 nm
material = fixed validated Si
geometry = current regular periodic structure
angles = 1–10 deg grazing parameterization smoke
polarization = S/P
direct solver only
no h/p adaptivity
no new iterative solver
no 0.7 nm
```

Task032 的第一目标是证明中间 z 不变区可以由二维截面模式可靠替代；第二目标才是评估 h2 Hybrid direct 是否进入 2–5 GiB 范围。
