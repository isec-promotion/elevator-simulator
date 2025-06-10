#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SEC-3000H Elevator Auto Pilot - USB Direct Connection
PCとRaspberry Pi 4をUSBケーブルで直接接続して通信
"""

import serial
import time
import logging
import threading
import signal
import sys
import json
from datetime import datetime
from typing import Optional, Dict, Any
from enum import IntEnum

# ── 設定 ───────────────────────────────────
# USB接続設定（Raspberry Pi 4との直接通信）
USB_PORTS = [
    "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9", "COM10",  # Windows
    "/dev/ttyACM0", "/dev/ttyACM1", "/dev/ttyUSB0", "/dev/ttyUSB1"    # Linux
]

USB_CONFIG = {
    'baudrate': 115200,  # USB通信は高速
    'bytesize': serial.EIGHTBITS,
    'parity': serial.PARITY_NONE,
    'stopbits': serial.STOPBITS_ONE,
    'timeout': 1
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
    FLOOR_SETTING = 0x0010  # 階数設定
    DOOR_CONTROL = 0x0011   # 扉制御

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
        self.is_moving = False
        self.door_status = "unknown"

# ── 自動運転シーケンス ─────────────────────────
AUTO_SEQUENCE = ["B1F", "1F", "2F", "3F", "4F", "5F"]

class ElevatorUSBPilot:
    """USB直接接続エレベーター自動操縦クラス"""
    
    def __init__(self):
        self.usb_conn: Optional[serial.Serial] = None
        self.state = ElevatorState()
        self.sequence_index = 0
        self.is_running = False
        self.status_broadcast_timer: Optional[threading.Timer] = None
        self.operation_timer: Optional[threading.Timer] = None
        self.lock = threading.Lock()
        self.connected_port = None

    def find_raspberry_pi(self) -> Optional[str]:
        """Raspberry Pi 4を自動検出"""
        logger.info("🔍 Raspberry Pi 4を検索中...")
        
        for port in USB_PORTS:
            try:
                test_conn = serial.Serial(port, **USB_CONFIG)
                
                # 識別メッセージを送信
                test_message = {
                    "type": "identify",
                    "timestamp": datetime.now().isoformat()
                }
                test_conn.write((json.dumps(test_message) + '\n').encode('utf-8'))
                
                # 応答を待機
                time.sleep(0.5)
                if test_conn.in_waiting > 0:
                    response = test_conn.readline().decode('utf-8').strip()
                    try:
                        response_data = json.loads(response)
                        if response_data.get("device") == "raspberry_pi_elevator":
                            logger.info(f"✅ Raspberry Pi 4を発見: {port}")
                            test_conn.close()
                            return port
                    except json.JSONDecodeError:
                        pass
                
                test_conn.close()
                
            except Exception as e:
                continue
        
        logger.error("❌ Raspberry Pi 4が見つかりません")
        return None

    def connect_usb(self) -> bool:
        """USB接続"""
        try:
            # Raspberry Pi 4を自動検出
            port = self.find_raspberry_pi()
            if not port:
                return False
            
            # USB接続
            self.usb_conn = serial.Serial(port, **USB_CONFIG)
            self.connected_port = port
            
            logger.info(f"✅ USB接続成功: {port}")
            logger.info(f"📡 通信設定: {USB_CONFIG['baudrate']}bps, USB直接通信")
            
            # 受信スレッド開始
            threading.Thread(target=self._listen_usb, daemon=True).start()
            
            return True
            
        except Exception as e:
            logger.error(f"❌ USB接続エラー: {e}")
            return False

    def _listen_usb(self):
        """USB受信処理"""
        while self.usb_conn and self.usb_conn.is_open:
            try:
                if self.usb_conn.in_waiting > 0:
                    line = self.usb_conn.readline().decode('utf-8').strip()
                    if line:
                        self._handle_usb_message(line)
                time.sleep(0.05)
            except Exception as e:
                logger.error(f"❌ USB受信エラー: {e}")
                break

    def _handle_usb_message(self, message: str):
        """USB受信メッセージ処理"""
        try:
            data = json.loads(message)
            msg_type = data.get("type")
            
            if msg_type == "status_update":
                # Raspberry Pi 4からの状態更新
                with self.lock:
                    if "current_floor" in data:
                        self.state.current_floor = data["current_floor"]
                    if "target_floor" in data:
                        self.state.target_floor = data["target_floor"]
                    if "load_weight" in data:
                        self.state.load_weight = data["load_weight"]
                    if "is_moving" in data:
                        self.state.is_moving = data["is_moving"]
                
                logger.info(f"📊 状態更新: 現在階={self.state.current_floor}, 行先階={self.state.target_floor}")
                
            elif msg_type == "ack":
                logger.info(f"✅ ACK受信: {data.get('command', 'unknown')}")
                
            elif msg_type == "error":
                logger.error(f"❌ エラー受信: {data.get('message', 'unknown error')}")
                
        except json.JSONDecodeError as e:
            logger.warning(f"⚠️ 無効なJSONメッセージ: {message}")

    def send_usb_command(self, command_type: str, **kwargs) -> bool:
        """USBコマンド送信"""
        if not self.usb_conn or not self.usb_conn.is_open:
            logger.error("❌ USB接続が確立されていません")
            return False
        
        try:
            message = {
                "type": command_type,
                "timestamp": datetime.now().isoformat(),
                **kwargs
            }
            
            json_message = json.dumps(message) + '\n'
            self.usb_conn.write(json_message.encode('utf-8'))
            
            logger.info(f"📤 USB送信: {command_type} - {kwargs}")
            return True
            
        except Exception as e:
            logger.error(f"❌ USB送信エラー: {e}")
            return False

    def set_floor(self, floor: str) -> bool:
        """階数設定"""
        return self.send_usb_command("set_floor", floor=floor)

    def control_door(self, action: str) -> bool:
        """扉制御"""
        return self.send_usb_command("door_control", action=action)

    def start_auto_pilot(self):
        """自動運転開始"""
        if self.is_running:
            logger.info("⚠️ 自動運転は既に実行中です")
            return

        logger.info("🚀 USB直接通信自動運転開始")
        logger.info(f"🏢 運転シーケンス: {' → '.join(AUTO_SEQUENCE)}")
        self.is_running = True

        # 初期位置を1Fに設定
        logger.info("🏢 初期位置を1Fに設定中...")
        self.set_floor("1F")
        time.sleep(2)

        # 自動運転ループ開始
        self._execute_auto_pilot_loop()

    def _execute_auto_pilot_loop(self):
        """自動運転ループ"""
        if not self.is_running:
            return

        try:
            target_floor = AUTO_SEQUENCE[self.sequence_index]

            with self.lock:
                current_floor = self.state.current_floor

            logger.info(f"\n🎯 次の目標階: {target_floor} (現在: {current_floor})")

            # 1. 扉を閉める
            logger.info("🚪 扉を閉めています...")
            self.control_door("close")
            time.sleep(3)

            # 2. 目標階に移動
            logger.info(f"🚀 {target_floor}に移動中...")
            with self.lock:
                self.state.is_moving = True
            self.set_floor(target_floor)
            time.sleep(5)  # 移動時間

            # 3. 到着
            logger.info(f"✅ {target_floor}に到着")
            with self.lock:
                self.state.current_floor = target_floor
                self.state.is_moving = False

            # 4. 扉を開ける
            logger.info("🚪 扉を開いています...")
            self.control_door("open")
            time.sleep(3)

            # 5. 乗客の出入り時間
            logger.info("👥 乗客の出入り中...")
            time.sleep(5)

            # 次の階へ
            self.sequence_index = (self.sequence_index + 1) % len(AUTO_SEQUENCE)

            # 次のサイクルをスケジュール
            if self.is_running:
                self.operation_timer = threading.Timer(2.0, self._execute_auto_pilot_loop)
                self.operation_timer.start()

        except Exception as e:
            logger.error(f"❌ 自動運転エラー: {e}")
            # エラー時は少し待ってから再試行
            if self.is_running:
                self.operation_timer = threading.Timer(5.0, self._execute_auto_pilot_loop)
                self.operation_timer.start()

    def stop_auto_pilot(self):
        """自動運転停止"""
        logger.info("🛑 自動運転停止")
        self.is_running = False

        if self.operation_timer:
            self.operation_timer.cancel()
            self.operation_timer = None

    def _display_status(self):
        """状態表示"""
        timestamp = datetime.now().strftime("%Y年%m月%d日 %H:%M:%S")

        with self.lock:
            current_floor = self.state.current_floor
            target_floor = self.state.target_floor or "-"
            load_weight = self.state.load_weight
            is_moving = "はい" if self.state.is_moving else "いいえ"
            door_status = self.state.door_status

        logger.info(f"\n[{timestamp}] 📊 エレベーター状態")
        logger.info(f"現在階: {current_floor}")
        logger.info(f"行先階: {target_floor}")
        logger.info(f"荷重: {load_weight}kg")
        logger.info(f"移動中: {is_moving}")
        logger.info(f"扉状態: {door_status}")
        logger.info(f"USB接続: {self.connected_port}")

    def start_status_display(self):
        """定期状態表示開始"""
        def _status_timer():
            if self.is_running:
                self._display_status()
                self.status_broadcast_timer = threading.Timer(30.0, _status_timer)
                self.status_broadcast_timer.start()

        _status_timer()

    def disconnect_usb(self):
        """USB切断"""
        if self.usb_conn and self.usb_conn.is_open:
            self.usb_conn.close()
            logger.info("📡 USB接続を切断しました")

    def shutdown(self):
        """終了処理"""
        logger.info("🛑 システム終了中...")

        self.stop_auto_pilot()

        if self.status_broadcast_timer:
            self.status_broadcast_timer.cancel()

        self.disconnect_usb()
        logger.info("✅ システム終了完了")

# ── メイン処理 ─────────────────────────────────
def signal_handler(signum, frame):
    """シグナルハンドラー"""
    logger.info(f"\n🛑 シグナル {signum} を受信しました")
    if 'pilot' in globals():
        pilot.shutdown()
    sys.exit(0)

def main():
    """メイン処理"""
    import argparse
    
    # コマンドライン引数解析
    parser = argparse.ArgumentParser(description='SEC-3000H Elevator Auto Pilot - USB Direct Connection')
    parser.add_argument('--manual', action='store_true', help='手動モード（自動運転しない）')
    args = parser.parse_args()
    
    # シグナルハンドラー設定
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    logger.info("🚀 SEC-3000H Elevator Auto Pilot - USB Direct Connection")
    logger.info("📱 PCとRaspberry Pi 4のUSB直接通信版")
    logger.info("=" * 60)
    
    # USB操縦システム初期化
    global pilot
    pilot = ElevatorUSBPilot()
    
    try:
        # USB接続
        if not pilot.connect_usb():
            logger.error("❌ Raspberry Pi 4との接続に失敗しました")
            sys.exit(1)
        
        if not args.manual:
            # 定期状態表示開始
            pilot.start_status_display()
            
            # 自動運転開始
            pilot.start_auto_pilot()
            
            logger.info("\n✅ 自動運転システム稼働中 (Ctrl+C で終了)")
        else:
            logger.info("\n✅ 手動モードで待機中 (Ctrl+C で終了)")
        
        # メインループ
        while True:
            time.sleep(1)

    except Exception as e:
        logger.error(f"❌ システムエラー: {e}")
        pilot.shutdown()
        sys.exit(1)

if __name__ == "__main__":
    main()
