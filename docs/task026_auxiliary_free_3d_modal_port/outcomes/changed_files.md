# 改动文件

| 文件 | 内容 |
|---|---|
| `src/solvers/condensed_dtn.py` | 通用 dense/PETSc 静态凝聚、显式与 matrix-free operator、回代和存储估计 |
| `src/studies/run_task026_auxiliary_free_modal_port.py` | h5/h2 reference、iterative、real-AMS、topology two-level runner |
| `src/studies/run_task023_petsc_mpi_fe_response_pc.py` | runtime assembler 支持自定义 raw/result 目录，默认行为不变 |
| `src/studies/run_task024_engineering_iterative_solver.py` | real-split export 增加全部 C 列 local CSR，修复最后 rank FE/aux 行切分 |
| `src/test/test_22_task026_condensed_dtn.py` | 非单位 H、符号、回代、MPI4、1000 apply 测试 |
| `notes/theory/task026_auxiliary_free_condensed_modal_port.md` | 凝聚与 COMSOL-style two-level 理论笔记 |
| `docs/README.md` | Task026 最新状态与结论 |
| `docs/task026.../outcomes/*` | 本轮轻量证据、表格与阶段总结 |

## Review V1 收尾新增

| 文件 | 内容 |
|---|---|
| `src/studies/run_task026_auxiliary_free_modal_port.py` | 流式 monitor、RSS/swap checkpoint、coarse rank gate、h2 action-check、谐波 coarse、外层 KSP 消融、custom additive backend |
| `outcomes/h2_matrix_free_action_equivalence*.csv` | h2 MPI1/MPI4 实际 action gate |
| `outcomes/raw_runs/task026_h2_*` | h2 资格、长跑、失败与资源证据 |
| `outcomes/response_v1.md` | 对 Review V1 的逐项响应 |
| `outcomes/summary.md` | 最新 h2 结论、表格与未关闭 Gate |
| `notes/theory/task026_auxiliary_free_condensed_modal_port.md` | Floquet 谐波 coarse 与下一步谱粗空间理论 |

`papers/` 与 `results/` 未加入 Git。
