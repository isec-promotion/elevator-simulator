#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SEC-3000H エレベーターシミュレーター 自動運転パイロット
Raspberry Pi 自動運転制御スクリプト
"""

import serial
import time
import json
import logging
import threading
import signal
import sys
import random
from datetime import datetime
from typing import Dict, Any, Optional, List

# ログ設定
import os
log_dir = os.path.expanduser('~/logs')
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, 'elevator_auto_pilot.log')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

class ElevatorAutoPilot:
    """エレベーター自動運転パイロットクラス"""
    
    def __init__(self, port: str = '/dev/ttyUSB0', baudrate: int = 9600):
        self.port = port
        self.baudrate = baudrate
        self.serial_conn: Optional[serial.Serial] = None
        self.running = False
        self.auto_pilot_enabled = False
        
        # 自動運転設定
        self.config = {
            'passenger_weight': 60,      # 1人あたりの重量（kg）
            'max_passengers': 10,        # 最大乗客数
            'min_floor': 1,              # 最低階
            'max_floor': 5,              # 最高階
            'operation_interval': 15,    # 運転間隔（秒）
            'door_open_time': 8,         # ドア開放時間（秒）
            'travel_time_per_floor': 3,  # 1階あたりの移動時間（秒）
            'passenger_boarding_time': 2, # 乗客乗降時間（秒）
        }
        
        # 現在の状態
        self.current_status = {
            'current_floor': 1,
            'target_floor': None,
            'door_status': 'closed',
            'load_weight': 0,
            'passengers': 0,
            'is_moving': False,
            'last_communication': None
        }
        
        # 自動運転シナリオ
        self.scenarios = [
            {'name': '朝の通勤ラッシュ', 'passenger_rate': 0.8, 'target_floors': [2, 3, 4, 5]},
            {'name': '昼間の軽い利用', 'passenger_rate': 0.3, 'target_floors': [1, 2, 3, 4, 5]},
            {'name': '夕方の帰宅ラッシュ', 'passenger_rate': 0.7, 'target_floors': [1]},
            {'name': '深夜の軽い利用', 'passenger_rate': 0.1, 'target_floors': [1, 2, 3]},
        ]
        
        self.current_scenario = self.scenarios[1]  # デフォルトは昼間
        
        # 通信ログ
        self.communication_logs = []
        
        # 自動運転スレッド
        self.auto_pilot_thread = None
        
    def connect(self) -> bool:
        """シリアルポートに接続"""
        try:
            self.serial_conn = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_EVEN,
                stopbits=serial.STOPBITS_ONE,
                timeout=1
            )
            logger.info(f"✅ シリアルポート {self.port} に接続しました")
            return True
        except Exception as e:
            logger.error(f"❌ シリアルポート接続エラー: {e}")
            return False
    
    def disconnect(self):
        """シリアルポート切断"""
        if self.serial_conn and self.serial_conn.is_open:
            self.serial_conn.close()
            logger.info("📡 シリアルポートを切断しました")
    
    def calculate_checksum(self, data: bytes) -> int:
        """チェックサム計算"""
        total = sum(data)
        lower_byte = total & 0xFF
        upper_byte = (total >> 8) & 0xFF
        return (lower_byte + upper_byte) & 0xFF
    
    def send_command(self, station: str, command: str, data_num: int, data_value: int) -> bool:
        """コマンド送信"""
        try:
            if not self.serial_conn or not self.serial_conn.is_open:
                return False
            
            # メッセージ作成
            message = bytearray()
            message.append(0x05)  # ENQ
            message.extend(station.encode('ascii'))
            message.append(ord(command))
            message.extend(f"{data_num:04X}".encode('ascii'))
            message.extend(f"{data_value:04X}".encode('ascii'))
            
            # チェックサム計算
            checksum = self.calculate_checksum(message)
            message.extend(f"{checksum:02X}".encode('ascii'))
            
            # 送信
            self.serial_conn.write(message)
            
            # ログ出力
            data_desc = self.format_command_description(data_num, data_value)
            logger.info(f"📤 送信: ENQ(05) 局番号:{station} CMD:{command} {data_desc} データ:{data_value:04X} チェックサム:{checksum:02X}")
            
            # 通信ログに追加
            self.add_communication_log("send", f"ENQ(05) 局番号:{station} CMD:{command} {data_desc}")
            
            return True
        except Exception as e:
            logger.error(f"❌ コマンド送信エラー: {e}")
            return False
    
    def format_command_description(self, data_num: int, data_value: int) -> str:
        """コマンドの説明を生成"""
        if data_num == 0x0010:  # 階数設定
            floor_name = "B1F" if data_value == 0xFFFF else f"{data_value}F"
            return f"階数設定: {floor_name}"
        elif data_num == 0x0011:  # 扉制御
            if data_value == 0x0001:
                return "扉制御: 開扉"
            elif data_value == 0x0002:
                return "扉制御: 閉扉"
            else:
                return "扉制御: 停止"
        elif data_num == 0x0003:  # 荷重設定
            return f"荷重設定: {data_value}kg"
        else:
            return f"データ番号: {data_num:04X}"
    
    def add_communication_log(self, direction: str, message: str, result: str = "success"):
        """通信ログを追加"""
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'direction': direction,
            'message': message,
            'result': result
        }
        
        self.communication_logs.append(log_entry)
        
        # ログの最大数を制限（最新500件）
        if len(self.communication_logs) > 500:
            self.communication_logs = self.communication_logs[-500:]
    
    def set_floor(self, floor: int) -> bool:
        """階数設定"""
        if floor < self.config['min_floor'] or floor > self.config['max_floor']:
            logger.warning(f"⚠️ 無効な階数: {floor}")
            return False
        
        success = self.send_command("0001", "W", 0x0010, floor)
        if success:
            self.current_status['target_floor'] = floor
            logger.info(f"🎯 目標階数を設定: {floor}F")
        return success
    
    def open_door(self) -> bool:
        """扉を開く"""
        success = self.send_command("0001", "W", 0x0011, 0x0001)
        if success:
            self.current_status['door_status'] = 'opening'
            logger.info("🚪 扉を開いています...")
        return success
    
    def close_door(self) -> bool:
        """扉を閉じる"""
        success = self.send_command("0001", "W", 0x0011, 0x0002)
        if success:
            self.current_status['door_status'] = 'closing'
            logger.info("🚪 扉を閉じています...")
        return success
    
    def set_load(self, weight: int) -> bool:
        """荷重設定"""
        success = self.send_command("0001", "W", 0x0003, weight)
        if success:
            self.current_status['load_weight'] = weight
            self.current_status['passengers'] = max(0, weight // self.config['passenger_weight'])
            logger.info(f"⚖️ 荷重を設定: {weight}kg ({self.current_status['passengers']}人)")
        return success
    
    def simulate_passenger_activity(self, floor: int) -> Dict[str, int]:
        """乗客の出入りをシミュレート"""
        current_passengers = self.current_status['passengers']
        scenario = self.current_scenario
        
        # 降車人数（現在の乗客数まで）
        if floor in scenario['target_floors']:
            # 目標階では降車率が高い
            exit_rate = 0.6 if floor != 1 else 0.8  # 1階では多くの人が降車
            exiting = min(current_passengers, int(current_passengers * exit_rate))
        else:
            exiting = random.randint(0, min(2, current_passengers))
        
        # 乗車人数（残り容量まで）
        remaining_capacity = self.config['max_passengers'] - (current_passengers - exiting)
        
        # シナリオに基づく乗車人数
        if floor == 1:
            # 1階では多くの人が乗車
            max_entering = min(remaining_capacity, int(self.config['max_passengers'] * scenario['passenger_rate']))
            entering = random.randint(0, max_entering)
        else:
            # 他の階では少ない乗車
            max_entering = min(remaining_capacity, 3)
            entering = random.randint(0, max_entering) if random.random() < scenario['passenger_rate'] else 0
        
        new_passengers = current_passengers - exiting + entering
        new_weight = new_passengers * self.config['passenger_weight']
        
        logger.info(f"🏢 {floor}F: 乗車 {entering}人, 降車 {exiting}人 → 総乗客数 {new_passengers}人 ({new_weight}kg)")
        
        return {
            'entering': entering,
            'exiting': exiting,
            'total_passengers': new_passengers,
            'total_weight': new_weight
        }
    
    def select_next_floor(self) -> int:
        """次の目標階を選択"""
        current_floor = self.current_status['current_floor']
        scenario = self.current_scenario
        
        # 乗客がいる場合は目標階を優先
        if self.current_status['passengers'] > 0:
            # 目標階からランダムに選択
            possible_floors = [f for f in scenario['target_floors'] if f != current_floor]
            if possible_floors:
                return random.choice(possible_floors)
        
        # 乗客がいない場合は1階に戻るか、ランダムに移動
        if current_floor != 1 and random.random() < 0.4:
            return 1  # 1階に戻る確率40%
        
        # ランダムな階を選択
        possible_floors = list(range(self.config['min_floor'], self.config['max_floor'] + 1))
        possible_floors = [f for f in possible_floors if f != current_floor]
        return random.choice(possible_floors)
    
    def change_scenario(self):
        """シナリオを変更"""
        current_hour = datetime.now().hour
        
        if 7 <= current_hour <= 9:
            self.current_scenario = self.scenarios[0]  # 朝の通勤ラッシュ
        elif 17 <= current_hour <= 19:
            self.current_scenario = self.scenarios[2]  # 夕方の帰宅ラッシュ
        elif 22 <= current_hour or current_hour <= 6:
            self.current_scenario = self.scenarios[3]  # 深夜の軽い利用
        else:
            self.current_scenario = self.scenarios[1]  # 昼間の軽い利用
        
        logger.info(f"🎭 シナリオ変更: {self.current_scenario['name']}")
    
    def execute_elevator_operation(self):
        """エレベーター運転を実行"""
        try:
            # シナリオ変更チェック
            if random.random() < 0.1:  # 10%の確率でシナリオ変更
                self.change_scenario()
            
            current_floor = self.current_status['current_floor']
            
            # 次の目標階を選択
            target_floor = self.select_next_floor()
            
            logger.info(f"🚀 自動運転開始: {current_floor}F → {target_floor}F")
            
            # 1. 扉を開く
            self.open_door()
            time.sleep(2)  # 扉が開くまで待機
            
            # 2. 乗客の出入りをシミュレート
            passenger_activity = self.simulate_passenger_activity(current_floor)
            
            # 3. 荷重を更新
            self.set_load(passenger_activity['total_weight'])
            time.sleep(self.config['passenger_boarding_time'])
            
            # 4. 扉を閉じる
            self.close_door()
            time.sleep(2)  # 扉が閉じるまで待機
            
            # 5. 目標階に移動
            if target_floor != current_floor:
                self.current_status['is_moving'] = True
                self.set_floor(target_floor)
                
                # 移動時間をシミュレート
                travel_time = abs(target_floor - current_floor) * self.config['travel_time_per_floor']
                logger.info(f"🏃 移動中... 予想時間: {travel_time}秒")
                time.sleep(travel_time)
                
                # 現在階を更新
                self.current_status['current_floor'] = target_floor
                self.current_status['is_moving'] = False
                logger.info(f"✅ {target_floor}F に到着しました")
            
            # 6. 到着階で扉を開く
            self.open_door()
            time.sleep(2)
            
            # 7. 乗客の出入りをシミュレート
            passenger_activity = self.simulate_passenger_activity(target_floor)
            
            # 8. 荷重を更新
            self.set_load(passenger_activity['total_weight'])
            time.sleep(self.config['passenger_boarding_time'])
            
            # 9. 扉を閉じる
            self.close_door()
            time.sleep(2)
            
            logger.info(f"🏁 運転完了: 現在 {target_floor}F, 乗客 {passenger_activity['total_passengers']}人")
            
        except Exception as e:
            logger.error(f"❌ 自動運転エラー: {e}")
            self.current_status['is_moving'] = False
    
    def auto_pilot_loop(self):
        """自動運転ループ"""
        logger.info("🤖 自動運転パイロットを開始します...")
        
        while self.auto_pilot_enabled and self.running:
            try:
                # 自動運転実行
                self.execute_elevator_operation()
                
                # 次の運転まで待機
                wait_time = self.config['operation_interval'] + random.randint(-3, 3)  # ランダムな待機時間
                logger.info(f"⏰ 次の運転まで {wait_time}秒待機...")
                
                for _ in range(wait_time):
                    if not self.auto_pilot_enabled or not self.running:
                        break
                    time.sleep(1)
                
            except Exception as e:
                logger.error(f"❌ 自動運転ループエラー: {e}")
                time.sleep(5)
    
    def enable_auto_pilot(self):
        """自動運転パイロットを有効化"""
        if not self.auto_pilot_enabled:
            self.auto_pilot_enabled = True
            logger.info("🤖 自動運転パイロットを有効にしました")
            self.add_communication_log("system", "自動運転パイロット有効化")
            
            # 自動運転スレッド開始
            self.auto_pilot_thread = threading.Thread(target=self.auto_pilot_loop, daemon=True)
            self.auto_pilot_thread.start()
    
    def disable_auto_pilot(self):
        """自動運転パイロットを無効化"""
        if self.auto_pilot_enabled:
            self.auto_pilot_enabled = False
            logger.info("🛑 自動運転パイロットを無効にしました")
            self.add_communication_log("system", "自動運転パイロット無効化")
    
    def get_status(self) -> Dict[str, Any]:
        """現在の状態を取得"""
        return {
            'auto_pilot_enabled': self.auto_pilot_enabled,
            'current_status': self.current_status.copy(),
            'config': self.config.copy(),
            'current_scenario': self.current_scenario.copy(),
            'communication_logs': self.communication_logs[-10:],  # 最新10件
            'connection_status': 'connected' if (self.serial_conn and self.serial_conn.is_open) else 'disconnected'
        }
    
    def start(self):
        """自動運転パイロット開始"""
        self.running = True
        
        if self.connect():
            # 初期設定
            self.set_floor(1)  # 1階からスタート
            self.set_load(0)   # 初期荷重0
            time.sleep(2)
            
            # 自動運転パイロットを有効化
            self.enable_auto_pilot()
            
            logger.info("🚀 エレベーター自動運転パイロットシステムを開始しました")
            
            try:
                while self.running:
                    # 定期的に状態をログ出力
                    time.sleep(60)  # 1分ごと
                    status = self.get_status()
                    logger.info(f"📊 現在の状態: {status['current_status']['current_floor']}F, "
                              f"乗客数={status['current_status']['passengers']}人, "
                              f"荷重={status['current_status']['load_weight']}kg, "
                              f"シナリオ={status['current_scenario']['name']}")
                    
            except KeyboardInterrupt:
                logger.info("🛑 キーボード割り込みを受信しました")
        else:
            logger.error("❌ シリアルポート接続に失敗しました")
    
    def stop(self):
        """自動運転パイロット停止"""
        self.running = False
        self.disable_auto_pilot()
        self.disconnect()
        logger.info("✅ エレベーター自動運転パイロットシステムを停止しました")

def signal_handler(signum, frame):
    """シグナルハンドラー"""
    logger.info(f"🛑 シグナル {signum} を受信しました。システムを停止します...")
    if 'pilot' in globals():
        pilot.stop()
    sys.exit(0)

def main():
    """メイン関数"""
    # シグナルハンドラー設定
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    logger.info("🏢 SEC-3000H エレベーターシミュレーター")
    logger.info("🤖 自動運転パイロットシステム v1.0")
    logger.info("=" * 50)
    
    # 自動運転パイロット初期化
    global pilot
    pilot = ElevatorAutoPilot()
    
    try:
        pilot.start()
    except Exception as e:
        logger.error(f"❌ システムエラー: {e}")
        pilot.stop()
        sys.exit(1)

if __name__ == "__main__":
    main()
