#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SEC-3000H ハンドシェイク型自動運転装置
Raspberry Pi側：疎通応答→状態確認→制御開始
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
SERIAL_PORT = "/dev/ttyUSB0"  # Raspberry Pi の場合

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

class AutoPilotHandshake:
    """ハンドシェイク型自動運転装置"""
    
    def __init__(self):
        self.serial_conn: Optional[serial.Serial] = None
        self.station_id = "0001"  # 自動運転装置側
        self.elevator_station = "0002"  # エレベーター側
        self.running = False
        self.comm_state = CommState.DISCONNECTED
        self.lock = threading.Lock()
        
        # エレベーター状態（受信データ）
        self.elevator_floor = 1
        self.elevator_load = 0
        self.elevator_door = "closed"
        self.elevator_moving = False
        
        # 自動運転制御
        self.control_active = False
        self.mission_queue = []  # 運転ミッション
        self.current_mission = None
        self.last_status_time = 0

    def initialize(self):
        """初期化"""
        logger.info("🤖 SEC-3000H ハンドシェイク型自動運転装置 起動中...")
        logger.info(f"📡 シリアルポート: {SERIAL_CONFIG['port']}")
        logger.info(f"🏷️ 局番号: {self.station_id} (自動運転装置側)")
        logger.info(f"🎯 通信相手: {self.elevator_station} (エレベーター側)")

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
                        # 状態要求を送信
                        time.sleep(0.5)
                        self._send_command(Commands.STATUS_REQ, 0x0000)

            elif cmd_code == Commands.PONG:
                # PONG受信
                logger.info("🏓 PONG受信")

            elif cmd_code == Commands.STATUS_RSP:
                # 状態応答受信
                floor = (data_value >> 8) & 0xFF
                load = data_value & 0xFF
                logger.info(f"📊 状態受信: {floor}F, 荷重{load}kg")
                
                with self.lock:
                    self.elevator_floor = floor
                    self.elevator_load = load
                    self.last_status_time = time.time()
                    
                    if self.comm_state == CommState.HANDSHAKING:
                        self.comm_state = CommState.CONNECTED
                        logger.info("✅ 通信確立完了")
                        # 制御要求を送信
                        time.sleep(0.5)
                        self._send_command(Commands.CONTROL_REQ, 0x0000)

            elif cmd_code == Commands.CONTROL_ACK:
                # 制御確認受信
                logger.info("🎮 制御確認受信")
                with self.lock:
                    self.comm_state = CommState.CONTROL_MODE
                    self.control_active = True
                    logger.info("🚀 自動運転制御開始")
                    # デモミッション追加
                    self._add_demo_missions()

        except Exception as e:
            logger.error(f"❌ メッセージ処理エラー: {e}")

    def _add_demo_missions(self):
        """デモミッション追加"""
        demo_missions = [
            {"type": "floor", "target": 3, "description": "3Fへ移動"},
            {"type": "door", "action": "open", "description": "扉開放"},
            {"type": "wait", "duration": 3, "description": "3秒待機"},
            {"type": "door", "action": "close", "description": "扉閉鎖"},
            {"type": "floor", "target": 1, "description": "1Fへ移動"},
            {"type": "door", "action": "open", "description": "扉開放"},
            {"type": "wait", "duration": 2, "description": "2秒待機"},
            {"type": "door", "action": "close", "description": "扉閉鎖"},
        ]
        
        with self.lock:
            self.mission_queue.extend(demo_missions)
            logger.info(f"📋 デモミッション追加: {len(demo_missions)}件")

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
            message.extend(self.elevator_station.encode('ascii'))  # 送信先
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
        logger.info("  1. PING受信 → PONG送信（疎通確認）")
        logger.info("  2. 状態要求 → 状態受信（接続確立）")
        logger.info("  3. 制御要求 → 制御開始（自動運転）")
        
        # 自動運転管理スレッド開始
        threading.Thread(target=self._auto_pilot_manager, daemon=True).start()

    def _auto_pilot_manager(self):
        """自動運転管理"""
        while self.running:
            try:
                with self.lock:
                    state = self.comm_state
                    active = self.control_active
                
                if state == CommState.CONTROL_MODE and active:
                    # ミッション実行
                    self._execute_missions()
                
                time.sleep(1)
                
            except Exception as e:
                logger.error(f"❌ 自動運転管理エラー: {e}")

    def _execute_missions(self):
        """ミッション実行"""
        with self.lock:
            if self.current_mission is None and self.mission_queue:
                # 次のミッション開始
                self.current_mission = self.mission_queue.pop(0)
                mission = self.current_mission
                
                logger.info(f"🎯 ミッション開始: {mission['description']}")
                
                if mission["type"] == "floor":
                    # 階数指令
                    target = mission["target"]
                    self._send_command(Commands.FLOOR_CMD, target)
                    mission["start_time"] = time.time()
                    
                elif mission["type"] == "door":
                    # 扉制御
                    action = mission["action"]
                    cmd_value = 0x0001 if action == "open" else 0x0002
                    self._send_command(Commands.DOOR_CMD, cmd_value)
                    mission["start_time"] = time.time()
                    
                elif mission["type"] == "wait":
                    # 待機
                    mission["start_time"] = time.time()
            
            elif self.current_mission is not None:
                # 現在のミッション進行チェック
                mission = self.current_mission
                elapsed = time.time() - mission["start_time"]
                
                if mission["type"] == "floor":
                    # 移動完了チェック（5秒タイムアウト）
                    if elapsed > 5.0:
                        logger.info(f"✅ ミッション完了: {mission['description']}")
                        self.current_mission = None
                        
                elif mission["type"] == "door":
                    # 扉動作完了チェック（2秒タイムアウト）
                    if elapsed > 2.0:
                        logger.info(f"✅ ミッション完了: {mission['description']}")
                        self.current_mission = None
                        
                elif mission["type"] == "wait":
                    # 待機時間チェック
                    if elapsed >= mission["duration"]:
                        logger.info(f"✅ ミッション完了: {mission['description']}")
                        self.current_mission = None

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
            control_status = "有効" if self.control_active else "無効"
            mission_count = len(self.mission_queue)
            current_desc = self.current_mission["description"] if self.current_mission else "-"

        logger.info(f"\n[{timestamp}] 🤖 自動運転装置状態")
        logger.info(f"通信状態: {state_name}")
        logger.info(f"制御状態: {control_status}")
        logger.info(f"エレベーター階: {self.elevator_floor}F")
        logger.info(f"エレベーター荷重: {self.elevator_load}kg")
        logger.info(f"現在ミッション: {current_desc}")
        logger.info(f"待機ミッション: {mission_count}件")

    def start_status_display(self):
        """定期状態表示開始"""
        def _status_timer():
            if self.running:
                self._display_status()
                threading.Timer(10.0, _status_timer).start()

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
    if 'autopilot' in globals():
        autopilot.shutdown()
    sys.exit(0)

def main():
    """メイン処理"""
    import argparse
    
    parser = argparse.ArgumentParser(description='SEC-3000H ハンドシェイク型自動運転装置')
    parser.add_argument('--port', default=SERIAL_PORT, help='シリアルポート')
    args = parser.parse_args()
    
    # シグナルハンドラー設定
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # シリアルポート設定を更新
    SERIAL_CONFIG['port'] = args.port
    
    # システム初期化
    global autopilot
    autopilot = AutoPilotHandshake()
    
    try:
        if not autopilot.initialize():
            sys.exit(1)
        
        # 通信開始
        autopilot.start_communication()
        
        # 定期状態表示開始
        autopilot.start_status_display()
        
        logger.info("\n✅ ハンドシェイク型自動運転装置稼働中 (Ctrl+C で終了)")
        
        # メインループ
        while autopilot.running:
            time.sleep(1)

    except KeyboardInterrupt:
        logger.info("\n🛑 Ctrl+C で終了")
    except Exception as e:
        logger.error(f"❌ システムエラー: {e}")
    finally:
        autopilot.shutdown()

if __name__ == "__main__":
    main()
