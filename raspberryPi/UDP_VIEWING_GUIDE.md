# UDP ストリーミング視聴ガイド

## VLC で UDP ストリーミングを視聴する方法

### 方法 1: ネットワークストリームを開く

1. VLC を起動
2. **メディア** → **ネットワークストリームを開く** (Ctrl+N)
3. ネットワーク URL に以下を入力:
   ```
   udp://@:8556
   ```
   または
   ```
   udp://192.168.40.239:8556
   ```
4. **再生**をクリック

### 方法 2: コマンドラインから起動

```bash
vlc udp://@:8556
```

### 方法 3: SDP ファイルを使用

1. 以下の内容で SDP ファイル（stream.sdp）を作成:
   ```
   v=0
   o=- 0 0 IN IP4 192.168.40.239
   s=Test Stream
   c=IN IP4 192.168.40.239
   t=0 0
   m=video 8556 RTP/AVP 96
   a=rtpmap:96 H264/90000
   ```
2. VLC で SDP ファイルを開く

## トラブルシューティング

### UDP が見れない場合の対処法

1. **ファイアウォール確認**

   ```bash
   sudo ufw status
   sudo ufw allow 8556/udp
   ```

2. **ポート確認**

   ```bash
   netstat -un | grep 8556
   ```

3. **VLC のログ確認**
   - VLC → ツール → メッセージ でエラーログを確認

### より確実な方法: HTTP ストリーミング

UDP が動作しない場合は、HTTP ストリーミング版を使用してください。
