#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Elevator Dashboard RTSP Server
  - RS-422シリアルで受信した現在階・行先階情報
    と現在時刻を重ねて RTSP で配信
"""

import serial
import time
import threading
import logging
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
SERIAL_PORT = '/dev/ttyUSB0'
BAUDRATE = 9600
FONT_PATH = "/usr/share/fonts/truetype/ipafont-mincho/ipam.ttf"

# ── ログ設定 ─────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ── エレベーター受信クラス ───────────────────
class AutoModeElevatorReceiver:
    """RS-422 で受信したメッセージを解析し、current_status を更新"""
    def __init__(self, port: str, baudrate: int):
        self.port = port
        self.baudrate = baudrate
        self.serial_conn: Optional[serial.Serial] = None
        self.running = False
        self.current_status = {
            'current_floor': '1F',
            'target_floor': None,
            'last_communication': None
        }
        self.lock = threading.Lock()

    def connect(self) -> bool:
        try:
            self.serial_conn = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_EVEN,
                stopbits=serial.STOPBITS_ONE,
                timeout=1
            )
            logger.info(f"✅ シリアルポート {self.port} 接続")
            return True
        except Exception as e:
            logger.error(f"❌ シリアル接続エラー: {e}")
            return False

    def parse_message(self, data: bytes) -> Optional[Dict[str, Any]]:
        # 最低長チェック、先頭 ENQ
        if len(data) < 16 or data[0] != 0x05:
            return None
        try:
            station = data[1:5].decode('ascii')
            data_num = int(data[6:10].decode('ascii'), 16)
            data_value = int(data[10:14].decode('ascii'), 16)
        except Exception:
            return None
        return {'data_num': data_num, 'data_value': data_value}

    def update_status(self, parsed: Dict[str, Any]):
        num = parsed['data_num']
        val = parsed['data_value']
        floor = "B1F" if val == 0xFFFF else f"{val}F"
        with self.lock:
            if num == 0x0001:  # 現在階数
                self.current_status['current_floor'] = floor
            elif num == 0x0002:  # 行先階
                self.current_status['target_floor'] = floor
            self.current_status['last_communication'] = datetime.now()

    def listen(self):
        logger.info("🎧 シリアル受信開始...")
        while self.running:
            if self.serial_conn and self.serial_conn.in_waiting:
                data = self.serial_conn.read(self.serial_conn.in_waiting)
                parsed = self.parse_message(data)
                if parsed:
                    self.update_status(parsed)
            time.sleep(0.05)

    def start(self):
        if not self.connect():
            sys.exit(1)
        self.running = True
        threading.Thread(target=self.listen, daemon=True).start()

    def stop(self):
        self.running = False
        if self.serial_conn and self.serial_conn.is_open:
            self.serial_conn.close()
        logger.info("🛑 シリアル受信停止")


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

class AppSrcFactory(GstRtspServer.RTSPMediaFactory):
    def __init__(self, receiver: AutoModeElevatorReceiver):
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
            font = ImageFont.truetype(FONT_PATH, 28)
        except IOError:
            font = ImageFont.load_default()

        while True:
            # 新規画像
            img = Image.new('RGB', (WIDTH, HEIGHT), 'black')
            draw = ImageDraw.Draw(img)

            # ステータス取得
            with self.receiver.lock:
                cur = self.receiver.current_status['current_floor']
                tgt = self.receiver.current_status['target_floor']

            # 描画するテキスト
            if tgt and tgt != cur:
                header = "現在階　　　行先階"
                body   = f"{cur}　⇒　{tgt}"
            else:
                header = "現在階"
                body   = cur

            # ヘッダー
            bb = draw.textbbox((0,0), header, font=font)
            draw.text(((WIDTH-bb[2])//2, 10), header, font=font, fill='white')
            # ボディ
            bb2 = draw.textbbox((0,0), body, font=font)
            draw.text(((WIDTH-bb2[2])//2, 10 + bb[3] + 5), body, font=font, fill='white')

            # 時刻
            now = datetime.now().strftime("%Y年%-m月%-d日 %H:%M:%S")
            bb3 = draw.textbbox((0,0), now, font=font)
            draw.text(((WIDTH-bb3[2])//2, HEIGHT - bb3[3] - 10), now, font=font, fill='white')

            # フレーム送出
            buf = pil_to_gst_buffer(img)
            ret = self.appsrc.emit('push-buffer', buf)
            if ret != Gst.FlowReturn.OK:
                break
            time.sleep(1.0 / FPS)

def signal_handler(signum, frame):
    logger.info(f"🛑 シグナル {signum} 受信、停止します")
    receiver.stop()
    sys.exit(0)

if __name__ == '__main__':
    # GStreamer 初期化
    Gst.init(None)

    # シリアル受信開始
    receiver = AutoModeElevatorReceiver(SERIAL_PORT, BAUDRATE)
    receiver.start()

    # RTSP サーバー構築
    server = GstRtspServer.RTSPServer.new()
    server.props.service = '8554'
    mount = server.get_mount_points()
    mount.add_factory('/elevator', AppSrcFactory(receiver))
    server.attach(None)

    # シグナルハンドラ
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    ip = get_local_ip()
    logger.info(f"✅ RTSP サーバー起動: rtsp://{ip}:8554/elevator")
    GLib.MainLoop().run()
