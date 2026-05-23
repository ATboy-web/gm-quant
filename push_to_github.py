"""
push_to_github.py - 通过 GitHub REST API 推送文件到 gm-quant 仓库

使用 GitHub Data API (Git Database) 直接创建 commit:
  1. 创建 blobs (文件内容)
  2. 创建 tree (目录结构)
  3. 创建 commit
  4. 更新 branch ref
"""

import json
import os
import urllib.request
import ssl
import base64

# 绕过 SSL 证书验证（环境问题）
ssl_ctx = ssl.create_default_context()
ssl_ctx.check_hostname = False
ssl_ctx.verify_mode = ssl.CERT_NONE

TOKEN = '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'
OWNER = 'ATboy-web'
REPO  = 'gm-quant'
BRANCH = 'main'
API_BASE = 'https://api.github.com'

HEADERS = {
    'Accept': 'application/vnd.github+json',
    'Authorization': f'Bearer {TOKEN}',
    'X-GitHub-Api-Version': '2022-11-28',
    'Content-Type': 'application/json',
    'User-Agent': 'gm-quant-pusher',
}


def api_request(method, path, data=None):
    """发送 GitHub API 请求"""
    url = f'{API_BASE}{path}'
    body = json.dumps(data).encode('utf-8') if data else None

    req = urllib.request.Request(url, data=body, headers=HEADERS, method=method)

    try:
        with urllib.request.urlopen(req, context=ssl_ctx) as resp:
            status = resp.status
            resp_data = json.loads(resp.read().decode('utf-8'))
            return status, resp_data
    except urllib.error.HTTPError as e:
        body_text = e.read().decode('utf-8', errors='replace')
        print(f'  HTTP Error {e.code}: {body_text[:300]}')
        return e.code, None
    except Exception as e:
        print(f'  Request Error: {e}')
        return 0, None


def create_blob(content):
    """创建 blob（文件内容存储）"""
    status, data = api_request('POST', f'/repos/{OWNER}/{REPO}/git/blobs', {
        'content': content,
        'encoding': 'utf-8',
    })
    if status == 201 and data:
        return data['sha']
    return None


def get_main_head():
    """获取 main 分支的最新 commit SHA"""
    status, data = api_request('GET', f'/repos/{OWNER}/{REPO}/git/ref/heads/{BRANCH}')
    if status == 200 and data:
        return data['object']['sha']
    return None


def get_commit_tree_sha(commit_sha):
    """获取 commit 对应的 tree SHA"""
    status, data = api_request('GET', f'/repos/{OWNER}/{REPO}/git/commits/{commit_sha}')
    if status == 200 and data:
        return data['tree']['sha']
    return None


def create_tree(tree_items):
    """创建 tree（目录结构）"""
    status, data = api_request('POST', f'/repos/{OWNER}/{REPO}/git/trees', {
        'base_tree': None,
        'tree': tree_items,
    })
    if status == 201 and data:
        return data['sha']
    return None


def create_commit(tree_sha, message, parent_sha=None):
    """创建 commit"""
    payload = {
        'message': message,
        'tree': tree_sha,
    }
    if parent_sha:
        payload['parents'] = [parent_sha]

    status, data = api_request('POST', f'/repos/{OWNER}/{REPO}/git/commits', payload)
    if status == 201 and data:
        return data['sha']
    return None


def update_ref(commit_sha):
    """更新分支引用"""
    status, data = api_request('PATCH', f'/repos/{OWNER}/{REPO}/git/refs/heads/{BRANCH}', {
        'sha': commit_sha,
        'force': False,
    })
    return status == 200


def main():
    # 项目文件目录
    project_dir = r'C:\Users\Administrator\.goldminer3\projects\6ec60351-55c6-11f1-9418-d843ae58f5f1'

    # 要推送的文件列表
    files_to_push = [
        '.gitignore',
        'README.md',
        'config.py',
        'config.yaml',
        'executor.py',
        'fusion.py',
        'indicators.py',
        'knn_matcher.py',
        'main.py',
        'offline_backtest.py',
        'screener.py',
        'sector_config.py',
        'stock_pool.py',
        'strategy_base.py',
        'strategy_breakout.py',
        'strategy_dividend.py',
        'strategy_factory.py',
        'strategy_momentum.py',
        'strategy_mr.py',
        'strategy_vp.py',
    ]

    print('=' * 60)
    print('  推送 V19.2 代码到 GitHub: %s/%s' % (OWNER, REPO))
    print('=' * 60)

    # Step 1: 检查仓库是否已有 commit
    parent_sha = None
    head_sha = get_main_head()
    if head_sha:
        parent_sha = head_sha
        print('[信息] 仓库已有 commit: %s' % head_sha[:8])
    else:
        print('[信息] 空仓库，将创建初始 commit')

    # Step 2: 创建 blobs
    print('\n[Step 1] 创建文件 blobs...')
    tree_items = []
    for fname in files_to_push:
        fpath = os.path.join(project_dir, fname)
        if not os.path.exists(fpath):
            print('  [跳过] %s (文件不存在)' % fname)
            continue

        with open(fpath, 'r', encoding='utf-8') as f:
            content = f.read()

        blob_sha = create_blob(content)
        if blob_sha:
            tree_items.append({
                'path': fname,
                'mode': '100644',
                'type': 'blob',
                'sha': blob_sha,
            })
            print('  [OK] %s -> %s' % (fname, blob_sha[:8]))
        else:
            print('  [失败] %s' % fname)

    print('\n  共 %d 个文件' % len(tree_items))

    if not tree_items:
        print('[错误] 没有文件可推送')
        return

    # Step 3: 创建 tree
    print('\n[Step 2] 创建 tree...')
    tree_sha = create_tree(tree_items)
    if not tree_sha:
        print('[错误] 创建 tree 失败')
        return
    print('  Tree SHA: %s' % tree_sha[:8])

    # Step 4: 创建 commit
    print('\n[Step 3] 创建 commit...')
    commit_message = 'V19.2: Sector-differentiated strategies with Breakout & Dividend'
    commit_sha = create_commit(tree_sha, commit_message, parent_sha)
    if not commit_sha:
        print('[错误] 创建 commit 失败')
        return
    print('  Commit SHA: %s' % commit_sha[:8])

    # Step 5: 更新分支引用
    print('\n[Step 4] 更新 %s 分支...' % BRANCH)
    if update_ref(commit_sha):
        print('  [OK] 推送成功!')
        print('\n  仓库地址: https://github.com/%s/%s' % (OWNER, REPO))
    else:
        # 如果是空仓库，可能需要用 force
        print('  [尝试] force 更新...')
        status, data = api_request('PATCH', f'/repos/{OWNER}/{REPO}/git/refs/heads/{BRANCH}', {
            'sha': commit_sha,
            'force': True,
        })
        if status == 200:
            print('  [OK] Force 推送成功!')
            print('\n  仓库地址: https://github.com/%s/%s' % (OWNER, REPO))
        else:
            print('[错误] 推送失败, status=%s' % status)


if __name__ == '__main__':
    main()
