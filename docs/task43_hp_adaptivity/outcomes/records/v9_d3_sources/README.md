# V9 D3 source and preparation archive

下面的 driver、probe、sanity 和只读审计脚本均为原字节审阅副本，不是执行授权或新运行入口。准备快照与root终态审计原件也按字节复制在 `preparation/`；ignored原件没有被移动或改写。

| 档案文件 | 原件来源 | SHA-256 | 用途 |
|---|---|---|---|
| `run_d3.sh` | `benchmarks/artifacts/task43/v7_support/d3_pml_ob1_import_probe_attempt1/driver_snapshot/run_d3.sh` | `e84d2eb0bfcd257549fcd85b336d5ce9ea5f8faa72eef5261e7ca936d076127a` | 受控支持 watchdog 外层启动脚本 |
| `probe_import_affinity.py` | `benchmarks/artifacts/task43/v7_support/d3_pml_ob1_import_probe_attempt1/driver_snapshot/probe_import_affinity.py` | `fa0dea6e8e049134c77c68e356eb377afeabd6080246e11b2e6acf5fbad3e1d4` | native imports、ABI/affinity 检查及固定 S2 fixture 的实际 worker |
| `sanity_once.py` | `benchmarks/artifacts/task43/v9_resume_preparation/sanity_once.py` | `fcefb49300b51356844df6b1276b6cdfc58bf881691e1d7d4414043370520ade` | D3 前唯一 stdlib/AST 合成 sanity 的实际输入 |
| `root_terminal_audit.py` | `/tmp/task43_v9_terminal_audit.py` | `d2c0801ab40ddae3a47798c16ebc6f6bf375adbe747f370408b9f7282cfaed38` | root 对本次已保存原件进行只读终态复核的脚本；没有运行PDE |

`preparation/` 内轻量原件及SHA：

| 文件 | SHA-256 | 内容 |
|---|---|---|
| `prelaunch_snapshot.json` | `ef12d0f5aed0d1925b274b1996d4c06743a84eada56ffa3a52044b4f0f883919` | S3冻结快照、完整八项源码清单和D3前置状态 |
| `s1_static_summary.json` | `d9e79dd8057ca08d9f99bc6b4f715b68600808c75487add0395ebbadb125641c` | S1只读输入、selector、ELF和依赖摘要 |
| `root_s1_review.json` | `6f72d07d0fdeaf7141a95b69013608225fc99826f07af7f2fa9402c99401f000` | 15个ELF、61条依赖边及3个桥接对象的独立审核 |
| `direct_needed_edge_map.json` | `d013d64d8c9e300e39b04b927ba23c3e9e5c55d1f02cded732550cd4093401e3` | 从已有61-edge静态stdout提取的逐项needed SONAME→candidate/realpath/object hash/BuildID/package映射；没有重新采集或加载库 |
| `root_s2_adoption.json` | `834314ef9a386f39aada91eee1cb1e1b86147b91bbe2674dea381dacb7d2b030` | 两个冻结driver字节与唯一D3 dispatch前状态 |
| `sanity_result.json` | `721a7a674c55c1d2eb5e70b48a59b1d1a64e9cafb51c2e905d82eb1798a62b05` | 19/19 synthetic sanity结果 |
| `root_terminal_audit.json` | `6ea7fb7f72dc24372db7a9a28e7d3711adf8a827ed7df2da02847de5a2f0a4ba` | D3终态、trace、资源、source/input hash和清理的root审计 |
| `closeout_path_read_error.json` | `5d4530bdd16fa790b5e7d15a1f8909c2cfaff6600afddaa8cddfad2e91acf1b5` | 收尾只读命令误拼两个sanity文件名；保留cat错误、后续正确路径与未计时限制 |

身份分开记录：V8 review提交与实际D3 source HEAD均为 `ef1e1ca5bb0b79f7cf5f6b6ce828d0e352ac44ba`；被审固定代码提交为 `c245dd060882df4dc6f30224ac0fa8be93f764d2`。八项tracked source hash匹配固定代码提交，D3实际shell/probe各自匹配冻结SHA。运行仅是受限import/fixture检查，不含mesh、assembly、solver或PDE。最终范围是 `PASS_LIMITED_ENGINEERING`，不是科学、生产或merge资格；详见[V9 D3 resume closeout](../v9_d3_resume_closeout_v1.json)。
