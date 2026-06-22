import os
import sys
import threading
import sqlite3
import json
import urllib.request
import urllib.error
import shutil
import stat
import webbrowser
import subprocess
import time
import socket
import ssl
from datetime import datetime, timezone, timedelta

# 实例检测：防止程序重复启动
try:
    instance_lock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    instance_lock.bind(('127.0.0.1', 58763)) 
except Exception:
    print("程序已经在后台运行中了！请查看系统托盘图标。")
    sys.exit(0)

def get_free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(('127.0.0.1', 0))
    port = s.getsockname()[1]
    s.close()
    return port

CURRENT_PORT = get_free_port()

# 设置全局代理环境（针对 GitHub API）
os.environ["http_proxy"] = "http://127.0.0.1:10808"
os.environ["https_proxy"] = "http://127.0.0.1:10808"

try:
    from flask import Flask, request, jsonify, render_template_string, Response
    from dulwich import porcelain
    from dulwich.repo import Repo
    import pystray
    from PIL import Image, ImageDraw
except ImportError:
    print("缺少依赖！请先在终端运行：pip install flask dulwich pystray pillow")
    sys.exit()

def get_resource_path(relative_path):
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath(os.path.dirname(__file__)), relative_path)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "manager_data.db")

# 【核心修正】加入大量常见的 IDE、系统缓存、构建包目录，防止底层时间遍历时的幽灵误报
IGNORE_PATTERNS = ('.db', '.log', '.sqlite', '.sqlite3', '.pyc', '.DS_Store', '.suo', '.user', '.pyo', '.pyd')
IGNORE_NAMES = ('manager_data.db', '__pycache__', '.DS_Store')
IGNORE_DIRS = {'.git', 'node_modules', 'venv', '.venv', '__pycache__', '.vscode', '.idea', '.cursor', '.github', 'dist', 'build', 'out', 'target'}

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS settings (id INTEGER PRIMARY KEY, token TEXT)')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY, name TEXT, path TEXT, repo_url TEXT, origin TEXT
        )
    ''')
    cursor.execute("PRAGMA table_info(projects)")
    columns = [info[1] for info in cursor.fetchall()]
    if 'last_sync' not in columns:
        cursor.execute("ALTER TABLE projects ADD COLUMN last_sync TEXT DEFAULT '缺省'")
    cursor.execute("PRAGMA table_info(settings)")
    setting_columns = [info[1] for info in cursor.fetchall()]
    if 'v2ray_path' not in setting_columns:
        cursor.execute("ALTER TABLE settings ADD COLUMN v2ray_path TEXT DEFAULT ''")

    cursor.execute("SELECT COUNT(*) FROM settings")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO settings (token) VALUES ('')")
    conn.commit()
    conn.close()

def get_token():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT token FROM settings WHERE id = 1")
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else ""

def save_token(token):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE settings SET token = ? WHERE id = 1", (token,))
    conn.commit()
    conn.close()

def get_v2ray_path():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT v2ray_path FROM settings WHERE id = 1")
    row = cursor.fetchone()
    conn.close()
    return row[0] if row and row[0] else ""

def save_v2ray_path(path):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE settings SET v2ray_path = ? WHERE id = 1", (path,))
    conn.commit()
    conn.close()

def start_v2rayn():
    v2ray_path = get_v2ray_path()
    if not v2ray_path:
        return {"status": "error", "msg": "未配置 V2rayN 启动路径"}
    if not os.path.exists(v2ray_path):
        return {"status": "error", "msg": f"路径不存在: {v2ray_path}"}
    try:
        if os.name == 'nt':
            subprocess.Popen(f'start "" "{v2ray_path}"', shell=True)
        else:
            subprocess.Popen([v2ray_path])
        time.sleep(2)
        if is_v2rayn_running():
            return {"status": "success", "msg": "V2rayN 启动成功"}
        else:
            return {"status": "error", "msg": "启动命令已执行，但V2rayN进程未检测到"}
    except Exception as e:
        return {"status": "error", "msg": f"启动失败: {str(e)}"}

def update_last_sync(name):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    tz_utc8 = timezone(timedelta(hours=8))
    now_str = datetime.now(tz_utc8).strftime('%Y-%m-%d %H:%M:%S')
    c.execute("UPDATE projects SET last_sync = ? WHERE name = ?", (now_str, name))
    conn.commit()
    conn.close()

init_db()

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>GitHub 工作台</title>
    <link rel="icon" type="image/svg+xml" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'><path fill='%231f2937' d='M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z'/></svg>">
    <style>
        :root {
            --primary: #3b82f6; --primary-hover: #2563eb;
            --success: #10b981; --success-hover: #059669;
            --danger: #ef4444; --danger-hover: #dc2626;
            --warning: #f59e0b; --warning-hover: #d97706;
            --info: #6366f1; --info-hover: #4f46e5;
            --secondary: #64748b; --secondary-hover: #475569;
            --bg-color: #f8fafc; --card-bg: #ffffff;
            --text-main: #1e293b; --text-light: #64748b;
        }
        * { box-sizing: border-box; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif; }
        
        html, body { height: 100vh; margin: 0; padding: 0; overflow: hidden; background-color: var(--bg-color); color: var(--text-main); }
        body { display: flex; justify-content: center; padding: 15px; }
        
        .container { width: 100%; max-width: 1400px; height: 100%; display: flex; flex-direction: column; gap: 15px; }
        
        .header { flex-shrink: 0; display: flex; justify-content: space-between; align-items: center; padding-bottom: 12px; border-bottom: 2px solid #e2e8f0; }
        .header h1 { margin: 0; font-size: 22px; color: #0f172a; display: flex; align-items: center; gap: 10px; }
        .header-actions { display: flex; gap: 12px; }

        .grid { flex: 1; min-height: 0; display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
        .card { background: var(--card-bg); border-radius: 12px; padding: 16px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05); border: 1px solid #e2e8f0; display: flex; flex-direction: column; min-height: 0;}
        .card h3 { margin-top: 0; margin-bottom: 12px; font-size: 16px; display: flex; align-items: center; gap: 8px; color: #334155; flex-shrink: 0;}
        
        .custom-list { flex: 1; min-height: 0; overflow-y: auto; border: 1px solid #cbd5e1; border-radius: 8px; background: #f8fafc; padding: 10px; margin-bottom: 0; display: flex; flex-direction: column; gap: 10px;}
        .custom-list::-webkit-scrollbar { width: 6px; }
        .custom-list::-webkit-scrollbar-thumb { background: #cbd5e1; border-radius: 4px; }
        .custom-list::-webkit-scrollbar-thumb:hover { background: #94a3b8; }

        .list-item { background: #ffffff; padding: 14px; border-radius: 8px; border: 1px solid #e2e8f0; display: flex; flex-direction: column; gap: 8px; transition: box-shadow 0.2s; box-shadow: 0 1px 2px rgba(0,0,0,0.02);}
        .list-item:hover { box-shadow: 0 4px 6px rgba(0,0,0,0.05); border-color: #cbd5e1; }
        .list-item.active { border-color: var(--primary); background: #eff6ff; }
        
        .item-header { display: flex; justify-content: space-between; align-items: center; }
        .item-name { font-weight: 600; font-size: 15px; color: #0f172a; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;}
        .item-meta { font-size: 12px; color: #64748b; display: flex; flex-wrap: wrap; gap: 12px; margin-bottom: 4px;}
        .item-meta span { display: flex; align-items: center; gap: 4px; }
        
        .item-actions { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; width: 100%;}
        .btn-right { margin-left: auto; }

        .badge { font-size: 11px; padding: 3px 8px; border-radius: 12px; background: #e2e8f0; color: #475569; font-weight: 500;}

        button { padding: 8px 12px; border: none; border-radius: 6px; font-weight: 600; font-size: 13px; cursor: pointer; display: flex; align-items: center; justify-content: center; gap: 6px; transition: all 0.2s; color: white;}
        button:disabled { opacity: 0.6; cursor: not-allowed; filter: grayscale(50%); }
        button:active:not(:disabled) { transform: translateY(1px); }
        .btn-primary { background: var(--primary); } .btn-primary:hover:not(:disabled) { background: var(--primary-hover); }
        .btn-success { background: var(--success); } .btn-success:hover:not(:disabled) { background: var(--success-hover); }
        .btn-danger { background: var(--danger); } .btn-danger:hover:not(:disabled) { background: var(--danger-hover); }
        .btn-warning { background: var(--warning); color: #fff;} .btn-warning:hover:not(:disabled) { background: var(--warning-hover); }
        .btn-info { background: var(--info); } .btn-info:hover:not(:disabled) { background: var(--info-hover); }
        .btn-secondary { background: var(--secondary); } .btn-secondary:hover:not(:disabled) { background: var(--secondary-hover); }
        .btn-sm { padding: 6px 12px; font-size: 12px; border-radius: 5px; }

        .spinner { display: none; width: 12px; height: 12px; border: 2px solid rgba(255,255,255,0.3); border-radius: 50%; border-top-color: #fff; animation: spin 1s linear infinite; }
        @keyframes spin { to { transform: rotate(360deg); } }

        .terminal-container { flex-shrink: 0; height: 25vh; min-height: 160px; max-height: 250px; background: var(--card-bg); border-radius: 12px; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1); border: 1px solid #e2e8f0; display: flex; flex-direction: column;}
        .terminal-header { background: #f1f5f9; padding: 8px 14px; display: flex; align-items: center; gap: 8px; border-bottom: 1px solid #e2e8f0; flex-shrink: 0;}
        .mac-dot { width: 10px; height: 10px; border-radius: 50%; }
        .terminal-title { margin-left: 8px; font-size: 12px; color: #64748b; font-weight: 600; }
        #log-console { flex: 1; width: 100%; background: #0f172a; color: #4ade80; font-family: 'Consolas', monospace; padding: 12px; border: none; resize: none; font-size: 13px; line-height: 1.5; outline: none; margin: 0;}
        #log-console::-webkit-scrollbar { width: 8px; }
        #log-console::-webkit-scrollbar-thumb { background: #334155; border-radius: 4px; }

        #toast-container { position: fixed; top: 20px; left: 50%; transform: translateX(-50%); z-index: 9999; display: flex; flex-direction: column; gap: 10px;}
        .toast { padding: 10px 20px; border-radius: 6px; color: white; font-weight: 500; font-size: 13px; box-shadow: 0 4px 12px rgba(0,0,0,0.15); opacity: 0; transform: translateY(-20px); transition: all 0.3s cubic-bezier(0.68, -0.55, 0.265, 1.55); display: flex; align-items: center; gap: 8px;}
        .toast.show { opacity: 1; transform: translateY(0); }
        .toast.success { background: #10b981; } .toast.error { background: #ef4444; } .toast.warn { background: #f59e0b; }

        .modal { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(15, 23, 42, 0.6); backdrop-filter: blur(4px); justify-content: center; align-items: center; z-index: 100; }
        .modal-content { background: white; padding: 20px; border-radius: 12px; width: 380px; box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.25); display: flex; flex-direction: column; }
        .modal-content h3 { margin-top: 0; margin-bottom: 12px; color: #0f172a; font-size: 18px; }
        .modal-content p { color: #475569; font-size: 14px; line-height: 1.5; margin-bottom: 16px; word-break: break-all; }
        .input-group { margin-bottom: 14px; }
        .input-group input[type="text"] { width: 100%; padding: 10px; border: 1px solid #cbd5e1; border-radius: 6px; outline: none; margin-top: 6px; font-size: 14px;}
        .input-group input[type="text"]:focus { border-color: var(--primary); box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.15); }
        .modal-actions { display: flex; gap: 10px; margin-top: auto; }
        
        #offline-overlay { display: none; position: fixed; top:0; left:0; width:100%; height:100%; background: #0f172a; color: white; z-index: 99999; flex-direction: column; justify-content: center; align-items: center; text-align: center;}
    </style>
</head>
<body>
    <div id="toast-container"></div>
    
    <div id="offline-overlay">
        <div style="font-size: 50px; margin-bottom: 20px;" id="offline-icon">🔌</div>
        <h2 style="margin:0; font-size: 28px;" id="offline-title">服务端已断开连接</h2>
        <p style="color: #94a3b8; margin-top: 15px;" id="offline-desc">安全自毁程序启动，正在关闭窗口...</p>
    </div>

    <div id="custom-alert-modal" class="modal" style="z-index: 200;">
        <div class="modal-content" style="width: 320px;">
            <h3 id="alert-title">提示</h3>
            <p id="alert-msg"></p>
            <div class="modal-actions">
                <button class="btn-primary" id="btn-alert-ok" style="width: 100%;">我已知晓</button>
            </div>
        </div>
    </div>

    <div id="custom-confirm-modal" class="modal" style="z-index: 200;">
        <div class="modal-content" style="width: 340px;">
            <h3 id="confirm-title">需要确认</h3>
            <p id="confirm-msg" style="white-space: pre-wrap;"></p>
            <div class="modal-actions">
                <button class="btn-success" id="btn-confirm-yes" style="flex: 1;">确认 (Y)</button>
                <button class="btn-danger" id="btn-confirm-no" style="flex: 1;">取消 (N)</button>
            </div>
        </div>
    </div>

    <div id="recreate-modal" class="modal">
        <div class="modal-content" style="width: 360px;">
            <h3>⚠️ 云端仓库未找到</h3>
            <p style="color: #ef4444; font-weight: 600; margin-bottom: 8px;">云端未找到该项目，可能已被删除或尚未上传云端。</p>
            <p style="margin-top: 0;">是否使用本地现有代码在云端重新创建该仓库，并推送所有历史记录？</p>
            <div class="input-group" style="margin-bottom: 15px;">
                <label style="display:flex; align-items:center; gap:8px; cursor:pointer; color:#475569; font-size:13px;">
                    <input type="checkbox" id="recreate-is-private" checked> 重新创建为私有仓库 (Private)
                </label>
            </div>
            <div class="modal-actions">
                <button class="btn-success" id="btn-recreate" style="flex: 2" onclick="submitRecreate()">
                    <div class="spinner"></div><span>重建并推送</span>
                </button>
                <button class="btn-danger" style="flex: 1" onclick="closeRecreateModal()">取消</button>
            </div>
        </div>
    </div>

    <div id="settings-modal" class="modal">
        <div class="modal-content" style="width: 450px;">
            <h3>⚙️ 系统设置</h3>
            <div class="input-group">
                <label style="font-size: 13px; font-weight: 600; color:#334155;">GitHub Personal Access Token</label>
                <p style="font-size: 12px; color: #64748b; margin: 4px 0 8px 0;">用于访问 GitHub API，需具备 repo 权限</p>
                <input type="text" id="github-token-input" placeholder="ghp_xxxxxxxxxxxx" />
                <div style="margin-top: 10px; display: flex; gap: 10px;">
                    <button class="btn-success btn-sm" id="btn-save-token" onclick="saveGitHubToken()">
                        <div class="spinner"></div><span>保存 Token</span>
                    </button>
                    <button class="btn-info btn-sm" onclick="testGitHubToken()">测试连接</button>
                </div>
            </div>
            <div class="input-group">
                <label style="font-size: 13px; font-weight: 600; color:#334155;">V2rayN 启动路径</label>
                <p style="font-size: 12px; color: #64748b; margin: 4px 0 8px 0;">配置 V2rayN.exe 的完整路径，当代理未启动时可自动拉起</p>
                <input type="text" id="v2ray-path-input" placeholder="例如：C:\\Program Files\\v2rayN\\v2rayN.exe" />
                <div style="margin-top: 10px; display: flex; gap: 10px;">
                    <button class="btn-success btn-sm" id="btn-save-v2ray-path" onclick="saveV2rayPath()">
                        <div class="spinner"></div><span>保存路径</span>
                    </button>
                    <button class="btn-info btn-sm" id="btn-start-v2rayn" onclick="startV2rayN()">
                        <div class="spinner"></div><span>启动 V2rayN</span>
                    </button>
                    <button class="btn-secondary btn-sm" onclick="testV2rayPath()">测试路径</button>
                </div>
            </div>
            <div class="modal-actions">
                <button class="btn-primary" style="width: 100%;" onclick="closeSettingsModal()">完成</button>
            </div>
        </div>
    </div>

    <div class="container">
        <div class="header">
            <h1>🚀 GitHub 极简工作台</h1>
            <div class="header-actions">
                <button class="btn-primary" id="btn-fetch" onclick="fetchCloudRepos()">
                    <div class="spinner"></div><span>☁️ 刷新云端</span>
                </button>
                <button class="btn-warning" onclick="showCreateModal()">➕ 新建上云</button>
                <button class="btn-secondary" onclick="showSettingsModal()">⚙️ 设置</button>
            </div>
        </div>

        <div class="grid">
            <div class="card">
                <h3>💻 本地已拉取项目</h3>
                <div id="local-list" class="custom-list"></div>
            </div>

            <div class="card">
                <h3>☁️ 云端仓库列表</h3>
                <div id="cloud-list" class="custom-list"></div>
            </div>
        </div>

        <div class="terminal-container">
            <div class="terminal-header">
                <div class="mac-dot" style="background: #ff5f56;"></div>
                <div class="mac-dot" style="background: #ffbd2e;"></div>
                <div class="mac-dot" style="background: #27c93f;"></div>
                <div class="terminal-title">Python Backend Console</div>
            </div>
            <textarea id="log-console" readonly></textarea>
        </div>
    </div>

    <div id="create-modal" class="modal">
        <div class="modal-content">
            <h3>新建 GitHub 仓库</h3>
            <div class="input-group">
                <label style="font-size: 13px; font-weight: 600; color:#334155;">仓库名称</label>
                <input type="text" id="new-repo-name" placeholder="例如：my-awesome-project" />
            </div>
            <div class="input-group" style="margin-bottom: 0;">
                <label style="display:flex; align-items:center; gap:8px; cursor:pointer; color:#475569; font-size:13px;">
                    <input type="checkbox" id="is-private" checked> 设置为私有仓库 (Private)
                </label>
            </div>
            <div class="modal-actions">
                <button class="btn-success" id="btn-create" style="flex: 2" onclick="submitCreate()">
                    <div class="spinner"></div><span>确定创建</span>
                </button>
                <button class="btn-danger" style="flex: 1" onclick="closeModal()">取消</button>
            </div>
        </div>
    </div>

    <script>
        let cloudRepos = [];
        let localRepos = [];
        let repoToRecreate = null;
        let selectedLocalIndex = -1;
        let selectedCloudIndex = -1;

        const CLOUD_TOLERANCE_MS = 60000; 
        const LOCAL_TOLERANCE_MS = 2000; 
        
        const shaCheckCache = {};

        // 【核心修正】强制时区对齐，防止因系统时区不同导致几小时的巨型误报
        function parseUTC8Time(timeStr) {
            if (!timeStr || timeStr === '缺省') return 0;
            // 将 "YYYY-MM-DD HH:MM:SS" 强转为 ISO 8601 并追加 +08:00
            const isoStr = timeStr.replace(' ', 'T') + '+08:00'; 
            return new Date(isoStr).getTime();
        }

        function customAlert(msg, title="提示") {
            return new Promise(resolve => {
                document.getElementById('alert-title').innerText = title;
                document.getElementById('alert-msg').innerText = msg;
                const modal = document.getElementById('custom-alert-modal');
                const btn = document.getElementById('btn-alert-ok');
                modal.style.display = 'flex';
                btn.onclick = () => { modal.style.display = 'none'; resolve(); };
            });
        }

        function customConfirm(msg, title="确认操作") {
            return new Promise(resolve => {
                document.getElementById('confirm-title').innerText = title;
                document.getElementById('confirm-msg').innerText = msg;
                const modal = document.getElementById('custom-confirm-modal');
                const btnYes = document.getElementById('btn-confirm-yes');
                const btnNo = document.getElementById('btn-confirm-no');
                modal.style.display = 'flex';
                btnYes.onclick = () => { modal.style.display = 'none'; resolve(true); };
                btnNo.onclick = () => { modal.style.display = 'none'; resolve(false); };
            });
        }

        function showToast(msg, type = 'success') {
            const container = document.getElementById('toast-container');
            const toast = document.createElement('div');
            toast.className = `toast ${type}`;
            const icon = type === 'success' ? '✅' : (type === 'error' ? '❌' : '⚠️');
            toast.innerHTML = `${icon} ${msg}`;
            container.appendChild(toast);
            setTimeout(() => toast.classList.add('show'), 10);
            setTimeout(() => {
                toast.classList.remove('show');
                setTimeout(() => toast.remove(), 300);
            }, 3000);
        }

        function log(msg) {
            const consoleArea = document.getElementById('log-console');
            const time = new Date().toLocaleTimeString();
            consoleArea.value += `[${time}] ${msg}\\n`;
            consoleArea.scrollTop = consoleArea.scrollHeight;
        }

        function setLoading(btnId, isLoading) {
            const btn = document.getElementById(btnId);
            if(!btn) return;
            const spinner = btn.querySelector('.spinner');
            const span = btn.querySelector('span');
            btn.disabled = isLoading;
            if(isLoading) {
                if(spinner) spinner.style.display = 'block';
                if(span) span.style.opacity = '0.7';
            } else {
                if(spinner) spinner.style.display = 'none';
                if(span) span.style.opacity = '1';
            }
        }

        function formatGithubTime(isoStr) {
            if(!isoStr) return "缺省";
            const d = new Date(isoStr);
            const y = d.getFullYear();
            const m = String(d.getMonth()+1).padStart(2, '0');
            const day = String(d.getDate()).padStart(2, '0');
            const h = String(d.getHours()).padStart(2, '0');
            const min = String(d.getMinutes()).padStart(2, '0');
            return `${y}-${m}-${day} ${h}:${min}`;
        }

        function applyShaStatus(status, idx) {
            const vsCodeBtn = document.getElementById(`btn-vscode-${idx}`);
            const folderBtn = document.getElementById(`btn-folder-${idx}`);
            const extraDiv = document.getElementById(`meta-extra-${idx}`);
            if (!extraDiv) return;

            if (status === 'same') {
                extraDiv.innerHTML = '<span style="color: #10b981; font-weight: bold; display: block; margin-top: 5px;">✅ 已经是最新状态</span>';
                if (vsCodeBtn) vsCodeBtn.disabled = false;
                if (folderBtn) folderBtn.disabled = false;
            } else if (status === 'cloud_newer') {
                extraDiv.innerHTML = '<span style="color: #ef4444; font-weight: bold; display: block; margin-top: 5px;">⚠️ 本地信息已不是最新版本，请同步云端数据</span>';
                if (vsCodeBtn) vsCodeBtn.disabled = true;
                if (folderBtn) folderBtn.disabled = true;
            } else if (status === 'local_newer') {
                extraDiv.innerHTML = '<span style="color: #10b981; font-weight: bold; display: block; margin-top: 5px;">💡 本地版本较新，建议推送到云端</span>';
                if (vsCodeBtn) vsCodeBtn.disabled = false;
                if (folderBtn) folderBtn.disabled = false;
            }
        }

        // 【核心修正】更加完善的状态核对中心，防止“空保存穿透”
        async function updateRepoStatuses() {
            for (let i = 0; i < localRepos.length; i++) {
                const r = localRepos[i];
                const cloudRepo = cloudRepos.find(c => c.name === r.name);
                const extraDiv = document.getElementById(`meta-extra-${i}`);

                if (extraDiv) extraDiv.innerHTML = '';

                if (cloudRepo && r.local_mtime !== '缺省') {
                    const localTime = parseUTC8Time(r.local_mtime);
                    const syncTime = parseUTC8Time(r.last_sync);
                    
                    // 修复 Github 假更新：使用 pushed_at (真实代码提交时间) 替代 updated_at (Star/Issue 时间)
                    const cloudTimeStr = cloudRepo.pushed_at || cloudRepo.updated_at;
                    const cloudTime = new Date(cloudTimeStr).getTime();

                    let determinedStatus = null;
                    let needsShaCheck = false; // 是否需要进行精确防误报核验

                    if (syncTime > 0) {
                        if (cloudTime > syncTime + CLOUD_TOLERANCE_MS || localTime > syncTime + LOCAL_TOLERANCE_MS) {
                            // 时间超出了上次同步锚点，可能有人写了代码，也可能是空保存。交给后台精确查验。
                            needsShaCheck = true;
                        } else {
                            // 一切都在锚点内，绝对是没碰过的
                            determinedStatus = 'same';
                        }
                    } else {
                        // 首次运行或无锚点记录，强行核对一次
                        needsShaCheck = true;
                    }

                    if (needsShaCheck) {
                        // 利用 mtime 作为缓存锁，mtime不变更就不会重复耗费 API 请求
                        const cacheKey = `${r.name}_${r.local_mtime}_${cloudTimeStr}`;
                        if (shaCheckCache[cacheKey]) {
                            if (shaCheckCache[cacheKey] !== 'pending') {
                                applyShaStatus(shaCheckCache[cacheKey], i);
                            }
                        } else {
                            shaCheckCache[cacheKey] = 'pending';
                            if (extraDiv) extraDiv.innerHTML = '<span style="color: #64748b; font-size: 11px; display: block; margin-top: 5px;">🔄 正在精准比对...</span>';
                            try {
                                const res = await fetch('/api/sha_compare', {
                                    method: 'POST',
                                    headers: {'Content-Type': 'application/json'},
                                    body: JSON.stringify({name: r.name, url: r.repo_url})
                                });
                                const data = await res.json();
                                if (data.status && data.status !== 'error') {
                                    shaCheckCache[cacheKey] = data.status;
                                    applyShaStatus(data.status, i);
                                } else {
                                    delete shaCheckCache[cacheKey];
                                    if (extraDiv) extraDiv.innerHTML = '';
                                }
                            } catch(e) {
                                delete shaCheckCache[cacheKey];
                                if (extraDiv) extraDiv.innerHTML = '';
                            }
                        }
                    } else {
                        applyShaStatus(determinedStatus, i);
                    }
                } else if (!cloudRepo) {
                    if (extraDiv) {
                        extraDiv.innerHTML = '<span style="color: #f59e0b; font-weight: bold; display: block; margin-top: 5px;">⚠️ 云端未找到该项目，可能已被删除或未上云</span>';
                    }
                }
            }
        }

        async function apiCall(endpoint, method='POST', body=null) {
            try {
                const options = { method: method, headers: {'Content-Type': 'application/json'} };
                if (body) options.body = JSON.stringify(body);
                const res = await fetch(endpoint, options);
                const data = await res.json();
                if (data.log) log(data.log);
                return data;
            } catch (err) {
                return {status: 'error'};
            }
        }

        const evtSource = new EventSource('/api/stream');
        evtSource.onerror = function() {
            document.getElementById('offline-overlay').style.display = 'flex';
            setTimeout(() => {
                try { window.close(); } catch(e) {}
            }, 100);
        };

        async function silentRefreshLocal() {
            try {
                const res = await fetch('/api/local_repos');
                if(!res.ok) return;
                const data = await res.json();
                if(data.repos) {
                    let needsFullRender = false;
                    if(data.repos.length !== localRepos.length) {
                        needsFullRender = true;
                    } else {
                        for(let i=0; i<data.repos.length; i++) {
                            if(data.repos[i].name !== localRepos[i].name) {
                                needsFullRender = true;
                                break;
                            }
                        }
                    }

                    if(needsFullRender) {
                        const oldSelectedName = selectedLocalIndex >= 0 ? localRepos[selectedLocalIndex].name : null;
                        await loadLocalRepos(); 
                        if(oldSelectedName) {
                            const newIdx = localRepos.findIndex(r => r.name === oldSelectedName);
                            if(newIdx !== -1) {
                                selectedLocalIndex = newIdx;
                                document.getElementById('local-list').children[newIdx].classList.add('active');
                            }
                        }
                    } else {
                        localRepos = data.repos;
                        data.repos.forEach((r, idx) => {
                            const mtimeSpan = document.getElementById(`mtime-${idx}`);
                            const syncSpan = document.getElementById(`sync-${idx}`);
                            if(mtimeSpan && mtimeSpan.innerHTML !== `🕒 <b>最后修改:</b> ${r.local_mtime}`) {
                                mtimeSpan.innerHTML = `🕒 <b>最后修改:</b> ${r.local_mtime}`;
                            }
                            if(syncSpan && syncSpan.innerHTML !== `🔄 <b>最后同步:</b> ${r.last_sync}`) {
                                syncSpan.innerHTML = `🔄 <b>最后同步:</b> ${r.last_sync}`;
                            }
                        });
                        await updateRepoStatuses();
                    }
                }
            } catch(e) {}
        }
        setInterval(silentRefreshLocal, 3000);

        async function checkInitInfo() {
            const res = await apiCall('/api/init_info', 'GET');
            if(res && res.v2rayN_running === false) {
                if (res.v2ray_path) {
                    const shouldStart = await customConfirm("检测到后台 V2rayN 代理程序未运行！\\n\\n由于系统已配置强制通过 10808 端口代理，若没有对应的代理软件接收流量，获取云端数据可能会一直卡死或报错超时。\\n\\n是否自动启动 V2rayN？", "⚠️ 代理未运行警告");
                    if (shouldStart) {
                        const startRes = await apiCall('/api/start_v2rayn', 'POST');
                        if (startRes.status === 'success') {
                            showToast("V2rayN 已启动", "success");
                        } else {
                            showToast(startRes.msg || "启动失败", "error");
                        }
                    }
                } else {
                    await customAlert("检测到后台 V2rayN 代理程序未运行！\\n\\n由于系统已配置强制通过 10808 端口代理，若没有对应的代理软件接收流量，获取云端数据可能会一直卡死或报错超时。\\n\\n请前往「设置」配置 V2rayN 启动路径，或手动启动 V2rayN。", "⚠️ 代理未运行警告");
                }
            }
        }

        async function loadLocalRepos() {
            const data = await apiCall('/api/local_repos', 'GET');
            const container = document.getElementById('local-list');
            container.innerHTML = '';
            
            if(data.repos && data.repos.length > 0) {
                localRepos = data.repos;
                localRepos.forEach((r, idx) => {
                    const div = document.createElement('div');
                    div.className = 'list-item';
                    div.innerHTML = `
                        <div class="item-header">
                            <span class="item-name">📦 ${r.name}</span>
                            <span class="badge">${r.origin}</span>
                        </div>
                        <div class="item-meta">
                            <span id="mtime-${idx}">🕒 <b>最后修改:</b> ${r.local_mtime}</span>
                            <span id="sync-${idx}">🔄 <b>最后同步:</b> ${r.last_sync}</span>
                            <div id="meta-extra-${idx}" style="flex-basis: 100%;"></div>
                        </div>
                        <div class="item-actions">
                            <button id="btn-sync-${idx}" class="btn-success btn-sm" onclick="syncProject(${idx}, event)"><div class="spinner"></div><span>智能比对同步</span></button>
                            <button id="btn-vscode-${idx}" class="btn-info btn-sm" onclick="openVsCode(${idx}, event)"><div class="spinner"></div><span>VS Code</span></button>
                            <button id="btn-folder-${idx}" class="btn-secondary btn-sm" onclick="openFolder(${idx}, event)"><div class="spinner"></div><span>文件夹</span></button>
                            <button id="btn-del-${idx}" class="btn-danger btn-sm btn-right" onclick="deleteLocal(${idx}, event)"><div class="spinner"></div><span>彻底删除</span></button>
                        </div>
                    `;
                    div.onclick = (e) => {
                        if(e.target.tagName === 'BUTTON' || e.target.closest('button')) return;
                        Array.from(container.children).forEach(c => c.classList.remove('active'));
                        div.classList.add('active');
                        selectedLocalIndex = idx;
                    };
                    container.appendChild(div);
                });
                await updateRepoStatuses();
            } else {
                container.innerHTML = '<div style="padding:20px; text-align:center; color:#94a3b8; font-size:13px;">暂无本地项目</div>';
            }
        }

        async function fetchCloudRepos() {
            setLoading('btn-fetch', true);
            log("正在向 GitHub 请求云端列表...");
            const data = await apiCall('/api/fetch_cloud', 'POST');
            const container = document.getElementById('cloud-list');
            container.innerHTML = '';

            if (data.status === 'success') {
                cloudRepos = data.repos;
                if(cloudRepos.length === 0) {
                    container.innerHTML = '<div style="padding:20px; text-align:center; color:#94a3b8; font-size:13px;">云端账号下没有项目</div>';
                } else {
                    cloudRepos.forEach((r, idx) => {
                        const div = document.createElement('div');
                        div.className = 'list-item';
                        div.innerHTML = `
                            <div class="item-header">
                                <span class="item-name">☁️ ${r.name}</span>
                                ${r.private ? '<span class="badge" style="background:#fef08a;color:#854d0e;">私有</span>' : ''}
                            </div>
                            <div class="item-meta">
                                <span>🕒 <b>云端最后修改:</b> ${formatGithubTime(r.pushed_at || r.updated_at)}</span>
                            </div>
                            <div class="item-actions">
                                <button id="btn-pull-${idx}" class="btn-primary btn-sm" onclick="pullProject(${idx}, event)"><div class="spinner"></div><span>⬇️ 拉取到本地</span></button>
                                <button class="btn-secondary btn-sm btn-right" onclick="openBrowser(${idx}, event)">🌐 网站主页</button>
                            </div>
                        `;
                        div.onclick = (e) => {
                            if(e.target.tagName === 'BUTTON' || e.target.closest('button')) return;
                            Array.from(container.children).forEach(c => c.classList.remove('active'));
                            div.classList.add('active');
                            selectedCloudIndex = idx;
                        };
                        container.appendChild(div);
                    });
                }
                showToast("云端列表已刷新");
                await updateRepoStatuses();
            } else {
                container.innerHTML = '<div style="padding:20px; text-align:center; color:#ef4444; font-size:13px;">获取失败，请检查 Token</div>';
                showToast("获取云端列表失败", "error");
            }
            setLoading('btn-fetch', false);
        }

        async function pullProject(idx, event) {
            if(event) event.stopPropagation();
            const btnId = `btn-pull-${idx}`;
            setLoading(btnId, true);
            const repo = cloudRepos[idx];
            log(`开始拉取: ${repo.name}...`);
            const res = await apiCall('/api/pull', 'POST', {name: repo.name, url: repo.clone_url});
            if(res.log && res.log.includes('✅')) showToast(`已成功拉取 ${repo.name}`);
            await loadLocalRepos();
            setLoading(btnId, false);
        }

        async function syncProject(idx, event) {
            if(event) event.stopPropagation();
            const btnId = `btn-sync-${idx}`;
            setLoading(btnId, true);
            const repo = localRepos[idx];
            log(`开始智能分析 [${repo.name}] ...`);
            
            const checkData = await apiCall('/api/sync_check', 'POST', {name: repo.name, url: repo.repo_url});
            
            if (checkData.status === 'not_found') {
                setLoading(btnId, false);
                repoToRecreate = repo;
                document.getElementById('recreate-is-private').checked = true;
                document.getElementById('recreate-modal').style.display = 'flex';
                return;
            } else if (checkData.status === 'need_push') {
                if(await customConfirm(checkData.msg, "推送确认")) {
                    const p = await apiCall('/api/push', 'POST', {name: repo.name, url: repo.repo_url});
                    if(p.log && p.log.includes('✅')) { 
                        showToast("推送成功"); 
                        await loadLocalRepos(); 
                        await new Promise(resolve => setTimeout(resolve, 5000));
                        await fetchCloudRepos(); 
                    }
                } else { log("已取消推送。"); }
            } else if (checkData.status === 'need_pull') {
                if(await customConfirm(checkData.msg, "覆盖确认")) {
                    const p = await apiCall('/api/pull_update', 'POST', {name: repo.name, url: repo.repo_url});
                    if(p.log && p.log.includes('✅')) { 
                        showToast("拉取覆盖成功"); 
                        await loadLocalRepos(); 
                        await fetchCloudRepos(); 
                    }
                } else { log("已取消拉取。"); }
            } else if (checkData.status === 'ok') {
                showToast("已经是最新状态", "success");
                await loadLocalRepos();
            }
            setLoading(btnId, false);
        }

        async function openVsCode(idx, event) {
            if(event) event.stopPropagation();
            const btnId = `btn-vscode-${idx}`;
            setLoading(btnId, true);
            const repo = localRepos[idx];
            await apiCall('/api/vscode', 'POST', {name: repo.name});
            setLoading(btnId, false);
        }

        async function openFolder(idx, event) {
            if(event) event.stopPropagation();
            const btnId = `btn-folder-${idx}`;
            setLoading(btnId, true);
            const repo = localRepos[idx];
            await apiCall('/api/open_folder', 'POST', {name: repo.name});
            setLoading(btnId, false);
        }

        function openBrowser(idx, event) {
            if(event) event.stopPropagation();
            const repo = cloudRepos[idx];
            window.open(repo.html_url, '_blank');
            log(`已在浏览器中打开: ${repo.html_url}`);
        }

        async function deleteLocal(idx, event) {
            if(event) event.stopPropagation();
            const repo = localRepos[idx];
            if(await customConfirm(`警告：确定彻底删除本地的 [${repo.name}] 项目文件夹吗？\\n\\n该操作无法撤销，但不会影响 GitHub 云端代码。`, "⚠️ 危险操作确认")) {
                const btnId = `btn-del-${idx}`;
                setLoading(btnId, true);
                const res = await apiCall('/api/delete_local', 'POST', {name: repo.name});
                if(res.log && res.log.includes('✅')) showToast(`已彻底删除 ${repo.name}`);
                await loadLocalRepos();
            }
        }

        function closeRecreateModal() {
            document.getElementById('recreate-modal').style.display = 'none';
            repoToRecreate = null;
        }

        function showSettingsModal() {
            document.getElementById('settings-modal').style.display = 'flex';
            loadGitHubToken();
            loadV2rayPath();
        }

        function closeSettingsModal() {
            document.getElementById('settings-modal').style.display = 'none';
        }

        async function loadGitHubToken() {
            const res = await apiCall('/api/github_token', 'GET');
            if (res && res.masked !== undefined) {
                document.getElementById('github-token-input').placeholder = res.masked || 'ghp_xxxxxxxxxxxx';
                document.getElementById('github-token-input').value = '';
            }
        }

        async function saveGitHubToken() {
            const token = document.getElementById('github-token-input').value.trim();
            if (!token) {
                await customAlert("请输入 Token", "提示");
                return;
            }
            setLoading('btn-save-token', true);
            const res = await apiCall('/api/github_token', 'POST', {token: token});
            if (res.status === 'success') {
                showToast("Token 已保存", "success");
                loadGitHubToken();
            } else {
                showToast(res.msg || "保存失败", "error");
            }
            setLoading('btn-save-token', false);
        }

        async function testGitHubToken() {
            const token = document.getElementById('github-token-input').value.trim();
            if (!token) {
                await customAlert("请输入要测试的 Token", "提示");
                return;
            }
            const res = await apiCall('/api/test_github_token', 'POST', {token: token});
            if (res.status === 'success') {
                await customAlert(res.msg, "测试成功");
            } else {
                await customAlert(res.msg || "测试失败", "测试失败");
            }
        }

        async function loadV2rayPath() {
            const res = await apiCall('/api/v2ray_path', 'GET');
            if (res && res.path !== undefined) {
                document.getElementById('v2ray-path-input').value = res.path;
            }
        }

        async function saveV2rayPath() {
            const path = document.getElementById('v2ray-path-input').value.trim();
            setLoading('btn-save-v2ray-path', true);
            const res = await apiCall('/api/v2ray_path', 'POST', {path: path});
            if (res.status === 'success') {
                showToast("路径已保存", "success");
            } else {
                showToast(res.msg || "保存失败", "error");
            }
            setLoading('btn-save-v2ray-path', false);
        }

        async function startV2rayN() {
            setLoading('btn-start-v2rayn', true);
            const res = await apiCall('/api/start_v2rayn', 'POST');
            if (res.status === 'success') {
                showToast("V2rayN 启动成功", "success");
            } else {
                showToast(res.msg || "启动失败", "error");
            }
            setLoading('btn-start-v2rayn', false);
        }

        async function testV2rayPath() {
            const path = document.getElementById('v2ray-path-input').value.trim();
            if (!path) {
                await customAlert("请先输入路径", "提示");
                return;
            }
            const res = await apiCall('/api/test_v2ray_path', 'POST', {path: path});
            if (res.status === 'success') {
                await customAlert("路径有效！", "测试成功");
            } else {
                await customAlert(res.msg || "路径无效", "测试失败");
            }
        }

        async function submitRecreate() {
            if (!repoToRecreate) return;
            const isPrivate = document.getElementById('recreate-is-private').checked;
            setLoading('btn-recreate', true);
            log(`准备重新创建并推送项目: ${repoToRecreate.name}...`);
            
            const res = await apiCall('/api/recreate_push', 'POST', {
                name: repoToRecreate.name, 
                is_private: isPrivate
            });
            
            if(res.log && res.log.includes('✅')) {
                showToast(`项目 ${repoToRecreate.name} 云端重建成功`);
                closeRecreateModal();
                await loadLocalRepos();
                await fetchCloudRepos();
            }
            setLoading('btn-recreate', false);
        }

        function showCreateModal() { 
            document.getElementById('new-repo-name').value = '';
            document.getElementById('create-modal').style.display = 'flex'; 
        }
        function closeModal() { document.getElementById('create-modal').style.display = 'none'; }
        
        async function submitCreate() {
            const name = document.getElementById('new-repo-name').value.trim();
            const isPrivate = document.getElementById('is-private').checked;
            if(!name) return await customAlert("仓库名称不能为空！", "验证失败");
            
            setLoading('btn-create', true);
            log(`准备创建新项目: ${name}...`);
            const res = await apiCall('/api/create', 'POST', {name: name, is_private: isPrivate});
            if(res.log && res.log.includes('✅')) {
                showToast(`新项目 ${name} 创建成功`);
                closeModal();
                await loadLocalRepos();
                await fetchCloudRepos();
            }
            setLoading('btn-create', false);
        }

        window.onload = async () => {
            log("系统内核已就绪，正在初始化...");
            await checkInitInfo();
            await Promise.all([loadLocalRepos(), fetchCloudRepos()]);
            log("初始化完成，所有功能可用。");
        };
    </script>
</body>
</html>
"""

app = Flask(__name__)

def is_v2rayn_running():
    if os.name == 'nt':
        try:
            result = subprocess.run(["tasklist", "/FI", "IMAGENAME eq v2rayn.exe"], capture_output=True, text=True, creationflags=0x08000000)
            if "v2rayN" in result.stdout or "v2rayn.exe" in result.stdout.lower():
                return True
            return False
        except Exception:
            return True
    return True

def is_ignored(item_str):
    if any(item_str.endswith(ext) for ext in IGNORE_PATTERNS): return True
    if any(name in item_str for name in IGNORE_NAMES): return True
    return False

def get_real_changes(path):
    status = porcelain.status(path)
    real_changes = []
    deleted_files = []
    for item in list(status.untracked) + list(status.unstaged):
        item_str = item.decode('utf-8', 'ignore') if isinstance(item, bytes) else item
        if is_ignored(item_str): continue
        if not os.path.exists(os.path.join(path, item_str)):
            deleted_files.append(item)
        else:
            real_changes.append(item)
    staged_files = [p for paths in status.staged.values() for p in paths]
    return real_changes, deleted_files, staged_files

def get_project_mtime(p_path):
    tz_utc8 = timezone(timedelta(hours=8))
    latest_ts = 0
    try:
        for root, dirs, files in os.walk(p_path):
            dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
            for f in files:
                if any(f.endswith(ext) for ext in IGNORE_PATTERNS) or f in IGNORE_NAMES: 
                    continue
                fp = os.path.join(root, f)
                try:
                    m = os.path.getmtime(fp)
                    if m > latest_ts: 
                        latest_ts = m
                except:
                    pass
    except Exception:
        pass

    commit_ts = 0
    try:
        repo = Repo(p_path)
        commit_ts = repo[repo.head()].commit_time
        repo.close()
    except Exception:
        pass
    
    final_ts = max(latest_ts, commit_ts)
    if final_ts == 0: 
        return "缺省"
    return datetime.fromtimestamp(final_ts, tz=timezone.utc).astimezone(tz_utc8).strftime('%Y-%m-%d %H:%M:%S')

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/stream')
def api_stream():
    def generate():
        try:
            while True:
                yield "data: ping\n\n"
                time.sleep(1)
        except GeneratorExit:
            pass
    return Response(generate(), mimetype='text/event-stream')

@app.route('/api/ping', methods=['GET'])
def api_ping():
    return jsonify({"status": "ok"})

@app.route('/api/init_info', methods=['GET'])
def api_init_info():
    return jsonify({"v2rayN_running": is_v2rayn_running(), "v2ray_path": get_v2ray_path()})

@app.route('/api/github_token', methods=['GET', 'POST'])
def api_github_token():
    if request.method == 'GET':
        token = get_token()
        masked = token[:4] + '****' + token[-4:] if len(token) > 8 else token
        return jsonify({"token": token, "masked": masked})
    else:
        data = request.json
        token = data.get('token', '').strip()
        save_token(token)
        return jsonify({"status": "success", "msg": "Token 已保存"})

@app.route('/api/test_github_token', methods=['POST'])
def api_test_github_token():
    data = request.json
    token = data.get('token', '').strip()
    if not token:
        return jsonify({"status": "error", "msg": "Token 不能为空"})
    try:
        url = "https://api.github.com/user"
        req = urllib.request.Request(url, headers={
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json"
        })
        with urllib.request.urlopen(req) as res:
            user_data = json.loads(res.read().decode())
            return jsonify({"status": "success", "msg": f"连接成功！用户: {user_data.get('login', 'unknown')}"})
    except urllib.error.HTTPError as e:
        if e.code == 401:
            return jsonify({"status": "error", "msg": "Token 无效或已过期"})
        return jsonify({"status": "error", "msg": f"请求失败: HTTP {e.code}"})
    except Exception as e:
        return jsonify({"status": "error", "msg": f"连接失败: {str(e)}"})

@app.route('/api/v2ray_path', methods=['GET', 'POST'])
def api_v2ray_path():
    if request.method == 'GET':
        return jsonify({"path": get_v2ray_path()})
    else:
        data = request.json
        path = data.get('path', '').strip()
        save_v2ray_path(path)
        return jsonify({"status": "success", "msg": "路径已保存"})

@app.route('/api/start_v2rayn', methods=['POST'])
def api_start_v2rayn():
    result = start_v2rayn()
    return jsonify(result)

@app.route('/api/test_v2ray_path', methods=['POST'])
def api_test_v2ray_path():
    data = request.json
    path = data.get('path', '').strip()
    if not path:
        return jsonify({"status": "error", "msg": "路径不能为空"})
    if os.path.exists(path):
        if path.lower().endswith('.exe'):
            return jsonify({"status": "success", "msg": "路径有效"})
        else:
            return jsonify({"status": "error", "msg": "文件不是 .exe 格式"})
    else:
        return jsonify({"status": "error", "msg": "路径不存在"})

@app.route('/api/local_repos', methods=['GET'])
def api_local_repos():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT name, origin, repo_url, last_sync FROM projects")
    rows = cursor.fetchall()
    conn.close()
    
    valid_repos = []
    
    for r in rows:
        p_name, origin, repo_url, last_sync = r[0], r[1], r[2], r[3]
        p_path = os.path.join(BASE_DIR, p_name)
        if os.path.exists(p_path):
            local_mtime = get_project_mtime(p_path)
            valid_repos.append({
                "name": p_name, 
                "origin": origin, 
                "repo_url": repo_url,
                "last_sync": last_sync if last_sync else "缺省",
                "local_mtime": local_mtime
            })
    return jsonify({"repos": valid_repos})

@app.route('/api/fetch_cloud', methods=['POST'])
def api_fetch_cloud():
    token = get_token()
    ts = int(time.time() * 1000)
    url = f"https://api.github.com/user/repos?per_page=100&sort=updated&t={ts}"
    
    headers = {
        "Authorization": f"token {token}", 
        "Accept": "application/vnd.github.v3+json",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache"
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req) as res:
            repos = json.loads(res.read().decode())
            return jsonify({"status": "success", "repos": repos, "log": f"✅ 成功加载了 {len(repos)} 个云端项目。"})
    except Exception as e:
        return jsonify({"status": "error", "log": f"❌ 获取云端失败: {str(e)}"})

@app.route('/api/sha_compare', methods=['POST'])
def api_sha_compare():
    data = request.json
    p_name = data['name']
    p_url = data['url']
    p_path = os.path.join(BASE_DIR, p_name)
    token = get_token()

    try:
        real_changes, deleted_files, staged_files = get_real_changes(p_path)
        if real_changes or deleted_files or staged_files:
            return jsonify({"status": "local_newer"})

        ts = int(time.time() * 1000)
        if "github.com" not in p_url:
            return jsonify({"status": "error"})
            
        api_url = f"https://api.github.com/repos/{p_url.split('github.com/')[-1].replace('.git','')}/commits?per_page=1&t={ts}"
        req = urllib.request.Request(api_url, headers={"Authorization": f"token {token}", "Cache-Control": "no-cache"})
        
        try:
            with urllib.request.urlopen(req) as res:
                commits_data = json.loads(res.read().decode())
                remote_sha = commits_data[0]['sha'] if commits_data else None
                if commits_data:
                    remote_date_str = commits_data[0]['commit']['committer']['date']
        except urllib.error.HTTPError:
            return jsonify({"status": "error"})

        if not remote_sha:
            return jsonify({"status": "same"})

        tz_utc8 = timezone(timedelta(hours=8))
        r = Repo(p_path)
        local_sha = r.head().decode('utf-8')
        local_time = datetime.fromtimestamp(r[local_sha.encode()].commit_time, tz=timezone.utc).astimezone(tz_utc8)
        r.close()
        remote_time = datetime.strptime(remote_date_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).astimezone(tz_utc8)

        if local_sha == remote_sha:
            return jsonify({"status": "same"})
        else:
            if remote_time > local_time:
                return jsonify({"status": "cloud_newer"})
            else:
                return jsonify({"status": "local_newer"})
    except Exception:
        return jsonify({"status": "error"})

@app.route('/api/pull', methods=['POST'])
def api_pull():
    data = request.json
    name = data['name']
    clone_url = data['url']
    target_path = os.path.join(BASE_DIR, name)
    token = get_token()
    auth_url = clone_url.replace("https://", f"https://{token}@")

    if os.path.exists(target_path):
        return jsonify({"log": f"⚠️ 目录 {name} 已存在，跳过拉取。"})
    try:
        porcelain.clone(auth_url, target_path)
        
        now_str = datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("INSERT INTO projects (name, path, repo_url, origin, last_sync) VALUES (?, ?, ?, ?, ?)", 
                  (name, target_path, clone_url, "Cloud", now_str))
        conn.commit()
        conn.close()
        
        return jsonify({"log": f"✅ {name} 已成功拉取到本地。"})
    except Exception as e:
        return jsonify({"log": f"❌ 拉取失败: {str(e)}"})

@app.route('/api/sync_check', methods=['POST'])
def api_sync_check():
    data = request.json
    p_name = data['name']
    p_url = data['url']
    p_path = os.path.join(BASE_DIR, p_name)
    token = get_token()

    try:
        ts = int(time.time() * 1000)
        api_url = f"https://api.github.com/repos/{p_url.split('github.com/')[-1].replace('.git','')}/commits?per_page=1&t={ts}"
        req = urllib.request.Request(api_url, headers={"Authorization": f"token {token}", "Cache-Control": "no-cache"})
        
        try:
            with urllib.request.urlopen(req) as res:
                commits_data = json.loads(res.read().decode())
                remote_sha = commits_data[0]['sha'] if commits_data else None
                if commits_data:
                    remote_date_str = commits_data[0]['commit']['committer']['date']
        except urllib.error.HTTPError as e:
            if e.code == 409:
                remote_sha = None 
            elif e.code == 404:
                return jsonify({"status": "not_found", "log": "❌ 智能检测：云端未找到该项目，可能已被删除或未上传云端。"})
            else:
                raise e

        real_changes, deleted_files, staged_files = get_real_changes(p_path)
        if real_changes or deleted_files or staged_files:
            return jsonify({"status": "need_push", "msg": "检测到本地代码有未暂存的修改，是否将本地代码推送到云端？", "log": "⚡ 发现本地未提交的修改。"})

        tz_utc8 = timezone(timedelta(hours=8))
        r = Repo(p_path)
        local_sha = r.head().decode('utf-8')
        local_time = datetime.fromtimestamp(r[local_sha.encode()].commit_time, tz=timezone.utc).astimezone(tz_utc8)
        r.close()

        if not remote_sha:
            return jsonify({"status": "ok", "log": "云端仓库为空，等待推送。"})
            
        remote_time = datetime.strptime(remote_date_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).astimezone(tz_utc8)

        if local_sha == remote_sha:
            update_last_sync(p_name)
            return jsonify({"status": "ok", "log": "🙌 本地与云端完全一致，无需同步。"})

        log_str = f"本地最后提交: {local_time.strftime('%m-%d %H:%M')} | 云端最后提交: {remote_time.strftime('%m-%d %H:%M')}"
        
        if remote_time > local_time:
            return jsonify({
                "status": "need_pull", 
                "msg": "检测到云端最后修改时间较新！\n即将从云端拉取最新数据并覆盖本地数据，是否确认执行？", 
                "log": f"{log_str}\n⚠️ 云端数据较新，需要覆盖本地。"
            })
        elif local_time > remote_time:
             return jsonify({
                 "status": "need_push", 
                 "msg": "检测到本地修改时间较新！\n是否将本地最新代码推送到云端？", 
                 "log": f"{log_str}\n💡 本地数据较新，建议推送。"
             })
        
        update_last_sync(p_name)
        return jsonify({"status": "ok", "log": log_str + "\\n两端一致。"})
    except Exception as e:
        return jsonify({"status": "error", "log": f"❌ 同步比对失败: {str(e)}"})

@app.route('/api/recreate_push', methods=['POST'])
def api_recreate_push():
    data = request.json
    name = data['name']
    is_private = data['is_private']
    token = get_token()
    target_path = os.path.join(BASE_DIR, name)

    try:
        api_url = "https://api.github.com/user/repos"
        payload = json.dumps({"name": name, "private": is_private}).encode()
        req = urllib.request.Request(api_url, data=payload, headers={"Authorization": f"token {token}"})
        with urllib.request.urlopen(req) as res:
            repo_info = json.loads(res.read().decode())
            clone_url = repo_info['clone_url']

        auth_url = clone_url.replace("https://", f"https://{token}@")
        
        default_committer = b"GitHubAutoTool <tool@localhost>"
        real_changes, deleted_files, _ = get_real_changes(target_path)
        if real_changes: porcelain.add(target_path, paths=real_changes)
        if deleted_files: porcelain.add(target_path, paths=deleted_files)
        if real_changes or deleted_files:
            porcelain.commit(target_path, b"Automated Sync Commit Before Recreate", author=default_committer, committer=default_committer)

        try:
            current_branch = porcelain.active_branch(target_path)
            refspec = b"refs/heads/" + current_branch + b":refs/heads/" + current_branch
        except:
            refspec = b"HEAD:refs/heads/main"

        porcelain.push(target_path, auth_url, refspecs=[refspec])

        now_str = datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("UPDATE projects SET repo_url = ?, origin = 'Local+Cloud', last_sync = ? WHERE name = ?", (clone_url, now_str, name))
        conn.commit()
        conn.close()

        return jsonify({"log": f"✅ 成功：项目 {name} 已在云端重建并推送所有数据。"})
    except Exception as e:
        return jsonify({"log": f"❌ 重建项目失败: {str(e)}"})

@app.route('/api/push', methods=['POST'])
def api_push():
    data = request.json
    name = data['name']
    path = os.path.join(BASE_DIR, name)
    auth_url = data['url'].replace("https://", f"https://{get_token()}@")
    default_committer = b"GitHubAutoTool <tool@localhost>"
    
    try:
        real_changes, deleted_files, _ = get_real_changes(path)
        if real_changes: porcelain.add(path, paths=real_changes)
        if deleted_files: porcelain.add(path, paths=deleted_files)

        if real_changes or deleted_files:
            porcelain.commit(path, b"Automated Sync Commit", author=default_committer, committer=default_committer)
        
        try:
            current_branch = porcelain.active_branch(path)
            refspec = b"refs/heads/" + current_branch + b":refs/heads/" + current_branch
        except:
            refspec = b"HEAD:refs/heads/main"

        porcelain.push(path, auth_url, refspecs=[refspec])
        
        pull_msg = ""
        try:
            porcelain.pull(path, auth_url)
            pull_msg = "并已自动拉取同步最新状态。"
        except Exception as pull_e:
            pull_msg = f"但自动拉取遇到问题: {str(pull_e)}"

        update_last_sync(name)
        return jsonify({"log": f"✅ 推送成功！{pull_msg}"})
    except Exception as e:
        return jsonify({"log": f"❌ 推送失败: {str(e)}"})

@app.route('/api/pull_update', methods=['POST'])
def api_pull_update():
    data = request.json
    name = data['name']
    path = os.path.join(BASE_DIR, name)
    auth_url = data['url'].replace("https://", f"https://{get_token()}@")
    try:
        porcelain.pull(path, auth_url)
        update_last_sync(name)
        return jsonify({"log": "✅ 拉取成功，本地已同步为云端最新代码。"})
    except Exception as e:
        return jsonify({"log": f"❌ 拉取更新失败: {str(e)}"})

@app.route('/api/vscode', methods=['POST'])
def api_vscode():
    path = os.path.join(BASE_DIR, request.json['name'])
    if not os.path.exists(path):
        return jsonify({"log": "❌ 启动失败：找不到本地项目文件夹。"})
    try:
        if os.name == 'nt':
            subprocess.Popen(f'code "{path}"', shell=True)
        else:
            subprocess.Popen(["code", path])
        return jsonify({"log": "✅ 已启动 VS Code。"})
    except Exception as e:
        return jsonify({"log": f"❌ 启动失败: {str(e)}"})

@app.route('/api/open_folder', methods=['POST'])
def api_open_folder():
    path = os.path.join(BASE_DIR, request.json['name'])
    if not os.path.exists(path):
        return jsonify({"log": "❌ 打开失败：找不到本地项目文件夹。"})
    try:
        if sys.platform == 'win32':
            os.startfile(path)
        elif sys.platform == 'darwin':
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
        return jsonify({"log": "✅ 已打开本地文件夹。"})
    except Exception as e:
        return jsonify({"log": f"❌ 打开失败: {str(e)}"})

@app.route('/api/delete_local', methods=['POST'])
def api_delete_local():
    name = request.json['name']
    path = os.path.join(BASE_DIR, name)
    try:
        if os.path.exists(path):
            def remove_readonly(func, p, exc_info):
                os.chmod(p, stat.S_IWRITE)
                func(p)
            try:
                shutil.rmtree(path, onerror=remove_readonly)
            except PermissionError:
                if os.name == 'nt':
                    temp_dir = os.path.join(BASE_DIR, '_empty_temp_del')
                    os.makedirs(temp_dir, exist_ok=True)
                    subprocess.run(['robocopy', temp_dir, path, '/MIR', '/NFL', '/NDL', '/NJH', '/NJS', '/NC', '/NS', '/NP'], 
                                 capture_output=True, creationflags=0x08000000)
                    shutil.rmtree(temp_dir, ignore_errors=True)
                    time.sleep(0.5)
                    if os.path.exists(path):
                        shutil.rmtree(path, ignore_errors=True)
                else:
                    raise
        
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("DELETE FROM projects WHERE name = ?", (name,))
        conn.commit()
        conn.close()
        return jsonify({"log": f"✅ 本地项目 {name} 已被彻底删除。"})
    except Exception as e:
        return jsonify({"log": f"❌ 删除失败: {str(e)}"})

@app.route('/api/create', methods=['POST'])
def api_create():
    data = request.json
    name = data['name']
    is_private = data['is_private']
    token = get_token()
    target_path = os.path.join(BASE_DIR, name)

    try:
        api_url = "https://api.github.com/user/repos"
        payload = json.dumps({"name": name, "private": is_private}).encode()
        req = urllib.request.Request(api_url, data=payload, headers={"Authorization": f"token {token}"})
        with urllib.request.urlopen(req) as res:
            repo_info = json.loads(res.read().decode())
            clone_url = repo_info['clone_url']

        os.makedirs(target_path, exist_ok=True)
        porcelain.init(target_path)
        r = Repo(target_path)
        r.refs.set_symbolic_ref(b'HEAD', b'refs/heads/main')
        r.close()
        
        with open(os.path.join(target_path, "README.md"), "w", encoding="utf-8") as f:
            f.write(f"# {name}\nCreated by Web Manager")
        with open(os.path.join(target_path, ".gitignore"), "w", encoding="utf-8") as f:
            f.write("*.db\n*.log\n*.sqlite\n*.pyc\n__pycache__/\nmanager_data.db\n")
        
        auth_url = clone_url.replace("https://", f"https://{token}@")
        porcelain.add(target_path, ["README.md", ".gitignore"])
        
        default_committer = b"GitHubAutoTool <tool@localhost>"
        porcelain.commit(target_path, b"Initial commit", author=default_committer, committer=default_committer)
        porcelain.push(target_path, auth_url, refspecs=[b"HEAD:refs/heads/main"])

        now_str = datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("INSERT INTO projects (name, path, repo_url, origin, last_sync) VALUES (?, ?, ?, ?, ?)", 
                  (name, target_path, clone_url, "Local+Cloud", now_str))
        conn.commit()
        conn.close()
        return jsonify({"log": f"✅ 新项目 {name} 已在云端创建。"})
    except Exception as e:
        return jsonify({"log": f"❌ 新建项目失败: {str(e)}"})

def get_tray_icon():
    png_path = get_resource_path("app_icon.png")
    if os.path.exists(png_path):
        return Image.open(png_path)
    
    img = Image.new('RGB', (64, 64), color=(59, 130, 246))
    d = ImageDraw.Draw(img)
    d.text((16, 24), "Git", fill=(255, 255, 255))
    return img

def create_systray():
    global systray_icon
    image = get_tray_icon()
    menu = pystray.Menu(
        pystray.MenuItem("打开 Web 工作台", lambda: webbrowser.open(f"http://127.0.0.1:{CURRENT_PORT}")),
        pystray.MenuItem("退出后台", lambda: exit_app())
    )
    systray_icon = pystray.Icon("GitHubTool", image, "GitHub 工作台", menu)
    systray_icon.run()

def exit_app():
    if 'systray_icon' in globals():
        systray_icon.stop()
    os._exit(0)

if __name__ == "__main__":
    import logging
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)
    
    print(f"正在启动 GitHub 工作台...")
    print(f"访问地址: http://127.0.0.1:{CURRENT_PORT}")
    print("按 Ctrl+C 停止服务")
    
    threading.Thread(target=lambda: app.run(port=CURRENT_PORT, host='127.0.0.1', use_reloader=False), daemon=True).start()
    threading.Thread(target=create_systray, daemon=True).start()
    
    webbrowser.open(f"http://127.0.0.1:{CURRENT_PORT}")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        exit_app()