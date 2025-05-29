#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# RTSP 時刻表示サーバーのテスト

import gi
gi.require_version('Gst', '1.0')
gi.require_version('GstRtspServer', '1.0')
from gi.repository import Gst, GstRtspServer, GLib

import socket
import threading
import time
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont

# ── 配信設定 ───────────────────────────────────
WIDTH, HEIGHT, FPS = 640, 360, 15

def get_local_ip():
    """ローカルIPアドレスを取得"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return '127.0.0.1'

def pil_to_gst_buffer(img: Image.Image):
    """PIL の RGB 画像 → Gst.Buffer"""
    data = img.tobytes()  # RGB24
    buf = Gst.Buffer.new_allocate(None, len(data), None)
    buf.fill(0, data)
    # duration だけ指定（タイムスタンプは do-timestamp=true に任せる）
    buf.duration = Gst.util_uint64_scale_int(1, Gst.SECOND, FPS)
    return buf

class AppSrcFactory(GstRtspServer.RTSPMediaFactory):
    def __init__(self):
        super().__init__()
        self.set_shared(True)
        # do-timestamp=true を追加
        self.launch_str = (
            '( appsrc name=src is-live=true block=true format=time '
            f' caps=video/x-raw,format=RGB,width={WIDTH},height={HEIGHT},framerate={FPS}/1 '
            ' do-timestamp=true '
            ' ! videoconvert '
            f' ! video/x-raw,format=I420,width={WIDTH},height={HEIGHT},framerate={FPS}/1 '
            ' ! x264enc tune=zerolatency bitrate=500 speed-preset=ultrafast '
            ' ! rtph264pay name=pay0 pt=96 config-interval=1 )'
        )

    def do_create_element(self, url):
        pipeline = Gst.parse_launch(self.launch_str)
        self.appsrc = pipeline.get_by_name('src')
        threading.Thread(target=self.push_frames, daemon=True).start()
        return pipeline

    def push_frames(self):
        """PIL で毎フレーム画像を描画→appsrc にプッシュ"""
        # 日本語対応フォントを指定
        font_path = "/usr/share/fonts/truetype/ipafont-mincho/ipam.ttf"
        try:
            font = ImageFont.truetype(font_path, 32)
        except IOError:
            font = ImageFont.load_default()

        while True:
            # 黒背景に中央揃えで時刻を描画
            img = Image.new('RGB', (WIDTH, HEIGHT), 'black')
            draw = ImageDraw.Draw(img)
            # 例：日本語年月日フォーマット
            now_text = datetime.now().strftime("2025年%-m月%-d日 %H:%M:%S")
            bb = draw.textbbox((0, 0), now_text, font=font)
            w, h = bb[2] - bb[0], bb[3] - bb[1]
            draw.text(((WIDTH - w)//2, (HEIGHT - h)//2), now_text, font=font, fill='white')

            buf = pil_to_gst_buffer(img)
            ret = self.appsrc.emit('push-buffer', buf)
            if ret != Gst.FlowReturn.OK:
                break

            time.sleep(1.0 / FPS)

def main():
    Gst.init(None)
    server = GstRtspServer.RTSPServer.new()
    server.props.service = '8554'
    mount = server.get_mount_points()
    mount.add_factory('/test', AppSrcFactory())
    server.attach(None)

    ip = get_local_ip()
    print(f'✅ RTSP サーバー起動: rtsp://{ip}:8554/test')
    GLib.MainLoop().run()

if __name__ == '__main__':
    main()
