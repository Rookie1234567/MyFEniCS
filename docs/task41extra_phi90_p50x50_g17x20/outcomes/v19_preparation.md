# Task41 Review V19 准备记录

**当前状态（2026-10-29）：V19 合成 service/checker 路由及历史证据账本定向验证完成；尚无新数值证据。** 本记录只记录 Review V19 的准备状态，不创建 window、authorization、T0 或正式 attempt。

## 范围与冻结身份

- 唯一当前范围：Review V19 两个单元（cells 7873、8014）、原 known 两列的独立 native rank-1 与原 scatter/MPC/组件合并来源。禁止扩展到 rank-2、LU、GETRS、恢复、全域 native action、200q 或 FGMRES。
- canonical 分支：`task41extra_phi90_p50x50_g17x20`；准备 base：`bb4649a1f7569a1438ba6268d23b792bbc6d7892`；冻结提交由主控提交后回读登记。
- V18 已完成并以 `LOCAL_MIXED_NOT_QUALIFIED` 收口；其 closeout 和 response 保留为历史证据，不能当作 V19 的授权或数值结果。
- V19 的 6 小时窗口（21,600 秒；数值 20,400 秒；收口 1,200 秒）尚未获用户批准。本轮不创建窗口/T0/auth，不执行 FE/native capture。

## 已有实现与发现

- `src/runners/task41_p0_v19_native_rank1.py` 的窄 rank-1 DOLFINx 抽取器已接入注册 saved-output service 与只读 checker 路由；接线仅经合成 fixture 验证，不能据此声称已取得数值证据。
- `FullspaceMpcFormAction` 增加了从真实 action form、function space、constants 与 coefficient packer 进入逐核回调的接口；原输出的 MPC 限制转置提取成共用 helper。`FullspaceSplitVolumeAction` 增加了逐组件捕获入口，仍保持 curl、material_mass 分别处理后再 `curl_result.axpy(1, mass_result)`。
- fixture 已走 split action → form-action capture callback → DOLFINx rank-1 adapter → 每项原子保存，覆盖两个 C++ integral index 与非连续 UFCx physical id、反序 entity 顺序、非连续原系数位置、`T_apply` 和复数输出。另一 fixture 覆盖非 Hermitian MPC 下分量各自限制后再合并。
- 两项当前定向 fixture 已在资格化 activation 下通过（2 passed，0.76 s）；仅 fake FFCx kernel 执行，未启动真实 native kernel 或 FE。
- 主控指出 kernel 输出调用数必须由 hash-bound donor 的真实积分清单推导，并逐项核对；不能用固定 `rank1_kernel_outputs_max=16` 截断合法 default/tag 核。该动态清单绑定及计数校验现已实现，并覆盖 tag 子集和空积分实体；早期发现保留于此。
- 主控审查发现并要求修正的 API/次序问题：使用工作站实际 Form `domains(type, index)` 与 C++ integral index；验证其与 UFCx physical integral id 的映射；使用 `FiniteElement.T_apply` 表示 `standard` test transformation；按原 integration entity 顺序过滤所选 cell；CFFI 指针按已知范围显式读取；coefficient pack 字节必须用 UFCx coefficient 数与原系数有限元维数推导并与真实 pack 核对。
- DOLFINx 0.10.0 本地头文件核验了 `assemble_vector_impl.h`：每个 cell integral 使用 `L.num_integrals(cell,0)` 的循环 index `i`，调用 `L.kernel(cell,i,cell_type_idx)`、`L.domain(cell,i,cell_type_idx)` 及 `coefficients.at({cell,i})`，最后应用 `dof_transformation_fn(standard)`。服务必须保留 curl/mass 分别装配和各自 MPC/ghost 处理后再 `axpy` 的顺序。

## 初始准备阶段记录（历史）

- 资格化本机 ABI preflight 通过：仓库 `.venv` Python，`_MYFENICS_WSL_QUALIFIED_ACTIVATION=1`，PETSc complex128/int32，DOLFINx 0.10.0.post2，Basix 0.10.0。该环境不是工作站历史 ABI 回执。
- 当时尚未完成真实 CLI/service/router、worker loader/serialization、只读 checker/接续三项定向回归；后续进展见下方日期记录。
- 未启动正式服务、未调用 V19 native capture、未重跑或重建任何已保存数值输入；未 commit/push。

## 2026-10-29 V19 service/checker 路由收口

- 修复 V19 合同 raw-artifact cap 的精确 scope 识别；watchdog 对输入路径与 SHA 做有序成对去重，并拒绝同一路径的冲突 SHA。service 的 checker 失败状态保留 `READ_ONLY_RECEIPT_BOUND`，worker 已完成时保留 `CAPTURE_COMPLETED`。
- V18 既有账本按原始来源区分执行源码 `ff22c0a78099e7e48e0c11127ce01e06ae1ac8cf` 与窗口 entry source `880fea2fca11f575b1234c6e1bb64442d70f30f7`；固定窗口 SHA `3d4158d70782f9789a997ecadac073f9ea2e7be104dc789e66c0758d45aee113`。UTC 纳秒字段以 `_utc_ns` 等值核验，不因格式精度不同误判。
- `src/test/test_task41_p0_v19_service_route.py` 通过真实 `watchdog.supervise` 到 V19 checker CLI 的合成 service-route fixture，覆盖初次负报告、只读复核不重跑 worker、坏外部 receipt hash/scope fail-closed、只读 receipt 绑定后的 checker 失败状态。路由测试：**2 passed in 9.44 s**。`src/test/test_task41_p0_v19_checker.py` 与 `src/test/test_task41_p0_v19_native_rank1.py`：**24 passed in 1.10 s**。
- 曾把三份测试合并在一个 pytest 进程中执行，结果 **1 failed, 25 passed**：route fixture 要求 watchdog 在无既存子进程的专用父进程中运行；独立执行 route 文件通过，checker/native-rank1 成对执行通过。此失败是该集成夹具的进程隔离要求，不能报告成全绿。
- 最终改动后的资格化 ABI preflight 通过：项目 `.venv`、`_MYFENICS_WSL_QUALIFIED_ACTIVATION=1`、PETSc 3.19.6 complex128/int32、SLEPc 3.19.2、DOLFINx 0.10.0.post2、mpi4py 与 Open MPI 4.1.6。所有本轮运行仅为合成 route/worker 和只读 checker 测试；没有实际授权窗口、T0、正式 service、FE/native capture 或新数值结论。没有 commit/push；当前执行分支 HEAD 仍为 `bb4649a1f7569a1438ba6268d23b792bbc6d7892`。保留未跟踪的 `pelican_bicycle_animation.html`，不得纳入本任务。



## 2026-10-29 worker 接续校验

- 主控最新人类任务指令已核实为 Review V19；V18 的 `LOCAL_MIXED_NOT_QUALIFIED` 仅作为已接收的历史结论。执行分支仍为 `task41extra_phi90_p50x50_g17x20`，HEAD `bb4649a1f7569a1438ba6268d23b792bbc6d7892`；本轮变更尚未提交。
- 修复完成回执过早返回：worker 现在会重新构造本轮所需 action/输入身份，逐项重开保存 kernel term；progress 中已登记的 archive SHA 必须匹配，归档成员还须与新鲜输入身份及内部数组身份一致。只有当前 contract/window/donor/source、map/MPC、动态积分清单、组件与 term/archive 引用全部和新构造的回执身份吻合时，才复用原完成回执。已有回执不匹配会 fail closed；不会因断点重开重写回执或重跑已验证 kernel。
- run identity 现在绑定当前两个 split action 各自的 bilinear/rank-1 UFL signature、FFCx `Form.code` 摘要、可读取时的 compiled-module 文件 SHA、JIT options、Python/FEM/PETSc/SLEPc/MPI ABI，以及 C++ integral index、UFCx physical id 和完整 entity 顺序。该双组件 identity 和 integral inventory 在任何 kernel 调用前写入 checkpoint；每项 term identity 绑定 component kernel identity 与 integral 清单 SHA。没有身份的旧 progress 若已有 term 会 fail closed。
- V3 历史 donor 与本次重建的 capture identity 分开记录；pinned closeout 没有历史 JIT/module hash，因此明确记为 `UNKNOWN_MISSING_FROM_PINNED_V3_CLOSEOUT`，不宣称 bitwise replay。V16 loader 到 active/original row、两列 known-field shape/dtype/bytes 的 layout gate 补齐 `TRACE_ROWS` 常量并加纯 fixture；action 构造后的验证与保存现在由 cleanup guard 覆盖。
- 新增 synthetic fixtures，分别覆盖 module/C、UFL、JIT、ABI identity 改变，积分清单改变时在 pack/kernel 前拒绝，旧 progress 的 fail-closed、V16 双列 layout 以及 action 异常清理。资格化 activation 下 ABI preflight 通过（PETSc complex128/int32；DOLFINx 0.10.0.post2、Basix 0.10.0、UFL 2025.2.1、FFCx 0.10.1.post0）；整个 V19 worker 定向文件为 **11 passed in 0.73 s**。Ruff 模块不在该环境内，本轮未安装依赖。所有 kernel 执行均来自 synthetic fixtures，没有真实 FE/native capture。
- 尚未完成注册 service/router 和独立只读 checker/closeout 链路；本轮只收口 worker 接续校验。尚无 V19 authorization/window/T0；没有启动 service、真实 FE/native capture 或其他科学运行。未修改 V18 证据、未 commit/push。

## 2026-10-29 独立 checker 短步骤

- 新增 `src/runners/task41_p0_v19_checker.py`：只读重开外部 SHA 固定的 worker receipt、progress checkpoint 和逐项 NPZ term archive；逐成员验证整体归档 SHA、dtype/shape/content identity、六个 fresh input/map identities、动态 C++ integral/UFCx physical-id/entity 顺序、V17 map/tensor 引用及 V3 donor 向量。checker 不建 FE form、不调用 native kernel、不组装 rank-2、不 factor/solve。
- 归档只在 checkpoint 的 `archive_sha256` 与 receipt、文件字节及全部 member references 一致时标为 `CHECKPOINT_SHA256_VERIFIED`。无 checkpoint 的孤立原子包明确标为 `ORPHAN_ATOMIC_ARCHIVE_INTERNAL_IDENTITY_ONLY`，报告保留该条目但完整性不成立。任何 member 与整体归档 SHA 不一致均保留完整负报告，不提前抛出通用异常。
- 数值审计保留 `audit_completed`、`data_complete`、`native_binding_status`、`original_action_status` 和 `official_result` 的独立分类。选中行或900个内部行与保存的 native volume RHS 不逐位匹配时，绑定状态为 `NATIVE_REPLAY_UNBOUND`，原因 `NUMERICAL_MISMATCH`；不把可读取数据或完整诊断误称为数值通过。
- Decimal 80/100 位下，A 从原 binary64 J/L 与 interior/trace 输入分别重新计算；Q 到原序分量 scatter 及最终 `curl_result.axpy(1, mass_result)` 分成三个带符号段。full RHS 同时报 `b_full-b_volume-b_alpha` 和先执行 `b_volume+b_alpha` 再与 full RHS 相减的 binary64 值，保留两种括号顺序。
- 定向测试覆盖真实写入/重开、重签内部 member identity 但外部 archive SHA 过期、孤立归档不升级绑定、动态积分实体顺序错位、缺 receipt 时完整负报告、坏 archive 后继续诊断但 binding 仍为 UNBOUND，以及 `10^50 + 1 - 10^50` 在 80/100 位重算中保留小项。数值不匹配 fixture 保持 `data_complete=true`，逐列和总报告均写为 `NATIVE_REPLAY_UNBOUND` / `NUMERICAL_MISMATCH`。worker 的 receipt SHA/member SHA 不一致也有拒绝用例。资格化 activation ABI preflight 通过（PETSc complex128/int32、SLEPc 3.19.2、DOLFINx 0.10.0、Basix、mpi4py 与 Open MPI 4.1.6）；checker + worker 定向测试 **19 passed**。
- 真实 V17 ignored report/maps/tensor 和 V3 vectors 在此 checkout 不齐，未运行真实 checker 数值审计；故没有数值捕获、结论或 source binding。service/router 仍未接线；接线步骤还需用窄 `perf_counter` 记录实际父阶段、native kernel 调用、方向处理和系数 packing 耗时，不能用 V17 历史成本代替。此短步骤没有创建/修改 authorization、window、T0 或 attempt，没有启动 FE/native service，也没有 commit/push。

## 当前总状态（2026-10-29，优先于前述阶段性记录）

- 随后的 V19 service/checker 路由已通过合成集成验证：路由文件单独 **2 passed in 9.44 s**；checker 与 native-rank1 两文件 **24 passed in 1.10 s**。一次把三文件合并到同一 pytest 进程的尝试为 **1 failed, 25 passed**，原因是 watchdog 集成 fixture 要求专用且无既存子进程的父进程；不得把合并运行表述为全通过。
- 可复核的定向命令应分成两个独立 pytest 进程，并先在每个新 shell 中完成资格化 activation 与 ABI preflight：

  ```bash
  cd /home/shenjh/Projects/MyFEniCSx_task40extra_0p7nm_engineering && source scripts/activate_myfenics_wsl.sh && python -m pytest -q src/test/test_task41_p0_v19_checker.py src/test/test_task41_p0_v19_native_rank1.py
  ```

  ```bash
  cd /home/shenjh/Projects/MyFEniCSx_task40extra_0p7nm_engineering && source scripts/activate_myfenics_wsl.sh && python -m pytest -q src/test/test_task41_p0_v19_service_route.py
  ```

  不要把三个文件合并进同一 pytest 进程；service-route fixture 要求其 watchdog 在专用、无既存子进程的父进程中运行。这是测试隔离约束，不应放宽生产 watchdog guard。
- 最终改动后的资格化 ABI preflight 通过（PETSc 3.19.6 complex128/int32、SLEPc 3.19.2、DOLFINx 0.10.0.post2、mpi4py/Open MPI 4.1.6）。所有验证仍是合成 worker/service 路由和只读 checker；没有真实 V19 numerical capture、正式 FE/service、授权窗口、T0 或新数值结论。V19 route 已接入的状态以本节及上方 service/checker 路由记录为准；前述 worker/checker 阶段的“尚未接线”是当时记录。
- 工作树没有提交或推送；分支 `task41extra_phi90_p50x50_g17x20` 的 HEAD 仍为 `bb4649a1f7569a1438ba6268d23b792bbc6d7892`。保留未跟踪的 `pelican_bicycle_animation.html`，不得纳入本任务。


## 主控最终复核与获准后命令

主控在相同资格化本机环境复核：合并三文件为 25 passed / 1 failed（1.73 s），首因 `watchdog must be a dedicated parent with no existing children`，未启动 capture worker；单独运行 service-route 为 **2 passed / 9.43 s**。保留这次测试隔离负结果，生产 watchdog 不变。`bash -n scripts/run_case_in_user_service.sh` 与 `git diff --check` 通过。此处的秒数是工程测试成本，不是科学核耗时；前期工程总父时钟未完整记录，保持 UNKNOWN。

以下为已实现的 CLI，只在用户批准 V19 新窗口、主控登记真实批准并冻结源码、工作站旧草稿已原样备份且同分支安全同步后运行。prepare 会核验独立授权文件；没有授权不能生成新科学窗口。旧 V18 source/window 和原始文件不改写。

```bash
cd /home/fenics/Projects/laptop_share
runtime="$PWD/benchmarks/artifacts/task40extra_0p7nm_engineering/local_w0_wsl/runtime_prefix"
abi="$PWD/benchmarks/artifacts/task40extra_0p7nm_engineering/local_v29_wsl/abi_receipt_v29_attempt2.json"
jit="$PWD/benchmarks/artifacts/task40extra_0p7nm_engineering/local_v29_wsl/jit_cache"
unset _MYFENICS_WSL_QUALIFIED_ACTIVATION
source scripts/task40_fresh_c1/activate_native_complex.sh "$runtime" "$abi" "$jit" native_linux
export PYTHONPATH="$PWD" PYTHONDONTWRITEBYTECODE=1
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
mkdir -p benchmarks/artifacts/task41extra_phi90_p50x50_g17x20/v19_controller
python -m src.runners.task41_p0_contract --prepare --case B0 \
  --runtime-prefix "$runtime" --abi-receipt "$abi" --jit-cache "$jit" \
  --b0-saved-diagnostics-instance v19_selected_native_rank1_6h \
  > benchmarks/artifacts/task41extra_phi90_p50x50_g17x20/v19_controller/prepare.json
python - <<'RUN_PREPARED_SERVICE'
import json, subprocess
from pathlib import Path
p=Path('benchmarks/artifacts/task41extra_phi90_p50x50_g17x20/v19_controller/prepare.json')
prepared=json.loads(p.read_text())
command=prepared['service_command']
assert command[:2] == ['bash', 'scripts/run_case_in_user_service.sh']
assert '--task41-p0-b0-v19-native-rank1' in command
subprocess.run(command, check=True)
RUN_PREPARED_SERVICE
```

prepare 产出的真实 service 命令绑定 B0 DAT、当前 source 的执行合同及当前窗口输出目录，不手工拼接假 hash。worker/checker 子命令由现有 service 生成并写进回执；checker 使用独立 watchdog，不裸启动。

已完成 capture 而仅 checker 失败时：保留原 receipt/archive/producer contract，重新 prepare 当前 consumer source（同一批准窗口，T0 不刷新），在其 `service_command` 后追加下列已实现参数，再经同一 wrapper 执行：

```text
--task41-p0-b0-v19-checker-only --v19-receipt-path <原完成worker回执绝对路径> --v19-receipt-sha256 <该文件真实SHA256>
```

路径与 SHA 必须来自已完成 attempt 的回执，不以新造文件代替。该路由不调用 worker、不建 FE/form、不重新取证。完整捕获和独立审核完成分别报告，`NATIVE_REPLAY_UNBOUND` 不升级为科学 PASS。正式窗口/批准、实际工作站启动、科学耗时与内存均仍为 NOT_RUN；源码冻结不等于科学资格。

## 获准启动时的命令修正

用户已明确批准本轮六小时取证。主控示例错误地同时传入 legacy `--b0-saved-diagnostics-6h` 与 named instance，首次 prepare 按互斥规则拒绝；没有触发科学 worker，也未因此刷新 T0。正确命令仅保留 `--b0-saved-diagnostics-instance v19_selected_native_rank1_6h`（上述示例已修）。固定 T0 为 `2026-10-29T06:58:54.288229236Z`，数值/总截止为 `12:38:54.288229236Z` / `12:58:54.288229236Z`。冻结科学 source 为 `5c764ec2677087a0e3bf9641ab29470a398b86c4`；本条仅修改本机文档，不热改工作站数值源码。

## 同窗 wrapper 窄修

首次正式服务 `myfenics-case-20261029T070552-3773295.service` 在 systemd 子 shell 的 `set -u` 处退出：`task41_v19_checker_only` 未初始化。外层有变量，内层缺初始化及 receipt 参数解析；尚无 worker/FE/native 产品，旧日志与费用保留。修复仅补内层解析和校验，数学代码不变。新增实际执行内嵌 shell 的 capture/checker/default 三条 fixture，主控资格化本机复核 **3 passed / 0.07 s**；bash 语法及 diff 检查通过。另一次执行者误在本机使用工作站 runtime 路径的 preflight 失败保留，未迁移/重装环境。新 source 重新 prepare 合同，原 window/T0/截止和授权不变。

## 同窗 native IntegralType 导入修复

冻结 `f8be458c9437d8be916cd33dc17e4633ec2297a9` 的服务 `myfenics-case-20261029T072200-3777733.service` 已越过 wrapper，在 worker 导入阶段因 `dolfinx.cpp.fem.IntegralType` 不存在而退出，未建 FE、未执行 native 核。worker watchdog 耗时 4.305215 s；service CPU 7.599906 s，父墙钟约8秒，口径不同不相加。改用公开 `dolfinx.fem.IntegralType.cell`，数学和资源合同不变。新增公开 namespace fixture 为 **1 passed / 0.65 s**；早一次 ABI 断言未正确门控的测试不计资格，修正 preflight 后同 shell 重跑通过。主控在工作站原 native activation 中额外执行 imports-only 检查，公开 cell enum 实际可用。原 libibverbs 编译路径 warning 保留，不冒充本轮 FE 结果。旧失败和原 T0/window 保留，修复源码冻结后同窗接续。

## 同窗 worker 导入闭包修复

服务 `myfenics-case-20261029T073009-3780685.service` 在导入未定义的 `TASK41_P0_B0_V16_V3_VECTOR_INDEX_SHA256` 时退出，无 FE/native 产品。修正为既有 `TASK41_P0_B0_V3_VECTOR_INDEX_SHA256`，真实 index SHA `332b9e5ed553916808cceccd92542b5086cbdbeaaa298d42d95d18916bb7ade3` 不变。imports-only 闭包检查同时发现 metadata helper 的错误模块路径，改为其真实定义模块 `src.solvers.hcurl_assembly_time_condensation`；无数学变化。worker 全部 from-import 与公开 enum 两项定向回归 **2 passed / 0.99 s**，不运行 worker/FE。旧失败回执保留，窗口不刷新。

## 同窗 NPY 文件/载荷口径修复

服务 `myfenics-case-20261029T073557-3782505.service` 在 FE 前 known-field layout 校验退出。真实两列 NPY 文件均为296,016,512 B，数组载荷296,016,384 B，mmap offset128 B；旧校验错误地要求文件大小等于数组载荷。原 donor loader 的文件SHA/size与header校验保持，新 layout 明确核验shape×itemsize、payload及offset+payload=file bytes，active/original映射不变。抽出的FE前checkpoint helper由真实worker调用，坏shape/dtype/file size/map在写checkpoint前拒绝。主控在本机资格化WSL activation下验证 **1 passed / 0.71 s**，未调用FE或native。执行者误用工作站独立prefix要求判断本机环境不可用的记录不作为真实ABI失败；主控实际preflight为complex128/int32且项目`.venv`。旧失败和成本保留，原窗口不刷新。

## 同窗 FFCx cache-hit 身份修复

服务 `myfenics-case-20261029T074947-3786283.service` 已通过原保存输入/layout，完成mesh/maps与form准备；在记录 `Form.code` 身份时失败，未pack或执行rank-1核，checker未运行。worker约85.49 s，tree RSS峰3,137,302,528 B、watchdog cgroup峰3,152,048,128 B，task swap峰0；systemd独立MemoryPeak口径另存，不能与watchdog混称。读取工作站已安装FFCx源码确认缓存命中合法返回 `(None,None)`。新分支仅接受该精确sentinel，并绑定非空配对C源码、module路径及真实哈希，返回源码与缓存源码哈希口径明确分开；partial-None、缺C、错module、无法hash仍拒绝。checker同步独立校验序列化身份。

主控首次两文件定向测试23 passed/5 failed（1.46 s）：旧fake模块无文件，触发新HASHED门。补synthetic fixture真实可hash文件后最终 **28 passed / 4.18 s**；生产门未放宽。执行者沙箱MPI socket preflight受限未启动pytest，主控使用已资格环境和许可的本地socket运行验证，不重装环境。旧失败、窗口和成本保持；本修复无数学变化。
