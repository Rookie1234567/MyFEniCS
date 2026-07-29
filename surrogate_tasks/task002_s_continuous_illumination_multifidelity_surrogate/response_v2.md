# Task002 Response V2：M2A complete，M2 remains stopped

Review V1 的 M2A 已完整执行，正式 Gate 未放宽，Case112 的 9 个 raw 样本未改写。全部新
PDE 绑定 clean baseline `a0b9ae0e457b74876eb39346885d53e940ab1584`，MPI2、单线程、
zero swap 且 watchdog cleanup complete。

中心点独立 Full3D p4/h10 得到 `R/T/A=0.818608/0.001415/0.179977`，energy closure
`4.92e-13`。Hybrid p4 的 R/T/A 与其接近，但 p4 M80/120/160/240 的能量误差均约
`-2.6e-5`，所以增加 M 无法通过原 `1e-5` Gate。p5/p6 虽内部能量闭合，却分别给出
`R=0.631653/0.621509`、`A=0.362443/0.372251`，与独立 Full3D 不构成可信 p-convergence。

规定 LF stencil 13 点完成，4 pass + 9 fail；最大能量误差出现在 0.5°/45°，为
`-3.299e-4`。追加 HF 选择了最大误差/曲率邻域的 30°/45°/60°，连同强制 15° 共四点；
HF 响应均稳定在 `R≈0.621`，45° 另失败 biorthogonality Gate。

cutoff v2 将 incident m0 与非零级分离：中心点 m0 指标为 `0.0087265`，最近非入射级为
bottom m=-7 的 `0.277715`，所有 stencil 的局部角邻域均无非零级 Rayleigh crossing。
因此失败不能再归因于旧 near-cutoff 标签，而表现为低掠射 conical/intermediate-azimuth
Hybrid 表示及 p 阶分支不一致。

最终 disposition：LF4 不能作为 0.5°--10° 全角域统一 low fidelity；M2 Gate 仍未通过。
没有启动 49 点正式 campaign、四维 bulk、surrogate、angle DOE、P/Hybrid-P 或反演。
现提交 Case113、完整 compact records、失败分析和更新 outcomes，等待 ChatGPT Review V2。
