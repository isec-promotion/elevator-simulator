#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mediamtxを使用した動的映像RTSPサーバー
VLCでの接続テスト用 - 1280x720解像度
"""

import time
import logging
import subprocess
import socket
import os
import threading
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import cv2

# ログ設定
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class VideoGenerator:
    """動的映像生成クラス"""
    
    def __init__(self, width=1280, height=720, fps=30):
        self.width = width
        self.height = height
        self.fps = fps
        self.frame_count = 0
        self.running = False
        
    def create_animated_frame(self):
        """アニメーション付きフレームを作成"""
        # 背景色を時間に応じて変化させる
        hue = (self.frame_count * 2) % 360
        bg_color = self._hsv_to_rgb(hue, 0.3, 0.9)
        
        # PILで画像を作成
        img = Image.new('RGB', (self.width, self.height), bg_color)
        draw = ImageDraw.Draw(img)
        
        # フォントを設定
        try:
            font_large = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 80)
            font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 40)
        except:
            font_large = ImageFont.load_default()
            font_small = ImageFont.load_default()
        
        # メインタイトル
        title = "RTSP VIDEO TEST"
        bbox = draw.textbbox((0, 0), title, font=font_large)
        text_width = bbox[2] - bbox[0]
        x = (self.width - text_width) // 2
        y = 150
        draw.text((x, y), title, fill='#000000', font=font_large)
        
        # 解像度情報
        resolution_text = f"{self.width}x{self.height} @ {self.fps}fps"
        bbox = draw.textbbox((0, 0), resolution_text, font=font_small)
        text_width = bbox[2] - bbox[0]
        x = (self.width - text_width) // 2
        y = 250
        draw.text((x, y), resolution_text, fill='#333333', font=font_small)
        
        # フレームカウンター
        frame_text = f"Frame: {self.frame_count}"
        bbox = draw.textbbox((0, 0), frame_text, font=font_small)
        text_width = bbox[2] - bbox[0]
        x = (self.width - text_width) // 2
        y = 320
        draw.text((x, y), frame_text, fill='#333333', font=font_small)
        
        # 時刻表示
        current_time = time.strftime("%Y-%m-%d %H:%M:%S")
        bbox = draw.textbbox((0, 0), current_time, font=font_small)
        text_width = bbox[2] - bbox[0]
        x = (self.width - text_width) // 2
        y = 390
        draw.text((x, y), current_time, fill='#333333', font=font_small)
        
        # 動く円を描画
        circle_x = int(self.width // 2 + 200 * np.sin(self.frame_count * 0.1))
        circle_y = int(self.height // 2 + 100 * np.cos(self.frame_count * 0.1))
        circle_color = self._hsv_to_rgb((self.frame_count * 5) % 360, 0.8, 1.0)
        draw.ellipse([circle_x-30, circle_y-30, circle_x+30, circle_y+30], fill=circle_color)
        
        # 動く四角形を描画
        rect_x = int(self.width // 2 + 150 * np.cos(self.frame_count * 0.08))
        rect_y = int(self.height // 2 + 80 * np.sin(self.frame_count * 0.08))
        rect_color = self._hsv_to_rgb((self.frame_count * 3 + 120) % 360, 0.6, 0.8)
        draw.rectangle([rect_x-25, rect_y-25, rect_x+25, rect_y+25], fill=rect_color)
        
        self.frame_count += 1
        return img
    
    def _hsv_to_rgb(self, h, s, v):
        """HSVからRGBに変換"""
        import colorsys
        r, g, b = colorsys.hsv_to_rgb(h/360.0, s, v)
        return (int(r*255), int(g*255), int(b*255))
    
    def generate_video_frames(self, output_pipe):
        """映像フレームを生成してパイプに送信"""
        self.running = True
        frame_duration = 1.0 / self.fps
        
        logger.info(f"📹 映像生成開始: {self.width}x{self.height} @ {self.fps}fps")
        
        try:
            while self.running:
                start_time = time.time()
                
                # フレームを生成
                pil_image = self.create_animated_frame()
                
                # PILからOpenCVフォーマットに変換
                cv_image = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)
                
                # フレームをパイプに書き込み
                try:
                    output_pipe.stdin.write(cv_image.tobytes())
                    output_pipe.stdin.flush()
                except BrokenPipeError:
                    logger.warning("⚠️ パイプが切断されました")
                    break
                except Exception as e:
                    logger.error(f"❌ フレーム送信エラー: {e}")
                    break
                
                # フレームレート調整
                elapsed = time.time() - start_time
                sleep_time = frame_duration - elapsed
                if sleep_time > 0:
                    time.sleep(sleep_time)
                
        except Exception as e:
            logger.error(f"❌ 映像生成エラー: {e}")
        finally:
            self.running = False
            logger.info("📹 映像生成終了")
    
    def stop(self):
        """映像生成を停止"""
        self.running = False

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

def check_mediamtx():
    """mediamtxがインストールされているかチェック"""
    try:
        result = subprocess.run(['which', 'mediamtx'], capture_output=True, text=True)
        if result.returncode == 0:
            return True
        
        # /usr/local/binも確認
        if os.path.exists('/usr/local/bin/mediamtx'):
            return True
            
        return False
    except:
        return False

def install_mediamtx():
    """mediamtxをインストール"""
    try:
        logger.info("📦 mediamtxをインストールしています...")
        
        # アーキテクチャを確認
        arch_result = subprocess.run(['uname', '-m'], capture_output=True, text=True)
        arch = arch_result.stdout.strip()
        
        if arch == 'aarch64' or arch == 'arm64':
            download_url = "https://github.com/bluenviron/mediamtx/releases/latest/download/mediamtx_v1.5.1_linux_arm64v8.tar.gz"
        elif 'arm' in arch:
            download_url = "https://github.com/bluenviron/mediamtx/releases/latest/download/mediamtx_v1.5.1_linux_armv7.tar.gz"
        else:
            download_url = "https://github.com/bluenviron/mediamtx/releases/latest/download/mediamtx_v1.5.1_linux_amd64.tar.gz"
        
        # ダウンロードとインストール
        commands = [
            f"wget -O /tmp/mediamtx.tar.gz {download_url}",
            "cd /tmp && tar -xzf mediamtx.tar.gz",
            "sudo mv /tmp/mediamtx /usr/local/bin/",
            "sudo chmod +x /usr/local/bin/mediamtx"
        ]
        
        for cmd in commands:
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            if result.returncode != 0:
                logger.error(f"❌ コマンド実行エラー: {cmd}")
                logger.error(f"STDERR: {result.stderr}")
                return False
        
        logger.info("✅ mediamtxのインストールが完了しました")
        return True
        
    except Exception as e:
        logger.error(f"❌ mediamtxインストールエラー: {e}")
        return False

def create_mediamtx_config():
    """mediamtx設定ファイルを作成"""
    config = """
# mediamtx configuration for RTSP streaming

# General settings
logLevel: info
logDestinations: [stdout]
logFile: ""

# API settings
api: yes
apiAddress: 127.0.0.1:9997

# RTSP settings
rtspAddress: :8554
protocols: [tcp]
encryption: "no"
serverKey: ""
serverCert: ""

# Path settings
paths:
  live:
    runOnInit: ""
    runOnInitRestart: no
    runOnDemand: ""
    runOnDemandRestart: no
    runOnDemandStartTimeout: 10s
    runOnDemandCloseAfter: 10s
    runOnReady: ""
    runOnReadyRestart: no
    runOnNotReady: ""
    runOnNotReadyRestart: no
    source: publisher
    sourceFingerprint: ""
    sourceOnDemand: no
    sourceOnDemandStartTimeout: 10s
    sourceOnDemandCloseAfter: 10s
    disablePublisherOverride: no
    fallback: ""
    srtReadTimeout: 10s
    rtmpReadTimeout: 10s
"""
    
    try:
        with open('/tmp/mediamtx.yml', 'w') as f:
            f.write(config)
        logger.info("✅ mediamtx設定ファイルを作成しました")
        return True
    except Exception as e:
        logger.error(f"❌ 設定ファイル作成エラー: {e}")
        return False

def start_mediamtx():
    """mediamtxサーバーを開始"""
    try:
        # 設定ファイルを作成
        if not create_mediamtx_config():
            return None
        
        # mediamtxを開始
        cmd = ['/usr/local/bin/mediamtx', '/tmp/mediamtx.yml']
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        
        # 起動を待つ
        time.sleep(3)
        
        if process.poll() is None:
            logger.info("✅ mediamtxサーバーが開始されました")
            return process
        else:
            stdout, stderr = process.communicate()
            logger.error(f"❌ mediamtx開始エラー:")
            logger.error(f"STDERR: {stderr}")
            return None
            
    except Exception as e:
        logger.error(f"❌ mediamtx開始エラー: {e}")
        return None

def test_rtsp_with_mediamtx():
    """mediamtxを使用したRTSPストリーミング"""
    try:
        # mediamtxの確認とインストール
        if not check_mediamtx():
            logger.info("📦 mediamtxが見つかりません。インストールを開始します...")
            if not install_mediamtx():
                logger.error("❌ mediamtxのインストールに失敗しました")
                return
        
        # mediamtxサーバーを開始
        mediamtx_process = start_mediamtx()
        if not mediamtx_process:
            logger.error("❌ mediamtxサーバーの開始に失敗しました")
            return
        
        try:
            video_gen = VideoGenerator(width=1280, height=720, fps=20)  # 適度なFPS
            
            # FFmpegでmediamtxにストリーミング
            cmd = [
                'ffmpeg',
                '-f', 'rawvideo',
                '-pix_fmt', 'bgr24',
                '-s', '1280x720',
                '-r', '20',
                '-i', '-',
                '-c:v', 'libx264',
                '-preset', 'ultrafast',
                '-tune', 'zerolatency',
                '-pix_fmt', 'yuv420p',
                '-g', '40',
                '-keyint_min', '40',
                '-b:v', '1500k',
                '-maxrate', '2000k',
                '-bufsize', '3000k',
                '-f', 'rtsp',
                'rtsp://127.0.0.1:8554/live'
            ]
            
            logger.info("📺 FFmpeg → mediamtx RTSPストリーミングを開始しています...")
            logger.info(f"📺 コマンド: {' '.join(cmd)}")
            
            ffmpeg_process = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, 
                                            stderr=subprocess.PIPE, universal_newlines=False)
            
            # 映像生成を別スレッドで開始
            video_thread = threading.Thread(target=video_gen.generate_video_frames, args=(ffmpeg_process,))
            video_thread.daemon = True
            video_thread.start()
            
            time.sleep(5)
            if ffmpeg_process.poll() is None:
                local_ip = get_local_ip()
                logger.info(f"✅ RTSP動的映像ストリーミングが開始されました")
                logger.info(f"📺 RTSP URL: rtsp://{local_ip}:8554/live")
                logger.info("📺 VLCで上記URLを開いてテストしてください")
                logger.info("📺 Ctrl+Cで停止します")
                
                try:
                    while True:
                        time.sleep(1)
                        if ffmpeg_process.poll() is not None or mediamtx_process.poll() is not None:
                            break
                except KeyboardInterrupt:
                    logger.info("🛑 サーバーを停止しています...")
                    video_gen.stop()
                    ffmpeg_process.terminate()
                    ffmpeg_process.wait()
            else:
                stdout, stderr = ffmpeg_process.communicate()
                logger.error(f"❌ FFmpeg開始エラー:")
                if stderr:
                    logger.error(f"STDERR: {stderr.decode()}")
                    
        finally:
            # mediamtxプロセスを終了
            if mediamtx_process and mediamtx_process.poll() is None:
                mediamtx_process.terminate()
                mediamtx_process.wait()
                logger.info("🛑 mediamtxサーバーを停止しました")
            
    except Exception as e:
        logger.error(f"❌ エラー: {e}")

def main():
    """メイン関数"""
    print("🎬 mediamtx使用 動的映像RTSPサーバー")
    print("=" * 60)
    print("📝 1280x720解像度 @ 20fps")
    print("📝 Raspberry Pi 4Bでの使用を想定した設定です")
    print("📝 mediamtxを使用した本格的なRTSPサーバーです")
    print("=" * 60)
    print("⚠️  初回実行時はmediamtxの自動インストールが行われます")
    print("=" * 60)
    
    choice = input("RTSPストリーミングを開始しますか？ (y/n): ")
    
    if choice.lower() in ['y', 'yes']:
        test_rtsp_with_mediamtx()
    else:
        print("❌ 終了します")

if __name__ == "__main__":
    main()
