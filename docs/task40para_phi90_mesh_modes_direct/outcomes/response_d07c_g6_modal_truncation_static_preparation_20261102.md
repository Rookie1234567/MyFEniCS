# D07C-G6：N32/N14 同网格模态截断静态准备

## 范围与基线

G6 N64 基线 `20261101T011146.746568Z` 已自然结束，exit 0，单场数值门通过，energy closure 为 `-8.405032225766718e-11`，子进程已清场。基线是 `[6,200,8]` / 9,600 cells、`m=-8…8,n=-64…1` / 4,488 modes。它仍是有限端口窗口，`FULL_DTN_NOT_VERIFIED`。

本次只准备两档有序 signed 子窗口。mesh、物理、P6 凝聚直接路线、q81 surface、q15/default volume、`scale_homogeneous_relative_only_v1` cutoff `1e-13`、场/模态/能量输出和数值比较门均沿用 G6；关闭 VTK/VTU/VTX/PVD。两份 `.dat` 只变更 run/profile identity，active signed window 由对应显式 profile 定义。

## 身份与模式核验

| case | signed window / modes | input SHA-256 | physical SHA-256 | resolved SHA-256 | 结果目录准备时存在 |
|---|---|---|---|---|---|
| G6 M8/N32 | `m=-8…8,n=-32…1` / 2,312；mode SHA `f81d3ff08f8950abcb4fa17736ee167e860d89c51baebc85a74fbea1b24493a4` | `867954d11d35c2afdd32c63b3cc28399bf3b3ade0eac59280b8d95db13ca4dce` | `6c2b170e4e2b7cc72628f43fb5a249d0c4305b3d7eadfa3f27d57c2589785387` | `c3d3c21c50f225e879fab5c1e5af82430e454bedae86fe2f430622a607d5eecf` | no |
| G6 M8/N14 | `m=-8…8,n=-14…1` / 1,088；mode SHA `8d7eda75f7bb3476fc2363231c6dde8ff6bdd225876cb41a4112c21a4799b158` | `6e44a8611e4781486b4756ca3d53d0c00315181944733458fc4137137d8ff7bc` | `6c2b170e4e2b7cc72628f43fb5a249d0c4305b3d7eadfa3f27d57c2589785387` | `522b30bc81590b7abb40c50f053240a21cc16f290bcaf72fd17eee2ca71aaed8` | no |

两窗均从相同 N64 有序父 inventory（4,488 keys，SHA `e4cef2ecadaab2563a46592dfe31df04aa47bc113f3a69e1ac0ecd70cebf2ef0`）选择。N32/N14 parent-index SHA 分别为 `86d4e9d09a0a91680b98814e5a39b07a30910e13622f709cb61fcba654ca17e6` 与 `1fc6bb7886a9858e3288ae45ee3ae50fea0bdf75881f03b52f45a26a3fe41fe1`；ordered signed-key SHA 分别为 `6c69e73eff8b237ee4d2c2242be5a4a9e7466ceb8a9000eed780dda75f559ded` 与 `03c5894de4fd5597da93a2971a1914ffca955b61e39a9f8db173d0fd39beebb0`。验证了 `N14 ⊂ N32 ⊂ N64`，轴哈希、实体 tags 和 G6 mesh plan 相同。

## 误差筛选与运行门

N64 已求解结果投影到 N32 时，省略通道 R/T 合计为 `1.606358203546357e-12 / 3.365566566377057e-12`；投影到 N14 时为 `5.772321850267811e-10 / 1.208698160845064e-9`。这些数只描述已有 N64 解的投影尾部，**不是** N32/N14 截断算子重新求解后的误差或通过结论。

每个独立新场仍需满足凝聚 residual `<=1e-9`、active-window A6 `<=1e-6`、energy balance 与 volume absorption 绝对差 `<=1e-5`，并保留 finite-value 检查。与 G6 N64 的比较门为总 R/T/A 绝对差 `<=1e-5`、每个共同 signed/power-carrying 通道 R/T 绝对差 `<=1e-6`、边界复幅及同坐标复 E/H 相对 L2 `<=1e-4`，不拟合相位。运行时测量各自 carrier/总耗时与整树 peak RSS，不从 N64 投影尾部或单一 RSS 作线性预测。

## 验证和下一步

| 检查 | 结果 | 范围 |
|---|---|---|
| G6 模态窗口、轴/mesh、no-VTK、worker argv、动态 CPU admission、cache/profile/one-shot 隔离 | 20 passed | 定向 G6/N32/N14 与 admission/profile 测试；无正式 FE 求解 |
| G3 N96、finite signed modes、D5C、D15、active FE port output 兼容组 | 56 passed | Task40 相关兼容测试 |
| Ruff、compileall、`git diff --check` | PASS | 本次改动文件 |
| N32/N14 formal loader 与 output parent 检查 | PASS | 两个 result parent 均不存在；未创建 |

目前未执行 full fresh、FE assembly/carrier、factor、PDE solve 或 systemd submission。N32/N14 scope、sidecar、service-unit identity 将绑定最终 clean source commit 后另行形成 hash-bound 主审包。执行顺序固定 N32 后 N14；每个 case 需主审对其 exact package 给出 PASS，并完成该 case 的完整 fresh PASS 后才可启动。N32 自然终态且清场后，再独立 fresh N14。Gate-CD 与本静态包无关。
