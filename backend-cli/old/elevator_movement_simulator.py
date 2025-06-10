#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
エレベーター移動シミュレーター（SEC-3000H仕様準拠・移動特化版）
COM27にSEC-3000H仕様準拠のENQ/ACK信号を送信
エレベーターの移動にのみフォーカス（扉制御なし）
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
    """エレベーター移動シミュレーター（SEC-3000H仕様準拠・移動特化版）"""
    
    def __init__(self):
        self.serial_conn: Optional[serial.Serial] = None
        self.running = False
        
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
        
        # 移動シナリオ
        self.scenarios = [
            {"from": 1, "to": 3, "duration": 8},   # 1F → 3F
            {"from": 3, "to": -1, "duration": 12}, # 3F → B1F
            {"from": -1, "to": 5, "duration": 15}, # B1F → 5F
            {"from": 5, "to": 1, "duration": 10},  # 5F → 1F
            {"from": 1, "to": 2, "duration": 5},   # 1F → 2F
            {"from": 2, "to": 4, "duration": 7},   # 2F → 4F
        ]
        self.current_scenario = 0

    def initialize(self):
        """初期化"""
        logger.info("🏢 エレベーター移動シミュレーター起動（SEC-3000H仕様準拠・移動特化版）")
        logger.info(f"📡 シリアルポート: {SERIAL_PORT}")
        logger.info(f"🏷️ エレベーター局番号: {self.elevator_station}")
        logger.info(f"🎯 自動運転装置局番号: {self.autopilot_station}")
        logger.info("📋 SEC-3000H仕様：着床後停止タイマーUP後に行先階データ0設定")
        logger.info("🚀 移動特化版：扉制御なし、移動のみに集中")
        
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
            
            # 次の送信スケジュール
            if self.running:
                threading.Timer(2.0, self._elevator_data_transmission).start()
                
        except Exception as e:
            logger.error(f"❌ エレベーターデータ送信エラー: {e}")
            if self.running:
                threading.Timer(2.0, self._elevator_data_transmission).start()

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
            
            # 次のコマンド送信スケジュール
            if self.running:
                threading.Timer(10.0, self._autopilot_command_transmission).start()
                
        except Exception as e:
            logger.error(f"❌ 自動運転装置コマンド送信エラー: {e}")
            if self.running:
                threading.Timer(10.0, self._autopilot_command_transmission).start()

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
            
            # SEC-3000H仕様：停止タイマー開始（3秒）
            self.stop_timer_active = True
            threading.Timer(3.0, self._stop_timer_up).start()
    
    def _stop_timer_up(self):
        """停止タイマーUP処理（SEC-3000H仕様）"""
        logger.info("⏰ 停止タイマーUP：行先階データを0に設定")
        
        # SEC-3000H仕様：着床後データ0を書き込み（停止タイマーUP後自動）
        self.target_floor = None
        self.stop_timer_active = False
        
        # 次のシナリオ準備（5秒後に次の移動開始可能）
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
        
        logger.info(f"\n[{timestamp}] 🏢 エレベーター状態（移動特化版）")
        logger.info(f"現在階: {current_str}")
        logger.info(f"行先階: {target_str}")
        logger.info(f"状態: {moving_str}")
        logger.info(f"荷重: {self.load_weight}kg")
        logger.info(f"停止タイマー: {timer_str}")
        logger.info(f"次のシナリオ: {self.scenarios[self.current_scenario]}")
        
        # 次の状態表示をスケジュール
        if self.running:
            threading.Timer(15.0, self._display_status).start()

    def start_simulation(self):
        """シミュレーション開始"""
        if self.running:
            logger.info("⚠️ シミュレーションは既に実行中です")
            return

        logger.info("🚀 エレベーター移動シミュレーション開始（SEC-3000H仕様準拠・移動特化版）")
        logger.info("📋 仕様準拠項目：")
        logger.info("   - 着床後停止タイマーUP後に行先階データ0設定")
        logger.info("   - 行先階と設定階が同一の場合、行先階は0")
        logger.info("   - 荷重データは昇降中、起動直前の荷重を維持")
        logger.info("🎯 移動特化版：扉制御なし、階数設定と移動のみ")
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
    
    parser = argparse.ArgumentParser(description='エレベーター移動シミュレーター（SEC-3000H仕様準拠・移動特化版）')
    parser.add_argument('--port', default=SERIAL_PORT, help='シリアルポート')
    parser.add_argument('--load', type=int, default=0, help='初期荷重 (kg)')
    args = parser.parse_args()
    
    # シグナルハンドラー設定
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # シリアルポート設定更新
    SERIAL_CONFIG['port'] = args.port
    
    # シミュレーター初期化
    global simulator
    simulator = ElevatorSimulator()
    simulator.load_weight = args.load
    
    try:
        # 初期化
        if not simulator.initialize():
            sys.exit(1)
        
        # シミュレーション開始
        simulator.start_simulation()
        
        logger.info("\n✅ エレベーター移動シミュレーター稼働中 (Ctrl+C で終了)")
        logger.info("🎯 移動特化版：扉制御なし、移動のみに集中")
        
        # メインループ
        while simulator.running:
            time.sleep(1)

    except Exception as e:
        logger.error(f"❌ システムエラー: {e}")
        simulator.shutdown()
        sys.exit(1)

if __name__ == "__main__":
    main()
