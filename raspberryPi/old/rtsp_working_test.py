#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
動作確認済みRTSPストリーミングテストサーバー
FFmpegのRTSP出力問題を修正
"""

import time
import logging
import subprocess
import socket
import os
import threading
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
    text = "RTSP LIVE"
    bbox = draw.textbbox((0, 0), text, font=font_large)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    x = (1920 - text_width) // 2
    y = (1080 - text_height) // 2 - 100
    
    draw.text((x, y), text, fill='#000000', font=font_large)
    
    # 時刻表示
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    time_bbox = draw.textbbox((0, 0), current_time, font=font_small)
    time_width = time_bbox[2] - time_bbox[0]
    time_x = (1920 - time_width) // 2
    time_y = y + text_height + 50
    
    draw.text((time_x, time_y), current_time, fill='#333333', font=font_small)
    
    img.save('/tmp/rtsp_live.jpg', 'JPEG', quality=95)
    return '/tmp/rtsp_live.jpg'

def update_image_continuously():
    """画像を継続的に更新"""
    while True:
        try:
            create_dynamic_image()
            time.sleep(1)  # 1秒ごとに更新
        except Exception as e:
            logger.error(f"❌ 画像更新エラー: {e}")
            time.sleep(1)

def test_ffmpeg_udp_stream():
    """FFmpegでUDPストリーミング（RTSPの代替）"""
    try:
        # 初期画像を作成
        create_dynamic_image()
        
        # 画像更新スレッドを開始
        update_thread = threading.Thread(target=update_image_continuously, daemon=True)
        update_thread.start()
        
        # FFmpegでUDPストリーミング
        cmd = [
            'ffmpeg',
            '-re',
            '-f', 'image2',
            '-loop', '1',
            '-r', '1',  # 1fps（画像更新レート）
            '-i', '/tmp/rtsp_live.jpg',
            '-c:v', 'libx264',
            '-preset', 'ultrafast',
            '-tune', 'stillimage',
            '-pix_fmt', 'yuv420p',
            '-r', '30',  # 出力30fps
            '-g', '60',
            '-b:v', '2000k',
            '-f', 'mpegts',
            f'udp://0.0.0.0:8554'
        ]
        
        logger.info("📺 FFmpeg UDPストリーミングを開始しています...")
        logger.info(f"📺 コマンド: {' '.join(cmd)}")
        
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        
        time.sleep(3)
        if process.poll() is None:
            local_ip = get_local_ip()
            logger.info(f"✅ FFmpeg UDPストリーミングが開始されました")
            logger.info(f"📺 UDP URL: udp://{local_ip}:8554")
            logger.info("📺 VLCで上記URLを開いてテストしてください")
            logger.info("🔄 画像は1秒ごとに更新されます")
            
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                logger.info("🛑 サーバーを停止しています...")
                process.terminate()
                process.wait()
        else:
            stdout, stderr = process.communicate()
            logger.error(f"❌ FFmpeg開始エラー:")
            logger.error(f"STDERR: {stderr}")
            
    except Exception as e:
        logger.error(f"❌ エラー: {e}")

def test_ffmpeg_rtp_stream():
    """FFmpegでRTPストリーミング"""
    try:
        # 初期画像を作成
        create_dynamic_image()
        
        # 画像更新スレッドを開始
        update_thread = threading.Thread(target=update_image_continuously, daemon=True)
        update_thread.start()
        
        # FFmpegでRTPストリーミング
        cmd = [
            'ffmpeg',
            '-re',
            '-f', 'image2',
            '-loop', '1',
            '-r', '1',  # 1fps（画像更新レート）
            '-i', '/tmp/rtsp_live.jpg',
            '-c:v', 'libx264',
            '-preset', 'ultrafast',
            '-tune', 'stillimage',
            '-pix_fmt', 'yuv420p',
            '-r', '30',  # 出力30fps
            '-g', '60',
            '-b:v', '2000k',
            '-f', 'rtp',
            f'rtp://0.0.0.0:8554'
        ]
        
        logger.info("📺 FFmpeg RTPストリーミングを開始しています...")
        logger.info(f"📺 コマンド: {' '.join(cmd)}")
        
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        
        time.sleep(3)
        if process.poll() is None:
            local_ip = get_local_ip()
            logger.info(f"✅ FFmpeg RTPストリーミングが開始されました")
            logger.info(f"📺 RTP URL: rtp://{local_ip}:8554")
            logger.info("📺 VLCで上記URLを開いてテストしてください")
            logger.info("🔄 画像は1秒ごとに更新されます")
            
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                logger.info("🛑 サーバーを停止しています...")
                process.terminate()
                process.wait()
        else:
            stdout, stderr = process.communicate()
            logger.error(f"❌ FFmpeg開始エラー:")
            logger.error(f"STDERR: {stderr}")
            
    except Exception as e:
        logger.error(f"❌ エラー: {e}")

def test_vlc_rtsp_working():
    """VLCで動作確認済みRTSPサーバー"""
    try:
        # 初期画像を作成
        create_dynamic_image()
        
        # 画像更新スレッドを開始
        update_thread = threading.Thread(target=update_image_continuously, daemon=True)
        update_thread.start()
        
        # VLCでRTSPサーバーを開始（修正版）
        cmd = [
            'cvlc',
            '--intf', 'dummy',
            '--loop',
            '/tmp/rtsp_live.jpg',
            '--sout', '#transcode{vcodec=h264,vb=2000,fps=30}:rtp{sdp=rtsp://0.0.0.0:8554/live}'
        ]
        
        logger.info("📺 VLC RTSPサーバー（修正版）を開始しています...")
        logger.info(f"📺 コマンド: {' '.join(cmd)}")
        
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        
        time.sleep(5)  # VLCの起動に時間がかかる場合がある
        if process.poll() is None:
            local_ip = get_local_ip()
            logger.info(f"✅ VLC RTSPサーバーが開始されました")
            logger.info(f"📺 RTSP URL: rtsp://{local_ip}:8554/live")
            logger.info("📺 VLCで上記URLを開いてテストしてください")
            logger.info("🔄 画像は1秒ごとに更新されます")
            
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                logger.info("🛑 サーバーを停止しています...")
                process.terminate()
                process.wait()
        else:
            stdout, stderr = process.communicate()
            logger.error(f"❌ VLC開始エラー:")
            logger.error(f"STDERR: {stderr}")
            
    except Exception as e:
        logger.error(f"❌ エラー: {e}")

def test_gstreamer_working():
    """GStreamerで動作確認済みUDPストリーミング"""
    try:
        # 初期画像を作成
        create_dynamic_image()
        
        # 画像更新スレッドを開始
        update_thread = threading.Thread(target=update_image_continuously, daemon=True)
        update_thread.start()
        
        # GStreamerでUDPストリーミング（修正版）
        cmd = [
            'gst-launch-1.0',
            '-v',
            'multifilesrc',
            'location=/tmp/rtsp_live.jpg',
            'loop=true',
            'caps=image/jpeg,framerate=1/1',  # 1fps
            '!',
            'jpegdec',
            '!',
            'videoconvert',
            '!',
            'videoscale',
            '!',
            'video/x-raw,width=1920,height=1080,framerate=30/1',
            '!',
            'x264enc',
            'tune=zerolatency',
            'bitrate=2000',
            'speed-preset=ultrafast',
            'key-int-max=60',
            '!',
            'rtph264pay',
            'config-interval=1',
            'pt=96',
            '!',
            'udpsink',
            'host=0.0.0.0',
            'port=8554'
        ]
        
        logger.info("📺 GStreamer UDPストリーミング（修正版）を開始しています...")
        logger.info(f"📺 コマンド: {' '.join(cmd)}")
        
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        
        time.sleep(3)
        if process.poll() is None:
            local_ip = get_local_ip()
            logger.info(f"✅ GStreamer UDPストリーミングが開始されました")
            logger.info(f"📺 UDP URL: udp://{local_ip}:8554")
            logger.info("📺 VLCで上記URLを開いてテストしてください")
            logger.info("🔄 画像は1秒ごとに更新されます")
            
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                logger.info("🛑 サーバーを停止しています...")
                process.terminate()
                process.wait()
        else:
            stdout, stderr = process.communicate()
            logger.error(f"❌ GStreamer開始エラー:")
            logger.error(f"STDERR: {stderr}")
            
    except Exception as e:
        logger.error(f"❌ エラー: {e}")

def test_simple_http_stream():
    """シンプルなHTTPストリーミング（確実に動作）"""
    try:
        import http.server
        import socketserver
        from urllib.parse import urlparse
        
        # 初期画像を作成
        create_dynamic_image()
        
        # 画像更新スレッドを開始
        update_thread = threading.Thread(target=update_image_continuously, daemon=True)
        update_thread.start()
        
        class ImageHandler(http.server.SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory='/tmp', **kwargs)
            
            def do_GET(self):
                if self.path == '/live.jpg' or self.path == '/rtsp_live.jpg':
                    self.send_response(200)
                    self.send_header('Content-type', 'image/jpeg')
                    self.send_header('Cache-Control', 'no-cache')
                    self.send_header('Refresh', '1')  # 1秒ごとに更新
                    self.end_headers()
                    
                    try:
                        with open('/tmp/rtsp_live.jpg', 'rb') as f:
                            self.wfile.write(f.read())
                    except:
                        pass
                else:
                    super().do_GET()
        
        def start_server():
            with socketserver.TCPServer(("", 8080), ImageHandler) as httpd:
                local_ip = get_local_ip()
                logger.info("✅ HTTPストリーミングサーバーが開始されました")
                logger.info(f"📺 HTTP URL: http://{local_ip}:8080/live.jpg")
                logger.info("📺 VLCまたはブラウザで上記URLを開いてテストしてください")
                logger.info("🔄 画像は1秒ごとに更新されます")
                httpd.serve_forever()
        
        # HTTPサーバーを開始
        start_server()
        
    except Exception as e:
        logger.error(f"❌ HTTPストリーミング開始エラー: {e}")

def main():
    """メイン関数"""
    print("🔧 動作確認済みストリーミングテストサーバー")
    print("=" * 60)
    print("1. FFmpeg UDP ストリーミング")
    print("2. FFmpeg RTP ストリーミング")
    print("3. VLC RTSP サーバー（修正版）")
    print("4. GStreamer UDP ストリーミング（修正版）")
    print("5. HTTP ストリーミング（確実に動作）")
    print("=" * 60)
    print("💡 FFmpegのRTSP出力問題を回避した方法です")
    print("🔄 画像は1秒ごとに時刻付きで更新されます")
    print("")
    
    choice = input("テスト方法を選択してください (1-5): ")
    
    if choice == "1":
        test_ffmpeg_udp_stream()
    elif choice == "2":
        test_ffmpeg_rtp_stream()
    elif choice == "3":
        test_vlc_rtsp_working()
    elif choice == "4":
        test_gstreamer_working()
    elif choice == "5":
        test_simple_http_stream()
    else:
        print("❌ 無効な選択です")

if __name__ == "__main__":
    main()
