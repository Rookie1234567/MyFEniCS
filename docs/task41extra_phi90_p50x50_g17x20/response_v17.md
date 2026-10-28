# Task41extra Response V17：两单元诊断接线

**状态：代码接线及合成定向回归完成；真实 V16/V3 ignored artifact 布局尚未核验；没有创建执行窗口或启动计算。** V17 只实现 active row `1622464` / original row `5218672` 对应 cells `[7873, 8014]` 的局部重放和归因输入，不能解锁 full owner、全域 action、official result、恢复、200q、完整参考或 target。

## 1. 实现结果

| 部分 | 本轮结果 | 边界 |
|---|---|---|
| Service selector | 新增只允许 V17 命名 selector、固定 consumer scope/window 与 hash-bound V16 manifest 的专用入口；与 V15 selector 互斥 | 不创建真实 contract/window/T0/auth |
| 两单元 callback | 只加载两单元的 fresh I/T/E map、候选张量和原有同 LU RHS 状态；保存 map、candidate、LU/R/T/S、初解/校正各步与返回 `-Jz` | 最大2个candidate/LU；矩阵 RHS GETRS≤6，内部 RHS GETRS≤12；没有新增伴随或恢复求解 |
| 数值次序 | `g` 从全局 native `b_t` 开始，再按 `[7873, 8014]` 加回实际 correction；`y` 按 cell 项后加一次 `Bα` | 精确重放失败时保留差值并分类为 `LOCAL_REPLAY_UNBOUND` |
| 独立 checker | 独立验证两列 y/g、fresh map、hash-bound数组、初解/校正各步残差与更新链、最终 RHS、实际 `-Jz` 和 signed cell/two-cell identity；对全部唯一 NPY 输入核算 128 MiB 上限 | 只产出本地诊断完整/未绑定状态，official/full-owner 标记固定为 false |
| 准入 | `_build_same_mesh_levels` 前读取剩余数值窗口，要求至少900秒工作估算和120秒终止余量；并检查16 GiB累计、128 MiB本窗新证据和2 GiB空闲磁盘底线 | 这是启动准入，不是900秒硬终止；后续每个candidate仍有既有准入检查 |

首轮 callback 测试发现新 map checkpoint 在 candidate identity 写入前落盘，导致正常首跑被身份门误拒。修复在首个 map checkpoint 同时保存候选输入 identity，保留原有严格相等比较；损坏或缺少必要 identity 的旧 checkpoint 仍会拒绝。独立 checker 使用自己的 JSON/数组 hash 与 NPY 路径读取逻辑；本轮又补齐逐步残差/更新复核、零 RHS 的 z0 保存与重开、完整数组字节统计，不调用 worker 私有 loader。

## 2. 测试证据

在仓库 qualified activation 下运行 V17 两个定向模块及直接受影响的 V8 兼容性模块：

```bash
source scripts/activate_myfenics_wsl.sh
python -m pytest -q \
  src/test/test_task41_v17_service_selector.py \
  src/test/test_task41_p0_v17_selected_replay.py \
  src/test/test_task41_v8_selected_trace_star.py
```

最终结果：`47 passed in 15.72s`。新增严格 loader 负例直接调用真实 contract、V16 manifest loader：错误 contract SHA、错误 scope 和错误 manifest SHA 均被拒绝；不通过 mock loader。端到端合成 fixture 调用真实 V17 callback，生成并保存候选/map/RHS数组，再由真实 checker CLI 重开；覆盖零 RHS 和非零 RHS、每步补偿残差复算、`z_before + delta = z_after`、完整唯一 NPY 字节计数，并验证损坏数组 SHA、错误 map coverage、总证据超限均失败关闭。昂贵积分/LU由fixture替代，I/T/E map及数组 schema 使用小型合成数据。另有 V15 合同兼容定向测试 `1 passed in 0.09s`。这些测试不代表真实 FE 结果，也不校验 workstation 上的 raw arrays。

`git diff --check` 通过；6个相关 Python 文件 AST parse 通过。当前环境没有 `ruff` 可执行文件，未报告 Ruff 结果。沙箱内单独 MPI/PMIx preflight曾因 socket `errno=1` 失败；测试是在获准的 qualified activation 执行环境运行，不把沙箱错误计作代码测试失败。

## 3. 固定输入与未核验项

代码固定的 V16 manifest identity 为：

- 相对路径：`results/task41extra_phi90_p50x50_g17x20/task41_p0_saved_diagnostics_6h/3d22e02f713c4a68c79759b2c5cb7cbcec693b7b3277ad98b529838008e38beb/saved_vector_distribution/attempt05.service/task41_p0_v16_metadata_bound_manifest.json`
- SHA-256：`3fae0774772550faf173444e9c5aedd608212b430957ae591ffdb31daabeb215`

该 manifest 在当前本地 worktree 不存在；V16 metadata JSON 存在，SHA-256 为 `35720a498334c463f660f9179315eb20d5dbed5d6111fcf7201f7de0c9344665`。本轮使用上一回合给出的 SSH agent 路径只检查了 socket，当前 socket 不存在；没有访问 workstation，也没有加载或传输任何真实数组。因此，V16 saved-vector manifest 和 V3 donor 下的 known/native RHS 数组目录、字节数与 hash 仍待从受信结果目录核对。

Review V17 提议的新6小时窗口没有在本轮获得执行授权；未创建 authorization、T0、window、accounting、DAT副本或真实 attempt。没有启动 service/worker、FE/PDE或真实 checker，也没有 commit/push。原全域 action 的失败状态不变。

## 4. 下一步

1. 在 SSH agent 可用后只读核对上述 V16 manifest 及其 V3 donor 引用；若路径/hash与固定合同不符，先修 binding，不载入大矩阵。
2. 主控冻结代码和 source SHA，整理真实命令、expected-file预算及 closeout 时间估计。
3. 只有用户另行明确批准新 V17 窗口及执行准备后，才可以创建窗口并启动正式诊断。

当前分支 `task41extra_phi90_p50x50_g17x20` 的提交 HEAD 仍为 `06cd1789c717face827476ad70f24ae8efb6b0f1`；本轮修改尚未提交，工作树包含本轮 V17 准备变更。没有改变普通 solver 默认、full-owner gate 或官方数值门。

## 主控准备提交说明

主控最终独立定向回归为 `48 passed in 15.74s`（47项V17/V8及1项V15合同兼容），ABI、shell语法及diff检查通过。本文件当前是准备进度响应，正式两cell结果仍 `NOT_RUN`，不是V17科学结项。实际命令模板、接续分支、输入/输出清单及启动阻塞见 `outcomes/v17_preparation.md` 的主控冻结前复核。准备代码集中提交后，旧HEAD仅表示review/base；实际准备提交SHA以Git提交及主控远端回读为准。
