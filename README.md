# Keeper

一个仅在本机运行的 **PySide6 / Qt** 桌面密码管理器,用于保存应用账号以及服务器中任意自定义命名的凭据项目。服务器以 IP 为核心容器,内部可保存网站后台、登录账户、SQL 数据库或任何其他类型的账户密码。

保险库是一个 **SQLCipher 整库加密**的本地文件,主密码派生密钥(PBKDF2-HMAC-SHA512,512,000 次迭代),不联网、不同步、无云端恢复。

## 目录

- [功能特性](#功能特性)
- [平台支持](#平台支持)
- [安装与运行](#安装与运行)
- [使用方式](#使用方式)
- [安全模型](#安全模型)
- [后台运行与自动锁定](#后台运行与自动锁定)
- [备份与限制](#备份与限制)
- [导出 Excel](#导出-excel)
- [打包发行](#打包发行)
- [常见问题](#常见问题)
- [项目结构](#项目结构)
- [开发验证](#开发验证)

## 功能特性

| 能力 | 说明 |
| --- | --- |
| **资产** | 两类:**服务器**(以 IP 为核心,下挂该机器的各类账号)与**应用**(阿里云、GPT 这类在线账号);类型在新增对话框内选择卡片,编辑时也可更换 |
| **标签** | 资产可挂多个标签(如 MySQL、生产环境),侧边栏按类型分组展示,搜索同时匹配名称、IP 与标签 |
| **项目** | 每个资产下任意多个自定义命名的凭据(用户名 / 密码 / 说明),可用 ↑ ↓ 调整顺序,顺序存进保险库 |
| **一键连接** | 系统登录项目会显示 **SSH 连接 / RDP 连接** 按钮,Windows 与 macOS 的 SSH 均自动填充密码 |
| **密码生成器** | 首页与项目对话框共用同一生成器:**自由勾选**数字/英文/符号字符集,长度 1–128 位滑杆(默认 12),按字符池熵值实时显示四档强度 |
| **搜索** | 侧边栏按名称、IP 或标签实时模糊搜索,类型筛选 chips 一键收窄 |
| **网站跳转** | 说明或网址中含 `http(s)://` 时,卡片自动出现 **↗ 访问网站**(优先 Chrome,否则系统默认浏览器) |
| **导出** | 一键导出全部项目为 `.xlsx`(含标签列),表头带筛选器 |
| **安全** | 整库加密、剪贴板 30 秒自动清除、空闲/隐藏 10 分钟自动锁定、解锁失败递增延迟、修改主密码需验证旧密码 |
| **后台** | 关闭窗口收进系统托盘(Windows 通知区域 / macOS 菜单栏),同一保险库单实例 |

<!-- 截图占位:主界面(左栏资产列表 + 右栏项目卡片)与密码生成器首页 -->

## 平台支持

**Windows 10 1809+** — 完整支持:SSH / RDP 密码自动填充、托盘后台、Windows 发行包。

**macOS 12+** — 支持创建、解锁、浏览、编辑、导出和备份加密保险库。连接行为:

- **SSH**:在 Terminal 中发起连接并自动填充密码。首次使用需允许 Keeper 控制 Terminal。
- **RDP**:调用 Microsoft **Windows App**(原 Microsoft Remote Desktop),通过一个只含地址和用户名的临时 `.rdp` 文件发起(60 秒后自动删除)。**密码不会写入该文件或命令行**,若客户端要求输入密码,请粘贴已复制到剪贴板的密码。想彻底免密见[常见问题](#macos-上-rdp-每次都要输密码能不能免密)。

## 安装与运行

需要 **Python 3.11 及以上**(仓库 `.python-version` 固定为 3.14;`pyproject.toml` 声明 `requires-python = ">=3.11"`)。`pip install` 会自动装上 PySide6 / Qt,首次安装体积较大。

Windows(PowerShell):

```powershell
python -m pip install -e ".[dev]"
python main.py
```

macOS / Linux:

```bash
python3 -m pip install -e ".[dev]"
python3 main.py
```

也可以安装后直接用入口脚本运行:

```powershell
password-manager
```

> **装不上 `sqlcipher3-wheels`?** 该依赖被钉在 `sqlcipher3-wheels==0.5.7`,它是预编译二进制轮子,只提供特定 Python 版本的 wheel。如果你的解释器版本没有对应轮子,安装会失败——请改用 3.11–3.14 之间的版本,或直接用仓库 `.python-version` 指定的 3.14。

### 指定保险库位置

用环境变量 `PASSWORD_MANAGER_VAULT` 指定保险库文件,便于测试或分隔不同保险库:

```powershell
$env:PASSWORD_MANAGER_VAULT = "E:\Safe\work-vault.sqlcipher"
python main.py
```

```bash
PASSWORD_MANAGER_VAULT=~/vaults/work.sqlcipher python3 main.py
```

## 使用方式

### 1. 设置主密码

初次打开时创建唯一主密码。**主密码无法恢复**,请妥善保存。

### 2. 创建资产

点侧边栏的 **+ 新增资产**,在对话框顶部的类型卡片里选择 **服务器** 或 **应用**(图标+名称横排,点选即切换,编辑时也可更换类型):

- **服务器** = 一台机器。它的 SSH/RDP 登录密码,以及部署在它上面的应用密码(MySQL、网站后台等),都作为项目建在这台服务器下面。只需填写 **服务器 IP**,显示名可选。
- **应用** = 在线账号(阿里云、百度云、GPT 这类),可填名称和可选网址。
- **标签**(可选)回车添加,或点下方快捷标签(服务器类:MySQL、Redis、Nginx、Docker…;应用类:云平台、工作、个人…);标签会显示在侧边栏与详情页,搜索时同样命中。

非默认端口直接写在 IP 后面即可:

| 写法 | 含义 |
| --- | --- |
| `192.168.1.101` | 默认端口 |
| `192.168.1.101:2222` | SSH 转成 `-p 2222`,RDP 写进 `full address:s:` |
| `[fd00::1]:3389` | IPv6 用方括号 |

### 3. 添加项目

打开资产,点 **+ 新增项目**,填写项目名称、用户名、密码和可选说明。例如服务器下可建「MySQL」「网站后台」等项目。

- 密码栏右侧的 **生成** 按钮一键填入 12 位随机混合字符密码;录入已有密码时忽略它即可。
- 卡片上的 **↑ ↓** 调整项目顺序,顺序保存在保险库内,导出 Excel 时同样按该顺序。
- **复制用户名 / 复制密码** 按钮取用凭据,30 秒后自动从剪贴板清除。

### 4. 创建系统登录(SSH / RDP 一键连接)

服务器详情页有 **+ 系统登录** 按钮,专建这台机器的登录账号:

1. 选择平台 **Linux(SSH)** 或 **Windows(RDP)**。
2. 填写登录账号与密码。账号会按平台自动填充 `root`(Linux)/ `administrator`(Windows)。
3. 项目默认命名为「系统登录账号」并**自动置顶**显示(仍可用 ↑ ↓ 调整)。

保存后卡片出现 **SSH 连接** 或 **RDP 连接** 按钮。SSH 在 Windows 和 macOS 上都会自动填充密码;macOS 的 RDP 请在客户端提示时粘贴已复制的密码。

### 5. 生成随机密码

首页是完整的随机密码生成器,项目对话框内也内嵌了同一个生成器(行为完全一致):**自由勾选**字符集(数字 0-9 / 英文 aA / 符号 !@#,至少保留一类),拖动长度滑杆选择 1–128 位(默认 12),生成的密码按字符池熵值(`长度 × log₂ 池大小`)实时显示四档强度(弱/中/强/极强),结果可复制(同样 30 秒后清理)。打开资产详情后,随时可以从侧边栏回到首页总览。

### 6. 访问网站

若项目的说明或网站地址中含 `http://` / `https://` 地址,卡片自动出现 **↗ 访问网站** 按钮;资产自身保存了网址时,详情页顶部有 **打开网站**。网站优先用 **Chrome** 打开,未安装 Chrome 时回退到系统默认浏览器。

## 安全模型

下面是使用者需要知道的结论;具体实现(socket 权限、DPAPI 格式、JXA 脚本、白名单环境变量等)见 **[docs/security.md](docs/security.md)**。

### 加密与主密码

- 保险库是 **SQLCipher** 整库加密的本地数据库,默认路径 `~/.keeper/vault.sqlcipher`。加密范围包括数据库结构、资产、用户名、网址和密码。
- 主密码由 SQLCipher 用每个保险库独有的随机 salt 和 **PBKDF2-HMAC-SHA512(512,000 次迭代)**派生数据库密钥。数据库**不保存主密码**,也不保存明文凭据。
- 侧边栏的 **修改主密码** 会用 `PRAGMA rekey` 把整库按新密码重新加密(内容、结构、排序都不变),并**要求先输入当前主密码**——这样即使窗口处于已解锁的无人看管状态,别人也无法把保险库改成只有他知道的密码。
- 应用在锁定或完全退出时关闭数据库连接,释放内存中的保险库密钥。

### 解锁失败节流

- 连续解锁失败触发递增延迟:0.5 秒起步、逐次翻倍、最高 8 秒,期间解锁按钮与输入框被禁用;成功解锁后重置。
- 失败次数与截止时间以 `0600` 权限记在保险库旁边的 `unlock-throttle.json` 里,**重启程序也不会清零**。
- 这只是尽力而为:能删掉该文件的人本来也能直接离线爆破保险库文件,真正的防线是 SQLCipher 的 512,000 次迭代。

### 自动锁定

- 关闭主窗口后会继续在系统通知区域运行(Windows 任务栏右下角 / macOS 菜单栏),**连续 10 分钟未重新打开则自动锁定**。
- 窗口一直开着时同样会锁:Keeper 每 5 秒读一次**系统级**空闲时间(macOS `CGEventSourceSecondsSinceLastEventType`、Windows `GetLastInputInfo`),超过 10 分钟没有任何键鼠输入就自动锁定。用系统级而非「本应用有没有收到事件」来判断,是为了让你在 Keeper 拉起的 SSH 终端里干活时不会被中途锁掉。
- 锁定后主区域显示 **保险库已锁定** 页面,而不是看起来像空保险库的首页:它会说明数据仍完整保存在本地加密文件里,点 **解锁保险库** 输入主密码即可把资产与项目全部加载回来。侧边栏的 **锁定** 按钮同样只锁定并停在该页面,不会把窗口藏起来(取消解锁才等于收进托盘)。

### 剪贴板保护

- 密码默认不显示。复制密码/用户名后,剪贴板在 **30 秒后自动清除**(如果期间没有复制新内容)。
- macOS 上还会给剪贴板项打上 `org.nspasteboard.ConcealedType` 和 `TransientType` 标记,剪贴板管理器与 Handoff/通用剪贴板会主动跳过它。
  - 标记由一小段 JXA 脚本直接写入 `NSPasteboard`,因为 Qt 6 会把自定义 flavor 改名成没人认得的 `com.trolltech.anymime.*`。
  - 密码通过环境变量传给 `osascript`,**不出现在命令行参数中**。
  - `osascript` 不可用时自动退回 Qt 剪贴板(仍有 30 秒自动清除,只是没有隐私标记)。

### SSH / RDP 密码注入

保存的密码**绝不出现在命令行参数中**,也不落盘:

- **Windows SSH**:通过 `SSH_ASKPASS` 机制把密码经子进程环境变量交给 ssh,由随包的 `keeper-askpass.exe` 输出(助手缺失时退回临时脚本,60 秒后删除)。首次连接自动信任服务器主机密钥,密钥后续发生变化则拒绝连接。
- **Windows RDP**:发起连接时生成临时 `.rdp` 文件,密码以 DPAPI 加密块写入(仅当前 Windows 用户可解密),60 秒后自动删除。若自动填充未生效,密码会同时在剪贴板中供手动粘贴。
- **macOS SSH**:Terminal 由 AppleScript 启动、继承不到 Keeper 的环境变量,所以 Keeper 生成一个只含随机令牌的 `SSH_ASKPASS` 小脚本,由脚本从一个私有 unix socket 取回密码交给 ssh。
  - socket 权限 `0600`,位于 `0700` 的临时目录中,最多应答 5 次提示、120 秒后连同目录一起删除。
  - 密码不进命令行、不进 Terminal 的命令行、也不落盘。
- **macOS RDP**:临时 `.rdp` 只含地址和用户名(60 秒后删除),密码只在剪贴板中暂存 30 秒,需要时手动粘贴。原因见[常见问题](#macos-上-rdp-每次都要输密码能不能免密)。

### 预编译二进制校验

`src/password_manager/assets/keeper-askpass.exe` 是仓库里唯一一个预编译二进制,而它直接经手 SSH 密码:

- 它的 SHA-256 记在 `scripts/keeper-askpass.sha256`,`build-windows.ps1` 在打包前会校验,不匹配就拒绝构建。
- 源码是 `scripts/keeper_askpass.cs`;在 Windows 上用 `csc` 重新编译后,记得同步刷新那个校验值。
- 细节见 [docs/security.md](docs/security.md#7-预编译二进制校验)。

## 后台运行与自动锁定

- 点击窗口关闭按钮时,Keeper 不会立刻退出,而是安静地保留在系统托盘图标中(Windows 为通知区域,macOS 为菜单栏)。
- 双击通知区图标,或右键选择「打开 Keeper」,即可重新显示窗口;点 macOS 程序坞(Dock)图标 / Windows 任务栏按钮同样会把窗口唤回(应用被重新激活时 Keeper 会自己把窗口显示出来,不会再出现「进程还在、屏幕上什么都没有」的状态)。
- 保险库会在连续隐藏 10 分钟后自动锁定;窗口开着但系统连续 10 分钟无输入时同样会锁定。再次打开时必须输入主密码。右键通知区图标可选择「打开 Keeper」或「完全退出」。
- 同一个保险库只允许一个 Keeper 进程打开(通过 `QLocalServer` 占位,名字由保险库路径派生,因此用 `PASSWORD_MANAGER_VAULT` 指定的不同保险库可以并存)。重复启动时第二个进程会把已有窗口调到前台然后退出;上次崩溃残留的占位会被自动回收。
- 从 PowerShell 启动时,请优先使用上述 UI 退出路径;在终端中按 `Ctrl+C` 也可以直接退出(Windows 下 `Ctrl+Z` 不是 GUI 程序的退出命令)。关闭窗口本身只会把程序收进通知区域,不会结束进程。
- 系统通知区域不可用时,关闭窗口会安全锁定并退出,避免留下无法访问的后台进程。

## 备份与限制

备份时先锁定或关闭程序,然后复制整个 `vault.sqlcipher` 文件到安全、受控的位置。SQLCipher 加密整个数据库,但备份副本仍应按敏感数据处理。

> **格式变化:** 新建的 SQLCipher 保险库固定使用 SQLCipher 4 和 PBKDF2-HMAC-SHA512(512,000 次迭代)。整库加密使用新的 `vault.sqlcipher` 文件,不会读取、转换或覆盖旧版 `vault.db`。如果你有旧文件,请先保留其备份;新版本需要创建新的保险库并重新录入数据。
>
> 如果你在此 KDF 配置前创建过、且无需保留数据的 `vault.sqlcipher`,请先完全退出 Keeper,删除该 `vault.sqlcipher` 文件后再启动新版并创建保险库。不要删除旧版 `vault.db`,也不要手动修改保险库文件。

这是单机、单人保险库,并非团队共享密钥系统:它没有用户权限、审计、多设备同步或云端恢复。不要将未受保护的保险库文件、主密码或复制出的凭据上传到聊天、代码仓库或工单系统。完整的威胁模型边界见 [docs/security.md](docs/security.md#10-威胁模型的边界)。

## 导出 Excel

侧边栏的 **导出 Excel** 会把所有应用与服务器中的项目(含用户名、密码和标签)导出为一个 `.xlsx` 文件,表头带筛选器,可按「类型」只看服务器或应用项目;导出顺序与卡片上的 ↑ ↓ 顺序一致。

> ⚠️ **导出的文件不加密、包含全部明文密码。** 请只保存到受信任的位置,使用完毕后及时删除。

导出时每个数据单元格都被强制为纯文本,防止以 `=` 开头的自由文本在 Excel 中被当作公式执行。

## 打包发行

### Windows EXE

先安装开发依赖,再在项目根目录运行构建脚本:

```powershell
python -m pip install -e ".[dev]"
powershell -ExecutionPolicy Bypass -File .\scripts\build-windows.ps1
```

构建完成后,可直接运行 `dist\Keeper\Keeper.exe`。这是 `one-folder` 发行包:**请分发整个 `dist\Keeper` 文件夹**,而不是只复制其中的 EXE。保险库仍保存在 `~/.keeper/vault.sqlcipher`(或 `PASSWORD_MANAGER_VAULT` 所指定的位置),不会被打进发行包。

脚本在调用 PyInstaller 之前会先校验 `keeper-askpass.exe` 的 SHA-256,不匹配直接失败(见[预编译二进制校验](#预编译二进制校验))。

### macOS App

先安装开发依赖,再在项目根目录运行:

```bash
python3 -m pip install -e ".[dev]"
bash scripts/build-macos.sh
```

构建完成后,可直接运行 `dist/Keeper.app`。分发时请复制整个 `.app` 包;保险库仍保存在 `~/.keeper/vault.sqlcipher`,不会被打进发行包。RDP 连接需要用户自行安装 Microsoft **Windows App**。

本机使用时装进 `/Applications` 后请顺手执行下面的清理:只要 `dist/Keeper.app` 与已安装的那一份同时存在,Spotlight 就会把两个同名「Keeper」都索引出来,`Cmd + 空格` 搜「Keeper」会出现两条结果:

```bash
ditto dist/Keeper.app /Applications/Keeper.app && rm -rf dist build
```

`dist/` 与 `build/` 都是构建产物,删掉不影响已安装的 App;下次构建会自动重新生成。

macOS 的构建走 `Keeper.spec`(不是命令行参数),因为 bundle identifier 和版本号只能用 spec 表达:

- `CFBundleIdentifier` 为 `com.seeed.keeper`;`CFBundleShortVersionString` / `CFBundleVersion` 从 `pyproject.toml` 的 `version` 读取。
- 稳定的 bundle id 很关键——macOS 的 TCC 按「bundle id + 代码签名」记住「允许 Keeper 控制 Terminal」这条授权,用 PyInstaller 默认的裸 `Keeper` 会和别的应用撞车。**改 bundle id 会让系统重新弹一次授权。**
- spec 里还带了 `NSAppleEventsUsageDescription`,否则新版 macOS 可能直接拒绝 AppleEvents 请求。

### macOS DMG

如需给其他 Mac 用户分发一个单文件安装镜像:

```bash
bash scripts/package-macos.sh
```

脚本会先生成 `dist/Keeper.app`,再压缩为 `dist/Keeper.dmg`。双击 DMG 后,把 `Keeper.app` 拖到「应用程序」或任意受信任目录即可运行。若未做 Apple 开发者签名/公证,首次打开可能需要在 Finder 中右键选择「打开」以通过 Gatekeeper。

## 常见问题

### macOS 上 RDP 每次都要输密码,能不能免密?

Keeper 按钮发起的是临时连接(Quick Connect),它不写入 Windows App 的连接列表,也**不会复用**你在 Windows App 里保存的凭据,因此每次仍会弹密码框。原因是 Windows App 在 macOS 上没有 AppleScript 字典、没有命令行接口,`ms-rd:` 又只用于 AVD 工作区订阅——没有任何官方接口能让 Keeper 直接启动一条已保存的连接。三条可行路径:

1. **在 Windows App 里保存一次凭据**:右键连接 → 编辑 → 凭据 → 添加凭据,填用户名和密码。之后从 Windows App 的连接列表双击即可,不再询问密码;密码由 Windows App 自己存进登录钥匙串(`svce=com.microsoft.rdc.macos`,`acct=` 该凭据的 GUID),Keeper 不参与。
2. **批量建列表**:用 `scripts/export_rdp_for_windows_app.py` 把保险库里的 RDP 凭据导出成 `.rdp`,再用 文件 → 从 RDP 文件导入... 一次建好。

   ```bash
   python scripts/export_rdp_for_windows_app.py [--vault PATH] [--out DIR]
   ```

   注意双击或 `open` 一个 `.rdp` 是**直接发起连接**,不会导入。
3. **Spotlight**:Windows App 会把每条已保存的连接捐给 Core Spotlight,`Cmd + 空格` 输入连接名再回车,同样能免密启动。

要让 Keeper 一键免密只能靠辅助功能 UI 自动化(需在 系统设置 → 隐私与安全性 → 辅助功能 中授权 Keeper,且 Windows App 改版后可能失效)。

### macOS 为什么弹出「Keeper 想要控制 Terminal」?

SSH 连接是通过 AppleScript 让 Terminal 执行的,这需要 AppleEvents 授权。允许一次即可,TCC 会按「bundle id + 代码签名」记住;改 bundle id 或重签名后会重新弹。

### macOS 上 SSH 没有自动填充密码?

自动填充依赖 `/usr/bin/nc`(BSD netcat 的 unix socket 支持)和 `osascript`。`nc` 不可用时 Keeper 仍会发起连接,只是需要你手动输密码。首次连接也可能因为 Terminal 授权未通过而只弹授权框。

### Windows 上 SSH 没有自动填充密码?

确认已启用 OpenSSH 客户端(Windows 设置 → 应用 → 可选功能)。Keeper 优先使用 `C:\Windows\System32\OpenSSH\ssh.exe` 而不是 PATH 上的 Git/MSYS ssh——后者不是真正的控制台程序,不尊重 `SSH_ASKPASS_REQUIRE`。密码同时会在剪贴板中,可手动粘贴。

### Windows 上 RDP 提示找不到客户端?

需要 `mstsc.exe`(默认在 `C:\Windows\System32`)。没有保存用户名和密码时,Keeper 只会打开普通的连接对话框。

### macOS 上找不到 Windows App?

从 App Store 安装 Microsoft **Windows App**(原 Microsoft Remote Desktop)。Windows App 11.x 已不再接受 `rdp://` 链接,任何写法都会被记为 `failed processing import URL` 并返回 `notSupported`,所以 Keeper 走的是临时 `.rdp` 文件。

### 窗口关了但进程还在?

这是设计如此:关闭窗口只是收进系统托盘。双击托盘图标(Windows 通知区域 / macOS 菜单栏)或右键选「打开 Keeper」即可唤回;要结束进程请右键选「完全退出」。从终端启动时也可以 `Ctrl+C`(Windows 下 `Ctrl+Z` 不是 GUI 程序的退出命令)。系统通知区域不可用时,关闭窗口会直接安全锁定并退出。

### 忘了主密码怎么办?

没有办法恢复。数据库不保存主密码,密钥由它派生;唯一的出路是删除 `vault.sqlcipher` 重新创建保险库并重新录入数据。

### 第二次启动 Keeper 没有反应?

同一个保险库只允许一个进程打开。第二个进程会把已有窗口调到前台然后自行退出;如果已有窗口在托盘里,它会被恢复出来。用 `PASSWORD_MANAGER_VAULT` 指定的不同保险库可以并存。

## 项目结构

```
├── main.py                       # 入口:调用 password_manager.app:main
├── Keeper.spec                   # macOS 打包配置(bundle id、版本、图标、Info.plist)
├── pyproject.toml                # 依赖、入口脚本、pytest 配置
├── docs/
│   ├── security.md               # 安全实现细节(SSH/RDP 注入、DPAPI、JXA、节流…)
│   └── ui-redesign-demo.html     # UI 重构的高保真预览(设计定稿参考)
├── scripts/
│   ├── build-windows.ps1         # Windows 打包(含 askpass 二进制校验)
│   ├── build-macos.sh            # macOS 打包(走 Keeper.spec)
│   ├── package-macos.sh          # 生成 DMG
│   ├── keeper_askpass.cs         # Windows SSH askpass 助手源码
│   ├── keeper-askpass.sha256     # 上述助手预编译二进制的摘要
│   ├── export_rdp_for_windows_app.py  # 批量导出 RDP 凭据为 .rdp
│   └── make_icon.py              # 生成应用图标
├── src/password_manager/
│   ├── app.py                    # Qt 窗口、对话框、托盘、自动锁定、节流、导出
│   ├── generator.py              # 密码生成与熵值强度(纯函数,首页/对话框/测试共用)
│   ├── models.py                 # Entry / Credential 数据类,host:port 解析
│   ├── vault/repository.py       # SQLCipher 连接、schema、CRUD、rekey、迁移
│   ├── services/actions.py       # SSH / RDP / 浏览器 / 剪贴板 / 系统空闲
│   ├── ui/                       # 设计令牌、内联 SVG 图标、可复用组件
│   │   ├── theme.py              # OKLCH 风格色板 + 全局 QSS
│   │   ├── icons.py              # SVG 图标渲染(带缓存)
│   │   └── widgets.py            # 强度计、字符集勾选、生成器、标签输入、Toast…
│   └── assets/                   # 图标与 keeper-askpass.exe
└── tests/                        # 132 个测试:repository / actions / app
```

## 开发验证

```powershell
python -m pytest
python -m compileall -q src
```

测试用 offscreen 平台插件运行 Qt,无需显示器(`tests/test_app.py` 里设置了 `QT_QPA_PLATFORM=offscreen`)。跑单个文件:

```powershell
python -m pytest tests/test_repository.py -v
```
