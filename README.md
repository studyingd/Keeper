# Keeper

一个仅在本机运行的 **PySide6 / Qt** 桌面密码管理器:保存应用账号与服务器凭据,一键发起 SSH / RDP 连接并自动填充密码。

保险库是一个 **SQLCipher 整库加密**的本地文件,主密码派生密钥(PBKDF2-HMAC-SHA512,512,000 次迭代)。不联网、不同步、无云端恢复。

## 核心特性

| 能力 | 说明 |
| --- | --- |
| **资产管理** | **服务器**(以 IP 为核心,下挂 SSH/RDP 登录及 MySQL、网站后台等任意凭据)与**应用**(阿里云、GPT 这类在线账号),支持标签、搜索、类型筛选 |
| **凭据项目** | 每个资产下任意多个自定义命名的项目(用户名 / 密码 / 说明),↑ ↓ 手动排序并存进保险库 |
| **一键连接** | 系统登录项目显示 **SSH 连接 / RDP 连接** 按钮,Windows 与 macOS 的 SSH 均自动填充密码,密码不进命令行、不落盘 |
| **密码生成器** | 首页与项目对话框共用:自选字符集、1–128 位长度、按熵值实时显示四档强度 |
| **剪贴板保护** | 复制后 30 秒自动清除;macOS 额外打隐私标记,剪贴板管理器与 Handoff 主动跳过 |
| **自动锁定** | 隐藏 10 分钟或系统空闲 10 分钟自动锁定;解锁失败递增延迟且重启不清零 |
| **导出** | 一键导出全部项目为 `.xlsx`(含标签列,表头带筛选器) |
| **托盘后台** | 关闭窗口收进系统托盘,同一保险库单实例,重复启动自动唤起已有窗口 |

<!-- 截图占位:主界面(左栏资产列表 + 右栏项目卡片)与密码生成器首页 -->

## 平台支持

- **Windows 10 1809+** — 完整支持:SSH / RDP 密码自动填充、托盘后台、发行包。
- **macOS 12+** — 支持全部保险库功能。SSH 在 Terminal 中发起并自动填充密码(首次需允许 Keeper 控制 Terminal);RDP 调用 Microsoft **Windows App**,密码需手动粘贴一次,免密方案见[常见问题](#macos-上-rdp-每次都要输密码能不能免密)。

## 快速开始

需要 **Python 3.11–3.14**(仓库 `.python-version` 固定为 3.14)。`pip install` 会装上 PySide6 / Qt,首次安装体积较大。

```powershell
# Windows (PowerShell)
python -m pip install -e ".[dev]"
python main.py
```

```bash
# macOS / Linux
python3 -m pip install -e ".[dev]"
python3 main.py
```

安装后也可以直接用入口脚本 `password-manager`,或从源码运行 `dist` 里构建好的 exe / app(见[打包发行](#打包发行))。

<details>
<summary><b>两个细节</b></summary>

- **界面选择**:默认启动 QML 界面。旧版 Qt Widgets 界面保留作后备,用 `KEEPER_UI=widgets python main.py` 启动。
- **装不上 `sqlcipher3-wheels`?** 它是预编译二进制轮子,只提供特定 Python 版本的 wheel,请改用 3.11–3.14 之间的版本。

</details>

<details>
<summary><b>指定保险库位置</b></summary>

默认路径 `~/.keeper/vault.sqlcipher`。用环境变量 `PASSWORD_MANAGER_VAULT` 指定其他位置,便于测试或分隔不同保险库(不同路径的保险库可以同时打开):

```powershell
$env:PASSWORD_MANAGER_VAULT = "E:\Safe\work-vault.sqlcipher"
python main.py
```

```bash
PASSWORD_MANAGER_VAULT=~/vaults/work.sqlcipher python3 main.py
```

</details>

## 使用方式

### 1. 设置主密码

初次打开时创建唯一主密码。**主密码无法恢复**,请妥善保存。

### 2. 创建资产

点侧边栏 **+ 新增资产**,在类型卡片里选择 **服务器** 或 **应用**(编辑时可更换):

- **服务器** = 一台机器:只需填 **服务器 IP**(显示名可选),它的 SSH/RDP 登录及部署其上的应用密码都建在这台服务器下。
- **应用** = 在线账号:填名称和可选网址。
- **标签** 回车添加,或点快捷标签(MySQL、生产环境、云平台…),侧边栏与搜索都会命中。

非默认端口直接写在 IP 后面:

| 写法 | 含义 |
| --- | --- |
| `192.168.1.101` | 默认端口 |
| `192.168.1.101:2222` | SSH 转成 `-p 2222`,RDP 写进 `full address:s:` |
| `[fd00::1]:3389` | IPv6 用方括号 |

### 3. 添加项目

打开资产,点 **+ 新增项目**,填项目名称、用户名、密码和可选说明。

- 密码栏右侧 **生成** 按钮一键填入随机密码;录入已有密码时忽略它即可。
- 卡片上的 **↑ ↓** 调整顺序,顺序保存在保险库内,导出时按此顺序。
- **复制用户名 / 复制密码** 30 秒后自动从剪贴板清除。

### 4. 系统登录(SSH / RDP 一键连接)

服务器详情页点 **+ 系统登录**:选择 **Linux(SSH)** 或 **Windows(RDP)**,填账号与密码(账号自动预填 `root` / `administrator`),保存后卡片出现连接按钮,一点即连。

### 5. 生成随机密码

首页是完整的密码生成器,项目对话框内嵌同一个(行为完全一致):勾选字符集(数字 / 英文 / 符号)、拖长度滑杆(默认 12 位),实时显示强度。点击侧边栏左上角的 Keeper 品牌区可随时返回首页总览。

### 6. 托盘、锁定与退出

- **关闭窗口** = 收进系统托盘,不是退出。双击托盘图标或右键「打开 Keeper」唤回。
- 保险库**隐藏 10 分钟**或**系统空闲 10 分钟**后自动锁定;侧边栏 **锁定** 按钮随时手动锁定。锁定页会明确说明数据仍在加密文件里,输入主密码即可全部恢复。
- 结束进程请右键托盘图标选 **完全退出**(终端启动时 `Ctrl+C` 亦可);托盘不可用时关闭窗口即安全锁定并退出。
- 同一保险库只允许一个进程:重复启动只会把已有窗口调到前台,崩溃残留的占位会被自动回收。

## 安全要点

使用者需要知道的结论;实现细节(socket 权限、DPAPI 格式、JXA 脚本等)见 **[docs/security.md](docs/security.md)**。

- **加密**:SQLCipher 整库加密,范围含结构、资产、用户名、网址和密码;主密码不落库。**修改主密码**走整库 rekey 且必须先验证旧密码,防止无人看管的窗口被他人改锁。
- **解锁节流**:连续失败 0.5s 起步逐次翻倍、封顶 8s,重启程序不清零。
- **剪贴板**:30 秒自动清除,且只清除仍是本程序复制内容的剪贴板(不会误伤你后来复制的东西)。
- **SSH / RDP 密码注入**:密码绝不进命令行参数、不落盘。Windows SSH 走随包 askpass 助手 + 环境变量;Windows RDP 走 DPAPI 加密的临时 `.rdp`(60 秒后删除);macOS 走私有 unix socket + 随机令牌。
- **供应链**:仓库唯一的预编译二进制 `keeper-askpass.exe` 经手 SSH 密码,其 SHA-256 记录在 `scripts/keeper-askpass.sha256`,Windows 构建脚本每次打包前校验。
- **边界**:这是单机单人保险库,没有用户权限、审计、多设备同步或云端恢复。不要把未受保护的保险库文件、主密码或导出的凭据上传到聊天、仓库或工单系统。

## 备份与导出

- **备份**:先锁定或退出程序,再复制整个 `vault.sqlcipher` 文件到安全位置。备份副本仍应按敏感数据处理。
- **导出 Excel**:侧边栏 **导出 Excel** 导出全部项目(含用户名、密码、标签),导出前会弹确认。

> ⚠️ **导出的文件不加密、包含全部明文密码。** 请只保存到受信任的位置,使用完毕后及时删除。单元格均被强制为纯文本,`=` 开头的内容不会在 Excel 中被当作公式执行。

> **旧版 `vault.db`**:新版只读写 `vault.sqlcipher`,不会读取或转换旧版未整库加密的 `vault.db`。旧文件请自行保留备份,新版本需新建保险库并重新录入。

## 打包发行

### Windows EXE

```powershell
python -m pip install -e ".[dev]"
powershell -ExecutionPolicy Bypass -File .\scripts\build-windows.ps1
```

产物是 `dist\Keeper\` 的 one-folder 发行包(**分发整个文件夹**,不是单个 EXE)。构建脚本会先校验 askpass 助手的 SHA-256,再打包并自动裁剪用不到的 Qt 模块(约 474 MB → 173 MB)。保险库文件不会被打进包。

### macOS App / DMG

```bash
python3 -m pip install -e ".[dev]"
bash scripts/build-macos.sh        # 产物 dist/Keeper.app
bash scripts/package-macos.sh      # 产物 dist/Keeper.dmg(分发用)
```

- 分发时复制整个 `.app` / `.dmg`;RDP 连接需要用户自装 Microsoft **Windows App**。
- 本机安装建议 `ditto dist/Keeper.app /Applications/Keeper.app && rm -rf dist build`,避免 Spotlight 索引出两个同名 Keeper。
- bundle id(`com.seeed.keeper`)承载 macOS 的 TCC 授权记忆,**修改后系统会重新弹授权**。

## 常见问题

### macOS 上 RDP 每次都要输密码,能不能免密?

Keeper 发起的是临时连接,不复用 Windows App 里保存的凭据。免密路径:在 Windows App 里**保存一次凭据**(右键连接 → 编辑 → 凭据),之后从其连接列表或 Spotlight(`Cmd + 空格` 输连接名)启动即可;也可用 `scripts/export_rdp_for_windows_app.py` 把保险库里的 RDP 凭据批量导出 `.rdp` 再从 Windows App 导入。

### macOS 弹出「Keeper 想要控制 Terminal」?

SSH 经 AppleScript 让 Terminal 执行,需要 AppleEvents 授权,允许一次即可(TCC 按 bundle id 记住)。

### SSH 没有自动填充密码?

- **macOS**:依赖 `/usr/bin/nc` 与 `osascript`;`nc` 缺失时仍会连接,只是要手动输密码。
- **Windows**:确认已启用 OpenSSH 客户端(设置 → 应用 → 可选功能)。Keeper 优先用系统自带 `ssh.exe`(Git/MSYS 版不尊重自动填充机制)。密码同时在剪贴板中,可手动粘贴。

### Windows 上 RDP 提示找不到客户端?

需要 `mstsc.exe`(默认在 `C:\Windows\System32`)。没保存用户名密码时,Keeper 只打开普通连接对话框。

### 窗口关了但进程还在?

设计如此:关闭窗口 = 收进托盘,双击托盘图标唤回,右键「完全退出」结束进程。

### 忘了主密码怎么办?

无法恢复。唯一出路是删除 `vault.sqlcipher` 后新建保险库重新录入。

### 第二次启动没有反应?

同一保险库单实例:第二个进程把已有窗口调到前台后自行退出。用 `PASSWORD_MANAGER_VAULT` 指定不同路径可并存。

## 项目结构

```
├── main.py                            # 启动器 → password_manager.entry
├── Keeper.spec                        # macOS 打包配置(bundle id、版本、图标)
├── pyproject.toml                     # 依赖、入口脚本、pytest/ruff 配置
├── docs/security.md                   # 安全实现细节(注入、DPAPI、JXA、节流…)
├── scripts/
│   ├── build-windows.ps1              # Windows 打包(含 askpass 校验 + 裁剪)
│   ├── build-macos.sh / package-macos.sh  # macOS App / DMG
│   ├── trim_dist.py                   # 冻结包裁剪(去掉未用 Qt 模块)
│   ├── keeper_askpass.cs + .sha256    # Windows SSH askpass 助手源码与摘要
│   ├── export_rdp_for_windows_app.py  # 批量导出 RDP 凭据
│   └── make_icon.py                   # 生成应用图标
├── src/password_manager/
│   ├── entry.py                       # 统一入口(默认 QML,KEEPER_UI=widgets 切换)
│   ├── app_qml.py                     # QML 应用:引擎、controller 接线、单实例
│   ├── app.py                         # 旧版 Widgets 界面(后备)
│   ├── controller.py                  # QML ↔ 后端桥:状态、CRUD、锁定、导出
│   ├── generator.py                   # 密码生成与熵值强度(纯函数)
│   ├── models.py                      # Entry / Credential 数据类,host:port 解析
│   ├── vault/repository.py            # SQLCipher 连接、schema、CRUD、rekey、迁移
│   ├── services/actions.py            # SSH / RDP / 浏览器 / 剪贴板 / 系统空闲
│   ├── qml/                           # QML 界面(Main、Sidebar、DetailView、对话框…)
│   ├── ui/                            # 设计令牌、图标、共享组件
│   └── assets/                        # 图标与 keeper-askpass.exe
└── tests/                             # 158 个测试:repository / actions / app / controller
```

## 开发与测试

```powershell
python -m pytest              # 全部测试(offscreen 平台,无需显示器)
python -m ruff check src tests scripts
python scripts/selfcheck_layout.py   # QML 布局离屏自检
```

## 许可证

[MIT](LICENSE) © aronurx
