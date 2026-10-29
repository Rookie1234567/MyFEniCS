# Task41 Review V18 准备记录

**状态：代码准备与合成接线验证已完成，等待主控冻结和 V18 窗口批准。** 本记录不创建 authorization、T0、window 或正式 attempt，也不代表任何数值结果。

## 范围与验证

- 分支：`task41extra_phi90_p50x50_g17x20`；本轮开始时 HEAD 为 `042538b7ea8f0b0cae7ee59684d6badaefaa36e1`。
- 定向 fixture 实际调用 V18 service 分支、`produce_saved_jz_candidate` worker、watchdog 的 `_validate_campaign_closeout_authorization` 注册入口和真实 `check_saved_jz_candidate` checker。只替代 watchdog 的进程监督、fixture Git 身份及合同加载；候选报告、worker、授权字段验证和 checker 均未整体 mock。
- fixture 检查 16 个输入、每个完整 432 行 correction、两列 signed-D 分解、16 MiB package cap、非 official/global/full-owner 状态；改写 candidate SHA 后，watchdog validator 拒绝命令。
- 使用仓库资格化 activation 的命令及结果：

  ```bash
  source scripts/activate_myfenics_wsl.sh >/dev/null
  python -m pytest -q src/test/test_task41_p0_v18_service_route.py
  # 1 passed in 14.48s
  ```

这是本机合成接线测试，不是工作站 service、FE 或 PDE 运行。V18 六小时窗口仍待单独批准；V15 的 36 小时批准不被当作 V18 授权。

## 批准后可用的实际命令形式

先在主控冻结的干净源版本和已资格化环境中核对 runtime、ABI receipt、JIT cache，再由用户批准后创建一次 V18 contract/window/T0。该命令当前**未执行**：

```bash
cd /home/fenics/Projects/laptop_share
unset _MYFENICS_WSL_QUALIFIED_ACTIVATION
RUNTIME_PREFIX="$PWD/benchmarks/artifacts/task40extra_0p7nm_engineering/local_w0_wsl/runtime_prefix"
ABI_RECEIPT="$PWD/benchmarks/artifacts/task40extra_0p7nm_engineering/local_v29_wsl/abi_receipt_v29_attempt2.json"
JIT_CACHE="$PWD/benchmarks/artifacts/task40extra_0p7nm_engineering/local_v29_wsl/jit_cache"
source scripts/task40_fresh_c1/activate_native_complex.sh \
  "$RUNTIME_PREFIX" "$ABI_RECEIPT" "$JIT_CACHE" native_linux
export PYTHONPATH="$PWD" PYTHONDONTWRITEBYTECODE=1
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
python -m src.runners.task41_p0_contract --prepare --case B0 \
  --runtime-prefix "$RUNTIME_PREFIX" \
  --abi-receipt "$ABI_RECEIPT" \
  --jit-cache "$JIT_CACHE" \
  --b0-saved-diagnostics-instance v18_saved_jz_candidate_6h
```

prepare 返回的准确 contract/window 路径与 SHA 才是后续输入。对该 contract 取 launcher 值的只读形式为：

```bash
python -m src.runners.task41_p0_contract --launcher-values \
  --contract "$V18_CONTRACT" --saved-output-continuation
```

获得已批准 contract 后，服务入口的真实参数形式如下；`$V18_OUTPUT` 必须是 prepare 返回的全新编号 attempt，不能覆盖任何旧结果：

```bash
bash scripts/run_case_in_user_service.sh \
  input/task41extra_phi90_p50x50_g17x20/b0_p6_07nm_iterative.dat \
  --task41-p0-execution-contract "$V18_CONTRACT" \
  --task41-p0-b0-v18-saved-jz-candidate \
  --v18-output-directory "$V18_OUTPUT"
```

实际 closeout checker 命令由 service 以冻结 runtime 组装，形式如下；路径和哈希须从同一次服务生成的 candidate、replay、contract、window 中读取：

```bash
"$RUNTIME_PREFIX/bin/python" -m src.runners.task41_p0_v18_saved_jz_checker \
  --candidate-report "$V18_OUTPUT/task41_p0_v18_saved_jz_candidate.json" \
  --candidate-sha256 "$CANDIDATE_SHA256" \
  --replay-report "$V18_OUTPUT/task41_p0_v18_saved_jz_replay.json" \
  --replay-sha256 "$REPLAY_SHA256" \
  --contract-path "$V18_CONTRACT" --contract-sha256 "$CONTRACT_SHA256" \
  --window-path "$V18_WINDOW" --window-sha256 "$WINDOW_SHA256"
```

watchdog 的 V18 closeout 授权还绑定干净 source HEAD/branch、consumer/checker source SHA、该 contract/window SHA、完整命令 SHA，以及所有输入路径和 SHA。源码改变后不得冒用旧 source 的 checker 命令授权；主控须冻结新 source 并重建对应命令授权。用户一次批准的同一 V18 窗口和范围内，普通工程修复不要求用户逐次重新批准，不刷新 T0/deadline。旧 producer 的 source/window/hash 保持原样。

## 失败后的接续边界

worker 先保存 candidate/replay；独立 checker 随后写入 `task41_p0_v18_independent_check.json`。checker 的实际 Python API/CLI 可以读取已保存输入，但当前没有 V18 专用的 service checker-only selector，也没有可以重用既有 attempt 和原 closeout 预算的受监督续接命令。V18 service 入口要求新的、尚不存在的输出 attempt；把旧输出目录再次交给完整 service 会因输出身份/目录已存在而拒绝。直接调用上面的 Python checker CLI 虽可用于诊断重读，但绕过 systemd/watchdog 的计时和 closeout 授权，不能记作受监督 continuation 或正式终态。若真实运行出现“candidate/replay 已保存、checker 未完成”，保留所有证据并交主控处理；不得重跑数值 worker、覆盖文件或声称 checker PASS。

## 明确未运行

- 未执行 `--prepare` / `--launcher-values`，未创建实际 V18 contract、授权、window、T0 或 attempt。
- 未启动或监督正式 service；没有 FE、LU/GETRS 或 PDE 运行。
- 未 commit 或 push。主控可在终审时按此边界冻结或指出需要补齐的 service-only continuation。

## 主控接手核对

远端分支只读回读为 `042538b7ea8f0b0cae7ee59684d6badaefaa36e1`，本机工作目录仍为 canonical Task41 worktree。工作站 `fenics-ws:/home/fenics/Projects/laptop_share` 的 Task41 分支干净，准备核对时没有运行中的 Task41 user service；没有启动、停止或改动数值作业。

V17 最终库存回执已从工作站原路径回读：`selected_incident_replay/attempt07.service/task41_p0_service_receipt.json`，48,544 B，SHA-256 `d5c6f842fa55c1ac4f58dba23dce39d61dfe805d4f7844606b291f71139aa5d6`，与仓库 `outcomes/v17_closeout/attempt07_service_receipt.json` 相同。记录累计 15,603,033,504 B 加旧窗口已记录产物 77,936,866 B，合计 15,680,970,370 B；实际启动仍重新 stat 旧窗口产物并按保守值计入，新 V18 窗口另记，不把只读引用的字节数冒充整个历史库存。

当前没有受监督的 V18 checker-only 恢复 selector 是明确的接线限制，不是数值失败，也不允许据此重复生成已保存候选。若首场遇到真实审核/字段故障，主控只补受影响的只读调用，不重建矩阵或重新计算候选，不另开窗口。

## 主控冻结前定向复核（2026-10-29）

- 资格化本机 ABI：canonical `.venv/bin/python`、PETSc complex128/int32。
- V18 核心和真实 service/watchdog/checker 两模块：**10 passed in 15.36s**。
- 直接受影响的旧 P6 same-LU 两项：**2 passed，48 deselected in 0.40s**。
- 改动 Python 文件 AST 语法、`bash -n scripts/run_case_in_user_service.sh` 和 `git diff --check` 通过；没有全仓测试。
- 主控第一次复核保留失败事实：散射测试错误导入旧 V4 模块，纠正后又暴露 fixture 使用旧 `target` 字段；改为实际 V18 worker 与 `target_position` 后通过。仅测试夹具修改，生产散射次序未变。
- 准备阶段发现并关闭 service/worker 输出目录创建冲突、checker 内部 NumPy 标量绑定错误及报告变量名错误。合成 fixture 曾因将一个活动行错误映射到全部 432 行而产生 27.9 MiB 报告；修正为本次选行结构后整链在 16 MiB 门内完成，所有 432 行误差检查仍保留。
- `ruff` 未安装，未为本轮安装环境或声称该检查通过。

上述均为准备和合成测试结果；科学16输入候选、正式成本/峰值与数值支持结论仍为 NOT_RUN。新六小时窗口仍待用户批准。首次科学结果产生后才新增 `response_v18.md`，不将本准备记录冒充科学回应。
