#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
エレベーターENQ受信専用RTSP映像配信システム
エレベーターからのENQメッセージのみを受信してRTSP映像で配信
ACK応答なし、受信のみに特化
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
from typing import Optional
from enum import IntEnum
from PIL import Image, ImageDraw, ImageFont
import termios

# ── 設定 ───────────────────────────────────
SERIAL_PORT = "/dev/ttyUSB0"  # Raspberry Pi（RS422アダプター）

SERIAL_CONFIG = {
    'port': SERIAL_PORT,
    'baudrate': 9600,
    'bytesize': serial.EIGHTBITS,
    'parity': serial.PARITY_EVEN,
    'stopbits': serial.STOPBITS_ONE,
    'timeout': None      # ← 0.5 → None に変更
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

class ElevatorState:
    """エレベーター状態管理（ENQ受信専用）"""
    def __init__(self):
        self.current_floor = "1F"
        self.target_floor = None
        self.load_weight = 0
        self.is_moving = False
        self.last_update = datetime.now()
        self.communication_log = []
        self.max_log_entries = 10
        self.connection_status = "切断中"
        
        # 着床検出用
        self.arrival_detected = False
        self.last_arrival_time = None

    def update_current_floor(self, floor_str: str):
        """現在階更新"""
        old_floor = self.current_floor
        self.current_floor = floor_str
        self.last_update = datetime.now()
        
        if old_floor != floor_str:
            logger.info(f"🏢 現在階変更: {old_floor} → {floor_str}")
            self.add_communication_log(f"現在階: {floor_str}")

    def update_target_floor(self, floor_str: str):
        """行先階更新（ENQ受信専用）"""
        old_target = self.target_floor
        
        if floor_str == "なし":
            # 行先階がなしになった = 着床完了
            if self.target_floor is not None:
                # 着床完了時は行先階を現在階として設定
                arrival_floor = self.target_floor
                logger.info(f"🏁 着床検出: {arrival_floor} (行先階クリア)")
                self.arrival_detected = True
                self.last_arrival_time = datetime.now()
                self.add_communication_log(f"着床完了: {arrival_floor}")
                
                # 現在階を着床階に更新（着床完了後に現在階信号が来るまでの間）
                if self.current_floor != arrival_floor:
                    logger.info(f"🏢 着床による現在階更新: {self.current_floor} → {arrival_floor}")
                    self.current_floor = arrival_floor
                    self.add_communication_log(f"現在階: {arrival_floor}")
            
            self.target_floor = None
            self.is_moving = False
        else:
            # 新しい行先階が設定された
            if old_target != floor_str:
                if old_target is None:
                    logger.info(f"🚀 移動開始: {self.current_floor} → {floor_str}")
                    self.add_communication_log(f"移動開始: {self.current_floor}→{floor_str}")
                else:
                    logger.info(f"🔄 行先階変更: {old_target} → {floor_str}")
                    self.add_communication_log(f"行先変更: {floor_str}")
            
            self.target_floor = floor_str
            
            # 移動状態の判定
            if self.current_floor != floor_str:
                self.is_moving = True
                self.arrival_detected = False
            else:
                # 現在階と行先階が同じ = 既に着床済み
                self.is_moving = False
                if not self.arrival_detected:
                    logger.info(f"🏁 即座着床: {self.current_floor} (同一階)")
                    self.arrival_detected = True
                    self.last_arrival_time = datetime.now()
        
        self.last_update = datetime.now()

    def update_load(self, weight: int):
        """荷重更新"""
        old_weight = self.load_weight
        self.load_weight = weight
        self.last_update = datetime.now()
        
        if old_weight != weight:
            logger.info(f"⚖️ 荷重変更: {old_weight}kg → {weight}kg")
            self.add_communication_log(f"荷重: {weight}kg")

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
        if self.connection_status != status:
            self.connection_status = status
            self.add_communication_log(f"接続: {status}")
            logger.info(f"📡 接続状態変更: {status}")

    def get_display_status(self):
        """表示用状態取得"""
        if self.is_moving and self.target_floor:
            return "moving", f"{self.current_floor} ⇒ {self.target_floor}"
        else:
            return "stopped", f"現在階: {self.current_floor}"

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
    """エレベーター映像配信ファクトリー（ENQ受信専用）"""
    
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
        """フレーム生成・配信（ENQ受信専用）"""
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
                title = "エレベーター監視システム（ENQ受信専用）"
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
                status_type, status_text = self.elevator_state.get_display_status()
                
                if status_type == "moving":
                    # 移動中（黄色背景）
                    status_color = 'yellow'
                    status_bg = (100, 100, 0)
                    status_border = 'orange'
                else:
                    # 停止中（緑色背景）
                    status_color = 'lightgreen'
                    status_bg = (0, 100, 0)
                    status_border = 'lightgreen'
                
                # 状態背景
                status_rect = [50, y_pos-10, WIDTH-50, y_pos+60]
                draw.rectangle(status_rect, fill=status_bg, outline=status_border, width=3)
                
                # 状態テキスト
                self._draw_centered_text(draw, status_text, font_large, WIDTH//2, y_pos+25, status_color)
                
                y_pos += 100
                
                # 詳細情報
                details = [
                    f"荷重: {self.elevator_state.load_weight}kg",
                    f"最終更新: {self.elevator_state.last_update.strftime('%H:%M:%S')}"
                ]
                
                # 着床情報表示
                if self.elevator_state.arrival_detected and self.elevator_state.last_arrival_time:
                    arrival_time = self.elevator_state.last_arrival_time.strftime('%H:%M:%S')
                    details.append(f"最終着床: {arrival_time}")
                
                for detail in details:
                    self._draw_centered_text(draw, detail, font_small, WIDTH//2, y_pos, 'lightblue')
                    y_pos += 25
                
                # 通信ログ表示
                y_pos += 15
                draw.text((20, y_pos), "ENQ受信ログ:", font=font_small, fill='white')
                y_pos += 25
                
                for log_entry in self.elevator_state.communication_log[-6:]:  # 最新6件
                    draw.text((20, y_pos), log_entry, font=font_small, fill='lightgray')
                    y_pos += 18
                
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

class SerialENQReceiver:
    """シリアルENQ受信専用クラス"""
    
    def __init__(self, elevator_state: ElevatorState):
        self.elevator_state = elevator_state
        self.serial_conn: Optional[serial.Serial] = None
        self.running = False
        # 重複チェック用の辞書を追加
        self.last_messages = {
            DataNumbers.CURRENT_FLOOR: None,  # 現在階
            DataNumbers.TARGET_FLOOR: None,   # 行先階
            DataNumbers.LOAD_WEIGHT: None     # 荷重
        }
        self.duplicate_timeout = 0.8  # 重複判定のタイムアウト（秒）を調整
        self.receive_buffer = bytearray()  # 受信バッファを追加

    def _is_duplicate_message(self, data_num: int, data_value: int) -> bool:
        """重複メッセージチェック"""
        current_time = time.time()
        last_message = self.last_messages.get(data_num)
        
        if last_message is None:
            # 初回メッセージ
            self.last_messages[data_num] = (data_value, current_time)
            return False
        
        last_value, last_time = last_message
        
        # タイムアウトチェック
        if current_time - last_time > self.duplicate_timeout:
            # タイムアウトした場合は新しいメッセージとして扱う
            self.last_messages[data_num] = (data_value, current_time)
            return False
        
        # 値が同じ場合は重複と判定
        if last_value == data_value:
            return True
        
        # 値が異なる場合は新しいメッセージとして扱う
        self.last_messages[data_num] = (data_value, current_time)
        return False

    def initialize(self):
        """初期化"""
        logger.info("📡 シリアルENQ受信専用システム初期化")
        logger.info(f"ポート: {SERIAL_CONFIG['port']}")
        logger.info("📋 受信専用モード: ACK応答なし")
        
        try:
            self._connect_serial()
            logger.info("✅ シリアル接続成功")
            return True
        except Exception as e:
            logger.error(f"❌ シリアル接続失敗: {e}")
            return False

    def _connect_serial(self):
        """シリアルポート接続＋termios 設定"""
        # タイムアウトを短く設定して1バイトずつ読み込み
        config = SERIAL_CONFIG.copy()
        config['timeout'] = 0.1  # 100ms タイムアウト
        
        self.serial_conn = serial.Serial(**config)
        
        # 受信バッファをクリア
        self.serial_conn.reset_input_buffer()
        self.receive_buffer.clear()
        
        fd = self.serial_conn.fileno()
        attrs = termios.tcgetattr(fd)
        # attrs[6] は c_cc 配列
        attrs[6][termios.VMIN]  = 1    # 1バイトずつ受信
        attrs[6][termios.VTIME] = 1    # 0.1秒（デシ秒）
        termios.tcsetattr(fd, termios.TCSANOW, attrs)

        logger.info(f"✅ シリアルポート {SERIAL_CONFIG['port']} 接続成功 (VMIN=1, VTIME=1)")
        self.elevator_state.set_connection_status("接続中")

    def start_receiving(self):
        """ENQ受信開始"""
        if self.running:
            return
        
        logger.info("🔍 シリアルENQ受信開始（受信専用モード）")
        self.running = True
        threading.Thread(target=self._receive_enq, daemon=True).start()

    def stop_receiving(self):
        """ENQ受信停止"""
        logger.info("🛑 シリアルENQ受信停止")
        self.running = False

    def _receive_enq(self):
        """ENQ受信処理（改善版）"""
        reconnect_attempts = 0
        consecutive_errors = 0
        max_consecutive_errors = 5

        while self.running:
            try:
                # シリアル接続確認
                if not (self.serial_conn and self.serial_conn.is_open):
                    if not self._reconnect_serial():
                        time.sleep(5)
                        continue

                # 1バイトずつ読み込んでバッファに蓄積
                data = self.serial_conn.read(1)
                
                if len(data) == 0:
                    # タイムアウト - 正常な状態
                    continue
                
                # 受信バッファに追加
                self.receive_buffer.extend(data)
                
                # バッファが十分に大きくなったら解析を試行
                if len(self.receive_buffer) >= 16:
                    self._parse_enq_messages(self.receive_buffer)
                
                # バッファサイズ制限（メモリリーク防止）
                if len(self.receive_buffer) > 1024:
                    logger.warning("⚠️ 受信バッファが大きくなりすぎました。クリアします。")
                    self.receive_buffer.clear()
                
                # エラーカウンターリセット
                consecutive_errors = 0

            except serial.SerialException as e:
                consecutive_errors += 1
                logger.error(f"❌ シリアル通信エラー ({consecutive_errors}/{max_consecutive_errors}): {e}")
                
                if consecutive_errors >= max_consecutive_errors:
                    logger.error("❌ 連続エラーが多すぎます。接続をリセットします。")
                    self._close_serial()
                    consecutive_errors = 0
                    time.sleep(5)
                else:
                    time.sleep(1)

            except Exception as e:
                consecutive_errors += 1
                logger.error(f"❌ 予期しないエラー ({consecutive_errors}/{max_consecutive_errors}): {e}")
                
                if consecutive_errors >= max_consecutive_errors:
                    logger.error("❌ 連続エラーが多すぎます。システムを一時停止します。")
                    time.sleep(10)
                    consecutive_errors = 0
                else:
                    time.sleep(1)

    def _parse_enq_messages(self, buffer: bytearray):
        """ENQメッセージ解析"""
        while len(buffer) >= 16:
            # ENQメッセージの検索
            enq_pos = -1
            for i in range(len(buffer) - 15):
                if buffer[i] == 0x05:  # ENQ
                    if i + 16 <= len(buffer):
                        # ENQメッセージの妥当性チェック
                        enq_candidate = buffer[i:i + 16]
                        if self._validate_enq_message(enq_candidate):
                            enq_pos = i
                            break
            
            if enq_pos >= 0:
                # ENQメッセージを抽出
                enq_message = buffer[enq_pos:enq_pos + 16]
                buffer[:] = buffer[enq_pos + 16:]
                self._parse_enq_message(enq_message)
            else:
                # 有効なENQメッセージが見つからない場合、1バイト破棄
                if len(buffer) > 0:
                    buffer.pop(0)
                else:
                    break

    def _validate_enq_message(self, data: bytes) -> bool:
        """ENQメッセージの妥当性チェック"""
        if len(data) != 16 or data[0] != 0x05:
            return False
        
        try:
            # 局番号部分（1-4バイト目）がASCII数字かチェック
            station = data[1:5]
            if not all(48 <= b <= 57 for b in station):  # '0'-'9'
                return False
            
            # コマンド部分（5バイト目）が'W'かチェック
            if data[5] != 0x57:  # 'W'
                return False
            
            # データ番号部分（6-9バイト目）がHEX文字かチェック
            data_num_bytes = data[6:10]
            if not all(self._is_hex_char(b) for b in data_num_bytes):
                return False
            
            # データ値部分（10-13バイト目）がHEX文字かチェック
            data_value_bytes = data[10:14]
            if not all(self._is_hex_char(b) for b in data_value_bytes):
                return False
            
            return True
            
        except:
            return False

    def _is_hex_char(self, byte_val: int) -> bool:
        """HEX文字かどうかチェック"""
        return (48 <= byte_val <= 57) or (65 <= byte_val <= 70) or (97 <= byte_val <= 102)  # 0-9, A-F, a-f

    def _parse_enq_message(self, data: bytes):
        """ENQメッセージ解析"""
        try:
            station = data[1:5].decode('ascii')
            command = chr(data[5])
            data_num_str = data[6:10].decode('ascii')
            data_value_str = data[10:14].decode('ascii')
            checksum = data[14:16].decode('ascii')

            data_num = int(data_num_str, 16)
            data_value = int(data_value_str, 16)

            # 重複チェック
            if self._is_duplicate_message(data_num, data_value):
                # 重複メッセージはデバッグレベルでログ出力（通常は表示されない）
                if data_num == DataNumbers.CURRENT_FLOOR:
                    floor = "B1F" if data_value == 0xFFFF else f"{data_value}F"
                    description = f"現在階数: {floor}"
                elif data_num == DataNumbers.TARGET_FLOOR:
                    if data_value == 0x0000:
                        description = "行先階: なし"
                    else:
                        floor = "B1F" if data_value == 0xFFFF else f"{data_value}F"
                        description = f"行先階: {floor}"
                elif data_num == DataNumbers.LOAD_WEIGHT:
                    description = f"荷重: {data_value}kg"
                else:
                    description = f"不明データ(0x{data_num:04X}): {data_value}"

                timestamp = datetime.now().strftime("%Y年%m月%d日 %H:%M:%S")
                logger.debug(f"[{timestamp}] 🔄 重複メッセージを破棄: {description}")
                return

            # ターミナル出力
            timestamp = datetime.now().strftime("%Y年%m月%d日 %H:%M:%S")
            
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
            else:
                description = f"不明データ(0x{data_num:04X}): {data_value}"

            log_message = f"📤 エレベーター→ENQ: {description}"
            logger.info(f"[{timestamp}] {log_message}")

        except Exception as e:
            logger.error(f"❌ ENQメッセージ解析エラー: {e}, データ: {data.hex()}")

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
        self.stop_receiving()
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
    
    parser = argparse.ArgumentParser(description='エレベーターENQ受信専用RTSP映像配信システム')
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
        if 'receiver' in locals():
            receiver.shutdown()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # システム初期化
    logger.info("🏢 エレベーターENQ受信専用RTSP映像配信システム起動")
    
    # エレベーター状態管理
    elevator_state = ElevatorState()
    
    # シリアルENQ受信初期化
    receiver = SerialENQReceiver(elevator_state)
    if not receiver.initialize():
        logger.warning("⚠️ 初期シリアル接続に失敗しましたが、自動復帰機能で継続します")
    
    # RTSPサーバー初期化
    rtsp_server = ElevatorRTSPServer(elevator_state, rtsp_port)
    rtsp_url = rtsp_server.start_server()
    if not rtsp_url:
        logger.error("❌ RTSPサーバー起動失敗")
        sys.exit(1)
    
    try:
        # ENQ受信開始
        receiver.start_receiving()
        
        logger.info("\n✅ システム稼働中 (Ctrl+C で終了)")
        logger.info(f"📡 シリアル監視: {args.port}")
        logger.info(f"📺 RTSP配信: {rtsp_url}")
        logger.info("🔍 エレベーターからのENQメッセージを受信中...")
        logger.info("📋 受信専用モード: ACK応答なし")
        logger.info("🔄 シリアル接続切断時は自動復帰します")
        
        # GLibメインループ実行
        GLib.MainLoop().run()
        
    except Exception as e:
        logger.error(f"❌ システムエラー: {e}")
    finally:
        receiver.shutdown()
        logger.info("✅ システム終了完了")

if __name__ == "__main__":
    main()
