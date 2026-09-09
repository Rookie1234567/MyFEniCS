# Response V2：用户授权后的性能验证接线

本轮由主控明确授权继续执行原生 Linux native-capacity campaign。此前 `f124679e75915758076d9240bd4bef2f5c772752` 已提交的 p4 按行内核、p4/p6 curl 独立循环合并和 PSS 降频作为唯一性能实现；不新增求解算法、预条件器、子域法或参数扫描。旧的 13.5 nm screen 负结果和首次 mode 失败保留不变，新正式运行必须从零、冷缓存、clean source 开始。

## 生效合同

| case | 材料身份 | screen | solve 上限 / s | workflow 上限 / s | 其他固定项 |
|---|---|---:|---:|---:|---|
| 13.5 nm original | Si，`n=0.999002304859+0.00182649365i` | 128 步、7200 s | 43200 | 64800 | MPI1、线程1、restart32、max2048、zero start |
| 13.5 nm notch | Si，同上 | 不启用，不增加 screen | 43200 | 64800 | 同上 |
| 5 nm（后续解锁） | Si，`density=2.33`，`delta=0.00603145547`，`beta=0.00435380777`，`n=0.99396854453+0.00435380777i` | 既有 10800 s | 86400 | 129600 | 仅在 R1/R2 资格后按实际 channel/inventory 预检 |

5 nm 数值来自用户本轮权威输入；本轮不声称已独立核验数据库来源。它是复折射率 `n`，不是 epsilon；运行时由 `epsilon=n*n` 生成并记录。3 nm/2 nm 材料身份不在本轮自行推断。

## 当前状态

截至本澄清文件创建时，唯一执行 worktree 为 `/home/fenics/Projects/Maxwell3D-Lab/task39extra_para_workstation_capacity`，交接 HEAD 为 `0e8c06e1f817fda22b10e75b03987ae5a4cce4b9`，工作树 clean。现先完成预算接线、最小参数验证和提交；提交后的 clean SHA 才允许启动新的 13.5 nm original。运行期间保留 CPU23 worker / CPU9 supervisor 的实际占用证据；绑核只说明 affinity，不外推共享内存带宽或功耗无竞争。
