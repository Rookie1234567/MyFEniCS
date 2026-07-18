# Task005 集中验证与 provenance

## 验证身份

| 项目 | 值 |
|---|---|
| branch | `ChatGPT/20260715-para-task-neural-local-pc` |
| clean validation SHA | `805dcd0c2b0a7e60483425c430a3a23ba0593c44` |
| FEniCS environment | `/home/fenics/.local/bin/myfenics-python-complex` |
| ML environment | `/home/fenics/miniforge3/envs/fenics-ml/bin/python` |
| workspace | `/mnt/c/Users/Administrator/Desktop/MyProject` |
| heavy evidence rerun | 否；遵循 Review V1，只验证代码与合同 |

## 结果

| 检查 | 命令范围 | 结果 |
|---|---|---|
| complete `src/test` | complex wrapper，`pytest -q src/test` | **207 passed, 12 skipped** |
| Task005 ML targeted | fenics-ml，`pytest -q src/test/test_45_para_task005_contract.py` | **6 passed** |
| MPI lifecycle targeted | MPI2，`test_38_local_backend_plan.py` | **每 rank 3 passed** |
| Ruff Task005 scope | Task005 benchmark、solver 与 test tracked files | **All checks passed** |
| compileall | `benchmarks/neural_pc src/solvers src/test` | **PASS** |
| diff check | `git diff --check` | **PASS** |
| artifact ignore | `git check-ignore -v benchmarks/artifacts/cases/094` | **PASS**, `.gitignore:58` |

FEniCS complex wrapper 不安装 PyTorch，因此 PyTorch/NumPy export test 在该环境中
明确 skip，并在已经配置 GPU/PyTorch 的 `fenics-ml` 环境单独通过。这不是缺测。

全仓 Ruff 另有 7 个 Task005 之前即存在的告警，位于
`src/solvers/common_3d_fields.py`、`common_3d_postprocess.py` 和
`solve_maxwell_3d_common_old.py`。本响应未扩大范围机械修改这些无关文件；Task005
实际改动文件的 Ruff 检查为零告警。

## 首轮验证发现与修复

在 `6821cd0` 上首次完整运行得到 `206 passed, 11 skipped, 2 failed`：

1. Case094 已存在但未注册到 `test_26_documentation_contract.py`；
2. Task005 nonlinear export test 在无 torch 的 complex wrapper 中无条件 import。

本地提交 `805dcd0` 补齐 Case094 的统一合同并分离 FEniCS/ML 环境测试，之后得到
上述 clean PASS。该失败记录保留，未删除或掩盖。
