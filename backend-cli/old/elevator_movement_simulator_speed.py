#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
エレベーター移動シミュレーター（SEC-3000H仕様準拠・移動特化版・速度オプション付き）
COM27にSEC-3000H仕様準拠のENQ/ACK信号を送信
エレベーターの移動にのみフォーカス（扉制御なし）
速度オプション：1=高速, 2=ゆっくり, 3=現実的
"""

import serial
import time
import threading
import logging
import signal
import sys
from datetime import datetime
from typing import Optional
from enum import IntEnum
import random

# ── 設定 ───────────────────────────────────
SERIAL_PORT = "COM27"
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
    FLOOR_SETTING = 0x0010  # 階数設定

class ElevatorSimulator:
    """エレベーター移動シミュレーター（SEC-3000H仕様準拠・移動特化版・速度オプション付き）"""
    
    def __init__(self, speed_mode: int = 1):
        self.serial_conn: Optional[serial.Serial] = None
        self.running = False
        self.speed_mode = speed_mode  # 1:高速, 2:ゆっくり, 3:現実的
        
        # エレベーター状態
        self.current_floor = 1  # 現在階（1F）
        self.target_floor = None  # 行先階
        self.load_weight = 0  # 荷重
        self.is_moving = False
        
        # SEC-3000H仕様：停止タイマー
        self.stop_timer_active = False
        
        # 通信設定
        self.elevator_station = "0002"  # エレベーター局番号
        self.autopilot_station = "0001"  # 自動運転装置局番号
        
        # 送信データシーケンス
        self.data_sequence = [
            DataNumbers.CURRENT_FLOOR,
            DataNumbers.TARGET_FLOOR,
            DataNumbers.LOAD_WEIGHT
        ]
        self.current_data_index = 0
        
        # 速度設定に基づく移動シナリオ
        self.scenarios = self._create_scenarios_by_speed()
        self.current_scenario = 0
        
        # 通信間隔設定
        self.communication_intervals = self._get_communication_intervals()

    def _create_scenarios_by_speed(self):
        """速度モードに基づく移動シナリオ作成"""
        base_scenarios = [
            {"from": 1, "to": 3, "floors": 2},   # 1F → 3F (2階分)
            {"from": 3, "to": -1, "floors": 4},  # 3F → B1F (4階分)
            {"from": -1, "to": 5, "floors": 6},  # B1F → 5F (6階分)
            {"from": 5, "to": 1, "floors": 4},   # 5F → 1F (4階分)
            {"from": 1, "to": 2, "floors": 1},   # 1F → 2F (1階分)
            {"from": 2, "to": 4, "floors": 2},   # 2F → 4F (2階分)
        ]
        
        # 速度モード別の移動時間計算
        if self.speed_mode == 1:  # 高速（現在の速度）
            # 1階あたり2.5秒 + 基本時間3秒
            scenarios = []
            for scenario in base_scenarios:
                duration = 3 + (scenario["floors"] * 2.5)
                scenarios.append({
                    "from": scenario["from"],
                    "to": scenario["to"],
                    "duration": int(duration)
                })
        elif self.speed_mode == 2:  # ゆっくり
            # 1階あたり5秒 + 基本時間5秒
            scenarios = []
            for scenario in base_scenarios:
                duration = 5 + (scenario["floors"] * 5)
                scenarios.append({
                    "from": scenario["from"],
                    "to": scenario["to"],
                    "duration": int(duration)
                })
        else:  # 現実的（速度モード3）
            # 1階あたり8秒 + 基本時間10秒（加減速含む）
            scenarios = []
            for scenario in base_scenarios:
                duration = 10 + (scenario["floors"] * 8)
                scenarios.append({
                    "from": scenario["from"],
                    "to": scenario["to"],
                    "duration": int(duration)
                })
        
        return scenarios

    def _get_communication_intervals(self):
        """速度モードに基づく通信間隔設定"""
        if self.speed_mode == 1:  # 高速
            return {
                "data_transmission": 2.0,    # エレベーターデータ送信間隔
                "command_transmission": 10.0, # 自動運転装置コマンド送信間隔
                "status_display": 15.0,      # 状態表示間隔
                "stop_timer": 3.0,           # 停止タイマー
                "next_movement_delay": 5.0   # 次の移動開始までの遅延
            }
        elif self.speed_mode == 2:  # ゆっくり
            return {
                "data_transmission": 5.0,    # エレベーターデータ送信間隔
                "command_transmission": 20.0, # 自動運転装置コマンド送信間隔
                "status_display": 30.0,      # 状態表示間隔
                "stop_timer": 8.0,           # 停止タイマー
                "next_movement_delay": 15.0  # 次の移動開始までの遅延
            }
        else:  # 現実的（速度モード3）
            return {
                "data_transmission": 10.0,   # エレベーターデータ送信間隔
                "command_transmission": 30.0, # 自動運転装置コマンド送信間隔
                "status_display": 60.0,      # 状態表示間隔
                "stop_timer": 15.0,          # 停止タイマー（扉開閉時間含む）
                "next_movement_delay": 30.0  # 次の移動開始までの遅延
            }

    def initialize(self):
        """初期化"""
        speed_names = {1: "高速", 2: "ゆっくり", 3: "現実的"}
        logger.info("🏢 エレベーター移動シミュレーター起動（SEC-3000H仕様準拠・移動特化版・速度オプション付き）")
        logger.info(f"📡 シリアルポート: {SERIAL_PORT}")
        logger.info(f"⚡ 速度モード: {self.speed_mode} ({speed_names.get(self.speed_mode, '不明')})")
        logger.info(f"🏷️ エレベーター局番号: {self.elevator_station}")
        logger.info(f"🎯 自動運転装置局番号: {self.autopilot_station}")
        logger.info("📋 SEC-3000H仕様：着床後停止タイマーUP後に行先階データ0設定")
        logger.info("🚀 移動特化版：扉制御なし、移動のみに集中")
        
        # 速度モード別の詳細情報
        intervals = self.communication_intervals
        logger.info(f"⏱️ 通信間隔設定:")
        logger.info(f"   - データ送信間隔: {intervals['data_transmission']}秒")
        logger.info(f"   - コマンド送信間隔: {intervals['command_transmission']}秒")
        logger.info(f"   - 停止タイマー: {intervals['stop_timer']}秒")
        
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
            logger.info(f"✅ シリアルポート {SERIAL_PORT} 接続成功")
        except Exception as e:
            logger.error(f"❌ シリアルポートエラー: {e}")
            raise

    def _calculate_checksum(self, data: bytes) -> str:
        """チェックサム計算"""
        total = sum(data)
        checksum = total & 0xFF
        return f"{checksum:02X}"

    def _send_enq_message(self, station_from: str, station_to: str, data_num: int, data_value: int):
        """ENQメッセージ送信"""
        if not self.serial_conn or not self.serial_conn.is_open:
            return

        try:
            # ENQメッセージ作成
            message = bytearray()
            message.append(0x05)  # ENQ
            message.extend(station_to.encode('ascii'))  # 送信先局番号
            message.append(0x57)  # 'W'
            
            # データ番号 (4桁HEX ASCII)
            data_num_str = f"{data_num:04X}"
            message.extend(data_num_str.encode('ascii'))
            
            # データ値 (4桁HEX ASCII)
            data_value_str = f"{data_value:04X}"
            message.extend(data_value_str.encode('ascii'))
            
            # チェックサム計算（ENQ以外）
            checksum_data = message[1:]
            checksum = self._calculate_checksum(checksum_data)
            message.extend(checksum.encode('ascii'))
            
            # 送信
            self.serial_conn.write(message)
            
            timestamp = datetime.now().strftime("%Y年%m月%d日 %H:%M:%S")
            
            # データ内容解釈
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
            elif data_num == DataNumbers.FLOOR_SETTING:
                floor = "B1F" if data_value == 0xFFFF else f"{data_value}F"
                description = f"階数設定: {floor}"
            
            sender = "エレベーター" if station_from == self.elevator_station else "自動運転装置"
            
            logger.info(
                f"[{timestamp}] 📤 {sender}→ENQ送信: {description} "
                f"(局番号:{station_to} データ:{data_value_str} チェックサム:{checksum})"
            )
            
        except Exception as e:
            logger.error(f"❌ ENQ送信エラー: {e}")

    def _send_ack_response(self, station_id: str):
        """ACK応答送信"""
        if not self.serial_conn or not self.serial_conn.is_open:
            return

        try:
            response = bytearray([0x06])  # ACK
            response.extend(station_id.encode('ascii'))
            
            self.serial_conn.write(response)
            
            timestamp = datetime.now().strftime("%Y年%m月%d日 %H:%M:%S")
            sender = "エレベーター" if station_id == self.elevator_station else "自動運転装置"
            
            logger.info(f"[{timestamp}] 📨 {sender}→ACK応答: {response.hex().upper()}")
            
        except Exception as e:
            logger.error(f"❌ ACK送信エラー: {e}")

    def _elevator_data_transmission(self):
        """エレベーターからのデータ送信"""
        if not self.running:
            return

        try:
            # 現在のデータ番号
            data_num = self.data_sequence[self.current_data_index]
            
            # データ値決定
            if data_num == DataNumbers.CURRENT_FLOOR:
                data_value = 0xFFFF if self.current_floor == -1 else self.current_floor
            elif data_num == DataNumbers.TARGET_FLOOR:
                # SEC-3000H仕様：行先階と設定階が同一の場合、行先階は0
                if self.target_floor is None:
                    data_value = 0x0000
                elif self.current_floor == self.target_floor:
                    data_value = 0x0000  # 同一階の場合は0
                else:
                    data_value = 0xFFFF if self.target_floor == -1 else self.target_floor
            elif data_num == DataNumbers.LOAD_WEIGHT:
                # SEC-3000H仕様：荷重データは昇降中、起動直前の荷重を維持
                data_value = self.load_weight
            else:
                data_value = 0x0000

            # ENQ送信（エレベーター → 自動運転装置）
            self._send_enq_message(
                self.elevator_station, 
                self.autopilot_station, 
                data_num, 
                data_value
            )
            
            # ACK応答シミュレーション（自動運転装置 → エレベーター）
            time.sleep(0.1)
            self._send_ack_response(self.autopilot_station)
            
            # 次のデータ番号へ
            self.current_data_index = (self.current_data_index + 1) % len(self.data_sequence)
            
            # 次の送信スケジュール（速度モード対応）
            if self.running:
                interval = self.communication_intervals["data_transmission"]
                threading.Timer(interval, self._elevator_data_transmission).start()
                
        except Exception as e:
            logger.error(f"❌ エレベーターデータ送信エラー: {e}")
            if self.running:
                interval = self.communication_intervals["data_transmission"]
                threading.Timer(interval, self._elevator_data_transmission).start()

    def _autopilot_command_transmission(self):
        """自動運転装置からのコマンド送信（階数設定のみ）"""
        if not self.running:
            return

        try:
            # 移動シナリオ実行
            scenario = self.scenarios[self.current_scenario]
            
            if not self.is_moving and self.target_floor is None and not self.stop_timer_active:
                # 新しい移動開始
                self.target_floor = scenario["to"]
                self.is_moving = True
                
                # 階数設定コマンド送信（自動運転装置 → エレベーター）
                target_value = 0xFFFF if self.target_floor == -1 else self.target_floor
                self._send_enq_message(
                    self.autopilot_station,
                    self.elevator_station,
                    DataNumbers.FLOOR_SETTING,
                    target_value
                )
                
                # ACK応答シミュレーション（エレベーター → 自動運転装置）
                time.sleep(0.1)
                self._send_ack_response(self.elevator_station)
                
                # 移動完了をスケジュール
                threading.Timer(scenario["duration"], self._complete_movement).start()
                
                logger.info(f"🚀 移動開始: {self._floor_to_string(self.current_floor)} → {self._floor_to_string(self.target_floor)} (所要時間: {scenario['duration']}秒)")
            
            # 次のコマンド送信スケジュール（速度モード対応）
            if self.running:
                interval = self.communication_intervals["command_transmission"]
                threading.Timer(interval, self._autopilot_command_transmission).start()
                
        except Exception as e:
            logger.error(f"❌ 自動運転装置コマンド送信エラー: {e}")
            if self.running:
                interval = self.communication_intervals["command_transmission"]
                threading.Timer(interval, self._autopilot_command_transmission).start()

    def _complete_movement(self):
        """移動完了処理（SEC-3000H仕様準拠・移動特化版）"""
        if self.target_floor is not None:
            # 着床処理
            arrived_floor = self.target_floor
            self.current_floor = self.target_floor
            self.is_moving = False
            
            logger.info(f"🏁 着床完了: {self._floor_to_string(self.current_floor)}")
            
            # 荷重変更（乗客の乗降をシミュレート）
            old_weight = self.load_weight
            self.load_weight = random.randint(100, 1500)  # 100kg〜1500kgの範囲
            logger.info(f"🎒 乗客乗降: 荷重 {old_weight}kg → {self.load_weight}kg")
            
            # SEC-3000H仕様：停止タイマー開始（速度モード対応）
            self.stop_timer_active = True
            stop_timer_duration = self.communication_intervals["stop_timer"]
            threading.Timer(stop_timer_duration, self._stop_timer_up).start()
    
    def _stop_timer_up(self):
        """停止タイマーUP処理（SEC-3000H仕様）"""
        logger.info("⏰ 停止タイマーUP：行先階データを0に設定")
        
        # SEC-3000H仕様：着床後データ0を書き込み（停止タイマーUP後自動）
        self.target_floor = None
        self.stop_timer_active = False
        
        # 次のシナリオ準備（速度モード対応の遅延）
        self.current_scenario = (self.current_scenario + 1) % len(self.scenarios)
        logger.info("📅 次の移動準備完了")

    def _floor_to_string(self, floor: int) -> str:
        """階数を文字列に変換"""
        return "B1F" if floor == -1 else f"{floor}F"

    def _display_status(self):
        """状態表示"""
        if not self.running:
            return

        timestamp = datetime.now().strftime("%Y年%m月%d日 %H:%M:%S")
        current_str = self._floor_to_string(self.current_floor)
        target_str = self._floor_to_string(self.target_floor) if self.target_floor else "なし"
        moving_str = "移動中" if self.is_moving else "停止中"
        timer_str = "作動中" if self.stop_timer_active else "停止"
        speed_names = {1: "高速", 2: "ゆっくり", 3: "現実的"}
        
        logger.info(f"\n[{timestamp}] 🏢 エレベーター状態（移動特化版・速度モード{self.speed_mode}）")
        logger.info(f"⚡ 速度設定: {speed_names.get(self.speed_mode, '不明')}")
        logger.info(f"現在階: {current_str}")
        logger.info(f"行先階: {target_str}")
        logger.info(f"状態: {moving_str}")
        logger.info(f"荷重: {self.load_weight}kg")
        logger.info(f"停止タイマー: {timer_str}")
        logger.info(f"次のシナリオ: {self.scenarios[self.current_scenario]}")
        
        # 次の状態表示をスケジュール（速度モード対応）
        if self.running:
            interval = self.communication_intervals["status_display"]
            threading.Timer(interval, self._display_status).start()

    def start_simulation(self):
        """シミュレーション開始"""
        if self.running:
            logger.info("⚠️ シミュレーションは既に実行中です")
            return

        speed_names = {1: "高速", 2: "ゆっくり", 3: "現実的"}
        logger.info(f"🚀 エレベーター移動シミュレーション開始（SEC-3000H仕様準拠・移動特化版・速度モード{self.speed_mode}）")
        logger.info("📋 仕様準拠項目：")
        logger.info("   - 着床後停止タイマーUP後に行先階データ0設定")
        logger.info("   - 行先階と設定階が同一の場合、行先階は0")
        logger.info("   - 荷重データは昇降中、起動直前の荷重を維持")
        logger.info("🎯 移動特化版：扉制御なし、階数設定と移動のみ")
        logger.info(f"⚡ 速度設定: {speed_names.get(self.speed_mode, '不明')}")
        self.running = True
        
        # 各送信処理を開始
        self._elevator_data_transmission()
        time.sleep(1)
        self._autopilot_command_transmission()
        time.sleep(1)
        self._display_status()

    def stop_simulation(self):
        """シミュレーション停止"""
        logger.info("🛑 シミュレーション停止")
        self.running = False

    def shutdown(self):
        """終了処理"""
        logger.info("🛑 システム終了中...")
        self.stop_simulation()
        
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
    
    parser = argparse.ArgumentParser(description='エレベーター移動シミュレーター（SEC-3000H仕様準拠・移動特化版・速度オプション付き）')
    parser.add_argument('--port', default=SERIAL_PORT, help='シリアルポート')
    parser.add_argument('--load', type=int, default=0, help='初期荷重 (kg)')
    parser.add_argument('--speed', type=int, choices=[1, 2, 3], default=1, 
                       help='速度モード: 1=高速(現在), 2=ゆっくり, 3=現実的')
    args = parser.parse_args()
    
    # シグナルハンドラー設定
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # シリアルポート設定更新
    SERIAL_CONFIG['port'] = args.port
    
    # シミュレーター初期化
    global simulator
    simulator = ElevatorSimulator(speed_mode=args.speed)
    simulator.load_weight = args.load
    
    try:
        # 初期化
        if not simulator.initialize():
            sys.exit(1)
        
        # シミュレーション開始
        simulator.start_simulation()
        
        speed_names = {1: "高速", 2: "ゆっくり", 3: "現実的"}
        logger.info(f"\n✅ エレベーター移動シミュレーター稼働中 (Ctrl+C で終了)")
        logger.info(f"🎯 移動特化版：扉制御なし、移動のみに集中")
        logger.info(f"⚡ 速度モード: {args.speed} ({speed_names.get(args.speed, '不明')})")
        
        # メインループ
        while simulator.running:
            time.sleep(1)

    except Exception as e:
        logger.error(f"❌ システムエラー: {e}")
        simulator.shutdown()
        sys.exit(1)

if __name__ == "__main__":
    main()
