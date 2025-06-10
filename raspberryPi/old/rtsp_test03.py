#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GStreamer RTSP サーバー版ストリーミングテスト
・5秒間隔で動的画像を生成
・GStreamer の multifilesrc で最新画像を検知
・RTSP サーバーをポート 8554 で待ち受け
"""

import time
import logging
import socket
import threading
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont

import gi
gi.require_version('Gst', '1.0')
gi.require_version('GstRtspServer', '1.0')
from gi.repository import Gst, GstRtspServer, GObject

# ─── ログ設定 ─────────────────────────────
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def get_local_ip():
    """ローカル IP アドレスを取得"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "127.0.0.1"

def create_dynamic_image():
    """5秒ごとに更新する動的画像を作成"""
    img = Image.new('RGB', (1920, 1080), '#b2ffff')
    draw = ImageDraw.Draw(img)
    try:
        fL = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 200)
        fM = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 100)
        fS = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 80)
    except IOError:
        fL = fM = fS = ImageFont.load_default()

    # メインテキスト
    txt = "RTSP TEST"
    bb = draw.textbbox((0,0), txt, font=fL)
    x = (1920 - (bb[2]-bb[0]))//2
    y = (1080 - (bb[3]-bb[1]))//2 - 150
    draw.text((x, y), txt, fill='#000', font=fL)

    # 日付・時刻
    now = datetime.now()
    ds = now.strftime("%Y/%m/%d")
    ts = now.strftime("%H:%M:%S")

    bb = draw.textbbox((0,0), ds, font=fM)
    draw.text(((1920-(bb[2]-bb[0]))//2, y+250), ds, fill='#333', font=fM)
    bb = draw.textbbox((0,0), ts, font=fM)
    draw.text(((1920-(bb[2]-bb[0]))//2, y+370), ts, fill='#333', font=fM)

    # 更新情報
    info = "duration: 5s"
    bb = draw.textbbox((0,0), info, font=fS)
    draw.text(((1920-(bb[2]-bb[0]))//2, y+500), info, fill='#888', font=fS)

    img.save('/tmp/rtsp_test.jpg', 'JPEG', quality=95)
    logger.info(f"📸 画像更新: {now.strftime('%H:%M:%S')}")

def update_image_continuously():
    """バックグラウンドで5秒ごとに画像更新"""
    while True:
        try:
            create_dynamic_image()
        except Exception as e:
            logger.error(f"❌ 画像更新エラー: {e}")
        time.sleep(5)

class ImageFactory(GstRtspServer.RTSPMediaFactory):
    """multifilesrc を使って動的画像を配信するファクトリ"""
    def __init__(self):
        super().__init__()
        # JPEG を 1/5 fps (＝5秒に1フレーム) で読み込む設定
        caps = 'image/jpeg,framerate=1/5'
        self.launch_str = (
            f'( multifilesrc location=/tmp/rtsp_test.jpg loop=true caps="{caps}" ! '
            'jpegdec ! videoconvert ! '
            'x264enc tune=zerolatency bitrate=2000 speed-preset=ultrafast ! '
            'rtph264pay name=pay0 pt=96 config-interval=1 )'
        )
        self.set_shared(True)

    def do_create_element(self, url):
        return Gst.parse_launch(self.launch_str)

def start_rtsp_server():
    """GStreamer RTSP サーバー起動"""
    Gst.init(None)
    server = GstRtspServer.RTSPServer.new()
    server.props.service = "8554"
    mount = server.get_mount_points()
    mount.add_factory("/test", ImageFactory())
    server.attach(None)
    ip = get_local_ip()
    logger.info(f"✅ RTSP サーバー起動: rtsp://{ip}:8554/test")
    GObject.MainLoop().run()

if __name__ == '__main__':
    # ① 初回画像生成 ② 更新スレッド起動 ③ RTSP サーバー起動
    create_dynamic_image()
    threading.Thread(target=update_image_continuously, daemon=True).start()
    start_rtsp_server()
