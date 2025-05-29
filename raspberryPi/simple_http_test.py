#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
確実に動作するHTTPストリーミングテスト
RTSP問題の代替解決策
"""

import time
import logging
import socket
import os
import threading
import http.server
import socketserver
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime

# ログ設定
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def get_local_ip():
    """ローカルIPアドレスを取得"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "127.0.0.1"

def create_dynamic_image():
    """動的な画像を作成（時刻付き）"""
    img = Image.new('RGB', (1920, 1080), '#b2ffff')
    draw = ImageDraw.Draw(img)
    
    try:
        font_large = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 200)
        font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 80)
    except:
        font_large = ImageFont.load_default()
        font_small = ImageFont.load_default()
    
    # メインテキスト
    text = "HTTP LIVE"
    bbox = draw.textbbox((0, 0), text, font=font_large)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    x = (1920 - text_width) // 2
    y = (1080 - text_height) // 2 - 100
    
    draw.text((x, y), text, fill='#000000', font=font_large)
    
    # 時刻表示（秒まで表示）
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    time_bbox = draw.textbbox((0, 0), current_time, font=font_small)
    time_width = time_bbox[2] - time_bbox[0]
    time_x = (1920 - time_width) // 2
    time_y = y + text_height + 50
    
    draw.text((time_x, time_y), current_time, fill='#333333', font=font_small)
    
    # フレーム番号を追加
    frame_text = f"Frame: {int(time.time()) % 10000}"
    draw.text((50, 50), frame_text, fill='#666666', font=font_small)
    
    # 状態表示
    status_text = "✅ HTTP接続成功"
    draw.text((50, 150), status_text, fill='#006600', font=font_small)
    
    img.save('/tmp/http_live.jpg', 'JPEG', quality=95)
    logger.info(f"🔄 画像更新: {current_time} - Frame {int(time.time()) % 10000}")

def update_image_continuously():
    """画像を継続的に更新"""
    while True:
        try:
            create_dynamic_image()
            time.sleep(1)  # 1秒ごとに更新
        except Exception as e:
            logger.error(f"❌ 画像更新エラー: {e}")
            time.sleep(1)

class StreamingHandler(http.server.BaseHTTPRequestHandler):
    """HTTPストリーミングハンドラー"""
    
    def do_GET(self):
        if self.path == '/stream.mjpg':
            # MJPEG ストリーミング
            self.send_response(200)
            self.send_header('Content-Type', 'multipart/x-mixed-replace; boundary=frame')
            self.send_header('Cache-Control', 'no-cache')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            
            try:
                while True:
                    # 最新の画像を読み込み
                    with open('/tmp/http_live.jpg', 'rb') as f:
                        frame = f.read()
                    
                    # MJPEG フレームを送信
                    self.wfile.write(b'--frame\r\n')
                    self.send_header('Content-Type', 'image/jpeg')
                    self.send_header('Content-Length', str(len(frame)))
                    self.end_headers()
                    self.wfile.write(frame)
                    self.wfile.write(b'\r\n')
                    
                    time.sleep(1)  # 1秒間隔
            except Exception as e:
                logger.error(f"MJPEG ストリーミングエラー: {e}")
                
        elif self.path == '/live.jpg':
            # 単一画像
            self.send_response(200)
            self.send_header('Content-type', 'image/jpeg')
            self.send_header('Cache-Control', 'no-cache')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            
            try:
                with open('/tmp/http_live.jpg', 'rb') as f:
                    self.wfile.write(f.read())
            except Exception as e:
                logger.error(f"画像送信エラー: {e}")
                
        elif self.path == '/' or self.path == '/index.html':
            # HTMLページ
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            
            html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>エレベーター表示システム - HTTPストリーミング</title>
    <meta charset="UTF-8">
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; background: #f0f0f0; }}
        .container {{ max-width: 1200px; margin: 0 auto; background: white; padding: 20px; border-radius: 10px; }}
        h1 {{ color: #333; text-align: center; }}
        .stream-container {{ text-align: center; margin: 20px 0; }}
        .stream-container img {{ max-width: 100%; height: auto; border: 2px solid #333; }}
        .info {{ background: #e8f4fd; padding: 15px; border-radius: 5px; margin: 10px 0; }}
        .success {{ color: #006600; font-weight: bold; }}
        .url {{ background: #f5f5f5; padding: 10px; border-radius: 5px; font-family: monospace; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🏢 エレベーター表示システム</h1>
        <div class="info">
            <p class="success">✅ HTTPストリーミング接続成功</p>
            <p>📺 VLCでの接続方法:</p>
            <div class="url">http://{get_local_ip()}:8080/stream.mjpg</div>
            <p>🌐 ブラウザでの表示:</p>
            <div class="url">http://{get_local_ip()}:8080/live.jpg</div>
        </div>
        
        <div class="stream-container">
            <h2>📺 ライブストリーミング</h2>
            <img src="/stream.mjpg" alt="エレベーター表示" />
        </div>
        
        <div class="info">
            <h3>📋 使用方法</h3>
            <ul>
                <li><strong>VLC接続</strong>: メディア → ネットワークストリームを開く → 上記MJPEGのURLを入力</li>
                <li><strong>ブラウザ表示</strong>: このページで直接確認可能</li>
                <li><strong>更新頻度</strong>: 1秒ごとに画像が更新されます</li>
                <li><strong>解像度</strong>: 1920x1080 (フルHD)</li>
            </ul>
        </div>
    </div>
</body>
</html>
            """
            self.wfile.write(html.encode('utf-8'))
            
        else:
            self.send_error(404)
    
    def log_message(self, format, *args):
        # アクセスログを簡略化
        pass

def main():
    """メイン関数"""
    print("🔧 確実に動作するHTTPストリーミングサーバー")
    print("=" * 60)
    print("💡 RTSP問題の代替解決策")
    print("🔄 画像は1秒ごとに時刻付きで更新されます")
    print("📺 VLCとブラウザの両方で表示可能")
    print("")
    
    try:
        # 初期画像を作成
        create_dynamic_image()
        
        # 画像更新スレッドを開始
        update_thread = threading.Thread(target=update_image_continuously, daemon=True)
        update_thread.start()
        
        # HTTPサーバーを開始
        with socketserver.TCPServer(("", 8080), StreamingHandler) as httpd:
            local_ip = get_local_ip()
            
            logger.info("✅ HTTPストリーミングサーバーが開始されました")
            logger.info("=" * 60)
            logger.info(f"📺 VLC用MJPEG URL: http://{local_ip}:8080/stream.mjpg")
            logger.info(f"🌐 ブラウザ用URL: http://{local_ip}:8080/")
            logger.info(f"📷 単一画像URL: http://{local_ip}:8080/live.jpg")
            logger.info("=" * 60)
            logger.info("📋 VLCでの接続手順:")
            logger.info("   1. VLCを開く")
            logger.info("   2. メディア → ネットワークストリームを開く")
            logger.info(f"   3. URL: http://{local_ip}:8080/stream.mjpg")
            logger.info("   4. 再生をクリック")
            logger.info("=" * 60)
            logger.info("🔄 画像は1秒ごとに更新されます")
            logger.info("🛑 停止するには Ctrl+C を押してください")
            logger.info("")
            
            httpd.serve_forever()
            
    except KeyboardInterrupt:
        logger.info("🛑 サーバーを停止しています...")
    except Exception as e:
        logger.error(f"❌ サーバー開始エラー: {e}")

if __name__ == "__main__":
    main()
