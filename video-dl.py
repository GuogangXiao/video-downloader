#!/usr/bin/env python3
"""
video-dl.py — 通过 GitHub Actions 云端代下海外视频，并把产物取回本地。

零依赖（仅标准库），Windows/Linux/macOS 均可运行。

用法:
    python video-dl.py "https://www.youtube.com/watch?v=xxx" [--height 1080] [--extra-args "..."] [--out ./downloads]

认证:
    需要 GitHub 访问令牌，按以下优先级读取:
      1. --token 参数
      2. 环境变量 GITHUB_TOKEN 或 GH_TOKEN
    令牌需有 repo + workflow 权限（生成后建议长期有效）。

退出码: 0=成功; 1=下载失败; 2=参数/认证错误
"""
import argparse
import io
import json
import os
import sys
import time
import urllib.error
import urllib.request
import zipfile

API = "https://api.github.com"
REPO = "GuogangXiao/video-downloader"
WORKFLOW = "download-video.yml"

HEADERS = {"Accept": "application/vnd.github+json"}


def api_request(path, method="GET", token=None, body=None):
    url = API + path
    headers = dict(HEADERS)
    if token:
        headers["Authorization"] = "Bearer " + token
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read()
            return r.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        return e.code, {"message": e.read().decode("utf-8", "replace")[:300]}
    except Exception as e:
        return -1, {"message": str(e)}


def get_token(args):
    token = args.token or os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        print("✗ 未找到 GitHub 令牌。请设置环境变量 GITHUB_TOKEN 或使用 --token 传入。")
        print("  生成方法: GitHub -> Settings -> Developer settings -> Personal access tokens")
        print("           需要勾选 repo 和 workflow 权限")
        sys.exit(2)
    return token


def dispatch(token, url, height, extra_args):
    body = {"ref": "main", "inputs": {"url": url, "height": str(height), "extra_args": extra_args or ""}}
    code, resp = api_request(f"/repos/{REPO}/actions/workflows/{WORKFLOW}/dispatches",
                             "POST", token, body)
    if code == 204:
        print(f"✓ 下载任务已提交: {url}")
        return True
    print(f"✗ 任务提交失败 (HTTP {code}): {resp.get('message', '')}")
    return False


def wait_for_run(token, timeout_min=15, before_id=0):
    """轮询直到出现新 run 并完成，返回 (status, run_id, html_url)"""
    deadline = time.time() + timeout_min * 60
    while time.time() < deadline:
        time.sleep(15)
        _, data = api_request(f"/repos/{REPO}/actions/runs?per_page=1", token=token)
        runs = data.get("workflow_runs") or []
        if not runs or runs[0]["id"] == before_id:
            continue
        run = runs[0]
        print(f"⏳ 任务运行中: {run['status']}...")
        if run["status"] == "completed":
            return run["conclusion"], run["id"], run["html_url"]
    print("✗ 等待超时")
    return None, None, None


def download_artifact(token, run_id, out_dir):
    """下载并解压 artifact 到 out_dir，返回文件列表"""
    code, data = api_request(f"/repos/{REPO}/actions/runs/{run_id}/artifacts", token=token)
    artifacts = data.get("artifacts") or []
    if not artifacts:
        print("✗ 运行完成但没有生成产物")
        return []
    art = artifacts[0]
    print(f"✓ 产物: {art['name']} ({art['size_in_bytes']/1024/1024:.1f} MB)")

    # 第一步：请求 zip 端点拿 302 跳转地址（需要认证，且不能自动跟随——
    # urllib 跟随重定向时会带上 Authorization 头，导致 Azure blob 返回 401）
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            raise urllib.error.HTTPError(newurl, code, msg, headers, fp)

    zip_url = f"{API}/repos/{REPO}/actions/artifacts/{art['id']}/zip"
    req = urllib.request.Request(zip_url, headers={"Authorization": "Bearer " + token,
                                                   "Accept": "application/vnd.github+json"})
    try:
        urllib.request.build_opener(NoRedirect).open(req, timeout=30)
        print("✗ 意外：zip 端点应返回 302")
        return []
    except urllib.error.HTTPError as e:
        if e.code != 302:
            print(f"✗ 获取产物地址失败 (HTTP {e.code})")
            return []
        blob_url = e.headers.get("Location")

    # 第二步：直接请求 blob（SAS 已内嵌在 URL，不能带 Authorization 头，否则 401）
    # 注意：SAS 地址约 10 分钟过期，大文件下载超时会被服务器断连，失败自动重试
    print("⏳ 正在取回产物到本地...")
    data = None
    for attempt in range(1, 4):
        try:
            with urllib.request.urlopen(blob_url, timeout=600) as r:
                data = r.read()
            break
        except Exception as e:
            if attempt == 3:
                print(f"✗ 下载产物失败（已重试 3 次）: {e}")
                return []
            print(f"⚠ 下载中断（{e}），重新获取地址并重试 {attempt}/3 ...")
            time.sleep(3)
            try:
                urllib.request.build_opener(NoRedirect).open(req, timeout=30)
            except urllib.error.HTTPError as e2:
                if e2.code == 302:
                    blob_url = e2.headers.get("Location")

    os.makedirs(out_dir, exist_ok=True)
    files = []
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for name in z.namelist():
            if name.endswith("/"):
                continue
            target = os.path.join(out_dir, os.path.basename(name))
            with open(target, "wb") as f:
                f.write(z.read(name))
            files.append(target)
    print(f"✓ 已取回 {len(files)} 个文件到: {os.path.abspath(out_dir)}")
    for f in files:
        size = os.path.getsize(f) / 1024 / 1024
        print(f"   - {f} ({size:.1f} MB)")
    return files


def fetch_error_summary(token, run_id):
    """下载运行日志，提取 yt-dlp 的错误行"""
    code, data = api_request(f"/repos/{REPO}/actions/runs/{run_id}/logs", token=token)
    if code == 200:
        # 二进制 zip，直接抓关键字
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                for name in z.namelist():
                    log = z.read(name).decode("utf-8", "replace")
                    for line in log.splitlines():
                        if "ERROR:" in line or "Traceback" in line:
                            print("  " + line.strip()[:220])
        except Exception:
            pass


def main():
    parser = argparse.ArgumentParser(description="GitHub Actions 云端代下视频并取回本地")
    parser.add_argument("url", help="视频页面链接或直链")
    parser.add_argument("--height", type=int, default=1080, help="最高分辨率，默认 1080")
    parser.add_argument("--extra-args", default="", help="额外 yt-dlp 参数（如 --write-subs --sub-langs en）")
    parser.add_argument("--out", default="downloads", help="输出目录，默认 ./downloads")
    parser.add_argument("--token", default=None, help="GitHub 令牌（也可用环境变量 GITHUB_TOKEN）")
    parser.add_argument("--timeout", type=int, default=15, help="等待超时分钟数，默认 15")
    args = parser.parse_args()

    token = get_token(args)

    # 在提交前记录当前最新 run id，避免把新任务误判为旧任务
    _, before = api_request(f"/repos/{REPO}/actions/runs?per_page=1", token=token)
    before_id = (before.get("workflow_runs") or [{}])[0].get("id", 0)

    if not dispatch(token, args.url, args.height, args.extra_args):
        sys.exit(1)

    conclusion, run_id, url = wait_for_run(token, args.timeout, before_id)
    if not run_id:
        sys.exit(1)

    print(f"📄 运行详情: {url}")
    if conclusion == "success":
        files = download_artifact(token, run_id, args.out)
        sys.exit(0 if files else 1)
    else:
        print(f"✗ 下载失败（结论: {conclusion}），错误信息：")
        fetch_error_summary(token, run_id)
        sys.exit(1)


if __name__ == "__main__":
    main()
