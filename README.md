# Structure Viewer for Codex

在 Codex 侧栏查看原子结构与分子动力学轨迹，支持本地文件、远程文件和配套拓扑／晶胞文件。结构始终只读；选择、测量、Wrap 和显示设置不会改写原文件。

当前代码版本：**0.13.2**。本文说明从源码安装和使用的方法；版本历史见 [CHANGELOG.md](CHANGELOG.md)。

- **结构与轨迹**：VASP、XYZ/extxyz、ASE traj、LAMMPS、GROMACS、CP2K，以及 PDB/CIF 静态结构。
- **交互查看**：多视图、原子选择与测量、按元素显隐、局部样式、质心漂移校正。
- **导出**：PNG/JPEG/PDF 快照与 GIF/MOV/MP4 动画；远程导出可通过 Mac 助手弹出系统保存窗口。
- **大轨迹**：先显示首帧，后台建立索引，完整帧按需读取并使用有限缓存，无需先下载整个远程轨迹。

无需 skill，也无需为查看器单独启动 HTTP 服务或开放端口。三维渲染资源随插件打包，不依赖外部 CDN。

## 目录

- [安装](#安装)
- [打开第一个结构](#打开第一个结构)
- [远程与多文件轨迹](#远程与多文件轨迹)
- [保存快照和动画到 Mac](#保存快照和动画到-mac)
- [支持的格式与可选依赖](#支持的格式与可选依赖)
- [常用操作](#常用操作)
- [常见问题](#常见问题)
- [更新与开发](#更新与开发)

## 安装

### 1. 安装本地查看器

需要支持 MCP Apps 文件入口和聊天侧栏入口的 Codex 桌面端、可执行 `codex plugin` 的 Codex CLI、Git，以及 **Python 3.9 或以上**。基础查看器仅使用 Python 标准库；部分格式需要[可选依赖](#支持的格式与可选依赖)。

在 Mac 终端执行：

```sh
git clone https://github.com/liyang-tju/extxyz-extension.git
cd extxyz-extension
codex plugin marketplace add .
codex plugin add structure-viewer@atomic-structure-tools
```

克隆需要仓库访问权限。若 `git clone` 提示无权访问，请先确认 GitHub 账户权限。

安装后重新打开 Structure Viewer 面板。如果未出现新入口，重新打开聊天；仍未发现时，再完整退出并重开 Codex。文件右上角列出 VS Code、Terminal 等的“打开”菜单是外部应用菜单，不是插件入口。

### 2. 在远程主机安装

每台需要查看结构的远程主机都要安装插件；Mac 上安装一次不会自动安装到服务器。在目标主机的终端中执行上面相同的克隆和插件安装命令，然后重新连接该主机的 Codex 远程聊天。

若服务器不能访问 GitHub，可将仓库复制到服务器再执行安装命令。插件注册至少需要保留 `.agents/plugins/marketplace.json` 和整个 `plugin/` 目录，目录关系与仓库一致。

**远程路径属于哪台机器，就在那台机器的 Codex 聊天中打开。** “按路径打开”会显示当前插件主机名，不是固定的 `mini.local`。

### 3. 可选：安装 Mac 保存助手

只在 Mac 上安装一次，即可接收多个远程主机的导出。需要 Apple Command Line Tools；未安装时先执行 `xcode-select --install`，完成系统安装后再运行：

```sh
python3 native/install_helper.py
```

请在本地仓库根目录运行。安装器会编译并注册菜单栏应用 **Structure Snapshot Saver**，同时设置当前用户登录时启动。无需 `sudo`。

本地 Mac 查看器保存到本机时直接调用系统文件夹窗口；这个助手用于**远程导出到 Mac**。具体使用见[保存快照和动画到 Mac](#保存快照和动画到-mac)。

## 打开第一个结构

仓库自带 [examples/water.xyz](examples/water.xyz)，包含两个示意水分子帧，不是模拟结果。

1. 在安装插件的主机上打开 Codex 聊天，让 agent 执行：

   > 请用 Structure Viewer 在侧栏打开这个仓库的 examples/water.xyz，使用它的绝对路径。

2. 侧栏显示水分子后，在底部时间轴切换两帧；左键拖动旋转，右键拖动平移，滚轮缩放。
3. 也可以从聊天侧栏的“＋／新增标签”工具列表打开 **Structure Viewer**，点击“按路径打开”，填写文件的绝对路径。在本地查看时，可用“本地文件”选择或拖入 `water.xyz`。

Agent 使用 `open_structure_path` 直接打开原文件，不需要生成中间文件。普通 `.xyz`、`.extxyz` 等文件链接也可进入文件查看器；若默认显示文本，可在文件查看器切换入口中选择 Structure Viewer，入口位置取决于 Codex 版本。

### POSCAR、CONTCAR、XDATCAR 不需要改名

使用上述聊天侧栏入口或让 agent 调用 `open_structure_path`，直接传入 `/work/run/POSCAR` 等原始路径即可。

当前宿主的按扩展名文件关联不能覆盖这些无后缀文件名，因此**普通 POSCAR 文件链接仍可能打开文本**。这不是解析器不支持；无需添加 `.poscar` 等后缀，也不要在外部应用“打开”菜单中寻找 Structure Viewer。

## 远程与多文件轨迹

### 推荐：让 agent 一次传入所有路径

在文件所在主机的远程聊天里，可以直接说：

> 请用 Structure Viewer 在侧栏打开 `/work/run/trajectory.dump`，配套读取同一次计算的 `/work/run/system.data` 和 `/work/run/log.lammps`，核对元素映射。直接打开，不生成中间文件。

对应工具参数如下，路径都是**当前远程主机**上的绝对路径：

```json
{
  "path": "/work/run/trajectory.dump",
  "companions": [
    "/work/run/system.data",
    "/work/run/log.lammps"
  ]
}
```

工具名为 `open_structure_path`。一次打开一条主轨迹及其配套文件；不要混入其他计算的拓扑或日志。普通聊天文件链接只携带一个路径，不能自动表达这一组关系。直接打开无需创建清单；只有需要可反复点击的 LAMMPS 文件链接时，才使用可选的 `.svtraj` 清单，示例见 [water.svtraj](examples/lammps/water.svtraj)。

### 手动打开

在“按路径打开”填写主文件绝对路径，配套文件每行一个绝对路径。这里读取的是**插件所在主机**的文件。“本地文件”则由 Mac 的文件选择器选择文件，不能用它浏览服务器目录。

本地多文件可一起选择或拖放。TOP 有目录层级的 ITP 引用时，优先使用“按路径打开”，保留原来的目录结构。

### 各格式如何配套

| 数据 | 主文件 | 配套文件与行为 |
| --- | --- | --- |
| LAMMPS | atom/custom 文本 dump | 加入同次计算的 data、输入脚本或 log，解析元素映射、单位和边界。支持 `metal` / `real`；质量推断会提示，映射冲突会报错。 |
| CP2K | 坐标 `.xyz` | 加入 `.cell`，按每帧注释的 `i = 步数` 精确匹配，每帧使用自己的晶胞；不是按文件行号配对。缺少所需步或重复步会报错，CELL 可有额外步。CELL 未声明周期方向，按三维周期显示。 |
| GROMACS | `.gro` | 可加入 `.top`，按分子拓扑展开并核对原子数、残基和原子名，以拓扑质量识别元素。 |
| GROMACS | `.trr` | 加入匹配的 `.tpr` 提供元素顺序和周期方向；逐帧从 TRR 读取坐标及晶胞，跳过不含坐标的记录。 |

GROMACS 的 nm 自动转换为 Å。按路径打开 TOP 时，本地 ITP 引用从 TOP 目录及其子目录解析，标准力场从 GROMACS 库读取；文件选择器方式需一并选择 TOP 引用的本地 ITP，不能保留嵌套目录关系。GRO＋TOP 和 TRR＋TPR 需要下面列出的额外依赖。

可先用仓库内的 [water.dump](examples/lammps/water.dump)、[system.data](examples/lammps/system.data) 与 [log.lammps](examples/lammps/log.lammps) 验证 LAMMPS 配套打开。

### 远程加载方式

结构文件保留在服务器。插件先返回首帧，再在服务器分批建立帧位置索引；查看或导出某帧时才传输其完整数据，Mac 侧栏负责渲染。后台扫描未完成时，可浏览已经索引的部分，帧数会继续增长。

缓存最多保留 16 帧，估算预算 64 MiB；单个大帧可以超过预算。**缓存预算不是轨迹文件大小上限**。对正在追加写入的 XYZ、VASP、dump、GRO 和 TRR，首次读取时固定文件末端，只纳入该范围内的完整帧；末尾半帧和之后追加的帧不加入本次查看。配套 log／CELL 也固定读取范围。需要最新内容时重新打开，文件更新通知不会自动重载视图。文件替换、截短或检测到已读内容被改写时仍要求重新打开。ASE ULM `.traj` 会回写文件头，暂不使用此追加容忍模式。更多实现细节见[加载与统一场景](docs/loading-and-scene.md)。

## 保存快照和动画到 Mac

### 本地结构

打开“快照”，设置文件名、格式、DPI、透明背景和裁边，再点击保存。Mac 插件会弹出系统文件夹选择窗口，取消不会写入文件。

### 远程结构：服务器与 Mac 二选一

- **保存到服务器**：默认目录为结构文件所在目录，可填写另一个已存在的绝对目录。同名文件自动追加序号，不覆盖已有文件。
- **保存到本地 Mac**：先在 Mac 安装保存助手，在远程查看器选择“保存到：本地 Mac”，点击“保存到 Mac…”。系统保存窗口出现后，选择本地位置并确认；也可取消。

正常的 Codex SSH 远程聊天**不需要再手动添加 SSH 配置或上传保存脚本**。助手自动发现当前 Codex 活跃的 OpenSSH 主机，沿用主机别名、SSH 配置文件、端口、跳板和认证参数，使用该主机已安装插件里的队列程序。菜单栏“结构快照 → 服务器”显示连接状态。

可同时连接多台服务器，各台保存请求独立处理；多个请求到达时，Mac 保存窗口依次弹出，保存／取消结果返回对应查看器。Mac 选中的路径不会回传服务器。

当前 Codex SSH 连接关闭了连接共享，因此助手另建一条非交互 SSH 通道来接收导出，**并非复用同一条 TCP 连接**。服务器须能通过现有认证非交互登录；助手不会枚举 SSH 配置中的全部主机并逐一登录。自动发现依赖 macOS 上 Codex 的 OpenSSH 进程；其他连接实现不保证自动识别。

### 需要独立连接时

若希望未打开远程聊天时仍监听某台服务器，或使用特殊队列路径，可在菜单栏选“添加独立连接…”，选择 SSH 配置文件和主机，再点“安装脚本并连接”。助手会部署队列脚本；每组配置文件与主机别名独立保存。移除独立配置后，仍活跃的 Codex 主机会恢复自动发现。

| 本地组件 | 位置 |
| --- | --- |
| 保存助手 | `~/Applications/Structure Snapshot Saver.app` |
| 登录启动项 | `~/Library/LaunchAgents/org.structure-viewer.snapshot-saver.plist` |
| 可选独立连接设置 | `~/Library/Application Support/Structure Viewer/connection.json` |

### 导出内容

快照沿用当前活动视图的相机、显隐、样式、原子序号、氢键和光影，不含临时选择圈、测量线、工具栏或坐标轴。PNG 可透明，JPEG/PDF 使用白底；可裁去四周空白，DPI 支持 96/150/300/600。PDF 内嵌栅格图，不是矢量结构图。

“导出动画”支持 GIF/MOV/MP4，可设起止帧、帧率、播放倍速和抽帧间隔；使用白色背景，固定开始导出时的视图与显示设置。编码需要插件所在主机安装 FFmpeg。远程动画也可通过保存助手保存到 Mac。

导出没有人为总文件大小上限，实际尺寸与耗时受 GPU、内存、磁盘及网络限制。当前使用 WebGL 渲染，不含光线追踪。

## 支持的格式与可选依赖

依赖应安装在**插件运行的主机**上。远程 TOP、TPR 解析和动画编码需要服务器上的依赖，仅在 Mac 安装不能替代。

| 格式 | 支持范围 | 额外依赖 |
| --- | --- | --- |
| XYZ / extxyz | 多帧；extxyz 属性、晶胞与 PBC；CP2K 可配 CELL | 无 |
| POSCAR / CONTCAR / `.vasp` | VASP 5/6，Direct/Cartesian，原名读取 | 无 |
| XDATCAR | 多帧、重复晶胞头部，每帧对应晶胞 | 无 |
| ASE `.traj` | 现代 ULM 多帧、可变原子数；不读旧 pickle | 无需 ASE |
| LAMMPS 文本 dump | atom/custom，多帧，可配 data/input/log | 无 |
| GRO | 单帧／多帧，坐标与晶胞 | 无；配 TOP 需要 MDAnalysis |
| TRR＋TPR | 坐标轨迹及匹配拓扑 | 能读取该 TPR 版本的 GROMACS |
| PDB / CIF / LAMMPS data 单独打开 | ASE 静态转换，输入最多 32 MiB | ASE |
| GIF / MOV / MP4 导出 | 动画编码 | FFmpeg |

XTC 尚未支持。VASP 4 缺少元素名时明确报错。静态转换的 32 MiB 限制不适用于 XYZ、XDATCAR、dump 等按需读取的轨迹。

建议为可选依赖建立独立 conda 环境，避免改变计算环境。例如：

```sh
conda create -n structure-viewer -c conda-forge python=3.11 ase mdanalysis gromacs ffmpeg
```

插件支持以下环境变量，值为已安装程序的绝对路径；必须在 **Codex 启动插件服务的环境**中生效，仅在无关终端 `export` 不会影响正在运行的服务：

| 环境变量 | 指向 |
| --- | --- |
| `STRUCTURE_VIEWER_ASE_PYTHON` | 安装 ASE 的 Python |
| `STRUCTURE_VIEWER_MDA_PYTHON` | 安装 MDAnalysis 的 Python |
| `STRUCTURE_VIEWER_GMX` | 兼容 TPR 的 `gmx` 可执行文件 |
| `GMXLIB` | 自定义 GROMACS 力场库目录（可选） |

使用独立环境时，可在源码 `plugin/.mcp.json` 的 `mcpServers.structure-viewer` 对象中添加 `env`，保留已有的 `command`、`args` 和 `cwd`。例如，将下面路径替换成该主机上的真实绝对路径，再重新安装插件并重开查看器：

```json
"env": {
  "STRUCTURE_VIEWER_ASE_PYTHON": "/absolute/path/to/env/bin/python",
  "STRUCTURE_VIEWER_MDA_PYTHON": "/absolute/path/to/env/bin/python",
  "STRUCTURE_VIEWER_GMX": "/absolute/path/to/env/bin/gmx"
}
```

这是 JSON 对象中的一个字段，添加时需与前一个字段用逗号分隔。只填写需要的依赖；每台主机的安装路径可以不同，更新源码时注意保留自己的设置。

FFmpeg 从插件进程的 PATH 等位置探测，需确保服务可见。Mac 可用 `brew install ffmpeg`；Linux 也可放入自动探测的独立环境：

```sh
conda create --prefix "$HOME/.local/share/structure-viewer-codecs" -c conda-forge ffmpeg
```

## 常用操作

| 操作 | 方法 |
| --- | --- |
| 旋转／平移／缩放 | 默认左键拖动／右键拖动／滚轮 |
| 快速切换视角 | `X` 看 YZ、`Y` 看 XZ、`Z` 看 XY；按住 `Option` 看反方向，作用于当前活动视口 |
| 复位视角 | 再次选择同一方向；另有适应视图按钮 |
| 点选／框选／反选 | 使用底部图标；任意视图模式下 `Shift`＋左键点击或拖框切换选中状态 |
| 测量 | 按点击顺序：2 原子距离、3 原子夹角（第二个为顶点）、4 原子二面角；5 个及以上显示组成 |
| 显隐与局部样式 | “显示设置”按元素显隐，或为所选原子设置样式与内置配色 |
| 主题、字号、语言 | 右侧齿轮设置，支持简体中文／English |
| Wrap | 独立开关，只沿启用 PBC 的方向折回 |
| 质心漂移校正 | 选参考帧与原子组并应用；随后清除或改变临时选择不会改动已应用的原子组 |

原子序号从 **1** 开始，质心参考帧从 **0** 开始。测量使用当前显示坐标，不自动计算周期最短距离。质心校正按质量加权，先校正再 Wrap；输入应是连续、未折回坐标，它不是自动 unwrap 算法。

氢键依据 N/O/F 供受体的距离与角度筛选，不代表电子结构判定；普通球棍键按距离推断，当前不包含跨周期边界的普通化学键。

## 常见问题

**安装了但没有 Structure Viewer 入口？** 先确认插件安装在当前聊天所在主机，重新打开面板／聊天，必要时重连远程聊天或重启桌面端。源码修改不会自动更新安装缓存。

**远程路径提示不存在，窗口却显示本地主机名？** 当前打开的是本地插件。切换到正确的远程聊天，再按原路径打开。

**POSCAR 仍然是文本？** 使用聊天侧栏的 Structure Viewer 入口，或让 agent 调用 `open_structure_path`；不要改文件名，外部应用“打开”菜单也不是此入口。

**有“本地 Mac”，点击后不弹窗？** 确认 Mac 菜单栏助手正在运行，“服务器”下目标主机显示已连接，远程也安装了当前插件。若提示助手未连接，检查非交互 SSH 认证；需要口令或交互式二次验证的连接无法直接建立保存通道。更新后重开查看器，避免旧服务继续工作。

**多文件元素识别不对或报配对错误？** 确认文件来自同一次计算，提供完整 data/log、TOP/ITP 或 TPR；CP2K XYZ 必须有可匹配的步号，CELL 必须包含这些步。不要仅凭轨迹显示成功判断元素、单位和晶胞一定正确。

**大文件帧数还在增长？** 后台正在建立索引，可以先看前面的帧。模拟程序可继续向文件追加，本次查看会停在打开时范围内的最后一个完整帧。想查看新增帧时重新打开；不是持续追踪模式。

## 更新与开发

更新已有源码安装，在每个安装主机的仓库目录执行：

```sh
git pull --ff-only
codex plugin marketplace add .
codex plugin add structure-viewer@atomic-structure-tools
```

Mac 保存助手更新时，在 Mac 仓库重新执行 `python3 native/install_helper.py`。随后重新打开查看器；若宿主仍缓存旧插件，重新连接聊天或在方便时重启 Codex。

开发回归需要 Python 和 Node.js，在仓库根目录执行：

```sh
python3 -m unittest discover -s tests -p 'test_*.py'
for test in tests/test_*.cjs; do node "$test" || exit 1; done
```

`tests/preview_host.py` 是本地协议测试宿主，不是产品启动方式。自动测试或模拟宿主通过不等于原生 Codex 已刷新插件；远程查看和 Mac 保存还需要实际入口验证。

## 许可与参考

项目源码采用 [MIT 许可证](LICENSE)。内置 3Dmol.js 的许可证见 [LICENSE-3Dmol.txt](plugin/web/vendor/LICENSE-3Dmol.txt)。

选择轮廓参考 ASE 的投影圆环思路，几何实现独立编写；质心校正语义参考 OVITO。更多内容见[加载与统一场景](docs/loading-and-scene.md)和[氢键显示调研](docs/hydrogen-bonds.md)。
