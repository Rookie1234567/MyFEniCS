# Case092：WSL 工作站受控可扩展性

本 Case 保存 Task034 的轻量、可审阅、hash-bound 资格化记录。重型 PDE 原始输出保留在
`benchmarks/artifacts/task034/`（gitignored），由本 Case 的 SHA-256、clean source
identity、Gate 状态和关键测量摘要绑定。Task033 的 14 GiB Gate 保持不变。

## 物理问题

固定 Stage-4 三维周期结构，波长 13.5 nm，入射掠射角 10°，s 偏振，材料、端口、
10/110 nm 接口和 official R/T/A 定义沿用 Task033。Task034 在 WSL2 Ubuntu 原生
环境中分级测量 p3/h3 与 p4/h5 full3D、Hybrid 和后续 fixed-p 收敛/自适应候选。

## 参数说明

| 编号 | 受控参数或合同 | 当前含义 |
|---:|---|---|
| 1. | `host_environment_id` | `WSL2-Ubuntu-24.04` |
| 2. | `source` | clean full SHA，运行前后必须稳定 |
| 3. | `wavelength_nm` | 13.5 |
| 4. | `incident_grazing_deg` | 10.0 |
| 5. | `polarization_kind` | `s` |
| 6. | `bottom_interface_nm` | 10.0 |
| 7. | `top_interface_nm` | 110.0 |
| 8. | `p3_h3` | finer discrete WSL anchor |
| 9. | `p4_h5` | staged workstation target |
| 10. | `full3D` | assembly → factorization → full solve |
| 11. | `Hybrid` | M80 → M120 → M160 |
| 12. | `M240` | 仅 M120→M160 单独模态不收敛时允许 |
| 13. | `mpi_size` | 当前 Phase D/E 正式锚为 4 |
| 14. | `solver_path` | `modal-schur-memory-minimal` |
| 15. | `comparison_solver_path` | `fast` |
| 16. | `direct_solver` | PETSc `preonly + LU + MUMPS` |
| 17. | `true_residual` | full solve 必须 `<= 1e-9` |
| 18. | `job_swap` | 正式内存权威要求 0 |
| 19. | `warning` | 现场 effective limit 的 80% |
| 20. | `termination` | 现场 effective limit 的 95% |
| 21. | `heavy_run_policy` | one-heavy-case-at-a-time |
| 22. | `0.7 nm PDE` | Task034 禁止运行，仅做资源评估 |
| 23. | `extended_mpi_qualification` | MPI1/2/4/8/16 formal；MPI32 exploratory |

## PyCharm

本 Case 不提供绕过 Gate 的 IDE 入口。若从 PyCharm 复现实验，解释器必须指向
`.venv/bin/python`，并通过项目的 WSL 激活脚本获得 complex PETSc/SLEPc ABI、
MPI 和线程上限。正式证据仍必须由 watchdog CLI 生成。

## CLI 或测试

环境激活：

```bash
cd /home/Projects/MyFEniCS
source .venv/bin/activate-myfenics
```

轻量合同回归：

```bash
pytest -q src/test/test_73_task034_hardening.py
pytest -q src/test/test_74_task034_workstation_resource_gate.py
ruff check .
```

扩展 MPI 环境资格化：

```bash
python -m benchmarks.run_task034_wsl_qualification \
  --mpi-sizes 1,2,4,8,16,32 \
  --distributed-solver-sizes 8,16,32 \
  --exploratory-mpi-sizes 32
```

重型命令不在 README 中提供无条件一键版本；必须按任务书顺序读取 candidate-specific
authority、现场内存、swap、磁盘和 source Gate。

## 代码路径与理论

- `benchmarks/task034_wsl_resources.py`：WSL 现场 effective memory 公式。
- `benchmarks/task034_workstation_resource_gates.py`：Task034 显式 opt-in Gate。
- `benchmarks/run_task033_full3d_watchdog.py`：assembly/factor/full-solve 分级权威。
- `benchmarks/run_task033_memory_watchdog.py`：QEP/Hybrid RSS、swap、timeout 权威。
- `records/workstation_hybrid_launch_authority.json`：候选级实测锚与保守预测。
- `records/p3_h3_reference_summary.json`：p3/h3 reference 与重新排名摘要。
- `benchmarks/task034_resource_model_v2.py`：不授权 launch 的 component-separated
  wavelength/budget prediction。
- `records/wsl_extended_mpi_qualification.json`：MPI1/2/4/8/16 与探索性 MPI32
  环境、ABI、MUMPS/PEP microfixture 的紧凑 hash-bound 记录。

## 当前证据

p3/h3 full3D、Hybrid M160 同阶闭合及 p2/h3 重跑已经形成 hash-bound 摘要。
p4/h5 E0 assembly、M80/M120/M160 funnel、factorization-only、full solve 和同阶
Hybrid/full3D closure 均已在 WSL 原生环境中完成。`records/p4_h5_workstation_summary.json`
已冻结 official R/T/A、true residual、五平面/接口/衍射阶 closure、memory、zero-swap、
source compatibility 和原始工件 SHA-256。重型原始工件继续保留在 gitignored
`benchmarks/artifacts/task034/phase_e/`。

clean SHA `70590b4f99a6c0e389ec69b7fcf10d1e421b4f7d` 上的 p2/h5 conforming
graded-h mechanism MPI8 资格化通过：材料面和 10/110 nm trace 精确，bottom/top 与
matching cross-section 的 x/y topology 一致；两侧各 484 条 p2 Floquet constraints，
pairing/phase/transform 误差均为 0。该记录只证明机制，不包含 PDE solve，不声明等误差
压缩或 genuine adaptive 已完成。轻量证据见
`records/adaptive_mechanism_qualification.json`。

clean SHA `455128a2f777dbadd8e38430bbcd3a2ad10e5a7e` 上完成 p2/h3 的
conservative/balanced/aggressive 三档 MPI8 Hybrid M80/M120/M160 funnel。三档 modal totals
均在 M120→M160 收敛，但全部超过固定 Full3D 同误差 Gate；aggressive 还未通过 interface H
Gate。因此 `records/adaptive_summary.json` 将结论冻结为 `controlled_negative`，raw DoF ratio
不得称为 qualified compression。首次 aggressive M80 瞬时 MPI/WSL 启动失败也保留，独立
retry1 才作为有效 M80 shard。任务书的 critical-observable stop condition 已触发，未继续
重型 common-mesh 与 p3 adaptive lane，也未改变 ordinary uniform default。

`records/resource_model_v2.json` 使用 p2/h3 Hybrid M160 组件库存、十个 fixed p/h peak
校准点和三档 adaptive negative 重新评估 13.5/5/2/1/0.7 nm。当前布局在 0.7 nm 下预测
约 2,014,975 GiB；dense multi-RHS 是首个主导失效组件，单个 complex `(2M)^2` 对象约
211 GiB。256 GiB、1 TiB、2 TiB 均分类为 `infeasible_current_layout`。该记录是 prediction，
不运行 PDE、不证明 0.7 nm 可行，也不授权重型 launch。

clean SHA `8440bbaf42de9d633479d0ed65bdda544bd871ef` 上的扩展 MPI 环境资格化通过：
48 个可用物理核，MPI1/2/4/8/16/32 均无 oversubscription，所有 rank 使用同一
Python/MPI/PETSc/SLEPc/DOLFINx ABI；MPI8/16/32 的分布式 MUMPS 与 PEP
microfixture 均通过。MPI32 明确为 exploratory，不替代正式 MPI16 或 PDE identity。

## 结果解释

`KSPSetUp` 在本 Case 的 direct profile 中表示 MUMPS 符号/数值分解，不是普通前处理。
p4/h5 普通 setup 为秒级，长耗时主要来自矩阵装配与直接分解。任何较粗 p4 closure
只能证明高阶耦合链工作，不能冒充 p4/h5 canonical positive；任何 measured negative
也必须原样保留。

## 限制

- 当前 Case092 状态仍为 Task034 in progress，不声明 fixed-geometry/adaptive 全部完成。
- `grid_converged=false` 时不得宣称连续解收敛。
- Hybrid-only 结果在同阶 full3D closure 前只属于 measured engineering result。
- 历史 Task033 资源模型不能单独授权工作站重型运行。
- git 只保留轻量记录；NPZ、VTU、timeline 和完整 solver output 不进入版本库。
- MPI32 microfixture 只证明环境与小型分布式代数链，不证明 MPI32 加速，也不构成
  MPI1/MPI32 代表性 PDE 数值一致性证据。
- 不得自行合并 master；最终提交与 push 后等待独立 review。
