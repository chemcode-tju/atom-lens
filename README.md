# Structure Viewer for Codex

在 Codex 侧面板查看原子结构与轨迹。MCP Apps 文件入口，无需 skill 或独立 HTTP 服务。0.5.0 起结构文件始终只读；快照另存为图片。

## 0.8.2：大 VASP 轨迹与输入框对比度

- 移除 VASP 原先的 64 MiB 文件限制。原名 XDATCAR 与 `.vasp` 轨迹先返回一帧，再按最多 32 帧或约 256 KiB 读取后续批次（不拆帧）；批次大小不限制文件总大小或帧数。POSCAR/CONTCAR 使用相同入口读取结构帧。
- 本地文件选择器也使用流式逐帧读取 VASP，不再对整个 XDATCAR 调用 `File.text()`。已加载帧可立即查看；源码面板只展示当前帧及头部。
- 界面仍需内存保存已加载的帧，实际容量取决于设备内存；格式校验、文件变化检查保持。
- 显式指定所有文本、路径、数值输入框和下拉框的背景、文字及光标颜色。宿主切换深色控件时仍使用白底深色字，避免默认深灰背景与继承深色文字混用。
- 回归覆盖超过 64 MiB 的文件、首帧提前可用、末帧读取、截断/变更文件、CRLF、UTF-8 分块、Direct/Cartesian 和缩放。浏览器验证 72.2 MB / 800 帧的 XDATCAR 与强制深色宿主环境。

## 原名 VASP 打开与选择标记（0.6.0）

- 新增 **Structure Viewer 聊天侧栏入口**（官方 `thread` entrypoint），独立于宿主按扩展名匹配的文件入口。打开后可输入当前主机上的完整路径，例如 `/work/run/POSCAR`，直接读取原文件；不改名、不生成副本、不使用伪后缀。
- 顶部 **按路径打开** 访问运行此插件的主机。nd3 聊天中的插件读取 nd3 路径，本地聊天读取 Mac 路径；弹窗标明主机名。**本地文件** 是 Mac 浏览器文件选择器，和远程路径读取用途不同。
- 新增 agent 可调用的 `open_structure_path` 工具；agent 可在用户要求查看时用原路径打开查看器，无需技能。手动侧栏入口用空参数打开路径输入界面。当前工具需要刷新宿主插件发现后才可用。
- 标准文件链接 `POSCAR` 在当前 Codex 中仍然进入文本视图；外部应用“打开”菜单也不会列出此插件。插件的独立侧栏入口解决原名读取，不宣称修改了宿主的裸文件名关联。
- 移除了人为 `.poscar` / `.contcar` / `.xdatcar` 文件入口声明。标准 XYZ/extxyz/traj/vasp 扩展名入口保留。
- 0.7.0：选中原子保留原色，边缘显示 ASE 风格深绿色细圆环。圆环始终朝向相机，透视视图按球体切线轮廓修正，参与深度测试，可被前方原子遮挡；不会在球体上显示三维色带。快照排除临时选择标记。
- 路径读取使用随机文件句柄绑定；后续读取和快照仅接受已打开的句柄。普通文件检查、读取版本检查与只读结构行为保持。XYZ/extxyz/traj/VASP 均可分段读取；句柄在服务重启后失效，需要重新打开。

## 选择与显示

- 底部“选择”启用点击拾取，再次点击同一原子取消选择。选中原子显示深绿色外缘圆环；下方按点击顺序显示元素、原始序号（从 1 开始）和当前显示坐标（Å）。旋转模式不会选中原子。
- 两原子显示距离，三原子显示以第二个原子为顶点的夹角，四原子显示按 1–2–3–4 顺序的有符号二面角（−180° 到 180°）。五个及以上按原子序数显示组成，例如 `H+3C+O`，不显示测量。共线或重合导致的未定义角度明确标注。
- 测量使用当前显示坐标的直接欧氏几何；启用 Wrap 时使用折回坐标，不自动计算周期最短距离。
- “框选”拖框选中投影落在矩形内的可见原子中心，包括被其他原子遮挡的后方原子；Shift 拖框反选（框内已选的取消、未选的加入）。框选按原始序号排序，精确指定角度顺序时先清除再逐个点击。
- 顶部“显示设置”：按元素控制显隐；对已选原子单独设置原子球/球棍/线棒、Jmol/RasMol/VESTA 或自定义颜色、显示/隐藏。可恢复选中原子默认或恢复全部设置。元素显隐是总开关；元素被关闭时，其局部显示设置不强制显示。隐藏原子不产生可见键或拾取目标。
- 切帧时优先按唯一原子 ID 对应选择和局部样式；没有 ID 则按序号且要求原子数及元素顺序相同。不兼容帧会清除局部选择与样式，元素显隐仍保留。没有 ID 的数据无法识别同元素原子之间的重排。
- 删除“启用编辑”、坐标修改、源码应用和文件写回；源码面板只读。所有样式、Wrap 和质心校正均不修改原文件。

## 视图、轨迹与快照

- 默认 XZ 正交视图（X 向右、Z 向上）；XY/XZ/YZ/透视，单/双/四视图。再次选择同一视角会复位，默认左键拖动旋转、右键拖动平移；支持缩放、适应视图与展开。
- 默认白底 Jmol，内置 RasMol/CPK 与 VESTA。元素显示半径采用 OVITO 3.15.5 表（H 0.46、O 0.74、Cu 1.28 Å），整体半径可调。固定柔和高光与环境补光。
- XYZ/extxyz 第一帧优先显示，随后每批最多 32 帧或约 256 KiB，加载途中可切帧。ASE `.traj` 按 ULM 索引读取，无需安装 ASE；不读取旧 pickle 格式。
- 氢键是 N/O/F 供受体的几何筛选：D–H ≤ 1.3 Å、H···A ≤ 2.5 Å、D···A ≤ 3.5 Å、D–H···A ≥ 150°，支持斜晶胞周期镜像。不是电子结构判断。
- Wrap 仅折回启用 PBC 的方向。质心漂移校正以参考帧（默认 0，编号从 0 开始）为基准，按质量计算位移并平移全部原子，晶胞不动；可仅用所选原子计算。读取 extxyz/ASE 自定义质量，否则使用标准原子质量。输入必须是连续、未折回坐标；启用时取消 Wrap。帧间原子无法对应则停用并提示。
- 播放设置含 fps、倍速、每 N 帧与循环。默认 60 fps × 1，渲染跟不上时跳帧。
- 快照保留当前视图的元素显隐、局部样式、氢键、编号及光影；不包含临时选择高亮与测量连线、工具栏或坐标轴。PNG 支持透明背景，JPEG/PDF 白底，可裁去四周空白，DPI 96/150/300/600。PDF 内嵌栅格图。
- 0.7.0 快照目的地：本地 Mac 插件弹出 macOS 原生文件夹选择窗口（可取消），随后保存图片；nd3 等服务器默认保存到结构文件本身所在目录，可输入另一个已存在的绝对目录。同名自动追加序号，不覆盖文件，不再创建 `structure-snapshots/` 子目录。
- nd3 快照选“本地 Mac”时，0.8.1 使用 **Structure Snapshot Saver** 后台助手：维护一条现有 SSH 连接，接收本次导出的图片，在 Mac 弹出 `NSSavePanel` 选择文件夹和文件名。取消不保存；覆盖由系统确认。无网络监听端口，不监控 Downloads，不依赖浏览器打开自定义 URL。
- 助手在登录时启动，菜单栏“结构快照 · nd3”表示已连接；可从菜单退出，或重新打开 App 恢复。每次保存都需要用户确认。插件等待助手回报已保存/已取消；离线明确报错。当前仅配置 nd3，单张最多 18 MiB。
- 图片暂存在 nd3 的 `~/.cache/structure-viewer/exports` 私有目录；请求超过 10 分钟未处理会过期，超过 24 小时的快照在下次导出时清理。Mac 保存路径不回传到服务器。SSH 中断后自动重连，不重试已经交给系统窗口的保存请求。
- 0.8.0 选择仅更新合批轮廓和测量连线，保留原子模型与相机；信息栏固定高度，尺寸变化不再触发自动适应。

## 安装

需要支持 MCP Apps 文件入口的新版 Codex 桌面端，以及 `python3`（3.9 或以上）。插件服务只使用 Python 标准库；运行插件不需要 ASE、Node.js 或 npm。

```sh
git clone https://github.com/liyang-tju/extxyz-extension.git
cd extxyz-extension
codex plugin marketplace add .
codex plugin add structure-viewer@atomic-structure-tools
```

如需 nd3 快照保存到本地 Mac，在 **Mac** 上额外执行（需要 Apple Command Line Tools）：

```sh
python3 native/install_helper.py
```

助手安装到 `~/Applications/Structure Snapshot Saver.app`，同时安装 `~/Library/LaunchAgents/org.structure-viewer.snapshot-saver.plist`。使用现有 `ssh nd3` 连接；目前仅配置 nd3 别名。卸载时先从菜单退出，再移除该登录项与 App；服务器保存功能独立可用。

安装后打开本地 `.extxyz` 文件。如果仍然使用内置文本编辑器，在文件的打开方式菜单中选择 **Structure Viewer**；宿主可以记住按扩展名选择的查看器。若新插件未被发现，重新打开聊天或重启桌面端后再试。

从 0.1.0 升级时，重新执行安装命令，并完整退出、重开桌面端。0.1.0 的 MCP 启动参数使用了未正确解析的插件根目录占位符，导致握手失败、查看器菜单缺失；0.1.1 改为以插件目录为工作目录运行 `server.py`。仅关闭文件标签可能仍沿用旧的插件发现缓存。

本地开发修改源码不会自动同步到插件安装缓存，更新后需重新安装对应版本。

### 远程聊天与渐进加载（0.2.0）

在 nd3 等服务器的 Codex 远程聊天中使用时，需要在**对应服务器上**执行同样的插件安装命令，再重新连接远程聊天；必要时完整退出、重开桌面端。本地安装不会自动为远程主机注册文件查看器。结构文件保留在服务器，插件通过 Codex 连接分批传输文本，三维渲染在本地侧面板执行，无需手动下载或开放额外端口。

XYZ/extxyz 首次只读取一个完整帧，后续每批最多 32 帧或约 256 KiB（不拆开单帧）。无需预先扫描全文件，帧数显示为已加载数量，完成后显示总数。播放到尚未加载的位置会等待。每批检查文件版本；文件在加载期间变化时停止，避免拼接不同版本。当前不是持续跟随正在写入的模拟轨迹。

查看模式始终只读，保留渐进加载。分段读取依赖宿主提供选中文件路径；旧宿主回退到完整读取。VASP 优先按完整帧分批读取，POSCAR/CONTCAR 读取一个结构帧；XDATCAR 无文件总大小或总帧数限制。

## 格式与宿主限制

| 原始文件 | 读取范围 |
| --- | --- |
| `POSCAR` / `CONTCAR` | VASP 5/6，Direct/Cartesian，保持原名 |
| `XDATCAR` | 固定晶胞多帧，保持原名，首帧优先渐进读取 |
| `.xyz` / `.extxyz` | 多帧、属性列、晶胞与 PBC |
| `.traj` | 现代 ASE ULM 多帧、可变原子数 |
| `.vasp` | VASP 结构 |

2026-10-28 核查本机当前 Codex：文件查看器仅检查文件名是否以 `"." + extension` 结尾；指定查看器和恢复文件标签时也再次执行匹配，没有完整文件名或通配符入口。当前协议文件入口只有 `type` 与 `extensions`。未修改应用包。要保留 VASP 原名，应使用新注册的聊天侧栏工具入口或 agent 的 `open_structure_path`，而非外部应用菜单。

VASP 4 缺少元素名时明确报错。XDATCAR 暂限固定晶胞，已移除原 64 MiB 单文件上限。球棍连接按距离推断，暂不包含跨周期边界的普通化学键。

## 开发验证

```sh
node tests/test_parser.cjs
node tests/test_viewport.cjs
node tests/test_selection.cjs
node tests/test_geometry.cjs
node tests/test_snapshot.cjs
node tests/test_ase_traj.cjs
python3 tests/test_path_access.py
python3 tests/test_binary_snapshot.py
python3 tests/test_server.py
python3 tests/test_trajectory.py
```

`tests/preview_host.py` 仅用于本机协议模拟与交互验证，不是产品启动方式。测试数据与截图由 .gitignore 排除。模拟页验证通过不等于原生 Codex 缓存已刷新；安装新版后需重新打开面板或在方便时重新连接。

## 接口与许可

- [MCP 文件入口协议](https://github.com/openai/mcp-extensions/blob/main/docs/spec.md#file-extension-entrypoint)
- [OpenAI 插件打包](https://developers.openai.com/plugins/build/plugins)
- [OVITO VESTA 主题](https://www.ovito.org/download/data/documentation/VESTA.ovito-theme)

项目源码 MIT；内置 3Dmol.js 使用独立许可证，见 `plugin/web/vendor/LICENSE-3Dmol.txt`。所有渲染资产随包发布，不访问外部 CDN。

选择轮廓参考本机 ASE `ase/gui/ui.py:Window.circle`（深绿色、3 px 边线）与 `ase/gui/view.py` 的投影绘制思路；圆环几何为本项目独立实现。

0.8.1 验证：通过 nd3 队列实际触发 Mac 原生保存窗口，分别核验取消回执和保存回执；保存到自选本地目录的 PNG 与服务器源数据 SHA-256 相同。Codex 中已打开的旧查看器仍可能保留旧服务，升级后需重新打开，必要时重连 nd3 聊天。

质心校正语义参考 [OVITO Center of mass correction](https://www.ovito.org/manual/reference/pipelines/modifiers/center_of_mass_correction.html)。
