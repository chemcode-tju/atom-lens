# 开发与仓库结构

[返回 README](../README.md)

macOS 与 Windows 独立 App、Codex 侧栏插件和 Linux 远程后端共用核心实现。`tests/preview_host.py` 用于协议与界面开发。

| 路径 | 用途 |
| --- | --- |
| `install.py` / `Install.command` | 共用安装器与 Mac 双击入口 |
| `native/Desktop.m` / `native/desktop.html` | 原生 WebKit 窗口、文件面板、主机切换与远端安装界面 |
| `native/desktop_host.py` / `desktop_backend.py` / `desktop_worker.py` | 私有回环宿主、持久 STDIO/SSH 会话与桌面后端接口 |
| `native/remote_bootstrap.py` | 校验并安装服务器后端，可选注册远程 Codex 插件 |
| `native/Installer.m` / `packaging/build_macos.py` | 可选本地插件安装器与内置运行环境的 DMG 构建 |
| `native/windows/` / `packaging/build_windows.py` | Windows 原生文件面板与窗口宿主，以及带运行时的 NSIS 安装包构建 |
| `plugin/` | MCP 服务、格式解析、导出和 WebGL 界面；由 Codex 安装缓存加载 |
| `.agents/plugins/marketplace.json` | 仓库市场清单 |
| `native/` | 可选的 Mac 保存助手与 SSH 导出队列连接 |
| `examples/` | 小型结构及配套文件示例 |
| `tests/` | Python、JavaScript 回归与开发宿主 |
| `docs/` | 安装、使用、实现说明 |
| `design/` | 已选 A 方案的比例修订、Mac 图标与早期候选 |

展示名称是 Atom Lens，机器标识 `structure-viewer`、`atomic-structure-tools`、资源 URI、缓存与助手设置路径保持兼容。更改安装标识会影响旧用户升级和助手查找远程插件，不应只为改名而修改。

运行回归：

```sh
python3 -m unittest discover -s tests -p 'test_*.py'
for test in tests/test_*.cjs; do node "$test" || exit 1; done
```

动画测试需要可用的 FFmpeg/ffprobe。安装器测试在临时目录中检查完整运行包、缺失资源、重复安装和失败恢复，不修改用户真实 Codex 配置。

桌面 HTTP 仅绑定 `127.0.0.1` 随机端口，使用每次启动的新路径令牌、Origin/Host 和 JSON 请求头检查；页面不加载外部资源。原生导航限制在自身地址。本地和最多 4 个远程连接各自持有 worker、文件会话和查看器。切换仅改变当前查看位置；RPC 和导出始终按来源查看器的会话 ID 路由，断开后旧 ID 失效。隐藏查看器暂停后台索引和播放。远端额外的目录列表与导出分块接口只存在于桌面 worker，Codex 工具协议保持兼容。

测试真实 CLI 安装时，将 `CODEX_HOME` 指向临时目录，再运行安装器；核对缓存里的解释器、环境和插件版本。安装器自检不等于桌面端入口已刷新，也不等于远程保存验收。

正式发布前，在 Mac 新聊天验证：本地 XYZ/POSCAR、侧栏入口、保存／取消；在目标 Linux 远程聊天验证：主文件及配套文件、随机切帧、导出到服务器、可选助手导出到 Mac。缺少实际 Linux 环境时应明确标注未验收。

Mac DMG 的构建见 [macOS 打包说明](macos-release.md)。

## Windows 打包

构建需要 Python 3.11+ 和 NSIS 3（`makensis` 在 PATH 中）。在 macOS 上可用 `brew install makensis` 安装。在仓库根目录运行：

```sh
python packaging/build_windows.py
```

脚本校验并缓存 Windows x64 Electron 和 Python，输出到 `dist/windows-x64/`。安装程序在当前用户的 `%LOCALAPPDATA%\Programs\Atom Lens` 安装应用，并添加开始菜单快捷方式和卸载入口。
