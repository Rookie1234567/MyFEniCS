# M2 连续角域资格化（Review V1 / M2A 更新）

解析 order-window Gate 仍通过，但 LF4 全角域数值资格化未通过。Case113 的规定 LF stencil
为 13 点，结果 4 pass + 9 fail；失败集中在低掠射的中间方位角，并随 conical 方位增强。
正式能量阈值保持 `1e-5`。

cutoff diagnostics v2 将 incident/specular m0 与非零衍射级分开：0.5° 的
`incident_specular_abs_beta_over_k0=0.0087265`，但中心点最近非入射级为 bottom m=-7，
`nearest_nonincident_abs_beta_over_k0=0.277715`；规定局部角邻域没有真正非零级 Rayleigh
crossing。因此旧 near-cutoff 标签不能解释失败。

独立 Full3D p4/h10 在 0.5°/15° 的闭合误差为 `4.92e-13`。Hybrid p4 的 R/T/A 接近
Full3D，但 M80--M240 均稳定失败能量 Gate；p5/p6 虽能量闭合，却进入与 Full3D 不一致的
响应分支。结论为：`S-Hybrid computable across the full formal angle domain = not
established`，且 LF4 不能作为统一 low fidelity。M2 controlled stop 与 bulk 禁令继续有效。
