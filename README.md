# Atom Lens

**原子结构与分子动力学轨迹查看器。可以作为独立 Mac App 使用，也可以在 Codex 聊天侧栏中查看本地或 SSH 服务器上的结构，支持多种原子结构文件格式。**

## 安装指南

### Mac：下载、拖动、直接打开

> 当前 DMG 是本地预览包，尚未上传 GitHub Releases。以下为计划采用的普通用户安装方式；预览包仅支持 Apple Silicon、macOS 12 或更新版本。
> 最新本地测试包为 `preview-14.dmg`。独立 App 支持结构标签页、本地与远程结构分屏，以及按主机记住上次打开的目录。分屏或矮窗格会使用单行底栏，点击帧号可展开时间轴。后台索引与取帧并行需要 preview-8 或更新的服务器后端。

1. 从 [Releases](https://github.com/liyang-tju/extxyz-extension/releases) 下载对应的 `.dmg` 安装包。
2. 双击打开，将 **Atom Lens** 拖进 **Applications**。
3. 从 Applications 打开 Atom Lens，选择 **“打开本地文件”**，即可查看结构。
4. 想在聊天侧栏使用时，再点击 **“Codex 插件” → “安装到 Codex”**，完成后重新打开聊天。

基础查看器已经内置 Python 运行环境，**独立使用无需 Codex，也不需要用户安装 Python、conda、Git 或编译工具**。只有聊天侧栏模式需要支持插件的 Codex 桌面端。请保留 Applications 中的 Atom Lens，它包含运行环境。

独立 App 可以直接把本地或远程结构的导出结果保存到 Mac。**Codex 侧栏模式**下，若需要把服务器导出结果保存到 Mac，可在插件安装界面勾选“同时安装远程保存助手”；图形安装包已预编译助手。

本地预览包位于 `dist/macos-arm64/`，尚未使用 Developer ID 签名或经 Apple 公证，不是正式公开发行包。源码方式与高级依赖见[详细安装说明](docs/installation.md)。

### 服务器：在 App 中选择 SSH 主机

1. 点击 **“服务器”**，从列表选择 SSH 主机，或点击 **“新增”**。填写显示名称、主机和 Python 路径后，可点击 **“保存配置”**，保存多台服务器供下次选择。
2. 点击 **“安装／更新”**，App 会上传自带后端；服务器无需访问 GitHub。
3. 点击 **“连接”**，再浏览文件或按路径打开。轨迹在服务器按需读取，不必先完整下载。
4. 如果也要在 Codex 中使用，安装时勾选 **“同时安装到服务器的 Codex”**。然后在本地 Codex App 通过 SSH 连接同一服务器，重新打开远程聊天，即可使用侧栏查看器。

选中列表项只切换待编辑的配置，点击“连接”才切换服务器。面板会单独显示当前连接；重启 App 后保存的列表仍在，默认从本地 Mac 开始。

服务器需要 Python 3.9+，以及已经可用的 SSH 密钥／agent 登录。独立查看不需要服务器安装 Codex；勾选插件安装时才需要支持插件的 Codex CLI。特殊 Python 环境可在连接面板填写完整路径。Linux 运行环境尚未随包提供。[独立 App 与远程连接说明](docs/desktop.md)

如果自行安装，在服务器的仓库根目录运行：

```sh
python3 install.py
```

此命令是可选的源码安装入口；普通用户可以使用上述图形流程。无需在服务器安装 Mac 保存助手。

## 打开第一个结构

独立 App：点击“打开本地文件”，选择 [water.xyz](examples/water.xyz)。也可以拖入结构文件；多文件打开时选择主结构，其余作为配套文件。

Codex 侧栏：在对应主机的聊天中说：

> 请用 Atom Lens 在侧栏打开这个仓库的 examples/water.xyz，使用它的绝对路径。

也可以从聊天侧栏的工具入口打开 **Atom Lens**，选择本地文件、拖入文件，或从右上角文件图标中选择“按路径打开”。仓库自带的 [water.xyz](examples/water.xyz) 有两帧示意结构，适合验证安装。

远程文件请在对应服务器的 Codex 聊天中打开，例如：

> 请用 Atom Lens 打开 `~/work/run/` 目录，自动识别轨迹和配套文件。

支持直接传入计算目录，也支持单个文件路径。LAMMPS、CP2K XYZ＋CELL、GRO＋TOP、TRR／XTC＋TPR 会自动查找配套文件；只有多条轨迹或多个可能的配套文件时才显示选择列表。LAMMPS 续跑目录会参考来源记录或附近父目录中的 data 文件，界面显示实际配套路径。不会执行输入脚本或修改原始文件。XTC 直接分帧解码，优先配对 TPR；没有 TPR 时可配对 GRO，无需转换整条轨迹。

POSCAR、CONTCAR 和 XDATCAR 可以按原名打开，无需改后缀；普通文件链接若显示文本，可改用侧栏的“按路径打开”。多文件应来自同一次计算。[多文件配套与常用操作](docs/usage.md)

底部采用紧凑播放控件，帧率、倍速和步长可在播放中直接调整。第一帧读出后即可边建索引边播。单帧隐藏轨迹条；“视图”集中切换方向和单／双／四视图，“结构信息”查看粒子、原始类型和晶胞。

## 哪些功能需要额外依赖

| 要使用的功能 | 额外依赖 |
| --- | --- |
| XYZ/extxyz、VASP、ASE traj、LAMMPS 文本 dump、GRO；CP2K XYZ＋CELL | 无 |
| CIF、PDB、单独的 LAMMPS data | ASE |
| GRO＋TOP/ITP | MDAnalysis；标准力场还需 GROMACS 库或 `GMXLIB` |
| TRR＋TPR | 能读取该 TPR 版本的 GROMACS |
| GIF／MOV／MP4 导出 | FFmpeg |

只安装自己需要的依赖，并安装在**读取文件／编码的主机**上。例如需要 CIF/PDB 和动画时：

```sh
conda create -n atomlens -c conda-forge python=3.11 ase ffmpeg
conda activate atomlens
python install.py
```

安装器会使用该环境，后续无需手动激活才能在 Codex 内使用。请保留这个环境；迁移或删除环境后需重新安装插件。GROMACS 配置及单独安装 FFmpeg 见[依赖说明](docs/installation.md#可选依赖)。

上述 conda 安装方式用于源码／Codex 模式，不会更改独立 Mac App 的内置环境。当前 App 尚无本地科学依赖配置界面；服务器模式可填写已安装所需依赖的 Python 路径。

## 使用边界

- 每帧读取保护上限为 1,000,000 个原子；已实测 158,559 原子的 GRO／TRR／XTC 水盒，百万原子的交互性能尚未验证。XTC 解码无需额外 Python 包；XTC＋GRO 可直接读取，TPR／TOP 仍需可选科学依赖。VASP 4 缺少元素名时会报错。CIF/PDB/LAMMPS data 静态转换输入上限为 32 MiB，其余轨迹不受这个文件大小上限限制。
- 正在追加写入的受支持轨迹固定本次打开的范围，只显示完整帧；查看新增内容需重新打开，不是实时跟随模式。
- 测量基于当前显示坐标，不自动计算周期最短距离；质心校正不是自动 unwrap。氢键与普通化学键为几何判定。
- PDF 导出内嵌栅格图。实际可处理规模与导出尺寸受内存、GPU、磁盘和网络影响。

## 更新与更多说明

Mac 图形安装：下载新版 DMG，退出 Atom Lens 后替换 Applications 中的旧应用。使用 Codex 插件时，再打开“Codex 插件”并重新安装；保存助手需再次勾选。远端在“服务器”面板中分别更新，需要更新远程 Codex 插件时保留相应勾选。

源码或服务器安装：更新仓库后重新运行安装器即可：

```sh
git pull --ff-only
python3 install.py
```

使用独立 conda 环境时，先激活该环境，再运行 `python install.py`。每台主机分别更新；Mac 保存助手的更新另见安装说明。

- [独立 App 与远程连接](docs/desktop.md) · [安装、更新、卸载与依赖](docs/installation.md)
- [完整使用手册与常见问题](docs/usage.md)
- [开发与仓库结构](docs/development.md) · [更新记录](CHANGELOG.md)
- [加载与场景实现](docs/loading-and-scene.md) · [图标设计](design/README.md)

源码采用 [MIT 许可证](LICENSE)；内置 3Dmol.js 的许可证见 [LICENSE-3Dmol.txt](plugin/web/vendor/LICENSE-3Dmol.txt)。
