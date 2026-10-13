# Review V30 真实续作交接

本工作包在固定数值截止停止；这里只交接可复用文件与断点，不能凭本文件自动新开窗口或重启服务。

## 已保留的身份

- 分支：`task40extra_0p7nm_engineering`；review：`8c05f1bf2aecd318ca3270ddfb0b787dcc3465e8`；审阅V29基准：`5823faf26e5425974645c2b1fc2b4004552b4324`。
- 最终正式科学源码：`1e9109cb62343b13c850da03432def2109fee481`。后续本次文档提交不是重新执行科学源码。
- 目标根：`fenics-ws:/home/fenics/Projects/laptop_share`；native ABI收据：`local_v29_wsl/abi_receipt_v29_attempt2.json`，SHA256 `1c4277c83a0ac6daf02197086264b9e5b337caee1b33d7cc1dd22a7dfcefe57d`。
- V30 target window：`local_v30_wsl/campaign_window_v30.json`，SHA256 `15ef0f6dd4221d71e488b2c2930ad1dd05328b06b0ce78819d8402093c1e8320`；执行contract：`local_v30_wsl/execution_contract_v30_fix01.json`，SHA256 `f00b58d717311d16fb6f70ab76992627e213837b6ee8b0ec5f364a19cfe4d295`。路径均相对于目标根的 `benchmarks/artifacts/task40extra_0p7nm_engineering/`。
- 保留V28 q0 COMPLETE manifest `ca3c8de9093fd1cfe9e17c8eb557cd2f96920a3ee110549f007e70835d4a2290` 与native PASS `63babb2943b7e0f613a2c531afd09f931c4ee5504a345748c52f6ef38b0e9c81`；V29 q0 factor已销毁，下一次实际bank仍需新建并计费。

## 真正的停止点与下一依赖

实际命令、source/input/ABI、互斥父阶段与raw hash见[主控审计](records/review_v30_controller_audit.json)和[Response V30](../response_v30.md)。最终run仍无 official packet/partial footer；没有新的合格q4 CSR/native、八qbank、完整reference或目标场。共享legacy marker不表示target已构建。没有完成阶段计时，不能把总setup归给单一JIT或q投影。

下一次授权后首先以保存数据完成q4自己的pattern/CSR并补齐独立native四作用，勿重跑q0 producer/native或用q0复制q4。对新twist再各做一次必要共同生产，逐阶段立即保存时间与产物。完整reference owner准备为何在首个q成果之前持续耗时尚缺精确阶段证据：先读取现有缓存/源码与保存进程证据，补必要阶段标记并做窄入口检查，避免盲目重复同一个昂贵前缀。只有八q资格齐全、所有current/future对象和窗口余量实际准入时，才在一次进程内建live bank、reference资格和条件target。

required-checker的监督使用数值cutoff，导致预留的收口阶段不能启动。新只读复核已经返回真实 `NO_PARTIAL_FOOTER`，原失败不能改写；下一次应窄修收口时间合同并做fixture，不因footer问题重解PDE。未获得新窗口前不执行任何新的重型命令。

原设置保持：exact MUMPS、complex128/int32、MPI1/数学线程1、task swap0、cap1649267441664B、host reserve68719476736B；cap非预分配、非factor实测。原尺寸完整冷流程与精度未资格，不能从旧q0乘8给出全场结论。
