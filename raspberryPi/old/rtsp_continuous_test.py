#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
連続RTSPストリーミングテストサーバー
5秒で途切れる問題を修正
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

def test_ffmpeg_continuous_rtsp():
    """FFmpegで連続RTSPサーバーをテスト"""
    try:
        # 初期画像を作成
        create_dynamic_image()
        
        # 画像更新スレッドを開始
        update_thread = threading.Thread(target=update_image_continuously, daemon=True)
        update_thread.start()
        
        # FFmpegで連続RTSPサーバーを開始
        cmd = [
            'ffmpeg',
            '-re',
            '-f', 'image2',
            '-loop', '1',
            '-r', '30',  # 30fps
            '-i', '/tmp/rtsp_live.jpg',
            '-c:v', 'libx264',
            '-preset', 'ultrafast',
            '-tune', 'stillimage',
            '-pix_fmt', 'yuv420p',
            '-g', '30',  # キーフレーム間隔
            '-keyint_min', '30',
            '-sc_threshold', '0',
            '-b:v', '2000k',
            '-maxrate', '2000k',
            '-bufsize', '4000k',
            '-f', 'rtsp',
            '-rtsp_transport', 'tcp',
            'rtsp://0.0.0.0:8554/live'
        ]
        
        logger.info("📺 FFmpeg 連続RTSPサーバーを開始しています...")
        logger.info(f"📺 コマンド: {' '.join(cmd)}")
        
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        
        time.sleep(3)
        if process.poll() is None:
            local_ip = get_local_ip()
            logger.info(f"✅ FFmpeg 連続RTSPサーバーが開始されました")
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
            logger.error(f"❌ FFmpeg開始エラー:")
            logger.error(f"STDERR: {stderr}")
            
    except Exception as e:
        logger.error(f"❌ エラー: {e}")

def test_ffmpeg_video_rtsp():
    """FFmpegで動画形式のRTSPサーバーをテスト"""
    try:
        # 初期画像を作成
        create_dynamic_image()
        
        # 画像更新スレッドを開始
        update_thread = threading.Thread(target=update_image_continuously, daemon=True)
        update_thread.start()
        
        # FFmpegで動画形式のRTSPサーバーを開始
        cmd = [
            'ffmpeg',
            '-f', 'image2',
            '-r', '1',  # 1fps（画像更新レート）
            '-i', '/tmp/rtsp_live.jpg',
            '-c:v', 'libx264',
            '-preset', 'ultrafast',
            '-tune', 'stillimage',
            '-pix_fmt', 'yuv420p',
            '-r', '30',  # 出力30fps
            '-g', '60',
            '-keyint_min', '60',
            '-x264-params', 'keyint=60:min-keyint=60:scenecut=-1',
            '-b:v', '2000k',
            '-maxrate', '2000k',
            '-bufsize', '4000k',
            '-f', 'rtsp',
            '-rtsp_transport', 'tcp',
            'rtsp://0.0.0.0:8554/video'
        ]
        
        logger.info("📺 FFmpeg 動画形式RTSPサーバーを開始しています...")
        logger.info(f"📺 コマンド: {' '.join(cmd)}")
        
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        
        time.sleep(3)
        if process.poll() is None:
            local_ip = get_local_ip()
            logger.info(f"✅ FFmpeg 動画形式RTSPサーバーが開始されました")
            logger.info(f"📺 RTSP URL: rtsp://{local_ip}:8554/video")
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

def test_vlc_continuous_rtsp():
    """VLCで連続RTSPサーバーをテスト"""
    try:
        # 初期画像を作成
        create_dynamic_image()
        
        # 画像更新スレッドを開始
        update_thread = threading.Thread(target=update_image_continuously, daemon=True)
        update_thread.start()
        
        # VLCで連続RTSPサーバーを開始
        cmd = [
            'cvlc',
            '--intf', 'dummy',
            '--loop',
            '--image-duration', '1',  # 1秒間隔
            '/tmp/rtsp_live.jpg',
            '--sout', '#transcode{vcodec=h264,vb=2000,fps=30,keyint=60}:rtp{sdp=rtsp://0.0.0.0:8554/vlc}'
        ]
        
        logger.info("📺 VLC 連続RTSPサーバーを開始しています...")
        logger.info(f"📺 コマンド: {' '.join(cmd)}")
        
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        
        time.sleep(3)
        if process.poll() is None:
            local_ip = get_local_ip()
            logger.info(f"✅ VLC 連続RTSPサーバーが開始されました")
            logger.info(f"📺 RTSP URL: rtsp://{local_ip}:8554/vlc")
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

def test_gstreamer_continuous_rtsp():
    """GStreamerで連続RTSPサーバーをテスト"""
    try:
        # 初期画像を作成
        create_dynamic_image()
        
        # 画像更新スレッドを開始
        update_thread = threading.Thread(target=update_image_continuously, daemon=True)
        update_thread.start()
        
        # GStreamerで連続RTSPサーバーを開始
        cmd = [
            'gst-launch-1.0',
            '-v',
            'multifilesrc',
            'location=/tmp/rtsp_live.jpg',
            'loop=true',
            'caps=image/jpeg,framerate=30/1',
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
            'port=8554',
            'auto-multicast=true'
        ]
        
        logger.info("📺 GStreamer 連続RTSPサーバーを開始しています...")
        logger.info(f"📺 コマンド: {' '.join(cmd)}")
        
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        
        time.sleep(3)
        if process.poll() is None:
            local_ip = get_local_ip()
            logger.info(f"✅ GStreamer 連続RTSPサーバーが開始されました")
            logger.info(f"📺 UDP URL: udp://{local_ip}:8554")
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
            logger.error(f"❌ GStreamer開始エラー:")
            logger.error(f"STDERR: {stderr}")
            
    except Exception as e:
        logger.error(f"❌ エラー: {e}")

def main():
    """メイン関数"""
    print("🔧 連続RTSPストリーミングテストサーバー")
    print("=" * 50)
    print("1. FFmpeg 連続RTSP (推奨)")
    print("2. FFmpeg 動画形式RTSP")
    print("3. VLC 連続RTSP")
    print("4. GStreamer 連続UDP")
    print("=" * 50)
    print("💡 各方法は5秒で途切れる問題を修正しています")
    print("🔄 画像は1秒ごとに時刻付きで更新されます")
    print("")
    
    choice = input("テスト方法を選択してください (1-4): ")
    
    if choice == "1":
        test_ffmpeg_continuous_rtsp()
    elif choice == "2":
        test_ffmpeg_video_rtsp()
    elif choice == "3":
        test_vlc_continuous_rtsp()
    elif choice == "4":
        test_gstreamer_continuous_rtsp()
    else:
        print("❌ 無効な選択です")

if __name__ == "__main__":
    main()
