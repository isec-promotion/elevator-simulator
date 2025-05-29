# RTSP 5 秒で途切れる問題の解決

## 🔍 問題の原因

VLC で RTSP 接続が 5 秒で途切れる問題は、静止画ストリーミングでよくある問題です。

### 主な原因

1. **静止画の無限ループ問題**

   - FFmpeg の `-loop 1` オプションで静止画を無限ループしているが、実際には有限の時間で終了する
   - デフォルトでは約 5 秒程度でストリームが終了してしまう

2. **キーフレーム設定の問題**

   - H.264 エンコーダのキーフレーム間隔が適切でない
   - VLC クライアントがストリームの継続性を認識できない

3. **ビットレート制御の問題**

   - 静止画では実際のビットレートが非常に低くなる
   - ストリームが「終了した」と判断される

4. **RTSP セッション管理の問題**
   - RTSP セッションのタイムアウト設定
   - クライアント・サーバー間のキープアライブが不十分

## 🛠️ 解決策

### 1. 動的画像更新（推奨）

**方法**: 画像を定期的に更新して「動画」として認識させる

```python
# rtsp_continuous_test.py の方法
def update_image_continuously():
    while True:
        create_dynamic_image()  # 時刻付き画像を生成
        time.sleep(1)  # 1秒ごとに更新
```

**効果**:

- ✅ ストリームが継続的に更新される
- ✅ VLC が「ライブストリーム」として認識
- ✅ 5 秒で途切れる問題を解決

### 2. FFmpeg パラメータの最適化

#### 連続 RTSP 用の設定

```bash
ffmpeg -re -f image2 -loop 1 -r 30 -i /tmp/rtsp_live.jpg \
    -c:v libx264 -preset ultrafast -tune stillimage \
    -pix_fmt yuv420p \
    -g 30 -keyint_min 30 -sc_threshold 0 \
    -b:v 2000k -maxrate 2000k -bufsize 4000k \
    -f rtsp -rtsp_transport tcp \
    rtsp://0.0.0.0:8554/live
```

**重要なパラメータ**:

- `-g 30`: キーフレーム間隔を 30 フレームに設定
- `-keyint_min 30`: 最小キーフレーム間隔
- `-sc_threshold 0`: シーンチェンジ検出を無効化
- `-rtsp_transport tcp`: TCP トランスポートを使用（より安定）

#### 動画形式用の設定

```bash
ffmpeg -f image2 -r 1 -i /tmp/rtsp_live.jpg \
    -c:v libx264 -preset ultrafast -tune stillimage \
    -pix_fmt yuv420p -r 30 \
    -g 60 -keyint_min 60 \
    -x264-params keyint=60:min-keyint=60:scenecut=-1 \
    -b:v 2000k -maxrate 2000k -bufsize 4000k \
    -f rtsp -rtsp_transport tcp \
    rtsp://0.0.0.0:8554/video
```

### 3. VLC サーバー設定の最適化

```bash
cvlc --intf dummy --loop --image-duration 1 /tmp/rtsp_live.jpg \
    --sout '#transcode{vcodec=h264,vb=2000,fps=30,keyint=60}:rtp{sdp=rtsp://0.0.0.0:8554/vlc}'
```

**重要なパラメータ**:

- `--image-duration 1`: 画像の表示時間を 1 秒に設定
- `keyint=60`: キーフレーム間隔を 60 フレームに設定

### 4. GStreamer 設定の最適化

```bash
gst-launch-1.0 -v multifilesrc location=/tmp/rtsp_live.jpg loop=true \
    caps=image/jpeg,framerate=30/1 ! jpegdec ! videoconvert ! videoscale ! \
    video/x-raw,width=1920,height=1080,framerate=30/1 ! \
    x264enc tune=zerolatency bitrate=2000 speed-preset=ultrafast key-int-max=60 ! \
    rtph264pay config-interval=1 pt=96 ! \
    udpsink host=0.0.0.0 port=8554 auto-multicast=true
```

## 📋 Raspberry Pi での実行手順

### ステップ 1: 連続ストリーミングテストの実行

```bash
# Raspberry Pi で実行
cd /path/to/elevator-simulator/raspberryPi
python3 rtsp_continuous_test.py
```

### ステップ 2: 方法の選択

```
1. FFmpeg 連続RTSP (推奨)
2. FFmpeg 動画形式RTSP
3. VLC 連続RTSP
4. GStreamer 連続UDP
```

**推奨**: 方法 1（FFmpeg 連続 RTSP）を選択

### ステップ 3: VLC での接続

```
rtsp://192.168.40.239:8554/live
```

### ステップ 4: 動作確認

- ✅ 画像に時刻が表示される
- ✅ 1 秒ごとに時刻が更新される
- ✅ 5 秒経っても映像が途切れない
- ✅ 長時間の連続再生が可能

## 🔧 トラブルシューティング

### 問題: まだ 5 秒で途切れる

**解決策**:

1. 画像更新スレッドが正常に動作しているか確認
2. FFmpeg のログを確認してエラーがないかチェック
3. VLC の設定で「ネットワークキャッシュ」を増やす

### 問題: 画像が更新されない

**解決策**:

1. `/tmp/rtsp_live.jpg` ファイルの権限を確認
2. Python スクリプトのログを確認
3. 画像更新スレッドのエラーログを確認

### 問題: CPU 使用率が高い

**解決策**:

1. 画像更新間隔を長くする（1 秒 →3 秒）
2. FFmpeg の `-preset` を `ultrafast` から `fast` に変更
3. 解像度を下げる（1920x1080→1280x720）

## 📊 各方法の比較

| 方法             | 安定性     | CPU 使用率 | 設定の簡単さ | 推奨度     |
| ---------------- | ---------- | ---------- | ------------ | ---------- |
| FFmpeg 連続 RTSP | ⭐⭐⭐⭐⭐ | ⭐⭐⭐     | ⭐⭐⭐⭐     | ⭐⭐⭐⭐⭐ |
| FFmpeg 動画形式  | ⭐⭐⭐⭐   | ⭐⭐⭐⭐   | ⭐⭐⭐       | ⭐⭐⭐⭐   |
| VLC 連続 RTSP    | ⭐⭐⭐     | ⭐⭐       | ⭐⭐⭐       | ⭐⭐⭐     |
| GStreamer UDP    | ⭐⭐       | ⭐⭐⭐     | ⭐⭐         | ⭐⭐       |

## 🎯 本番環境への適用

### elevator_display_streamer_fixed.py の修正

元のエレベーター表示システムに連続ストリーミング機能を適用する場合：

```python
def create_display_image(self):
    # 既存の画像生成コード
    # ...

    # 時刻情報を追加（デバッグ用）
    current_time = datetime.now().strftime("%H:%M:%S")
    time_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 40)
    draw.text((50, 50), current_time, fill='#333333', font=time_font)

    img.save(self.image_path, 'JPEG', quality=95)
```

### FFmpeg コマンドの修正

```python
def start_ffmpeg_rtsp_server(self):
    ffmpeg_cmd = [
        'ffmpeg', '-re', '-f', 'image2', '-loop', '1', '-r', '30',
        '-i', self.image_path,
        '-c:v', 'libx264', '-preset', 'ultrafast', '-tune', 'stillimage',
        '-pix_fmt', 'yuv420p',
        '-g', '30', '-keyint_min', '30', '-sc_threshold', '0',
        '-b:v', '2000k', '-maxrate', '2000k', '-bufsize', '4000k',
        '-f', 'rtsp', '-rtsp_transport', 'tcp',
        f'rtsp://0.0.0.0:{self.rtsp_port}/live'
    ]
```

## 🎉 まとめ

### 5 秒で途切れる問題の解決方法

1. **動的画像更新**: 画像を定期的に更新してライブストリームとして認識させる
2. **FFmpeg パラメータ最適化**: キーフレーム間隔とビットレート制御を適切に設定
3. **TCP トランスポート使用**: UDP より安定した TCP を使用
4. **連続ストリーミング**: 無限ループではなく、実際の連続ストリームを生成

### 推奨設定

- **方法**: FFmpeg 連続 RTSP
- **画像更新**: 1 秒間隔
- **解像度**: 1920x1080
- **ビットレート**: 2000kbps
- **トランスポート**: TCP

この設定により、VLC で安定した長時間の RTSP ストリーミングが可能になります。
