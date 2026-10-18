# Keeper 安全实现说明

本文记录 README「安全模型」背后的具体实现,面向想审计代码或复现构建的人。
所有行为均以 `src/password_manager/` 下的代码为准,文中给出文件与符号名便于对照。

- 保险库与密钥派生:[`vault/repository.py`](../src/password_manager/vault/repository.py)
- 解锁节流、自动锁定、剪贴板清理:[`controller.py`](../src/password_manager/controller.py)(QML 默认 UI)与 [`app.py`](../src/password_manager/app.py)(`KEEPER_UI=widgets` 后备 UI,同一套规则的两份实现)
- SSH / RDP / 浏览器 / 剪贴板标记:[`services/actions.py`](../src/password_manager/services/actions.py)

## 目录

- [1. 保险库加密与主密码](#1-保险库加密与主密码)
- [2. 解锁失败节流](#2-解锁失败节流)
- [3. 自动锁定与密钥释放](#3-自动锁定与密钥释放)
- [4. 剪贴板保护](#4-剪贴板保护)
- [5. SSH 密码注入](#5-ssh-密码注入)
- [6. RDP 密码注入](#6-rdp-密码注入)
- [7. 预编译二进制校验](#7-预编译二进制校验)
- [8. Excel 导出加固](#8-excel-导出加固)
- [9. 单实例与并发打开](#9-单实例与并发打开)
- [10. 威胁模型的边界](#10-威胁模型的边界)

## 1. 保险库加密与主密码

| 项目 | 值 | 来源 |
| --- | --- | --- |
| 加密引擎 | SQLCipher,`PRAGMA cipher_compatibility = 4` | `SQLCIPHER_COMPATIBILITY` |
| KDF | PBKDF2-HMAC-SHA512 | SQLCipher 4 默认 |
| 迭代次数 | 512,000 | `SQLCIPHER_KDF_ITER` |
| salt | 每个保险库文件独有的随机 salt | SQLCipher 页头 |
| 文件标识 | `PRAGMA application_id = 0x564B5032`(`"VKP2"`) | `APPLICATION_ID` |
| 结构版本 | `PRAGMA user_version = 6`(v6 恢复了 `entries.tags` 资产标签列,旧库解锁时自动迁移) | `SCHEMA_VERSION` |
| 默认路径 | `~/.keeper/vault.sqlcipher` | `DEFAULT_VAULT` |

关键点:

- **所有 KDF 设置必须在 `PRAGMA key` 之前执行**(`_connect`)。SQLCipher 只对由本连接新建的数据库应用这些参数;打开已有数据库时,它从加密页头里读回该文件自己的迭代次数。顺序写错会得到一个用错误参数派生密钥、因而永远解不开的库。
- 主密码以 `PRAGMA key = '<escaped>'` 传入,单引号按 SQLCipher 规则转义为两个单引号。含 NUL 字符的密码会被拒绝并给出中文提示,而不是静默截断。
- 数据库中**不保存主密码**,也不保存任何明文凭据;解锁成功的唯一判据是 SQLCipher 能用派生密钥解开页头。
- `PRAGMA cipher_log_level = none`,避免 SQLCipher 把密钥材料写进日志。

### 修改主密码(`PRAGMA rekey`)

`VaultRepository.rekey(current_password, new_password)`:

1. 先用**当前**密码开一条独立连接验证。这一步是必需的:窗口可能处于已解锁的无人看管状态,若不校验旧密码,任何人过来点一下就能把保险库改成只有他知道的密码,等于把所有者锁在门外。
2. 验证通过后执行 `PRAGMA rekey`。SQLCipher 会用**新的随机 salt** 重新派生密钥并重写每一个页。
3. 内容、结构、排序、`user_version` 全部原样保留;rekey 不是导入导出。

### 旧版 `vault.db`

新版只读写 `vault.sqlcipher`,不会读取、转换或覆盖旧版 `vault.db`。旧文件请自行保留备份,新版本需要新建保险库并重新录入。

## 2. 解锁失败节流

`unlock_failure_delay_ms(failure_count)`:延迟 = `min(500ms × 2^(n-1), 8000ms)`,即 0.5s → 1s → 2s → 4s → 8s(封顶)。

- 节流期间解锁按钮与密码输入框被禁用,界面每 100 ms 刷新剩余时间。
- 状态**持久化**在保险库同目录的 `unlock-throttle.json`,权限 `0600`(`os.open` + `O_CREAT`,不经过先建后改的窗口期)。文件里存 `failures` 与墙钟 `until`,读取时换算回单调时钟,因此**重启程序不会清零**;跨睡眠/时钟跳变也不会被绕过。
- 解锁成功后计数与文件一并重置。

这是尽力而为的缓解措施,不是防线:能删掉这个文件的人本来就能直接对保险库文件做离线爆破。真正的成本来自 512,000 次 PBKDF2 迭代。

## 3. 自动锁定与密钥释放

两条独立的锁定路径,阈值同为 `AUTO_LOCK_MS = 10 分钟`:

| 路径 | 触发条件 | 函数 |
| --- | --- | --- |
| 收进托盘后 | 窗口连续隐藏 10 分钟 | `auto_lock` |
| 窗口开着 | **系统级**空闲 10 分钟 | `lock_when_idle` |

系统级空闲由 `system_idle_seconds()` 读取:

- macOS:`CGEventSourceSecondsSinceLastEventType(0, 0xFFFFFFFF)`,即 combined session state + 任意输入事件。
- Windows:`GetLastInputInfo` 与 `GetTickCount` 之差。
- 其他平台返回 `None`,此时不触发空闲锁定。

用系统级计数而不是「本应用有没有收到 Qt 事件」,是为了让你在 Keeper 拉起的 SSH 终端里干活时不会被中途锁掉——那种场景下键盘事件属于 Terminal,不属于 Keeper。轮询间隔 `IDLE_POLL_MS = 5 秒`。

`lock_vault()` 在锁定时会:

- 停止两个计时器;
- 递增 `clipboard_token`,使尚未到期的剪贴板清理回调失效;
- 清空系统剪贴板;
- 调用 `repository.lock()` **关闭数据库连接以释放内存中的密钥**;
- 清空资产列表与搜索框(否则下次解锁会带着上次的搜索词,看起来像数据丢了);
- 切到「保险库已锁定」页面。该页面的状态栏提示不设超时——否则提示淡出后,窗口看起来就像一个空保险库。

## 4. 剪贴板保护

复制用户名/密码后,`QTimer.singleShot(30_000, ...)` 在 30 秒后清除剪贴板,但**仅当期间没有发生新的复制**:`clipboard_token` 在每次复制时自增,回调里比对令牌,不匹配就什么都不做。这样不会把你刚复制的第二条密码误清掉。

macOS 上额外打隐私标记(`set_concealed_clipboard`):

- 目标是 `org.nspasteboard.ConcealedType` 与 `org.nspasteboard.TransientType`,剪贴板管理器与 Handoff/通用剪贴板会主动跳过带这两个标记的项。
- **不能走 Qt**:Qt 6 会把自定义 pasteboard flavor 改名成 `com.trolltech.anymime.*`,没有任何剪贴板管理器认得。
- 因此由一段 JXA 脚本(`CONCEALED_CLIPBOARD_SCRIPT`)直接操作 `NSPasteboard`。待复制文本通过环境变量 `KEEPER_CLIP_TEXT` 传给 `osascript`,**不出现在 argv 中**——`ps` 看不到它。
- 超时 5 秒,实测约 40 ms。`osascript` 不存在或返回非 0 时,函数返回 `False`,调用方退回普通 Qt 剪贴板(仍有 30 秒自动清除,只是没有隐私标记)。

## 5. SSH 密码注入

共同前提:OpenSSH 拒绝从命令行接收密码,但提供 `SSH_ASKPASS` 钩子;`SSH_ASKPASS_REQUIRE=force` 让它在**已附着终端**时也走这个钩子。两个平台的差异都源于「能不能把环境变量交给最终那个 ssh 进程」。

`ssh_executable()` 的选择顺序值得注意:Windows 上优先 `C:\Windows\System32\OpenSSH\ssh.exe`,**而不是 PATH 上更靠前的 Git/MSYS ssh**。原生构建是真正的控制台程序且尊重 `SSH_ASKPASS_REQUIRE`,自动填充依赖这两点。

### Windows

1. 优先使用随包的 `keeper-askpass.exe`(`askpass_executable()`,兼容 PyInstaller 的 `sys._MEIPASS`)。它只做一件事:把 `KEEPER_SSH_PASSWORD` 环境变量的内容以裸 UTF-8 字节写到 stdout。密码只存在于子 ssh 进程的环境里,不落盘、不进 argv。
2. 助手缺失时退回生成的 `.bat`(`set /p ="%KEEPER_SSH_PASSWORD%" < nul`),同样只用环境变量,并由 `_schedule_cleanup` 在 60 秒后删除。
3. 环境里还设 `DISPLAY=1`,因为部分 OpenSSH 构建在没有 DISPLAY 时不会启用 askpass。
4. 以 `CREATE_NEW_CONSOLE` 启动:ssh 是控制台程序,而 Keeper 是 windowed(无控制台)应用,不开新控制台的话会话会随主窗口一起消失。

主机密钥策略为 `-o StrictHostKeyChecking=accept-new`:首次连接自动信任(一键连接没法回答交互式 yes/no),但密钥**后续发生变化时拒绝连接**。这保留了 MITM 检测能力,代价是首次连接不校验指纹。

### macOS

Terminal.app 由 AppleScript 启动,继承的是 Terminal 的环境而非 Keeper 的,所以环境变量这条路走不通。改为「令牌换密码」:

1. `tempfile.mkdtemp(prefix="keeper-ssh-")` 建目录并 `chmod 0700`。
2. 目录内先绑定 unix socket 再收紧权限(`_bind_askpass_socket`:`bind` → `chmod 0600` → `listen`)。顺序是刻意的:如果交给后台线程去 chmod,socket 会有一小段时间是别人可连的。
3. 生成 `askpass.sh`(权限 `0700`),内容只有一条命令:把一个 `secrets.token_urlsafe(24)` 随机令牌 `printf` 给 `nc -U <socket>`。**脚本里没有任何密码。**
4. 后台线程 `_serve_password_over_socket` 最多应答 `MACOS_ASKPASS_ATTEMPTS = 5` 次提示:对端必须先原样发回令牌,才把密码发过去。5 次而不是 1 次,是因为 ssh 可能先问 identity file 的 passphrase 再问密码。
5. `MACOS_ASKPASS_TIMEOUT = 120` 秒后,socket 连同整个目录被删除(实际定时 125 秒,留出余量)。
6. 传给 Terminal 的命令行前缀由 `MACOS_INLINE_ENV_KEYS = ("SSH_ASKPASS", "SSH_ASKPASS_REQUIRE")` **白名单**过滤,保证内联进命令行的只有这两个路径/常量,任何密钥都无法经由这条路径泄漏到 `ps` 或 Terminal 的标题里。
7. 依赖 `/usr/bin/nc`(BSD netcat 的 `-U` 支持 unix socket)。`nc` 不可用时 `_macos_askpass_environment` 返回 `None`,SSH 仍能连接,只是需要手动输密码。
8. socket 路径长度会检查 `UNIX_PATH_MAX = 104`(BSD socket 路径字段的硬上限),超长则放弃自动填充而不是静默失败。

首次使用需要在系统弹窗中允许 Keeper 控制 Terminal(AppleEvents);该授权由 TCC 按「bundle id + 代码签名」记住,所以 `Keeper.spec` 里固定的 `com.seeed.keeper` 很重要。

## 6. RDP 密码注入

`.rdp` 文件统一以 UTF-16 编码写入(`write_rdp_file`),这是所有 RDP 客户端的期望编码。公共行由 `rdp_connection_lines` 生成:

- `full address:s:`、`prompt for credentials:i:0`、`smart sizing:i:1`,以及可选的 `username:s:`;
- **刻意不写屏幕模式与分辨率**,让会话继承客户端自己的默认值(通常是原生分辨率全屏),`smart sizing` 则让窗口化会话可自由缩放。

### Windows

`_generate_rdp_file` 追加一行 `password 51:b:<hex>`:

- `<hex>` 是密码的 UTF-16LE 字节经 DPAPI `CryptProtectData` 加密后的小写十六进制,与 mstsc 自己的「记住我的凭据」完全同格式,**仅当前 Windows 用户可解密**。
- 用 `mstsc <临时文件>` 启动,文件由 `_schedule_cleanup` 在 60 秒后删除。
- 不走凭据管理器,因为两条路都不通:mstsc 会忽略 GENERIC 凭据的密码字段;而第三方写入的 DOMAIN_PASSWORD 条目,密码会被 Windows 剥离。`.rdp` 文件是唯一真能自动填充的机制。
- DPAPI 不可用时(`_dpapi_protect` 返回 `None`)退回 `mstsc /v:<address>`,即普通的连接对话框;此时密码同时在剪贴板中供手动粘贴(30 秒后清除)。

### macOS

调用 `open -b com.microsoft.rdc.macos <临时 .rdp>` 交给 Microsoft **Windows App**(原 Microsoft Remote Desktop)。限制来自 Windows App 本身:

- Windows App 11.x **不再接受 `rdp://` 链接**,任何写法都会被记为 `failed processing import URL` 并返回 `notSupported`。递交 `.rdp` 文件是仅存的编程式发起会话的办法。
- macOS 没有 DPAPI,无法生成 `password 51:b:` 加密块。

因此临时 `.rdp` 只含地址与用户名(60 秒后删除),**密码不写入文件**,只在剪贴板中暂存 30 秒,客户端提示时手动粘贴。

### macOS 上做到真正免密

Keeper 的按钮发起的是临时连接(Quick Connect),它不写入 Windows App 的连接列表,也**不会复用**你在 Windows App 里保存的凭据,因此每次仍会弹密码框。Windows App 在 macOS 上没有 AppleScript 字典、没有命令行接口,`ms-rd:` 只用于 AVD 工作区订阅——没有任何官方接口能让 Keeper 直接启动一条已保存的连接。

可行的免密路径:

1. **在 Windows App 里保存一次凭据**:右键连接 → 编辑 → 凭据 → 添加凭据。之后从连接列表双击即可,不再询问密码。密码由 Windows App 自己存进登录钥匙串(`svce=com.microsoft.rdc.macos`,`acct=` 该凭据的 GUID),Keeper 不参与。
2. **批量导入**:`scripts/export_rdp_for_windows_app.py` 把保险库里所有 RDP 凭据导出成 `.rdp`(只含地址与用户名),再用 文件 → 从 RDP 文件导入... 一次建好连接列表。

   ```
   python scripts/export_rdp_for_windows_app.py [--vault PATH] [--out DIR]
   ```

   注意双击或 `open` 一个 `.rdp` 是**直接发起连接**,不会导入;菜单导入是唯一能让它们变成持久连接的途径。每条连接首次连接时输一次密码,之后由 Windows App 记住。
3. **Spotlight**:Windows App 会把每条已保存的连接捐给 Core Spotlight,`Cmd + 空格` 输入连接名回车即可免密启动。

要让 Keeper 的按钮本身免密,只能靠辅助功能 UI 自动化(需在 系统设置 → 隐私与安全性 → 辅助功能 中授权 Keeper),且 Windows App 改版后随时可能失效——所以没有采用。

## 7. 预编译二进制校验

`src/password_manager/assets/keeper-askpass.exe` 是仓库里**唯一**的预编译二进制,而它直接经手 SSH 密码,因此纳入校验:

- 源码:`scripts/keeper_askpass.cs`(32 行,无网络、无文件访问,只读一个环境变量写 stdout)。
- 记录的摘要:`scripts/keeper-askpass.sha256`。
- `scripts/build-windows.ps1` 在调用 PyInstaller **之前**比对实际 SHA-256,不匹配直接 `exit 1`,拒绝构建。

之所以提交二进制:`csc.exe` 只在 Windows 上可用,macOS/Linux 无法重建它。重新编译后必须同步刷新摘要:

```powershell
csc /nologo /optimize /target:exe /out:keeper-askpass.exe keeper_askpass.cs
certutil -hashfile keeper-askpass.exe SHA256
```

## 8. Excel 导出加固

`write_export_xlsx` 把每一个数据单元格强制为纯文本(`cell.data_type = "s"`)。导出的项目名、用户名、说明都是不受信任的自由文本:若某个值以 `=` 开头,openpyxl 默认会把它存成**活的电子表格公式**,在 Excel 中打开该文件时执行。强制文本类型堵掉了这条公式注入路径。

其余为可用性设置:表头加粗、`freeze_panes = "A2"`、`auto_filter` 覆盖全部数据区(可按「类型」列只看服务器或应用项目)、固定列宽。

> 导出的 `.xlsx` **不加密且包含全部明文密码**。请只保存到受信任的位置,用完及时删除。

## 9. 单实例与并发打开

同一个保险库只允许一个 Keeper 进程打开,通过 `QLocalServer` 占位实现:

- 名字由保险库路径派生:`keeper-vault-<sha256(路径)[:16]>`(`single_instance_name`)。因此用 `PASSWORD_MANAGER_VAULT` 指定的**不同**保险库可以并存,同一保险库不行。
- 重复启动时,第二个进程连上已有占位、把已有窗口调到前台(必要时先从托盘恢复),然后自行退出。
- 上次崩溃残留的占位会被探测并回收(`QLocalServer.removeServer`)后重新绑定。
- **降级而非拒绝服务**:若占位既无法绑定也无法应答(权限异常、临时目录写满),Keeper 会以无保护方式继续运行,而不是把用户锁在自己的保险库外面。

SQLCipher 本身不阻止两个进程同时打开同一文件,这层占位是为了避免两个窗口对同一保险库做出互相覆盖的写入。

## 10. 威胁模型的边界

Keeper 防的是:**别人拿到你的电脑或保险库文件副本,但不知道主密码**。

它不防、也不试图防:

- **已解锁状态下的本机攻击者。** 窗口解锁后,内存里有数据库密钥,屏幕上就是明文。自动锁定与节流只是缩小这个窗口,不能消除它。离开座位请手动锁定。
- **能删改本地文件的攻击者。** 删掉 `unlock-throttle.json` 就绕过了节流;这类攻击者本来就能离线爆破保险库,防线是 512,000 次迭代本身。
- **键盘记录器、恶意扩展、被入侵的 SSH/RDP 客户端。** Keeper 把密码交给系统客户端之后就失去了控制。
- **导出的 Excel 文件。** 明文、不加密。
- **团队场景。** 这是单机单人保险库:没有用户权限、没有审计日志、没有多设备同步、没有云端恢复,也不是共享密钥系统。

另外:不要把未受保护的保险库文件、主密码或复制出的凭据上传到聊天工具、代码仓库或工单系统。
