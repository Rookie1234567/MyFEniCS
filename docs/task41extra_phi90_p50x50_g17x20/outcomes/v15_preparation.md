# Task41 V15 P0 已完成：待批准36h全域验收窗口

本文件记录启动前只读核验，未建立 V15 T0、授权文件或正式运行。任务仍为 Task41，canonical 目录保留历史 Task40 名称。

## 身份与现场

- 本机及工作站 HEAD：611f3497c4b977b10e783444bcd9c9a8aea9a9c5；Task41 分支。
- Review SHA256：35f0d6c9caa9d85044aac7a5382f9f344b51f550b62fdfd3ab543c1565d557b8。
- 只读现场快照：2026-10-25T12:32:00Z，fenics-ws01。
- 工作站总物理内存 2163100385280 B，可用 2031860932608 B；磁盘可用 2013804806144 B。
- task cap 1649267441664 B，host reserve 68719476736 B，task reserve 0。实际服务尚未创建，不能将 SSH 进程的 swap=0 当作正式 task PASS。
- 宿主与祖先 cgroup 存在约 0.94 GB 旧/其他任务 swap；保留该事实。新 task 必须独立 MemorySwapMax=0 且全树 swap=0。
- 未发现活动 Task41 服务。其他工作站任务未停止或修改。

## 证据配额

历史合同的 16 GiB 累计 raw 数组范围，不是全部 results 目录，也不包括已存在的大 carrier；不能把所有 A1/A2 文件加入新范围，或漏掉后续同范围负结果。

| 范围 | 实读字节 |
|---|---:|
| 冻结 donor + V6 + V7 | 14622146704 |
| V8 完整 star | 154632208 |
| V8 counterfactual | 13085472 |
| V9 两份 action NPY | 368135936 |
| 保存诊断 V12/V13/V14 根全部 NPY | 76896992 |
| 当前累计 | 15234897312 |
| 16 GiB 剩余 | 1944971872 |

旧六向量布局预留 2144274944 B，当前不够。Review 允许的终态充分布局纯载荷 1552201216 B，剩 392770656 B 给 NPY 头、manifest、必要失败块与其他本范围证据。新的原始证据 ceiling 必须连历史累计一起检查。计数、path/inode 去重与实际输出的绑定须在正式入口再次核验。

旧 V9 watchdog/resources.jsonl 为 1567050985 B，mode manifest 为 72687587 B；它们与 raw 数组口径分列，磁盘预算必须包含。本轮不能降低监督采样、删除历史或声称日志免费。完整 donor/hash 资格尚未在本轮重读；目前只是文件 stat，不是科学复核。

## 内存与时间

526373172000 B 是 K/J/LU/R/T/S 局部保留载荷推导，不是 RSS 或全对象需求。正式准入还须加入当前 FE/MPC/native、映射和元数据、共享参考表、donor 驻留页/哈希缓冲、两个 B 帧、action/recovery 工作区、输出和独立 checker；每阶段读取实时 host/task/ancestor，不能沿用本快照直接放行。

可用旧 V9 阶段作校准，不能冒充本轮测量：

- exact full admission 旧 additional=435527080128 B，workspace=247527432 B，projected RSS=444056850632 B。
- compact action/recovery workspace=1734217216 B；独立 checker workspace=592032768 B。
- prefix prepare workspace=1126516744 B；surface mapping/pairing workspace=1618840704 B。
- 本轮新增 K=90720000000 B，实际通过容量公式和当前对象清单重算。

时间情景沿 Review：旧 owner 父成本约18.95h；两列 action 和两列初次恢复的四轮 fsum RHS 另为13104–20496s，合计约22.59–24.65h，尚不含全部 native、保存、checker、清场。不能用该情景作完成承诺，不能重复相加旧 workflow 父子费用。

新窗口拟129600/128400/1200秒，仍待用户明确批准；正式准备从新 T0 计费。本 P0 开发、imports-only ABI 与小 fixture 另列工程费用。默认成功出口仅全域验收。条件下游若尚未通过接线/完整共驻账，不宣称已经就绪。

## 已完成工程核验

- 原 activation imports-only：complex128/int32/MPI1，OMP/OpenBLAS/MKL线程均1，runtime/库均来自工作站原资格化路径。
- 合同两 fixture：2 passed in 0.43s；补丁 SHA256 4146506705ec0ae7f3a5017111443e5a8fe38931f0783753a92e7d5090051da6。
- 无正式 FE、owner、200q、factor 或 target 运行。

本记录已完成最终代码与命令核验；它不能作为 response_v15 数值结果。

## 接线阶段定向测试（工程记录）

第二单元快照补丁 SHA-256：`ee57ebaec37855928ddf76dedd774e75a879766300e24332db6a3eb68387683a`。原工作站 activation 下，合同、缺授权不创建窗口、严格 full-owner scope、跨 attempt 单次 claim、构建后身份审核失败仍保留清理引用、service selector、实际输出目录绑定共7项：`7 passed in 2.01s`。直接受影响的旧V9 dispatcher 参数回归：`1 passed in 0.46s`。

日志取回合并 SHA-256：`3a0ae727f41a17b0b55e873b5983114578dc9c65c20890cbcf288fd22998f233`；工作站原日志 `/tmp/task41_v15_p0_unit2_tests.log`、`/tmp/task41_v15_p0_dispatch_regression.log`。这些小测试没有建立FE或正式窗口，不能称为全域科学资格。最终新增的 compact/checker 和真实调用链须在冻结前另行完成对应检查。

输出路径保护采用实际创建后绑定：service先核新scope/source/window；launcher实际分配run目录后，把精确绝对路径传入worker环境；dispatcher继续核对目录、parent、containment和环境一致。没有删除旧exact-output守卫。

一次构建额度在真实builder调用前原子保存`BUILD_STARTED`，以固定window的claim路径限制全部attempt；service注册本身不耗额度。构建开始后的失败仍保留额度占用；修改attempt名不解除。若owner已经返回而后续身份/回执写入失败，先注册清理引用，不能丢失对象所有权后假称已释放。

## 当前执行边界

- V15正式新窗、授权文件、全域owner、action和recovery均未运行；旧V14窗口不复活。
- 默认只到全域两列验收和独立审核。`official_result=false`；全域旧V9 action FAIL不改判。
- 本文是准备记录，不是`response_v15.md`或运行许可。完成P0后由用户明确批准新36h；实际启动会重新读取内存、磁盘、任务与祖先cgroup和source状态。
- 不将已接受的两个star局部改善作为全域PASS，不以工程fixture计数替代数值进展。


## 最终P0结果与边界

本次把既有保存数据审核扩展为全域验收收口：每列新y/g先保存，再判门；仅两列action通过才恢复。新终态布局保存两列最终场及独立native作用，以旧RHS减新作用重算残差，避免多存相同全长残差。它减少证据磁盘载荷，不改变数学运算、精度或误差门。

新合同统一绑定scope、refinement=2、actual K/LU同源、实际run目录和一次owner额度。旧saved-only合同仍拒绝全域构建。全域验收出口位于carrier读取之前，完成callback后直接转受监督终态审核，不继续64,120模式扫描或200q。源码、合同、保存文件hash、独立审核和清理状态分开记录。

- 最终工作站定向回归：**31 passed in 7.42s**；日志及SHA见[v15_preparation/preparation_record.json](v15_preparation/preparation_record.json)。测试patch SHA为`1b4fa69e92c0109e9478478670816e0da89225d6af124ed6f8c649a451e54faa`，基于Review HEAD；提交中数值源码与该patch一致。
- 真实prepare→scope/一次claim→小compact producer→本run独立终态审核调用链通过；昂贵FE/数组用小fixture替身，未声称全域运行。另覆盖PASS、action FAIL、recovery FAIL、部分产品、缺物理输出目录，以及旧V9布局、V14策略与清理兼容。
- 合同/命令到真实watchdog的closeout授权检查通过；错误selector/input hash仍拒绝。审核完成不自动代表数值PASS；producer/required-checker的swap和后代清理不合格不能标验收通过。
- 早期fixture失败及源patch、日志保留。最终修正了checker把完整storage行数误当trace+port行数的检查、局部导入、零向量布尔比较，以及终态service输出位置等工程问题，未改变科学门。
- `bash -n`、`git diff --check`及实际prepare/checker帮助入口通过。未跑全仓、未重积分或建立全域owner；无CI声明。

最终时间准入在唯一正常构建的首批已生成key之后，使用其排他成本投影剩余构建，再加四个RHS补偿残差情景20,496s和其他action/native/恢复/保存/checker的14,400s计划预留，与真实数值余额比较。后者是保守计划量，**不是实测上界，也不是新增4h阶段终止线**。沿途实时监督与固定截止仍有效。

compact工作空间按最多16份full-storage向量的保守载荷加活动向量计入，独立checker另有工作区准入；全部局部对象的构建公式已包含保留原K。实时RSS/cgroup、文件页和FE/native等实际常驻继续由原gate采样，不将526.37GB派生载荷当完整RSS。

物理磁盘额外保留4GiB监控日志、256MiB元数据及1.9GB新raw上限，再保留2GiB空闲底线。4GiB来自旧约1.57GB/19.44h日志的保守36h情景，不是实测；日志与raw16GiB口径分列。实际raw剩余1,944,971,872B可容终态纯数组1,552,201,216B及头/有限失败证据，正式启动前再次stat核验。已有负结果不删除。

## 实际入口（批准后由主控使用）

以下均是已实现并通过CLI/调用链核验的入口。当前尚无V15正式授权JSON、window或run，不能预填未来hash或假造T0。用户批准后主控按既有schema原子登记`full_acceptance_v15_user_authorization.json`，绑定当时clean source、原V14窗口/账本hash和首项正式准备时间；再执行prepare，直接使用其返回的`service_command`与合同hash。普通修复不刷新该窗，BUILD_STARTED额度不因attempt名变化清零。

```bash
cd /home/fenics/Projects/laptop_share
source scripts/task40_fresh_c1/activate_native_complex.sh \
  "$PWD/benchmarks/artifacts/task40extra_0p7nm_engineering/local_w0_wsl/runtime_prefix" \
  "$PWD/benchmarks/artifacts/task40extra_0p7nm_engineering/local_v29_wsl/abi_receipt_v29_attempt2.json" \
  "$PWD/benchmarks/artifacts/task40extra_0p7nm_engineering/local_w0_wsl/jit_cache" native_linux
python -m src.runners.task41_p0_contract --prepare --case B0 \
  --b0-saved-diagnostics-instance v15_full_two_column_acceptance_36h \
  --runtime-prefix "$PWD/benchmarks/artifacts/task40extra_0p7nm_engineering/local_w0_wsl/runtime_prefix" \
  --abi-receipt "$PWD/benchmarks/artifacts/task40extra_0p7nm_engineering/local_v29_wsl/abi_receipt_v29_attempt2.json" \
  --jit-cache "$PWD/benchmarks/artifacts/task40extra_0p7nm_engineering/local_w0_wsl/jit_cache"
```

prepare返回的实际service命令使用原DAT及新selector：

```text
bash scripts/run_case_in_user_service.sh input/task41extra_phi90_p50x50_g17x20/b0_p6_07nm_iterative.dat --task41-p0-execution-contract <prepare返回的精确contract_path> --task41-p0-b0-v15-full-acceptance
```

同一service自动生成并由watchdog监督required checker，参数中的path/hash来自实际run，而非成功物理目录：

```text
<qualified runtime>/bin/python -m src.runners.task41_p0_checker --v15-terminal-audit --run-root <实际run> --summary <实际run>/task40_v10_p6_candidate_summary.json --manifest <实际run>/run_manifest.json --contract <同一合同> --contract-sha256 <同一hash> --output <合同service_directory>/task41_p0_checker_result.json
```

不手动裸启动checker，不用旧V14命令。若全部两列通过，标`FULL_ACTION_RECOVERY_QUALIFIED`，仍`official_result=false`。本次待批准出口仅全域验收，随后按合同清场；未来下游重建的费用风险保留，未声称200q/完整reference/target已准备或授权。工程开发总耗时没有完整连续父计时，保持UNKNOWN；31项测试7.42s仅是该测试进程父时间，不与正式成本混加。

## 2026-10-26 用户批准的一次接续构建

用户明确回复“授权”，批准错误JIT缓存导致的构建前失败后增加一次接续。原失败run `20261025T145135.719911Z`、BUILD_STARTED claim和费用全部保留。追加授权通过独立文件绑定旧claim、失败summary、原窗口和只做全域验收的范围；新claim使用固定独立路径和排他创建，更换attempt名不能再次取得额度。原窗口、数学策略、资源门不变，不启动200q。

最终5项定向回归通过（2.28 s），覆盖实际dispatcher→worker传递、旧默认、失败owner清理、授权hash/窗口/前序拒绝及仅一次接续。测试不是科学验收；本提交冻结时尚未启动新构建。补丁SHA256为 `fdca1e6a2252d7cfe400e6b22d5dee45d0c207b9f31080fb9bd7f7cedc1e8a3b`。

追加授权SHA256 `85981ba987a7515cd76c813034073f0eb09f133ef30acfa972d911a2e4cfa0c6`，旧claim SHA256仍为 `a35431d3fffc896b9ca8e909b60b2f269d8d94f22d0a96e2ed3ef4a60e5659eb`。2026-10-25 22:53 UTC按campaign API读得数值余额98772.9658625秒；这只是当时快照，正式prepare/启动须重新读取。授权文件中的时间为主控登记时间，非用户消息精确到达时刻。
