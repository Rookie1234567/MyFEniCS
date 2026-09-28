# Dataset、model 与 source provenance

| 对象 | 身份 / 实际状态 | 证据与边界 |
|---|---|---|
| frozen base | `ccd357885f7f9be84efe3be07868cc94f13d93fc` | 是分支祖先，不reset到它 |
| 初始 task提交 | `f8c51c8e614edc806cf72120ac2cfd14ae8b62f7` | 身份锚点；开始时ls-remote也实读此头 |
| C1 interface源码 | `2c9b54b4f4f7e8e083c398c0290c3881f3dc8980` | clean首次pure import/失败FE preflight；失败未覆盖 |
| 修复后 clean F0 source | `9934c2e08d017124ba70bdc86ec0c22f39ca792f` | 最终pure/FE/ML资格和33测试的真实SHA |
| physics/discretization seed | blob `0c5211a0e99b4f1b74ad5e4223b5d91066b57816`；SHA256 `da6fd8771bd6a4f46b31fe5be3eee1e172589885adea5e560d10a4167216877e` | [静态冻结清单](../../../input/task042_neural_coarse_inverse/frozen_model.json) |
| mesh / original A4/A6 / modes / MPC | not_run，identity字段null | 尚未创建，不把静态config SHA或历史数量当runtime身份 |
| dataset / split / teacher | not_run；无capture、标签、split hash或teacher因子 | [manifest](records/dataset_model_manifest.json) |
| basis / normalization / R-LIN | not_run；无rank、basis SHA、映射或buffer | 不宣布线性表示/精度资格 |
| R-NN / checkpoint / optimizer | not_run；无权重、训练seed或checkpoint SHA | CPU Torch只是环境，模型未创建 |
| old neural branch | `d91652dd2d611d6d6bedd10e677c3f7030c07d4f` | [实际读取文件/blob](records/neural_reference_audit.json)；无旧数据/权重迁移 |
| toy fixture | complex128 3×3三角矩阵+1port+1slave，解析back-substitution | [audit](records/pure_component_audit.json)；不属于Maxwell数据、teacher、训练或heldout |
| ML dependencies | Torch2.7.1+cpu/NumPy1.26.4，全部解析版本锁定 | [lock](../../../input/task042_neural_coarse_inverse/requirements-ml.lock.txt)；安装raw log/hash归运行账 |

每个受监督调用记录实际 command、UTC、CPU、environment mode、source SHA、git status、exit/清场、RSS/swap和小型raw文件hash。早期安装与development tests为未提交工作树，真实dirty记录保留，不能称clean formal run。最后环境与测试在已提交9934c2e、tracked与nonignored untracked均clean时执行；提取交付证据时只有文档变化，明确非formal PDE。

大raw时间线与pip缓存均ignored。记录文件只包含小型身份/指标，不复制旧任务大结果、矩阵或缓存。文档提交HEAD以后改变时，这些source字段保持原实际值。

F2 future packet至少需要schema、operator/physical/mesh/MPC/全部mode SHA、原RHS/复相位/幅值/归一化、whole-trajectory身份和independent seed、source clean状态、sample hashes、train/validation/heldout角色与使用历史；teacher每对原A4 residual及因子释放。F3还需basis/decoder/weights/normalization exact bytes SHA、FP64设置、训练source、epochs/time/RSS/VRAM与选择依据。这些是续做要求，当前不生成假manifest值。
