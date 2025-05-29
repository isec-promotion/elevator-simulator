#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RTSP 5秒問題の最終解決版
画像更新とVLCキャッシュ問題を解決
"""

import time
import logging
import subprocess
import socket
import os
import threading
import shutil
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

def create_dynamic_image(image_path):
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
    
    # 時刻表示（秒まで表示）
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    time_bbox = draw.textbbox((0, 0), current_time, font=font_small)
    time_width = time_bbox[2] - time_bbox[0]
    time_x = (1920 - time_width) // 2
    time_y = y + text_height + 50
    
    draw.text((time_x, time_y), current_time, fill='#333333', font=font_small)
    
    # フレーム番号を追加（デバッグ用）
    frame_text = f"Frame: {int(time.time()) % 10000}"
    draw.text((50, 50), frame_text, fill='#666666', font=font_small)
    
    img.save(image_path, 'JPEG', quality=95)
    return image_path

def create_image_sequence():
    """画像シーケンスを作成（VLCキャッシュ問題を回避）"""
    sequence_dir = '/tmp/rtsp_sequence'
    os.makedirs(sequence_dir, exist_ok=True)
    
    # 既存のファイルを削除
    for f in os.listdir(sequence_dir):
        if f.endswith('.jpg'):
            os.remove(os.path.join(sequence_dir, f))
    
    frame_count = 0
    while True:
        try:
            # 新しいファイル名で画像を作成
            image_path = os.path.join(sequence_dir, f'frame_{frame_count:06d}.jpg')
            create_dynamic_image(image_path)
            
            # 最新の画像へのシンボリックリンクを更新
            latest_path = '/tmp/rtsp_latest.jpg'
            if os.path.exists(latest_path):
                os.remove(latest_path)
            shutil.copy2(image_path, latest_path)
            
            logger.info(f"🔄 画像更新: {datetime.now().strftime('%H:%M:%S')} - Frame {frame_count}")
            
            frame_count += 1
            time.sleep(1)  # 1秒ごとに更新
            
            # 古いフレームを削除（最新10フレームのみ保持）
            if frame_count > 10:
                old_frame = frame_count - 10
                old_path = os.path.join(sequence_dir, f'frame_{old_frame:06d}.jpg')
                if os.path.exists(old_path):
                    os.remove(old_path)
                    
        except Exception as e:
            logger.error(f"❌ 画像更新エラー: {e}")
            time.sleep(1)

def test_vlc_with_image_sequence():
    """VLCで画像シーケンスを使用したRTSPサーバー"""
    try:
        # 初期画像を作成
        create_dynamic_image('/tmp/rtsp_latest.jpg')
        
        # 画像更新スレッドを開始
        update_thread = threading.Thread(target=create_image_sequence, daemon=True)
        update_thread.start()
        
        time.sleep(2)  # 画像更新スレッドの開始を待つ
        
        # VLCで画像シーケンスを使用したRTSPサーバー
        cmd = [
            'cvlc',
            '--intf', 'dummy',
            '--loop',
            '--image-duration', '1',  # 1秒間隔
            '/tmp/rtsp_sequence/frame_%06d.jpg',  # 画像シーケンス
            '--sout', '#transcode{vcodec=h264,vb=2000,fps=30,keyint=30}:rtp{sdp=rtsp://0.0.0.0:8554/live}'
        ]
        
        logger.info("📺 VLC 画像シーケンスRTSPサーバーを開始しています...")
        logger.info(f"📺 コマンド: {' '.join(cmd)}")
        
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        
        time.sleep(5)
        if process.poll() is None:
            local_ip = get_local_ip()
            logger.info(f"✅ VLC 画像シーケンスRTSPサーバーが開始されました")
            logger.info(f"📺 RTSP URL: rtsp://{local_ip}:8554/live")
            logger.info("📺 VLCで上記URLを開いてテストしてください")
            logger.info("🔄 画像は1秒ごとに新しいファイルで更新されます")
            
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

def test_ffmpeg_with_concat():
    """FFmpegでconcatフィルターを使用した連続ストリーミング"""
    try:
        # 初期画像を作成
        create_dynamic_image('/tmp/rtsp_latest.jpg')
        
        # 画像更新スレッドを開始
        update_thread = threading.Thread(target=create_image_sequence, daemon=True)
        update_thread.start()
        
        time.sleep(2)
        
        # FFmpegでconcatフィルターを使用
        cmd = [
            'ffmpeg',
            '-f', 'image2',
            '-framerate', '1',  # 1fps
            '-pattern_type', 'glob',
            '-i', '/tmp/rtsp_sequence/*.jpg',
            '-c:v', 'libx264',
            '-preset', 'ultrafast',
            '-tune', 'stillimage',
            '-pix_fmt', 'yuv420p',
            '-r', '30',  # 出力30fps
            '-g', '30',
            '-b:v', '2000k',
            '-f', 'mpegts',
            'udp://0.0.0.0:8554'
        ]
        
        logger.info("📺 FFmpeg concat UDPストリーミングを開始しています...")
        logger.info(f"📺 コマンド: {' '.join(cmd)}")
        
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        
        time.sleep(3)
        if process.poll() is None:
            local_ip = get_local_ip()
            logger.info(f"✅ FFmpeg concat UDPストリーミングが開始されました")
            logger.info(f"📺 UDP URL: udp://{local_ip}:8554")
            logger.info("📺 VLCで上記URLを開いてテストしてください")
            logger.info("🔄 画像は1秒ごとに新しいファイルで更新されます")
            
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

def test_gstreamer_multifilesrc():
    """GStreamerでmultifilesrcを使用した連続ストリーミング"""
    try:
        # 初期画像を作成
        create_dynamic_image('/tmp/rtsp_latest.jpg')
        
        # 画像更新スレッドを開始
        update_thread = threading.Thread(target=create_image_sequence, daemon=True)
        update_thread.start()
        
        time.sleep(2)
        
        # GStreamerでmultifilesrcを使用
        cmd = [
            'gst-launch-1.0',
            '-v',
            'multifilesrc',
            'location=/tmp/rtsp_sequence/frame_%06d.jpg',
            'index=0',
            'caps=image/jpeg,framerate=1/1',
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
            'key-int-max=30',
            '!',
            'rtph264pay',
            'config-interval=1',
            'pt=96',
            '!',
            'udpsink',
            'host=0.0.0.0',
            'port=8554'
        ]
        
        logger.info("📺 GStreamer multifilesrc UDPストリーミングを開始しています...")
        logger.info(f"📺 コマンド: {' '.join(cmd)}")
        
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        
        time.sleep(3)
        if process.poll() is None:
            local_ip = get_local_ip()
            logger.info(f"✅ GStreamer multifilesrc UDPストリーミングが開始されました")
            logger.info(f"📺 UDP URL: udp://{local_ip}:8554")
            logger.info("📺 VLCで上記URLを開いてテストしてください")
            logger.info("🔄 画像は1秒ごとに新しいファイルで更新されます")
            
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

def test_http_mjpeg_stream():
    """HTTP MJPEG ストリーミング（最も確実）"""
    try:
        import http.server
        import socketserver
        from urllib.parse import urlparse
        
        # 初期画像を作成
        create_dynamic_image('/tmp/rtsp_latest.jpg')
        
        # 画像更新スレッドを開始
        update_thread = threading.Thread(target=create_image_sequence, daemon=True)
        update_thread.start()
        
        class MJPEGHandler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == '/stream.mjpg':
                    self.send_response(200)
                    self.send_header('Content-Type', 'multipart/x-mixed-replace; boundary=frame')
                    self.send_header('Cache-Control', 'no-cache')
                    self.end_headers()
                    
                    try:
                        while True:
                            # 最新の画像を読み込み
                            with open('/tmp/rtsp_latest.jpg', 'rb') as f:
                                frame = f.read()
                            
                            # MJPEG フレームを送信
                            self.wfile.write(b'--frame\r\n')
                            self.send_header('Content-Type', 'image/jpeg')
                            self.send_header('Content-Length', str(len(frame)))
                            self.end_headers()
                            self.wfile.write(frame)
                            self.wfile.write(b'\r\n')
                            
                            time.sleep(1)  # 1秒間隔
                    except:
                        pass
                elif self.path == '/live.jpg':
                    self.send_response(200)
                    self.send_header('Content-type', 'image/jpeg')
                    self.send_header('Cache-Control', 'no-cache')
                    self.end_headers()
                    
                    try:
                        with open('/tmp/rtsp_latest.jpg', 'rb') as f:
                            self.wfile.write(f.read())
                    except:
                        pass
                else:
                    self.send_error(404)
        
        def start_server():
            with socketserver.TCPServer(("", 8080), MJPEGHandler) as httpd:
                local_ip = get_local_ip()
                logger.info("✅ HTTP MJPEG ストリーミングサーバーが開始されました")
                logger.info(f"📺 MJPEG URL: http://{local_ip}:8080/stream.mjpg")
                logger.info(f"📺 JPEG URL: http://{local_ip}:8080/live.jpg")
                logger.info("📺 VLCまたはブラウザで上記URLを開いてテストしてください")
                logger.info("🔄 画像は1秒ごとに更新されます")
                httpd.serve_forever()
        
        # HTTPサーバーを開始
        start_server()
        
    except Exception as e:
        logger.error(f"❌ HTTP MJPEG ストリーミング開始エラー: {e}")

def main():
    """メイン関数"""
    print("🔧 RTSP 5秒問題の最終解決版")
    print("=" * 60)
    print("1. VLC 画像シーケンス RTSP")
    print("2. FFmpeg concat UDP ストリーミング")
    print("3. GStreamer multifilesrc UDP ストリーミング")
    print("4. HTTP MJPEG ストリーミング（最も確実）")
    print("=" * 60)
    print("💡 画像更新とVLCキャッシュ問題を解決した方法です")
    print("🔄 画像は1秒ごとに新しいファイルで更新されます")
    print("📊 フレーム番号と時刻が表示されます")
    print("")
    
    choice = input("テスト方法を選択してください (1-4): ")
    
    if choice == "1":
        test_vlc_with_image_sequence()
    elif choice == "2":
        test_ffmpeg_with_concat()
    elif choice == "3":
        test_gstreamer_multifilesrc()
    elif choice == "4":
        test_http_mjpeg_stream()
    else:
        print("❌ 無効な選択です")

if __name__ == "__main__":
    main()
