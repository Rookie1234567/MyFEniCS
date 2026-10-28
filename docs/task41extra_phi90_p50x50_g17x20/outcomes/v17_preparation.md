# Task41 V17 准备记录（进行中）

状态：`IN_PROGRESS`。本文只记录代码准备，不授权创建执行窗口、T0、authorization、contract 实例或启动正式计算。

## 固定范围

- active row `1622464`、original row `5218672`，只处理按生产顺序排列的 cells `[7873, 8014]`。
- 复用 V16 的保存向量和 hash-bound metadata；不重跑分布、旧 star、accepted checker、carrier 或 full owner。
- 窗口合同草案为 21,600 秒总量、20,400 秒数值阶段、1,200 秒收口；V17 专属 authorization/window/accounting 文件尚不存在，且需要新的明确批准。
- 仅用于新证据的限额为 128 MiB，累计原始产物上限 16 GiB，保留 2 GiB 空闲空间底线。当前 worktree 不创建这些授权或窗口文件。

## 已实现的准备部分

- selected-cell trace-star metadata builder 接受严格的 ordered cell scope，并保留旧调用的记录格式。
- selected-cell role artifacts 可通过 callback 按 raw、oriented、R/T/S、LU/pivots 逐项持久化，以支持阶段中断后复用。
- V17 checker metadata reader 固定读取 V16 `max_row_probe_metadata.json` 的 SHA 与坐标顺序；几何顺序来自 `coordinate_hex`，不信任排序后的 `actual_keys`。
- V17 signed identity helper 把每单元局部项与两单元共用的全局项分开；二进制64位和 `clongdouble` 作为不同的 evaluation diagnostics 输出。全局 `b_t_volume` 与 `epsilon_t` 在两单元 aggregator 中各扣一次。
- V17 saved-diagnostics contract scope 已起草；所有构建、分解、GETRS 数量均为上限，避免因复用已有数据而人为重算。
- 已新增窄 callback：`src.runners.task41_p0_v4_volume_only_audit._run_v17_selected_two_cell_candidate_callback(...)`。输入为已通过严格 loader 的 consumer contract/window、V16 metadata与saved-vector manifest、V9/V15两列向量、V3 donor、fresh selected-cell I/T/E map、actual-qmetric evaluator及持久化/预算回调。它只处理 active row `1622464` / original row `5218672` 和按序 cells `[7873, 8014]`，不创建 full owner、carrier、surface 或 full-q 对象。
- callback 将数学输入/固定窗口身份与consumer contract/source身份分开；重开时先按路径和SHA重新加载原producer contract，要求同一固定窗口、scope和数学输入。仅源码修复可沿同窗重开已完成数据；跨窗或数学身份变化拒绝续作。
- 完成cell通过 `_task41_p0_v17_reopen_completed_candidate` 使用生产的 hash-bound NPY loader 读取；完成RHS通过 `_task41_p0_v17_reopen_completed_rhs` 重开。RHS重开会重新核验返回值逐元素等于 `-J @ z`，污染correction会拒绝。每次生产solve保存的同次初解 `z0` 可直接计算 `g9` 的 `-Jz0` 对照，不额外GETRS；callback也调用已有V17 signed cell/two-cell identity函数，局部/全局项及 `b_t`、`Bα` 的次数保持显式。
- signed identity 的 `q` 从当前cell的 `E[:, active_slot]` 读取并核对为该cell的局部 `+1` trace slot；不沿用上一个cell的slot。
- V17 selector已接入Python `run_service`→Task41 contract scope/window guard→saved-output service。saved-output service现从固定 V16 manifest、V16 metadata及V3索引/manifest重新核验两列所需原始向量，建立全新编号 attempt；worker只构建两单元 fresh map、保存 actual-qmetric candidate/RHS结果并受 128 MiB、16 GiB累计及2 GiB空闲空间门限约束。
- worker CLI只接受V17专属参数，并绑定当前 consumer contract、V16 manifest、固定行/单元、FFCx源码路径与哈希。service按数值窗口监督worker，只有worker回执满足scope及非official标记才启动只读独立checker；checker在closeout窗口内独立重开保存数组并复算，watchdog现注册专用checker类型并校验契约、固定窗口、manifest、worker报告及授权输入哈希。服务终态仍明确保持 `official_result=false`、`scientific_qualified=false`、`full_owner_unlocked=false`。
- 新增fixture覆盖service生成worker命令→worker CLI→真实V17 callback→数组持久化→真实checker CLI→checker receipt gate，并覆盖禁止full-owner和official标记；另有watchdog route/授权哈希fixture。首轮checkpoint现在在首次fresh-map保存时同步绑定candidate identity，原有完整性等值比较保持不变。
- 独立checker现自有V17规范化JSON/数组哈希和hash-bound NPY读取逻辑；不引用worker私有helper，并核验路径、SHA、大小、shape、dtype及有限值。现还逐RHS复算每步补偿残差、校验 `z_before + delta = z_after`、将终解连接到校正链，重算GETRS/残差计数，并按唯一文件统计全部新NPY字节；超128 MiB拒绝。

## 已验证

- Qualified activation preflight 之前通过：项目虚拟环境、PETSc `complex128`/`int32`、SLEPc 3.19.2、Open MPI 4.1.6 及 PETSc/mpi4py communicator 栈一致。
- 本回合在受限沙箱单独导入MPI栈时，Open MPI/PMIx `socket()` 返回 `errno=1`；获准后用仓库qualified activation在具备MPI socket权限的执行环境运行定向测试。
- 首次端到端执行依次发现并修正测试fixture缺失NumPy导入、复数抵消期望值、fresh-cell索引字段，以及生产callback首轮checkpoint的identity绑定顺序和checker中缺失/误命名的独立hash/NPY helper。最终checker fixture还明确验证损坏的map数组SHA和缺失map coverage均被拒绝。
- 最终V17 service/callback/checker与V8兼容性定向测试：`47 passed in 15.72s`。新增真实严格loader负例直接调用contract与V16 manifest loader，错误contract SHA、错误scope、错误manifest SHA均被拒绝，没有mock loader。此次测试使用合成V16/V3数据、minimal FE映射和替代昂贵kernel；包括零 RHS、非零 RHS一步零残差、篡改步残差拒绝、全量唯一NPY字节核算及限额拒绝；未读取真实ignored数组、未运行真实service或FE/PDE。
- 主控在资格化本机环境以 `set -e`、仓库activation及 complex128/int32 preflight 运行 `test_task41_p0_v17_selected_replay.py` 与 `test_task41_v8_selected_trace_star.py`：`33 passed in 0.86s`。该结果早于下面的per-cell E-column修复，不作为当前完整回归结果。
- 重开/污染fixture定向结果：`1 passed, 4 deselected in 0.65s`。修复两cell q槽位串用后新增的不同E槽位测试在资格化activation下：`1 passed, 5 deselected in 0.10s`；同一命令的 `git diff --check` 通过。
- 早先及本回合沙箱内PMIx socket errno=1的尝试不计作测试结果；最终46项通过来自获准的qualified activation执行。V15合同兼容测试另为 `1 passed in 0.09s`。服务真实hash-bound输入、watchdog closeout和完整FE worker仍没有执行。
- 没有运行 FE、MPI PDE、真实 service、checker-only 终态路径，也没有创建窗口或启动计算。

## 尚未完成

1. 从工作站受信结果目录核对V16 saved-vector manifest及V3 donor/input真实ignored artifact布局；当前固定V16 manifest在本地worktree不存在，仅追踪的20KiB metadata存在，因此fixture的绑定结构已验证、真实路径布局尚未验证。
2. 确认服务closeout阶段的完整输入哈希授权在批准窗口的余时内可完成。当前服务会对绑定输入逐项重新hash，尚无本地性能测量。
3. 主控冻结源码后再评估是否请求V17窗口/authorization准备授权。当前状态仍为 `IN_PROGRESS`，不称 `READY`。

## 执行边界

不执行 prepare/launcher-values，不创建实际 authorization/T0/window，不启动或监督 V15/V16/V17 正式 PDE，不 commit/push。完成实现和 fixture 后，仍须等待主控冻结源代码及用户批准的新六小时窗口，才能进入正式准备。

## 主控冻结前复核（2026-10-28）

主控在执行者结束修改后的稳定快照，使用资格化 activation 独立复跑 V17 两模块、直接受影响的 V8 模块及一个 V15 合同兼容测试：`48 passed in 15.74s`；complex128/int32 preflight、`bash -n scripts/run_case_in_user_service.sh`、`git diff --check` 均通过。测试仍为本机合成/接线验证，不是工作站数值资格。

正式接续增加显式旧 producer contract/progress/report 路径及 SHA。旧文件只读；新 consumer 使用新输出目录。已有完整 report 走独立 checker，不启动 FE worker；partial progress 只重开已完成 cell/RHS，未完成状态不冒充完成。新 consumer 与旧 producer 必须属于同一个已批准 V17 窗口及数学范围。不同源码修复不刷新窗口。

当前远端及准备 base 为 `06cd1789c717face827476ad70f24ae8efb6b0f1`。非交互 SSH 探针仍返回 `Permission denied (publickey)`，所以工作站存活服务、原始文件及实际磁盘余量尚未重新核验；本次没有工作站写入。源码可以作为准备成果集中提交，但正式启动仍须 SSH 恢复、只读库存核验及用户明确批准新 V17 六小时窗口。

### 已实现入口与批准后命令模板

以下是既有 CLI 的真实参数模板，不代表已经执行。先在已指定工作站目录、资格化 activation 下，由主控登记用户批准的 authorization；不得在未批准时运行 `--prepare`，因为它会冻结新窗口。

```bash
python -m src.runners.task41_p0_contract --prepare --case B0 \
  --runtime-prefix benchmarks/artifacts/task40extra_0p7nm_engineering/local_w0_wsl/runtime_prefix \
  --abi-receipt benchmarks/artifacts/task40extra_0p7nm_engineering/local_v29_wsl/abi_receipt_v29_attempt2.json \
  --jit-cache benchmarks/artifacts/task40extra_0p7nm_engineering/local_v29_wsl/jit_cache \
  --b0-saved-diagnostics-6h \
  --b0-saved-diagnostics-instance v17_selected_two_cell_replay_6h
```

先核实这些既有 runtime/ABI/JIT 路径与工作站当前合同一致。prepare 返回的 `service_command` 是首跑权威命令，包含真实 contract、固定 V16 manifest/hash 和新窗口 attempt01，直接交既有 `scripts/run_case_in_user_service.sh`。service 再生成 worker 命令、只读 checker 命令及 closeout 授权；禁止以裸 worker/checker 代替监督。

partial 续作在同一 service 命令上绑定实际旧文件：`--v17-producer-contract PATH --v17-producer-contract-sha256 SHA --v17-producer-progress PATH --v17-producer-progress-sha256 SHA`；已有完整 report 再加 `--v17-producer-report PATH --v17-producer-report-sha256 SHA`。新 `--output-dir` 必须是同窗新的编号 attempt，不能覆盖旧报告。这些 PATH/SHA 只有实际运行产生后才能填入，不预造 attempt 或 hash。

expected-file 范围：V16 frozen manifest/metadata、V9/V15 y/g、V3 两列 known/native full/native volume RHS/active rows/Balpha；每个新 cell 的有序坐标/I/T/E、raw/oriented、LU/pivots/R/T/S；四个 RHS 的同次 z0、最多两步 residual/delta/z、终态 z/correction；progress、worker report、独立 checker 与监督回执。两个 cell 的矩阵/因子载荷推导为 74,684,304 B，映射、状态、NPY headers、JSON、scratch 另计；新增≤128 MiB、累计≤16 GiB、自由空间≥2 GiB必须按现场真实库存准入。FE 准备 workspace 预留与实际 RSS 不混称。
