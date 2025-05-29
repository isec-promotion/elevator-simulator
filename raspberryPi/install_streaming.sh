#!/bin/bash
# SEC-3000H エレベーター表示システム インストールスクリプト
# Raspberry Pi 4B用

echo "🏢 SEC-3000H エレベーター表示システム インストール開始"
echo "📺 RTSPストリーミング対応版"
echo "=================================================="

# システム更新
echo "📦 システムパッケージを更新中..."
sudo apt update
sudo apt upgrade -y

# 必要なシステムパッケージをインストール
echo "📦 必要なシステムパッケージをインストール中..."
sudo apt install -y \
    python3 \
    python3-pip \
    python3-venv \
    git \
    libopencv-dev \
    python3-opencv \
    gstreamer1.0-tools \
    gstreamer1.0-plugins-base \
    gstreamer1.0-plugins-good \
    gstreamer1.0-plugins-bad \
    gstreamer1.0-plugins-ugly \
    gstreamer1.0-libav \
    libgstreamer1.0-dev \
    libgstreamer-plugins-base1.0-dev \
    fonts-dejavu-core \
    fonts-dejavu-extra \
    libjpeg-dev \
    zlib1g-dev \
    libfreetype6-dev \
    liblcms2-dev \
    libwebp-dev \
    tcl8.6-dev \
    tk8.6-dev \
    python3-tk

# Python仮想環境を作成
echo "🐍 Python仮想環境を作成中..."
python3 -m venv ~/elevator_env

# 仮想環境をアクティベート
echo "🔄 仮想環境をアクティベート中..."
source ~/elevator_env/bin/activate

# pip を最新版にアップグレード
echo "📦 pipを最新版にアップグレード中..."
pip install --upgrade pip

# 必要なPythonパッケージをインストール
echo "📦 Pythonパッケージをインストール中..."
pip install -r requirements_streaming.txt

# ログディレクトリを作成
echo "📁 ログディレクトリを作成中..."
mkdir -p ~/logs

# 実行権限を付与
echo "🔐 実行権限を付与中..."
chmod +x elevator_display_streamer.py

# systemdサービスファイルを作成
echo "⚙️ systemdサービスを設定中..."
sudo tee /etc/systemd/system/elevator-display.service > /dev/null <<EOF
[Unit]
Description=SEC-3000H Elevator Display System with RTSP Streaming
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=$(pwd)
Environment=PATH=$(echo ~/elevator_env/bin):$PATH
ExecStart=$(echo ~/elevator_env/bin/python) $(pwd)/elevator_display_streamer.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# systemdサービスを有効化
echo "🔄 systemdサービスを有効化中..."
sudo systemctl daemon-reload
sudo systemctl enable elevator-display.service

# ファイアウォール設定（RTSPポート8554を開放）
echo "🔥 ファイアウォール設定中..."
if command -v ufw &> /dev/null; then
    sudo ufw allow 8554/tcp
    echo "✅ UFWでポート8554を開放しました"
else
    echo "⚠️ UFWが見つかりません。手動でポート8554を開放してください"
fi

# 使用方法を表示
echo ""
echo "✅ インストールが完了しました！"
echo ""
echo "📋 使用方法:"
echo "----------------------------------------"
echo "🚀 サービス開始: sudo systemctl start elevator-display"
echo "🛑 サービス停止: sudo systemctl stop elevator-display"
echo "📊 サービス状態: sudo systemctl status elevator-display"
echo "📝 ログ確認: journalctl -u elevator-display -f"
echo ""
echo "🔧 手動実行:"
echo "source ~/elevator_env/bin/activate"
echo "python3 elevator_display_streamer.py"
echo ""
echo "📺 RTSPストリーミング:"
echo "URL: rtsp://$(hostname -I | awk '{print $1}'):8554/"
echo "VLCなどのプレイヤーで上記URLを開いてください"
echo ""
echo "🖼️ 画像ファイル: /tmp/elevator_display.jpg"
echo "📁 ログファイル: ~/logs/elevator_display_streamer.log"
echo ""
echo "⚠️ 注意事項:"
echo "- シリアルポート /dev/ttyUSB0 が接続されていることを確認してください"
echo "- RTSPストリーミングにはGStreamerが必要です"
echo "- ネットワーク設定でポート8554が開放されていることを確認してください"
echo ""
echo "🎉 セットアップ完了！"
