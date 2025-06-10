# エレベーター信号スヌーピング＆RTSP 映像配信システム

SEC-3000H 仕様準拠のエレベーター・自動運転装置間シリアル信号をスヌーピングして、エレベーター状態を RTSP 映像で配信するシステムです。

## システム構成

```
[backend-cli]                    [COM27]                    [raspberryPi]
エレベーター                      ↓                         Raspberry Pi
シミュレーター          ←→ シリアル信号スヌーピング ←→        RTSP映像配信
                                                           ↓
                                                      [VLC等で視聴]
```

## ファイル構成

### backend-cli

- `elevator_serial_simulator.py` - エレベーター・自動運転装置間シリアル信号シミュレーター

### raspberryPi

- `elevator_rtsp_snooper.py` - シリアル信号スヌーピング＆RTSP 映像配信システム

## 機能

### 1. エレベーターシミュレーター（backend-cli）

- SEC-3000H 仕様準拠の ENQ/ACK 信号を送信
- エレベーター（局番号: 0002）と自動運転装置（局番号: 0001）の両方をシミュレート
- 自動移動シナリオ実行：
  - 1F → 3F → B1F → 5F → 1F の循環
  - 各移動に 8〜15 秒の移動時間
  - 荷重のランダム変更

### 2. Raspberry Pi スヌーピングシステム

- COM27 のシリアル信号をリアルタイム監視
- ENQ/ACK メッセージの解析・表示
- エレベーター状態の追跡：
  - 現在階数
  - 行先階
  - 荷重
  - 移動状態
  - 扉状態

### 3. RTSP 映像配信

- エレベーター状態を映像化
- 停止中：「現在階: 1F」
- 移動中：「1F ⇒ 3F」
- 日時付きで配信
- 通信ログ表示

## 使用方法

### 1. 必要な依存関係のインストール

#### backend-cli（Windows）

```bash
cd backend-cli
pip install pyserial
```

#### raspberryPi（Linux）

```bash
cd raspberryPi
sudo apt update
sudo apt install -y python3-gi python3-gi-cairo gir1.2-gtk-3.0 gir1.2-gstreamer-1.0 gir1.2-gst-plugins-base-1.0 gir1.2-gst-rtsp-server-1.0
sudo apt install -y gstreamer1.0-plugins-base gstreamer1.0-plugins-good gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly gstreamer1.0-libav
sudo apt install -y fonts-ipafont-mincho
pip3 install pyserial pillow
```

### 2. システム起動

#### Step 1: エレベーターシミュレーター起動（Windows）

```bash
cd backend-cli
python elevator_serial_simulator.py --port COM27
```

出力例：

```
2025年05月30日 14:20:00 - INFO - 🏢 エレベーター・自動運転装置シリアル信号シミュレーター起動
2025年05月30日 14:20:00 - INFO - 📡 シリアルポート: COM27
2025年05月30日 14:20:00 - INFO - ✅ シリアルポート COM27 接続成功
2025年05月30日 14:20:00 - INFO - 🚀 エレベーター・自動運転装置シミュレーション開始
```

#### Step 2: Raspberry Pi スヌーピングシステム起動

```bash
cd raspberryPi
python3 elevator_rtsp_snooper.py --port COM27
```

出力例：

```
2025年05月30日 14:20:10 - INFO - 🏢 エレベーター信号スヌーピング＆RTSP映像配信システム起動
2025年05月30日 14:20:10 - INFO - ✅ シリアル接続成功
2025年05月30日 14:20:10 - INFO - ✅ RTSP配信開始: rtsp://192.168.1.100:8554/elevator
2025年05月30日 14:20:10 - INFO - 📱 VLCなどで上記URLを開いて映像を確認してください
```

### 3. RTSP 映像視聴

VLC メディアプレイヤーで以下の URL を開く：

```
rtsp://[Raspberry PiのIPアドレス]:8554/elevator
```

例：`rtsp://192.168.1.100:8554/elevator`

## 映像表示内容

### 停止中の表示

```
┌─────────────────────────────────┐
│    エレベーター監視システム        │
│    2025年05月30日 14:20:30       │
│                                │
│  ┌─────────────────────────┐    │
│  │      現在階: 1F          │    │
│  └─────────────────────────┘    │
│                                │
│    荷重: 250kg                 │
│    扉状態: 閉扉                │
│    最終更新: 14:20:30          │
│                                │
│  通信ログ:                     │
│  [14:20:28] ENQ: 現在階数: 1F   │
│  [14:20:29] ACK: 自動運転装置   │
│  [14:20:30] ENQ: 行先階: なし   │
└─────────────────────────────────┘
```

### 移動中の表示

```
┌─────────────────────────────────┐
│    エレベーター監視システム        │
│    2025年05月30日 14:21:15       │
│                                │
│  ┌─────────────────────────┐    │
│  │      1F ⇒ 3F            │    │
│  └─────────────────────────┘    │
│                                │
│    荷重: 450kg                 │
│    扉状態: 閉扉                │
│    最終更新: 14:21:15          │
│                                │
│  通信ログ:                     │
│  [14:21:13] ENQ: 階数設定: 3F   │
│  [14:21:14] ACK: エレベーター   │
│  [14:21:15] ENQ: 現在階数: 1F   │
└─────────────────────────────────┘
```

## シリアル信号仕様

### ENQ メッセージ（16 バイト）

```
05H + 局番号(4桁) + W + データ番号(4桁HEX) + データ値(4桁HEX) + チェックサム(2桁HEX)
```

例：

- 現在階数 1F: `05 0001 W 0001 0001 XX`
- 行先階 3F: `05 0001 W 0002 0003 XX`
- 荷重 250kg: `05 0001 W 0003 00FA XX`

### ACK メッセージ（5 バイト）

```
06H + 局番号(4桁)
```

例：

- エレベーター応答: `06 0002`
- 自動運転装置応答: `06 0001`

## データ番号定義

| データ番号 | 内容     | 送信方向                    |
| ---------- | -------- | --------------------------- |
| 0001       | 現在階数 | エレベーター → 自動運転装置 |
| 0002       | 行先階   | エレベーター → 自動運転装置 |
| 0003       | 荷重     | エレベーター → 自動運転装置 |
| 0010       | 階数設定 | 自動運転装置 → エレベーター |
| 0011       | 扉制御   | 自動運転装置 → エレベーター |

## 階数データ形式

| 階数 | データ値 |
| ---- | -------- |
| B1F  | FFFF     |
| 1F   | 0001     |
| 2F   | 0002     |
| 3F   | 0003     |
| ...  | ...      |

## トラブルシューティング

### 1. シリアルポート接続エラー

```
❌ シリアルポートエラー: [Errno 2] could not open port COM27
```

**解決方法：**

- COM27 ポートが存在するか確認
- 他のプログラムがポートを使用していないか確認
- ポート番号を変更：`--port COM28`

### 2. RTSP 配信エラー

```
❌ RTSPサーバー起動エラー: ...
```

**解決方法：**

- GStreamer がインストールされているか確認
- ポート 8554 が使用可能か確認
- ポート番号を変更：`--rtsp-port 8555`

### 3. 映像が表示されない

**解決方法：**

- VLC で「メディア」→「ネットワークストリームを開く」
- RTSP の URL を正確に入力
- ファイアウォール設定を確認
- ネットワーク接続を確認

### 4. 日本語フォントが表示されない

**解決方法：**

```bash
# Linux
sudo apt install fonts-ipafont-mincho

# Windows
# システムにMS Gothic等の日本語フォントがインストールされているか確認
```

## コマンドライン オプション

### elevator_serial_simulator.py

```bash
python elevator_serial_simulator.py [オプション]

オプション:
  --port PORT    シリアルポート (デフォルト: COM27)
```

### elevator_rtsp_snooper.py

```bash
python3 elevator_rtsp_snooper.py [オプション]

オプション:
  --port PORT         シリアルポート (デフォルト: COM27)
  --rtsp-port PORT    RTSPポート番号 (デフォルト: 8554)
```

## システム要件

### backend-cli（Windows）

- Python 3.7+
- pyserial
- Windows 10/11

### raspberryPi（Linux）

- Python 3.7+
- GStreamer 1.0+
- PyGObject
- PIL (Pillow)
- pyserial
- Raspberry Pi OS または Ubuntu

## ライセンス

このプロジェクトは MIT ライセンスの下で公開されています。

## 更新履歴

- v1.0.0 (2025/05/30) - 初回リリース
  - SEC-3000H 仕様準拠シリアル信号シミュレーター
  - シリアル信号スヌーピング機能
  - RTSP 映像配信機能
  - 日本語対応映像表示
