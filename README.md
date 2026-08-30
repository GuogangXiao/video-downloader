# video-downloader — 海外视频云端代下

在国内无法直接访问海外站点的情况下，利用 GitHub Actions（海外服务器、免费额度）
在云端执行 yt-dlp 下载视频，产物（artifact）从 GitHub 取回 —— GitHub 国内可直连。
零成本、无需代理。

## 用法一：网页操作（无需任何安装）

1. 本仓库 → **Actions** → **Video Download** → **Run workflow**
2. 粘贴视频链接，选分辨率，运行
3. 几分钟后进入该次运行页面，底部 **Artifacts** 点 `video` 下载 zip

## 用法二：命令行一条命令（自动取回解压到本地）

下载本仓库的 `video-dl.py`（零依赖，纯 Python 标准库）：

```bash
# 直接下载（raw 可能被墙时用 gh-proxy 镜像）
curl -L -o video-dl.py https://raw.githubusercontent.com/GuogangXiao/video-downloader/main/video-dl.py
curl -L -o video-dl.py https://gh-proxy.com/https://raw.githubusercontent.com/GuogangXiao/video-downloader/main/video-dl.py
```

使用（需要环境变量 `GITHUB_TOKEN`，classic PAT，勾选 repo + workflow 权限）：

```bash
python video-dl.py "https://www.youtube.com/watch?v=xxx" --height 1080 --out ./downloads
```

脚本自动完成：提交任务 → 轮询运行 → 取回产物 → 解压到 `--out` 目录。
退出码 `0` 成功 / `1` 失败（打印云端错误摘要）/ `2` 认证错误。

大文件注意：产物下载地址约 10 分钟有效期，脚本遇断连会自动重试（最多 3 次）。

## 平台支持现状（2026-08 实测）

| 平台 | 状态 |
|---|---|
| YouTube | ⚠️ 需先配置真实登录 cookies（见下节） |
| Twitter/X、Instagram、TikTok、Facebook 公开视频 | ✅ 直接可用 |
| 网页直链视频（.mp4 等） | ✅ 直接可用 |
| Internet Archive | ✅ 实测通过 |
| Vimeo | ⚠️ 需要账号 cookies |

## YouTube 为什么下不了 & 怎么解决

YouTube 对数据中心 IP（包括 GitHub Actions 的服务器）风控极严，报
"Sign in to confirm you're not a bot"。已实测无效的免登录方案：游客 cookies、
tv/web_safari 客户端伪装、cobalt 公共实例（已大面积关停/收费）。

**唯一可行路径：提供真实登录 cookies**

1. 找一台能访问 YouTube 的设备，Chrome 安装扩展 "Get cookies.txt LOCALLY"
2. 登录 YouTube 后导出 `cookies.txt`
3. 仓库 → Settings → Secrets and variables → Actions → New repository secret
4. 名称 `YTDLP_COOKIES`，值粘贴 cookies.txt 全部内容，保存即可长期使用

## 工作流说明

| Workflow | 作用 |
|---|---|
| `download-video.yml` | 主下载流程：装 deno/ffmpeg/yt-dlp → 下载 → 上传产物 |
| `browser-cookies.yml` | 云端浏览器获取 YouTube 游客 cookies 写入 Secrets（对绕过 IP 风控无效，供参考/非 YouTube 站点使用） |

## 注意事项

- 单次产物建议 1GB 内；artifact 保留 3 天
- 公开仓库 Actions 免费无限额；转私有会降至每月 500MB 配额
- 下载的视频仅供个人观看，请勿二次传播
