# Structure Viewer for Codex

在 Codex 桌面端点击 `.extxyz` / `.xyz` 文件，在聊天侧面板查看、切换帧、编辑并保存原子结构。采用官方 MCP Apps **File Extension Entrypoint**，不包含技能，不需要通过聊天命令启动，也不需要本地 HTTP 服务。

## 初版功能

- 原子球、球棍、线棒；拖动旋转、滚轮缩放，晶胞和原子编号开关。
- 底部帧滑块、帧号跳转、前后帧、2/5/10 帧每秒播放；支持各帧原子数不同。
- 点击原子查看坐标；XYZ/extxyz 可编辑单原子的笛卡尔坐标。
- 当前帧源码编辑；保留 extxyz 的 `Properties`、晶胞、PBC、能量、力及其他属性。
- 点击“保存”或 Cmd/Ctrl+S，通过宿主文件接口写回；使用 ETag 检查外部修改冲突。
- 渲染库随插件打包，结构查看和编辑不使用外部服务。

## 安装

需要支持 MCP Apps 文件入口的新版 Codex 桌面端，以及 `python3`（3.9 或以上）。插件服务只使用 Python 标准库；运行插件不需要 ASE、Node.js 或 npm。

```sh
git clone https://github.com/liyang-tju/extxyz-extension.git
cd extxyz-extension
codex plugin marketplace add .
codex plugin add structure-viewer@atomic-structure-tools
```

安装后打开本地 `.extxyz` 文件。如果仍然使用内置文本编辑器，在文件的打开方式菜单中选择 **Structure Viewer**；宿主可以记住按扩展名选择的查看器。若新插件未被发现，重新打开聊天或重启桌面端后再试。

从 0.1.0 升级时，重新执行安装命令，并完整退出、重开桌面端。0.1.0 的 MCP 启动参数使用了未正确解析的插件根目录占位符，导致握手失败、查看器菜单缺失；0.1.1 改为以插件目录为工作目录运行 `server.py`。仅关闭文件标签可能仍沿用旧的插件发现缓存。

本地开发修改源码不会自动同步到插件安装缓存，更新后需重新安装对应版本。

## 支持范围

| 格式 | 查看 | 编辑 |
| --- | --- | --- |
| `.xyz` / `.extxyz` | 多帧、属性列顺序变化、晶胞和 PBC | 原子坐标、当前帧源码 |
| `.poscar` / `.contcar` / `.vasp` | VASP 5/6，Direct/Cartesian、缩放因子 | 文件源码 |
| `.xdatcar` | 固定晶胞多帧 | 文件源码 |

**当前宿主的入口按扩展名匹配。**裸文件名 `POSCAR`、`CONTCAR`、`XDATCAR` 虽然解析器可以读取，但尚不能靠这个入口自动关联；测试时使用 `structure.poscar`、`trajectory.xdatcar` 等带扩展名的副本。VASP 4 缺少元素名时明确报错，不猜测元素。

编辑不会重新运行计算。改变坐标后，原有能量、力、应力等标签仍被保留，但可能已不适用于新结构；将编辑结构用于训练前须重新计算标签。界面会显示此提示。

测量目前显示两原子的**直接距离**，未实现周期最短距离。球棍连线按距离推断，不包含跨周期边界的键。XDATCAR 首版仅覆盖固定晶胞；大文件仍受宿主读写大小上限和内存限制。保存前请确认未保存标记已消失，避免关闭面板丢失草稿。

## 验证

```sh
node tests/test_parser.cjs
python3 tests/test_server.py
```

对真实数据做逐帧 ASE 对照（可选，测试数据不随仓库分发）：

```sh
conda install -n work -c conda-forge ase numpy
conda run -n work python tests/validate_real_data.py
```

将测试文件放在 `test-data/train.extxyz`。已在本地 800 帧、每帧 66–226 原子的文件上比对全部元素、坐标、晶胞和 PBC；未编辑文件可原文往返。解析器单元测试覆盖重排属性列、不同原子数、CRLF、单帧修改、错误输入和 VASP 格式。

`tests/preview_host.py` 是**仅供开发验证的协议模拟宿主**，不是插件的打开方式。运行后访问 `http://127.0.0.1:8767`，保存只写到 `test-results/roundtrip.extxyz`，不会覆盖原始测试文件。已验证加载 800 帧、跳到末帧、编辑及保存仅改变目标坐标行。原生文件入口和原生保存需要单独验证，模拟宿主通过不代表桌面端已成功加载插件。

0.1.1 已通过桌面端自带 app-server 的 `mcpServerStatus/list` 实测：服务成功初始化，返回 `open_structure` 及文件入口元数据，`toolsError` 为空。当前桌面窗口在关闭、重开文件后仍未出现菜单；完整重启后的菜单、原生渲染和保存仍待确认。

## 目录

- `plugin/server.py`：MCP STDIO 入口、工具声明与内嵌 UI 资源。
- `plugin/web/parser.js`：原文保留与按帧坐标解析。
- `plugin/web/app.js`：交互、渲染、宿主读写协议。
- `.agents/plugins/marketplace.json`：可安装的本地插件市场。
- `examples/water.xyz`：可公开的两帧小样例。

测试数据、测试输出、截图均已被 `.gitignore` 排除。

## 接口依据

- [OpenAI Plugin Extensions：File viewers and editors](https://developers.openai.com/plugins/build/extensions)
- [OpenAI 插件打包](https://developers.openai.com/plugins/build/plugins)
- [MCP 文件入口、读取和写入协议](https://github.com/openai/mcp-extensions/blob/main/docs/spec.md#file-extension-entrypoint)

## 许可证

项目源码为 MIT。内置 3Dmol.js 使用其独立许可证，见 `plugin/web/vendor/LICENSE-3Dmol.txt`。3Dmol.js 下载来源为 https://3dmol.org/build/3Dmol-min.js；固定的完整文件随 Git 提交保存，使用时不从 CDN 加载。
