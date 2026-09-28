# Task042 实际变化与依赖

| 组 | 文件 / 行为 | 依赖、验证与fresh PDE |
|---|---|---|
| research numerical interface | `src/solvers/coarse_inverse_protocol.py`；新严格返回检查，未接入旧数值路径 | NumPy；33 pure-array tests；无fresh FE/PDE |
| focused tests | `src/test/test_task042_coarse_inverse_protocol.py` | 解析复杂toy与错误注入；无teacher/factor/globalPC |
| local activation | `scripts/activate_task042.sh`、`.gitignore`增加`.venv-ml/` | 两新venv与只读ABI prefix；三模式导入/实际cache核验 |
| bounded F0 tooling | `scripts/task042_preflight.py`、`scripts/task042_bounded_check.py` | 复用既有subreaper及采样，固定busy F0容量；不复制数值runner |
| input preparation | `input/task042_neural_coarse_inverse/{README.md,frozen_model.json,requirements-ml.txt,requirements-ml.lock.txt}` | 从指定seed冻结physics/采样，runtime identity仍null；不是可执行candidate dat/profile |
| compact docs/evidence | Task042 outcomes全部新文件、`response_v1.md` | 真实source/正负/未运行、raw hashes、测试与资源记录 |
| project bookkeeping | `docs/development_progress.md`新阶段、`docs/development_model_registry.md`第3章独立小节 | 不改旧结果/分类；所有物理项not_run |

C1为`2c9b54b4f4f7e8e083c398c0290c3881f3dc8980`。一次最小预检修复为`9934c2e08d017124ba70bdc86ec0c22f39ca792f`（实际DOLFINx0.10 `get_options()`与XDG_CONFIG_HOME）。C2/C3/C4没有实施；C5只收口F0真实结果和资源等待。

没有修改根/docs AGENTS、任务README/task/review、旧任务文件、A4/A6/BAL_H/传递/凝聚/runner数值源码、普通默认或共享native库。没有从神经分支迁移代码。任何研究路径提升为生产或合并master均未获批准；建议审阅顺序为隔离与协议→数组测试→轻量证据/文档，真实candidate之后必须独立F1/F4/F5资格。

venv、pip/Torch/HF/bytecode/JIT caches、raw worker日志/资源时间线位于本地ignored路径。只提交轻量manifest/JSON/CSV/hash，不含矩阵、factor、模型权重、训练dataset、旧结果或下载文件。
