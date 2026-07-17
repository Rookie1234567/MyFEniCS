# Response V7：Review V6 F0 收口与选择性合并

## 决定

接受 Review V6 的修正后判定，并按用户决定把 conforming graded-h /
h-adaptive、measured adaptive compression 和更新后的 1 TiB / 0.7 nm 推演
整体移交下一独立任务。Task033 不再增加 Maxwell、QEP、Hybrid、p3/h3、
p4 target 或 adaptive PDE。

本轮正式身份为：

```text
task033_reduced_scope_complete = true
original_task033_full_scope_complete = false
adaptive_transferred_to_next_task = true
ordinary_default_changed = false
```

## 已完成的 F0

1. 新增 p3/h10 与 p3/h7.5 两段 descriptor-only source split 审计。两段
   direct/Hybrid 提交虽不同，但所有关键 Maxwell、Floquet、QEP、Hybrid 和
   postprocess numerical kernel blob 一致；差异只涉及 descriptor、aggregate
   和文档。
2. D1 aggregate 冻结 Docker image/digest、MPI4、zero swap、同一 Hybrid
   solver、各自 clean source、one-heavy-case、external memory authority 和
   指示性 wall-time 语义。
3. 正式分类统一为
   `fixed_p_equal_accuracy_clear_success_with_qualifications`。p3/h10 仍为
   accuracy negative；p3/h7.5 相对 provisional p3/h5 reference 全部规定物理
   误差不劣，并相对 p2/h3 改善 FE DoF、local-system rows、total rows、
   factor-inventory NNZ、memory 与指示性时间。
4. 冻结高阶资源模型偏差：p3/h10 `1.947 -> 1.980 GiB`，
   p3/h7.5 `2.463 -> 3.667 GiB`。旧模型仅可作 launch guard，重校准前禁止
   用于 1 TiB 外推。
5. 新增 fail-closed reduced-scope completion record/checker，绑定已接受证据、
   测试摘要和精确 merge manifest；原 21-role
   `formal_evidence_manifest_NOT_RUN.json` 保持不变。
6. 把原 glob 清单替换为逐文件 allowlist/exclude list。

F0 没有修改 Maxwell、Floquet、QEP、Hybrid coupling、solver 或 physical
postprocess numerical kernel，也没有运行新 PDE。

## 验证结果

- host F0/D1/D2/证据/文档组：`146 passed, 4 skipped`；
- 文档同步后 focused host regression：`46 passed`；
- 冻结 DOLFINx 镜像中的 Task33 high-order 与 Task32 anchors：除一个旧测试
  断言外，其余 `47 passed, 7 skipped, 81 subtests`；
- 旧断言把已接受的 p3/h5 reference wiring 当成不存在，已改为只接受 p3/h5、
  继续拒绝 p3/h3/p1；隔离重跑 `3 passed, 8 subtests`；
- matching trace MPI2/MPI4：各 rank `1 passed, 4 subtests`；
- targeted Ruff、`compileall`、CSV/manifest 审计与 `git diff --check`：通过。

completion record 的 payload SHA256 为
`a656f2608a12a0b915bf46755669732cece7d37510fbb87c503e67af80682cd2`，
文件 SHA256 为
`7c3306a1bf5fadc94155eace314503efdfdeed551eb0216916b8efd1ee7f2b34`。
生成后 unit test 与 CLI exact-equality verify 均通过。

## 选择性合并

本次只合入：

- 已资格化高阶 Floquet、QEP、mode tracking、matching trace 和 Hybrid 改动；
- p3/h5 full3D wiring、资源 watchdog、D1/D2 与 reduced completion checker；
- 与其一一对应的测试；
- Case090/091 的轻量 hash-bound record；
- Task33 任务书、全部 review/response、summary、completion matrix、
  negative results、quick-start、theory、capability matrix 与 roadmap。

明确不合入：

- adaptive mesh/graded-h prototype 及测试；
- interface buffer prototype test；
- 1 TiB projection runner；
- 原 21-role full-scope 自动执行、formal publication 与 final-outcome 路径；
- 旧 20 项矩阵自动 equal-accuracy 路径；
- 任意 heavy mesh、field、matrix、factor、timeline 或 log。

原任务书、审阅和 `NOT_RUN` 记录保留是为了防止历史身份被改写，不代表这些
未资格化路径成为 master 当前能力。

## 结果边界

Task033 reduced scope 已完成，但它没有证明 continuum/grid convergence、
p2 adaptive compression、0.7 nm 可运行或 1 TiB 可行。p3/h5 仍是
provisional discrete reference；不同 clean SHA 的 wall time 只作指示性比较。
后续 adaptive task 应从 h5 mechanism、周期同步 mesh、独立 accuracy/MPI Gate
和重校准资源模型重新开始。
