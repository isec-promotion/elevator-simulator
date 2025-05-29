#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
シンプルなRTSPテストサーバー
VLCでの接続テスト用
"""

import time
import logging
import subprocess
import socket
import os
from PIL import Image, ImageDraw, ImageFont

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

def create_test_image():
    """テスト画像を作成"""
    img = Image.new('RGB', (1920, 1080), '#b2ffff')
    draw = ImageDraw.Draw(img)
    
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 200)
    except:
        font = ImageFont.load_default()
    
    text = "RTSP TEST"
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    x = (1920 - text_width) // 2
    y = (1080 - text_height) // 2
    
    draw.text((x, y), text, fill='#000000', font=font)
    img.save('/tmp/rtsp_test.jpg', 'JPEG', quality=95)
    logger.info("✅ テスト画像を作成しました: /tmp/rtsp_test.jpg")

def test_ffmpeg_rtsp():
    """FFmpegでRTSPサーバーをテスト"""
    try:
        create_test_image()
        
        # FFmpegでRTSPサーバーを開始
        cmd = [
            'ffmpeg',
            '-re',
            '-stream_loop', '-1',          # 無限ループでフレーム生成（-loop 1 でも可）
            '-i', '/tmp/rtsp_test.jpg',
            '-c:v', 'libx264',
            '-preset', 'ultrafast',
            '-tune', 'stillimage',
            '-pix_fmt', 'yuv420p',
            '-r', '30',
            '-f', 'rtsp',
            '-rtsp_flags', 'listen',       # ★ここが重要
            '-rtsp_transport', 'tcp',      # （推奨）TCP に固定
            'rtsp://0.0.0.0:8554/test'
        ]
        
        logger.info("📺 FFmpeg RTSPサーバーを開始しています...")
        logger.info(f"📺 コマンド: {' '.join(cmd)}")
        
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        
        time.sleep(3)
        if process.poll() is None:
            local_ip = get_local_ip()
            logger.info(f"✅ FFmpeg RTSPサーバーが開始されました")
            logger.info(f"📺 RTSP URL: rtsp://{local_ip}:8554/test")
            logger.info("📺 VLCで上記URLを開いてテストしてください")
            
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

def test_vlc_rtsp():
    """VLCでRTSPサーバーをテスト"""
    try:
        create_test_image()
        
        # VLCでRTSPサーバーを開始
        cmd = [
            'cvlc',
            '--intf', 'dummy',
            '--loop',
            '/tmp/rtsp_test.jpg',
            '--image-duration=-1',
            '--sout-keep',
            '--sout', '#transcode{vcodec=h264,vb=2000,fps=30}:rtp{sdp=rtsp://0.0.0.0:8554/test}'
        ]
        
        logger.info("📺 VLC RTSPサーバーを開始しています...")
        logger.info(f"📺 コマンド: {' '.join(cmd)}")
        
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        
        time.sleep(3)
        if process.poll() is None:
            local_ip = get_local_ip()
            logger.info(f"✅ VLC RTSPサーバーが開始されました")
            logger.info(f"📺 RTSP URL: rtsp://{local_ip}:8554/test")
            logger.info("📺 VLCで上記URLを開いてテストしてください")
            
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

def test_gstreamer_rtsp():
    """GStreamerでRTSPサーバーをテスト"""
    try:
        create_test_image()
        
        # GStreamerでRTSPサーバーを開始
        cmd = [
            'gst-launch-1.0',
            '-v',
            'multifilesrc',
            'location=/tmp/rtsp_test.jpg',
            'loop=true',
            'caps=image/jpeg,framerate=30/1',
            '!',
            'jpegdec',
            '!',
            'videoconvert',
            '!',
            'videoscale',
            '!',
            'video/x-raw,width=1920,height=1080',
            '!',
            'x264enc',
            'tune=zerolatency',
            'bitrate=2000',
            'speed-preset=ultrafast',
            '!',
            'rtph264pay',
            'config-interval=1',
            'pt=96',
            '!',
            'udpsink',
            'host=0.0.0.0',
            'port=8554'
        ]
        
        logger.info("📺 GStreamer RTSPサーバーを開始しています...")
        logger.info(f"📺 コマンド: {' '.join(cmd)}")
        
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        
        time.sleep(3)
        if process.poll() is None:
            local_ip = get_local_ip()
            logger.info(f"✅ GStreamer RTSPサーバーが開始されました")
            logger.info(f"📺 UDP URL: udp://{local_ip}:8554")
            logger.info(f"📺 RTP URL: rtp://{local_ip}:8554")
            logger.info("📺 VLCで上記URLを開いてテストしてください")
            
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
    print("🔧 RTSPテストサーバー")
    print("=" * 40)
    print("1. FFmpeg RTSP")
    print("2. VLC RTSP")
    print("3. GStreamer UDP")
    print("=" * 40)
    
    choice = input("テスト方法を選択してください (1-3): ")
    
    if choice == "1":
        test_ffmpeg_rtsp()
    elif choice == "2":
        test_vlc_rtsp()
    elif choice == "3":
        test_gstreamer_rtsp()
    else:
        print("❌ 無効な選択です")

if __name__ == "__main__":
    main()
