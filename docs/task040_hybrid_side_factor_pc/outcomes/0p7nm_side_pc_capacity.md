# 0.7 nm side-PC capacity boundary

## Status: not_run_by_gate

Task040 没有取得 0.7 nm 资格结论。T40-3 的固定三组、固定一阶 impedance 和固定
forward/backward sweep 是真实数值负结果；V1-1 的 scalar Krylov 也是 directional fail。
但 V1-2 Run B 在 exact oracle ready/release 后触发 `45.05752944946289 GiB` resource hard
stop，尚未得到 exact interface probe 或 projected transmission 数值。因此不能把本次停止
写成 transmission mechanism fail，也不能把 V1-3、V1-4、bounded patch、Level B、top/full
Hybrid 或 h3 当作已测试失败。

最新硬停止最可信的 blocker 是同一 MPI8 进程中 exact-oracle 阶段的内存/allocator 生命周期
与后续 projected/scalar 构造的叠加：逻辑 factor count 已记录 `3 -> 0`，但 RSS 不一定随
对象销毁立即回落。exact oracle 的构造/释放不等于 projected transmission 已通过或失败。
这排除了“本次已证明 transmission 数学机制失败”的说法，但也没有证明资源方案可行。

如果未来继续，优先审查阶段分进程、持久化 V1-2 packet 或有证据的 collective heap trim；
不要据本次 raw 自行选择 coarse、modal DtN、具体 mode basis 或某种 allocator 方案。

另一个、较早且独立的边界仍然成立：T40-3 exact-subdomain solve 仍给出五个 rho 全部大于 1，
这提示固定标量一阶 impedance 缺少人工截面上的跨截面/多模切向传播耦合信息，并排除了
“只是 local solve 不准”作为 T40-3 的充分解释。但这不能外推为所有 bounded local PC、coarse
space、完整 Hybrid 或 0.7 nm 都不可行。
