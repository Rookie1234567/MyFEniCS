# Task000 M0 本地环境只读盘点

## 1. 盘点身份与边界

| 项目 | 实测值 | 状态 / 说明 |
|---|---|---|
| 盘点日期 | 2026-07-27（China Standard Time / Asia/Shanghai） | `measured` |
| Windows 用户 | `admin` | `measured`，`C:\Users\admin` |
| WSL 用户 | `shenjh` | `measured`，由当前 Linux 用户和 repository path 确认 |
| 当前 distribution | `Ubuntu-24.04` | `measured`，默认 distribution，WSL2，运行中 |
| repository root | `/home/shenjh/Projects/MyFEniCS-Surrogate` | `measured`，位于 WSL ext4 Linux 文件系统，不在 `/mnt/c` 或 `/mnt/d` |
| artifact 目录 | 尚未建立 | `not_run`；M3 以后必须建立在 WSL Linux 文件系统并保持 Git ignored |
| 本阶段允许操作 | Windows / WSL / Docker / Git 只读盘点；新增本 inventory | 未启动 Docker Desktop，未安装或卸载软件，未注销 distribution，未删除数据，未运行 PDE |

本报告是 M0 Gate。用户在盘点期间曾原则性同意卸载 Docker，随后以最新明确指令撤销该授权并要求保留 Docker、跳过 M1。最终有效决策是：Docker Desktop、`docker-desktop` 和约 17.86 GiB Docker 数据盘全部保留；后续 Task000 不启动、不进入、不使用 Docker。

## 2. Windows 与 WSL

### 2.1 Windows 主机

| 指标 | 实测值 | 口径 / 结论 |
|---|---:|---|
| Windows edition | Microsoft Windows 11 家庭版 | `Win32_OperatingSystem.Caption` |
| Windows version / build | `10.0.26200` / `26200.8655` | CIM 返回 build `26200`；`wsl --version` 返回完整 Windows build `26200.8655` |
| 架构 | 64-bit | `measured` |
| 机器 | ASUSTeK ASUS EXPERTBOOK B3405CVA_P3455CVA | `measured` |
| CPU | 13th Gen Intel Core i7-13620H，8 cores / 16 logical CPUs visible to WSL | `measured` |
| 物理内存 | 16,733,323,264 bytes（约 15.59 GiB） | Windows `Win32_ComputerSystem` |
| pagefile | `C:\pagefile.sys`，17,408 MiB（17.00 GiB） | 当前使用 17 MiB，历史峰值 23 MiB |
| C: | 407,550,365,696 bytes；空闲 194,799,067,136 bytes（约 181.42 GiB） | NTFS；Docker 与 WSL VHDX 位于此盘 |
| D: | 614,522,155,008 bytes；空闲 575,180,742,656 bytes（约 535.68 GiB） | NTFS；不得据此把正式 FEM 移到 `/mnt/d` |
| Hypervisor | `HypervisorPresent = True` | 当前 WSL2 正常运行，满足功能性虚拟化前提 |

处理器 CIM 同时返回 `VirtualizationFirmwareEnabled=False`、`VMMonitorModeExtensions=False` 和 `SLAT=False`。这些值与 `HypervisorPresent=True`、WSL2 distribution 正在运行、Linux 内可见 VT-x 和 Microsoft hypervisor 的直接证据冲突；在 Hyper-V 已接管硬件虚拟化时，这组 guest-facing CIM 标志不能单独用于否决 BIOS/WSL2 前提。M0 结论以实际 WSL2 正常运行作为资格证据，不修改 BIOS。

### 2.2 WSL 平台与 distributions

| 指标 | 实测值 | 状态 / 说明 |
|---|---|---|
| WSL package | `2.7.3.0` | `wsl --version` |
| WSL kernel | `6.6.114.1-1` | Windows CLI；Linux `uname` 为 `6.6.114.1-microsoft-standard-WSL2` |
| WSLg | `1.0.73` | `measured` |
| 默认 distribution | `Ubuntu-24.04` | `wsl --status`，默认 WSL version 为 2 |
| `Ubuntu-24.04` | Running，WSL2 | 必须保留；Ubuntu 24.04.4 LTS (Noble) |
| `docker-desktop` | Stopped，WSL2 | Docker 专用；M1 候选删除项，但只能在精确确认后注销 |
| `docker-desktop-data` | 不存在 | 当前 Docker Desktop 使用单 `docker-desktop` distribution 加独立 `docker_data.vhdx` 布局 |

WSL VHDX：

| 所属 | Windows 路径 | 当前文件长度 | M0 决策 |
|---|---|---:|---|
| Ubuntu-24.04 | `C:\Users\admin\AppData\Local\wsl\{bb298883-9031-4854-a46f-fe067cfd0cb8}\ext4.vhdx` | 2,771,386,368 bytes（约 2.58 GiB） | **保留，不得注销或删除** |
| docker-desktop root | `C:\Users\admin\AppData\Local\Docker\wsl\main\ext4.vhdx` | 109,051,904 bytes（约 104 MiB） | M1 候选删除 |
| Docker data | `C:\Users\admin\AppData\Local\Docker\wsl\disk\docker_data.vhdx` | 19,177,406,464 bytes（约 17.86 GiB） | 内容未枚举；备份或放弃必须明确确认 |

### 2.3 当前 Ubuntu 资源

| 指标 | 实测值 | 结论 |
|---|---:|---|
| Ubuntu | 24.04.4 LTS | 已存在干净、合适的 Ubuntu LTS；M2 应优先复用，不应无意义重装 |
| WSL 可见内存 | 14,311,488 KiB（约 13.65 GiB） | 小于主机物理内存；后续 16 GB 资源纪律适用 |
| 当前可用内存 | 13,572,256 KiB（约 12.94 GiB） | M0 时点测量，不代表重型运行预算 |
| WSL swap | 40 GiB，当前使用 0 | swap 很大；后续不得把“能在 swap 中存活”当作成功 |
| repository filesystem | ext4，约 1007 GiB virtual，954 GiB available | 动态 VHDX 的 Linux 逻辑容量；实际受 C: 空闲空间约束 |
| 虚拟化 | VT-x，Microsoft hypervisor，full virtualization | `lscpu` |

## 3. Docker 只读盘点

### 3.1 安装与运行状态

| 项目 | 实测值 | 状态 / 说明 |
|---|---|---|
| Docker Desktop | 4.76.0 (product build 4.76.0.228118) | 已安装 |
| 安装目录 | `C:\Users\admin\AppData\Local\Programs\DockerDesktop` | 约 3.5 GiB filesystem usage |
| Windows Docker CLI | 29.5.2，API 1.54 | 可执行文件存在 |
| Docker Compose plugin | v5.1.4 | 由 CLI plugin inventory 确认 |
| Desktop autostart | `false` | `settings-store.json` |
| Windows Docker 进程 | 无 | Windows `Get-Process` 无 Docker 相关进程输出 |
| Docker daemon | stopped / unavailable | `desktop-linux` named pipe 不存在；未为盘点启动 Docker Desktop |
| Ubuntu WSL integration | 未启用或当前不可用 | Ubuntu 内 `docker` 包装器明确提示本 distribution 未激活 Docker Desktop WSL integration |

### 3.2 镜像、容器、volume 与空间

| 对象 | 数量 | 大致体积 | 证据状态 |
|---|---:|---:|---|
| images | unknown | 包含在约 17.86 GiB `docker_data.vhdx` 中 | daemon stopped，不能把 Docker CLI 返回的空 client info 误写成 0 |
| containers | unknown | 同上 | daemon stopped，未启动 Desktop |
| volumes | unknown | 同上 | daemon stopped，未挂载或修改 VHDX |
| Compose projects | runtime list unknown | n/a | daemon stopped；源码扫描发现现有 Compose 定义 |
| Docker local data directory | n/a | 约 18 GiB | `C:\Users\admin\AppData\Local\Docker` filesystem usage |
| Docker Desktop program | n/a | 约 3.5 GiB | 安装目录 filesystem usage |
| 预计可释放空间 | n/a | 约 21.5 GiB 上下 | `derived`：程序约 3.5 GiB + local data 约 18 GiB；稀疏 VHDX、卸载器保留项会使实际释放量不同，M1 后必须重新实测 C: 空闲空间 |

没有启动 daemon 的前提下，无法安全、真实地列出 data VHDX 内每个 image/container/volume 的身份与独立体积。可审计的两个选择是：

1. 保守备份：Docker 停止时复制完整 `docker_data.vhdx` 到用户确认的备份位置，再卸载；
2. 明确放弃：用户确认不需要其中任何 image/container/volume 后，允许卸载器和 Docker 专用数据清理删除该 VHDX。

### 3.3 其他项目依赖线索

只读文件扫描发现：

- 当前 repository 保留 `Dockerfile.mpc` 和 `docker/Dockerfile.stage4`，但 Task000 明确规定 Docker 不再是本支线正式后端；
- `C:\Users\admin\Desktop\Code\docker-compose.yml` 定义 `code-dolfinx:latest` 与 `code-dolfinx-mpc:latest`；
- `C:\Users\admin\Desktop\Code` 下的多个旧 FEniCS 项目、staging 目录和备份目录仍含 Dockerfile。

因此只能得出“存在历史或可复现 Docker 项目定义”，不能得出“其他项目绝对不再依赖 Docker”。卸载 Docker Desktop不会删除这些源码文件，但会使其 Docker 运行入口不可用，除非未来重新安装。用户已说明 Docker 可以卸载；是否放弃 data VHDX 中的已构建 image、container 和 volume 仍需精确确认。

## 4. Git 工作区

| 检查项 | 实测值 | Gate |
|---|---|---|
| root | `/home/shenjh/Projects/MyFEniCS-Surrogate` | pass |
| absolute git dir | `/home/shenjh/Projects/MyFEniCS-Surrogate/.git` | pass |
| origin | `https://github.com/Rookie1234567/MyFEniCS.git` | pass |
| branch | `codex/only-one-13p5nm-surrogate-inversion` | pass |
| upstream | `origin/codex/only-one-13p5nm-surrogate-inversion` | pass |
| HEAD | `5f43fb1ca01be2e323e5573b337d4ea0fca2164f` | `measured` |
| `HEAD...@{u}` | `0 0` | pass，同步 |
| `origin/master...HEAD` | 原命令不可执行 | `--single-branch` clone 未创建本地 `origin/master` ref；未 fetch、未切换分支 |
| remote master | `9c2160d41382026352908d692ad479dc4508424d` | 通过只读 `git ls-remote` 获取，等于任务书 `initial_forward_source_sha` |
| remote-master-SHA `...HEAD` | `0 6` | 以 SHA 直接比较：master 侧 0，当前分支侧 6；merge-base 为同一 initial base SHA |
| 工作树 | clean | 盘点开始时 `git status --short` 无输出；新增本 inventory 后预期仅出现本任务文件修改 |

M0 Git Gate 通过。不得 fetch/merge/rebase/cherry-pick/switch 到 `master` 或任何其他分支；后续提交和 push 只能进入当前代理分支。

## 5. M0 Gate 决策清单

### 5.1 必须保留

| 内容 | 原因 |
|---|---|
| `Ubuntu-24.04` distribution 及其 2.58 GiB VHDX | 当前合格候选 Linux 后端、当前 Codex 会话和 repository 所在环境；**不得注销** |
| 当前 repository、branch、`.git` 和所有用户源码 | Task000 唯一执行工作区 |
| `C:\Users\admin\Desktop\Code` 中的项目与备份文件 | 卸载 Docker 不等于删除项目源码 |
| Windows C:/D: 上所有非 Docker 用户数据 | 不属于 Task000 删除范围 |
| Docker data VHDX | 在用户明确选择备份或放弃前临时保留 |

### 5.2 需要备份或明确放弃

| 内容 | 当前状态 | 下一步选择 |
|---|---|---|
| `docker_data.vhdx`（约 17.86 GiB） | 对象清单 unknown；daemon stopped | A. 完整复制备份；或 B. 用户明确确认其中所有 images/containers/volumes 均可放弃 |
| Docker 用户配置 | `.docker` 与 Roaming 配置体积较小 | 默认无需备份；如需保留 registry/context 设置，应在卸载前另行复制。不得输出或提交凭据内容 |

### 5.3 候选卸载 / 删除（M1，尚未执行）

| 内容 | 精确边界 |
|---|---|
| Docker Desktop 4.76.0 | 使用已记录的官方 uninstall entry；当前已停止 |
| `docker-desktop` WSL2 distribution | 仅 Docker 专用 distribution；卸载后核验是否仍存在 |
| Docker data VHDX / local data | 仅在用户明确放弃 Docker data 后允许清理 |
| Docker CLI plugins /残留配置 | 只在卸载器结果审计后提出最小、明确的残留清理；不得泛化删除用户目录 |

明确排除：`Ubuntu-24.04`、其他用户 distribution、当前 repository、`Desktop/Code` 项目、任何非 Docker 用户文件。

### 5.4 新建内容（后续阶段）

| 内容 | M0 建议 |
|---|---|
| 新 Ubuntu distribution | **不新建**；现有 `Ubuntu-24.04` 已是 WSL2、Ubuntu LTS、位于 Linux 文件系统，应在 M2 复用并资格化 |
| project-local `.venv` | M3 建立，必须位于 repository 内 |
| 独立 cache/log/artifact | M3 建立在 WSL ext4；不得放到 `/mnt/c` 或 `/mnt/d` |
| complex PETSc/SLEPc/DOLFINx/MPI stack | M3 按仓库 ABI 说明安装和资格化；M0 不安装 |

### 5.5 可能需要重启或中断

| 步骤 | 可能影响 |
|---|---|
| Docker Desktop 官方卸载 | 卸载器可能要求 Windows restart；执行前应保存其他应用工作 |
| 注销 `docker-desktop` | 只应影响已停止的 Docker distribution；不得运行 `wsl --shutdown` 终止当前 Ubuntu/Codex 会话 |
| M3 系统包安装 | 可能需要用户在 Ubuntu 终端输入 sudo 密码；Codex 不索取、记录或回显密码 |

## 6. M0 结论与停止点

| Gate | 结论 | 证据 |
|---|---|---|
| 唯一 Git branch/upstream | pass | 当前分支与 upstream 正确，HEAD 与 upstream `0 0` |
| WSL2 前提 | pass | WSL 2.7.3.0；Ubuntu-24.04 Running / version 2；HypervisorPresent |
| Linux filesystem | pass | repository 位于 ext4 `/home/shenjh/...` |
| 合适 Ubuntu 是否已存在 | yes | 24.04.4 LTS；建议复用，不重建 |
| Docker 是否已停止 | yes | `docker-desktop` Stopped；Windows daemon pipe 和 Docker 进程均不存在 |
| Docker 对象是否已完整枚举 | no | daemon stopped；data VHDX 约 17.86 GiB，不得写成 0 objects |
| destructive M1 | **skipped_by_user** | 用户最新指令要求保留 Docker；不卸载 Desktop、不注销 `docker-desktop`、不删除 data VHDX |

M0 到此停止。未执行 Docker uninstall、`wsl --unregister`、数据删除、系统安装、PDE、p6/h10、批量训练数据生成、训练或反演。

## 7. 用户最终决策与后续边界

| 项目 | 最终状态 |
|---|---|
| Docker Desktop | 保留，不卸载 |
| `docker-desktop` | 保留，不注销 |
| Docker images / containers / volumes / VHDX | 全部保留，不删除、不清理 |
| Task000 M1 | `skipped_by_user` |
| Task000 后续执行后端 | 仅当前 `Ubuntu-24.04` 原生 WSL2 环境 |
| Docker 使用边界 | 不启动 Docker Desktop，不进入 `docker-desktop`，不调用 Docker daemon，不用 Docker 执行安装、测试或 FEM |

该决策允许 Task000 直接进入 M2：复用并审计现有 `Ubuntu-24.04`，随后建立原生 WSL complex FEM 环境。Docker 保留不构成后续环境资格化证据。
