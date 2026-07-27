# Task000 Review Report V1

## 审阅结论

```text
review_status = approved_for_task001
bulk_generation = not_approved
forward_environment = qualified
hybrid_high_fidelity = not_yet_qualified_on_local_machine
```

Task000 按任务边界完成，可作为 Task001 的起点。批准的是本地原生 WSL complex FEM 环境、Git 防护、薄前向接口、记录合同和低资源 development smoke；不批准直接开始批量训练数据生成。

## 通过项

- `Ubuntu-24.04` / WSL2、项目 `.venv`、complex PETSc/SLEPc、DOLFINx、dolfinx_mpc、OpenMPI、MUMPS、PEP 和 FFCx JIT 已资格化；
- Docker 被完整保留且 Task000 未调用 Docker；
- branch/upstream/pre-commit/pre-push 防护和 workspace audit 通过；
- `src.forward_data` 保持薄适配，不复制 Maxwell、网格、DtN、装配或后处理核心；
- Linux CLI、Windows-to-WSL launcher prototype、source/config/artifact hash 和 dataset 混源拒绝合同已经建立；
- 单个 13.5 nm development smoke 通过 residual、R/T/A、体吸收和无 swap Gate；
- targeted tests、Case095/096 compact authority、Bash syntax、compileall、PowerShell parser 和 `git diff --check` 均通过。

## p6/h10 结论的解释

Task000 将 p6/h10 分类为 `blocked` 是正确的受控行为，不是数值失败：

1. 历史 Case096 六路 authority 绑定 `244b62e1...`，而 Task000 实施期间 source 不同且 dirty；
2. Full3D static 历史峰值 14.722 GiB 超过本机 WSL 13.65 GiB 总内存；
3. Task000 v1 薄接口尚未封装 Hybrid static M120；
4. 40 GiB swap 不能被当作物理内存来伪造可行性。

Task001 可以在 clean branch source 上资格化本机 Hybrid，但不得把历史不同 SHA 的结果直接标记为当前 formal sample。

## Task001 前必须解决的事项

Task001 必须先完成以下 Gate，再允许任何正式 pilot 数据：

- 冻结仅两个可反演参数及窄范围：高度和 x 向宽度；
- 固定 13.5 nm、材料、周期、y 向满宽、矩形侧壁和其余物理参数；
- 扩展 ForwardParameters/observables schema，而不是绕过 Task000 adapter；
- 建立 Hybrid 单任务 watchdog、process-tree memory/swap 监控和 clean-source formal run；
- 在当前 source 上重新资格化 nominal p6/h10 Hybrid static M120；
- 对用户提出的 p6/h7.5 先做资源预估，只有满足安全内存 Gate 才允许完整求解；
- 选择并验证一个低保真 Hybrid 模型；
- 先完成局部敏感度与可辨识性 pilot，不直接生成完整 49 点或更大的数据集。

## 批准的下一步

批准创建并执行：

```text
surrogate_tasks/task001_two_parameter_hybrid_multifidelity_pilot/
```

Task001 结束后必须由 ChatGPT 再次审阅，才可开始正式多保真数据集生成。