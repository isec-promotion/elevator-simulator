# 動的映像 RTSP 配信ガイド

## 概要

このガイドでは、`rtsp_video_test.py`を使用して動的映像を RTSP 配信する方法を説明します。静止画像ではなく、リアルタイムで生成される動的映像を配信することで、VLC での接続安定性を検証できます。

## 特徴

- **動的映像生成**: 静止画像ではなく、リアルタイムでアニメーション付き映像を生成
- **1280x720 解像度**: Raspberry Pi 4B に適した解像度
- **3 つの品質設定**: 標準品質、軽量版、最軽量版から選択可能
- **Raspberry Pi 最適化**: 低負荷で安定動作するよう調整済み

## 必要な環境

### システム要件

- Raspberry Pi 4B (推奨)
- Python 3.7 以上
- FFmpeg
- 十分なメモリ (最低 2GB 推奨)

### 依存関係のインストール

```bash
# Python依存関係をインストール
pip install -r requirements_video.txt

# FFmpegがインストールされていない場合
sudo apt update
sudo apt install ffmpeg
```

## 使用方法

### 1. スクリプトの実行

```bash
cd raspberryPi
python3 rtsp_video_test.py
```

### 2. 品質設定の選択

スクリプト実行時に以下から選択できます：

#### オプション 1: 標準品質 (30fps, 2Mbps)

- **フレームレート**: 30fps
- **ビットレート**: 2Mbps
- **用途**: 高品質な映像が必要な場合
- **負荷**: 中程度

#### オプション 2: 軽量版 (20fps, 1.5Mbps)

- **フレームレート**: 20fps
- **ビットレート**: 1.5Mbps
- **用途**: バランスの取れた設定
- **負荷**: 軽量

#### オプション 3: 最軽量版 (15fps, CRF28)

- **フレームレート**: 15fps
- **品質**: CRF28 (可変ビットレート)
- **用途**: 最低限のリソースで動作
- **負荷**: 最軽量

### 3. VLC での視聴

スクリプトが開始されると、以下のような RTSP URL が表示されます：

```
rtsp://192.168.1.100:8554/video        # 標準品質
rtsp://192.168.1.100:8554/video_light  # 軽量版
rtsp://192.168.1.100:8554/simple       # 最軽量版
```

VLC で「メディア」→「ネットワークストリームを開く」から上記 URL を入力してください。

## 映像の内容

生成される映像には以下の要素が含まれます：

- **背景色**: 時間に応じて変化するグラデーション
- **タイトル**: "RTSP VIDEO TEST"
- **解像度情報**: 現在の解像度とフレームレート
- **フレームカウンター**: リアルタイムで更新
- **現在時刻**: 秒単位で更新
- **動くアニメーション**: 円と四角形が軌道を描いて移動

## トラブルシューティング

### 接続が 5 秒で切断される場合

1. **最軽量版を試す**: オプション 3 を選択
2. **システムリソースを確認**: `htop`で CPU/メモリ使用率をチェック
3. **ネットワーク設定を確認**: ファイアウォールやルーター設定

### FFmpeg エラーが発生する場合

```bash
# FFmpegのバージョンを確認
ffmpeg -version

# 必要に応じて最新版をインストール
sudo apt update
sudo apt install ffmpeg
```

### Python 依存関係エラー

```bash
# 仮想環境を作成（推奨）
python3 -m venv venv
source venv/bin/activate

# 依存関係を再インストール
pip install --upgrade pip
pip install -r requirements_video.txt
```

## パフォーマンス最適化

### Raspberry Pi 4B での推奨設定

1. **GPU 分割の調整**:

   ```bash
   sudo raspi-config
   # Advanced Options → Memory Split → 128
   ```

2. **CPU ガバナーの設定**:

   ```bash
   echo performance | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor
   ```

3. **スワップファイルの無効化**（SD カード保護）:
   ```bash
   sudo dphys-swapfile swapoff
   sudo dphys-swapfile uninstall
   ```

## 静止画像版との比較

| 項目         | 静止画像版 | 動的映像版                   |
| ------------ | ---------- | ---------------------------- |
| CPU 使用率   | 低         | 中〜高                       |
| メモリ使用量 | 低         | 中                           |
| 接続安定性   | 5 秒で切断 | 改善される可能性             |
| 視覚的確認   | 困難       | 容易                         |
| デバッグ     | 困難       | フレームカウンターで確認可能 |

## ログの確認

スクリプト実行中は詳細なログが出力されます：

```
2025-05-28 17:20:00,123 - INFO - 📹 映像生成開始: 1280x720 @ 30fps
2025-05-28 17:20:00,456 - INFO - ✅ FFmpeg 動的映像RTSPサーバーが開始されました
2025-05-28 17:20:00,789 - INFO - 📺 RTSP URL: rtsp://192.168.1.100:8554/video
```

## 注意事項

- **長時間実行**: 連続実行時はシステム温度に注意
- **ネットワーク帯域**: 複数クライアント接続時は帯域幅を考慮
- **ストレージ**: ログファイルのサイズに注意

## 次のステップ

このテストで接続が安定した場合、実際のアプリケーション（エレベーター表示など）に応用できます。設定値を参考に、本番環境での最適化を行ってください。
