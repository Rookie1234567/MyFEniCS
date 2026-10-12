# Task40extra Review V29 执行响应

**V29 factor 没有开始。** 主控已冻结并远端回读源码 45628068263181b83739ff80f4f34ffaa472e943；Review 登记 source_at_entry 保持 e85992c79d7e2b3f41cd1396ffb06edccdd93421。本轮完成本机依赖与 strict factor-only 接线准备、修复冷启动/native profile 接线并通过定向软件验证；target service/worker 尚未启动。剩余资源/依赖包授权、目标 ABI/runtime 资格和固定窗口都未完成，故没有 F_q/S_q 或 factor/PDE 结果。

## 首要数值与运行状态

| 项目 | 本轮结果 | 解释 |
|---|---|---|
| 实际 factor / q coverage | NOT_RUN；没有 service、run_id、worker PID；factor count 0 | 只完成软件准备。 |
| symbolic / numeric / MatSolve | 全部 NOT_RUN；本轮未调用 | V28 的早期 conversion resource stop 是历史结果；没有用同一 16 GiB 条件重试。 |
| F_q | UNKNOWN / NOT_MEASURED | 字段已接线；正式计时需从 strict identity check 和初始 CSR loader开始，到首次真实因子资格结束。 |
| S_q | UNKNOWN / NOT_MEASURED | 未来 S_q 的主指标取 native_MatSolveRepeated_seconds；第二组测试 RHS 的完整 parent、残差与 raw save/readback 另列。 |
| fresh probe / 第二 RHS true residual | NOT_RUN | 没有新测试向量、解或残差 artifact。 |
| factor 常驻/瞬时峰值 | UNKNOWN | 没有 Task40 cgroup 或 worker 进程峰值。 |
| 物理输出 | NOT_RUN | R00_s/R00_p/R00_total、R/T/A/A_volume、diffraction、target A6 和 2 TB/48 h 均未资格化。 |

V28 已接受的 regular-reference q0 CSR 身份保持不变：shape 777,644²，577,061,168 个结构槽，CSR payload 11,544,333,940 B；V28 保存 native PASS SHA-256 为 63babb2943b7e0f613a2c531afd09f931c4ee5504a345748c52f6ef38b0e9c81，四个完整 CSR 作用和独立保存输出复算最大相对误差为 1.9116580127738185e-14，门限 1e-11。此处的数值资格仍是 V28 产生的旧资格。V29 prepare --verify-only 已对 39 个依赖文件做全文件 SHA-256 读取，合计 24,317,319,033 B，其中包括 q0 CSR；这证明本机依赖字节与所需身份匹配，但没有重跑 native operator 对照。本轮文档收口没有重复这批大文件哈希。

## 冷启动与 native Linux 修复

冷 systemd shell 的 V29 路径曾在激活数值环境前用 python -S 启动服务工作流，可能在项目数值模块导入处失败；外层合同检查也使用脚本路径从任意当前目录运行，无法稳定解析项目根包。本轮将两处标准库合同检查统一为先切到仓库根目录再执行 python3 -m src.runners.task40_v29_contract，随后才 source 现有 native activation，并让 runtime Python 使用已激活环境。

另一个真实接线错误是把目标 native Linux 环境送入 WSL activation 与 WSL marker 检查。V29 现在使用仓库已有 activate_native_complex.sh 的 native_linux profile，并用 qualified ABI manifest digest 作为运行身份；普通旧 WSL 分支未改。初始环境资格仍是 imports-only，不能当作 FE/JIT 已运行。

F_q 的完整阶段边界现在在 operation receipt 中包含严格身份匹配和首次只读 CSR loader，随后为转换、symbolic、numeric、首次 MatSolve、完整 true residual 与 hash-bound raw readback，止于第二 RHS 和 eviction 前。S_q 主值取 MatSolveRepeated 原生调用时间；第二 RHS 构造、PETSc Vec 创建、完整 residual、raw 保存/回读分别列出，eviction 单独记账。这些字段目前是实现定义，尚无实测数。

## 定向验证

在本机资格化 WSL 测试环境完成 ABI preflight（Python 位于该 checkout .venv；PETSc 3.19.6、complex128/int32、MPI1；petsc4py/SLEPc/DOLFINx/mpi4py 均来自 Linux 路径），并通过：

- targeted pytest：**15 passed in 1.14 s**；
- 改动 Python 文件 py_compile：通过；
- bash -n scripts/run_case_in_user_service.sh：通过；
- git diff --check：通过，随后源码由主控冻结并推送。

文档合同组另有 **29 passed**；耗时与日志哈希见测试收据。这不是目标机 ABI 资格，不是 factor/RHS 数值测试，也不代表 full repository pytest、MPI2/4、Ruff 或 CI 通过。详细命令与日志 SHA-256 见 [定向测试收据](outcomes/records/targeted_tests_v29.json)。

## 目标准备与资源边界

本机准备清单记录所需依赖 39/39 存在且 SHA 匹配，共 24,317,319,033 B；此项包含多个大型 CSR/producer payload，本次文档收口只引用已完成的 V29 prepare 收据，未重复读取或哈希这批大文件，也没有传输。目标机只读观察收据确认 /home/fenics/Projects/laptop_share 当时为空；这是空目录检查，不是 target runtime 资格。目标 ABI/runtime 仍未建立。运行时准备方案是从本机 benchmarks/artifacts/task40extra_0p7nm_engineering/local_w0_wsl/runtime_prefix 复制到目标 laptop_share 下相同相对路径；此前 du 目录树观察为 2,625,190,071 B，但这不是精确传输字节数或内容 hash。复制仍待授权，之后必须在目标以 native_linux profile 对 PETSc 3.25.6 做新 ABI qualification；旧收据只作发现资料，不复用为 PASS。

拟议的 task cap 512 GiB、host reserve 64 GiB、task swap 0、MPI1/线程1、6 小时窗口仍未获得执行批准或实际应用。目标机快照的 MemTotal 为 2,163,100,385,280 B、MemAvailable 为 1,413,713,145,856 B；host SwapTotal 为 8,589,930,496 B、SwapFree 为 8,569,143,296 B、SwapUsed 为 20,787,200 B。没有 Task40 dedicated cgroup，所以 task swap 保持 null，且这些主机快照不等同于 factor 峰值。当前 T0、deadline、服务、run_id 和 PID 都为空。

记录的本地准备区间为 UTC 4,008.5096 s、monotonic 3,607.9524 s、boottime 3,607.9524 s；三种时钟分列，约 400.5572 s 的 UTC/monotonic 差异保持 UNKNOWN。此历史子区间包含在主控随后测得的同一父区间中：UTC 7,676.157756943 s、monotonic 6,952.337018444 s、boottime 6,952.3370187 s，保守取 7,676.157756943 s。端点为 2026-10-12T04:28:37.848919Z，仍是当前下界，final_closeout_complete=false；不能再加原 4,008.5096 s。此前未记录的准备前缀、后续少量收口及未单独计时子项保持 UNKNOWN。这些是工程准备成本，不是 factor 时间，新 heavy T0 尚未启动。

## 后续门

当前实现已冻结到 45628068263181b83739ff80f4f34ffaa472e943。主控将询问一次剩余资源/依赖/runtime package 授权；获准后再准备目标 ABI 与路径并登记固定窗口。之后消费现有完整 CSR/native PASS，运行唯一 held factor-only 命令。命令不得提前启动。worker 启动后，按用户已授权范围发送一次 V26 service/run_id/source/worker PID 状态通知；当前没有 worker，因此不发该通知。

详见 [执行交接](outcomes/target_stage_handoff_v29.md)、[factor/准备记录](outcomes/records/target_operator_probe_v29.json)、[时间资源账](outcomes/records/time_resource_accounting_v29.json)、[就绪状态](outcomes/records/v29_execution_readiness.json)。
