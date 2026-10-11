# Task40extra V27 CSR_PENDING 单 q 续作交接

本轮只完成 regular-reference q0 的结构位置与列索引。数值 manifest 仍为 `NUMERIC_FILL_INCOMPLETE`，`contribution_cursor=null`。不要重跑 producer、FE/MPC/native、routes 或结构阶段。

## 源码与输入身份

producer source `9d0f4dbfc730dd620b709d048e33e9da6c77520c` 对应 V25 donor payload。V26 accepted science source 为 `f9093c87f81d52b75fbc156e562b3745df45ccf4`，其结果 base 为 `399787abc991e0e30975bc694bd18a9a30c5470e`。V27 分阶段冻结 source 依次为 `c1307939a028bdce491ef242ab1c13d70c05cc37`、`99429d69e29d2180892814d370a41dae2dc31c03`、`66d49273737ae1f8362e06e255f3b76565173cea`、`61530133bd02b18052e3ba64a5f78b87424c57f6`；正式运行使用最后一个 source。当前 input SHA 为 `134ea5f08d5d5dbc366870f451ba0de0df5893c5cd73d227dac77f8a11aa2c0b`，window SHA 为 `e806c514c8208ae7a887bdb6ddaaec25936c9204a3ccc34a4fb870ad0bb0010d`，旧 window 未刷新。完整 `donor_identity` 的 payload、native NPZ、recovery manifest/checker、saved replay 和结构见证路径与哈希都保存在 [operator compact](records/target_operator_probe_v27.json)。V26 的 native recovery 是本次的 donor 身份证据，不是 V27 新运行结果。

## 已保存且可核对的文件

| Artifact | 大小 | 内容身份 |
|---|---:|---|
| `results/task40extra_nonseparable_0p7nm/task40extra_0p7nm_target_original_ny8_operator_probe_v22__full3d_iterative__mpi1__Mna/20261011T153931.649307Z/v27_q0_csr/task40_v27_q0_csr_manifest.json` | 18,336 B | SHA-256 `1ea707f3c201359c390b620a5122d0102f5b34bd74873b5f00e3a40b673b94de`；`NUMERIC_FILL_INCOMPLETE` |
| `results/task40extra_nonseparable_0p7nm/task40extra_0p7nm_target_original_ny8_operator_probe_v22__full3d_iterative__mpi1__Mna/20261011T153931.649307Z/v27_q0_csr/task40_v27_q0_row_structure.npz` | 2,121,772 B | SHA-256 `56d344256ff60e73ec36ecd58d1aade6e6d7dac5164741de60f0631dc0407bda` |
| `results/task40extra_nonseparable_0p7nm/task40extra_0p7nm_target_original_ny8_operator_probe_v22__full3d_iterative__mpi1__Mna/20261011T153931.649307Z/v27_q0_csr/task40_v27_q0_support_routes.sqlite3` | 1,328,558,080 B | SHA-256 `a27d291a1bc41751b7a70f15bfef6cf1d1fc85aeb9ce4c01fd7f5153143186f1` |
| `results/task40extra_nonseparable_0p7nm/task40extra_0p7nm_target_original_ny8_operator_probe_v22__full3d_iterative__mpi1__Mna/20261011T153931.649307Z/v27_q0_csr/task40_v27_q0_00_indptr.npy` | 3,110,708 B | SHA-256 `6d24828a2cd820601fedf92c5b6575fc2dd95a905c2533677f3a3367648a7819` |
| `results/task40extra_nonseparable_0p7nm/task40extra_0p7nm_target_original_ny8_operator_probe_v22__full3d_iterative__mpi1__Mna/20261011T153931.649307Z/v27_q0_csr/task40_v27_q0_00_indices.npy` | 2,308,244,800 B | SHA-256 `9279c5dbfb8921c61dc229ea6a99d30bb76f8b31d005076796d4504a1e7d0d6e` |
| `results/task40extra_nonseparable_0p7nm/task40extra_0p7nm_target_original_ny8_operator_probe_v22__full3d_iterative__mpi1__Mna/20261011T153931.649307Z/v27_q0_csr/task40_v27_q0_00_data.npy` | 9,232,978,816 B | 完整 shape 的预分配文件；数值不完整、无 hash |

文件长度含 NPY header。data 长度不表示已写入比例；numeric nonzero、exact-zero 数及完整 data SHA 均未知。续填前必须先清零 data。

## 数值续填

新执行窗口获授权且通过资源预检后，用 donor 绑定数组重建保存的 q0 adapter，再调用既有 API：

```python
from src.solvers.task40_v27_saved_q0 import fill_saved_q0_csr_values

q0_csr, completed_manifest = fill_saved_q0_csr_values(
    adapter,
    manifest_path=manifest_path,
    allocation_gate=allocation_gate,
    source_identity=continuation_identity,
)
```

`continuation_identity` 必须保留现有 `donor_identity`。API 接受 `STRUCTURE_COMPLETE_VALUES_PENDING` 与 `NUMERIC_FILL_INCOMPLETE` 状态，并在每次数值 pass 前清零 data，因此不需要猜测贡献游标。此阶段无需 FE、producer、native、routes 或重新构造 pattern。

## 因子续作

独立的 factor continuation CLI/wrapper 尚未实现。只有 manifest 达到 `COMPLETE_CSR` 后，才可组合现有底层 API：

```python
from src.solvers.task40_v27_saved_q0 import open_saved_q0_csr_from_manifest
from src.solvers.task40_v10_p6_mumps import run_task40_v26_selected_q0_factor_lifecycle

q0_csr, complete_manifest = open_saved_q0_csr_from_manifest(manifest_path)
factor_report = run_task40_v26_selected_q0_factor_lifecycle(
    q0_csr,
    allocation_gate=allocation_gate,
    checkpoint_directory=checkpoint_directory,
    current_identity=current_identity,
)
```

manifest opener 会检查 `COMPLETE_CSR` 状态以及三份数组的 hash。对本次 pending manifest 的只读调用按设计返回 `ValueError`。由于 CSR 尚未完成，本轮没有尝试 factor；这不是本次运行触发了 factor 资源 Gate。source CSR 加转换副本的 derived 下界为 23,088,667,880 B，保守准入 envelope 为 80,884,991,404 B，都不是 MUMPS factor 实测峰值。当前本机 16 GiB cap 不足以资格化后续 factor 阶段；恢复工作仍需新授权窗口与环境预检。

## 停止与生命周期

T0=`2026-10-11T13:37:38Z`，数值 cutoff=`2026-10-11T19:17:38Z`，总 deadline=`2026-10-11T19:37:38Z`。watchdog 判定 `PERFORMANCE_CONTROLLED_STOP`、leader exit 15，并清理了全部 descendants。数学 worker PID 为 2321856，watchdog root 为 2321839，systemd service parent 为 2321801。task cgroup swap peak 为 0；WSL 全局 swap 计数有变化但无法归因到本任务。target PDE、R/T/A、full q 与 2 TB / 48 h 均未资格化。

更多数值状态见 [Response V27](../response_v27.md)、[operator compact](records/target_operator_probe_v27.json)、[资源账](records/time_resource_accounting_v27.json)、[workflow ledger](records/review_v27_incremental_workflow_ledger.json) 与 [分阶段测试摘要](test_summary.md)。
