# Centered p4 独立保存证据复核

结论：固定源码 ad356715da86ab34fa6b10838cccc8629b3f6e8b 的新 p2 桥接与 p4 记录通过本次只读复核，未发现具体证据缺口。没有导入求解器、重跑 checker 或执行数值求解。

逐项核对 1251 个冻结 Git 源文件、591 个产物哈希（桥接 288、p4 303）及 48 个原始因子诊断哈希；报告、provenance、独立 checker、live receipt、ABI 和监督记录一致。桥接保留旧 7c4410d dense 权威的三份固定哈希；在新源码上重新比较全部 2048 原始列，差异为 0。独立 checker 分别 164/164、148/148 通过。

P4 是同 80 个真实三维单元，15872 独立自由度、8640 内部自由度、全部 532 物理端口。自身实际 local basis 300、Gauss degree 23 / 144 点已绑定至同一 live carrier；全部模式的系数、rank-one、五态恢复和输出 ledger 完整，保存值均通过原门限。live 证明完成于 53.13090642 s，factor 前 carrier 检查于 93.84091781 s；所有对称性门于 97.94208332 s 通过，退出时 carrier 身份保持。每方 40 项完整 532 模式输出比较通过，要求的 global output 均可表示。

P4 regular 最大原残差为 4.2235258786613412e-12；notch 四负载迭代数 4/4/3/4，最大原残差 7.9668823919400921e-12；完整增广 off-q 相对量 5.0521957269858186e-16。

从保存的整进程树采样重算，p4 worker 为 117.446407880 s、913350656 B；checker 为 4.791007419 s、524525568 B。桥接 worker 为 14.880568978 s、462925824 B。四个 worker/checker 均正常退出、swap 0、后代清理完成，低于 1.5 GiB / 600 s 准入上限。峰值是采样 RSS。

限制明确保留：没有全局 p4 direct control；原 volume action 由保存的 live FFCx 作用向量作为权威，独立 checker 重算保存向量的残差、端口输出和稀疏块恒等式。本结果只支持同一小夹具的 p 增长离散架构，不构成 p6、完整目标物理尺寸、连续/几何精度、官方 R/T/A 或 2 TB / 48 h 可行性资格。

精确文件哈希、ABI、载体标识、资源、逐类负载和 ledger 最大值见 independent_verification.json；verify_saved_evidence.py 记录主要只读核验方法。
