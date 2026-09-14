# V18 装配时单元凝聚：执行证据

本轮在单元内先消去只属于该单元的未知量，再装配共享边界与原 80 端口的全局矩阵。每次新输入先处理内部右端项，做一次全局回代，再恢复全部内部未知量。这样减少全局因子需要处理的规模；局部 LU、恢复算子与装配工作区的费用仍需计入。准确性和实际内存结果由后续正式运行裁决，不能从自由度比例推断节省。

执行基线：`96827e89ce5ba446c4faa7cb507b777f21953af8`，分支 `task39extra`。旧 V17 阈值试验关闭，旧文件与负结果保留。

| 阶段 | 当前证据 | 边界 |
|---|---|---|
| U0 | 新代码及旧 profile/budget 定向测试 74 passed；旧 helper 串行 4 passed；MPI2 三项各 rank 3 passed | 仅小算例和接口合同，不等于正式三输入或 p6 通过 |
| U1 | 复用 Q1 原始三 RHS、原始资源轨迹与环境身份，基线 RSS 2,825,973,760 B | 最终比较须同时核对新运行 scope；历史 Q1 无 CSR 内容 hash，不补造 |
| U2–U5 | 正式结果待追加 | 不将未运行项写成通过 |
| U6 | `response_v19.md` 与最终 compact/decision 在全流程裁决后提交 | 不合并 master |

U0 包含真实两材料单元的完整张量先相加再凝聚、复数 MPC、非零内部 RHS 和端口左右耦合、完整恢复及 slave-zero、重复/线性、CSR 内容身份、owning 清理、真实 p6 dispatch，以及逐 RHS 保存与异常保留。开发中发现并修复了组合积分丢项、端口矩阵插入布局、缓存记账和测试夹具符号等问题；失败日志保留在 ignored 工程目录，尚未使用正式计算的 bug replay。

工程证据目录：`benchmarks/artifacts/task39extra/p4_cell_condensed_v18/root_engineering/`。独立检查器是 `benchmarks/check_p4_cell_condensed_v18.py`。准入检查从原始数组、范数、factor 控制和连续进程树轨迹重算；准确路线不设内存节省百分比门槛。U3 仅允许新凝聚矩阵的一个 `tau=1e-5`，不足则选择准确凝聚继续。

本地未安装 Ruff，未安装新包；没有执行全仓库 pytest 或声称 CI 通过。完整 formal source SHA、命令与阶段结果随正式证据追加。
