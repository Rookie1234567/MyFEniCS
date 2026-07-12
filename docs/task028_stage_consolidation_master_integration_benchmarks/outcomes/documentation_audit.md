# 文档审计

## 审计方法

从真实入口、config dataclass、solver、PETSc ownership、后处理、tests 和 records 反向核对文档；不根据文件名猜测能力，不把代码存在写成数值资格。

## 五层结构

| 层 | V3 结果 | 自动保护 |
|---|---|---|
| Capability/Progress | 状态与 qualification 更新 | Stage2B/2C 不夸大 |
| Quick Start | 15 篇核心教程，全部 16 节、>=100 行 | test26 |
| Walkthrough | 11 篇核心 >=100 行；15 篇总覆盖 | test26 |
| Theory | 统一符号、强弱式、边界、RTA、solver | 技术关键字/链接 |
| Benchmark | 13 个 case-contained closed loops | checker + test26 |

## 技术准确性

| 审查问题 | 修正 |
|---|---|
| coarse vector 字段 | 去除虚构 constructor，列出五个真实字段 |
| PC apply 顺序 | 按源码写成 smoother-first |
| H inverse | 明确 `np.linalg.inv`，不是 LU factor |
| explicit Schur | 明确只支持 verified `H=I` |
| 3D DtN | 完整追踪 order/polarization 到 R/T |
| 2D TM 弱式 | 修复积分排版逗号 |
| 2D/3D power | 解释单位长度/单胞面积与公共常数 |

## Quick Start

每篇覆盖功能图景、能力状态、前提、PyCharm、实际修改位置、参数块、参数/资格、CLI、调用链、输出、JSON、ParaView、Gate、常见错误、自定义 case 和交叉链接。Workstation 篇提供 Docker/WSL External Tool、MPI4 wrapper、candidate record 路径和单进程非资格说明。

## Walkthrough

核心主线列出文件、签名、caller/callee、shape/global size、输出、PETSc/MPI lifecycle、公式映射、一次真实顺序、tests/cases、official/diagnostic 身份与限制。h5 示例固定 `n_fe=44,698`、`n_aux=80`、75D coarse、16 slabs、MPI4。

## Theory

统一表明确 2D x/y、3D x/y/z、top/bottom 法向、入射/出射、alpha/gamma/beta、TE/TM/s/p、F/C/D/H 和 R/T/A。理论代码锚点统一为 `module::function`。绝对 code-unit power 不跨 2D/3D 比较，归一化 R/T/A 可比较比例。

## Benchmark Cases

| 身份 | Cases | 文件契约 |
|---|---|---|
| recorded | 002/003/010/021/031 | config + expected + run + records |
| test-backed/experimental | 001/011/012/013/020 | config + expected + run，显式无 record 状态 |
| algebra/profile | 022/030/040 | fixture/config + expected + test command |

每个 README 保留 22 项表，并展开物理、参数、PyCharm、CLI、代码、证据、解释和限制。Case002/003 已写入当前数值表；Case021 与 target preset 对齐；Case031 有 MPI4 PyCharm 操作。

## 自动契约

`test_26_documentation_contract.py` 现有 11 个 tests，不再只检查“表中出现 1 至 22”。它解析 JSON records、检查目录结构与深度、阻止旧 preset 名、保护技术修正并验证全部本地链接。`benchmarks/check_benchmarks.py` 另有 143 个数值/provenance Gate。

## 保留边界

旧理论/历史开发文档继续保留；若与规范入口冲突，以当前源码、核心 Theory/Walkthrough、case expected 和 canonical record 为准。Task/review 文档未修改，重型 artifact 未提交。
