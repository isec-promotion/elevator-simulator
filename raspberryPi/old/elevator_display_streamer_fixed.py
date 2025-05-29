#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SEC-3000H エレベーターシミュレーター 表示システム with RTSPストリーミング (修正版)
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
    """エレベーター表示システム with RTSPストリーミング (修正版)"""
    
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
        self.gstreamer_process = None
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
    
    def start_gstreamer_rtsp_server(self):
        """GStreamerを使用してRTSPサーバーを開始"""
        try:
            # GStreamerのRTSPサーバーコマンド
            gst_command = [
                'gst-launch-1.0',
                '-v',
                'multifilesrc',
                f'location={self.image_path}',
                'loop=true',
                '!',
                'jpegdec',
                '!',
                'videoconvert',
                '!',
                'videoscale',
                '!',
                f'video/x-raw,width={self.image_width},height={self.image_height},framerate=30/1',
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
                'host=127.0.0.1',
                f'port={self.rtsp_port}'
            ]
            
            logger.info("📺 GStreamerでRTSPストリーミングを開始しています...")
            logger.info(f"📺 コマンド: {' '.join(gst_command)}")
            
            # GStreamerプロセスを開始
            self.gstreamer_process = subprocess.Popen(
                gst_command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True
            )
            
            # プロセスが正常に開始されたかチェック
            time.sleep(2)
            if self.gstreamer_process.poll() is None:
                local_ip = self.get_local_ip()
                logger.info(f"✅ GStreamerストリーミングが開始されました")
                logger.info(f"📺 RTSP URL: rtsp://{local_ip}:{self.rtsp_port}/")
                logger.info(f"📺 UDP URL: udp://@:{self.rtsp_port}")
                return True
            else:
                stdout, stderr = self.gstreamer_process.communicate()
                logger.error(f"❌ GStreamer開始エラー:")
                logger.error(f"STDOUT: {stdout}")
                logger.error(f"STDERR: {stderr}")
                return False
                
        except Exception as e:
            logger.error(f"❌ GStreamerストリーミング開始エラー: {e}")
            return False
    
    def start_simple_rtsp_server(self):
        """シンプルなRTSPサーバーを開始（代替方法）"""
        try:
            # gst-rtsp-serverを使用
            rtsp_command = [
                'gst-rtsp-server',
                '--port', str(self.rtsp_port),
                '--gst-debug-level=2'
            ]
            
            logger.info("📺 gst-rtsp-serverでRTSPサーバーを開始しています...")
            
            # RTSPサーバープロセスを開始
            self.gstreamer_process = subprocess.Popen(
                rtsp_command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True
            )
            
            time.sleep(2)
            if self.gstreamer_process.poll() is None:
                local_ip = self.get_local_ip()
                logger.info(f"✅ RTSPサーバーが開始されました")
                logger.info(f"📺 RTSP URL: rtsp://{local_ip}:{self.rtsp_port}/test")
                return True
            else:
                stdout, stderr = self.gstreamer_process.communicate()
                logger.error(f"❌ RTSPサーバー開始エラー:")
                logger.error(f"STDOUT: {stdout}")
                logger.error(f"STDERR: {stderr}")
                return False
                
        except Exception as e:
            logger.error(f"❌ RTSPサーバー開始エラー: {e}")
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
                
                # 方法1: GStreamerでRTSPストリーミング
                if not streaming_started:
                    logger.info("📺 方法1: GStreamerでRTSPストリーミングを試行...")
                    streaming_started = self.start_gstreamer_rtsp_server()
                
                # 方法2: gst-rtsp-server
                if not streaming_started:
                    logger.info("📺 方法2: gst-rtsp-serverを試行...")
                    streaming_started = self.start_simple_rtsp_server()
                
                # 方法3: HTTPストリーミング（代替）
                if not streaming_started:
                    logger.info("📺 方法3: HTTPストリーミング（代替）を試行...")
                    streaming_started = self.start_http_streaming()
                
                if not streaming_started:
                    logger.error("❌ すべてのストリーミング方法が失敗しました")
                    logger.info("💡 画像ファイルのみ生成します")
                
                # 画像更新ループ
                while self.running:
                    try:
                        # 定期的に画像を更新
                        if self.image_updated:
                            self.create_display_image()
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
            'entering': entering,
            'exiting': exiting,
            'total_passengers': new_passengers,
            'total_weight': new_weight
        }
    
    def process_auto_mode_logic(self, parsed: Dict[str, Any]):
        """自動運転モードのロジック処理"""
        if not self.auto_mode_enabled:
            return
        
        data_num = parsed['data_num']
        
        # 扉開放時の乗客出入りシミュレーション
        if data_num == 0x0011 and parsed['data_value'] == 0x0001:  # 開扉
            current_floor = self.current_status.get('current_floor', '1F')
            
            # 少し待ってから乗客の出入りをシミュレート
            def delayed_passenger_simulation():
                time.sleep(2)  # 扉が開くまで待機
                passenger_activity = self.simulate_passenger_activity(current_floor)
                
                # 新しい荷重を記録
                self.current_status['passengers'] = passenger_activity['total_passengers']
                self.current_status['load_weight'] = passenger_activity['total_weight']
                
                logger.info(f"🤖 自動運転モード: {current_floor}での乗客出入り完了")
            
            # 別スレッドで実行
            threading.Thread(target=delayed_passenger_simulation, daemon=True).start()
    
    def listen(self):
        """メッセージ受信ループ"""
        logger.info("🎧 メッセージ受信を開始します...")
        
        while self.running:
            try:
                if not self.serial_conn or not self.serial_conn.is_open:
                    time.sleep(1)
                    continue
                
                # データ受信
                if self.serial_conn.in_waiting > 0:
                    data = self.serial_conn.read(self.serial_conn.in_waiting)
                    
                    if len(data) >= 16:  # 最小メッセージ長
                        parsed = self.parse_message(data)
                        
                        if parsed:
                            # 人間が読める形式でログ出力
                            readable_msg = self.format_readable_message(parsed)
                            logger.info(f"📨 受信: {readable_msg}")
                            
                            # 通信ログに追加
                            self.add_communication_log("receive", readable_msg)
                            
                            # 状態更新
                            self.update_status_from_message(parsed)
                            
                            # 自動運転モードのロジック処理
                            self.process_auto_mode_logic(parsed)
                            
                            # 正常応答送信（受信した局番号で応答）
                            response_station = "0002" if parsed['station'] == "0002" else "0001"
                            self.send_response(response_station, True)
                        else:
                            logger.warning(f"⚠️ 無効なメッセージ: {data.hex()}")
                            self.add_communication_log("receive", f"無効なメッセージ: {data.hex()}", "error")
                
                time.sleep(0.1)  # CPU使用率を下げる
                
            except Exception as e:
                logger.error(f"❌ 受信エラー: {e}")
                self.add_communication_log("system", f"受信エラー: {e}", "error")
                time.sleep(1)
    
    def enable_auto_mode(self):
        """自動運転モードを有効化"""
        self.auto_mode_enabled = True
        logger.info("🤖 自動運転モードを有効にしました")
        self.add_communication_log("system", "自動運転モード有効化")
    
    def disable_auto_mode(self):
        """自動運転モードを無効化"""
        self.auto_mode_enabled = False
        logger.info("🛑 自動運転モードを無効にしました")
        self.add_communication_log("system", "自動運転モード無効化")
    
    def get_status(self) -> Dict[str, Any]:
        """現在の状態を取得"""
        local_ip = self.get_local_ip()
        return {
            'auto_mode_enabled': self.auto_mode_enabled,
            'current_status': self.current_status.copy(),
            'auto_config': self.auto_config.copy(),
            'communication_logs': self.communication_logs[-10:],  # 最新10件
            'connection_status': 'connected' if (self.serial_conn and self.serial_conn.is_open) else 'disconnected',
            'image_path': self.image_path,
            'rtsp_url': f"rtsp://{local_ip}:{self.rtsp_port}/",
            'http_url': f"http://{local_ip}:8080/elevator_display.jpg"
        }
    
    def start(self):
        """システム開始"""
        self.running = True
        
        # 初期画像を作成
        self.create_display_image()
        
        # RTSPストリーミングを開始
        self.start_rtsp_streaming()
        
        if self.connect():
            # 自動運転モードを有効化
            self.enable_auto_mode()
            
            # 受信スレッド開始
            listen_thread = threading.Thread(target=self.listen, daemon=True)
            listen_thread.start()
            
            logger.info("🚀 エレベーター表示システム with RTSPストリーミング (修正版) を開始しました")
            local_ip = self.get_local_ip()
            logger.info(f"📺 RTSP URL: rtsp://{local_ip}:{self.rtsp_port}/")
            logger.info(f"📺 HTTP URL: http://{local_ip}:8080/elevator_display.jpg")
            logger.info(f"🖼️ 画像ファイル: {self.image_path}")
            
            try:
                while self.running:
                    # 定期的に状態をログ出力
                    time.sleep(30)
                    status = self.get_status()
                    current_floor = status['current_status']['current_floor'] or '---'
                    target_floor = status['current_status']['target_floor'] or '---'
                    is_moving = status['current_status']['is_moving']
                    
                    if is_moving:
                        logger.info(f"📊 現在の状態: {current_floor} ⇒ {target_floor} (移動中), "
                                  f"乗客数={status['current_status']['passengers']}人, "
                                  f"荷重={status['current_status']['load_weight']}kg")
                    else:
                        logger.info(f"📊 現在の状態: {current_floor} (停止中), "
                                  f"乗客数={status['current_status']['passengers']}人, "
                                  f"荷重={status['current_status']['load_weight']}kg")
                    
            except KeyboardInterrupt:
                logger.info("🛑 キーボード割り込みを受信しました")
        else:
            logger.error("❌ シリアルポート接続に失敗しました")
            logger.info("💡 画像生成とストリーミングのみ継続します")
            
            try:
                while self.running:
                    time.sleep(30)
                    logger.info("📊 シリアル接続なしで動作中（画像生成・ストリーミングのみ）")
            except KeyboardInterrupt:
                logger.info("🛑 キーボード割り込みを受信しました")
    
    def stop(self):
        """システム停止"""
        self.running = False
        self.disable_auto_mode()
        self.disconnect()
        
        # GStreamerプロセスを停止
        if self.gstreamer_process:
            try:
                self.gstreamer_process.terminate()
                self.gstreamer_process.wait(timeout=5)
                logger.info("📺 GStreamerプロセスを停止しました")
            except:
                try:
                    self.gstreamer_process.kill()
                    logger.info("📺 GStreamerプロセスを強制終了しました")
                except:
                    pass
        
        logger.info("✅ エレベーター表示システムを停止しました")

def signal_handler(signum, frame):
    """シグナルハンドラー"""
    logger.info(f"🛑 シグナル {signum} を受信しました。システムを停止します...")
    if 'streamer' in globals():
        streamer.stop()
    sys.exit(0)

def main():
    """メイン関数"""
    # シグナルハンドラー設定
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    logger.info("🏢 SEC-3000H エレベーターシミュレーター 表示システム")
    logger.info("📺 RTSPストリーミング対応 v2.0 (修正版)")
    logger.info("=" * 60)
    
    # システム初期化
    global streamer
    streamer = ElevatorDisplayStreamer()
    
    try:
        streamer.start()
    except Exception as e:
        logger.error(f"❌ システムエラー: {e}")
        streamer.stop()
        sys.exit(1)

if __name__ == "__main__":
    main()
