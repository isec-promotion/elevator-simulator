#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SEC-3000H ハンドシェイク型通信システム
エレベーター側：疎通確認→データ送信→制御受信
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
SERIAL_PORT = "COM27"

SERIAL_CONFIG = {
    'port': SERIAL_PORT,
    'baudrate': 9600,
    'bytesize': serial.EIGHTBITS,
    'parity': serial.PARITY_EVEN,
    'stopbits': serial.STOPBITS_ONE,
    'timeout': 1
}

# ── ログ設定 ─────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ── 通信状態 ─────────────────────────────────
class CommState(IntEnum):
    DISCONNECTED = 0    # 未接続
    HANDSHAKING = 1     # ハンドシェイク中
    CONNECTED = 2       # 接続確立
    DATA_EXCHANGE = 3   # データ交換中
    CONTROL_MODE = 4    # 制御モード

# ── コマンド定義 ─────────────────────────────
class Commands(IntEnum):
    PING = 0x0000       # 疎通確認
    PONG = 0x0001       # 疎通応答
    STATUS_REQ = 0x0010 # 状態要求
    STATUS_RSP = 0x0011 # 状態応答
    CONTROL_REQ = 0x0020 # 制御要求
    CONTROL_ACK = 0x0021 # 制御確認
    FLOOR_CMD = 0x0030  # 階数指令
    DOOR_CMD = 0x0031   # 扉制御

class ElevatorHandshakeSystem:
    """ハンドシェイク型エレベーター通信システム"""
    
    def __init__(self):
        self.serial_conn: Optional[serial.Serial] = None
        self.station_id = "0002"  # エレベーター側
        self.auto_pilot_station = "0001"  # 自動運転装置側
        self.running = False
        self.comm_state = CommState.DISCONNECTED
        self.lock = threading.Lock()
        
        # エレベーター状態
        self.current_floor = 1
        self.target_floor = None
        self.load_weight = 0
        self.door_status = "closed"
        self.is_moving = False
        
        # 通信管理
        self.last_ping_time = 0
        self.ping_interval = 5.0  # 5秒間隔でPING
        self.response_timeout = 3.0
        self.auto_pilot_active = False

    def initialize(self):
        """初期化"""
        logger.info("🏢 SEC-3000H ハンドシェイク型通信システム 起動中...")
        logger.info(f"📡 シリアルポート: {SERIAL_CONFIG['port']}")
        logger.info(f"🏷️ 局番号: {self.station_id} (エレベーター側)")
        logger.info(f"🎯 通信相手: {self.auto_pilot_station} (自動運転装置側)")

        try:
            self.serial_conn = serial.Serial(**SERIAL_CONFIG)
            logger.info(f"✅ シリアルポート接続成功")
            
            # 受信スレッド開始
            self.running = True
            threading.Thread(target=self._listen_serial, daemon=True).start()
            
            return True
        except Exception as e:
            logger.error(f"❌ 初期化失敗: {e}")
            return False

    def _listen_serial(self):
        """シリアル受信処理"""
        buffer = bytearray()
        
        while self.running and self.serial_conn and self.serial_conn.is_open:
            try:
                if self.serial_conn.in_waiting > 0:
                    data = self.serial_conn.read(self.serial_conn.in_waiting)
                    if data:
                        buffer.extend(data)
                        self._process_buffer(buffer)
                
                time.sleep(0.05)
                
            except Exception as e:
                logger.error(f"❌ シリアル受信エラー: {e}")
                break

    def _process_buffer(self, buffer: bytearray):
        """バッファ処理"""
        while len(buffer) >= 16:  # 最小メッセージサイズ
            if buffer[0] == 0x05:  # ENQ
                message = buffer[:16]
                del buffer[:16]
                self._handle_received_message(message)
            else:
                del buffer[0]  # 不正データ破棄

    def _handle_received_message(self, data: bytes):
        """受信メッセージ処理"""
        try:
            if len(data) < 16 or data[0] != 0x05:
                return

            # メッセージ解析
            station = data[1:5].decode('ascii')
            command = chr(data[5])
            cmd_code_str = data[6:10].decode('ascii')
            data_value_str = data[10:14].decode('ascii')
            checksum = data[14:16].decode('ascii')

            # 自分宛かチェック
            if station != self.station_id:
                return

            cmd_code = int(cmd_code_str, 16)
            data_value = int(data_value_str, 16)

            timestamp = datetime.now().strftime("%H:%M:%S")
            logger.info(f"[{timestamp}] 📨 受信: CMD={cmd_code:04X} データ={data_value:04X}")

            # コマンド処理
            if cmd_code == Commands.PING:
                # PING受信 → PONG応答
                logger.info("🏓 PING受信 → PONG送信")
                self._send_command(Commands.PONG, 0x0000)
                with self.lock:
                    if self.comm_state == CommState.DISCONNECTED:
                        self.comm_state = CommState.HANDSHAKING
                        logger.info("🤝 ハンドシェイク開始")

            elif cmd_code == Commands.STATUS_REQ:
                # 状態要求 → 状態応答
                logger.info("📊 状態要求受信 → 状態応答送信")
                status_data = (self.current_floor << 8) | self.load_weight
                self._send_command(Commands.STATUS_RSP, status_data)
                with self.lock:
                    if self.comm_state == CommState.HANDSHAKING:
                        self.comm_state = CommState.CONNECTED
                        logger.info("✅ 通信確立完了")

            elif cmd_code == Commands.CONTROL_REQ:
                # 制御要求 → 制御確認
                logger.info("🎮 制御要求受信 → 制御確認送信")
                self._send_command(Commands.CONTROL_ACK, 0x0000)
                with self.lock:
                    self.comm_state = CommState.CONTROL_MODE
                    self.auto_pilot_active = True
                    logger.info("🚀 自動運転モード開始")

            elif cmd_code == Commands.FLOOR_CMD:
                # 階数指令
                target_floor = data_value
                logger.info(f"🎯 階数指令受信: {target_floor}F")
                with self.lock:
                    self.target_floor = target_floor
                    self.is_moving = True
                # 移動シミュレーション開始
                threading.Thread(target=self._simulate_movement, daemon=True).start()

            elif cmd_code == Commands.DOOR_CMD:
                # 扉制御
                if data_value == 0x0001:  # 開扉
                    logger.info("🚪 扉開放指令受信")
                    with self.lock:
                        self.door_status = "opening"
                        if self.target_floor and self.is_moving:
                            self.current_floor = self.target_floor
                            self.target_floor = None
                            self.is_moving = False
                            logger.info(f"🏢 到着完了: {self.current_floor}F")
                elif data_value == 0x0002:  # 閉扉
                    logger.info("🚪 扉閉鎖指令受信")
                    with self.lock:
                        self.door_status = "closing"

        except Exception as e:
            logger.error(f"❌ メッセージ処理エラー: {e}")

    def _simulate_movement(self):
        """移動シミュレーション"""
        time.sleep(3)  # 移動時間
        with self.lock:
            if self.is_moving:
                logger.info(f"🚀 {self.target_floor}F到着（扉開放待ち）")

    def _calculate_checksum(self, data: bytes) -> str:
        """チェックサム計算"""
        total = sum(data)
        lower_byte = total & 0xFF
        upper_byte = (total >> 8) & 0xFF
        checksum = (lower_byte + upper_byte) & 0xFF
        return f"{checksum:02X}"

    def _send_command(self, cmd_code: int, data_value: int) -> bool:
        """コマンド送信"""
        if not self.serial_conn or not self.serial_conn.is_open:
            return False

        try:
            # メッセージ作成
            message = bytearray()
            message.append(0x05)  # ENQ
            message.extend(self.auto_pilot_station.encode('ascii'))  # 送信先
            message.append(0x57)  # 'W'
            message.extend(f"{cmd_code:04X}".encode('ascii'))
            message.extend(f"{data_value:04X}".encode('ascii'))
            
            # チェックサム
            checksum_data = message[1:]
            checksum = self._calculate_checksum(checksum_data)
            message.extend(checksum.encode('ascii'))

            # 送信
            self.serial_conn.write(message)
            
            timestamp = datetime.now().strftime("%H:%M:%S")
            logger.info(f"[{timestamp}] 📤 送信: CMD={cmd_code:04X} データ={data_value:04X}")
            
            return True

        except Exception as e:
            logger.error(f"❌ コマンド送信エラー: {e}")
            return False

    def start_communication(self):
        """通信開始"""
        logger.info("🚀 ハンドシェイク型通信開始")
        logger.info("📋 通信フロー:")
        logger.info("  1. PING送信 → PONG受信（疎通確認）")
        logger.info("  2. 状態送信 → 状態確認（接続確立）")
        logger.info("  3. 制御待機 → 自動運転開始")
        
        # 通信管理スレッド開始
        threading.Thread(target=self._communication_manager, daemon=True).start()

    def _communication_manager(self):
        """通信管理"""
        while self.running:
            try:
                current_time = time.time()
                
                with self.lock:
                    state = self.comm_state
                
                if state == CommState.DISCONNECTED:
                    # 定期的にPING送信
                    if current_time - self.last_ping_time >= self.ping_interval:
                        logger.info("🏓 PING送信（疎通確認）")
                        self._send_command(Commands.PING, 0x0000)
                        self.last_ping_time = current_time
                
                elif state == CommState.CONNECTED:
                    # 定期的に状態送信
                    if current_time - self.last_ping_time >= 10.0:
                        logger.info("📊 状態送信")
                        status_data = (self.current_floor << 8) | self.load_weight
                        self._send_command(Commands.STATUS_RSP, status_data)
                        self.last_ping_time = current_time
                
                time.sleep(1)
                
            except Exception as e:
                logger.error(f"❌ 通信管理エラー: {e}")

    def _display_status(self):
        """状態表示"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        with self.lock:
            state_names = {
                CommState.DISCONNECTED: "未接続",
                CommState.HANDSHAKING: "ハンドシェイク中",
                CommState.CONNECTED: "接続確立",
                CommState.DATA_EXCHANGE: "データ交換中",
                CommState.CONTROL_MODE: "制御モード"
            }
            
            state_name = state_names.get(self.comm_state, "不明")
            auto_status = "有効" if self.auto_pilot_active else "無効"
            target = f"{self.target_floor}F" if self.target_floor else "-"
            moving = "移動中" if self.is_moving else "停止中"

        logger.info(f"\n[{timestamp}] 🏢 システム状態")
        logger.info(f"通信状態: {state_name}")
        logger.info(f"自動運転: {auto_status}")
        logger.info(f"現在階: {self.current_floor}F")
        logger.info(f"行先階: {target}")
        logger.info(f"動作状態: {moving}")
        logger.info(f"扉状態: {self.door_status}")
        logger.info(f"荷重: {self.load_weight}kg")

    def start_status_display(self):
        """定期状態表示開始"""
        def _status_timer():
            if self.running:
                self._display_status()
                threading.Timer(15.0, _status_timer).start()

        _status_timer()

    def shutdown(self):
        """終了処理"""
        logger.info("🛑 システム終了中...")
        self.running = False
        if self.serial_conn and self.serial_conn.is_open:
            self.serial_conn.close()
        logger.info("✅ システム終了完了")

# ── メイン処理 ─────────────────────────────────
def signal_handler(signum, frame):
    """シグナルハンドラー"""
    logger.info(f"\n🛑 シグナル {signum} を受信しました")
    if 'system' in globals():
        system.shutdown()
    sys.exit(0)

def main():
    """メイン処理"""
    import argparse
    
    parser = argparse.ArgumentParser(description='SEC-3000H ハンドシェイク型通信システム')
    parser.add_argument('--port', default=SERIAL_PORT, help='シリアルポート')
    args = parser.parse_args()
    
    # シグナルハンドラー設定
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # シリアルポート設定を更新
    SERIAL_CONFIG['port'] = args.port
    
    # システム初期化
    global system
    system = ElevatorHandshakeSystem()
    
    try:
        if not system.initialize():
            sys.exit(1)
        
        # 通信開始
        system.start_communication()
        
        # 定期状態表示開始
        system.start_status_display()
        
        logger.info("\n✅ ハンドシェイク型通信システム稼働中 (Ctrl+C で終了)")
        
        # メインループ
        while system.running:
            time.sleep(1)

    except KeyboardInterrupt:
        logger.info("\n🛑 Ctrl+C で終了")
    except Exception as e:
        logger.error(f"❌ システムエラー: {e}")
    finally:
        system.shutdown()

if __name__ == "__main__":
    main()
