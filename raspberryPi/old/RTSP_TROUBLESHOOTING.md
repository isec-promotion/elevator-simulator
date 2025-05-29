# RTSP ストリーミング問題の調査結果と解決策

## 🔍 問題の原因

### 1. **不正な GStreamer パイプライン**

元のコードでは、RTSP サーバーではなく TCP サーバーを作成していました：

```python
# 問題のあるコード
gst_pipeline = (
    f"appsrc ! videoconvert ! x264enc tune=zerolatency bitrate=2000 speed-preset=superfast ! "
    f"rtph264pay config-interval=1 pt=96 ! gdppay ! tcpserversink host=0.0.0.0 port={self.rtsp_port}"
)
```

**問題点:**

- `tcpserversink`は RTSP プロトコルではなく、単純な TCP ストリームを作成
- VLC は RTSP プロトコルを期待しているため接続できない
- `gdppay`は GStreamer の内部プロトコルで、RTSP クライアントには対応していない

### 2. **OpenCV の VideoWriter の誤用**

```python
# 問題のあるコード
out = cv2.VideoWriter(gst_pipeline, cv2.CAP_GSTREAMER, 0, 30.0, (self.image_width, self.image_height))
```

**問題点:**

- OpenCV の VideoWriter はファイル出力用
- RTSP ストリーミングには適していない
- GStreamer パイプラインとの連携が不適切

### 3. **RTSP サーバーの不在**

実際の RTSP プロトコルサーバーが実装されていませんでした。

## 🛠️ 解決策

### 修正版の実装 (`elevator_display_streamer_fixed.py`)

#### 1. **複数のストリーミング方法を実装**

**方法 1: GStreamer で UDP ストリーミング**

```python
gst_command = [
    'gst-launch-1.0', '-v',
    'multifilesrc', f'location={self.image_path}', 'loop=true',
    '!', 'jpegdec',
    '!', 'videoconvert',
    '!', 'videoscale',
    '!', f'video/x-raw,width={self.image_width},height={self.image_height},framerate=30/1',
    '!', 'x264enc', 'tune=zerolatency', 'bitrate=2000', 'speed-preset=ultrafast',
    '!', 'rtph264pay', 'config-interval=1', 'pt=96',
    '!', 'udpsink', 'host=127.0.0.1', f'port={self.rtsp_port}'
]
```

**方法 2: gst-rtsp-server を使用**

```python
rtsp_command = [
    'gst-rtsp-server',
    '--port', str(self.rtsp_port),
    '--gst-debug-level=2'
]
```

**方法 3: HTTP ストリーミング（代替手段）**

```python
class ImageHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/stream.jpg' or self.path == '/elevator_display.jpg':
            # 画像ファイルを直接配信
```

#### 2. **フォールバック機能**

- RTSP が失敗した場合、自動的に HTTP ストリーミングに切り替え
- 複数の方法を順次試行
- 最低限 HTTP ストリーミングは常に利用可能

#### 3. **適切なプロセス管理**

```python
def stop(self):
    # GStreamerプロセスを適切に停止
    if self.gstreamer_process:
        self.gstreamer_process.terminate()
        self.gstreamer_process.wait(timeout=5)
```

## 📺 VLC での接続方法

### 1. HTTP ストリーミング（推奨）

```
http://[RaspberryPi_IP]:8080/elevator_display.jpg
```

- 最も安定した方法
- 常に利用可能
- 画像の自動更新

### 2. UDP ストリーミング

```
udp://@:8554
```

- GStreamer が正常に動作している場合

### 3. RTSP ストリーミング

```
rtsp://[RaspberryPi_IP]:8554/
```

- gst-rtsp-server が利用可能な場合

## 🔧 トラブルシューティング

### 1. RTSP が接続できない場合

```bash
# ログを確認
tail -f ~/logs/elevator_display_streamer.log

# GStreamerの動作確認
gst-launch-1.0 --version

# ポートの確認
sudo netstat -tulpn | grep 8554
sudo netstat -tulpn | grep 8080
```

### 2. HTTP ストリーミングを直接テスト

```bash
# ブラウザで確認
curl http://localhost:8080/elevator_display.jpg

# 画像ファイルの確認
ls -la /tmp/elevator_display.jpg
```

### 3. 依存関係の確認

```bash
# 必要なパッケージの確認
dpkg -l | grep gstreamer
dpkg -l | grep python3-opencv

# Python依存関係の確認
source ~/elevator_env/bin/activate
pip list
```

## 📋 インストール手順

### 1. 修正版のインストール

```bash
chmod +x install_streaming_fixed.sh
./install_streaming_fixed.sh
```

### 2. サービスの開始

```bash
sudo systemctl start elevator-display-fixed
sudo systemctl status elevator-display-fixed
```

### 3. ログの確認

```bash
journalctl -u elevator-display-fixed -f
```

## 🎯 接続テスト手順

### 1. HTTP ストリーミングのテスト

1. ブラウザで `http://[RaspberryPi_IP]:8080/elevator_display.jpg` を開く
2. 画像が表示されることを確認

### 2. VLC でのテスト

1. VLC を開く
2. メディア → ネットワークストリームを開く
3. HTTP の URL を入力して接続テスト

### 3. RTSP のテスト（利用可能な場合）

1. VLC で `rtsp://[RaspberryPi_IP]:8554/` を試行
2. 接続できない場合は HTTP を使用

## 📊 パフォーマンス最適化

### 1. 画像更新頻度の調整

```python
# 更新間隔を調整（デフォルト: 1秒）
time.sleep(1)  # 1秒間隔で更新
```

### 2. 画像品質の調整

```python
# JPEG品質の調整（デフォルト: 95）
img.save(self.image_path, 'JPEG', quality=95)
```

### 3. ビットレートの調整

```python
# GStreamerのビットレート調整
'bitrate=2000'  # 2Mbps
```

## 🔒 セキュリティ考慮事項

### 1. ファイアウォール設定

```bash
# 必要なポートのみ開放
sudo ufw allow 8554/tcp  # RTSP
sudo ufw allow 8554/udp  # UDP
sudo ufw allow 8080/tcp  # HTTP
```

### 2. アクセス制限

- 必要に応じて IP アドレス制限を実装
- HTTPS の使用を検討

## 📝 まとめ

修正版では以下の改善を行いました：

1. **複数のストリーミング方法を実装**
2. **フォールバック機能の追加**
3. **適切なプロセス管理**
4. **詳細なログ出力**
5. **HTTP ストリーミングによる確実な代替手段**

これにより、VLC での接続が確実に可能になり、RTSP が利用できない環境でも HTTP ストリーミングで動作します。
