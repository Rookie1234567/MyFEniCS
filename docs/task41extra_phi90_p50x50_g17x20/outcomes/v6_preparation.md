# V6 P0 准备包：尚未运行新数值资格

本包把逐单元慢张量生成改成候选的分块矩阵乘法，同时保留冻结 FFCx 的实际几何表达式。它只是可审查实现，尚未证明加速、局部正确性或全域作用通过。

## 权威与身份

用户明确指定的报告是 `archive/review_report_v6_chat_attachment_20261020.md`，SHA256 `b0b680648d0581593cf72fa5a8d75527eabaf2b9caf02105867c00f03c4ac8b9`。该文件在 `618edb71c5bf800e83a3d2a0cd35aab38792fb03` 中原样保存。本包按其 `actual_qmetric_blocked_gram`、point block 32 和局部张量/R/T/S 1e-11 筛查执行。另一份正式命名 V6 原文保持不变，不混用其不同候选/局部门。原最终两列、恢复、native、物理门不变。

结果基线 `dcc2737a9166e6c9185223ac084f811d5068ad4b`，旧科学基线 `179cf7369e6bc5894fa87af6b74cf5c73938b6d4`。V5 是 CANDIDATE_NOT_ADMITTED，不是新数学失败，也不是修复成功。

## 已准备与未完成

| 项目 | 当前状态 |
|---|---|
| 冻结 actual 几何 C helper、参考表与 Gram | 已实现，绑定原 C/module/表/实现身份；未实际编译执行新工作站候选 |
| actual 构建路径 | 已接 evaluator；方向、LU、R/T/S 保持；新缓存分开身份 |
| 八键前缀 | 两份保存 actual 块复用，其余最多六份原 kernel oracle；先保存再判门；未完成/失败不能进入全域 |
| checker | P0未运行与正式八键资格分开；消元缺陷为诊断，不新增停止阈值 |
| 新窗口 | 独立 V6 86400/85200/1200 路由；真实授权及窗口均未创建 |
| 普通修复续作 | 首建绑定 entry source；后续 run source 可变，原窗口/T0/授权/父身份不可变 |
| 完整两列 | NOT_RUN，仍须独立数值资格 |
| 同 owner → 200q | 尚未接通；现有 volume audit 完成后返回并释放 owner。不得声称已实现连续参考/target 求解；主线接续仍需必要生产接线与冻结 |
| 新性能/内存/全域数值 | NOT_RUN；旧17.224天及348.56GB均仍为旧候选推导 |

旧端口、141数组、A1/A2和已接受恢复不重跑。工作站仍保留旧科学源；当前没有 V6正式计算或新T0。

## 最后定向验证

主控在资格化 WSL activation 中检查 PETSc complex128/int32 及 Linux PETSc/SLEPc/DOLFINx/MPI 路径后执行：

```bash
python -m pytest -q src/test/test_task41_actual_qmetric_blocked_gram.py src/test/test_task41_p0_contract.py src/test/test_task41_p0_saved_output_continuation.py src/test/test_115_task035b_assembly_time_condensation.py src/test/test_task41_v4_volume_only_audit.py -k 'actual_qmetric or v6 or v3_window_immutable or b0_default_window_route'
```

结果32 passed、64 deselected，0.83s；工具输出 `956292`。这不是实际工作站 FFCx tensor PASS。执行者相关 py_compile、git diff --check 通过；Ruff未安装，未安装新依赖。旧完整 B0 service fixture 本轮未获得新 PASS，其历史时钟/输出问题不伪报通过；新 saved-selector 实际解析链有针对性 fixture。

## 批准后使用的入口（现在不执行）

先由主控记录用户对本 V6 新窗口的明确批准；部署 clean source，核对无重叠 Task41 heavy，并通过原动态准入。旧主机、1.5TiB cap、64GiB host reserve、task reserve0、swap0、MPI1/math1、ABI、16GiB证据/2GiB磁盘余量均不变。授权 receipt 按 `task41_p0_contract.py` 的 V6 schema 绑定真实 entry SHA、父窗口路径/hash；不伪造批准、不先取T0。

工作站 `/home/fenics/Projects/laptop_share` 资格化 activation 后：

```bash
python -m src.runners.task41_p0_contract --prepare --case B0 --b0-v6-continuation \
  --runtime-prefix benchmarks/artifacts/task40extra_0p7nm_engineering/local_w0_wsl/runtime_prefix \
  --abi-receipt benchmarks/artifacts/task40extra_0p7nm_engineering/local_v29_wsl/abi_receipt_v29_attempt2.json \
  --jit-cache benchmarks/artifacts/task40extra_0p7nm_engineering/local_v29_wsl/jit_cache
```

prepare 本轮首次调用前需开始记录必要准备费用；实际新 window/T0 保持唯一。科学源变动后用同窗 prepare 生成新 run contract，不能覆盖原 entry/window。以下 service **无位置 DAT**；保存路由必须是首个 case 参数。`V6_RUN_ROOT` 由本次唯一 attempt 分配（不得覆盖旧输出）；`V6_CONTRACT` 由 prepare 输出：

```bash
V6_CONTRACT="benchmarks/artifacts/task41extra_phi90_p50x50_g17x20/p0_b0_controller/execution_contract_source_$(git rev-parse HEAD).json"
DONOR_ROOT="/home/fenics/Projects/laptop_share/results/task41extra_phi90_p50x50_g17x20/task41extra_b0_p6_phi90_07nm_iterative__full3d_iterative__mpi1__Mna/20261019T053402.514018Z"
bash scripts/run_case_in_user_service.sh \
  --task41-p0-saved-b0-volume-only-attribution \
  --task41-p0-execution-contract "$V6_CONTRACT" \
  --donor-contract benchmarks/artifacts/task41extra_phi90_p50x50_g17x20/p0_b0_controller/execution_contract_source_afbe91e5947ed18fb74d7105097e129c1b8b4cc7.json \
  --donor-contract-sha256 9e312f86cdd6b15fff9015faf4fb7dce19043fa3798a3f35cf2e57f79149713c \
  --summary "$DONOR_ROOT/task40_v10_p6_candidate_summary.json" \
  --numerical-output "$DONOR_ROOT/numerical_output" \
  --output-dir "${V6_RUN_ROOT:?assign a new attempt directory}" \
  --geometry-policy mesh_actual_exact \
  --geometry-reference-report results/task41extra_phi90_p50x50_g17x20/task41_b0_v4_geometry_pair_02523b3d_attempt1/task41_p0_v4_geometry_pair_probe.json \
  --raw-tensor-evaluator actual_qmetric_blocked_gram \
  --ffcx-c-source benchmarks/artifacts/task40extra_0p7nm_engineering/local_v29_wsl/jit_cache/fenics/libffcx_forms_2f92c03a20c09db3cb8f0382bec2294daa94ab16.c
```

`numerical_output` 是旧服务记录的逻辑输出前缀，并非现存同名目录；保存数组位于其父 run 目录，不应擅自新造目录或更换 donor身份。required checker 由此 saved service 受监督执行，不裸启动checker绕过资源/时限。

主控只读回验：旧V3 window SHA `68e6d8dfcccc9dee98bc161730957dc76f70a9e2dea2ee78455b66c9d8b37c38`；旧 donor contract SHA `9e312f86cdd6b15fff9015faf4fb7dce19043fa3798a3f35cf2e57f79149713c`；旧summary SHA `651c7a84db27e02c02879b10a28fe5580911678d25b5c7b8018a882d467c98d9`；两cell报告 SHA `a47eb7a8795b5af542c23ae45915588d89c962d1af1bb8360b8a9d42f1e7c031`，均匹配。

实际资格前不称候选有效；局部通过后仍须全域两列和原生恢复/独立checker。完整场、最终精度及2TB/48h均未闭合。本文件是执行准备记录，不替代用户报告，也不是本轮最终 response_v6。
