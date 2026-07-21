# Task034：工作站 WSL、自适应与资源重校准

Task034 从包含本目录任务书的最新 clean `origin/master` 开始，由 Codex 在工作站 WSL Ubuntu 中创建执行分支：

```text
codex/20260717-task34-workstation-wsl-adaptive-scalability
```

执行权威：

- [`task.md`](task.md)：WSL 迁移、hardening、p3/h3、p4、自适应、资源 Gate 和交付要求；
- [`task_fixed_geometry_convergence_addendum.md`](task_fixed_geometry_convergence_addendum.md)：正式补充权威；要求 adaptive 之前先完成固定结构 p2/p3/p4 uniform 收敛、full3D–Hybrid 同阶闭合、MPI1/MPI8/MPI16 资格化并冻结 Case093 benchmark；
- Task033 最终权威：[`../task033_high_order_floquet_hybrid_hp_adaptivity/review_report_v6.md`](../task033_high_order_floquet_hybrid_hp_adaptivity/review_report_v6.md)；
- Task033 合并回应：[`../task033_high_order_floquet_hybrid_hp_adaptivity/response_v7.md`](../task033_high_order_floquet_hybrid_hp_adaptivity/response_v7.md)；
- 仓库治理：[`../repository_work_principles.md`](../repository_work_principles.md)。

Codex 必须同时读取两个 Task34 任务文件；如阶段顺序或措辞冲突，以补充任务书为准。Review V1–V3 与 addendum 已直接提交到同一执行分支，Codex 通过 Response V1–V4 逐轮关闭；未经最终 Review V4 和用户授权不得合并 `master`。

当前状态：

```text
implementation_complete_pass_with_qualifications
review_v1_v2_v3_blockers_closed_in_response_v4
final_review_v4_and_user_merge_authorization_pending
```

修正后的核心顺序：

```text
WSL native environment qualification
-> post-merge hardening
-> Task33 anchor reproduction
-> p3/h3 staged reference
-> p4/h5 staged workstation study
-> fixed-geometry p2/p3/p4 convergence
-> full3D–Hybrid closure
-> MPI1/MPI8/MPI16 identity and scalability
-> Case093 canonical benchmark freeze
-> conforming graded-h and genuine fixed-p h-adaptivity
-> 256 GiB / 1 TiB / 2 TiB / 0.7 nm resource recalibration
```

Task034 不运行 0.7 nm 正式 PDE，不实施 arbitrary variable-p H(curl)，不在最终审查前修改 ordinary default。固定 `p`、由场相关误差指标驱动逐轮局部加密属于 genuine h-adaptivity；一次性手工 graded mesh 不得冒充 adaptive。

最终证据入口：[`outcomes/summary.md`](outcomes/summary.md)、[`outcomes/all_model_results.json`](outcomes/all_model_results.json)、[`outcomes/all_model_authority_audit.json`](outcomes/all_model_authority_audit.json)、[`outcomes/selective_merge_manifest.csv`](outcomes/selective_merge_manifest.csv)。主线是 S 偏振；P 仅保留 p2/h5 capability sample。p3/h3、p4/h5 与代表性 MPI 矩阵已接受；p2/h1、p3/h2、p4/h3 Full3D 均按 assembly/resource Gate 受控停止。graded-h mechanism 可执行，但 same-error compression 为 controlled negative，field-driven adaptive 和 `src/geometry/task034_adaptive_mesh.py` 保持 research-only。Task035 当前仅为 planning package，不在本任务运行代码或重型 PDE。