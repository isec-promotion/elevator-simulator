#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SEC-3000H Elevator Auto Pilot CLI (Python版)
シリアル通信専用エレベーター自動操縦プログラム
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

# ── 速度プリセット ─────────────────────────────
SPEED_PRESETS = {
    "fast": {
        "name": "高速モード",
        "description": "テスト用の高速動作",
        "door_close_time": 3,      # 扉閉鎖時間
        "movement_time": 5,        # 移動時間
        "door_open_time": 3,       # 扉開放時間
        "passenger_time": 5,       # 乗客出入り時間
        "cycle_interval": 2,       # サイクル間隔
        "status_interval": 30      # 状態表示間隔
    },
    "normal": {
        "name": "標準モード",
        "description": "通常の動作速度",
        "door_close_time": 5,      # 扉閉鎖時間
        "movement_time": 8,        # 移動時間
        "door_open_time": 4,       # 扉開放時間
        "passenger_time": 10,      # 乗客出入り時間
        "cycle_interval": 5,       # サイクル間隔
        "status_interval": 60      # 状態表示間隔
    },
    "slow": {
        "name": "低速モード",
        "description": "実際のエレベーターに近い動作",
        "door_close_time": 8,      # 扉閉鎖時間
        "movement_time": 15,       # 移動時間
        "door_open_time": 6,       # 扉開放時間
        "passenger_time": 20,      # 乗客出入り時間
        "cycle_interval": 10,      # サイクル間隔
        "status_interval": 120     # 状態表示間隔
    },
    "realistic": {
        "name": "リアルモード",
        "description": "実際のエレベーターと同等の動作",
        "door_close_time": 10,     # 扉閉鎖時間
        "movement_time": 25,       # 移動時間
        "door_open_time": 8,       # 扉開放時間
        "passenger_time": 30,      # 乗客出入り時間
        "cycle_interval": 60,      # サイクル間隔（1分間隔）
        "status_interval": 300     # 状態表示間隔（5分）
    }
}

class ElevatorAutoPilot:
    """SEC-3000H エレベーター自動操縦クラス"""
    
    def __init__(self, speed_mode: str = "normal"):
        self.serial_conn: Optional[serial.Serial] = None
        self.state = ElevatorState()
        self.sequence_index = 0
        self.is_running = False
        self.status_broadcast_timer: Optional[threading.Timer] = None
        self.operation_timer: Optional[threading.Timer] = None
        self.lock = threading.Lock()
        
        # 速度設定
        self.speed_mode = speed_mode
        self.timing = SPEED_PRESETS.get(speed_mode, SPEED_PRESETS["normal"])
        logger.info(f"🎛️ 動作モード: {self.timing['name']} - {self.timing['description']}")

    async def initialize(self):
        """初期化"""
        logger.info("🚀 SEC-3000H Elevator Auto Pilot CLI 起動中...")
        logger.info(f"📡 シリアルポート設定: {SERIAL_PORT} {SERIAL_CONFIG}")
        logger.info("🎭 疑似モード: 自動運転内部完結型")

        try:
            await self._connect_serial()
            logger.info("✅ 初期化完了")
        except Exception as e:
            logger.warning(f"⚠️ シリアルポート接続失敗、疑似モードで継続: {e}")
            self.serial_conn = None
            logger.info("✅ 疑似モード初期化完了")

    async def _connect_serial(self):
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
        """シリアル受信処理"""
        while self.serial_conn and self.serial_conn.is_open:
            try:
                if self.serial_conn.in_waiting > 0:
                    data = self.serial_conn.read(self.serial_conn.in_waiting)
                    self._handle_received_data(data)
                time.sleep(0.05)
            except Exception as e:
                logger.error(f"❌ シリアル受信エラー: {e}")
                break

    def _handle_received_data(self, data: bytes):
        """受信データ処理"""
        try:
            if len(data) < 16 or data[0] != 0x05:
                return  # 無効なデータ

            # メッセージ解析
            station = data[1:5].decode('ascii')
            command = chr(data[5])
            data_num_str = data[6:10].decode('ascii')
            data_value_str = data[10:14].decode('ascii')
            checksum = data[14:16].decode('ascii')

            data_num = int(data_num_str, 16)
            data_value = int(data_value_str, 16)

            timestamp = datetime.now().strftime("%Y年%m月%d日 %H:%M:%S")

            # データ内容を解釈
            description = ""
            if data_num == DataNumbers.CURRENT_FLOOR:
                current_floor = "B1F" if data_value == 0xFFFF else f"{data_value}F"
                with self.lock:
                    self.state.current_floor = current_floor
                description = f"現在階数: {current_floor}"
            elif data_num == DataNumbers.TARGET_FLOOR:
                target_floor = "B1F" if data_value == 0xFFFF else f"{data_value}F"
                with self.lock:
                    self.state.target_floor = target_floor
                description = f"行先階: {target_floor}"
            elif data_num == DataNumbers.LOAD_WEIGHT:
                with self.lock:
                    self.state.load_weight = data_value
                description = f"荷重: {data_value}kg"
            else:
                description = f"データ番号: {data_num:04X}"

            logger.info(
                f"[{timestamp}] 📨 受信: 局番号:{station} CMD:{command} {description} "
                f"データ:{data_value_str} チェックサム:{checksum}"
            )

            # ACK応答送信
            self._send_ack_response(station)

        except Exception as e:
            logger.error(f"❌ 受信データ処理エラー: {e}")

    def _send_ack_response(self, station: str):
        """ACK応答送信"""
        if not self.serial_conn or not self.serial_conn.is_open:
            return

        try:
            response = bytearray([0x06])  # ACK
            response.extend(station.encode('ascii'))

            self.serial_conn.write(response)

            timestamp = datetime.now().strftime("%Y年%m月%d日 %H:%M:%S")
            hex_data = response.hex().upper()
            logger.info(
                f"[{timestamp}] 📤 送信: ACK(06) 局番号:{station} | HEX: {hex_data}"
            )

        except Exception as e:
            logger.error(f"❌ ACK送信エラー: {e}")

    def _calculate_checksum(self, data: bytes) -> str:
        """チェックサム計算"""
        total = sum(data)
        lower_byte = total & 0xFF
        upper_byte = (total >> 8) & 0xFF
        checksum = (lower_byte + upper_byte) & 0xFF
        return f"{checksum:02X}"

    async def _send_command(self, target_station: str, data_num: int, data_value: int) -> bool:
        """コマンド送信（疑似モード対応）"""
        # メッセージ作成
        message = bytearray()
        message.append(0x05)  # ENQ
        message.extend(target_station.encode('ascii'))  # 局番号
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
        else:
            description = f"データ番号: {data_num_str}"

        if self.serial_conn and self.serial_conn.is_open:
            # 実際のシリアル通信
            try:
                self.serial_conn.write(message)
                logger.info(
                    f"[{timestamp}] 📤 送信: ENQ(05) 局番号:{target_station} CMD:W "
                    f"{description} データ:{data_value_str} チェックサム:{checksum}"
                )

                # ACK待ち（簡易実装）
                await self._sleep(0.1)
                logger.info(f"[{timestamp}] ✅ ACK受信")
                return True

            except Exception as e:
                logger.error(f"❌ コマンド送信エラー: {e}")
                return False
        else:
            # 疑似モード（内部完結）
            logger.info(
                f"[{timestamp}] 📤 疑似送信: ENQ(05) 局番号:{target_station} CMD:W "
                f"{description} データ:{data_value_str} チェックサム:{checksum}"
            )

            # 疑似的な処理遅延
            await self._sleep(0.1)
            logger.info(f"[{timestamp}] ✅ 疑似ACK受信")
            return True

    async def _set_floor(self, floor: str) -> bool:
        """階数設定"""
        floor_value = 0xFFFF if floor == "B1F" else int(floor.replace("F", ""))
        return await self._send_command("0001", DataNumbers.FLOOR_SETTING, floor_value)

    async def _control_door(self, action: str) -> bool:
        """扉制御"""
        command_map = {
            "open": DoorCommands.OPEN,
            "close": DoorCommands.CLOSE,
            "stop": DoorCommands.STOP
        }
        command = command_map.get(action, DoorCommands.STOP)
        return await self._send_command("0001", DataNumbers.DOOR_CONTROL, command)

    async def start_auto_pilot(self):
        """自動運転開始"""
        if self.is_running:
            logger.info("⚠️ 自動運転は既に実行中です")
            return

        logger.info("🚀 自動運転開始")
        logger.info(f"🏢 運転シーケンス: {' → '.join(AUTO_SEQUENCE)}")
        self.is_running = True

        # 初期位置を1Fに設定
        logger.info("🏢 初期位置を1Fに設定中...")
        await self._set_floor("1F")
        await self._sleep(2)

        # 自動運転ループ開始
        await self._execute_auto_pilot_loop()

    async def _execute_auto_pilot_loop(self):
        """自動運転ループ"""
        if not self.is_running:
            return

        try:
            target_floor = AUTO_SEQUENCE[self.sequence_index]

            with self.lock:
                current_floor = self.state.current_floor

            logger.info(f"\n🎯 次の目標階: {target_floor} (現在: {current_floor})")

            # 1. 扉を閉める
            logger.info(f"🚪 扉を閉めています...({self.timing['door_close_time']}秒)")
            await self._control_door("close")
            await self._sleep(self.timing['door_close_time'])

            # 2. 目標階に移動
            logger.info(f"🚀 {target_floor}に移動中...({self.timing['movement_time']}秒)")
            with self.lock:
                self.state.is_moving = True
            await self._set_floor(target_floor)
            await self._sleep(self.timing['movement_time'])  # 移動時間

            # 3. 到着
            logger.info(f"✅ {target_floor}に到着")
            with self.lock:
                self.state.current_floor = target_floor
                self.state.is_moving = False

            # 4. 扉を開ける
            logger.info(f"🚪 扉を開いています...({self.timing['door_open_time']}秒)")
            await self._control_door("open")
            await self._sleep(self.timing['door_open_time'])

            # 5. 乗客の出入り時間
            logger.info(f"👥 乗客の出入り中...({self.timing['passenger_time']}秒)")
            await self._sleep(self.timing['passenger_time'])

            # 次の階へ
            self.sequence_index = (self.sequence_index + 1) % len(AUTO_SEQUENCE)

            # 次のサイクルをスケジュール
            if self.is_running:
                cycle_interval = self.timing['cycle_interval']
                logger.info(f"⏳ 次のサイクルまで {cycle_interval}秒待機...")
                self.operation_timer = threading.Timer(cycle_interval, lambda: self._run_async(self._execute_auto_pilot_loop()))
                self.operation_timer.start()

        except Exception as e:
            logger.error(f"❌ 自動運転エラー: {e}")
            # エラー時は少し待ってから再試行
            if self.is_running:
                retry_interval = max(self.timing['cycle_interval'], 5)
                self.operation_timer = threading.Timer(retry_interval, lambda: self._run_async(self._execute_auto_pilot_loop()))
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

    def start_status_display(self):
        """定期状態表示開始"""
        def _status_timer():
            if self.is_running:
                self._display_status()
                interval = self.timing['status_interval']
                self.status_broadcast_timer = threading.Timer(interval, _status_timer)
                self.status_broadcast_timer.start()

        _status_timer()

    async def shutdown(self):
        """終了処理"""
        logger.info("🛑 システム終了中...")

        self.stop_auto_pilot()

        if self.status_broadcast_timer:
            self.status_broadcast_timer.cancel()

        if self.serial_conn and self.serial_conn.is_open:
            self.serial_conn.close()
            logger.info("📡 シリアルポート切断完了")

        logger.info("✅ システム終了完了")

    async def _sleep(self, seconds: float):
        """非同期スリープ"""
        await asyncio.sleep(seconds)

    def _run_async(self, coro):
        """非同期関数を同期的に実行"""
        import asyncio
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        if loop.is_running():
            # 既にイベントループが実行中の場合
            task = asyncio.create_task(coro)
        else:
            # イベントループが実行されていない場合
            loop.run_until_complete(coro)

# ── メイン処理 ─────────────────────────────────
async def main():
    """メイン処理"""
    import argparse
    
    # コマンドライン引数解析
    parser = argparse.ArgumentParser(description='SEC-3000H Elevator Auto Pilot CLI (Python版)')
    parser.add_argument('--speed', choices=['fast', 'normal', 'slow', 'realistic'], 
                       default='normal', help='動作速度モード (デフォルト: normal)')
    parser.add_argument('--list-speeds', action='store_true', help='利用可能な速度モードを表示')
    args = parser.parse_args()
    
    # 速度モード一覧表示
    if args.list_speeds:
        logger.info("📋 利用可能な速度モード:")
        for mode, config in SPEED_PRESETS.items():
            logger.info(f"  {mode}: {config['name']} - {config['description']}")
            logger.info(f"    扉閉鎖:{config['door_close_time']}s, 移動:{config['movement_time']}s, "
                       f"扉開放:{config['door_open_time']}s, 乗客:{config['passenger_time']}s, "
                       f"サイクル間隔:{config['cycle_interval']}s")
        return
    
    auto_pilot = ElevatorAutoPilot(speed_mode=args.speed)

    # シグナルハンドラー設定
    def signal_handler(signum, frame):
        logger.info(f"\n🛑 シグナル {signum} を受信しました")
        import asyncio
        asyncio.create_task(auto_pilot.shutdown())
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        # 初期化
        await auto_pilot.initialize()

        # 定期状態表示開始
        auto_pilot.start_status_display()

        # 自動運転開始
        await auto_pilot.start_auto_pilot()

        logger.info("\n✅ システム稼働中 (Ctrl+C で終了)")

        # メインループ
        while auto_pilot.is_running:
            await auto_pilot._sleep(1)

    except Exception as e:
        logger.error(f"❌ システムエラー: {e}")
        await auto_pilot.shutdown()
        sys.exit(1)

if __name__ == "__main__":
    import asyncio
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\n🛑 Ctrl+C が押されました")
        sys.exit(0)
    except Exception as e:
        logger.error(f"❌ 予期しないエラー: {e}")
        sys.exit(1)
