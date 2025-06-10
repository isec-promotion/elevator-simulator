#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
エレベーターENQ受信専用システム
エレベーターからのENQメッセージのみを受信
ACK応答なし、受信のみに特化
"""

import serial
import threading
import time
import logging
import signal
import sys
from datetime import datetime
from typing import Optional
from enum import IntEnum

# ── 設定 ───────────────────────────────────
SERIAL_PORT = "/dev/ttyUSB0"  # Raspberry Pi（RS422アダプター）

SERIAL_CONFIG = {
    'port': SERIAL_PORT,
    'baudrate': 9600,
    'bytesize': serial.EIGHTBITS,
    'parity': serial.PARITY_EVEN,
    'stopbits': serial.STOPBITS_ONE,
    'timeout': 0.5
}

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
                logger.info(f"🏁 着床検出: {self.current_floor} (行先階クリア)")
                self.arrival_detected = True
                self.last_arrival_time = datetime.now()
                self.add_communication_log(f"着床完了: {self.current_floor}")
            
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
        self.duplicate_timeout = 0.2  # 重複判定のタイムアウト（秒）

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
        """シリアルポート接続"""
        try:
            self.serial_conn = serial.Serial(**SERIAL_CONFIG)
            logger.info(f"✅ シリアルポート {SERIAL_CONFIG['port']} 接続成功")
            self.elevator_state.set_connection_status("接続中")
        except Exception as e:
            logger.error(f"❌ シリアルポートエラー: {e}")
            self.elevator_state.set_connection_status("切断中")
            raise

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
        """ENQ受信処理"""
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
                    
                    # ENQメッセージ解析
                    self._parse_enq_messages(buffer)
                
                # 長時間データが来ない場合の接続チェック
                if time.time() - last_data_time > 30:  # 30秒間データなし
                    logger.warning("⚠️ 30秒間データを受信していません。接続を確認中...")
                    if not self._test_serial_connection():
                        self._close_serial()
                        continue
                    last_data_time = time.time()
                
                time.sleep(0.1)  # 0.05 → 0.1秒に変更（CPU負荷軽減）
                
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
                # データ内容の解釈（ログ表示用）
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
                logger.info(f"[{timestamp}] 🔄 重複メッセージを破棄しました: {description}")
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

def main():
    """メイン処理"""
    import argparse
    
    parser = argparse.ArgumentParser(description='エレベーターENQ受信専用システム')
    parser.add_argument('--port', default=SERIAL_PORT, help='シリアルポート')
    parser.add_argument('--debug', action='store_true', help='デバッグモード')
    args = parser.parse_args()
    
    # デバッグモード設定
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # 設定更新
    SERIAL_CONFIG['port'] = args.port
    
    # シグナルハンドラー設定
    def signal_handler(signum, frame):
        logger.info(f"\n🛑 シグナル {signum} を受信しました")
        if 'receiver' in locals():
            receiver.shutdown()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # システム初期化
    logger.info("🏢 エレベーターENQ受信専用システム起動")
    
    # エレベーター状態管理
    elevator_state = ElevatorState()
    
    # シリアルENQ受信初期化
    receiver = SerialENQReceiver(elevator_state)
    if not receiver.initialize():
        logger.warning("⚠️ 初期シリアル接続に失敗しましたが、自動復帰機能で継続します")
    
    try:
        # ENQ受信開始
        receiver.start_receiving()
        
        logger.info("\n✅ システム稼働中 (Ctrl+C で終了)")
        logger.info(f"📡 シリアル監視: {args.port}")
        logger.info("🔍 エレベーターからのENQメッセージを受信中...")
        logger.info("📋 受信専用モード: ACK応答なし")
        logger.info("🔄 シリアル接続切断時は自動復帰します")
        
        # メインループ
        while True:
            time.sleep(1)
            
    except Exception as e:
        logger.error(f"❌ システムエラー: {e}")
    finally:
        receiver.shutdown()
        logger.info("✅ システム終了完了")

if __name__ == "__main__":
    main()
