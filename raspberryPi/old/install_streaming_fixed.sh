#!/bin/bash
# SEC-3000H エレベーター表示システム インストールスクリプト (修正版)
# Raspberry Pi 4B用

echo "🏢 SEC-3000H エレベーター表示システム インストール開始"
echo "📺 RTSPストリーミング対応版 v2.0 (修正版)"
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
    gstreamer1.0-rtsp \
    libgstreamer1.0-dev \
    libgstreamer-plugins-base1.0-dev \
    libgstrtspserver-1.0-dev \
    gstreamer1.0-rtsp \
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

# gst-rtsp-serverをインストール（利用可能な場合）
echo "📦 gst-rtsp-serverをインストール中..."
sudo apt install -y gst-rtsp-server || echo "⚠️ gst-rtsp-serverが利用できません（代替方法を使用します）"

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
chmod +x elevator_display_streamer_fixed.py

# systemdサービスファイルを作成（修正版用）
echo "⚙️ systemdサービスを設定中..."
sudo tee /etc/systemd/system/elevator-display-fixed.service > /dev/null <<EOF
[Unit]
Description=SEC-3000H Elevator Display System with RTSP Streaming (Fixed)
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=$(pwd)
Environment=PATH=$(echo ~/elevator_env/bin):$PATH
ExecStart=$(echo ~/elevator_env/bin/python) $(pwd)/elevator_display_streamer_fixed.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# systemdサービスを有効化
echo "🔄 systemdサービスを有効化中..."
sudo systemctl daemon-reload
sudo systemctl enable elevator-display-fixed.service

# ファイアウォール設定（RTSPポート8554とHTTPポート8080を開放）
echo "🔥 ファイアウォール設定中..."
if command -v ufw &> /dev/null; then
    sudo ufw allow 8554/tcp
    sudo ufw allow 8554/udp
    sudo ufw allow 8080/tcp
    echo "✅ UFWでポート8554（RTSP）と8080（HTTP）を開放しました"
else
    echo "⚠️ UFWが見つかりません。手動でポート8554と8080を開放してください"
fi

# GStreamerの動作確認
echo "🔧 GStreamerの動作確認中..."
if gst-launch-1.0 --version > /dev/null 2>&1; then
    echo "✅ GStreamer 1.0が利用可能です"
else
    echo "❌ GStreamer 1.0が見つかりません"
fi

# テスト画像を作成
echo "🖼️ テスト画像を作成中..."
python3 -c "
from PIL import Image, ImageDraw, ImageFont
import os

# テスト画像を作成
img = Image.new('RGB', (1920, 1080), '#b2ffff')
draw = ImageDraw.Draw(img)

try:
    font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 200)
except:
    font = ImageFont.load_default()

text = 'TEST'
bbox = draw.textbbox((0, 0), text, font=font)
text_width = bbox[2] - bbox[0]
text_height = bbox[3] - bbox[1]
x = (1920 - text_width) // 2
y = (1080 - text_height) // 2

draw.text((x, y), text, fill='#000000', font=font)
img.save('/tmp/elevator_display.jpg', 'JPEG', quality=95)
print('✅ テスト画像を作成しました: /tmp/elevator_display.jpg')
"

# 使用方法を表示
echo ""
echo "✅ インストールが完了しました！"
echo ""
echo "📋 使用方法:"
echo "----------------------------------------"
echo "🚀 サービス開始: sudo systemctl start elevator-display-fixed"
echo "🛑 サービス停止: sudo systemctl stop elevator-display-fixed"
echo "📊 サービス状態: sudo systemctl status elevator-display-fixed"
echo "📝 ログ確認: journalctl -u elevator-display-fixed -f"
echo ""
echo "🔧 手動実行:"
echo "source ~/elevator_env/bin/activate"
echo "python3 elevator_display_streamer_fixed.py"
echo ""
echo "📺 ストリーミングURL:"
echo "----------------------------------------"
LOCAL_IP=$(hostname -I | awk '{print $1}')
echo "🌐 HTTP画像URL: http://${LOCAL_IP}:8080/elevator_display.jpg"
echo "📺 RTSP URL: rtsp://${LOCAL_IP}:8554/ (GStreamerが利用可能な場合)"
echo "📺 UDP URL: udp://@:8554 (GStreamerが利用可能な場合)"
echo ""
echo "🎯 VLCでの接続方法:"
echo "----------------------------------------"
echo "1. VLCを開く"
echo "2. メディア → ネットワークストリームを開く"
echo "3. 以下のURLを入力:"
echo "   - HTTP: http://${LOCAL_IP}:8080/elevator_display.jpg"
echo "   - RTSP: rtsp://${LOCAL_IP}:8554/ (利用可能な場合)"
echo "   - UDP: udp://@:8554 (利用可能な場合)"
echo ""
echo "🖼️ ファイル:"
echo "----------------------------------------"
echo "📁 画像ファイル: /tmp/elevator_display.jpg"
echo "📁 ログファイル: ~/logs/elevator_display_streamer.log"
echo ""
echo "⚠️ 注意事項:"
echo "----------------------------------------"
echo "- シリアルポート /dev/ttyUSB0 が接続されていることを確認してください"
echo "- RTSPストリーミングにはGStreamerが必要です"
echo "- ネットワーク設定でポート8554と8080が開放されていることを確認してください"
echo "- HTTPストリーミングは代替手段として常に利用可能です"
echo ""
echo "🔧 トラブルシューティング:"
echo "----------------------------------------"
echo "1. RTSPが接続できない場合:"
echo "   → HTTPストリーミング（http://${LOCAL_IP}:8080/elevator_display.jpg）を試してください"
echo "2. GStreamerエラーが発生する場合:"
echo "   → HTTPストリーミングが自動的に代替として使用されます"
echo "3. 画像が更新されない場合:"
echo "   → ログを確認してください: tail -f ~/logs/elevator_display_streamer.log"
echo ""
echo "🎉 セットアップ完了！"
