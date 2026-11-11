# 手机 / 电脑 App 与离线使用

> 更新：2026-11-11。覆盖根路径 `/` 的班级门户、`/personalcenter/` 个人中心、`/daliy/` 班级截止日，以及 Android APK / Windows 桌面版的打包方式。

## 1. 三种入口

| 形态 | 位置 | 适用 | 说明 |
| --- | --- | --- | --- |
| PWA（推荐） | <https://www.2026hfutintegratedcircuit1.com/> | Android / iPhone / Windows / macOS | 浏览器安装，根作用域 Service Worker + 清单，免应用商店 |
| Android APK | `release/ClassHub-android-debug.apk` | Android 7.0+（`minSdk 24`） | WebView 壳，debug 签名，不是 Play 商店正式包 |
| Windows 安装包 | `release/ClassHub-Setup-1.0.0.exe` | Windows 10/11 x64 | Electron + NSIS，未签名，首次运行会有 SmartScreen 提示 |

三者加载的都是同一个线上站点；**不是**三套独立后端。登录、班级数据、DDL 仍以服务器为准。

PWA、Android APK、Windows 安装包以及 DDL 顶栏统一使用**微电子学院院徽**作为标识；离线缓存名见下文 Service Worker 版本。

## 2. 安装 PWA

### Android（Chrome / Edge）

1. 打开 <https://www.2026hfutintegratedcircuit1.com/>，先联网完整打开一次。
2. 浏览器菜单 →「安装应用」/「添加到主屏幕」。
3. 安装后从桌面图标打开；首次仍联网，之后离线可看已缓存内容。浏览器安装图标、Android 桌面图标、Windows 快捷方式图标均使用微电子学院院徽。

### iPhone / iPad（Safari）

1. Safari 打开站点。
2. 分享 →「添加到主屏幕」。
3. iOS 的离线缓存由 Safari 管理，长期不打开或系统清理存储后可能失效。

### Windows / macOS（Chrome / Edge）

1. 地址栏右侧「安装」图标，或菜单 →「应用」→「安装此站点」。
2. 也可以直接使用 `release/ClassHub-Setup-1.0.0.exe`。

## 3. 离线时能做什么

### 3.1 可离线

- 打开**至少完整联网访问过一次**的以下页面：
  - 班级门户 `/`
  - 个人中心 `/personalcenter/`
  - 班级截止日 `/daliy/`
- 查看上次成功加载并缓存的：
  - 登录后的个人资料（姓名、班级、角色、头像）
  - DDL 列表、任务周历、已缓存的新闻
  - 个人中心已加载过的个人待办
- **离线新增 / 修改 / 删除个人待办（个人计划）**。
- 离线操作会暂存在本机，联网后自动同步；同步失败会恢复本地待办。

### 3.2 不可离线 / 只读

- 提交、修改班级 DDL（班委发布/编辑/归档）需要联网。
- 审批成员、通知、报表、后台、QQ/AI 导入需要联网。
- 新闻、班级 DDL 是**只读缓存**，离线不会产生假的班级数据。
- 离线时不能首次登录；只能打开上一次登录后缓存的身份。

## 4. 缓存与账号隔离

- 页面外壳由根作用域 Service Worker 缓存：`/sw.js`，缓存名 `classhub-shell-v28`。
- 接口数据**不由 SW 缓存**，由 `web/assets/offline.js` 按学号存到浏览器 `localStorage`，键前缀 `cdh.offline.v1.`，避免多个账号串数据。
- 离线个人待办使用 `client_key` 幂等键；同一条离线计划即使重复提交，服务端也只会落一条。
- 退出登录会清空本机缓存（需要能连到服务器完成退出；离线时请在浏览器设置里清除站点数据）。
- 共用电脑/手机请在使用后退出，避免下一位使用者看到上一位的缓存资料。

> 本机缓存不加密。它只保存本人可见的班级数据；设备丢失或转借时，应及时在个人中心退出，或在浏览器设置中清除该站点数据。

## 5. 原生包构建

### Android

前置：JDK 17+、Android SDK（`platforms;android-35`、`build-tools;35.0.0`）、Gradle 8.10.2。

```powershell
# 本机 SDK 路径写入 native\android\local.properties，例如：
# sdk.dir=C:\\Users\\<用户>\\AppData\\Local\\Android\\Sdk
$env:JAVA_HOME="C:\Program Files\Zulu\zulu-21"
& "$env:TEMP\gradle-8.10.2\bin\gradle.bat" -p native\android assembleDebug
Copy-Item native\android\app\build\outputs\apk\debug\app-debug.apk release\ClassHub-android-debug.apk
```

- 包名 `com.hfut.classhub`，应用名「微电子学院班级门户」，`compileSdk 35 / targetSdk 35 / minSdk 24`。
- 只申请 `INTERNET` 和 `ACCESS_NETWORK_STATE`；站点域名与 `*.hfut.edu.cn` 在 WebView 内打开，其他链接交给系统浏览器。
- 当前为 **debug 签名**，仅供班级内安装测试；上架或正式分发需另行配置 release 签名。

### Windows

前置：Node 24 + pnpm（本仓库使用运行时自带 Node/pnpm），Electron 33.2.1。

```powershell
cd native\desktop
pnpm install
# 若 Electron 二进制未随依赖下载，可手动执行：
node node_modules\electron\install.js
node node_modules\electron-builder\cli.js --win nsis --publish never
```

- 产物：`release/ClassHub-Setup-1.0.0.exe`（NSIS，安装目录可选，创建桌面/开始菜单快捷方式）。
- `package.json` 中 `win.signAndEditExecutable` 保持 `false`，否则 Windows 无符号链接权限时 `winCodeSign` 解压会失败；安装器和卸载器图标由 NSIS 自动使用 `build/icon.ico`。
- 该设置也会让 `win-unpacked\微电子学院班级门户.exe` 保留 Electron 默认图标。发布前用已有的 `rcedit-x64.exe` 补一次：
  ```powershell
  $rcedit = "$env:LOCALAPPDATA\electron-builder\Cache\winCodeSign\080642987\rcedit-x64.exe"
  & $rcedit "release\win-unpacked\微电子学院班级门户.exe" --set-icon "native\desktop\build\icon.ico"
  node native\desktop\node_modules\electron-builder\cli.js --win nsis --prepackaged release\win-unpacked --projectDir native\desktop
  ```
  第二条命令会重打安装包，确保安装后的主程序也是院徽。
- 未签名，Windows 会显示「未知发布者」；不要向同学宣称这是微软签名应用。
- 桌面壳只做窗口与外部链接转发，不启用 Node 集成；页面仍在默认 Electron 会话中运行，PWA 缓存可复用。
- 应用启动时会加载线上地址；**首次启动需要联网**。

## 6. 验证与已知限制

已验证：

- 根 PWA：`/sw.js` scope `/`，清单 `application/manifest+json`，离线重载首页能在无网络时显示上次内容；
- 本地 QA：离线打开个人中心、DDL、首页；离线新增个人待办；联网后同步只落一条（`client_key` 幂等）；
- 48 个 unittest 通过（含 PWA 外壳、离线脚本、幂等个人待办）；
- Windows 打包版启动并注册根 Service Worker，断网重载仍能显示缓存首页；
- APK 通过 `aapt dump badging` 检查：包名、SDK、应用名与图标正确。

限制：

1. 首次离线打开某页面前，必须先联网打开过该页；没缓存过的页面会提示「这个页面还没有缓存」。
2. Android APK 是 debug 包，不能直接上架；iOS 暂无 IPA（需 macOS/Xcode 与签名）。
3. Windows 安装包未签名；SmartScreen 会拦截，需用户选择「仍要运行」。
4. 原生壳没有推送、自动更新、后台同步；打开时才同步离线队列。
5. 原生壳不替代服务器备份；班级数据仍以 `data/classes/*.db` 与远端 `/opt/classhub/data` 为准。
6. PWA 在 iOS 上的离线持久性受 Safari 存储策略影响。
7. 浏览器 `localStorage` 有容量上限；个人待办与缓存数据量小，班级 DDL 的缓存只保留最近一次成功响应，不做长期归档。

### 6.1 当前产物

| 文件 | 大小 | SHA-256 |
| --- | --- | --- |
| `release/ClassHub-android-debug.apk` | 343,066 B | `FA5AE8E4F1B38C76DEC98843FBF97C59D047736F9EAFBF7873EB21E83840F341` |
| `release/ClassHub-Setup-1.0.0.exe` | 82,422,160 B | `E7C8146FD4A29DB7D1A3B6D7EE9F2C9035FAA5CEB5FCE6045D4ABA8DBE05863B` |

校验文件：`release/SHA256SUMS.txt`；安装说明：`release/README.md`。

## 7. 相关文件

| 文件 | 作用 |
| --- | --- |
| `web/sw.js` | 根作用域 Service Worker，缓存三套页面外壳 |
| `web/assets/offline.js` | 接口缓存、离线身份、个人待办队列与同步 |
| `web/manifest.webmanifest` | 根作用域 PWA 清单、快捷方式、图标 |
| `app/schema.sql` / `app/db.py` | `personal_items.client_key` 与唯一索引迁移 |
| `native/android/` | Android WebView 工程 |
| `native/desktop/` | Electron + electron-builder 工程 |
| `release/` | 已构建 APK / Windows 安装包 |
