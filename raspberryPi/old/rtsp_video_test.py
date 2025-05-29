#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
動的映像生成RTSPテストサーバー
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

def test_ffmpeg_video_udp():
    """FFmpegで動的映像UDPストリーミング"""
    try:
        video_gen = VideoGenerator(width=1280, height=720, fps=30)
        
        # FFmpegでUDPストリーミング
        cmd = [
            'ffmpeg',
            '-f', 'rawvideo',
            '-pix_fmt', 'bgr24',
            '-s', '1280x720',
            '-r', '30',
            '-i', '-',
            '-c:v', 'libx264',
            '-preset', 'fast',
            '-tune', 'zerolatency',
            '-pix_fmt', 'yuv420p',
            '-g', '60',
            '-keyint_min', '60',
            '-b:v', '2000k',
            '-maxrate', '2500k',
            '-bufsize', '5000k',
            '-f', 'mpegts',
            'udp://0.0.0.0:8554'
        ]
        
        logger.info("📺 FFmpeg 動的映像UDPストリーミングを開始しています...")
        logger.info(f"📺 コマンド: {' '.join(cmd)}")
        
        process = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, 
                                 stderr=subprocess.PIPE, universal_newlines=False)
        
        # 映像生成を別スレッドで開始
        video_thread = threading.Thread(target=video_gen.generate_video_frames, args=(process,))
        video_thread.daemon = True
        video_thread.start()
        
        time.sleep(3)
        if process.poll() is None:
            local_ip = get_local_ip()
            logger.info(f"✅ FFmpeg 動的映像UDPストリーミングが開始されました")
            logger.info(f"📺 UDP URL: udp://{local_ip}:8554")
            logger.info("📺 VLCで上記URLを開いてテストしてください")
            logger.info("📺 Ctrl+Cで停止します")
            
            try:
                while True:
                    time.sleep(1)
                    if process.poll() is not None:
                        break
            except KeyboardInterrupt:
                logger.info("🛑 サーバーを停止しています...")
                video_gen.stop()
                process.terminate()
                process.wait()
        else:
            stdout, stderr = process.communicate()
            logger.error(f"❌ FFmpeg開始エラー:")
            if stderr:
                logger.error(f"STDERR: {stderr.decode()}")
            
    except Exception as e:
        logger.error(f"❌ エラー: {e}")

def test_opencv_video_udp():
    """OpenCVで動的映像UDPストリーミング（軽量版）"""
    try:
        video_gen = VideoGenerator(width=1280, height=720, fps=20)  # 少し低いFPSで負荷軽減
        
        # FFmpegでUDPストリーミング（軽量設定）
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
            '-threads', '2',
            '-f', 'mpegts',
            'udp://0.0.0.0:8555'
        ]
        
        logger.info("📺 軽量版 動的映像UDPストリーミングを開始しています...")
        logger.info(f"📺 コマンド: {' '.join(cmd)}")
        
        process = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, 
                                 stderr=subprocess.PIPE, universal_newlines=False)
        
        # 映像生成を別スレッドで開始
        video_thread = threading.Thread(target=video_gen.generate_video_frames, args=(process,))
        video_thread.daemon = True
        video_thread.start()
        
        time.sleep(3)
        if process.poll() is None:
            local_ip = get_local_ip()
            logger.info(f"✅ 軽量版 動的映像UDPストリーミングが開始されました")
            logger.info(f"📺 UDP URL: udp://{local_ip}:8555")
            logger.info("📺 VLCで上記URLを開いてテストしてください")
            logger.info("📺 Ctrl+Cで停止します")
            
            try:
                while True:
                    time.sleep(1)
                    if process.poll() is not None:
                        break
            except KeyboardInterrupt:
                logger.info("🛑 サーバーを停止しています...")
                video_gen.stop()
                process.terminate()
                process.wait()
        else:
            stdout, stderr = process.communicate()
            logger.error(f"❌ FFmpeg開始エラー:")
            if stderr:
                logger.error(f"STDERR: {stderr.decode()}")
            
    except Exception as e:
        logger.error(f"❌ エラー: {e}")

def test_simple_video_udp():
    """シンプルな動的映像UDPストリーミング（最軽量版）"""
    try:
        video_gen = VideoGenerator(width=1280, height=720, fps=15)  # さらに低いFPS
        
        # 最軽量設定のFFmpeg
        cmd = [
            'ffmpeg',
            '-f', 'rawvideo',
            '-pix_fmt', 'bgr24',
            '-s', '1280x720',
            '-r', '15',
            '-i', '-',
            '-c:v', 'libx264',
            '-preset', 'ultrafast',
            '-tune', 'zerolatency',
            '-crf', '28',
            '-pix_fmt', 'yuv420p',
            '-g', '30',
            '-keyint_min', '30',
            '-threads', '1',
            '-f', 'mpegts',
            'udp://0.0.0.0:8556'
        ]
        
        logger.info("📺 シンプル版 動的映像UDPストリーミングを開始しています...")
        logger.info(f"📺 コマンド: {' '.join(cmd)}")
        
        process = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, 
                                 stderr=subprocess.PIPE, universal_newlines=False)
        
        # 映像生成を別スレッドで開始
        video_thread = threading.Thread(target=video_gen.generate_video_frames, args=(process,))
        video_thread.daemon = True
        video_thread.start()
        
        time.sleep(3)
        if process.poll() is None:
            local_ip = get_local_ip()
            logger.info(f"✅ シンプル版 動的映像UDPストリーミングが開始されました")
            logger.info(f"📺 UDP URL: udp://{local_ip}:8556")
            logger.info("📺 VLCで上記URLを開いてテストしてください")
            logger.info("📺 Ctrl+Cで停止します")
            
            try:
                while True:
                    time.sleep(1)
                    if process.poll() is not None:
                        break
            except KeyboardInterrupt:
                logger.info("🛑 サーバーを停止しています...")
                video_gen.stop()
                process.terminate()
                process.wait()
        else:
            stdout, stderr = process.communicate()
            logger.error(f"❌ FFmpeg開始エラー:")
            if stderr:
                logger.error(f"STDERR: {stderr.decode()}")
            
    except Exception as e:
        logger.error(f"❌ エラー: {e}")

def test_http_video_stream():
    """HTTPで動的映像ストリーミング（最も確実）"""
    try:
        import http.server
        import socketserver
        import threading
        import io
        
        video_gen = VideoGenerator(width=1280, height=720, fps=10)  # HTTPに適したFPS
        
        class VideoStreamHandler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == '/video.mjpg':
                    self.send_response(200)
                    self.send_header('Content-Type', 'multipart/x-mixed-replace; boundary=frame')
                    self.send_header('Cache-Control', 'no-cache')
                    self.end_headers()
                    
                    try:
                        while video_gen.running:
                            # フレームを生成
                            pil_image = video_gen.create_animated_frame()
                            
                            # JPEGに変換
                            img_buffer = io.BytesIO()
                            pil_image.save(img_buffer, format='JPEG', quality=85)
                            img_data = img_buffer.getvalue()
                            
                            # MJPEGストリーム形式で送信
                            self.wfile.write(b'--frame\r\n')
                            self.send_header('Content-Type', 'image/jpeg')
                            self.send_header('Content-Length', str(len(img_data)))
                            self.end_headers()
                            self.wfile.write(img_data)
                            self.wfile.write(b'\r\n')
                            
                            time.sleep(1.0 / video_gen.fps)
                            
                    except Exception as e:
                        logger.error(f"❌ ストリーミングエラー: {e}")
                        
                elif self.path == '/':
                    # 簡単なHTMLページ
                    html = f"""
                    <!DOCTYPE html>
                    <html>
                    <head>
                        <title>動的映像ストリーミング</title>
                        <style>
                            body {{ font-family: Arial, sans-serif; text-align: center; margin: 50px; }}
                            img {{ border: 2px solid #333; }}
                        </style>
                    </head>
                    <body>
                        <h1>🎬 動的映像ストリーミング</h1>
                        <p>解像度: 1280x720 @ {video_gen.fps}fps</p>
                        <img src="/video.mjpg" alt="Video Stream" width="640" height="360">
                        <p>VLCで視聴する場合: <code>http://{get_local_ip()}:8080/video.mjpg</code></p>
                    </body>
                    </html>
                    """
                    self.send_response(200)
                    self.send_header('Content-Type', 'text/html')
                    self.end_headers()
                    self.wfile.write(html.encode())
                else:
                    self.send_error(404)
        
        # 映像生成を開始
        video_gen.running = True
        
        # HTTPサーバーを開始
        with socketserver.TCPServer(("", 8080), VideoStreamHandler) as httpd:
            local_ip = get_local_ip()
            logger.info("✅ HTTP動的映像ストリーミングサーバーが開始されました")
            logger.info(f"📺 ブラウザURL: http://{local_ip}:8080/")
            logger.info(f"📺 VLC URL: http://{local_ip}:8080/video.mjpg")
            logger.info("📺 ブラウザまたはVLCで上記URLを開いてテストしてください")
            logger.info("📺 Ctrl+Cで停止します")
            
            try:
                httpd.serve_forever()
            except KeyboardInterrupt:
                logger.info("🛑 サーバーを停止しています...")
                video_gen.stop()
                
    except Exception as e:
        logger.error(f"❌ HTTPストリーミング開始エラー: {e}")

def main():
    """メイン関数"""
    print("🎬 動的映像ストリーミングテストサーバー")
    print("=" * 60)
    print("1. 標準品質 UDP (30fps, 2Mbps) - UDP:8554")
    print("2. 軽量版 UDP (20fps, 1.5Mbps) - UDP:8555")
    print("3. 最軽量版 UDP (15fps, CRF28) - UDP:8556")
    print("4. HTTP ストリーミング (10fps, MJPEG) - 最も確実")
    print("=" * 60)
    print("📝 すべて1280x720解像度で出力されます")
    print("📝 Raspberry Pi 4Bでの使用を想定した設定です")
    print("📝 UDPが見れない場合は4番を選択してください")
    print("=" * 60)
    
    choice = input("テスト方法を選択してください (1-4): ")
    
    if choice == "1":
        test_ffmpeg_video_udp()
    elif choice == "2":
        test_opencv_video_udp()
    elif choice == "3":
        test_simple_video_udp()
    elif choice == "4":
        test_http_video_stream()
    else:
        print("❌ 無効な選択です")

if __name__ == "__main__":
    main()
