# 安装与维护

[返回 README](../README.md) · [使用手册](usage.md)

## Mac 图形安装（本地预览）

已提供 Apple Silicon、macOS 12+ 的独立 App DMG 预览包。普通用户流程为：下载 DMG → 拖动 Atom Lens 到 Applications → 打开结构文件。运行环境随应用提供；独立查看无需 Codex、外部 Python、conda、Git 或开发工具。需要聊天侧栏时，先安装 Codex，再打开 App 的“Codex 插件”并点击安装。

服务器图形安装与独立查看见[桌面与 SSH 使用说明](desktop.md)。服务器需要已有 Python 3.9+；可以同时注册远程 Codex 插件。

图形安装包中也包含预编译的保存助手，勾选即可安装，无需编译。请保留主应用：插件和可选助手使用其中的 Python；如果移动主应用，重新打开应用并安装一次，以更新路径。更新应用前先退出 Atom Lens；更新保存助手时重新勾选该选项。

当前包只做了本地 ad-hoc 签名，尚未使用 Developer ID 签名或通过 Apple 公证，未上传 Release。正式分发前的工作见[Mac 打包说明](macos-release.md)。

## 源码与服务器安装

在完整仓库的根目录运行 `python3 install.py`。Mac 可以双击 `Install.command`；Linux 服务器使用同一个 Python 安装器。服务器首次安装前，先建立对应的 Codex 远程聊天，或在服务器配置支持插件的 Codex CLI。

基础查看器无需 pip、conda 环境、管理员权限或开放网络端口。必须已有 Python 3.9+ 和支持插件的 Codex；Mac 未安装 Python 时，可用 Homebrew 安装：`brew install python`。

安装器依次完成：查找 Codex → 复制运行文件 → 自检 MCP 与完整界面 → 注册市场与插件。不会自动下载依赖、修改 SSH 配置、安装登录项或连接其他服务器。

如果 CLI 不在 PATH 或常见应用目录，在仓库根目录 `install.py` 顶部的 `codex_executable` 填入完整路径后重试。源码副本应包含隐藏目录 `.agents/plugins` 与完整 `plugin` 目录。直接解压 GitHub ZIP 也可安装，不强制要求 Git。

## 安装位置与环境

| 内容 | 默认位置 |
| --- | --- |
| 安装器管理的源码副本 | `~/.codex/structure-viewer-source` |
| Codex 运行缓存 | 由 `codex plugin add` 管理 |
| 保存助手（可选） | `~/Applications/Structure Snapshot Saver.app` |
| 助手登录项（可选） | `~/Library/LaunchAgents/org.structure-viewer.snapshot-saver.plist` |
| 助手独立连接设置（可选） | `~/Library/Application Support/Structure Viewer/connection.json` |

设置了 `CODEX_HOME` 时，源码副本使用该目录。插件仍以 `structure-viewer@atomic-structure-tools` 标识，展示名为 Atom Lens，旧安装可直接更新。

安装器仅复制运行文件和市场清单，不复制测试、大轨迹或设计文件；只在安装副本写入当前 Python 与检测到的程序路径。源码中的 `plugin/.mcp.json` 无需手改。源码下载目录可移动，但所绑定的 Python 环境应保留。使用 DMG 安装时，请保留 Atom Lens 应用的安装位置；移动后需重新点击安装。

重新运行安装器即可刷新安装副本。预检失败不会替换原副本；注册失败会恢复原副本文件，但 Codex 可能已记录市场地址，修复提示的问题后重试即可。安装器不会用旧配置整体覆盖用户的 Codex 设置。

## 可选依赖

XTC 解码器已内置，XTC＋GRO 不需要额外 Python 包。若使用 TPR 拓扑，需要已有 GROMACS；GRO＋TOP 或 XTC＋GRO＋TOP 的 TOP／ITP 展开需要 MDAnalysis。

按需在文件所在主机安装。推荐独立 conda 环境，例如：

```sh
conda create -n atomlens -c conda-forge python=3.11 ase ffmpeg
conda activate atomlens
python install.py
```

GRO＋TOP 需要 MDAnalysis：

```sh
conda install -n atomlens -c conda-forge mdanalysis
```

TRR＋TPR 需要 GROMACS；GRO＋TOP 引用标准力场时，也需要相应力场文件：

```sh
conda install -n atomlens -c conda-forge gromacs
conda activate atomlens
python install.py
```

GROMACS 必须兼容生成 TPR 的版本。已有集群 GROMACS 时，可先加载对应模块，再运行安装器；若运行还依赖模块设置的动态库环境，应由集群环境提供这些变量，仅记录 `gmx` 路径不能代替整个模块环境。

只需动画编码时，Mac 可执行 `brew install ffmpeg`；服务器可使用已有 FFmpeg，或：

```sh
conda create --prefix "$HOME/.local/share/structure-viewer-codecs" -c conda-forge ffmpeg
```

之后重新运行安装器并重开查看器。插件也会探测运行 Python 环境的 `bin/ffmpeg` 和上述服务器环境。

特殊安装位置可以在运行安装器前设置以下环境变量，安装器会记录到该主机的安装副本中：

| 变量 | 指向 |
| --- | --- |
| `STRUCTURE_VIEWER_ASE_PYTHON` | 已安装 ASE 的 Python |
| `STRUCTURE_VIEWER_MDA_PYTHON` | 已安装 MDAnalysis 的 Python |
| `STRUCTURE_VIEWER_GMX` | `gmx` 可执行文件 |
| `STRUCTURE_VIEWER_FFMPEG` | `ffmpeg` 可执行文件 |
| `GMXLIB` | GROMACS 力场库目录 |

请填写真实绝对路径。重新安装时需要再次提供特殊变量；常规安装只需激活目标 conda 环境，无需这些变量。

## Mac 保存助手

只有“远程导出 → 本地 Mac”需要助手。Mac 本地查看与保存、导出到服务器均不需要。助手保持原应用名称与标识，避免已有连接设置丢失。

在 Mac 仓库根目录执行：

```sh
python3 native/install_helper.py
```

以下编译要求只适用于源码安装；DMG 安装包已包含助手。若源码安装提示缺少编译工具，先执行 `xcode-select --install`，完成 Apple 安装窗口后重试。安装器会编译应用、注册当前用户登录项并启动助手，无需 sudo。双击安装入口也提供相同的可选步骤。

助手自动发现 Codex 正在使用的 OpenSSH 主机；需要服务器已安装插件且支持非交互 SSH 认证。无需再逐台配置服务器地址。特殊连接、手动部署和保存行为见[使用手册](usage.md#保存快照和动画到-mac)。

## 更新与卸载

Mac 图形安装：使用新版 DMG 替换 Applications 中的应用，再点击安装；保存助手需在更新时再次勾选。

Git 安装：`git pull --ff-only` 后重新运行 `python3 install.py`。使用专门环境时先激活它。ZIP 安装：下载新版完整源码后运行同一安装器。Mac 保存助手更新时重新运行 `python3 native/install_helper.py`。

卸载插件使用：

```sh
codex plugin remove structure-viewer@atomic-structure-tools
```

不再使用此市场时，再运行 `codex plugin marketplace remove atomic-structure-tools`。如 CLI 不在 PATH，使用安装器显示的 Codex 完整路径。卸载插件及可选保存助手后，可将 Applications 中的 Atom Lens 移到废纸篓。随后可手动移除安装器管理的 `structure-viewer-source` 副本；不会删除结构文件或用户导出。

如需卸载保存助手，先在菜单栏退出助手，并在“系统设置 → 通用 → 登录项”中停用它，再移除上表中的应用及对应 LaunchAgent。独立连接设置可保留，便于以后恢复。
