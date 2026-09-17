# Response V3：2 nm h1.5 按实测内存上限重启

用户于 2026-09-18 明确要求：“要等真正超过1537.5GB再终止，而不是一个预估值”。本轮将此解释为同期整个任务进程树 RSS 上限 1,537,500,000,000 B（十进制 1537.5 GB，约 1431.908 GiB）。该指令覆盖本次 P2 预测准入和此前迁移重试次数限制，批准一次新运行；不更改数值或物理标准。用户另要求启动后停止主动查询和汇报，之后由用户按需询问，因此保留独立资源 watchdog，不启动聊天通知 observer 或定时主动查询。

## 上一轮实测与预测分开

| 项目 | 记录及解释 |
|---|---|
| 旧 run / source | `20260915T210201.504107Z` / `2cc58bb4a76e88a35c41243f420331252a5a23eb` |
| 终态 | `WORKER_FAILED/exit4`；底层 `REFERENCE_RESOURCE_BLOCKED` |
| 时间 | 2026-09-17 18:09:05 +08:00 结束；workflow 133624.287 s，约37.118 h |
| 已完成 | p4增广10608132行、4899800920 NNZ；PORD64 symbolic `INFOG(1)=0` |
| 实测内存 | 同期进程树采样峰277716156416 B；symbolic后222001508352 B；swap峰0，子进程已清场 |
| 预测值 | 因子估计1222578000000 B乘2，加现存RSS、48545448448 B未来工作区、1073741824 B工程余量，得到2716776698624 B；并非实测需求或严格上界 |
| 原拦截线 | 1537541295924 B；仅因预测超线退出，numeric/solve/outer未运行，无official R/T/A |

## 本次最小修改

新增显式输入 `input/task39extra_para_workstation_capacity/original_2nm_si_p6h1p5_measured.dat` 和 `balanced_h6_p4_native_2nm_measured` 配置，仅允许2 nm、p6/h1.5。旧输入和旧profile保留。材料、网格、A/b、BAL_H、积分、zero start、FGMRES32/max2048、128步进展判据及数值/物理门限与旧run一致。

预测公式与symbolic估计继续写日志；新profile的资源检查依据实测RSS，不用预测值或planning ceiling拒绝numeric，也不再向MUMPS安装由未来工作区扣减得出的ICNTL(23)限额。MUMPS自身错误仍会如实报出；无OOC、无换排序或新PC。旧profile保持原预测准入和原MUMPS内存限制。

独立父watchdog沿用已存在的整树采样与subreaper清场，标称间隔0.25 s（实际间隔含采样开销），实测RSS达到上限立即SIGKILL本次后代；采样可能有短暂越线，不能保证字节级无超调。系统可用内存reserve、job swap=0、全局新增换页检查和监控可读性要求保留。系统剩余内存不足时可更早停止，这是实测系统压力条件，不是因子预测。worker使用CPU23、MPI1/线程1、preferred_node1；watchdog在CPU9。只改本worktree，不操作邻项目进程或文件。

## 验证和启动

组件验证包括：真实MUMPS小矩阵在注入大预测值时完成numeric/solve并保持ICNTL(23)=0；达到实测RSS门限、swap或不可读时拒绝；真实子进程实际分配内存超过256 MiB缩小测试上限时被终止并清场；旧p4数值合同、native配置及既有subreaper回归。完整命令、实际测试数量、日志hash和ABI记录见 [本轮证据](outcomes/records/2nm_h1p5_measured_retry_v1.json)。未运行全库测试或CI。

初次ABI查询脚本误用无下划线的PORD符号，未进入测试或PDE；用实际导出 `mumps_pord_intsize_` 更正后，验证PORD64、complex128/int64、唯一PETSc映射和原库hash。无环境重建。

本轮先将代码、证据和授权记录提交到同一执行分支，绑定clean source后通过原detached启动器的 `--input` 参数启动唯一新run；大矩阵和checkpoint均未保存，不能续接旧37小时装配。新run身份和启动检查在 `benchmarks/artifacts/native_capacity/measured_retry_20260918/launch_check.json` 保存。启动后停止主动查询，由用户后续询问进度。h2和其他模型不在本轮启动，未批准master合并。

文档检查为20 passed、1 failed。唯一失败来自基线已引用但HEAD及磁盘均缺失的 `docs/task038_extra_full3d_iterative_0p7nm/outcomes/memory_first_small_v2_checker.json`；不是本轮新增路径，不伪造缺失历史证据。本轮表格Markdown和任务文档合同通过。
