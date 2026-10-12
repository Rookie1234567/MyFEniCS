# Task40extra Review V29：q0 factor-only 启动包（保持暂停）

主控已冻结并远端回读实现源码。Review 登记 source_at_entry 为 e85992c79d7e2b3f41cd1396ffb06edccdd93421；当前实现冻结源码为 45628068263181b83739ff80f4f34ffaa472e943。V29 资源/依赖包授权与目标 ABI/runtime 资格仍未完成，文件传输和固定窗口未登记；没有 V29 service、worker、run_id 或 T0。

factor-only 表示只对已有矩阵做一次单 q 分解与两组非零测试 RHS，不重新生成 FE 网格或 CSR。F_q 是一次冷 cache miss 从身份核验与初始 CSR loader 到新分解的首次完整残差核验；S_q 的主指标是同一因子上的 native MatSolveRepeated 秒数。制造第二组测试 RHS 的完整父段、残差和保存回读另列；两者目前都没有实测值。

## 当前科学身份与结果边界

- 输入 SHA-256：134ea5f08d5d5dbc366870f451ba0de0df5893c5cd73d227dac77f8a11aa2c0b；V28 manifest SHA-256：ca3c8de9093fd1cfe9e17c8eb557cd2f96920a3ee110549f007e70835d4a2290；V28 native PASS SHA-256：63babb2943b7e0f613a2c531afd09f931c4ee5504a345748c52f6ef38b0e9c81。
- 现有 q0 CSR：777,644 × 777,644，577,061,168 structural slots，11,544,333,940 B payload；V28 四次 CSR/native comparison 的最大相对误差 1.9116580127738185e-14，门限 1e-11。资格从 V28 沿用；V29 prepare --verify-only 已对 39 个依赖完整读取并做 SHA-256，合计 24,317,319,033 B，其中包括 CSR 数组；文档收口没有重做该 hash。该检查是字节身份核验，不是新 native/numeric qualification。
- 当前分类：本地准备完成，源码已冻结，目标运行保持 HELD；实际 factor、symbolic/numeric、fresh/repeated MatSolve、残差、内存峰值、F_q、S_q 均 NOT_RUN/UNKNOWN。

## 唯一生成的 factor-only 命令（不得提前执行）

以下内容与 local_v29_preparation/factor_only_command_v29.sh.txt 一致。命令目前明确标记为 HELD；不要仅凭本交接文档启动。

~~~bash
# HELD: do not run before package/resource approval, target runtime qualification, and main source freeze.
cd /home/fenics/Projects/laptop_share
bash scripts/run_case_in_user_service.sh benchmarks/artifacts/task40extra_0p7nm_engineering/local_v28_wsl/stage_inputs/selected_reference_q_csr/target_original_ny8_operator_probe_v22.dat --task40-v29-execution-contract benchmarks/artifacts/task40extra_0p7nm_engineering/local_v29_preparation/execution_contract_v29.json --task40-v29-factor-only-selector benchmarks/artifacts/task40extra_0p7nm_engineering/local_v29_preparation/factor_only_selector_v29.json
~~~

当前目标 root 为空，命令引用的输入与 contracts 尚未传入该 root。只有获得剩余资源/依赖/runtime package 批准并登记固定窗口后，才可启动。

## 记录入口

- [执行准备与未运行状态](records/target_operator_probe_v29.json)
- [时间与资源账](records/time_resource_accounting_v29.json)
- [就绪 Gate](records/v29_execution_readiness.json)
- [源码快照](records/v29_source_snapshot.json)
- [定向软件测试](records/targeted_tests_v29.json)
- [本轮响应](../response_v29.md)
