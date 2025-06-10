#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
エレベーター信号スヌーピング＆RTSP映像配信システム（ENQ解析エラー修正版）
/dev/ttyUSB0のシリアル信号をスヌーピングして、エレベーター状態をRTSP映像で配信
シリアル接続切断時の自動復帰機能とENQ解析エラー対策を搭載
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
SERIAL_PORT = "/dev/ttyUSB0"  # Raspberry Pi（RS422アダプター）

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
        self.connection_status = "切断中"

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

    def set_connection_status(self, status: str):
        """接続状態更新"""
        self.connection_status = status
        self.add_communication_log(f"接続状態: {status}")

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
    
    def __init__(self, elevator_state: ElevatorState, rtsp_port: int):
        super().__init__()
        self.elevator_state = elevator_state
        self.rtsp_port = rtsp_port
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
                
                # 接続状態表示
                connection_color = 'lightgreen' if self.elevator_state.connection_status == "接続中" else 'red'
                self._draw_centered_text(draw, f"接続状態: {self.elevator_state.connection_status}", 
                                       font_small, WIDTH//2, 110, connection_color)
                
                # エレベーター状態表示
                y_pos = 150
                
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
    """シリアル信号スヌーピング（ENQ解析エラー修正版）"""
    
    def __init__(self, elevator_state: ElevatorState):
        self.elevator_state = elevator_state
        self.serial_conn: Optional[serial.Serial] = None
        self.running = False

    def initialize(self):
        """初期化"""
        logger.info("📡 シリアルスヌーピング初期化（ENQ解析エラー修正版）")
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
            self.elevator_state.set_connection_status("接続中")
        except Exception as e:
            logger.error(f"❌ シリアルポートエラー: {e}")
            self.elevator_state.set_connection_status("切断中")
            raise

    def start_snooping(self):
        """スヌーピング開始"""
        if self.running:
            return
        
        logger.info("🔍 シリアル信号スヌーピング開始（ENQ解析エラー修正版）")
        self.running = True
        threading.Thread(target=self._snoop_serial, daemon=True).start()

    def stop_snooping(self):
        """スヌーピング停止"""
        logger.info("🛑 シリアル信号スヌーピング停止")
        self.running = False

    def _snoop_serial(self):
        """シリアル信号監視（ENQ解析エラー修正版）"""
        buffer = bytearray()
        reconnect_attempts = 0
        max_reconnect_attempts = 10
        last_data_time = time.time()
        
        while self.running:
            try:
                # シリアル接続チェック
                if not self.serial_conn or not self.serial_conn.is_open:
                    if not self._reconnect_serial():
                        time.sleep(5)  # 5秒待機してリトライ
                        continue
                    buffer.clear()  # バッファクリア
                    reconnect_attempts = 0
                    last_data_time = time.time()
                
                # データ受信チェック
                if self.serial_conn.in_waiting > 0:
                    data = self.serial_conn.read(self.serial_conn.in_waiting)
                    if not data:  # データが空の場合（切断検出）
                        logger.warning("⚠️ シリアルデータが空です。接続を確認中...")
                        self._close_serial()
                        continue
                    
                    buffer.extend(data)
                    last_data_time = time.time()
                    
                    # メッセージ解析（改良版）
                    self._parse_messages_improved(buffer)
                
                # 長時間データが来ない場合の接続チェック
                if time.time() - last_data_time > 30:  # 30秒間データなし
                    logger.warning("⚠️ 30秒間データを受信していません。接続を確認中...")
                    if not self._test_serial_connection():
                        self._close_serial()
                        continue
                    last_data_time = time.time()
                
                time.sleep(0.05)
                
            except serial.SerialException as e:
                logger.error(f"❌ シリアル通信エラー: {e}")
                self._close_serial()
                reconnect_attempts += 1
                
                if reconnect_attempts >= max_reconnect_attempts:
                    logger.error(f"❌ 最大再接続試行回数({max_reconnect_attempts})に達しました")
                    self.elevator_state.set_connection_status("接続失敗")
                    time.sleep(10)  # 10秒待機してリセット
                    reconnect_attempts = 0
                    continue
                
                logger.info(f"🔄 {reconnect_attempts}/{max_reconnect_attempts} 回目の再接続を試行中...")
                time.sleep(2)  # 2秒待機
                
            except Exception as e:
                logger.error(f"❌ 予期しないエラー: {e}")
                self._close_serial()
                time.sleep(1)

    def _parse_messages_improved(self, buffer: bytearray):
        """改良版メッセージ解析"""
        while len(buffer) >= 5:
            # ENQメッセージの検索
            enq_pos = -1
            for i in range(len(buffer) - 15):
                if buffer[i] == 0x05:  # ENQ
                    # 16バイトのENQメッセージかチェック
                    if i + 16 <= len(buffer):
                        enq_pos = i
                        break
            
            if enq_pos >= 0:
                # ENQメッセージを抽出
                enq_message = buffer[enq_pos:enq_pos + 16]
                buffer = buffer[enq_pos + 16:]
                self._parse_enq_message_safe(enq_message)
                continue
            
            # ACKメッセージの検索
            ack_pos = -1
            for i in range(len(buffer) - 4):
                if buffer[i] == 0x06:  # ACK
                    # 5バイトのACKメッセージかチェック
                    if i + 5 <= len(buffer):
                        ack_pos = i
                        break
            
            if ack_pos >= 0:
                # ACKメッセージを抽出
                ack_message = buffer[ack_pos:ack_pos + 5]
                buffer = buffer[ack_pos + 5:]
                self._parse_ack_message_safe(ack_message)
                continue
            
            # 有効なメッセージが見つからない場合、1バイト破棄
            if len(buffer) > 0:
                buffer = buffer[1:]
            else:
                break

    def _parse_enq_message_safe(self, data: bytes):
        """安全なENQメッセージ解析"""
        try:
            if len(data) < 16:
                logger.warning(f"⚠️ ENQメッセージが短すぎます: {len(data)}バイト, データ: {data.hex()}")
                return

            # デバッグ用ログ
            logger.debug(f"🔍 ENQ解析開始: {data.hex()}")

            # バイナリデータの検証と変換
            try:
                station = data[1:5].decode('ascii', errors='replace')
                command = chr(data[5]) if 32 <= data[5] <= 126 else '?'
                data_num_bytes = data[6:10]
                data_value_bytes = data[10:14]
                checksum_bytes = data[14:16]
                
                # ASCII文字のみかチェック
                data_num_str = data_num_bytes.decode('ascii', errors='replace')
                data_value_str = data_value_bytes.decode('ascii', errors='replace')
                checksum = checksum_bytes.decode('ascii', errors='replace')
                
            except Exception as e:
                logger.warning(f"⚠️ ENQメッセージのデコードエラー: {e}, データ: {data.hex()}")
                return

            # HEX文字列の検証
            if not all(c in '0123456789ABCDEFabcdef' for c in data_num_str):
                logger.warning(f"⚠️ 不正なデータ番号: {repr(data_num_str)}, データ: {data.hex()}")
                return
            
            if not all(c in '0123456789ABCDEFabcdef' for c in data_value_str):
                logger.warning(f"⚠️ 不正なデータ値: {repr(data_value_str)}, データ: {data.hex()}")
                return

            # HEX変換
            try:
                data_num = int(data_num_str, 16)
                data_value = int(data_value_str, 16)
            except ValueError as e:
                logger.warning(f"⚠️ HEX変換エラー: {e}, データ番号: {repr(data_num_str)}, データ値: {repr(data_value_str)}")
                return

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
            else:
                description = f"不明データ(0x{data_num:04X}): {data_value}"

            log_message = f"📤 {sender}→ENQ: {description}"
            logger.info(f"[{timestamp}] {log_message}")
            
            # 通信ログに追加
            self.elevator_state.add_communication_log(f"ENQ: {description}")

        except Exception as e:
            logger.error(f"❌ ENQメッセージ解析エラー: {e}, データ: {data.hex()}")

    def _parse_ack_message_safe(self, data: bytes):
        """安全なACKメッセージ解析"""
        try:
            if len(data) >= 5 and data[0] == 0x06:
                station = data[1:5].decode('ascii', errors='replace')
                timestamp = datetime.now().strftime("%Y年%m月%d日 %H:%M:%S")
                sender = "エレベーター" if station == "0002" else "自動運転装置"
                
                log_message = f"📨 {sender}→ACK応答"
                logger.info(f"[{timestamp}] {log_message}")
                
                # 通信ログに追加
                self.elevator_state.add_communication_log(f"ACK: {sender}")
                
        except Exception as e:
            logger.error(f"❌ ACKメッセージ解析エラー: {e}, データ: {data.hex()}")

    def _test_serial_connection(self) -> bool:
        """シリアル接続テスト"""
        try:
            if self.serial_conn and self.serial_conn.is_open:
                return True
            return False
        except:
            return False

    def _reconnect_serial(self) -> bool:
        """シリアル再接続"""
        try:
            logger.info("🔄 シリアルポート再接続中...")
            self._close_serial()
            time.sleep(2)  # 2秒待機
            self._connect_serial()
            logger.info("✅ シリアルポート再接続成功")
            return True
        except Exception as e:
            logger.error(f"❌ シリアルポート再接続失敗: {e}")
            self.elevator_state.set_connection_status("再接続失敗")
            return False

    def _close_serial(self):
        """シリアルポート切断"""
        try:
            if self.serial_conn and self.serial_conn.is_open:
                self.serial_conn.close()
        except:
            pass
        self.serial_conn = None
        self.elevator_state.set_connection_status("切断中")

    def shutdown(self):
        """終了処理"""
        self.stop_snooping()
        self._close_serial()
        logger.info("📡 シリアルポート切断完了")

class ElevatorRTSPServer:
    """エレベーターRTSPサーバー"""
    
    def __init__(self, elevator_state: ElevatorState, rtsp_port: int):
        self.elevator_state = elevator_state
        self.rtsp_port = rtsp_port
        self.server = None

    def start_server(self):
        """RTSPサーバー開始"""
        logger.info("📺 RTSP映像配信サーバー起動中...")
        
        try:
            Gst.init(None)
            
            self.server = GstRtspServer.RTSPServer.new()
            self.server.props.service = str(self.rtsp_port)
            
            mount = self.server.get_mount_points()
            factory = ElevatorRTSPFactory(self.elevator_state, self.rtsp_port)
            mount.add_factory(RTSP_PATH, factory)
            
            self.server.attach(None)
            
            ip = get_local_ip()
            rtsp_url = f"rtsp://{ip}:{self.rtsp_port}{RTSP_PATH}"
            
            logger.info(f"✅ RTSP配信開始: {rtsp_url}")
            logger.info(f"📱 VLCなどで上記URLを開いて映像を確認してください")
            
            return rtsp_url
            
        except Exception as e:
            logger.error(f"❌ RTSPサーバー起動エラー: {e}")
            return None

def main():
    """メイン処理"""
    import argparse
    
    parser = argparse.ArgumentParser(description='エレベーター信号スヌーピング＆RTSP映像配信システム（ENQ解析エラー修正版）')
    parser.add_argument('--port', default=SERIAL_PORT, help='シリアルポート')
    parser.add_argument('--rtsp-port', type=int, default=RTSP_PORT, help='RTSPポート番号')
    parser.add_argument('--debug', action='store_true', help='デバッグモード')
    args = parser.parse_args()
    
    # デバッグモード設定
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # 設定更新
    SERIAL_CONFIG['port'] = args.port
    rtsp_port = args.rtsp_port
    
    # シグナルハンドラー設定
    def signal_handler(signum, frame):
        logger.info(f"\n🛑 シグナル {signum} を受信しました")
        if 'snooper' in locals():
            snooper.shutdown()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # システム初期化
    logger.info("🏢 エレベーター信号スヌーピング＆RTSP映像配信システム起動（ENQ解析エラー修正版）")
    
    # エレベーター状態管理
    elevator_state = ElevatorState()
    
    # シリアルスヌーピング初期化
    snooper = SerialSnooper(elevator_state)
    if not snooper.initialize():
        logger.warning("⚠️ 初期シリアル接続に失敗しましたが、自動復帰機能で継続します")
    
    # RTSPサーバー初期化
    rtsp_server = ElevatorRTSPServer(elevator_state, rtsp_port)
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
        logger.info("🔄 シリアル接続切断時は自動復帰します")
        logger.info("🛡️ ENQ解析エラー対策済み")
        
        # GLibメインループ実行
        GLib.MainLoop().run()
        
    except Exception as e:
        logger.error(f"❌ システムエラー: {e}")
    finally:
        snooper.shutdown()
        logger.info("✅ システム終了完了")

if __name__ == "__main__":
    main()
