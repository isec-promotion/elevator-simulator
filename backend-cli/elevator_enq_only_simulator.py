#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
エレベーターENQ専用シミュレーター
指定された仕様に従ってENQメッセージのみを送信
①現在階 → ②行先階 → ③着床（行先階0000） → ④乗客降客 → 5秒待機
"""

import serial
import time
import logging
import signal
import sys
import random
from datetime import datetime
from typing import Optional

# ── 設定 ───────────────────────────────────
SERIAL_PORT = "COM31"  # Windows

SERIAL_CONFIG = {
    'port': SERIAL_PORT,
    'baudrate': 9600,
    'bytesize': serial.EIGHTBITS,
    'parity': serial.PARITY_EVEN,
    'stopbits': serial.STOPBITS_ONE,
    'timeout': 0.2
}

# ── ログ設定 ─────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class ElevatorENQSimulator:
    """エレベーターENQ専用シミュレーター"""
    
    def __init__(self, port: str):
        self.port = port
        self.serial_conn: Optional[serial.Serial] = None
        self.running = False
        
        # 階数定義
        self.floors = [-1, 1, 2, 3]  # B1F, 1F, 2F, 3F
        self.current_floor = 1  # 初期階数：1F
        
    def initialize(self):
        """初期化"""
        logger.info("🏢 エレベーターENQ専用シミュレーター初期化")
        logger.info(f"📡 シリアルポート: {self.port}")
        
        try:
            # シリアル接続設定を更新
            config = SERIAL_CONFIG.copy()
            config['port'] = self.port
            
            self.serial_conn = serial.Serial(**config)
            logger.info(f"✅ シリアルポート {self.port} 接続成功")
            return True
        except Exception as e:
            logger.error(f"❌ シリアル接続失敗: {e}")
            return False
    
    def _calculate_checksum(self, data: str) -> str:
        """チェックサム計算"""
        checksum = 0
        for char in data:
            checksum += ord(char)
        return f"{checksum & 0xFF:02X}"
    
    def _send_enq(self, data_num: str, data_value: str, description: str):
        """ENQメッセージ送信"""
        try:
            # ENQメッセージ構築
            station = "0002"  # エレベーター局番号
            command = "W"
            
            # データ部分
            data_part = f"{station}{command}{data_num}{data_value}"
            
            # チェックサム計算
            checksum = self._calculate_checksum(data_part)
            
            # 完全なメッセージ
            message = f"\x05{data_part}{checksum}"
            
            # 送信
            self.serial_conn.write(message.encode('ascii'))
            
            # ログ出力
            timestamp = datetime.now().strftime("%Y年%m月%d日 %H:%M:%S")
            logger.info(f"[{timestamp}] 📤 ENQ送信: {description} (局番号:{station} データ:{data_value} チェックサム:{checksum})")
            
        except Exception as e:
            logger.error(f"❌ ENQ送信エラー: {e}")
    
    def _floor_to_hex(self, floor: int) -> str:
        """階数をHEX文字列に変換"""
        if floor == -1:  # B1F
            return "FFFF"
        else:
            return f"{floor:04X}"
    
    def _floor_to_string(self, floor: int) -> str:
        """階数を文字列に変換"""
        if floor == -1:
            return "B1F"
        else:
            return f"{floor}F"
    
    def start_simulation(self):
        """シミュレーション開始"""
        if not self.serial_conn:
            logger.error("❌ シリアル接続が確立されていません")
            return
        
        logger.info("🚀 エレベーターENQ専用シミュレーション開始")
        logger.info("📋 送信仕様:")
        logger.info("   ①現在階 → ②行先階 → ③着床 → ④乗客降客 → 5秒待機")
        logger.info("   ①～④は1秒間隔で送信")
        
        self.running = True
        
        try:
            while self.running:
                # ランダムな行先階を選択（現在階以外）
                available_floors = [f for f in self.floors if f != self.current_floor]
                target_floor = random.choice(available_floors)
                
                logger.info(f"\n🎯 新しい移動シナリオ: {self._floor_to_string(self.current_floor)} → {self._floor_to_string(target_floor)}")
                
                # ①現在階送信（5回）
                current_hex = self._floor_to_hex(self.current_floor)
                for i in range(5):
                    self._send_enq("0001", current_hex, f"現在階: {self._floor_to_string(self.current_floor)} ({i+1}/5)")
                    time.sleep(1)  # 1秒間隔で送信
                logger.info("⏰ 3秒待機中...")
                time.sleep(3)
                
                # ②行先階送信（5回）
                target_hex = self._floor_to_hex(target_floor)
                for i in range(5):
                    self._send_enq("0002", target_hex, f"行先階: {self._floor_to_string(target_floor)} ({i+1}/5)")
                    time.sleep(1)  # 1秒間隔で送信
                logger.info("⏰ 3秒待機中...")
                time.sleep(3)

                # ④着床送信（5回）
                for i in range(5):
                    self._send_enq("0002", "0000", f"着床: 行先階クリア ({i+1}/5)")
                    time.sleep(1)  # 1秒間隔で送信
                
                # 現在階を更新
                self.current_floor = target_floor
                logger.info(f"🏁 着床完了: {self._floor_to_string(self.current_floor)}")
                
                # ③乗客降客送信（5回）
                for i in range(5):
                    self._send_enq("0003", "074E", f"乗客降客: 1870kg ({i+1}/5)")
                    time.sleep(1)  # 1秒間隔で送信
                
                # 5秒待機 次のシナリオへ移る
                logger.info("⏰ 5秒待機中...")
                for i in range(5):
                    if not self.running:
                        break
                    time.sleep(1)
                
                if not self.running:
                    break
                
        except KeyboardInterrupt:
            logger.info("\n🛑 Ctrl+C が押されました")
        except Exception as e:
            logger.error(f"❌ シミュレーションエラー: {e}")
        finally:
            self.stop_simulation()
    
    def stop_simulation(self):
        """シミュレーション停止"""
        logger.info("🛑 シミュレーション停止")
        self.running = False
        
        if self.serial_conn and self.serial_conn.is_open:
            self.serial_conn.close()
            logger.info("📡 シリアルポート切断完了")

def main():
    """メイン処理"""
    import argparse
    
    parser = argparse.ArgumentParser(description='エレベーターENQ専用シミュレーター')
    parser.add_argument('--port', default=SERIAL_PORT, help='シリアルポート')
    parser.add_argument('--start-floor', type=int, choices=[-1, 1, 2, 3], default=1, 
                       help='開始階数 (-1:B1F, 1:1F, 2:2F, 3:3F)')
    args = parser.parse_args()
    
    # シグナルハンドラー設定
    def signal_handler(signum, frame):
        logger.info(f"\n🛑 シグナル {signum} を受信しました")
        if 'simulator' in locals():
            simulator.stop_simulation()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # シミュレーター初期化
    simulator = ElevatorENQSimulator(args.port)
    simulator.current_floor = args.start_floor
    
    if not simulator.initialize():
        logger.error("❌ 初期化失敗")
        sys.exit(1)
    
    logger.info(f"🏢 開始階数: {simulator._floor_to_string(args.start_floor)}")
    logger.info("✅ システム準備完了 (Ctrl+C で終了)")
    
    # シミュレーション開始
    simulator.start_simulation()

if __name__ == "__main__":
    main()
