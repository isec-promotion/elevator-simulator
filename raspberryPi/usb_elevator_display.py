#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SEC-3000H Elevator Display - USB Direct Connection
PCとRaspberry Pi 4をUSBケーブルで直接接続してエレベーター案内ディスプレイ
"""

import serial
import time
import json
import logging
import threading
import signal
import sys
import socket
from datetime import datetime
from typing import Dict, Any, Optional

from PIL import Image, ImageDraw, ImageFont
import gi
gi.require_version('Gst', '1.0')
gi.require_version('GstRtspServer', '1.0')
from gi.repository import Gst, GstRtspServer, GLib

# ── 設定 ───────────────────────────────────
WIDTH, HEIGHT, FPS = 640, 360, 15
USB_DEVICE = '/dev/ttyACM0'  # USB接続デバイス
USB_CONFIG = {
    'baudrate': 115200,
    'bytesize': serial.EIGHTBITS,
    'parity': serial.PARITY_NONE,
    'stopbits': serial.STOPBITS_ONE,
    'timeout': 1
}
FONT_PATH = "/usr/share/fonts/truetype/ipafont-mincho/ipam.ttf"

# ── ログ設定 ─────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ── USB通信受信クラス ───────────────────────
class USBElevatorReceiver:
    """USB直接通信エレベーター受信クラス"""
    
    def __init__(self, usb_device: str = None):
        self.usb_device = usb_device
        self.usb_conn: Optional[serial.Serial] = None
        self.running = False
        self.current_status = {
            'current_floor': '1F',
            'target_floor': None,
            'is_moving': False,
            'door_status': 'unknown',
            'load_weight': 0,
            'last_communication': None
        }
        self.lock = threading.Lock()

    def find_usb_device(self) -> Optional[str]:
        """利用可能なUSBデバイスを検索"""
        import glob
        import os
        
        logger.info("🔍 利用可能なUSBデバイスを検索中...")
        
        # 一般的なUSBシリアルデバイスパターン
        device_patterns = [
            '/dev/ttyACM*',
            '/dev/ttyUSB*',
            '/dev/ttyAMA*',
            '/dev/serial/by-id/*'
        ]
        
        found_devices = []
        for pattern in device_patterns:
            devices = glob.glob(pattern)
            found_devices.extend(devices)
        
        if found_devices:
            logger.info(f"📱 発見されたデバイス: {found_devices}")
            
            # 各デバイスをテスト
            for device in found_devices:
                if self._test_device(device):
                    logger.info(f"✅ 使用可能なデバイス: {device}")
                    return device
            
            # テストに失敗した場合、最初のデバイスを返す
            logger.warning("⚠️ テストに失敗しましたが、最初のデバイスを試行します")
            return found_devices[0]
        else:
            logger.error("❌ USBデバイスが見つかりません")
            logger.info("💡 以下を確認してください:")
            logger.info("   - USBケーブルが接続されているか")
            logger.info("   - PCとの接続が確立されているか")
            logger.info("   - デバイスの権限設定")
            return None

    def _test_device(self, device: str) -> bool:
        """デバイスが使用可能かテスト"""
        try:
            test_conn = serial.Serial(device, **USB_CONFIG)
            test_conn.close()
            return True
        except Exception:
            return False

    def connect_usb(self) -> bool:
        """USB接続"""
        # デバイスが指定されていない場合は自動検出
        if not self.usb_device:
            self.usb_device = self.find_usb_device()
            if not self.usb_device:
                return False
        
        try:
            self.usb_conn = serial.Serial(self.usb_device, **USB_CONFIG)
            logger.info(f"✅ USB接続成功: {self.usb_device}")
            logger.info(f"📡 通信設定: {USB_CONFIG['baudrate']}bps, USB直接通信")
            return True
        except Exception as e:
            logger.error(f"❌ USB接続エラー ({self.usb_device}): {e}")
            
            # 自動検出を再試行
            if self.usb_device != USB_DEVICE:
                logger.info("🔄 別のデバイスで再試行...")
                self.usb_device = self.find_usb_device()
                if self.usb_device:
                    try:
                        self.usb_conn = serial.Serial(self.usb_device, **USB_CONFIG)
                        logger.info(f"✅ USB接続成功: {self.usb_device}")
                        return True
                    except Exception as e2:
                        logger.error(f"❌ 再試行も失敗: {e2}")
            
            return False

    def send_usb_message(self, message_type: str, **kwargs) -> bool:
        """USBメッセージ送信"""
        if not self.usb_conn or not self.usb_conn.is_open:
            return False
        
        try:
            message = {
                "type": message_type,
                "timestamp": datetime.now().isoformat(),
                **kwargs
            }
            
            json_message = json.dumps(message) + '\n'
            self.usb_conn.write(json_message.encode('utf-8'))
            return True
            
        except Exception as e:
            logger.error(f"❌ USB送信エラー: {e}")
            return False

    def handle_usb_command(self, data: Dict[str, Any]):
        """USB受信コマンド処理"""
        try:
            command_type = data.get("type")
            timestamp = data.get("timestamp")
            
            if command_type == "identify":
                # 識別応答
                self.send_usb_message("identify_response", 
                                    device="raspberry_pi_elevator",
                                    version="2.0",
                                    capabilities=["rtsp_streaming", "elevator_display"])
                logger.info("🔍 識別要求に応答しました")
                
            elif command_type == "set_floor":
                floor = data.get("floor")
                if floor:
                    with self.lock:
                        old_floor = self.current_status['current_floor']
                        if old_floor != floor:
                            self.current_status['target_floor'] = floor
                            self.current_status['is_moving'] = True
                            logger.info(f"🎯 移動指示: {old_floor} → {floor}")
                        else:
                            self.current_status['target_floor'] = None
                            self.current_status['is_moving'] = False
                            logger.info(f"🏢 同一階設定: {floor}")
                    
                    # ACK応答
                    self.send_usb_message("ack", command="set_floor", floor=floor)
                    
                    # 移動シミュレーション
                    if self.current_status['is_moving']:
                        threading.Thread(target=self._simulate_movement, args=(floor,), daemon=True).start()
                
            elif command_type == "door_control":
                action = data.get("action")
                if action:
                    with self.lock:
                        if action == "open":
                            self.current_status['door_status'] = 'opening'
                            # 扉開放時に移動完了
                            if self.current_status['target_floor']:
                                self.current_status['current_floor'] = self.current_status['target_floor']
                                self.current_status['target_floor'] = None
                                self.current_status['is_moving'] = False
                                logger.info(f"🏢 扉開放により到着完了: {self.current_status['current_floor']}")
                        elif action == "close":
                            self.current_status['door_status'] = 'closing'
                        else:
                            self.current_status['door_status'] = 'unknown'
                    
                    logger.info(f"🚪 扉制御: {action}")
                    
                    # ACK応答
                    self.send_usb_message("ack", command="door_control", action=action)
            
            # 状態更新を送信
            self._send_status_update()
            
        except Exception as e:
            logger.error(f"❌ コマンド処理エラー: {e}")
            self.send_usb_message("error", message=str(e))

    def _simulate_movement(self, target_floor: str):
        """移動シミュレーション"""
        time.sleep(3)  # 移動時間
        
        with self.lock:
            if self.current_status['is_moving'] and self.current_status['target_floor'] == target_floor:
                self.current_status['current_floor'] = target_floor
                self.current_status['target_floor'] = None
                self.current_status['is_moving'] = False
                logger.info(f"✅ 移動完了: {target_floor}")
                
        self._send_status_update()

    def _send_status_update(self):
        """状態更新送信"""
        with self.lock:
            status = self.current_status.copy()
        
        self.send_usb_message("status_update", **status)

    def listen_usb(self):
        """USB受信ループ"""
        logger.info("🎧 USB受信開始...")
        
        while self.running:
            try:
                if self.usb_conn and self.usb_conn.is_open:
                    if self.usb_conn.in_waiting > 0:
                        line = self.usb_conn.readline().decode('utf-8').strip()
                        if line:
                            try:
                                data = json.loads(line)
                                logger.info(f"📨 USB受信: {data.get('type', 'unknown')}")
                                self.handle_usb_command(data)
                            except json.JSONDecodeError:
                                logger.warning(f"⚠️ 無効なJSONメッセージ: {line}")
                
                time.sleep(0.05)
                
            except Exception as e:
                logger.error(f"❌ USB受信エラー: {e}")
                time.sleep(1)

    def start(self):
        """受信開始"""
        if not self.connect_usb():
            return False
        
        self.running = True
        threading.Thread(target=self.listen_usb, daemon=True).start()
        return True

    def stop(self):
        """受信停止"""
        self.running = False
        if self.usb_conn and self.usb_conn.is_open:
            self.usb_conn.close()
        logger.info("🛑 USB受信停止")

# ── RTSP サーバー ────────────────────────────
def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        return s.getsockname()[0]
    finally:
        s.close()

def pil_to_gst_buffer(img: Image.Image):
    data = img.tobytes()
    buf = Gst.Buffer.new_allocate(None, len(data), None)
    buf.fill(0, data)
    buf.duration = Gst.util_uint64_scale_int(1, Gst.SECOND, FPS)
    return buf

class USBElevatorDisplayFactory(GstRtspServer.RTSPMediaFactory):
    def __init__(self, receiver: USBElevatorReceiver):
        super().__init__()
        self.receiver = receiver
        self.set_shared(True)
        self.launch_str = (
            '( appsrc name=src is-live=true block=true format=time '
            f' caps=video/x-raw,format=RGB,width={WIDTH},height={HEIGHT},framerate={FPS}/1 '
            ' do-timestamp=true ! videoconvert '
            f'! video/x-raw,format=I420,width={WIDTH},height={HEIGHT},framerate={FPS}/1 '
            ' ! x264enc tune=zerolatency bitrate=500 speed-preset=ultrafast '
            ' ! rtph264pay name=pay0 pt=96 config-interval=1 )'
        )
    
    def do_create_element(self, url):
        pipeline = Gst.parse_launch(self.launch_str)
        self.appsrc = pipeline.get_by_name('src')
        threading.Thread(target=self.push_frames, daemon=True).start()
        return pipeline
    
    def push_frames(self):
        try:
            font_large = ImageFont.truetype(FONT_PATH, 36)
            font_medium = ImageFont.truetype(FONT_PATH, 28)
            font_small = ImageFont.truetype(FONT_PATH, 20)
        except IOError:
            font_large = ImageFont.load_default()
            font_medium = ImageFont.load_default()
            font_small = ImageFont.load_default()
        
        while True:
            img = Image.new('RGB', (WIDTH, HEIGHT), 'black')
            draw = ImageDraw.Draw(img)
            
            with self.receiver.lock:
                cur = self.receiver.current_status['current_floor']
                tgt = self.receiver.current_status['target_floor']
                is_moving = self.receiver.current_status['is_moving']
            
            # エレベーター案内ディスプレイのレイアウト
            if is_moving and tgt:
                # 移動中: 現在階と行先階を表示
                header = "移動中"
                body = f"{cur} → {tgt}"
                
                # ヘッダー（移動中）
                bb_header = draw.textbbox((0,0), header, font=font_medium)
                draw.text(((WIDTH-bb_header[2])//2, 30), header, font=font_medium, fill='yellow')
                
                # メイン表示（現在階 → 行先階）
                bb_body = draw.textbbox((0,0), body, font=font_large)
                draw.text(((WIDTH-bb_body[2])//2, 100), body, font=font_large, fill='white')
                
                # 矢印アニメーション
                arrow_y = 160
                arrow_x = WIDTH // 2
                # 簡単な点滅効果
                if int(time.time() * 2) % 2:
                    draw.text((arrow_x - 10, arrow_y), "▶", font=font_medium, fill='green')
                
            else:
                # 停止中: 現在階のみ表示
                header = "現在階"
                body = cur
                
                # ヘッダー（現在階）
                bb_header = draw.textbbox((0,0), header, font=font_medium)
                draw.text(((WIDTH-bb_header[2])//2, 50), header, font=font_medium, fill='lightblue')
                
                # メイン表示（現在階）
                bb_body = draw.textbbox((0,0), body, font=font_large)
                draw.text(((WIDTH-bb_body[2])//2, 120), body, font=font_large, fill='white')
            
            # USB接続状態表示
            connection_status = "USB接続" if (self.receiver.usb_conn and self.receiver.usb_conn.is_open) else "USB切断"
            connection_color = 'green' if (self.receiver.usb_conn and self.receiver.usb_conn.is_open) else 'red'
            draw.text((10, 10), connection_status, font=font_small, fill=connection_color)
            
            # 日時表示
            now = datetime.now().strftime("%Y年%-m月%-d日 %H:%M:%S")
            bb_time = draw.textbbox((0,0), now, font=font_small)
            draw.text(((WIDTH-bb_time[2])//2, HEIGHT-40), now, font=font_small, fill='gray')
            
            # フレーム送信
            buf = pil_to_gst_buffer(img)
            if self.appsrc.emit('push-buffer', buf) != Gst.FlowReturn.OK:
                break
            time.sleep(1.0/FPS)

def signal_handler(signum, frame):
    logger.info(f"🛑 シグナル {signum} 受信、停止します")
    receiver.stop()
    sys.exit(0)

if __name__ == '__main__':
    import argparse
    
    # コマンドライン引数解析
    parser = argparse.ArgumentParser(description='SEC-3000H Elevator Display - USB Direct Connection')
    parser.add_argument('--no-rtsp', action='store_true', help='RTSPサーバーを起動しない')
    parser.add_argument('--usb-device', default='/dev/ttyACM0', help='USBデバイスパス')
    args = parser.parse_args()
    
    logger.info("🏢 SEC-3000H エレベーター案内ディスプレイ起動中...")
    logger.info("📱 USB直接通信版")
    logger.info(f"🔌 USBデバイス: {args.usb_device}")
    
    # USB受信システム初期化（デバイス指定）
    receiver = USBElevatorReceiver(usb_device=args.usb_device)
    
    usb_connected = receiver.start()
    if not usb_connected:
        logger.warning("⚠️ USB接続に失敗しましたが、スタンドアロンモードで継続します")
        logger.info("💡 RTSPサーバーのみ起動し、デモ表示を行います")
    
    # RTSPサーバー起動
    if not args.no_rtsp:
        Gst.init(None)
        server = GstRtspServer.RTSPServer.new()
        server.props.service = '8554'
        mount = server.get_mount_points()
        mount.add_factory('/elevator', USBElevatorDisplayFactory(receiver))
        server.attach(None)
        
        ip = get_local_ip()
        logger.info(f"✅ RTSPサーバー起動: rtsp://{ip}:8554/elevator")
    
    # シグナルハンドラー設定
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    logger.info("🎯 USB直接通信エレベーター案内ディスプレイ稼働中...")
    
    try:
        if not args.no_rtsp:
            GLib.MainLoop().run()
        else:
            # RTSPなしの場合は単純なループ
            while True:
                time.sleep(1)
    except KeyboardInterrupt:
        logger.info("🛑 キーボード割り込みを受信しました")
        receiver.stop()
        sys.exit(0)
