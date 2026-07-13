# Changed Files

| 文件 | 说明 |
|---|---|
| `src/studies/run_task023_petsc_mpi_fe_response_pc.py` | 新增 Task023 PETSc FE-response / FieldSplit / selected-response research runner；修正 MPI FieldSplit IS ownership |
| `docs/task023_petsc_mpi_fe_response_pc/outcomes/summary.md` | 本轮结果总表，含 h=5 R/T/A 闭环、h=2 诊断、h=1.5 外推 |
| `docs/task023_petsc_mpi_fe_response_pc/outcomes/*.csv` | route1/2/3/4/5、gate、R/T/A、mode mapping、h=2 preflight 等机器可读结果 |
| `docs/task023_petsc_mpi_fe_response_pc/outcomes/*.md` | solver ranking、merge recommendation、next decision、route 风险说明 |
| `docs/task023_petsc_mpi_fe_response_pc/outcomes/raw_runs/` | 轻量 JSON/CSV 结果记录；未提交大型 matrix/mesh/VTU/HDF5 |

未修改 production 默认 solver profile。
