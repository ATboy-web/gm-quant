"""
push_versions.py - 推送版本历史目录到 GitHub

将 versions/ 目录下的所有版本文件推送到 gm-quant 仓库。
"""

import json
import os
import urllib.request
import ssl

# 绕过 SSL 证书验证
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
    status, data = api_request('POST', f'/repos/{OWNER}/{REPO}/git/blobs', {
        'content': content,
        'encoding': 'utf-8',
    })
    if status == 201 and data:
        return data['sha']
    return None


def get_main_head():
    status, data = api_request('GET', f'/repos/{OWNER}/{REPO}/git/ref/heads/{BRANCH}')
    if status == 200 and data:
        return data['object']['sha']
    return None


def create_tree(tree_items, base_tree_sha=None):
    payload = {'tree': tree_items}
    if base_tree_sha:
        payload['base_tree'] = base_tree_sha
    status, data = api_request('POST', f'/repos/{OWNER}/{REPO}/git/trees', payload)
    if status == 201 and data:
        return data['sha']
    return None


def create_commit(tree_sha, message, parent_sha=None):
    payload = {'message': message, 'tree': tree_sha}
    if parent_sha:
        payload['parents'] = [parent_sha]
    status, data = api_request('POST', f'/repos/{OWNER}/{REPO}/git/commits', payload)
    if status == 201 and data:
        return data['sha']
    return None


def update_ref(commit_sha):
    status, data = api_request('PATCH', f'/repos/{OWNER}/{REPO}/git/refs/heads/{BRANCH}', {
        'sha': commit_sha,
        'force': False,
    })
    return status == 200


def main():
    project_dir = r'C:\Users\Administrator\.goldminer3\projects\6ec60351-55c6-11f1-9418-d843ae58f5f1'

    # Collect all version files
    versions_dir = os.path.join(project_dir, 'versions')
    files_to_push = []

    for root, dirs, files in os.walk(versions_dir):
        for fname in files:
            fpath = os.path.join(root, fname)
            # Compute relative path from project_dir
            rel_path = os.path.relpath(fpath, project_dir).replace('\\', '/')
            # Skip __pycache__ and .pyc files
            if '__pycache__' in rel_path or rel_path.endswith('.pyc'):
                continue
            files_to_push.append((rel_path, fpath))

    # Also include root-level files
    root_files = [
        '.gitignore', 'README.md', 'config.py', 'config.yaml',
        'fusion.py', 'indicators.py', 'knn_matcher.py', 'main.py',
        'offline_backtest.py', 'push_to_github.py', 'screener.py',
        'stock_pool.py', 'strategy_momentum.py', 'strategy_mr.py', 'strategy_vp.py',
    ]
    for fname in root_files:
        fpath = os.path.join(project_dir, fname)
        if os.path.exists(fpath):
            # Check if already in files_to_push
            if not any(f[0] == fname for f in files_to_push):
                files_to_push.append((fname, fpath))

    # Sort by path
    files_to_push.sort(key=lambda x: x[0])

    print('=' * 60)
    print('  推送版本历史到 GitHub: %s/%s' % (OWNER, REPO))
    print('=' * 60)
    print('  共 %d 个文件' % len(files_to_push))

    # Get current HEAD
    parent_sha = get_main_head()
    if parent_sha:
        print('  当前 HEAD: %s' % parent_sha[:8])
    else:
        print('  [错误] 无法获取当前 HEAD')
        return

    # Create blobs
    print('\n[Step 1] 创建文件 blobs...')
    tree_items = []
    for rel_path, fpath in files_to_push:
        with open(fpath, 'r', encoding='utf-8') as f:
            content = f.read()

        blob_sha = create_blob(content)
        if blob_sha:
            tree_items.append({
                'path': rel_path,
                'mode': '100644',
                'type': 'blob',
                'sha': blob_sha,
            })
            print('  [OK] %s' % rel_path)
        else:
            print('  [失败] %s' % rel_path)

    print('\n  共 %d 个文件 blob 化' % len(tree_items))

    if not tree_items:
        print('[错误] 没有文件可推送')
        return

    # Create tree
    print('\n[Step 2] 创建 tree...')
    tree_sha = create_tree(tree_items)
    if not tree_sha:
        print('[错误] 创建 tree 失败')
        return
    print('  Tree SHA: %s' % tree_sha[:8])

    # Create commit
    print('\n[Step 3] 创建 commit...')
    commit_sha = create_commit(tree_sha, 'Add version history: V1-V18.1 with strategy documentation', parent_sha)
    if not commit_sha:
        print('[错误] 创建 commit 失败')
        return
    print('  Commit SHA: %s' % commit_sha[:8])

    # Update ref
    print('\n[Step 4] 更新 %s 分支...' % BRANCH)
    if update_ref(commit_sha):
        print('  [OK] 推送成功!')
        print('\n  仓库地址: https://github.com/%s/%s' % (OWNER, REPO))
    else:
        print('[错误] 推送失败')


if __name__ == '__main__':
    main()
