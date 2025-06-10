#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SEC-3000H Elevator Display RTSP Server
backend-cli専用 - エレベーター案内ディスプレイ
"""

import serial
import time
import threading
import logging
import signal
import sys
import socket
from datetime import datetime
from typing import Dict, Any, Optional

from PIL import Image, ImageDraw, ImageFont
import gi
gi.require_version('Gst', '1.0')
gi.require_version('GstRtspServer', '1.0')
from gi.repository import Gst, GstRtspServer, GLib

# ── 設定 ───────────────────────────────────
WIDTH, HEIGHT, FPS = 640, 360, 15
SERIAL_PORT = '/dev/ttyUSB0'
BAUDRATE = 9600
FONT_PATH = "/usr/share/fonts/truetype/ipafont-mincho/ipam.ttf"

# ── ログ設定 ─────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ── エレベーター受信クラス ───────────────────
class ElevatorDisplayReceiver:
    """SEC-3000H エレベーター案内ディスプレイ用受信クラス"""
    def __init__(self, port: str, baudrate: int):
        self.port = port
        self.baudrate = baudrate
        self.serial_conn: Optional[serial.Serial] = None
        self.running = False
        self.current_status = {
            'current_floor': '1F', 
            'target_floor': None,
            'is_moving': False,
            'door_status': 'unknown'
        }
        self.lock = threading.Lock()
        self.recv_buffer = b''

    def connect(self) -> bool:
        try:
            self.serial_conn = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_EVEN,
                stopbits=serial.STOPBITS_ONE,
                timeout=1
            )
            logger.info(f"✅ シリアルポート {self.port} に接続")
            return True
        except Exception as e:
            logger.error(f"❌ シリアル接続エラー: {e}")
            return False

    def process_buffer(self):
        """受信バッファを処理して完全なメッセージを抽出"""
        while len(self.recv_buffer) >= 16:
            # ENQ (0x05) を探す
            idx = self.recv_buffer.find(b'\x05')
            if idx < 0:
                self.recv_buffer = b''
                return
            
            if idx > 0:
                self.recv_buffer = self.recv_buffer[idx:]
            
            if len(self.recv_buffer) < 16:
                return
            
            # 16バイトのメッセージを抽出
            packet = self.recv_buffer[:16]
            self.recv_buffer = self.recv_buffer[16:]
            
            # メッセージの妥当性をチェック
            if self.validate_packet(packet):
                self.handle_packet(packet)
            else:
                logger.warning(f"⚠️ 無効なパケット: {packet.hex().upper()}")

    def validate_packet(self, packet: bytes) -> bool:
        """パケットの妥当性をチェック"""
        try:
            if len(packet) != 16 or packet[0] != 0x05:
                return False
            
            # ASCII文字の妥当性をチェック
            station = packet[1:5].decode('ascii')
            command = chr(packet[5])
            data_num = packet[6:10].decode('ascii')
            data_value = packet[10:14].decode('ascii')
            checksum = packet[14:16].decode('ascii')
            
            # 16進数として解析可能かチェック
            int(data_num, 16)
            int(data_value, 16)
            int(checksum, 16)
            
            return True
        except (UnicodeDecodeError, ValueError):
            return False

    def handle_packet(self, data: bytes):
        """受信パケットを解析して状態を更新"""
        try:
            if len(data) < 16 or data[0] != 0x05:
                return
            
            # メッセージ解析
            station = data[1:5].decode('ascii')
            command = chr(data[5])
            data_num = data[6:10].decode('ascii')
            data_value = data[10:14].decode('ascii')
            checksum = data[14:16].decode('ascii')
            
            # データ番号を整数に変換
            data_num_int = int(data_num, 16)
            data_value_int = int(data_value, 16)
            
            # 人間が読める形式でメッセージをフォーマット
            description = self.format_readable_message(data_num_int, data_value_int)
            
            # ログ出力
            readable_msg = f"ENQ(05) 局番号:{station} CMD:{command} {description} データ:{data_value} チェックサム:{checksum}"
            logger.info(f"📨 受信: {readable_msg}")
            
            # ACK応答送信
            self.send_response(station, True)
            
            # 状態更新
            self.update_status_from_message(data_num_int, data_value_int)
            
            # ステータス表示
            with self.lock:
                cur = self.current_status['current_floor']
                tgt = self.current_status['target_floor'] or '-'
                moving = "移動中" if self.current_status['is_moving'] else "停止中"
            logger.info(f"===== Status: 現在階={cur} 行先階={tgt} 状態={moving} =====")
            
        except Exception as e:
            logger.error(f"❌ メッセージ解析エラー: {e}")

    def send_response(self, station: str, is_ack: bool = True) -> bool:
        """応答送信"""
        try:
            if not self.serial_conn or not self.serial_conn.is_open:
                return False
            
            # ACK/NAK応答作成
            response = bytearray()
            response.append(0x06 if is_ack else 0x15)
            response.extend(station.encode('ascii'))
            
            self.serial_conn.write(response)
            
            response_type = "ACK" if is_ack else "NAK"
            hex_data = response.hex().upper()
            logger.info(f"📤 送信: {response_type}({response[0]:02X}) 局番号:{station} | HEX: {hex_data}")
            
            return True
        except Exception as e:
            logger.error(f"❌ 応答送信エラー: {e}")
            return False

    def format_readable_message(self, data_num: int, data_value: int) -> str:
        """人間が読める形式でメッセージをフォーマット"""
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
        else:
            description = f"データ番号: {data_num:04X}"
        
        return description

    def update_status_from_message(self, data_num: int, data_value: int):
        """受信メッセージから状態を更新"""
        with self.lock:
            if data_num == 0x0001:  # 現在階数（エレベーターからの状態報告）
                floor_name = "B1F" if data_value == 0xFFFF else f"{data_value}F"
                old_floor = self.current_status.get('current_floor')
                
                # 現在階が変わった場合、移動完了
                if old_floor != floor_name:
                    self.current_status['target_floor'] = None
                    self.current_status['is_moving'] = False
                    logger.info(f"🏢 現在階更新: {old_floor} → {floor_name} (移動完了)")
                
                # 現在階を常に更新
                self.current_status['current_floor'] = floor_name
                logger.info(f"📍 現在階確定: {floor_name}")
                
            elif data_num == 0x0002:  # 行先階（エレベーターからの状態報告）
                floor_name = "B1F" if data_value == 0xFFFF else f"{data_value}F"
                self.current_status['target_floor'] = floor_name
                logger.info(f"🎯 行先階確定: {floor_name}")
                
            elif data_num == 0x0010:  # 階数設定（移動指示）
                floor_name = "B1F" if data_value == 0xFFFF else f"{data_value}F"
                current_floor = self.current_status.get('current_floor')
                
                # 現在階と異なる場合のみ移動指示として処理
                if current_floor != floor_name:
                    self.current_status['target_floor'] = floor_name
                    self.current_status['is_moving'] = True
                    logger.info(f"🎯 移動指示: {current_floor} → {floor_name}")
                else:
                    # 同じ階の場合は到着完了として処理
                    self.current_status['target_floor'] = None
                    self.current_status['is_moving'] = False
                    logger.info(f"🏢 同一階設定により停止確定: {floor_name}")
                    
            elif data_num == 0x0011:  # 扉制御
                if data_value == 0x0001:  # 開扉
                    self.current_status['door_status'] = 'opening'
                    # 扉が開いた時、行先階があれば到着完了
                    target_floor = self.current_status.get('target_floor')
                    if target_floor and self.current_status.get('is_moving'):
                        old_floor = self.current_status.get('current_floor')
                        self.current_status['current_floor'] = target_floor
                        self.current_status['target_floor'] = None
                        self.current_status['is_moving'] = False
                        logger.info(f"🏢 扉開放により到着完了: {old_floor} → {target_floor}")
                    else:
                        logger.info(f"🚪 扉開放: 現在階={self.current_status.get('current_floor')}")
                        
                elif data_value == 0x0002:  # 閉扉
                    self.current_status['door_status'] = 'closing'
                    logger.info(f"🚪 扉閉鎖: 現在階={self.current_status.get('current_floor')}")
                else:
                    self.current_status['door_status'] = 'unknown'

    def listen(self):
        logger.info("🎧 シリアル受信開始...")
        while self.running:
            try:
                if self.serial_conn and self.serial_conn.is_open:
                    if self.serial_conn.in_waiting > 0:
                        chunk = self.serial_conn.read(self.serial_conn.in_waiting)
                        if chunk:
                            self.recv_buffer += chunk
                            self.process_buffer()
                else:
                    # シリアルポートが切断された場合、再接続を試行
                    logger.warning("⚠️ シリアルポート切断を検出、再接続を試行...")
                    self.reconnect()
                    
            except Exception as e:
                logger.error(f"❌ シリアル受信エラー: {e}")
                logger.info("🔄 シリアルポート再接続を試行...")
                self.reconnect()
                
            time.sleep(0.05)

    def reconnect(self):
        """シリアルポート再接続"""
        try:
            if self.serial_conn and self.serial_conn.is_open:
                self.serial_conn.close()
            
            # 少し待ってから再接続
            time.sleep(2)
            
            if self.connect():
                logger.info("✅ シリアルポート再接続成功")
                # バッファをクリア
                self.recv_buffer = b''
            else:
                logger.warning("⚠️ シリアルポート再接続失敗、5秒後に再試行...")
                time.sleep(5)
                
        except Exception as e:
            logger.error(f"❌ 再接続エラー: {e}")
            time.sleep(5)

    def start(self):
        if not self.connect(): 
            sys.exit(1)
        self.running = True
        threading.Thread(target=self.listen, daemon=True).start()

    def stop(self):
        self.running = False
        if self.serial_conn and self.serial_conn.is_open:
            self.serial_conn.close()
        logger.info("🛑 シリアル受信停止")

# ── RTSP サーバー ────────────────────────────
def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        return s.getsockname()[0]
    finally:
        s.close()

def pil_to_gst_buffer(img: Image.Image):
    data = img.tobytes()
    buf = Gst.Buffer.new_allocate(None, len(data), None)
    buf.fill(0, data)
    buf.duration = Gst.util_uint64_scale_int(1, Gst.SECOND, FPS)
    return buf

class ElevatorDisplayFactory(GstRtspServer.RTSPMediaFactory):
    def __init__(self, receiver: ElevatorDisplayReceiver):
        super().__init__()
        self.receiver = receiver
        self.set_shared(True)
        self.launch_str = (
            '( appsrc name=src is-live=true block=true format=time '
            f' caps=video/x-raw,format=RGB,width={WIDTH},height={HEIGHT},framerate={FPS}/1 '
            ' do-timestamp=true ! videoconvert '
            f'! video/x-raw,format=I420,width={WIDTH},height={HEIGHT},framerate={FPS}/1 '
            ' ! x264enc tune=zerolatency bitrate=500 speed-preset=ultrafast '
            ' ! rtph264pay name=pay0 pt=96 config-interval=1 )'
        )
    
    def do_create_element(self, url):
        pipeline = Gst.parse_launch(self.launch_str)
        self.appsrc = pipeline.get_by_name('src')
        threading.Thread(target=self.push_frames, daemon=True).start()
        return pipeline
    
    def push_frames(self):
        try:
            font_large = ImageFont.truetype(FONT_PATH, 36)
            font_medium = ImageFont.truetype(FONT_PATH, 28)
            font_small = ImageFont.truetype(FONT_PATH, 20)
        except IOError:
            font_large = ImageFont.load_default()
            font_medium = ImageFont.load_default()
            font_small = ImageFont.load_default()
        
        while True:
            img = Image.new('RGB', (WIDTH, HEIGHT), 'black')
            draw = ImageDraw.Draw(img)
            
            with self.receiver.lock:
                cur = self.receiver.current_status['current_floor']
                tgt = self.receiver.current_status['target_floor']
                is_moving = self.receiver.current_status['is_moving']
            
            # エレベーター案内ディスプレイのレイアウト
            if is_moving and tgt:
                # 移動中: 現在階と行先階を表示
                header = "移動中"
                body = f"{cur} → {tgt}"
                
                # ヘッダー（移動中）
                bb_header = draw.textbbox((0,0), header, font=font_medium)
                draw.text(((WIDTH-bb_header[2])//2, 30), header, font=font_medium, fill='yellow')
                
                # メイン表示（現在階 → 行先階）
                bb_body = draw.textbbox((0,0), body, font=font_large)
                draw.text(((WIDTH-bb_body[2])//2, 100), body, font=font_large, fill='white')
                
                # 矢印アニメーション
                arrow_y = 160
                arrow_x = WIDTH // 2
                # 簡単な点滅効果
                if int(time.time() * 2) % 2:
                    draw.text((arrow_x - 10, arrow_y), "▶", font=font_medium, fill='green')
                
            else:
                # 停止中: 現在階のみ表示
                header = "現在階"
                body = cur
                
                # ヘッダー（現在階）
                bb_header = draw.textbbox((0,0), header, font=font_medium)
                draw.text(((WIDTH-bb_header[2])//2, 50), header, font=font_medium, fill='lightblue')
                
                # メイン表示（現在階）
                bb_body = draw.textbbox((0,0), body, font=font_large)
                draw.text(((WIDTH-bb_body[2])//2, 120), body, font=font_large, fill='white')
            
            # 日時表示
            now = datetime.now().strftime("%Y年%-m月%-d日 %H:%M:%S")
            bb_time = draw.textbbox((0,0), now, font=font_small)
            draw.text(((WIDTH-bb_time[2])//2, HEIGHT-40), now, font=font_small, fill='gray')
            
            # フレーム送信
            buf = pil_to_gst_buffer(img)
            if self.appsrc.emit('push-buffer', buf) != Gst.FlowReturn.OK:
                break
            time.sleep(1.0/FPS)

def signal_handler(signum, frame):
    logger.info(f"🛑 シグナル {signum} 受信、停止します")
    receiver.stop()
    sys.exit(0)

if __name__ == '__main__':
    logger.info("🏢 SEC-3000H エレベーター案内ディスプレイ起動中...")
    logger.info("📺 backend-cli専用バージョン")
    
    Gst.init(None)
    receiver = ElevatorDisplayReceiver(SERIAL_PORT, BAUDRATE)
    receiver.start()
    
    server = GstRtspServer.RTSPServer.new()
    server.props.service = '8554'
    mount = server.get_mount_points()
    mount.add_factory('/elevator', ElevatorDisplayFactory(receiver))
    server.attach(None)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    ip = get_local_ip()
    logger.info(f"✅ RTSPサーバー起動: rtsp://{ip}:8554/elevator")
    logger.info("🎯 エレベーター案内ディスプレイ稼働中...")
    
    GLib.MainLoop().run()
