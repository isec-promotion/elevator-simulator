#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
エレベーター信号スヌーピング＆RTSP映像配信システム
COM27のシリアル信号をスヌーピングして、エレベーター状態をRTSP映像で配信
"""

import gi
gi.require_version('Gst', '1.0')
gi.require_version('GstRtspServer', '1.0')
from gi.repository import Gst, GstRtspServer, GLib

import serial
import threading
import time
import logging
import signal
import sys
import socket
from datetime import datetime
from typing import Optional, Dict, Any
from enum import IntEnum
from PIL import Image, ImageDraw, ImageFont

# ── 設定 ───────────────────────────────────
SERIAL_PORT = "COM27"  # Windows の場合
# SERIAL_PORT = "/dev/ttyUSB0"  # Linux の場合

SERIAL_CONFIG = {
    'port': SERIAL_PORT,
    'baudrate': 9600,
    'bytesize': serial.EIGHTBITS,
    'parity': serial.PARITY_EVEN,
    'stopbits': serial.STOPBITS_ONE,
    'timeout': 0.1
}

# RTSP配信設定
WIDTH, HEIGHT, FPS = 640, 480, 15
RTSP_PORT = 8554
RTSP_PATH = "/elevator"

# ── ログ設定 ─────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ── データ番号定義 ─────────────────────────────
class DataNumbers(IntEnum):
    CURRENT_FLOOR = 0x0001  # 現在階数
    TARGET_FLOOR = 0x0002   # 行先階
    LOAD_WEIGHT = 0x0003    # 荷重
    FLOOR_SETTING = 0x0010  # 階数設定
    DOOR_CONTROL = 0x0011   # 扉制御

class ElevatorState:
    """エレベーター状態管理"""
    def __init__(self):
        self.current_floor = "1F"
        self.target_floor = None
        self.load_weight = 0
        self.is_moving = False
        self.door_status = "閉扉"
        self.last_update = datetime.now()
        self.communication_log = []
        self.max_log_entries = 10

    def update_current_floor(self, floor_str: str):
        """現在階更新"""
        self.current_floor = floor_str
        self.last_update = datetime.now()

    def update_target_floor(self, floor_str: str):
        """行先階更新"""
        if floor_str == "なし":
            self.target_floor = None
            self.is_moving = False
        else:
            self.target_floor = floor_str
            if self.current_floor != floor_str:
                self.is_moving = True
        self.last_update = datetime.now()

    def update_load(self, weight: int):
        """荷重更新"""
        self.load_weight = weight
        self.last_update = datetime.now()

    def add_communication_log(self, message: str):
        """通信ログ追加"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] {message}"
        self.communication_log.append(log_entry)
        
        # ログ数制限
        if len(self.communication_log) > self.max_log_entries:
            self.communication_log.pop(0)

def get_local_ip():
    """ローカルIPアドレスを取得"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return '127.0.0.1'

def pil_to_gst_buffer(img: Image.Image):
    """PIL の RGB 画像 → Gst.Buffer"""
    data = img.tobytes()  # RGB24
    buf = Gst.Buffer.new_allocate(None, len(data), None)
    buf.fill(0, data)
    buf.duration = Gst.util_uint64_scale_int(1, Gst.SECOND, FPS)
    return buf

class ElevatorRTSPFactory(GstRtspServer.RTSPMediaFactory):
    """エレベーター映像配信ファクトリー"""
    
    def __init__(self, elevator_state: ElevatorState):
        super().__init__()
        self.elevator_state = elevator_state
        self.set_shared(True)
        
        # GStreamerパイプライン設定
        self.launch_str = (
            '( appsrc name=src is-live=true block=true format=time '
            f' caps=video/x-raw,format=RGB,width={WIDTH},height={HEIGHT},framerate={FPS}/1 '
            ' do-timestamp=true '
            ' ! videoconvert '
            f' ! video/x-raw,format=I420,width={WIDTH},height={HEIGHT},framerate={FPS}/1 '
            ' ! x264enc tune=zerolatency bitrate=800 speed-preset=ultrafast '
            ' ! rtph264pay name=pay0 pt=96 config-interval=1 )'
        )

    def do_create_element(self, url):
        """パイプライン要素作成"""
        pipeline = Gst.parse_launch(self.launch_str)
        self.appsrc = pipeline.get_by_name('src')
        threading.Thread(target=self.push_frames, daemon=True).start()
        return pipeline

    def push_frames(self):
        """フレーム生成・配信"""
        # 日本語フォント設定
        font_paths = [
            "/usr/share/fonts/truetype/ipafont-mincho/ipam.ttf",  # Linux
            "/System/Library/Fonts/Hiragino Sans GB.ttc",        # macOS
            "C:/Windows/Fonts/msgothic.ttc"                      # Windows
        ]
        
        font_large = None
        font_medium = None
        font_small = None
        
        for font_path in font_paths:
            try:
                font_large = ImageFont.truetype(font_path, 48)
                font_medium = ImageFont.truetype(font_path, 32)
                font_small = ImageFont.truetype(font_path, 20)
                break
            except (IOError, OSError):
                continue
        
        if font_large is None:
            font_large = ImageFont.load_default()
            font_medium = ImageFont.load_default()
            font_small = ImageFont.load_default()

        while True:
            try:
                # 背景画像作成
                img = Image.new('RGB', (WIDTH, HEIGHT), (20, 30, 50))  # 濃紺背景
                draw = ImageDraw.Draw(img)
                
                # 現在時刻
                now = datetime.now()
                timestamp = now.strftime("%Y年%m月%d日 %H:%M:%S")
                
                # タイトル
                title = "エレベーター監視システム"
                self._draw_centered_text(draw, title, font_medium, WIDTH//2, 40, 'white')
                
                # 現在時刻表示
                self._draw_centered_text(draw, timestamp, font_small, WIDTH//2, 80, 'lightgray')
                
                # エレベーター状態表示
                y_pos = 140
                
                # 状態判定
                if self.elevator_state.is_moving and self.elevator_state.target_floor:
                    # 移動中
                    status_text = f"{self.elevator_state.current_floor} ⇒ {self.elevator_state.target_floor}"
                    status_color = 'yellow'
                    status_bg = (100, 100, 0)
                else:
                    # 停止中
                    status_text = f"現在階: {self.elevator_state.current_floor}"
                    status_color = 'lightgreen'
                    status_bg = (0, 100, 0)
                
                # 状態背景
                status_rect = [50, y_pos-10, WIDTH-50, y_pos+60]
                draw.rectangle(status_rect, fill=status_bg, outline='white', width=2)
                
                # 状態テキスト
                self._draw_centered_text(draw, status_text, font_large, WIDTH//2, y_pos+25, status_color)
                
                y_pos += 100
                
                # 詳細情報
                details = [
                    f"荷重: {self.elevator_state.load_weight}kg",
                    f"扉状態: {self.elevator_state.door_status}",
                    f"最終更新: {self.elevator_state.last_update.strftime('%H:%M:%S')}"
                ]
                
                for detail in details:
                    self._draw_centered_text(draw, detail, font_small, WIDTH//2, y_pos, 'lightblue')
                    y_pos += 30
                
                # 通信ログ表示
                y_pos += 20
                draw.text((20, y_pos), "通信ログ:", font=font_small, fill='white')
                y_pos += 25
                
                for log_entry in self.elevator_state.communication_log[-5:]:  # 最新5件
                    draw.text((20, y_pos), log_entry, font=font_small, fill='lightgray')
                    y_pos += 20
                
                # フレームバッファに送信
                buf = pil_to_gst_buffer(img)
                ret = self.appsrc.emit('push-buffer', buf)
                if ret != Gst.FlowReturn.OK:
                    break
                
                time.sleep(1.0 / FPS)
                
            except Exception as e:
                logger.error(f"❌ フレーム生成エラー: {e}")
                time.sleep(1.0)

    def _draw_centered_text(self, draw, text, font, x, y, color):
        """中央揃えテキスト描画"""
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        draw.text((x - text_width//2, y - text_height//2), text, font=font, fill=color)

class SerialSnooper:
    """シリアル信号スヌーピング"""
    
    def __init__(self, elevator_state: ElevatorState):
        self.elevator_state = elevator_state
        self.serial_conn: Optional[serial.Serial] = None
        self.running = False

    def initialize(self):
        """初期化"""
        logger.info("📡 シリアルスヌーピング初期化")
        logger.info(f"ポート: {SERIAL_CONFIG['port']}")
        
        try:
            self._connect_serial()
            logger.info("✅ シリアル接続成功")
            return True
        except Exception as e:
            logger.error(f"❌ シリアル接続失敗: {e}")
            return False

    def _connect_serial(self):
        """シリアルポート接続"""
        try:
            self.serial_conn = serial.Serial(**SERIAL_CONFIG)
            logger.info(f"✅ シリアルポート {SERIAL_CONFIG['port']} 接続成功")
        except Exception as e:
            logger.error(f"❌ シリアルポートエラー: {e}")
            raise

    def start_snooping(self):
        """スヌーピング開始"""
        if self.running:
            return
        
        logger.info("🔍 シリアル信号スヌーピング開始")
        self.running = True
        threading.Thread(target=self._snoop_serial, daemon=True).start()

    def stop_snooping(self):
        """スヌーピング停止"""
        logger.info("🛑 シリアル信号スヌーピング停止")
        self.running = False

    def _snoop_serial(self):
        """シリアル信号監視"""
        buffer = bytearray()
        
        while self.running and self.serial_conn and self.serial_conn.is_open:
            try:
                if self.serial_conn.in_waiting > 0:
                    data = self.serial_conn.read(self.serial_conn.in_waiting)
                    buffer.extend(data)
                    
                    # メッセージ解析
                    while len(buffer) >= 5:
                        if buffer[0] == 0x05:  # ENQ
                            if len(buffer) >= 16:
                                enq_message = buffer[:16]
                                buffer = buffer[16:]
                                self._parse_enq_message(enq_message)
                            else:
                                break
                        elif buffer[0] == 0x06:  # ACK
                            if len(buffer) >= 5:
                                ack_message = buffer[:5]
                                buffer = buffer[5:]
                                self._parse_ack_message(ack_message)
                            else:
                                break
                        else:
                            # 不正なデータを破棄
                            buffer = buffer[1:]
                
                time.sleep(0.05)
                
            except Exception as e:
                logger.error(f"❌ シリアル受信エラー: {e}")
                break

    def _parse_enq_message(self, data: bytes):
        """ENQメッセージ解析"""
        try:
            if len(data) < 16:
                return

            station = data[1:5].decode('ascii')
            command = chr(data[5])
            data_num_str = data[6:10].decode('ascii')
            data_value_str = data[10:14].decode('ascii')
            checksum = data[14:16].decode('ascii')

            data_num = int(data_num_str, 16)
            data_value = int(data_value_str, 16)

            # ターミナル出力
            timestamp = datetime.now().strftime("%Y年%m月%d日 %H:%M:%S")
            sender = "エレベーター" if station == "0001" else "自動運転装置"
            
            # データ内容解釈
            description = ""
            if data_num == DataNumbers.CURRENT_FLOOR:
                floor = "B1F" if data_value == 0xFFFF else f"{data_value}F"
                description = f"現在階数: {floor}"
                self.elevator_state.update_current_floor(floor)
                
            elif data_num == DataNumbers.TARGET_FLOOR:
                if data_value == 0x0000:
                    description = "行先階: なし"
                    self.elevator_state.update_target_floor("なし")
                else:
                    floor = "B1F" if data_value == 0xFFFF else f"{data_value}F"
                    description = f"行先階: {floor}"
                    self.elevator_state.update_target_floor(floor)
                    
            elif data_num == DataNumbers.LOAD_WEIGHT:
                description = f"荷重: {data_value}kg"
                self.elevator_state.update_load(data_value)
                
            elif data_num == DataNumbers.FLOOR_SETTING:
                floor = "B1F" if data_value == 0xFFFF else f"{data_value}F"
                description = f"階数設定: {floor}"
                
            elif data_num == DataNumbers.DOOR_CONTROL:
                door_cmd = "開扉" if data_value == 1 else "閉扉" if data_value == 2 else "停止"
                description = f"扉制御: {door_cmd}"
                self.elevator_state.door_status = door_cmd

            log_message = f"📤 {sender}→ENQ: {description}"
            logger.info(f"[{timestamp}] {log_message}")
            
            # 通信ログに追加
            self.elevator_state.add_communication_log(f"ENQ: {description}")

        except Exception as e:
            logger.error(f"❌ ENQメッセージ解析エラー: {e}")

    def _parse_ack_message(self, data: bytes):
        """ACKメッセージ解析"""
        try:
            if len(data) >= 5 and data[0] == 0x06:
                station = data[1:5].decode('ascii')
                timestamp = datetime.now().strftime("%Y年%m月%d日 %H:%M:%S")
                sender = "エレベーター" if station == "0002" else "自動運転装置"
                
                log_message = f"📨 {sender}→ACK応答"
                logger.info(f"[{timestamp}] {log_message}")
                
                # 通信ログに追加
                self.elevator_state.add_communication_log(f"ACK: {sender}")
                
        except Exception as e:
            logger.error(f"❌ ACKメッセージ解析エラー: {e}")

    def shutdown(self):
        """終了処理"""
        self.stop_snooping()
        if self.serial_conn and self.serial_conn.is_open:
            self.serial_conn.close()
            logger.info("📡 シリアルポート切断完了")

class ElevatorRTSPServer:
    """エレベーターRTSPサーバー"""
    
    def __init__(self, elevator_state: ElevatorState):
        self.elevator_state = elevator_state
        self.server = None

    def start_server(self):
        """RTSPサーバー開始"""
        logger.info("📺 RTSP映像配信サーバー起動中...")
        
        try:
            Gst.init(None)
            
            self.server = GstRtspServer.RTSPServer.new()
            self.server.props.service = str(RTSP_PORT)
            
            mount = self.server.get_mount_points()
            factory = ElevatorRTSPFactory(self.elevator_state)
            mount.add_factory(RTSP_PATH, factory)
            
            self.server.attach(None)
            
            ip = get_local_ip()
            rtsp_url = f"rtsp://{ip}:{RTSP_PORT}{RTSP_PATH}"
            
            logger.info(f"✅ RTSP配信開始: {rtsp_url}")
            logger.info(f"📱 VLCなどで上記URLを開いて映像を確認してください")
            
            return rtsp_url
            
        except Exception as e:
            logger.error(f"❌ RTSPサーバー起動エラー: {e}")
            return None

def main():
    """メイン処理"""
    import argparse
    
    parser = argparse.ArgumentParser(description='エレベーター信号スヌーピング＆RTSP映像配信システム')
    parser.add_argument('--port', default=SERIAL_PORT, help='シリアルポート')
    parser.add_argument('--rtsp-port', type=int, default=RTSP_PORT, help='RTSPポート番号')
    args = parser.parse_args()
    
    # 設定更新
    SERIAL_CONFIG['port'] = args.port
    global RTSP_PORT
    RTSP_PORT = args.rtsp_port
    
    # シグナルハンドラー設定
    def signal_handler(signum, frame):
        logger.info(f"\n🛑 シグナル {signum} を受信しました")
        if 'snooper' in locals():
            snooper.shutdown()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # システム初期化
    logger.info("🏢 エレベーター信号スヌーピング＆RTSP映像配信システム起動")
    
    # エレベーター状態管理
    elevator_state = ElevatorState()
    
    # シリアルスヌーピング初期化
    snooper = SerialSnooper(elevator_state)
    if not snooper.initialize():
        logger.error("❌ シリアルスヌーピング初期化失敗")
        sys.exit(1)
    
    # RTSPサーバー初期化
    rtsp_server = ElevatorRTSPServer(elevator_state)
    rtsp_url = rtsp_server.start_server()
    if not rtsp_url:
        logger.error("❌ RTSPサーバー起動失敗")
        sys.exit(1)
    
    try:
        # スヌーピング開始
        snooper.start_snooping()
        
        logger.info("\n✅ システム稼働中 (Ctrl+C で終了)")
        logger.info(f"📡 シリアル監視: {args.port}")
        logger.info(f"📺 RTSP配信: {rtsp_url}")
        logger.info("🔍 エレベーター・自動運転装置間の通信を監視中...")
        
        # GLibメインループ実行
        GLib.MainLoop().run()
        
    except Exception as e:
        logger.error(f"❌ システムエラー: {e}")
    finally:
        snooper.shutdown()
        logger.info("✅ システム終了完了")

if __name__ == "__main__":
    main()
