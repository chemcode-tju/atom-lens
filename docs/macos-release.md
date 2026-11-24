# Mac 图形安装包

[返回 README](../README.md) · [安装说明](installation.md)

## 普通用户流程

Release 下载 DMG → 拖动 **Atom Lens** 到 **Applications** → 直接打开结构文件。需要聊天侧栏时，再打开“Codex 插件”注册。基础查看不要求用户自行安装 Python、conda、Git 或 Apple Command Line Tools。

这是独立结构查看器，同时提供可选的 Codex 插件安装。请保留 Applications 中的应用；本地插件使用其内置运行环境。CIF/PDB、特定 GROMACS 拓扑和动画编码仍属于可选依赖，见安装说明。

当前构建为 **Apple Silicon / macOS 12+**，不声称已经验证 Intel Mac。App 可通过 SSH 上传 Linux 后端，服务器需已有 Python 3.9+；远程 Codex 插件为可选安装。

## 构建

维护者需在 Apple Silicon Mac 上准备 Python、Command Line Tools，以及已经渲染好的 `design/app-icon.png`：

```sh
python3 design/render_icons.py
python3 packaging/build_macos.py
python3 packaging/verify_macos.py
```

构建器只生成本地预览，不上传 GitHub。输出位于 `dist/macos-arm64/`，包括应用、DMG 和 SHA256 校验文件；当前为 `preview-14`，表示预览包修订号。图标修改时需要本机 Inkscape；图标源图、暗色版本和小尺寸加重版本由同一脚本生成，16/32 pt ICNS 图层采用加重版本。`dist/` 已忽略，不应把运行环境二进制提交到源码仓库。

Python 采用 Astral 的 python-build-standalone 官方发布包，固定版本、下载 URL 和 SHA256，校验后才解包。运行时、动态库和原有许可证一并保留。构建器在本机预编译安装界面与保存助手，因此用户安装时无需编译。

内置运行环境的来源及许可记录在应用的 `Contents/Resources/RUNTIME-NOTICE.txt`。目前提供基础标准库运行环境，不把全部科学计算依赖强行打包。

## 验证边界

预览需要检查：DMG 完整性、应用签名结构、运行环境移动后的可用性、隔离 `CODEX_HOME` 中的首次安装与更新，以及安装缓存中的结构打开和逐帧读取。原生界面需实际打开核对完成状态。

构建器在签名前使用应用内置 Python 和资源生成一次服务器部署包；缺少任何必需文件时停止构建。`verify_macos.py` 将应用复制到带空格的临时目录，只提供系统 PATH。它从移动后的 App 生成部署包，在临时目录完成后端首次／重复安装、许可证核对和两帧读取；再验证独立宿主读取两帧且不创建 Codex 配置，并使用本机 Codex CLI 执行可选插件首次／重复安装。运行前后检查应用签名。它不修改用户真实 Codex 配置，也不连接远程服务器。

图形安装包不自动改写用户的 SSH 配置。只有用户勾选保存助手时，才安装助手及用户登录项。应用不能直接从只读 DMG 或 App Translocation 位置注册插件，会提示先拖入 Applications。

## 公开 Release 前

当前构建器执行的是 **ad-hoc 本地签名**，尚未通过 Apple 公证。不能将“本机运行成功”等同于“其他用户下载后无提示打开”。

正式分发应使用 Developer ID Application 对应用及嵌套可执行组件按 Apple 要求签名，启用相应 hardened runtime 配置，再对分发包公证并装订票据；随后在另一台干净 Mac 上验证 Gatekeeper、安装与升级。相关凭据不写入仓库。

只有维护者审阅并授权发布后，才将验证完成的 DMG 上传到 GitHub Release。用户下载的是 DMG 资产，不是 GitHub 自动生成的 Source code ZIP。

参考：[Python 运行时说明](https://gregoryszorc.com/docs/python-build-standalone/main/running.html)、[Apple 软件公证说明](https://developer.apple.com/documentation/security/notarizing-macos-software-before-distribution)。
