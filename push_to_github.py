"""
push_to_github.py - 閫氳繃 GitHub REST API 鎺ㄩ€佹枃浠?绠€鍗曠殑鍗曟枃浠舵帹閫佽剼鏈紝鐢ㄤ簬 git 涓嶅彲鐢ㄧ殑鎯呭喌銆?"""
import os
import base64
import json
import urllib.request

GITHUB_TOKEN = "YOUR_GITHUB_PAT_HERE"  # GitHub PAT (姘镐箙鏈夋晥, 2026-05-25)
REPO_OWNER = "ATboy-web"
REPO_NAME = "gm-quant"
BRANCH = "main"

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))

FILES_TO_PUSH = [
    # 鏍稿績鍏ュ彛
    "main.py",
    "config.py",
    "offline_backtest.py",
    # 鏃ュ織
    "gm_logger.py",
    # 鑲＄エ姹?& 鎸囨爣 & 閫夎偂
    "stock_pool.py",
    "indicators.py",
    "screener.py",
    # 鍏瓥鐣?    "strategy_mr.py",
    "strategy_momentum.py",
    "strategy_breakout.py",
    "strategy_dividend.py",
    "strategy_reversal.py",
    "strategy_vrc.py",        # V29.7: VRC replaces VP
    "strategy_factory.py",
    # 琛屼笟閰嶇疆 & 铻嶅悎 & 鎵ц
    "sector_config.py",
    "fusion.py",
    "executor.py",
    # 鎯呯华 & AI
    "sentiment_engine.py",
    "ai_assistant.py",
    # 蹇冭烦 & 宸ュ叿
    "trace.py",
    "push_to_github.py",
    # V29.4: 鍙鍖?    "visualizer.py",
    "README.md",
    "CHANGELOG.md",
    "SECURITY.md",
    "setup.py",
]

def push_file(filepath):
    """閫氳繃 GitHub Contents API 鏇存柊鏂囦欢銆?""
    with open(os.path.join(PROJECT_DIR, filepath), 'rb') as f:
        content = f.read()

    encoded = base64.b64encode(content).decode('utf-8')

    # 鍏堣幏鍙栧綋鍓嶆枃浠剁殑 SHA
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
            print(f"  [閿欒] 鑾峰彇 {filepath} SHA 澶辫触: {e.code} {e.reason}")
            return False

    # 鏇存柊鏂囦欢
    body = json.dumps({
        "message": f"V26: 鍏ㄩ潰浼樺寲 鈥?浠撲綅鍒╃敤鐜?鍏ュ満鏀剁揣+浜ゆ槗棰戠巼闄愬埗+RT鏀剁揣 - {filepath}",
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
        print(f"  [閿欒] 鎺ㄩ€?{filepath} 澶辫触: {e.code} {e.reason}")
        print(f"         {e.read().decode('utf-8', errors='replace')[:200]}")
        return False


if __name__ == "__main__":
    print("=" * 50)
    print("  GitHub Push 鈥?V26 鍏ㄩ潰浼樺寲")
    print("=" * 50)
    ok = 0
    for f in FILES_TO_PUSH:
        if push_file(f):
            ok += 1
    print(f"\n  瀹屾垚: {ok}/{len(FILES_TO_PUSH)} 涓枃浠跺凡鎺ㄩ€?)
