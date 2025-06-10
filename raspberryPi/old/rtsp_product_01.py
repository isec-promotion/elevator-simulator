#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Elevator Dashboard RTSP Server
  - RS-422シリアルで受信した現在階・行先階情報
    を可読メッセージでターミナル表示し、
    同時にRTSPで時刻とともに配信
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
class AutoModeElevatorReceiver:
    """RS-422メッセージを解析し、可読形式でターミナル表示"""
    def __init__(self, port: str, baudrate: int):
        self.port = port
        self.baudrate = baudrate
        self.serial_conn: Optional[serial.Serial] = None
        self.running = False
        self.current_status = {'current_floor': '1F', 'target_floor': None}
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
                # ENQが見つからない場合、バッファをクリア
                self.recv_buffer = b''
                return
            
            if idx > 0:
                # ENQより前のデータを削除
                self.recv_buffer = self.recv_buffer[idx:]
            
            if len(self.recv_buffer) < 16:
                # 完全なメッセージがない場合は待機
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
            if len(data) < 16 or data[0] != 0x05:  # ENQ
                return
            
            # メッセージ解析
            station = data[1:5].decode('ascii')
            command = chr(data[5])
            data_num = data[6:10].decode('ascii')
            data_value = data[10:14].decode('ascii')
            checksum = data[14:16].decode('ascii')
            
            # データ番号を整数に変換（16進数として解析）
            data_num_int = int(data_num, 16)
            data_value_int = int(data_value, 16)
            
            # 人間が読める形式でメッセージをフォーマット
            description = self.format_readable_message(data_num_int, data_value_int)
            
            # ログ出力（auto_mode_receiver.pyと同じ形式）
            readable_msg = f"ENQ(05) 局番号:{station} CMD:{command} {description} データ:{data_value} チェックサム:{checksum}"
            logger.info(f"📨 受信: {readable_msg}")
            
            # ACK応答送信（auto_mode_receiver.pyと同じ）
            self.send_response(station, True)
            
            # 状態更新
            self.update_status_from_message(data_num_int, data_value_int)
            
            # ステータス表示
            with self.lock:
                cur = self.current_status['current_floor']
                tgt = self.current_status['target_floor'] or '-'
            logger.info(f"===== Status: 現在階={cur} 行先階={tgt} =====")
            
        except Exception as e:
            logger.error(f"❌ メッセージ解析エラー: {e}")

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
        
        return description

    def update_status_from_message(self, data_num: int, data_value: int):
        """受信メッセージから状態を更新"""
        with self.lock:
            if data_num == 0x0001:  # 現在階数（エレベーターからの状態報告）
                floor_name = "B1F" if data_value == 0xFFFF else f"{data_value}F"
                # 現在階が変わった場合、行先階をクリア（到着完了）
                if self.current_status.get('current_floor') != floor_name:
                    self.current_status['target_floor'] = None
                    logger.info(f"🏢 到着完了: {floor_name} (行先階クリア)")
                self.current_status['current_floor'] = floor_name
                logger.info(f"🏢 現在階数を更新: {floor_name} (データ値: {data_value:04X})")
            elif data_num == 0x0002:  # 行先階（エレベーターからの状態報告）
                floor_name = "B1F" if data_value == 0xFFFF else f"{data_value}F"
                self.current_status['target_floor'] = floor_name
                logger.info(f"🎯 行先階を更新: {floor_name} (データ値: {data_value:04X})")
            elif data_num == 0x0010:  # 階数設定（移動指示）
                floor_name = "B1F" if data_value == 0xFFFF else f"{data_value}F"
                current_floor = self.current_status.get('current_floor')
                
                # 移動指示として行先階を設定
                self.current_status['target_floor'] = floor_name
                logger.info(f"🎯 移動指示: {current_floor} → {floor_name} (データ値: {data_value:04X})")
            elif data_num == 0x0016:  # 階数設定（自動運転モード移動指示）
                floor_name = "B1F" if data_value == 0xFFFF else f"{data_value}F"
                current_floor = self.current_status.get('current_floor')
                
                # 移動指示として行先階を設定
                self.current_status['target_floor'] = floor_name
                logger.info(f"🎯 自動運転移動指示: {current_floor} → {floor_name} (データ値: {data_value:04X})")
            elif data_num == 0x0011:  # 扉制御
                # 扉が開いた時、移動完了とみなして行先階をクリア
                if data_value == 0x0001:  # 開扉
                    target_floor = self.current_status.get('target_floor')
                    if target_floor:
                        self.current_status['current_floor'] = target_floor
                        self.current_status['target_floor'] = None
                        logger.info(f"🏢 扉開放により到着完了: {target_floor}")
            elif data_num == 0x0017:  # 扉制御（自動運転モード）
                # 扉が開いた時、移動完了とみなして行先階をクリア
                if data_value == 0x0001:  # 開扉
                    target_floor = self.current_status.get('target_floor')
                    if target_floor:
                        self.current_status['current_floor'] = target_floor
                        self.current_status['target_floor'] = None
                        logger.info(f"🏢 自動運転扉開放により到着完了: {target_floor}")

    def listen(self):
        logger.info("🎧 シリアル受信開始...")
        while self.running:
            if self.serial_conn and self.serial_conn.in_waiting:
                chunk = self.serial_conn.read(self.serial_conn.in_waiting)
                self.recv_buffer += chunk
                self.process_buffer()
            time.sleep(0.05)

    def start(self):
        if not self.connect(): sys.exit(1)
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

class AppSrcFactory(GstRtspServer.RTSPMediaFactory):
    def __init__(self, receiver: AutoModeElevatorReceiver):
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
            font = ImageFont.truetype(FONT_PATH, 28)
        except IOError:
            font = ImageFont.load_default()
        while True:
            img = Image.new('RGB', (WIDTH, HEIGHT), 'black')
            draw = ImageDraw.Draw(img)
            with self.receiver.lock:
                cur = self.receiver.current_status['current_floor']
                tgt = self.receiver.current_status['target_floor']
            header = "現在階　　　行先階" if tgt and tgt!=cur else "現在階"
            body   = f"{cur}　⇒　{tgt}" if tgt and tgt!=cur else cur
            bb = draw.textbbox((0,0), header, font=font)
            draw.text(((WIDTH-bb[2])//2,10), header, font=font, fill='white')
            bb2=draw.textbbox((0,0), body, font=font)
            draw.text(((WIDTH-bb2[2])//2,10+bb[3]+5), body, font=font, fill='white')
            now=datetime.now().strftime("%Y年%-m月%-d日 %H:%M:%S")
            bb3=draw.textbbox((0,0), now, font=font)
            draw.text(((WIDTH-bb3[2])//2,HEIGHT-bb3[3]-10), now, font=font, fill='white')
            buf=pil_to_gst_buffer(img)
            if self.appsrc.emit('push-buffer',buf)!=Gst.FlowReturn.OK: break
            time.sleep(1.0/FPS)

def signal_handler(signum, frame):
    logger.info(f"🛑 シグナル {signum} 受信、停止します")
    receiver.stop()
    sys.exit(0)

if __name__=='__main__':
    Gst.init(None)
    receiver=AutoModeElevatorReceiver(SERIAL_PORT,BAUDRATE)
    receiver.start()
    server=GstRtspServer.RTSPServer.new()
    server.props.service='8554'
    mount=server.get_mount_points()
    mount.add_factory('/elevator',AppSrcFactory(receiver))
    server.attach(None)
    signal.signal(signal.SIGINT,signal_handler)
    signal.signal(signal.SIGTERM,signal_handler)
    ip=get_local_ip()
    logger.info(f"✅ RTSPサーバー起動: rtsp://{ip}:8554/elevator")
    GLib.MainLoop().run()
