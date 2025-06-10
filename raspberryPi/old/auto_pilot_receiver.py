#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SEC-3000H Auto Pilot Receiver
自動運転装置側受信機（局番号: 0001）
エレベーターからの状態データを受信してRTSP配信
"""

import serial
import time
import threading
import logging
import signal
import sys
import socket
from datetime import datetime
from typing import Optional, Dict, Any
from enum import IntEnum

from PIL import Image, ImageDraw, ImageFont
import gi
gi.require_version('Gst', '1.0')
gi.require_version('GstRtspServer', '1.0')
from gi.repository import Gst, GstRtspServer, GLib

# ── 設定 ───────────────────────────────────
SERIAL_PORT = "/dev/ttyUSB0"  # Raspberry Pi の場合
# SERIAL_PORT = "COM27"  # Windows の場合

SERIAL_CONFIG = {
    'port': SERIAL_PORT,
    'baudrate': 9600,
    'bytesize': serial.EIGHTBITS,
    'parity': serial.PARITY_EVEN,
    'stopbits': serial.STOPBITS_ONE,
    'timeout': 1
}

# RTSP設定
WIDTH, HEIGHT, FPS = 640, 360, 15
FONT_PATH = "/usr/share/fonts/truetype/ipafont-mincho/ipam.ttf"

# ── ログ設定 ─────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ── SEC-3000H データ番号定義 ─────────────────
class DataNumbers(IntEnum):
    CURRENT_FLOOR = 0x0001  # 現在階数
    TARGET_FLOOR = 0x0002   # 行先階
    LOAD_WEIGHT = 0x0003    # 荷重
    FLOOR_SETTING = 0x0010  # 階数設定（送信用）
    DOOR_CONTROL = 0x0011   # 扉制御（送信用）

# ── 扉制御コマンド ─────────────────────────────
class DoorCommands(IntEnum):
    STOP = 0x0000   # 停止
    OPEN = 0x0001   # 開扉
    CLOSE = 0x0002  # 閉扉

# ── エレベーター状態 ───────────────────────────
class ElevatorStatus:
    def __init__(self):
        self.current_floor = "1F"
        self.target_floor = None
        self.load_weight = 0
        self.last_update = None
        self.communication_active = False

class AutoPilotReceiver:
    """SEC-3000H 自動運転装置受信機"""
    
    def __init__(self):
        self.serial_conn: Optional[serial.Serial] = None
        self.status = ElevatorStatus()
        self.station_id = "0001"  # 自動運転装置側局番号
        self.elevator_station = "0002"  # エレベーター側局番号
        self.running = False
        self.lock = threading.Lock()
        self.local_ip = self._get_local_ip()

    def _get_local_ip(self) -> str:
        """ローカルIPアドレスを取得"""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(('8.8.8.8', 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"

    def initialize(self):
        """初期化"""
        logger.info("🤖 SEC-3000H Auto Pilot Receiver 起動中...")
        logger.info(f"📡 シリアルポート設定: {SERIAL_PORT}")
        logger.info(f"🏷️ 局番号: {self.station_id} (自動運転装置側)")
        logger.info(f"🎯 受信元: {self.elevator_station} (エレベーター側)")

        try:
            self._connect_serial()
            logger.info("✅ 初期化完了")
            return True
        except Exception as e:
            logger.error(f"❌ 初期化失敗: {e}")
            return False

    def _connect_serial(self):
        """シリアルポート接続"""
        try:
            self.serial_conn = serial.Serial(**SERIAL_CONFIG)
            logger.info(f"✅ シリアルポート {SERIAL_PORT} 接続成功")
            
            # 受信スレッド開始
            threading.Thread(target=self._listen_serial, daemon=True).start()
            
        except Exception as e:
            logger.error(f"❌ シリアルポートエラー: {e}")
            raise

    def _listen_serial(self):
        """シリアル受信処理（エレベーターからのデータ受信）"""
        buffer = bytearray()
        
        while self.running and self.serial_conn and self.serial_conn.is_open:
            try:
                if self.serial_conn.in_waiting > 0:
                    data = self.serial_conn.read(self.serial_conn.in_waiting)
                    buffer.extend(data)
                    
                    # ENQ(05H)で始まるメッセージを検索
                    while len(buffer) >= 16:
                        enq_pos = buffer.find(0x05)
                        if enq_pos == -1:
                            buffer.clear()
                            break
                        
                        if enq_pos > 0:
                            buffer = buffer[enq_pos:]
                        
                        if len(buffer) >= 16:
                            message = buffer[:16]
                            buffer = buffer[16:]
                            self._handle_received_data(message)
                        else:
                            break
                
                time.sleep(0.05)
                
            except Exception as e:
                logger.error(f"❌ シリアル受信エラー: {e}")
                break

    def _handle_received_data(self, data: bytes):
        """受信データ処理（エレベーターからの状態データ）"""
        try:
            if len(data) < 16 or data[0] != 0x05:
                return

            # メッセージ解析
            station = data[1:5].decode('ascii')
            command = chr(data[5])
            data_num_str = data[6:10].decode('ascii')
            data_value_str = data[10:14].decode('ascii')
            checksum = data[14:16].decode('ascii')

            # 自分宛のメッセージかチェック
            if station != self.station_id:
                return

            data_num = int(data_num_str, 16)
            data_value = int(data_value_str, 16)

            timestamp = datetime.now().strftime("%Y年%m月%d日 %H:%M:%S")

            # データ処理
            with self.lock:
                self.status.last_update = datetime.now()
                self.status.communication_active = True

                if data_num == DataNumbers.CURRENT_FLOOR:
                    # 現在階数
                    current_floor = "B1F" if data_value == 0xFFFF else f"{data_value}F"
                    self.status.current_floor = current_floor
                    description = f"現在階数: {current_floor}"
                    
                elif data_num == DataNumbers.TARGET_FLOOR:
                    # 行先階
                    if data_value == 0x0000:
                        self.status.target_floor = None
                        description = "行先階: なし"
                    else:
                        target_floor = "B1F" if data_value == 0xFFFF else f"{data_value}F"
                        self.status.target_floor = target_floor
                        description = f"行先階: {target_floor}"
                    
                elif data_num == DataNumbers.LOAD_WEIGHT:
                    # 荷重
                    self.status.load_weight = data_value
                    description = f"荷重: {data_value}kg"
                else:
                    description = f"データ番号: {data_num:04X}"

            logger.info(
                f"[{timestamp}] 📨 受信: ENQ(05) 局番号:{self.elevator_station} CMD:{command} "
                f"{description} データ:{data_value_str} チェックサム:{checksum}"
            )

            # ACK応答送信
            self._send_ack_response()

        except Exception as e:
            logger.error(f"❌ 受信データ処理エラー: {e}")

    def _send_ack_response(self):
        """ACK応答送信"""
        if not self.serial_conn or not self.serial_conn.is_open:
            return

        try:
            response = bytearray([0x06])  # ACK
            response.extend(self.elevator_station.encode('ascii'))  # 0002

            self.serial_conn.write(response)

            timestamp = datetime.now().strftime("%Y年%m月%d日 %H:%M:%S")
            hex_data = response.hex().upper()
            logger.info(f"[{timestamp}] 📤 ACK送信: {hex_data}")

        except Exception as e:
            logger.error(f"❌ ACK送信エラー: {e}")

    def _calculate_checksum(self, data: bytes) -> str:
        """チェックサム計算"""
        total = sum(data)
        lower_byte = total & 0xFF
        upper_byte = (total >> 8) & 0xFF
        checksum = (lower_byte + upper_byte) & 0xFF
        return f"{checksum:02X}"

    def send_command(self, data_num: int, data_value: int) -> bool:
        """コマンド送信（エレベーターへの指令）"""
        if not self.serial_conn or not self.serial_conn.is_open:
            return False

        try:
            # メッセージ作成
            message = bytearray()
            message.append(0x05)  # ENQ
            message.extend(self.elevator_station.encode('ascii'))  # 0002（送信先）
            message.append(0x57)  # 'W'

            # データ番号 (4桁ASCII)
            data_num_str = f"{data_num:04X}"
            message.extend(data_num_str.encode('ascii'))

            # データ (4桁HEX ASCII)
            data_value_str = f"{data_value:04X}"
            message.extend(data_value_str.encode('ascii'))

            # チェックサム計算 (ENQ以外)
            checksum_data = message[1:]
            checksum = self._calculate_checksum(checksum_data)
            message.extend(checksum.encode('ascii'))

            # 送信
            self.serial_conn.write(message)

            timestamp = datetime.now().strftime("%Y年%m月%d日 %H:%M:%S")
            
            # データ内容を解釈
            description = ""
            if data_num == DataNumbers.FLOOR_SETTING:
                floor = "B1F" if data_value == 0xFFFF else f"{data_value}F"
                description = f"階数設定: {floor}"
            elif data_num == DataNumbers.DOOR_CONTROL:
                if data_value == DoorCommands.OPEN:
                    description = "扉制御: 開扉"
                elif data_value == DoorCommands.CLOSE:
                    description = "扉制御: 閉扉"
                else:
                    description = "扉制御: 停止"

            logger.info(
                f"[{timestamp}] 📤 送信: ENQ(05) 局番号:{self.elevator_station} CMD:W "
                f"{description} データ:{data_value_str} チェックサム:{checksum}"
            )

            return True

        except Exception as e:
            logger.error(f"❌ コマンド送信エラー: {e}")
            return False

    def set_floor(self, floor: str) -> bool:
        """階数設定"""
        floor_value = 0xFFFF if floor == "B1F" else int(floor.replace("F", ""))
        return self.send_command(DataNumbers.FLOOR_SETTING, floor_value)

    def control_door(self, action: str) -> bool:
        """扉制御"""
        command_map = {
            "open": DoorCommands.OPEN,
            "close": DoorCommands.CLOSE,
            "stop": DoorCommands.STOP
        }
        command = command_map.get(action, DoorCommands.STOP)
        return self.send_command(DataNumbers.DOOR_CONTROL, command)

    def start_receiver(self):
        """受信開始"""
        if self.running:
            logger.info("⚠️ 受信は既に実行中です")
            return

        logger.info("🎧 エレベーターデータ受信開始")
        logger.info(f"📊 受信データ: 現在階数(0001), 行先階(0002), 荷重(0003)")
        self.running = True

    def stop_receiver(self):
        """受信停止"""
        logger.info("🛑 データ受信停止")
        self.running = False

    def _display_status(self):
        """状態表示"""
        timestamp = datetime.now().strftime("%Y年%m月%d日 %H:%M:%S")

        with self.lock:
            current_floor = self.status.current_floor
            target_floor = self.status.target_floor or "-"
            load_weight = self.status.load_weight
            last_update = self.status.last_update
            communication_active = self.status.communication_active

        # 通信状態チェック
        if last_update:
            time_diff = (datetime.now() - last_update).total_seconds()
            comm_status = "正常" if time_diff < 10 else "タイムアウト"
        else:
            comm_status = "未受信"

        logger.info(f"\n[{timestamp}] 📊 エレベーター状態")
        logger.info(f"現在階: {current_floor}")
        logger.info(f"行先階: {target_floor}")
        logger.info(f"荷重: {load_weight}kg")
        logger.info(f"通信状態: {comm_status}")
        if last_update:
            logger.info(f"最終更新: {last_update.strftime('%H:%M:%S')}")

    def start_status_display(self):
        """定期状態表示開始"""
        def _status_timer():
            if self.running:
                self._display_status()
                threading.Timer(30.0, _status_timer).start()

        _status_timer()

    def shutdown(self):
        """終了処理"""
        logger.info("🛑 システム終了中...")

        self.stop_receiver()

        if self.serial_conn and self.serial_conn.is_open:
            self.serial_conn.close()
            logger.info("📡 シリアルポート切断完了")

        logger.info("✅ システム終了完了")

# ── RTSP サーバー ────────────────────────────
def pil_to_gst_buffer(img: Image.Image):
    data = img.tobytes()
    buf = Gst.Buffer.new_allocate(None, len(data), None)
    buf.fill(0, data)
    buf.duration = Gst.util_uint64_scale_int(1, Gst.SECOND, FPS)
    return buf

class AutoPilotDisplayFactory(GstRtspServer.RTSPMediaFactory):
    def __init__(self, receiver: AutoPilotReceiver):
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
                current_floor = self.receiver.status.current_floor
                target_floor = self.receiver.status.target_floor
                load_weight = self.receiver.status.load_weight
                last_update = self.receiver.status.last_update
                communication_active = self.receiver.status.communication_active

            # 通信状態チェック
            if last_update:
                time_diff = (datetime.now() - last_update).total_seconds()
                comm_active = time_diff < 10
            else:
                comm_active = False

            # ヘッダー
            header = "SEC-3000H 自動運転装置"
            bb_header = draw.textbbox((0,0), header, font=font_medium)
            draw.text(((WIDTH-bb_header[2])//2, 20), header, font=font_medium, fill='lightblue')

            # 現在階表示
            floor_text = f"現在階: {current_floor}"
            bb_floor = draw.textbbox((0,0), floor_text, font=font_large)
            draw.text(((WIDTH-bb_floor[2])//2, 70), floor_text, font=font_large, fill='white')

            # 行先階表示
            if target_floor:
                target_text = f"行先階: {target_floor}"
                color = 'yellow'
            else:
                target_text = "行先階: なし"
                color = 'gray'
            
            bb_target = draw.textbbox((0,0), target_text, font=font_medium)
            draw.text(((WIDTH-bb_target[2])//2, 120), target_text, font=font_medium, fill=color)

            # 荷重表示
            load_text = f"荷重: {load_weight}kg"
            bb_load = draw.textbbox((0,0), load_text, font=font_medium)
            draw.text(((WIDTH-bb_load[2])//2, 160), load_text, font=font_medium, fill='lightgreen')

            # 通信状態表示
            if comm_active:
                comm_text = "通信: 正常"
                comm_color = 'green'
            else:
                comm_text = "通信: 切断"
                comm_color = 'red'
            
            draw.text((10, 10), comm_text, font=font_small, fill=comm_color)

            # 局番号表示
            station_text = f"局番号: {self.receiver.station_id}"
            draw.text((10, 35), station_text, font=font_small, fill='gray')

            # IPアドレス表示
            ip_text = f"IP: {self.receiver.local_ip}"
            draw.text((10, 60), ip_text, font=font_small, fill='gray')

            # 日時表示
            now = datetime.now().strftime("%Y年%-m月%-d日 %H:%M:%S")
            bb_time = draw.textbbox((0,0), now, font=font_small)
            draw.text(((WIDTH-bb_time[2])//2, HEIGHT-40), now, font=font_small, fill='gray')

            # 最終更新時刻
            if last_update:
                update_text = f"最終更新: {last_update.strftime('%H:%M:%S')}"
                bb_update = draw.textbbox((0,0), update_text, font=font_small)
                draw.text(((WIDTH-bb_update[2])//2, HEIGHT-20), update_text, font=font_small, fill='gray')

            # フレーム送信
            buf = pil_to_gst_buffer(img)
            if self.appsrc.emit('push-buffer', buf) != Gst.FlowReturn.OK:
                break
            time.sleep(1.0/FPS)

# ── メイン処理 ─────────────────────────────────
def signal_handler(signum, frame):
    """シグナルハンドラー"""
    logger.info(f"\n🛑 シグナル {signum} を受信しました")
    if 'receiver' in globals():
        receiver.shutdown()
    sys.exit(0)

def main():
    """メイン処理"""
    import argparse
    
    # コマンドライン引数解析
    parser = argparse.ArgumentParser(description='SEC-3000H Auto Pilot Receiver')
    parser.add_argument('--port', default=SERIAL_PORT, help='シリアルポート')
    parser.add_argument('--no-rtsp', action='store_true', help='RTSPサーバーを起動しない')
    args = parser.parse_args()
    
    # シグナルハンドラー設定
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # グローバル変数設定


    SERIAL_CONFIG['port'] = args.port
    
    # 自動運転装置受信機初期化
    global receiver
    receiver = AutoPilotReceiver()
    
    try:
        # 初期化
        if not receiver.initialize():
            sys.exit(1)
        
        # 受信開始
        receiver.start_receiver()
        
        # 定期状態表示開始
        receiver.start_status_display()
        
        # RTSPサーバー起動
        if not args.no_rtsp:
            Gst.init(None)
            server = GstRtspServer.RTSPServer.new()
            server.props.service = '8554'
            mount = server.get_mount_points()
            mount.add_factory('/elevator', AutoPilotDisplayFactory(receiver))
            server.attach(None)
            
            logger.info(f"✅ RTSPサーバー起動: rtsp://{receiver.local_ip}:8554/elevator")
        
        logger.info("\n✅ 自動運転装置受信機稼働中 (Ctrl+C で終了)")
        
        # メインループ
        if not args.no_rtsp:
            GLib.MainLoop().run()
        else:
            while receiver.running:
                time.sleep(1)

    except Exception as e:
        logger.error(f"❌ システムエラー: {e}")
        receiver.shutdown()
        sys.exit(1)

if __name__ == "__main__":
    main()
