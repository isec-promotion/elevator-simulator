#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
エレベーターENQ受信専用RTSP映像配信システム（マルチスレッド改良版）
シリアル受信とRTSP配信を完全に分離したマルチスレッド実装
シリアル信号の受信漏れを回避するための最適化

主な改良点：
1. シリアル受信スレッドと処理スレッドの分離
2. スレッドセーフな状態管理
3. メッセージキューによる非同期処理
4. 高速化されたシリアル受信ループ
5. 統計情報の追加
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
import queue
from datetime import datetime
from typing import Optional
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
    'timeout': 0.1  # タイムアウトを短縮（受信漏れ回避）
}

# RTSP配信設定
WIDTH, HEIGHT, FPS = 640, 480, 15
RTSP_PORT = 8554
RTSP_PATH = "/elevator"

# スレッド間通信設定
MESSAGE_QUEUE_SIZE = 1000  # メッセージキューサイズ
SERIAL_BUFFER_SIZE = 4096  # シリアルバッファサイズ

# ── ログ設定 ─────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(threadName)s] - %(message)s'
)
logger = logging.getLogger(__name__)

# ── データ番号定義 ─────────────────────────────
class DataNumbers(IntEnum):
    CURRENT_FLOOR = 0x0001  # 現在階数
    TARGET_FLOOR = 0x0002   # 行先階
    LOAD_WEIGHT = 0x0003    # 荷重

class ElevatorState:
    """エレベーター状態管理（スレッドセーフ）"""
    def __init__(self):
        self._lock = threading.RLock()  # 再帰ロック
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
        
        # 統計情報
        self.message_count = 0
        self.error_count = 0

    def update_current_floor(self, floor_str: str):
        """現在階更新（スレッドセーフ）"""
        with self._lock:
            old_floor = self.current_floor
            self.current_floor = floor_str
            self.last_update = datetime.now()
            
            if old_floor != floor_str:
                logger.info(f"🏢 現在階変更: {old_floor} → {floor_str}")
                self._add_communication_log_unsafe(f"現在階: {floor_str}")

    def update_target_floor(self, floor_str: str):
        """行先階更新（スレッドセーフ）"""
        with self._lock:
            old_target = self.target_floor
            
            if floor_str == "なし":
                # 行先階がなしになった = 着床完了
                if self.target_floor is not None:
                    logger.info(f"🏁 着床検出: {self.current_floor} (行先階クリア)")
                    self.arrival_detected = True
                    self.last_arrival_time = datetime.now()
                    self._add_communication_log_unsafe(f"着床完了: {self.current_floor}")
                
                self.target_floor = None
                self.is_moving = False
            else:
                # 新しい行先階が設定された
                if old_target != floor_str:
                    if old_target is None:
                        logger.info(f"🚀 移動開始: {self.current_floor} → {floor_str}")
                        self._add_communication_log_unsafe(f"移動開始: {self.current_floor}→{floor_str}")
                    else:
                        logger.info(f"🔄 行先階変更: {old_target} → {floor_str}")
                        self._add_communication_log_unsafe(f"行先変更: {floor_str}")
                
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
        """荷重更新（スレッドセーフ）"""
        with self._lock:
            old_weight = self.load_weight
            self.load_weight = weight
            self.last_update = datetime.now()
            
            if old_weight != weight:
                logger.info(f"⚖️ 荷重変更: {old_weight}kg → {weight}kg")
                self._add_communication_log_unsafe(f"荷重: {weight}kg")

    def _add_communication_log_unsafe(self, message: str):
        """通信ログ追加（ロック不要版）"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] {message}"
        self.communication_log.append(log_entry)
        
        # ログ数制限
        if len(self.communication_log) > self.max_log_entries:
            self.communication_log.pop(0)

    def add_communication_log(self, message: str):
        """通信ログ追加（スレッドセーフ）"""
        with self._lock:
            self._add_communication_log_unsafe(message)

    def set_connection_status(self, status: str):
        """接続状態更新（スレッドセーフ）"""
        with self._lock:
            if self.connection_status != status:
                self.connection_status = status
                self._add_communication_log_unsafe(f"接続: {status}")
                logger.info(f"📡 接続状態変更: {status}")

    def increment_message_count(self):
        """メッセージカウント増加（スレッドセーフ）"""
        with self._lock:
            self.message_count += 1

    def increment_error_count(self):
        """エラーカウント増加（スレッドセーフ）"""
        with self._lock:
            self.error_count += 1

    def get_safe_copy(self):
        """状態の安全なコピーを取得"""
        with self._lock:
            return {
                'current_floor': self.current_floor,
                'target_floor': self.target_floor,
                'load_weight': self.load_weight,
                'is_moving': self.is_moving,
                'last_update': self.last_update,
                'communication_log': self.communication_log.copy(),
                'connection_status': self.connection_status,
                'arrival_detected': self.arrival_detected,
                'last_arrival_time': self.last_arrival_time,
                'message_count': self.message_count,
                'error_count': self.error_count
            }

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
    """エレベーター映像配信ファクトリー（マルチスレッド対応）"""
    
    def __init__(self, elevator_state: ElevatorState, rtsp_port: int):
        super().__init__()
        self.elevator_state = elevator_state
        self.rtsp_port = rtsp_port
        self.set_shared(True)
        self._frame_thread = None
        self._frame_running = False
        
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
        
        # フレーム生成スレッドを開始
        if not self._frame_running:
            self._frame_running = True
            self._frame_thread = threading.Thread(
                target=self.push_frames, 
                name="RTSP-FrameGenerator",
                daemon=True
            )
            self._frame_thread.start()
            logger.info("📺 RTSP フレーム生成スレッド開始")
        
        return pipeline

    def push_frames(self):
        """フレーム生成・配信（専用スレッド）"""
        logger.info("🎬 RTSP フレーム生成開始")
        
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

        frame_count = 0
        last_fps_time = time.time()
        actual_fps = 0

        while self._frame_running:
            try:
                # エレベーター状態の安全なコピーを取得
                state = self.elevator_state.get_safe_copy()
                
                # 背景画像作成
                img = Image.new('RGB', (WIDTH, HEIGHT), (20, 30, 50))  # 濃紺背景
                draw = ImageDraw.Draw(img)
                
                # 現在時刻
                now = datetime.now()
                timestamp = now.strftime("%Y年%m月%d日 %H:%M:%S")
                
                # タイトル
                title = "エレベーター監視システム（マルチスレッド版）"
                self._draw_centered_text(draw, title, font_medium, WIDTH//2, 40, 'white')
                
                # 現在時刻表示
                self._draw_centered_text(draw, timestamp, font_small, WIDTH//2, 80, 'lightgray')
                
                # 接続状態表示
                connection_color = 'lightgreen' if state['connection_status'] == "接続中" else 'red'
                self._draw_centered_text(draw, f"接続状態: {state['connection_status']}", 
                                       font_small, WIDTH//2, 110, connection_color)
                
                # エレベーター状態表示
                y_pos = 150
                
                # 状態判定
                if state['is_moving'] and state['target_floor']:
                    status_text = f"{state['current_floor']} ⇒ {state['target_floor']}"
                    status_color = 'yellow'
                    status_bg = (100, 100, 0)
                    status_border = 'orange'
                else:
                    status_text = f"現在階: {state['current_floor']}"
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
                    f"荷重: {state['load_weight']}kg",
                    f"最終更新: {state['last_update'].strftime('%H:%M:%S')}",
                    f"受信数: {state['message_count']} / エラー数: {state['error_count']}",
                    f"実際FPS: {actual_fps:.1f}"
                ]
                
                # 着床情報表示
                if state['arrival_detected'] and state['last_arrival_time']:
                    arrival_time = state['last_arrival_time'].strftime('%H:%M:%S')
                    details.append(f"最終着床: {arrival_time}")
                
                for detail in details:
                    self._draw_centered_text(draw, detail, font_small, WIDTH//2, y_pos, 'lightblue')
                    y_pos += 25
                
                # 通信ログ表示
                y_pos += 15
                draw.text((20, y_pos), "ENQ受信ログ:", font=font_small, fill='white')
                y_pos += 25
                
                for log_entry in state['communication_log'][-6:]:  # 最新6件
                    draw.text((20, y_pos), log_entry, font=font_small, fill='lightgray')
                    y_pos += 18
                
                # フレームバッファに送信
                buf = pil_to_gst_buffer(img)
                ret = self.appsrc.emit('push-buffer', buf)
                if ret != Gst.FlowReturn.OK:
                    logger.warning("⚠️ フレームバッファ送信失敗")
                    break
                
                # FPS計算
                frame_count += 1
                current_time = time.time()
                if current_time - last_fps_time >= 1.0:
                    actual_fps = frame_count / (current_time - last_fps_time)
                    frame_count = 0
                    last_fps_time = current_time
                
                time.sleep(1.0 / FPS)
                
            except Exception as e:
                logger.error(f"❌ フレーム生成エラー: {e}")
                time.sleep(1.0)

        logger.info("🎬 RTSP フレーム生成終了")

    def _draw_centered_text(self, draw, text, font, x, y, color):
        """中央揃えテキスト描画"""
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        draw.text((x - text_width//2, y - text_height//2), text, font=font, fill=color)

    def stop_frames(self):
        """フレーム生成停止"""
        self._frame_running = False
        if self._frame_thread and self._frame_thread.is_alive():
            self._frame_thread.join(timeout=2.0)

class SerialENQReceiver:
    """シリアルENQ受信専用クラス（高速化対応）"""
    
    def __init__(self, elevator_state: ElevatorState):
        self.elevator_state = elevator_state
        self.serial_conn: Optional[serial.Serial] = None
        self.running = False
        self.message_queue = queue.Queue(maxsize=MESSAGE_QUEUE_SIZE)
        
        # 受信スレッドと処理スレッドを分離
        self._receive_thread = None
        self._process_thread = None
        
        # 重複チェック用の辞書
        self.last_messages = {
            DataNumbers.CURRENT_FLOOR: None,
            DataNumbers.TARGET_FLOOR: None,
            DataNumbers.LOAD_WEIGHT: None
        }
        self.duplicate_timeout = 0.2

    def _is_duplicate_message(self, data_num: int, data_value: int) -> bool:
        """重複メッセージチェック"""
        current_time = time.time()
        last_message = self.last_messages.get(data_num)
        
        if last_message is None:
            self.last_messages[data_num] = (data_value, current_time)
            return False
        
        last_value, last_time = last_message
        
        if current_time - last_time > self.duplicate_timeout:
            self.last_messages[data_num] = (data_value, current_time)
            return False
        
        if last_value == data_value:
            return True
        
        self.last_messages[data_num] = (data_value, current_time)
        return False

    def initialize(self):
        """初期化"""
        logger.info("📡 シリアルENQ受信専用システム初期化（マルチスレッド版）")
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
        """シリアルポート接続"""
        try:
            self.serial_conn = serial.Serial(**SERIAL_CONFIG)
            # バッファサイズ設定
            if hasattr(self.serial_conn, 'set_buffer_size'):
                self.serial_conn.set_buffer_size(rx_size=SERIAL_BUFFER_SIZE)
            
            logger.info(f"✅ シリアルポート {SERIAL_CONFIG['port']} 接続成功")
            self.elevator_state.set_connection_status("接続中")
        except Exception as e:
            logger.error(f"❌ シリアルポートエラー: {e}")
            self.elevator_state.set_connection_status("切断中")
            raise

    def start_receiving(self):
        """ENQ受信開始（マルチスレッド）"""
        if self.running:
            return
        
        logger.info("🔍 シリアルENQ受信開始（マルチスレッド版）")
        self.running = True
        
        # 受信スレッド開始
        self._receive_thread = threading.Thread(
            target=self._receive_raw_data, 
            name="Serial-Receiver",
            daemon=True
        )
        self._receive_thread.start()
        
        # 処理スレッド開始
        self._process_thread = threading.Thread(
            target=self._process_messages, 
            name="Message-Processor",
            daemon=True
        )
        self._process_thread.start()
        
        logger.info("✅ シリアル受信・処理スレッド開始完了")

    def stop_receiving(self):
        """ENQ受信停止"""
        logger.info("🛑 シリアルENQ受信停止")
        self.running = False
        
        # スレッド終了待機
        if self._receive_thread and self._receive_thread.is_alive():
            self._receive_thread.join(timeout=2.0)
        if self._process_thread and self._process_thread.is_alive():
            self._process_thread.join(timeout=2.0)

    def _receive_raw_data(self):
        """生データ受信スレッド（高速化）"""
        logger.info("📥 シリアル生データ受信スレッド開始")
        buffer = bytearray()
        reconnect_attempts = 0
        max_reconnect_attempts = 10
        last_data_time = time.time()
        
        while self.running:
            try:
                # シリアル接続チェック
                if not self.serial_conn or not self.serial_conn.is_open:
                    if not self._reconnect_serial():
                        time.sleep(1)  # 短縮
                        continue
                    buffer.clear()
                    reconnect_attempts = 0
                    last_data_time = time.time()
                
                # データ受信（ノンブロッキング）
                if self.serial_conn.in_waiting > 0:
                    data = self.serial_conn.read(self.serial_conn.in_waiting)
                    if data:
                        buffer.extend(data)
                        last_data_time = time.time()
                        
                        # ENQメッセージ検索・キューイング
                        self._extract_enq_messages(buffer)
                
                # 接続チェック（間隔短縮）
                if time.time() - last_data_time > 15:  # 15秒に短縮
                    if not self._test_serial_connection():
                        self._close_serial()
                        continue
                    last_data_time = time.time()
                
                time.sleep(0.01)  # 10ms（高速化）
                
            except serial.SerialException as e:
                logger.error(f"❌ シリアル通信エラー: {e}")
                self._close_serial()
                reconnect_attempts += 1
                
                if reconnect_attempts >= max_reconnect_attempts:
                    logger.error(f"❌ 最大再接続試行回数({max_reconnect_attempts})に達しました")
                    self.elevator_state.set_connection_status("接続失敗")
                    time.sleep(5)
                    reconnect_attempts = 0
                    continue
                
                logger.info(f"🔄 {reconnect_attempts}/{max_reconnect_attempts} 回目の再接続を試行中...")
                time.sleep(1)
                
            except Exception as e:
                logger.error(f"❌ 予期しないエラー: {e}")
                self.elevator_state.increment_error_count()
                time.sleep(0.1)

        logger.info("📥 シリアル生データ受信スレッド終了")

    def _extract_enq_messages(self, buffer: bytearray):
        """ENQメッセージ抽出・キューイング"""
        while len(buffer) >= 16:
            enq_pos = -1
            for i in range(len(buffer) - 15):
                if buffer[i] == 0x05:  # ENQ
                    if i + 16 <= len(buffer):
                        enq_candidate = buffer[i:i + 16]
                        if self._validate_enq_message(enq_candidate):
                            enq_pos = i
                            break
            
            if enq_pos >= 0:
                enq_message = buffer[enq_pos:enq_pos + 16]
                buffer[:] = buffer[enq_pos + 16:]
                
                # メッセージをキューに追加
                try:
                    self.message_queue.put_nowait(enq_message)
                except queue.Full:
                    logger.warning("⚠️ メッセージキューが満杯です")
                    # 古いメッセージを破棄
                    try:
                        self.message_queue.get_nowait()
                        self.message_queue.put_nowait(enq_message)
                    except queue.Empty:
                        pass
            else:
                if len(buffer) > 0:
                    buffer.pop(0)
                else:
                    break

    def _process_messages(self):
        """メッセージ処理スレッド"""
        logger.info("⚙️ メッセージ処理スレッド開始")
        
        while self.running:
            try:
                # キューからメッセージを取得（タイムアウト付き）
                message = self.message_queue.get(timeout=1.0)
                self._parse_enq_message(message)
                self.elevator_state.increment_message_count()
                
            except queue.Empty:
                continue  # タイムアウト時は継続
            except Exception as e:
                logger.error(f"❌ メッセージ処理エラー: {e}")
                self.elevator_state.increment_error_count()
                time.sleep(0.1)

        logger.info("⚙️ メッセージ処理スレッド終了")

    def _validate_enq_message(self, data: bytes) -> bool:
        """ENQメッセージの妥当性チェック"""
        if len(data) != 16 or data[0] != 0x05:
            return False
        
        try:
            station = data[1:5]
            if not all(48 <= b <= 57 for b in station):
                return False
            
            if data[5] != 0x57:  # 'W'
                return False
            
            data_num_bytes = data[6:10]
            if not all(self._is_hex_char(b) for b in data_num_bytes):
                return False
            
            data_value_bytes = data[10:14]
            if not all(self._is_hex_char(b) for b in data_value_bytes):
                return False
            
            return True
            
        except:
            return False

    def _is_hex_char(self, byte_val: int) -> bool:
        """HEX文字かどうかチェック"""
        return (48 <= byte_val <= 57) or (65 <= byte_val <= 70) or (97 <= byte_val <= 102)

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
