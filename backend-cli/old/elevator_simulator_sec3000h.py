#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SEC-3000H Elevator Simulator (SEC-3000H仕様準拠版)
エレベーター側シミュレーター（局番号: 0002）
自動運転装置に対してACK応答待ちで順次データ送信
"""

import serial
import time
import threading
import logging
import signal
import sys
from datetime import datetime
from typing import Optional, Dict, Any
from enum import IntEnum

# ── 設定 ───────────────────────────────────
SERIAL_PORT = "COM27"  # Windows の場合
# SERIAL_PORT = "/dev/ttyUSB0"  # Linux の場合

SERIAL_CONFIG = {
    'port': SERIAL_PORT,
    'baudrate': 9600,
    'bytesize': serial.EIGHTBITS,
    'parity': serial.PARITY_EVEN,
    'stopbits': serial.STOPBITS_ONE,
    'timeout': 1  # ACK応答待ち1秒（エコーバック環境対応）
}

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
    FLOOR_SETTING = 0x0010  # 階数設定（受信用）
    DOOR_CONTROL = 0x0011   # 扉制御（受信用）

# ── 扉制御コマンド ─────────────────────────────
class DoorCommands(IntEnum):
    STOP = 0x0000   # 停止
    OPEN = 0x0001   # 開扉
    CLOSE = 0x0002  # 閉扉

# ── エレベーター状態 ───────────────────────────
class ElevatorState:
    def __init__(self):
        self.current_floor = "1F"
        self.target_floor = None
        self.load_weight = 0
        self.door_status = "closed"
        self.is_moving = False

class ElevatorSimulator:
    """SEC-3000H エレベーターシミュレーター（仕様準拠版）"""
    
    def __init__(self):
        self.serial_conn: Optional[serial.Serial] = None
        self.state = ElevatorState()
        self.station_id = "0002"  # エレベーター側局番号
        self.auto_pilot_station = "0001"  # 自動運転装置側局番号
        self.running = False
        self.lock = threading.Lock()
        
        # 送信データのインデックス（SEC-3000H仕様：0001→0002→0003の順）
        self.data_sequence = [
            DataNumbers.CURRENT_FLOOR,
            DataNumbers.TARGET_FLOOR,
            DataNumbers.LOAD_WEIGHT
        ]
        self.current_data_index = 0
        self.retry_count = 0
        self.max_retries = 8  # SEC-3000H仕様：8回リトライ

    def initialize(self):
        """初期化"""
        logger.info("🏢 SEC-3000H Elevator Simulator 起動中...")
        logger.info(f"📡 シリアルポート設定: {SERIAL_CONFIG['port']}")
        logger.info(f"🏷️ 局番号: {self.station_id} (エレベーター側)")
        logger.info(f"🎯 送信先: {self.auto_pilot_station} (自動運転装置側)")
        logger.info("📋 SEC-3000H仕様準拠：ACK応答待ち、3秒タイムアウト、8回リトライ")

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
            logger.info(f"✅ シリアルポート {SERIAL_CONFIG['port']} 接続成功")
            
            # 受信スレッド開始
            threading.Thread(target=self._listen_serial, daemon=True).start()
            
        except Exception as e:
            logger.error(f"❌ シリアルポートエラー: {e}")
            raise

    def _listen_serial(self):
        """シリアル受信処理（自動運転装置からのコマンド受信）"""
        buffer = bytearray()
        
        while self.running and self.serial_conn and self.serial_conn.is_open:
            try:
                if self.serial_conn.in_waiting > 0:
                    data = self.serial_conn.read(self.serial_conn.in_waiting)
                    buffer.extend(data)
                    
                    # ACK(06H)またはENQ(05H)で始まるメッセージを検索
                    while len(buffer) >= 5:  # 最小ACKサイズ
                        if buffer[0] == 0x06:  # ACK
                            if len(buffer) >= 5:
                                ack_message = buffer[:5]
                                buffer = buffer[5:]
                                self._handle_ack_response(ack_message)
                            else:
                                break
                        elif buffer[0] == 0x05:  # ENQ（コマンド受信）
                            if len(buffer) >= 16:
                                enq_message = buffer[:16]
                                buffer = buffer[16:]
                                self._handle_received_command(enq_message)
                            else:
                                break
                        else:
                            # 不正なデータを破棄
                            buffer = buffer[1:]
                
                time.sleep(0.05)
                
            except Exception as e:
                logger.error(f"❌ シリアル受信エラー: {e}")
                break

    def _handle_ack_response(self, data: bytes):
        """ACK応答処理"""
        try:
            if len(data) >= 5 and data[0] == 0x06:
                station = data[1:5].decode('ascii')
                timestamp = datetime.now().strftime("%Y年%m月%d日 %H:%M:%S")
                
                # デバッグログ追加
                logger.info(f"🔍 ACK解析: 局番号={station}, 期待={self.elevator_station}")
                # エコーバック対応：自分の局番号（0001）のACKも受け入れる
                if station == self.elevator_station or station == self.auto_pilot_station:
                    logger.info(f"[{timestamp}] 📨 ACK受信: {data.hex().upper()}")
                    # ACK受信成功をシグナル
                    self.ack_received = True
                else:
                    logger.warning(f"⚠️ 他局からのACK: {station}")
        except Exception as e:
            logger.error(f"❌ ACK処理エラー: {e}")

    def _handle_received_command(self, data: bytes):
        """受信コマンド処理（自動運転装置からの指令）"""
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

            # コマンド処理
            if data_num == DataNumbers.FLOOR_SETTING:
                # 階数設定
                target_floor = "B1F" if data_value == 0xFFFF else f"{data_value}F"
                with self.lock:
                    old_target = self.state.target_floor
                    self.state.target_floor = target_floor
                    if old_target != target_floor:
                        self.state.is_moving = True
                        logger.info(f"🎯 階数設定受信: {target_floor}")
                        # 移動シミュレーション開始
                        threading.Thread(target=self._simulate_movement, args=(target_floor,), daemon=True).start()
                
            elif data_num == DataNumbers.DOOR_CONTROL:
                # 扉制御
                if data_value == DoorCommands.OPEN:
                    with self.lock:
                        self.state.door_status = "opening"
                        # 扉開放時に移動完了
                        if self.state.target_floor and self.state.is_moving:
                            self.state.current_floor = self.state.target_floor
                            self.state.target_floor = None
                            self.state.is_moving = False
                            logger.info(f"🏢 扉開放により到着完了: {self.state.current_floor}")
                    logger.info("🚪 扉制御受信: 開扉")
                elif data_value == DoorCommands.CLOSE:
                    with self.lock:
                        self.state.door_status = "closing"
                    logger.info("🚪 扉制御受信: 閉扉")
                else:
                    with self.lock:
                        self.state.door_status = "stopped"
                    logger.info("🚪 扉制御受信: 停止")

            # ACK応答送信
            self._send_ack_response()

        except Exception as e:
            logger.error(f"❌ 受信コマンド処理エラー: {e}")

    def _simulate_movement(self, target_floor: str):
        """移動シミュレーション"""
        time.sleep(5)  # 移動時間
        
        with self.lock:
            if self.state.is_moving and self.state.target_floor == target_floor:
                # 移動完了（扉開放まで待機）
                logger.info(f"🚀 {target_floor}への移動完了（扉開放待ち）")

    def _send_ack_response(self):
        """ACK応答送信"""
        if not self.serial_conn or not self.serial_conn.is_open:
            return

        try:
            response = bytearray([0x06])  # ACK
            response.extend(self.auto_pilot_station.encode('ascii'))  # 0001

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

    def _send_data_with_ack_wait(self, data_num: int, data_value: int) -> bool:
        """データ送信（ACK応答待ち）"""
        if not self.serial_conn or not self.serial_conn.is_open:
            return False

        try:
            # メッセージ作成
            message = bytearray()
            message.append(0x05)  # ENQ
            message.extend(self.auto_pilot_station.encode('ascii'))  # 0001（送信先）
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

            # ACK受信フラグをリセット
            self.ack_received = False

            # 送信
            self.serial_conn.write(message)

            timestamp = datetime.now().strftime("%Y年%m月%d日 %H:%M:%S")
            
            # データ内容を解釈
            description = ""
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

            logger.info(
                f"[{timestamp}] 📤 送信: ENQ(05) 局番号:{self.auto_pilot_station} CMD:W "
                f"{description} データ:{data_value_str} チェックサム:{checksum}"
            )

            # ACK応答待ち（3秒タイムアウト）
            start_time = time.time()
            while time.time() - start_time < 3.0:
                if hasattr(self, 'ack_received') and self.ack_received:
                    logger.info(f"✅ ACK受信成功 (データ番号: {data_num:04X})")
                    self.retry_count = 0  # リトライカウントリセット
                    return True
                time.sleep(0.1)

            # タイムアウト
            logger.warning(f"⏰ ACK応答タイムアウト (データ番号: {data_num:04X})")
            return False

        except Exception as e:
            logger.error(f"❌ データ送信エラー: {e}")
            return False

    def _sec3000h_transmission(self):
        """SEC-3000H仕様準拠データ送信"""
        if not self.running:
            return

        try:
            # 現在のデータ番号を取得
            data_num = self.data_sequence[self.current_data_index]
            
            with self.lock:
                if data_num == DataNumbers.CURRENT_FLOOR:
                    # 現在階数
                    if self.state.current_floor == "B1F":
                        data_value = 0xFFFF
                    else:
                        data_value = int(self.state.current_floor.replace("F", ""))
                
                elif data_num == DataNumbers.TARGET_FLOOR:
                    # 行先階
                    if self.state.target_floor is None:
                        data_value = 0x0000
                    elif self.state.target_floor == "B1F":
                        data_value = 0xFFFF
                    else:
                        data_value = int(self.state.target_floor.replace("F", ""))
                
                elif data_num == DataNumbers.LOAD_WEIGHT:
                    # 荷重
                    data_value = self.state.load_weight

            # データ送信（ACK応答待ち）
            if self._send_data_with_ack_wait(data_num, data_value):
                # ACK受信成功：次のデータ番号へ
                self.current_data_index = (self.current_data_index + 1) % len(self.data_sequence)
                self.retry_count = 0
                
                # wait無し、即座に次のデータを送信
                if self.running:
                    threading.Timer(0.1, self._sec3000h_transmission).start()
            else:
                # ACK受信失敗：リトライ処理
                self.retry_count += 1
                if self.retry_count <= self.max_retries:
                    logger.warning(f"⚠️ リトライ {self.retry_count}/{self.max_retries} (データ番号: {data_num:04X})")
                    if self.running:
                        threading.Timer(0.5, self._sec3000h_transmission).start()
                else:
                    logger.error(f"❌ 最大リトライ回数到達、通信終了 (データ番号: {data_num:04X})")
                    self.running = False

        except Exception as e:
            logger.error(f"❌ SEC-3000H送信エラー: {e}")
            if self.running:
                threading.Timer(1.0, self._sec3000h_transmission).start()

    def start_transmission(self):
        """データ送信開始"""
        if self.running:
            logger.info("⚠️ データ送信は既に実行中です")
            return

        logger.info("🚀 SEC-3000H準拠データ送信開始")
        logger.info(f"📊 送信順序: 現在階数(0001) → 行先階(0002) → 荷重(0003) → 繰り返し")
        logger.info(f"⏰ ACK応答待ち: 3秒タイムアウト、最大{self.max_retries}回リトライ")
        self.running = True

        # SEC-3000H準拠送信開始
        self._sec3000h_transmission()

    def stop_transmission(self):
        """データ送信停止"""
        logger.info("🛑 データ送信停止")
        self.running = False

    def _display_status(self):
        """状態表示"""
        timestamp = datetime.now().strftime("%Y年%m月%d日 %H:%M:%S")

        with self.lock:
            current_floor = self.state.current_floor
            target_floor = self.state.target_floor or "-"
            load_weight = self.state.load_weight
            door_status = self.state.door_status
            is_moving = "はい" if self.state.is_moving else "いいえ"

        logger.info(f"\n[{timestamp}] 🏢 エレベーター状態")
        logger.info(f"現在階: {current_floor}")
        logger.info(f"行先階: {target_floor}")
        logger.info(f"荷重: {load_weight}kg")
        logger.info(f"扉状態: {door_status}")
        logger.info(f"移動中: {is_moving}")
        logger.info(f"送信データ番号: {self.data_sequence[self.current_data_index]:04X}")
        logger.info(f"リトライ回数: {self.retry_count}/{self.max_retries}")

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

        self.stop_transmission()

        if self.serial_conn and self.serial_conn.is_open:
            self.serial_conn.close()
            logger.info("📡 シリアルポート切断完了")

        logger.info("✅ システム終了完了")

# ── メイン処理 ─────────────────────────────────
def signal_handler(signum, frame):
    """シグナルハンドラー"""
    logger.info(f"\n🛑 シグナル {signum} を受信しました")
    if 'simulator' in globals():
        simulator.shutdown()
    sys.exit(0)

def main():
    """メイン処理"""
    import argparse
    
    # コマンドライン引数解析
    parser = argparse.ArgumentParser(description='SEC-3000H Elevator Simulator (仕様準拠版)')
    parser.add_argument('--port', default=SERIAL_PORT, help='シリアルポート')
    parser.add_argument('--load', type=int, default=0, help='初期荷重 (kg)')
    args = parser.parse_args()
    
    # シグナルハンドラー設定
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # シリアルポート設定を更新
    SERIAL_CONFIG['port'] = args.port
    
    # エレベーターシミュレーター初期化
    global simulator
    simulator = ElevatorSimulator()
    simulator.state.load_weight = args.load
    
    try:
        # 初期化
        if not simulator.initialize():
            sys.exit(1)
        
        # 定期状態表示開始
        simulator.start_status_display()
        
        # データ送信開始
        simulator.start_transmission()
        
        logger.info("\n✅ SEC-3000H準拠エレベーターシミュレーター稼働中 (Ctrl+C で終了)")
        
        # メインループ
        while simulator.running:
            time.sleep(1)

    except Exception as e:
        logger.error(f"❌ システムエラー: {e}")
        simulator.shutdown()
        sys.exit(1)

if __name__ == "__main__":
    main()
