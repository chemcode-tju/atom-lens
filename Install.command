#!/bin/bash
# Double-click in Finder; use python3 install.py to select an existing conda environment.
cd "$(dirname "$0")" || exit 1
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
if ! command -v python3 >/dev/null 2>&1; then
    echo "需要 Python 3.9+。已安装 Homebrew 时可执行：brew install python"
    read -r -p "按回车关闭…"
    exit 1
fi
python3 install.py
result=$?
if [ "$result" -eq 0 ]; then
    echo
    read -r -p "同时安装远程导出到 Mac 的保存助手？需要 Apple Command Line Tools。[y/N] " answer
    case "$answer" in
        y|Y) python3 native/install_helper.py; result=$? ;;
    esac
fi
echo
read -r -p "按回车关闭…"
exit "$result"
