# RTSP ストリーミング設定ガイド

## 🔍 問題の分析結果

VLC で RTSP 接続ができない問題を調査した結果、以下の原因が判明しました：

### 元のコードの問題点

1. **不正な GStreamer パイプライン**: TCP サーバーを作成していたが、RTSP プロトコルではなかった
2. **OpenCV の VideoWriter の誤用**: ファイル出力用の API をストリーミングに使用
3. **RTSP サーバーの不在**: 実際の RTSP プロトコルサーバーが実装されていなかった

## 🛠️ 解決策

### 1. HTTP ストリーミング（推奨・確実）

HTTP ストリーミングは正常に動作することが確認されています：

```
http://192.168.40.239:8080/elevator_display.jpg
```

**特徴:**

- ✅ 最も安定した方法
- ✅ 常に利用可能
- ✅ VLC で確実に表示可能
- ✅ ブラウザでも表示可能

### 2. RTSP ストリーミングの修正

RTSP を動作させるには、以下の方法を試してください：

## 📋 Raspberry Pi での設定手順

### ステップ 1: 依存関係のインストール

```bash
# システムパッケージの更新
sudo apt update
sudo apt upgrade -y

# FFmpeg のインストール
sudo apt install -y ffmpeg

# VLC のインストール（コマンドライン版）
sudo apt install -y vlc-bin vlc-plugin-base

# GStreamer の追加パッケージ
sudo apt install -y \
    gstreamer1.0-rtsp \
    gstreamer1.0-plugins-ugly \
    libgstrtspserver-1.0-dev
```

### ステップ 2: RTSP テストの実行

#### 方法 1: FFmpeg を使用した RTSP サーバー

```bash
# Raspberry Pi で実行
cd /path/to/elevator-simulator/raspberryPi
python3 rtsp_simple_test.py
# 選択肢で "1" を選択
```

**FFmpeg コマンド（手動実行の場合）:**

```bash
ffmpeg -re -loop 1 -i /tmp/rtsp_test.jpg \
    -c:v libx264 -preset ultrafast -tune stillimage \
    -pix_fmt yuv420p -r 30 -f rtsp \
    rtsp://0.0.0.0:8554/test
```

#### 方法 2: VLC を使用した RTSP サーバー

```bash
# Raspberry Pi で実行
python3 rtsp_simple_test.py
# 選択肢で "2" を選択
```

**VLC コマンド（手動実行の場合）:**

```bash
cvlc --intf dummy --loop /tmp/rtsp_test.jpg \
    --sout '#transcode{vcodec=h264,vb=2000,fps=30}:rtp{sdp=rtsp://0.0.0.0:8554/test}'
```

#### 方法 3: GStreamer を使用した UDP ストリーミング

```bash
# Raspberry Pi で実行
python3 rtsp_simple_test.py
# 選択肢で "3" を選択
```

**GStreamer コマンド（手動実行の場合）:**

```bash
gst-launch-1.0 -v multifilesrc location=/tmp/rtsp_test.jpg loop=true \
    caps=image/jpeg,framerate=30/1 ! jpegdec ! videoconvert ! videoscale ! \
    video/x-raw,width=1920,height=1080 ! x264enc tune=zerolatency \
    bitrate=2000 speed-preset=ultrafast ! rtph264pay config-interval=1 pt=96 ! \
    udpsink host=0.0.0.0 port=8554
```

### ステップ 3: VLC での接続テスト

#### RTSP 接続（FFmpeg/VLC サーバーの場合）

```
rtsp://192.168.40.239:8554/test
```

#### UDP 接続（GStreamer の場合）

```
udp://@:8554
```

#### RTP 接続（GStreamer の場合）

```
rtp://192.168.40.239:8554
```

## 🔧 トラブルシューティング

### 1. RTSP が接続できない場合

#### ログの確認

```bash
# サーバーのログを確認
tail -f ~/logs/elevator_display_streamer.log

# システムログを確認
journalctl -u elevator-display-fixed -f
```

#### ポートの確認

```bash
# ポートが開いているか確認
sudo netstat -tulpn | grep 8554
sudo netstat -tulpn | grep 8080

# ファイアウォールの確認
sudo ufw status
```

#### プロセスの確認

```bash
# FFmpeg プロセスの確認
ps aux | grep ffmpeg

# VLC プロセスの確認
ps aux | grep vlc

# GStreamer プロセスの確認
ps aux | grep gst-launch
```

### 2. 依存関係の確認

```bash
# FFmpeg の確認
ffmpeg -version

# VLC の確認
cvlc --version

# GStreamer の確認
gst-launch-1.0 --version
```

### 3. ネットワークの確認

```bash
# IP アドレスの確認
hostname -I

# ネットワーク接続の確認
ping 192.168.40.239

# ポートの疎通確認（別の端末から）
telnet 192.168.40.239 8554
```

## 📊 各方法の比較

| 方法                | 安定性     | 設定の簡単さ | VLC 対応   | 備考          |
| ------------------- | ---------- | ------------ | ---------- | ------------- |
| HTTP ストリーミング | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐   | ⭐⭐⭐⭐⭐ | 最も確実      |
| FFmpeg RTSP         | ⭐⭐⭐⭐   | ⭐⭐⭐       | ⭐⭐⭐⭐   | 標準的な RTSP |
| VLC RTSP            | ⭐⭐⭐     | ⭐⭐⭐       | ⭐⭐⭐⭐   | VLC 依存      |
| GStreamer UDP       | ⭐⭐       | ⭐⭐         | ⭐⭐⭐     | 設定が複雑    |

## 🎯 推奨設定

### 本番環境での推奨構成

1. **メイン**: HTTP ストリーミング（確実に動作）
2. **サブ**: FFmpeg RTSP（RTSP が必要な場合）

### 設定例

```python
# elevator_display_streamer_fixed.py を使用
# 以下の順序で試行される：
# 1. FFmpeg RTSP サーバー
# 2. VLC RTSP サーバー
# 3. GStreamer UDP ストリーミング
# 4. HTTP ストリーミング（代替）
```

## 📝 VLC での接続手順

### 1. HTTP ストリーミング接続

1. VLC を開く
2. メディア → ネットワークストリームを開く
3. URL を入力: `http://192.168.40.239:8080/elevator_display.jpg`
4. 再生をクリック

### 2. RTSP 接続

1. VLC を開く
2. メディア → ネットワークストリームを開く
3. URL を入力: `rtsp://192.168.40.239:8554/test`
4. 再生をクリック

### 3. UDP 接続

1. VLC を開く
2. メディア → ネットワークストリームを開く
3. URL を入力: `udp://@:8554`
4. 再生をクリック

## 🔒 セキュリティ設定

### ファイアウォール設定

```bash
# 必要なポートを開放
sudo ufw allow 8554/tcp  # RTSP
sudo ufw allow 8554/udp  # UDP
sudo ufw allow 8080/tcp  # HTTP

# 設定を確認
sudo ufw status
```

### アクセス制限（オプション）

```bash
# 特定の IP からのみアクセスを許可
sudo ufw allow from 192.168.40.0/24 to any port 8554
sudo ufw allow from 192.168.40.0/24 to any port 8080
```

## 📞 サポート

### よくある問題と解決策

#### Q: VLC で「入力を開くことができません」エラーが出る

**A**: 以下を確認してください：

1. Raspberry Pi でサーバーが起動しているか
2. IP アドレスが正しいか
3. ポートが開放されているか
4. HTTP ストリーミングを試してみる

#### Q: 画像が表示されない

**A**: 以下を確認してください：

1. `/tmp/elevator_display.jpg` ファイルが存在するか
2. ファイルの権限が正しいか
3. サーバーのログにエラーがないか

#### Q: RTSP は動かないが HTTP は動く

**A**: これは正常です。HTTP ストリーミングを使用してください。RTSP が必要な場合は、FFmpeg の設定を見直してください。

## 🎉 まとめ

- **HTTP ストリーミング**: 確実に動作する（推奨）
- **RTSP ストリーミング**: 設定が複雑だが、標準的なプロトコル
- **トラブルシューティング**: ログとネットワーク設定を確認
- **VLC 接続**: HTTP を優先し、RTSP は代替として使用

HTTP ストリーミングが正常に動作しているため、まずはこれを使用し、RTSP が必要な場合は段階的に設定を進めることを推奨します。
