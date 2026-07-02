#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GitHub推送工具 打包脚本
使用 PyInstaller 打包为目录模式（--onedir，非单文件）
"""

import os
import sys
import shutil
import subprocess

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DIST_DIR = os.path.join(BASE_DIR, "dist")
BUILD_DIR = os.path.join(BASE_DIR, "build")
APP_NAME = "GitHub推送工具"

# 需要打包进去的额外文件
DATA_FILES = [
    ("app_icon.png", "."),
    ("sing-box.exe", "."),
]

def clean():
    """清理旧的构建文件"""
    for d in [DIST_DIR, BUILD_DIR]:
        if os.path.exists(d):
            print(f"清理目录: {d}")
            shutil.rmtree(d, ignore_errors=True)
    for f in [f"{APP_NAME}.spec"]:
        p = os.path.join(BASE_DIR, f)
        if os.path.exists(p):
            os.remove(p)

def build():
    """执行 PyInstaller 打包"""
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", APP_NAME,
        "--noconfirm",
        "--clean",
        "--onedir",
        "--windowed",
        "--icon", os.path.join(BASE_DIR, "app_icon.png"),
    ]

    # 添加数据文件
    for src, dst in DATA_FILES:
        src_path = os.path.join(BASE_DIR, src)
        if os.path.exists(src_path):
            cmd.extend(["--add-data", f"{src_path}{os.pathsep}{dst}"])
        else:
            print(f"警告: 文件不存在，跳过: {src}")

    # 隐含依赖
    cmd.extend([
        "--hidden-import", "dulwich",
        "--hidden-import", "dulwich.porcelain",
        "--hidden-import", "dulwich.repo",
        "--hidden-import", "flask",
        "--hidden-import", "pystray",
        "--hidden-import", "PIL",
        "--hidden-import", "PIL.Image",
        "--hidden-import", "PIL.ImageDraw",
    ])

    # 入口脚本
    cmd.append(os.path.join(BASE_DIR, "app.py"))

    print("=" * 50)
    print("开始打包...")
    print("=" * 50)
    print(f"命令: {' '.join(cmd)}")
    print()

    result = subprocess.run(cmd, cwd=BASE_DIR)
    if result.returncode != 0:
        print("打包失败！")
        return False

    print()
    print("=" * 50)
    print("打包完成！")
    print("=" * 50)

    # 复制额外文件到 dist 目录
    app_dir = os.path.join(DIST_DIR, APP_NAME)
    if os.path.exists(app_dir):
        print()
        print(f"输出目录: {app_dir}")
        print(f"运行 {APP_NAME}.exe 即可启动程序")

    return True

def main():
    print(f"GitHub推送工具 打包工具")
    print(f"工作目录: {BASE_DIR}")
    print()

    # 检查 PyInstaller
    try:
        import PyInstaller
        print(f"PyInstaller 版本: {PyInstaller.__version__}")
    except ImportError:
        print("错误: 未安装 PyInstaller")
        print("请运行: pip install pyinstaller")
        sys.exit(1)

    # 清理
    clean()

    # 打包
    if build():
        print()
        print("打包成功！")
    else:
        print()
        print("打包失败，请检查错误信息")
        sys.exit(1)

if __name__ == "__main__":
    main()
