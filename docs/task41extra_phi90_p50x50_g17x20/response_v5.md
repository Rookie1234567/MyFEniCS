# Task41extra Review V5 执行回应：实际坐标候选未获固定窗口准入

V5 唯一候选 mesh_actual_exact 把每个单元的 rank-2 局部张量直接交给原始 mesh coordinates 求值，再由同一张量生成局部 LU 与 R/T/S。它旨在让生产凝聚路径与 native volume action 使用相同的几何输入，减少平移、规范端点等 canonical 坐标处理带来的局部浮点差异；代价是原来 3 个 canonical 共享类变成 28,000 个 exact keys，构建费用和对象库存都随之增加。

本轮完成 actual exact-key 清点、8 个 cache-miss 前缀测量和两个保存单元的集成对照。cells 26762 与 26897 的原坐标以及 K/G/J/L 块均逐位重现 V4 保存的 actual 记录。构建仅推进到 fresh mesh 与 volume-owner 构建前缀；owner 并未完整建成。随后完整候选被固定时间门拒绝，分类为 CANDIDATE_NOT_ADMITTED。全域候选、两列作用和 checker 均未运行，因此这不是新的数值失败。

V3 的 two-input full-action 数值失败继续有效：两列误差为 3.042118678294192e-10 和 6.391893878204816e-10，超过原 1e-11 门。V4 保存数据审核、recovery PASS 与 action FAIL 也保持原分类。V5 没有推翻或重写这些结果。

| V5 问题 | 结果 |
|---|---|
| 冻结身份 | 分支 task41extra_phi90_p50x50_g17x20；consumer source 179cf7369e6bc5894fa87af6b74cf5c73938b6d4；contract SHA-256 f94f43133e5589062b1b2cba0e9cdf0261de43d077c40f3b35f60dfafa5db888 |
| donor | source afbe91e5947ed18fb74d7105097e129c1b8b4cc7；contract SHA-256 9e312f86cdd6b15fff9015faf4fb7dce19043fa3798a3f35cf2e57f79149713c；V3 manifest SHA-256 f55ac594382f40662954e19521ef9922d805abc64459cc7812877b12ec618465；input SHA-256 a0c45d0475bd2b41d2d19589831086468a62f39fdca5b74734b62751df1485c1 |
| actual-coordinate key 库存 | raw 与 oriented key 各 28,000；清单 16,224,652 B，SHA-256 147ab6347e6b0059ea97627a48802a970e8450d20e832a716bcd60d95233c952。按 exact geometry/kernel/material/orientation 身份计数，不按近似容差合并 |
| 两格集成对照 | cells 26762 和 26897 的坐标、K/G/J/L 块均 bitwise_equal=true；V4 几何参考报告 SHA-256 a47eb7a8795b5af542c23ae45915588d89c962d1af1bb8360b8a9d42f1e7c031。此项只验证两个局部重放 |
| 前缀实测 | 8 个真实 cache miss 的 kernel 时间总计 419.1692760037258 s，均值 52.39615950046573 s，范围 51.93273649–52.97407951 s。其余 phase 独立记录在 compact 与原 prefix JSON |
| 固定窗口准入 | window SHA 68e6d8dfcccc9dee98bc161730957dc76f70a9e2dea2ee78455b66c9d8b37c38，T0 2026-10-19T05:23:07.094241922Z。准入快照数值余额 712.8634632226167 s，估计剩余工作 1,490,279.122617107 s，缺口 1,489,566.2591538844 s |
| 数值与checker | 全域候选未建成；两列比较、candidate checker、200q、factor、KSP/FGMRES、完整场、A6、R/T/A 均 NOT_RUN。candidate_numeric_status=null；没有新的 official field，official_result=false |

## 前缀成本与准入计算

前缀测量在 fresh mesh 和 volume-owner 的构建过程中，对最初 8 个 cache miss 分别记账。kernel 占主要成本：总计 419.1692760037258 s，均值 52.39615950046573 s，范围 51.93273649–52.97407951 s。orientation、tensor preparation、LU/solve、Schur、observer 与 release 的 8 项逐笔时间保存在 prefix JSON；其 scope 分开记录。不能把整个 worker 父时间说成 kernel 时间，也不能把前缀称作完整 owner 构建。

按样本对剩余 exact classes 的分 phase max 估算，剩余构建上界为 1,488,176.122617107 s，约 17.224 天。之后预留 1,803 s，来自既有 V4 service parent 1,638.8259056420065 s 乘 1.1 安全系数；该父段已经覆盖 required checker，因此不再把 59.97374047804624 s checker 子段重复加一次。另有 300 s termination reserve，固定窗口总需求为 1,490,279.122617107 s。准入时原窗口仅余 712.8634632226167 s，故缺口 1,489,566.2591538844 s。

单独延长 24 小时仍不足以覆盖约 17.2 天的保守构建上界。本次不据此自行添加分块或缓存算法候选；需要由主审决定后续是否只测量/改造 actual per-cell kernel 的生成成本，并另行冻结范围与窗口。

raw 与 oriented key 各 28,000 个。retained numeric payload 上界为 348,561,972,000 B；key/cell metadata 上界为 53,760,000 B；condensation 与 key 合计上界为 348,615,732,000 B。workspace 派生值为 1,392,216,128 B，raw-cache 上界为 0 B，策略是一次生成一个 exact key、消元后释放。它们都是准入估算，不是全域分配或实测内存峰值。

本次 inventory/prefix attempt 的 simultaneous process-tree RSS 峰值为 6,674,780,160 B，task-cgroup memory 峰值为 6,830,514,176 B；process-tree swap 与专用 cgroup swap 的峰值/结束值均为 0，host pswpin/pswpout 变化也为 0 页，PSS 未采样。进程树 RSS 与 cgroup 是不同口径。由于全域候选没有构建，完整候选 peak 仍 NOT_MEASURED；不能把估算对象总量称为已分配，也不能说完整缓存通过内存准入。

证据总量投影为 13,314,647,284 B，低于 16 GiB 上限 17,179,869,184 B，合同另留 2 GiB free-space floor。attempt3 的停止原因为时间缺口，不是数值门或磁盘门失败。保留内容是回执、事件/资源样本、28,000 项 key inventory 和 8 项 prefix JSON；没有复制数值大数组。

## 三次正式尝试、修复与费用

| 尝试 | source / service parent | 结果 | 资源与清场 |
|---|---|---|---|
| attempt1 | 69ae04a4610dd80d49e08a650ac5787cf65838a0；myfenics-case-20261020T042351-2332485；4.526531178 s | audit 读取错误的 checker elapsed 字段名 required_checker_watchdog_seconds，KeyError；候选未构建 | watchdog 3.413762260 s；tree RSS peak 105,185,280 B；descendants_cleared=true，剩余子 PID=[] |
| attempt2 | 0985d12919b77db797f2a5eaa44cbd18e6a50919；myfenics-case-20261020T043358-2334668；99.455304882 s | 前一轮字段名修正已进入源码；fresh mesh levels 与 volume form compile 完成，随后 fresh volume owner 因缺少 shutil import 报 NameError；候选未构建 | watchdog 98.332699572 s；tree RSS peak 6,942,826,496 B；process-tree swap peak 0；后代已清场 |
| attempt3 | 179cf7369e6bc5894fa87af6b74cf5c73938b6d4；myfenics-case-20261020T044239-2335996；518.842395907 s | 两项前置字段/导入问题已修正；exact-key 库存、8 项测量和两格重放通过；完整候选因时间缺口 CANDIDATE_NOT_ADMITTED | watchdog 517.721660486 s；tree RSS 6,674,780,160 B；cgroup peak 6,830,514,176 B；swap 0；477 个样本；后代已清场 |

正式 worker 前另有两次入口拒绝：`myfenics-case-20261020T042025-2331661.service` 与 `myfenics-case-20261020T042212-2332132.service`。二者把 DAT 放在保存审核模式之前，导致 service 未识别保存审核路由；均未启动数值 worker。旧日志保留于工作站 `benchmarks/artifacts/user_services/<unit>.log`，单独耗时未记录，仍计入原固定窗口，不从历史删除。

三次 service parent 合计 622.824231967 s；准备和入口成本没有同口径的合格计时，记为 UNKNOWN，不并入 parent 合计。attempt1 的字段修正是让 audit 读取 V4 实际提供的 checker elapsed 字段；attempt2 后的最小修复再导入 shutil 并添加 disk-usage evidence gate 回归。最终 source 只在 volume-only audit 和对应 test 增加这项工程修复，不改数值算法、阈值、native rank-1、输入/RHS 或 solver default。

## 测试和下一断点

科学 source 69ae04a4 冻结前的几何/生产作用/路由定向子集为 10 passed in 0.74 s；0985d129 的 checker 计时字段修复后为 11 passed in 0.72 s；179cf736 的 shutil 导入修复只新增运行 disk-usage 回归，1 passed in 0.10 s。随后将整个 volume-only audit 模块与三份文档合同一起验证，32 passed、3 failed in 1.35 s；原始输出的路径与 hash 保存在 V5 compact。三个失败来自两个 owner 测试替身缺少 cfg.tags，以及一个 TinyOwner 替身缺少 build_audit；补齐真实配置/owner 元数据，并让 tabulation 替身接受 production 的 geometry_policy 关键字后，仅重跑原三项，3 passed in 0.90 s。修复只改测试文件，不改 production source；原32/3结果仍保留为修复前记录。资格化 WSL ABI preflight 与 git diff --check 通过。Ruff F821 为 NOT_RUN（运行环境没有 Ruff，未安装环境），全仓 pytest 未运行。

尚无 V5 全域候选、candidate checker 或两列原门结果。不能用两个局部对照或源码回归测试宣称几何修复已通过。24 小时也不足以覆盖当前前缀外推的全库存构建时间；接续前需要主审明确后续范围与资源窗口。此前失败、V3/V4 负结果和费用均保留，普通 solver default 与 master 未改变。

忽略目录中的原件包括：controller_v5_review 下的 report.json、prefix.json、service.json、watchdog.json；v5_attempt3_179cf736 下的 key inventory、events、resource samples、worker log；v5_prior_attempts 下 attempt1/2 receipts、watchdog 和失败日志。主控已离线核验17个归档原件的路径、字节数和 SHA-256 全部匹配；这只是证据身份核验，candidate numerical checker 仍为 NOT_RUN。原始回执不改写。
