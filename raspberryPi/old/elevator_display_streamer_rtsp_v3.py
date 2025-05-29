#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SEC-3000H エレベーターシミュレーター 表示システム with 真のRTSPストリーミング v3.0
"""

import serial
import time
import json
import logging
import threading
import signal
import sys
import cv2
import numpy as np
from datetime import datetime
from typing import Dict, Any, Optional
from PIL import Image, ImageDraw, ImageFont
import os
import subprocess
import socket
import tempfile

# ログ設定
log_dir = os.path.expanduser('~/logs')
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, 'elevator_display_streamer.log')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

class ElevatorDisplayStreamer:
    """エレベーター表示システム with 真のRTSPストリーミング v3.0"""
    
    def __init__(self, port: str = '/dev/ttyUSB0', baudrate: int = 9600, rtsp_port: int = 8554):
        self.port = port
        self.baudrate = baudrate
        self.rtsp_port = rtsp_port
        self.serial_conn: Optional[serial.Serial] = None
        self.running = False
        self.auto_mode_enabled = False
        
        # 画像設定
        self.image_width = 1920
        self.image_height = 1080
        self.background_color = '#b2ffff'  # 指定された背景色
        self.text_color = '#000000'  # 黒色テキスト
        self.image_path = '/tmp/elevator_display.jpg'  # 一時ファイル（上書き用）
        self.video_path = '/tmp/elevator_stream.mp4'  # 動画ファイル
        
        # 自動運転モード設定
        self.auto_config = {
            'passenger_weight': 60,
            'max_passengers': 10,
            'operation_interval': 10,
            'door_open_time': 5
        }
        
        # 現在の状態
        self.current_status = {
            'current_floor': None,
            'target_floor': None,
            'door_status': 'unknown',
            'load_weight': 0,
            'passengers': 0,
            'last_communication': None,
            'is_moving': False
        }
        
        # 通信ログ
        self.communication_logs = []
        
        # RTSPストリーミング用
        self.streaming_thread = None
        self.rtsp_process = None
        self.ffmpeg_process = None
        self.image_updated = False
        
    def get_local_ip(self) -> str:
        """ローカルIPアドレスを取得"""
        try:
            # ダミー接続でローカルIPを取得
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except:
            return "127.0.0.1"
    
    def connect(self) -> bool:
        """シリアルポートに接続"""
        try:
            self.serial_conn = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_EVEN,
                stopbits=serial.STOPBITS_ONE,
                timeout=1
            )
            logger.info(f"✅ シリアルポート {self.port} に接続しました")
            return True
        except Exception as e:
            logger.error(f"❌ シリアルポート接続エラー: {e}")
            return False
    
    def disconnect(self):
        """シリアルポート切断"""
        if self.serial_conn and self.serial_conn.is_open:
            self.serial_conn.close()
            logger.info("📡 シリアルポートを切断しました")
    
    def calculate_checksum(self, data: bytes) -> int:
        """チェックサム計算"""
        total = sum(data)
        lower_byte = total & 0xFF
        upper_byte = (total >> 8) & 0xFF
        return (lower_byte + upper_byte) & 0xFF
    
    def parse_message(self, message: bytes) -> Optional[Dict[str, Any]]:
        """受信メッセージを解析"""
        try:
            if len(message) < 16 or message[0] != 0x05:  # ENQ
                return None
            
            # メッセージ解析
            station = message[1:5].decode('ascii')
            command = chr(message[5])
            data_num = message[6:10].decode('ascii')
            data_value = message[10:14].decode('ascii')
            checksum = message[14:16].decode('ascii')
            
            # データ番号を整数に変換（16進数として解析）
            data_num_int = int(data_num, 16)
            data_value_int = int(data_value, 16)
            
            return {
                'station': station,
                'command': command,
                'data_num': data_num_int,
                'data_value': data_value_int,
                'raw_data': data_value,
                'checksum': checksum,
                'timestamp': datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"❌ メッセージ解析エラー: {e}")
            return None
    
    def format_readable_message(self, parsed: Dict[str, Any]) -> str:
        """人間が読める形式でメッセージをフォーマット"""
        data_num = parsed['data_num']
        data_value = parsed['data_value']
        
        if data_num == 0x0001:  # 現在階数
            floor_name = "B1F" if data_value == 0xFFFF else f"{data_value}F"
            description = f"現在階数: {floor_name}"
        elif data_num == 0x0002:  # 行先階
            floor_name = "B1F" if data_value == 0xFFFF else f"{data_value}F"
            description = f"行先階: {floor_name}"
        elif data_num == 0x0003:  # 荷重
            description = f"荷重: {data_value}kg"
        elif data_num == 0x0010:  # 階数設定
            floor_name = "B1F" if data_value == 0xFFFF else f"{data_value}F"
            description = f"階数設定: {floor_name}"
        elif data_num == 0x0011:  # 扉制御
            if data_value == 0x0001:
                door_action = "開扉"
            elif data_value == 0x0002:
                door_action = "閉扉"
            elif data_value == 0x0000:
                door_action = "停止"
            else:
                door_action = "不明"
            description = f"扉制御: {door_action}"
        elif data_num == 0x0016:  # 階数設定（自動運転モード）
            floor_name = "B1F" if data_value == 0xFFFF else f"{data_value}F"
            description = f"階数設定: {floor_name}"
        elif data_num == 0x0017:  # 扉制御（自動運転モード）
            if data_value == 0x0001:
                door_action = "開扉"
            elif data_value == 0x0002:
                door_action = "閉扉"
            elif data_value == 0x0000:
                door_action = "停止"
            else:
                door_action = "不明"
            description = f"扉制御: {door_action}"
        else:
            description = f"データ番号: {data_num:04X}"
        
        return f"ENQ(05) 局番号:{parsed['station']} CMD:{parsed['command']} {description} データ:{parsed['raw_data']} チェックサム:{parsed['checksum']}"
    
    def send_response(self, station: str, is_ack: bool = True) -> bool:
        """応答送信"""
        try:
            if not self.serial_conn or not self.serial_conn.is_open:
                return False
            
            # ACK/NAK応答作成
            response = bytearray()
            response.append(0x06 if is_ack else 0x15)  # ACK or NAK
            response.extend(station.encode('ascii'))
            
            self.serial_conn.write(response)
            
            response_type = "ACK" if is_ack else "NAK"
            hex_data = response.hex().upper()
            logger.info(f"📤 送信: {response_type}({response[0]:02X}) 局番号:{station} | HEX: {hex_data}")
            
            return True
        except Exception as e:
            logger.error(f"❌ 応答送信エラー: {e}")
            return False
    
    def create_display_image(self):
        """表示用画像を生成"""
        try:
            # PIL画像を作成
            img = Image.new('RGB', (self.image_width, self.image_height), self.background_color)
            draw = ImageDraw.Draw(img)
            
            # フォントサイズを大きく設定（遠くから見えるように）
            try:
                # システムフォントを試行
                font_size = 200  # 非常に大きなフォントサイズ
                font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_size)
            except:
                try:
                    # 代替フォント
                    font = ImageFont.truetype("/usr/share/fonts/TTF/arial.ttf", font_size)
                except:
                    # デフォルトフォント（サイズ指定なし）
                    font = ImageFont.load_default()
                    logger.warning("⚠️ システムフォントが見つかりません。デフォルトフォントを使用します")
            
            # 表示テキストを決定
            current_floor = self.current_status.get('current_floor', '---')
            target_floor = self.current_status.get('target_floor', None)
            
            # 移動中かどうかを判定
            if target_floor and target_floor != current_floor and target_floor != '---':
                # 移動中: 現在階 ⇒ 行先階
                display_text = f"{current_floor} ⇒ {target_floor}"
                self.current_status['is_moving'] = True
            else:
                # 停止中: 現在階のみ
                display_text = current_floor
                self.current_status['is_moving'] = False
            
            # テキストサイズを取得
            bbox = draw.textbbox((0, 0), display_text, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            
            # 中央に配置
            x = (self.image_width - text_width) // 2
            y = (self.image_height - text_height) // 2
            
            # テキストを描画
            draw.text((x, y), display_text, fill=self.text_color, font=font)
            
            # 画像を保存（上書き）
            img.save(self.image_path, 'JPEG', quality=95)
            
            self.image_updated = True
            logger.info(f"🖼️ 表示画像を更新: {display_text}")
            
        except Exception as e:
            logger.error(f"❌ 画像生成エラー: {e}")
    
    def create_video_from_image(self):
        """画像から動画を作成（RTSPストリーミング用）"""
        try:
            if not os.path.exists(self.image_path):
                self.create_display_image()
            
            # FFmpegで画像から動画を作成
            ffmpeg_cmd = [
                'ffmpeg',
                '-y',  # 上書き
                '-loop', '1',  # ループ
                '-i', self.image_path,  # 入力画像
                '-c:v', 'libx264',  # H.264エンコーダ
                '-preset', 'ultrafast',  # 高速エンコード
                '-tune', 'stillimage',  # 静止画用最適化
                '-pix_fmt', 'yuv420p',  # ピクセルフォーマット
                '-r', '30',  # フレームレート
                '-t', '10',  # 10秒の動画
                self.video_path
            ]
            
            result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
            if result.returncode == 0:
                logger.info(f"✅ 動画ファイルを作成: {self.video_path}")
                return True
            else:
                logger.error(f"❌ FFmpeg動画作成エラー: {result.stderr}")
                return False
                
        except Exception as e:
            logger.error(f"❌ 動画作成エラー: {e}")
            return False
    
    def start_ffmpeg_rtsp_server(self):
        """FFmpegを使用してRTSPサーバーを開始"""
        try:
            # まず動画ファイルを作成
            if not self.create_video_from_image():
                return False
            
            # FFmpegでRTSPサーバーを開始
            ffmpeg_cmd = [
                'ffmpeg',
                '-re',  # リアルタイム読み込み
                '-stream_loop', '-1',  # 無限ループ
                '-i', self.video_path,  # 入力動画
                '-c:v', 'copy',  # ビデオコーデックコピー
                '-f', 'rtsp',  # RTSP出力
                f'rtsp://0.0.0.0:{self.rtsp_port}/live'
            ]
            
            logger.info("📺 FFmpegでRTSPサーバーを開始しています...")
            logger.info(f"📺 コマンド: {' '.join(ffmpeg_cmd)}")
            
            # FFmpegプロセスを開始
            self.ffmpeg_process = subprocess.Popen(
                ffmpeg_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True
            )
            
            # プロセスが正常に開始されたかチェック
            time.sleep(3)
            if self.ffmpeg_process.poll() is None:
                local_ip = self.get_local_ip()
                logger.info(f"✅ FFmpeg RTSPサーバーが開始されました")
                logger.info(f"📺 RTSP URL: rtsp://{local_ip}:{self.rtsp_port}/live")
                return True
            else:
                stdout, stderr = self.ffmpeg_process.communicate()
                logger.error(f"❌ FFmpeg開始エラー:")
                logger.error(f"STDOUT: {stdout}")
                logger.error(f"STDERR: {stderr}")
                return False
                
        except Exception as e:
            logger.error(f"❌ FFmpeg RTSPサーバー開始エラー: {e}")
            return False
    
    def start_vlc_rtsp_server(self):
        """VLCを使用してRTSPサーバーを開始"""
        try:
            if not os.path.exists(self.image_path):
                self.create_display_image()
            
            # VLCでRTSPサーバーを開始
            vlc_cmd = [
                'cvlc',  # コマンドライン版VLC
                '--intf', 'dummy',  # インターフェースなし
                '--loop',  # ループ再生
                self.image_path,  # 入力画像
                '--sout', f'#transcode{{vcodec=h264,vb=2000,fps=30}}:rtp{{sdp=rtsp://0.0.0.0:{self.rtsp_port}/live}}'
            ]
            
            logger.info("📺 VLCでRTSPサーバーを開始しています...")
            logger.info(f"📺 コマンド: {' '.join(vlc_cmd)}")
            
            # VLCプロセスを開始
            self.rtsp_process = subprocess.Popen(
                vlc_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True
            )
            
            # プロセスが正常に開始されたかチェック
            time.sleep(3)
            if self.rtsp_process.poll() is None:
                local_ip = self.get_local_ip()
                logger.info(f"✅ VLC RTSPサーバーが開始されました")
                logger.info(f"📺 RTSP URL: rtsp://{local_ip}:{self.rtsp_port}/live")
                return True
            else:
                stdout, stderr = self.rtsp_process.communicate()
                logger.error(f"❌ VLC開始エラー:")
                logger.error(f"STDOUT: {stdout}")
                logger.error(f"STDERR: {stderr}")
                return False
                
        except Exception as e:
            logger.error(f"❌ VLC RTSPサーバー開始エラー: {e}")
            return False
    
    def start_gstreamer_rtsp_server_v2(self):
        """GStreamer RTSPサーバー v2（改良版）"""
        try:
            if not os.path.exists(self.image_path):
                self.create_display_image()
            
            # GStreamerでRTSPサーバーを開始（改良版）
            gst_cmd = [
                'gst-launch-1.0',
                '-v',
                'multifilesrc',
                f'location={self.image_path}',
                'loop=true',
                'caps=image/jpeg,framerate=30/1',
                '!',
                'jpegdec',
                '!',
                'videoconvert',
                '!',
                'videoscale',
                '!',
                f'video/x-raw,width={self.image_width},height={self.image_height}',
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
                f'port={self.rtsp_port}',
                'auto-multicast=true'
            ]
            
            logger.info("📺 GStreamer RTSPサーバー v2を開始しています...")
            logger.info(f"📺 コマンド: {' '.join(gst_cmd)}")
            
            # GStreamerプロセスを開始
            self.rtsp_process = subprocess.Popen(
                gst_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True
            )
            
            # プロセスが正常に開始されたかチェック
            time.sleep(3)
            if self.rtsp_process.poll() is None:
                local_ip = self.get_local_ip()
                logger.info(f"✅ GStreamer RTSPサーバー v2が開始されました")
                logger.info(f"📺 UDP URL: udp://{local_ip}:{self.rtsp_port}")
                logger.info(f"📺 RTP URL: rtp://{local_ip}:{self.rtsp_port}")
                return True
            else:
                stdout, stderr = self.rtsp_process.communicate()
                logger.error(f"❌ GStreamer v2開始エラー:")
                logger.error(f"STDOUT: {stdout}")
                logger.error(f"STDERR: {stderr}")
                return False
                
        except Exception as e:
            logger.error(f"❌ GStreamer RTSPサーバー v2開始エラー: {e}")
            return False
    
    def start_http_streaming(self):
        """HTTPストリーミングを開始（代替方法）"""
        try:
            import http.server
            import socketserver
            from urllib.parse import urlparse
            
            class ImageHandler(http.server.SimpleHTTPRequestHandler):
                def __init__(self, *args, **kwargs):
                    super().__init__(*args, directory='/tmp', **kwargs)
                
                def do_GET(self):
                    if self.path == '/stream.jpg' or self.path == '/elevator_display.jpg':
                        self.send_response(200)
                        self.send_header('Content-type', 'image/jpeg')
                        self.send_header('Cache-Control', 'no-cache')
                        self.send_header('Refresh', '1')  # 1秒ごとに更新
                        self.end_headers()
                        
                        try:
                            with open('/tmp/elevator_display.jpg', 'rb') as f:
                                self.wfile.write(f.read())
                        except:
                            pass
                    else:
                        super().do_GET()
            
            def start_server():
                with socketserver.TCPServer(("", 8080), ImageHandler) as httpd:
                    logger.info("📺 HTTPストリーミングサーバーを開始しました")
                    local_ip = self.get_local_ip()
                    logger.info(f"📺 HTTP URL: http://{local_ip}:8080/elevator_display.jpg")
                    httpd.serve_forever()
            
            # HTTPサーバーを別スレッドで開始
            http_thread = threading.Thread(target=start_server, daemon=True)
            http_thread.start()
            
            return True
            
        except Exception as e:
            logger.error(f"❌ HTTPストリーミング開始エラー: {e}")
            return False
    
    def start_rtsp_streaming(self):
        """RTSPストリーミングを開始"""
        def streaming_loop():
            try:
                # 初期画像を作成
                self.create_display_image()
                
                # 複数の方法を試行
                streaming_started = False
                
                # 方法1: FFmpegでRTSPサーバー
                if not streaming_started:
                    logger.info("📺 方法1: FFmpegでRTSPサーバーを試行...")
                    streaming_started = self.start_ffmpeg_rtsp_server()
                
                # 方法2: VLCでRTSPサーバー
                if not streaming_started:
                    logger.info("📺 方法2: VLCでRTSPサーバーを試行...")
                    streaming_started = self.start_vlc_rtsp_server()
                
                # 方法3: GStreamer RTSPサーバー v2
                if not streaming_started:
                    logger.info("📺 方法3: GStreamer RTSPサーバー v2を試行...")
                    streaming_started = self.start_gstreamer_rtsp_server_v2()
                
                # 方法4: HTTPストリーミング（代替）
                if not streaming_started:
                    logger.info("📺 方法4: HTTPストリーミング（代替）を試行...")
                    streaming_started = self.start_http_streaming()
                else:
                    # RTSPが成功した場合でもHTTPも開始
                    logger.info("📺 追加: HTTPストリーミングも開始...")
                    self.start_http_streaming()
                
                if not streaming_started:
                    logger.error("❌ すべてのストリーミング方法が失敗しました")
                    logger.info("💡 画像ファイルのみ生成します")
                
                # 画像更新ループ
                while self.running:
                    try:
                        # 定期的に画像を更新
                        if self.image_updated:
                            self.create_display_image()
                            # 動画も更新（RTSPストリーミング用）
                            if self.ffmpeg_process and self.ffmpeg_process.poll() is None:
                                self.create_video_from_image()
                            self.image_updated = False
                        
                        time.sleep(1)  # 1秒間隔で更新
                        
                    except Exception as e:
                        logger.error(f"❌ 画像更新エラー: {e}")
                        time.sleep(1)
                
            except Exception as e:
                logger.error(f"❌ ストリーミングループエラー: {e}")
        
        self.streaming_thread = threading.Thread(target=streaming_loop, daemon=True)
        self.streaming_thread.start()
    
    def update_status_from_message(self, parsed: Dict[str, Any]):
        """受信メッセージから状態を更新"""
        data_num = parsed['data_num']
        data_value = parsed['data_value']
        status_changed = False
        
        if data_num == 0x0001:  # 現在階数
            floor_name = "B1F" if data_value == 0xFFFF else f"{data_value}F"
            if self.current_status['current_floor'] != floor_name:
                self.current_status['current_floor'] = floor_name
                status_changed = True
                logger.info(f"🏢 現在階数を更新: {floor_name} (データ値: {data_value:04X})")
        elif data_num == 0x0002:  # 行先階
            floor_name = "B1F" if data_value == 0xFFFF else f"{data_value}F"
            if self.current_status['target_floor'] != floor_name:
                self.current_status['target_floor'] = floor_name
                status_changed = True
                logger.info(f"🎯 行先階を更新: {floor_name} (データ値: {data_value:04X})")
        elif data_num == 0x0003:  # 荷重
            if self.current_status['load_weight'] != data_value:
                self.current_status['load_weight'] = data_value
                self.current_status['passengers'] = max(0, data_value // self.auto_config['passenger_weight'])
                logger.info(f"⚖️ 荷重を更新: {data_value}kg, 乗客数: {self.current_status['passengers']}人")
        elif data_num == 0x0010:  # 階数設定
            floor_name = "B1F" if data_value == 0xFFFF else f"{data_value}F"
            if self.current_status['current_floor'] != floor_name:
                self.current_status['current_floor'] = floor_name
                status_changed = True
                logger.info(f"🏢 階数設定により現在階数を更新: {floor_name} (データ値: {data_value:04X})")
        elif data_num == 0x0016:  # 階数設定（自動運転モード）
            floor_name = "B1F" if data_value == 0xFFFF else f"{data_value}F"
            if self.current_status['current_floor'] != floor_name:
                self.current_status['current_floor'] = floor_name
                status_changed = True
                logger.info(f"🏢 自動運転モード階数設定により現在階数を更新: {floor_name} (データ値: {data_value:04X})")
        
        self.current_status['last_communication'] = datetime.now().isoformat()
        
        # 状態が変更された場合、画像を更新
        if status_changed:
            self.image_updated = True
    
    def add_communication_log(self, direction: str, message: str, result: str = "success"):
        """通信ログを追加"""
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'direction': direction,
            'message': message,
            'result': result
        }
        
        self.communication_logs.append(log_entry)
        
        # ログの最大数を制限（最新500件）
        if len(self.communication_logs) > 500:
            self.communication_logs = self.communication_logs[-500:]
    
    def simulate_passenger_activity(self, floor: str) -> Dict[str, int]:
        """乗客の出入りをシミュレート"""
        import random
        
        current_passengers = self.current_status['passengers']
        
        # 降車人数（現在の乗客数まで）
        exiting = random.randint(0, current_passengers)
        
        # 乗車人数（残り容量まで）
        remaining_capacity = self.auto_config['max_passengers'] - (current_passengers - exiting)
        entering = random.randint(0, min(remaining_capacity, self.auto_config['max_passengers']))
        
        new_passengers = current_passengers - exiting + entering
        new_weight = new_passengers * self.auto_config['passenger_weight']
        
        logger.info(f"🏢 {floor}: 乗車 {entering}人, 降車 {exiting}人 → 総乗客数 {new_passengers}人 ({new_weight}kg)")
        
        return {
            'entering':
