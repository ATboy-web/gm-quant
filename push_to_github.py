"""
push_to_github.py - 通过 GitHub REST API 推送文件
简单的单文件推送脚本，用于 git 不可用的情况。
"""
import os
import base64
import json
import urllib.request

GITHUB_TOKEN = "YOUR_GITHUB_PAT_HERE"  # 替换为你的 GitHub Personal Access Token (需要 repo 权限)
# 创建 Token: https://github.com/settings/tokens → Generate new token (classic) → 勾选 repo
REPO_OWNER = "ATboy-web"
REPO_NAME = "gm-quant"
BRANCH = "main"

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))

FILES_TO_PUSH = [
    # 核心入口
    "main.py",
    "config.py",
    "offline_backtest.py",
    # 日志
    "gm_logger.py",
    # 股票池 & 指标 & 选股
    "stock_pool.py",
    "indicators.py",
    "screener.py",
    # 六策略
    "strategy_mr.py",
    "strategy_momentum.py",
    "strategy_vp.py",
    "strategy_breakout.py",
    "strategy_dividend.py",
    "strategy_reversal.py",
    "strategy_factory.py",
    # 行业配置 & 融合 & 执行
    "sector_config.py",
    "fusion.py",
    "executor.py",
    # 情绪 & AI
    "sentiment_engine.py",
    "ai_assistant.py",
    # 心跳 & 工具
    "trace.py",
    "push_to_github.py",
]

def push_file(filepath):
    """通过 GitHub Contents API 更新文件。"""
    with open(os.path.join(PROJECT_DIR, filepath), 'rb') as f:
        content = f.read()

    encoded = base64.b64encode(content).decode('utf-8')

    # 先获取当前文件的 SHA
    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/{filepath}?ref={BRANCH}"
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Bearer {GITHUB_TOKEN}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")

    try:
        resp = urllib.request.urlopen(req)
        data = json.loads(resp.read().decode())
        sha = data["sha"]
    except urllib.error.HTTPError as e:
        if e.code == 404:
            sha = None
        else:
            print(f"  [错误] 获取 {filepath} SHA 失败: {e.code} {e.reason}")
            return False

    # 更新文件
    body = json.dumps({
        "message": f"V25: 宽松方案 + 仿真账户配置 + 日志系统 + SDK调研修复 - {filepath}",
        "content": encoded,
        "branch": BRANCH,
    } | ({"sha": sha} if sha else {}))
    
    req = urllib.request.Request(
        url, data=body.encode('utf-8'),
        method="PUT"
    )
    req.add_header("Authorization", f"Bearer {GITHUB_TOKEN}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")

    try:
        resp = urllib.request.urlopen(req)
        print(f"  [OK] {filepath}")
        return True
    except urllib.error.HTTPError as e:
        print(f"  [错误] 推送 {filepath} 失败: {e.code} {e.reason}")
        print(f"         {e.read().decode('utf-8', errors='replace')[:200]}")
        return False


if __name__ == "__main__":
    print("=" * 50)
    print("  GitHub Push — V25 全量同步")
    print("=" * 50)
    ok = 0
    for f in FILES_TO_PUSH:
        if push_file(f):
            ok += 1
    print(f"\n  完成: {ok}/{len(FILES_TO_PUSH)} 个文件已推送")
