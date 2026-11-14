# 运行与证据索引

所有数值大文件保留在工作站 ignored artifacts。下表链接到轻量收据的相对路径；完整远端绝对路径、字节、SHA-256、输入和实际 worker 命令见 [compact_v1.json](records/compact_v1.json)。主控已核对本机取回的六份 summary/manifest/supervision 与原 artifact hash 清单一致。

| case_id / run 目录 | 科学 source | 监督秒数 | 采样进程树峰值 B | 终态 |
|---|---|---:|---:|---|
| `w13p5_direct` | `f1ad2aa51e27aa7ae014cf3a6257da8c1338dffd` | 66.181830557 | 439730176 | 退出0，swap0，后代为空 |
| `w13p5_n2` | `f1ad2aa51e27aa7ae014cf3a6257da8c1338dffd` | 142.657965131 | 761593856 | 退出0，swap0，后代为空 |
| `w13p5_n4` | `20712b4aa13c5c48aecfdf981ba8fbf97fe26e81` | 151.270012621 | 919085056 | 退出0，swap0，后代为空 |
| `w5_direct` | `20712b4aa13c5c48aecfdf981ba8fbf97fe26e81` | 68.079329847 | 593358848 | 退出0，swap0，后代为空 |
| `w5_n2` | `20712b4aa13c5c48aecfdf981ba8fbf97fe26e81` | 140.713219441 | 781942784 | 退出0，swap0，后代为空 |
| `w5_n4` | `20712b4aa13c5c48aecfdf981ba8fbf97fe26e81` | 184.090048321 | 936599552 | 退出0，swap0，后代为空 |

正式根为 `/home/fenics/Projects/laptop_share/benchmarks/artifacts/pstddm_workstation/runs/<case_id>`。每场 `artifact_hashes.json` 绑定原矩阵、RHS、解、场、模式、材料、runtime、输入、监督和输出；不把未取回的大数组冒称已本机重算。独立数值检查在工作站读取完整原始数组执行，其回执已取回并纳入 compact。

0.7 nm 的 no-FE preflight 同样纳入 compact，正式数值未运行。13.5 nm N2 原 local pair 数组未保存，不能离线重算该项；其原进程内数值和已有完整场审核保留，状态为 COMPLETE_WITH_LIMITATIONS。

六场监督父时间合计 752.9924059184268 s。各独立审核的进程内时间/RSS在各自回执中；服务启动、前置测试和未知人工准备时间不得混入或重复相加。直接/候选的 JIT 缓存状态、编译路径和算法不同，本表不是严格受控速度排名。

主控最终只读检查：本批 pstddm 用户服务无 running 项；邻项目 PID 2651881 仍存活，未停止或修改。邻项目所在父工作树 HEAD 保持 `12718ec898588eb94a7cd0f9d747dd21f8da9231`；本批工作站执行源码保持 `20712b4aa13c5c48aecfdf981ba8fbf97fe26e81` 且工作树干净。宿主已有 swap，不等于本批任务 swap；本批六场均 task swap=0。

## 合入边界

| 依赖组 | 内容与边界 |
|---|---|
| 可复用实现 | 显式波长/材料及 native workstation profile；先审源代码和相应测试，不改 ordinary default。 |
| runner/watchdog/checker | 薄 worker、现有监督 profile、局部矩阵保存和缺失历史数组的明确分类。 |
| compact/docs | 本目录结果、负结果与 hash 索引。 |
| research-only | PSTDDM 当前 p2 固定离散试验；物理能量与规模性能未资格。 |
| do-not-merge | ignored 原始大数组、缓存及任何主机凭据；本轮不合并 master。 |

## p6用户续作：第一次h10装配（失败保留）

`p6_h10_direct_13p5`，source `2ba53154fbcee9af30477b0398302bb24708b98b`，504 cells、612 modes、凝聚增广102996行/86586068 stored NNZ。2026-11-14 21:40:39至21:58:07（Asia/Singapore），supervisor完整1048.3153135273606 s。MUMPS桥接所读sysconfig仍含旧prefix，因编译器资格守卫退出；symbolic/numeric/场/R均未完成。进程树采样峰值3167588352 B，systemd任务cgroup峰值3638575104 B，两者口径不同；任务swap0、后代清空。原始及紧凑证据见[失败回执](records/p6_h10_attempt1.json)。旧文件不覆盖，修复后使用独立retry目录且继续累计费用。
