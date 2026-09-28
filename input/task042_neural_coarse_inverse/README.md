# Task042 输入准备

[frozen_model.json](frozen_model.json) 是首轮物理、离散与预算的静态冻结清单，读取 base 的指定 dat 并保留其 Git blob 和文件 SHA256。它不属于 `run_case.py` 的可执行 dat，也没有创建真实 mesh、mode inventory、A4/A6 或 candidate。

F0 时共享工作站存在 heavy，不能复制旧 `balanced_h6_p4_v5` profile 并标称无因子候选。F1 需在资源空闲、同机 heavy lock 和前置 Gate 通过后新增独立 opt-in dat/profile：从构建起禁止 global p4 LU，显式使用原 A4 的内层 RIGHT FGMRES32/max256/zero start，并绑定三个真实残差 witness。旧准确 LU 只在分进程的离线参考/teacher 阶段出现。

[requirements-ml.txt](requirements-ml.txt) 固定独立 CPU-only Torch 和 NumPy。环境、pip 下载与 bytecode 缓存均由 [activation](../../scripts/activate_task042.sh) 放在 NN-Lab 的 ignored 目录；不安装到原任务环境。

实际运行状态与继续条件见 [Task042 outcomes](../../docs/task042_neural_coarse_inverse/outcomes/summary.md)。首轮仅冻结 original 13.5 nm/p6/h10，同网格 p4；不执行短波、notch 或参数扫描。
