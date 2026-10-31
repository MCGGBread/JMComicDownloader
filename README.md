# JMComicDownloader

基于 [JMComic-Crawler-Python](https://github.com/hect0x7/JMComic-Crawler-Python) 的禁漫本子下载器，
提供 **Windows 便携版** 和 **Android 版** 两个客户端：输入番号 → 自动下载 → 还原图片 → 合成 PDF。

> 本仓库只包含客户端代码与构建产物，不提供、不托管任何内容。

## 下载

| 平台 | 文件 | 说明 |
| --- | --- | --- |
| Windows 10/11 | [JMComicClient.exe](https://github.com/MCGGBread/JMComicDownloader/releases/latest/download/JMComicClient.exe) | 单文件便携版，约 26 MB，双击即用，无需安装 Python |
| Android 10+ | [JMComicClient.apk](https://github.com/MCGGBread/JMComicDownloader/releases/latest/download/JMComicClient.apk) | 约 61 KB，自签名，需允许「安装未知来源应用」 |

所有历史版本见 [Releases](https://github.com/MCGGBread/JMComicDownloader/releases)。
仓库只保存源码，编译产物统一放在 Release 附件里。

两个客户端都是免安装的：Windows 版把 exe 放到任意文件夹双击运行，会在同级目录生成
`config/`、`crawled_data/`、`logs/`；安卓版直接把 PDF 存到系统「下载 / JMComic」。

## 功能

- **番号解析**：兼容各种粘贴格式，重复自动去重、保持顺序
  ```
  jm54747电梯（极品）
  h540931(瞬)-h499835(幼瞬)✔️
  142176(母子大车)404477(长篇大车，经典作品)404098(狐娘)
  47228，118983，152470，197393
  JM-54747 / JM 28650 / [JM100]
  https://18comic.vip/album/54747/   aid=54747
  ```
  日期、版本号、`【分类】22`、`(C88)` 这类数字不会被误判。

- **批量队列**：逐条下载、实时进度；运行中可以继续粘贴番号「追加任务」，不用等上一批结束。
- **断点续传**：队列持久化，关掉应用（甚至强杀）后重开，列表还在、未完成的自动继续。
- **自动出 PDF**：每本一个 PDF，按章节和页码顺序合成；可选保留原图 / ZIP。
- **爬取记录**：记录番号、标题、页数、时间、PDF 路径，支持搜索、导出、重新爬取。
- **可调参数**：并发数、代理、Cookie、PDF 质量/宽度、文件命名模板等。

## 两个版本的差异

| 项目 | Windows 版 | Android 版 |
| --- | --- | --- |
| 技术栈 | Python + tkinter，PyInstaller 打包 | Java + WebView，SDK 工具手工打包 APK |
| 客户端实现 | api / html 可切换，失败自动回退 | 仅 api（html 端有 Cloudflare 风控） |
| 存储位置 | 可在设置里指定任意目录 | PDF 固定在系统下载目录（分区存储限制） |
| 处理流程 | 下载 → ZIP → 解包 → PDF | 下载 → 还原 → PDF（ZIP 可选） |
| 后台运行 | 窗口最小化即继续 | 前台服务 + 通知栏进度，切后台/息屏继续 |

## 快速开始

**Windows**

1. 下载 `windows/dist/JMComicClient.exe`，放到任意文件夹；
2. 双击运行，粘贴番号，点「开始爬取」；
3. PDF 在 `crawled_data/pdf/`（或你在设置里指定的目录）。

**Android**

1. 下载 `android/dist/JMComicClient.apk` 传到手机，点击安装；
2. 首次启动允许通知权限（显示下载进度）；
3. 粘贴番号 → 开始爬取，PDF 存到「下载 / JMComic」。

## 目录结构

```
windows/                Windows 便携版
  app/                  源码（runtime / config / parser / pipeline / pdf / history / ui）
  tools/                开发用脚本（截图、冒烟测试、协议验证）
  dist/                 本地构建产物（不提交，发布版见 Releases）
  main.py  build.py  build.bat  run_dev.bat  requirements.txt

android/                Android 版
  app/
    src/com/jmcomic/app/   Java 源码（API / 解析 / 还原 / PDF / 队列 / 前台服务）
    assets/                界面（HTML/CSS/JS）
    res/                   图标与主题
  desktop/              桌面 JVM 验证程序（不打包进 APK）
  screenshots/          界面截图
  dist/                 本地构建产物（不提交，发布版见 Releases）
  build.py  build.bat
```

## 从源码构建

**Windows**（需要 Python 3.10+，带 tkinter）

```bat
cd windows
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt pyinstaller
.venv\Scripts\python build.py
```

**Android**（需要 JDK 17 + Android SDK build-tools 35 / platform 35，不需要 Gradle）

```bat
cd android
build.bat
```

构建脚本会依次执行 `aapt2 → javac → d8 → zipalign → apksigner`。
仓库不含签名密钥，首次构建会在 `android/keystore/` 生成新的自签名证书；
**用新证书签的 APK 无法覆盖安装官方发布的包**，需要先卸载旧版。

## 常见问题

**下载一直失败 / 超时**
国内网络通常需要代理。Windows 版在设置里把「网络代理」改成 `127.0.0.1:7890`（按你的端口）；
安卓版在设置里填 `host:port`。也可以切换客户端实现（Windows）或稍后重试。

**提示「没有下载到图片」**
多为番号不存在、域名被墙或需要登录。少数题材需要填 Cookie（浏览器里名为 `AVS` 的值）。

**杀毒软件报毒（Windows）**
PyInstaller 单文件程序常被误判为加壳，加入信任即可；也可以按上面的步骤从源码运行。

**PDF 图片错位**
v1.0.0 的安卓版存在分块还原参数错误，已在 v1.0.1 修复；旧 PDF 需要重新爬取。

## 致谢

- 核心下载能力来自 [jmcomic](https://github.com/hect0x7/JMComic-Crawler-Python)（MIT）。
- 安卓版的图片分块还原算法移植自该项目，与官方实现逐像素一致。

## 免责声明

本项目仅供学习与技术研究使用，不提供、不托管、不传播任何内容。
请遵守当地法律法规与目标站点的服务条款，仅下载你有权访问的内容，并控制请求频率。
因使用本项目产生的一切后果由使用者自行承担。

## License

[MIT](LICENSE)
