# Task40extra V28：现成 CSR/PASS 与 AUTO 续作交接

完整矩阵来自7,616-cell regular-reference q0，shape777,644²，stored slots577,061,168，有效payload11,544,333,940 B。三数组是稀疏矩阵的行指针、列号与复数值；V28复用V27行列结构，清零未完成data后填值，没有复制整个CSR或重建FE/native。

| 保存入口 | 状态 / SHA-256 |
|---|---|
| [V28 continuation manifest](../../../results/task40extra_nonseparable_0p7nm/task40extra_0p7nm_target_original_ny8_operator_probe_v22__full3d_iterative__mpi1__Mna/20261011T153931.649307Z/v27_q0_csr/task40_v28_q0_csr_continuation_manifest.json) | COMPLETE_CSR；`ca3c8de9093fd1cfe9e17c8eb557cd2f96920a3ee110549f007e70835d4a2290` |
| [native资格收据](../../../results/task40extra_nonseparable_0p7nm/task40extra_0p7nm_target_original_ny8_operator_probe_v22__full3d_iterative__mpi1__Mna/20261012T002559.817050Z/v28_q0_native_qualification.json) | PASS_COMPLETE_Q0_CSR_NATIVE_READBACK；`63babb2943b7e0f613a2c531afd09f931c4ee5504a345748c52f6ef38b0e9c81` |
| 四个保存输出 | 资格收据内`readback_artifact.path`；49,770,300 B；`304f3029e147ba0d4054efdf484757581a88b71a0ae60f6bea7235003eeac9ac` |
| 原V27 manifest | 同目录`task40_v27_q0_csr_manifest.json`；`1ea707f3c201359c390b620a5122d0102f5b34bd74873b5f00e3a40b673b94de`；原incomplete字节保留 |
| data / indices / indptr | 完整路径与三hash见manifest及[operator compact](records/target_operator_probe_v28.json)；正式required checker已实际核验 |

冻结科学source为`c6624391d8f96e257d1efa914cb38821e2a87eb9`。manifest创建身份source52b435d2保留；numeric_fill_identity/qualification另列实际c662。producer/V26/V27 donor身份不改署名。

## 现有 service 的三个独立起点

| manifest / native资格状态 | AUTO动作 | 本轮情况 |
|---|---|---|
| pending或incomplete | 实时完整CSR准入→全部清零data→full fill→4次readback→保存PASS→factor准入 | 两次attempt按此进入；当前已complete |
| COMPLETE但没有匹配PASS | 跳过fill→4次readback→保存PASS→factor准入 | 独立消费保存文件，不重做贡献生成 |
| COMPLETE且有匹配PASS | 跳过fill/readback→factor preflight/lifecycle | **当前状态**；同16GiB条件已拒绝 |

三种起点复用同一个AUTO CLI，service完成activation/ABI/source/input/window/donor/资源检查。命令没有强制篡改状态的操作。guard只读检查示例起点，实际loader继续核验三数组hash、资格/output hash、donor/input/mode和全部误差。

**以下命令在本次收口中未执行。** 它们绑定原V28固定窗口：T0=2026-10-11T23:24:00Z，数值cutoff=2026-10-12T05:04:00Z，总deadline=05:24:00Z。当前资源拒绝已记录，不重复运行C。后续新窗口/资源由主控登记；此冻结wrapper仍绑定V28、本机路径和16GiB合同，不刷新旧窗口或编造新主机。

### A. pending/incomplete fill

```bash
cd /home/shenjh/Projects/MyFEniCSx_task40extra_0p7nm_engineering
source scripts/activate_myfenics_wsl.sh
jq -e '.status == "STRUCTURE_COMPLETE_VALUES_PENDING" or .status == "NUMERIC_FILL_INCOMPLETE"' results/task40extra_nonseparable_0p7nm/task40extra_0p7nm_target_original_ny8_operator_probe_v22__full3d_iterative__mpi1__Mna/20261011T153931.649307Z/v27_q0_csr/task40_v28_q0_csr_continuation_manifest.json >/dev/null &&
bash scripts/run_case_in_user_service.sh \
  benchmarks/artifacts/task40extra_0p7nm_engineering/local_v28_wsl/stage_inputs/selected_reference_q_csr/target_original_ny8_operator_probe_v22.dat \
  --task40-v10-campaign-window benchmarks/artifacts/task40extra_0p7nm_engineering/local_v28_wsl/campaign_window_v28.json \
  --v28-q0-continuation-selector benchmarks/artifacts/task40extra_0p7nm_engineering/local_v28_wsl/stage_inputs/selected_reference_q_csr/q0_continuation.json
```

当前COMPLETE状态下guard会停止，因此不会清零已经完成的数据。fill前资源门计入完整CSR页、adapter/q0 map、共享class、有界scratch/向量与余量；factor预算独立。

### B. COMPLETE但尚无native收据的readback

```bash
cd /home/shenjh/Projects/MyFEniCSx_task40extra_0p7nm_engineering
source scripts/activate_myfenics_wsl.sh
jq -e '.status == "COMPLETE_CSR" and .native_qualification == null' results/task40extra_nonseparable_0p7nm/task40extra_0p7nm_target_original_ny8_operator_probe_v22__full3d_iterative__mpi1__Mna/20261011T153931.649307Z/v27_q0_csr/task40_v28_q0_csr_continuation_manifest.json >/dev/null &&
bash scripts/run_case_in_user_service.sh \
  benchmarks/artifacts/task40extra_0p7nm_engineering/local_v28_wsl/stage_inputs/selected_reference_q_csr/target_original_ny8_operator_probe_v22.dat \
  --task40-v10-campaign-window benchmarks/artifacts/task40extra_0p7nm_engineering/local_v28_wsl/campaign_window_v28.json \
  --v28-q0-continuation-selector benchmarks/artifacts/task40extra_0p7nm_engineering/local_v28_wsl/stage_inputs/selected_reference_q_csr/q0_continuation.json
```

这是无收据的独立起点；若存在不匹配收据，AUTO内部仍会重新判定readback需求。不得删除当前有效PASS来制造该起点。4次完整CSR作用为x1、x2、x1 trace-only、x1 port-only；不复制子块、不第二遍遍历贡献。

### C. COMPLETE+PASS的factor

```bash
cd /home/shenjh/Projects/MyFEniCSx_task40extra_0p7nm_engineering
source scripts/activate_myfenics_wsl.sh
jq -e '.status == "COMPLETE_CSR" and .native_qualification.status == "PASS_COMPLETE_Q0_CSR_NATIVE_READBACK"' results/task40extra_nonseparable_0p7nm/task40extra_0p7nm_target_original_ny8_operator_probe_v22__full3d_iterative__mpi1__Mna/20261011T153931.649307Z/v27_q0_csr/task40_v28_q0_csr_continuation_manifest.json >/dev/null &&
bash scripts/run_case_in_user_service.sh \
  benchmarks/artifacts/task40extra_0p7nm_engineering/local_v28_wsl/stage_inputs/selected_reference_q_csr/target_original_ny8_operator_probe_v22.dat \
  --task40-v10-campaign-window benchmarks/artifacts/task40extra_0p7nm_engineering/local_v28_wsl/campaign_window_v28.json \
  --v28-q0-continuation-selector benchmarks/artifacts/task40extra_0p7nm_engineering/local_v28_wsl/stage_inputs/selected_reference_q_csr/q0_continuation.json
```

当前已匹配PASS，loader直接使用`open_saved_q0_csr_from_manifest`及既有`run_task40_v26_selected_q0_factor_lifecycle`。获准时顺序为symbolic→numeric→fresh probe→另一非零RHS→evict，完整CSR true residual≤1e-10。当前拒绝在PETSc conversion前，actual factor峰值/INFOG/时间/残差均NOT_RUN或UNKNOWN。

## 资源合同与下一负责人

当前B=11,544,333,940 B；源CSR与显式转换副本2B=23,088,667,880 B，现行保守envelope=80,884,991,404 B，另计共驻owner/系统余量；均为当前所有权布局的derived账，不能冒充factor实测。

实际新增请求69,340,657,464 B，host effective available4,873,007,104 B，host缺64,467,650,360 B；cgroup current+新增81,647,519,544 B，扣reserve额度17,045,651,456 B，cgroup缺64,601,868,088 B。两缺口不相加。目标执行主机/新资源授权待主控安排；改变存储/所有权后需重算，不把80.885GB当永久下界。

下一证据为完整单q cache-miss分解父成本F_q和业务RHS成本S_q；fresh probe若在F_q内不重复计，再按整机2TB共驻账决定可保留多少相同精确因子。其余q、target PDE、物理输出、最终精度和48h全过程未资格化。[资源账](records/time_resource_accounting_v28.json)与[Response V28](../response_v28.md)保留所有负结果和边界。
