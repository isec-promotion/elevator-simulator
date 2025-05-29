#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
改良版連続RTSPストリーミングテストサーバー
VLC RTSP自動実行、5秒間隔画像更新
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
    """動的な画像を作成（詳細な時刻付き）"""
    img = Image.new('RGB', (1920, 1080), '#b2ffff')
    draw = ImageDraw.Draw(img)
    
    try:
        font_large = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 200)
        font_medium = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 100)
        font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 80)
    except:
        font_large = ImageFont.load_default()
        font_medium = ImageFont.load_default()
        font_small = ImageFont.load_default()
    
    # メインテキスト "RTSP TEST"
    text = "RTSP TEST"
    bbox = draw.textbbox((0, 0), text, font=font_large)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    x = (1920 - text_width) // 2
    y = (1080 - text_height) // 2 - 150
    
    draw.text((x, y), text, fill='#000000', font=font_large)
    
    # 現在の日時表示（日付から秒数まで）
    current_datetime = datetime.now()
    
    # 日付表示
    date_str = current_datetime.strftime("%Y/%m/%d")
    date_bbox = draw.textbbox((0, 0), date_str, font=font_medium)
    date_width = date_bbox[2] - date_bbox[0]
    date_x = (1920 - date_width) // 2
    date_y = y + text_height + 30
    
    draw.text((date_x, date_y), date_str, fill='#333333', font=font_medium)
    
    # 時刻表示（時分秒）
    time_str = current_datetime.strftime("%H:%M:%S")
    time_bbox = draw.textbbox((0, 0), time_str, font=font_medium)
    time_width = time_bbox[2] - time_bbox[0]
    time_x = (1920 - time_width) // 2
    time_y = date_y + 120
    
    draw.text((time_x, time_y), time_str, fill='#333333', font=font_medium)
    
    iso_y = time_y + 120
    
    # 更新間隔情報
    update_info = "duration: 5s"
    info_bbox = draw.textbbox((0, 0), update_info, font=font_small)
    info_width = info_bbox[2] - info_bbox[0]
    info_x = (1920 - info_width) // 2
    info_y = iso_y + 100
    
    draw.text((info_x, info_y), update_info, fill='#888888', font=font_small)
    
    img.save('/tmp/rtsp_test.jpg', 'JPEG', quality=95)
    logger.info(f"📸 画像を更新しました: {current_datetime.strftime('%H:%M:%S')}")
    return '/tmp/rtsp_test.jpg'

def update_image_continuously():
    """画像を5秒間隔で継続的に更新"""
    while True:
        try:
            create_dynamic_image()
            time.sleep(5)  # 5秒間隔で更新
        except Exception as e:
            logger.error(f"❌ 画像更新エラー: {e}")
            time.sleep(5)

def start_vlc_rtsp_server():
    """VLC RTSPサーバーを自動開始"""
    try:
        # 初期画像を作成
        create_dynamic_image()
        
        # 画像更新スレッドを開始
        update_thread = threading.Thread(target=update_image_continuously, daemon=True)
        update_thread.start()
        
        # VLC RTSPサーバーを開始
        cmd = [
            'cvlc',
            '--intf', 'dummy',
            '--loop',
            '/tmp/rtsp_test.jpg',
            '--image-duration=-1',
            '--sout-keep',
            '--sout', '#transcode{vcodec=h264,vb=2000,fps=30}:rtp{sdp=rtsp://0.0.0.0:8554/test}'
        ]
        
        logger.info("📺 VLC RTSPサーバーを自動開始しています...")
        logger.info(f"📺 コマンド: {' '.join(cmd)}")
        
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        
        time.sleep(5)  # VLCの起動を待つ
        if process.poll() is None:
            local_ip = get_local_ip()
            logger.info(f"✅ VLC RTSPサーバーが開始されました")
            logger.info(f"📺 RTSP URL: rtsp://{local_ip}:8554/test")
            logger.info("📺 VLCで上記URLを開いてテストしてください")
            logger.info("🔄 画像は5秒ごとに更新されます")
            logger.info("📅 日時は秒単位まで表示されます")
            logger.info("📺 Ctrl+Cで停止します")
            
            try:
                while True:
                    time.sleep(1)
                    if process.poll() is not None:
                        logger.warning("⚠️ VLCプロセスが終了しました")
                        break
            except KeyboardInterrupt:
                logger.info("🛑 サーバーを停止しています...")
                process.terminate()
                process.wait()
                logger.info("✅ サーバーを停止しました")
        else:
            stdout, stderr = process.communicate()
            logger.error(f"❌ VLC開始エラー:")
            logger.error(f"STDERR: {stderr}")
            
    except Exception as e:
        logger.error(f"❌ エラー: {e}")

def test_ffmpeg_rtsp_server():
    """FFmpeg RTSPサーバー（代替オプション）"""
    try:
        # 初期画像を作成
        create_dynamic_image()
        
        # 画像更新スレッドを開始
        update_thread = threading.Thread(target=update_image_continuously, daemon=True)
        update_thread.start()
        
        # FFmpeg RTSPサーバーを開始
        cmd = [
            'ffmpeg',
            '-re',
            '-f', 'image2',
            '-loop', '1',
            '-r', '0.2',  # 0.2fps = 5秒間隔
            '-i', '/tmp/rtsp_test.jpg',
            '-c:v', 'libx264',
            '-preset', 'ultrafast',
            '-tune', 'stillimage',
            '-pix_fmt', 'yuv420p',
            '-r', '30',  # 出力30fps
            '-g', '60',
            '-keyint_min', '60',
            '-sc_threshold', '0',
            '-b:v', '2000k',
            '-maxrate', '2000k',
            '-bufsize', '4000k',
            '-f', 'mpegts',  # RTSPの代わりにUDPを使用
            'udp://0.0.0.0:8554'
        ]
        
        logger.info("📺 FFmpeg UDPサーバーを開始しています...")
        logger.info(f"📺 コマンド: {' '.join(cmd)}")
        
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        
        time.sleep(3)
        if process.poll() is None:
            local_ip = get_local_ip()
            logger.info(f"✅ FFmpeg UDPサーバーが開始されました")
            logger.info(f"📺 UDP URL: udp://{local_ip}:8554")
            logger.info("📺 VLCで上記URLを開いてテストしてください")
            logger.info("🔄 画像は5秒ごとに更新されます")
            logger.info("📅 日時は秒単位まで表示されます")
            logger.info("📺 Ctrl+Cで停止します")
            
            try:
                while True:
                    time.sleep(1)
                    if process.poll() is not None:
                        logger.warning("⚠️ FFmpegプロセスが終了しました")
                        break
            except KeyboardInterrupt:
                logger.info("🛑 サーバーを停止しています...")
                process.terminate()
                process.wait()
                logger.info("✅ サーバーを停止しました")
        else:
            stdout, stderr = process.communicate()
            logger.error(f"❌ FFmpeg開始エラー:")
            logger.error(f"STDERR: {stderr}")
            
    except Exception as e:
        logger.error(f"❌ エラー: {e}")

def main():
    """メイン関数"""
    print("🎬 改良版RTSPストリーミングテストサーバー")
    print("=" * 60)
    print("📝 自動機能:")
    print("   • VLC RTSPサーバーを即座に開始")
    print("   • 画像を5秒間隔で自動更新")
    print("   • 日時を秒単位まで表示")
    print("=" * 60)
    print("1. VLC RTSPサーバー（推奨・自動実行）")
    print("2. FFmpeg UDPサーバー（代替オプション）")
    print("=" * 60)
    
    choice = input("サーバーを選択してください (1-2, Enterで1): ").strip()
    
    if choice == "" or choice == "1":
        logger.info("🚀 VLC RTSPサーバーを自動開始します...")
        start_vlc_rtsp_server()
    elif choice == "2":
        logger.info("🚀 FFmpeg UDPサーバーを開始します...")
        test_ffmpeg_rtsp_server()
    else:
        print("❌ 無効な選択です")

if __name__ == "__main__":
    main()
