# ENQ 信号を RTSP 映像に変換する：Python で作るエレベーター映像監視システム

## はじめに

これまでの記事では、エレベーターと自動運転装置間の通信を模擬するための**ENQ 信号送信シミュレーター（PC 側）**、および**受信確認ツール（Raspberry Pi 側）**について紹介してきました。

本記事では、シリーズの第 3 弾として、**Raspberry Pi で受信した ENQ 信号の内容をリアルタイムに映像化し、RTSP で配信する監視システム**の構築方法を解説します。

このシステムでは、以下の 3 つの主要な処理を Python で実装しています：

- **ENQ 信号の受信処理**（PySerial + termios）
- **エレベーター状態の管理**（現在階・行先階・荷重・接続状態の更新）
- **映像の自動生成と RTSP 配信**（PIL + GStreamer + RTSP Server）

Raspberry Pi 上で本アプリケーションを起動することで、**監視室や他のクライアント端末から VLC プレーヤー等を用いて、エレベーターの状態をリアルタイム映像で確認できる**ようになります。

なお、本システムは**ENQ 受信のみに特化した受信専用設計**となっており、ACK や NAK などの応答は一切行いません。そのため、開発初期フェーズにおいても安定した動作が可能です。

本記事では、ENQ 信号から映像配信までをつなぐアーキテクチャ全体と、各処理の役割・構成について詳しく解説していきます。

---

## Raspberry Pi のセットアップ

Raspberry Pi をクリーンインストール直後の状態から本システムを動作させるには、**GStreamer による RTSP 配信機能**や、**Pillow を用いた画像生成処理**、および**日本語フォントの描画**に必要なパッケージを追加でインストールする必要があります。

以下の手順に従って、必要なシステムパッケージと Python ライブラリを導入してください。

### インストール手順

```bash
# システムパッケージの更新
sudo apt update

# Python3 および GObject ライブラリ
sudo apt install python3-pip python3-gi python3-gi-cairo gir1.2-gtk-3.0 -y

# GStreamer 基本プラグイン（映像生成に必要）
sudo apt install gstreamer1.0-tools gstreamer1.0-plugins-base gstreamer1.0-plugins-good -y

# GStreamer 拡張プラグイン（H.264 など）
sudo apt install gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly gstreamer1.0-libav -y

# RTSP サーバ関連ライブラリ
sudo apt install libgstrtspserver-1.0-dev gir1.2-gst-rtsp-server-1.0 -y

# 日本語フォント（映像に表示するテキストのため）
sudo apt install fonts-ipafont fonts-ipafont-gothic fonts-ipafont-mincho -y

# Python パッケージ（ENQ受信・画像生成に使用）
pip3 install pyserial pillow
```

---

## プログラムの起動方法

本システムでは `elevator_enq_rtsp_receiver.py` を実行することで、ENQ 信号をリアルタイム映像に変換し、RTSP でストリーム配信を行います。

```bash
python3 elevator_enq_rtsp_receiver.py
```

シリアルポートや解像度、ログ出力などはオプション引数でカスタマイズ可能です。

---

## 利用可能なオプション一覧

| オプション     | 説明                                     | 例                    |
| -------------- | ---------------------------------------- | --------------------- |
| `--port`       | 使用するシリアルポートの指定             | `--port /dev/ttyUSB1` |
| `--rtsp-port`  | RTSP サーバのポート番号を変更            | `--rtsp-port 8555`    |
| `--resolution` | 出力映像の解像度を指定（1080/720/480）   | `--resolution 1080`   |
| `--debug`      | 詳細なログを標準出力に表示（デバッグ用） | `--debug`             |
| `--test-ports` | 利用可能なシリアルポートを列挙して終了   | `--test-ports`        |

> `--resolution` を利用する派生版では、スクリプト内で定数を直接編集する代わりに、コマンドラインから動的に解像度指定が可能です。

---

## 起動パターンの例

| シナリオ                             | 実行コマンド例                                                                                    |
| ------------------------------------ | ------------------------------------------------------------------------------------------------- |
| `/dev/ttyUSB1` から 1080p 映像を配信 | `python3 elevator_enq_rtsp_receiver.py --port /dev/ttyUSB1 --resolution 1080`                     |
| 軽量配信（480p／ビットレート調整）   | `python3 elevator_enq_rtsp_receiver.py --resolution 480`<br>※ `x264enc bitrate=` をソース内で調整 |
| 詳細ログ付きで起動                   | `python3 elevator_enq_rtsp_receiver.py --debug`                                                   |

---

## VLC で映像を視聴する方法

1. VLC メディアプレーヤーを起動します。

2. メニューから「**メディア → ネットワークストリームを開く**」を選択。

3. アドレス欄に以下の URL を入力：

   ```
   rtsp://<RaspberryPiのIPアドレス>:8554/elevator
   ```

4. 再生ボタンを押すと、**現在階・行先階・荷重・通信ログ**などがリアルタイム映像として表示されます。

---

## システム構成図

本システムは、ENQ 信号を送信する PC（シミュレーター）と、受信・映像配信を担当する Raspberry Pi 4B の 2 台構成で動作します。

```plaintext
┌────────────┐               ┌────────────────────┐
│   PC側     │               │ Raspberry Pi 4B     │
│（送信機） │               │（受信 + 映像配信）│
├────────────┤               ├────────────────────┤
│ Python送信│──── RS422 ───▶│ PySerial + termios │
│  ENQ発行  │               │ 16バイト固定受信   │
└────────────┘               ├────────────────────┤
                             │ ENQ解析 + 状態管理 │
                             ├────────────────────┤
                             │ PIL画像生成         │
                             ├────────────────────┤
                             │ GStreamer + RTSP配信│
                             └────────────────────┘
```

クライアント側では、VLC メディアプレーヤーなどの RTSP 対応ソフトから
`rtsp://<RaspberryPiのIP>:8554/elevator` にアクセスすることで、
**リアルタイムにエレベーターの状態を視覚的に監視**することが可能です。

---

## 主な処理フロー

ENQ 信号の受信から映像生成、RTSP 配信までの一連の流れは以下の通りです。

### 1. ENQ 信号の受信

- Raspberry Pi の指定シリアルポート（例：`/dev/ttyUSB0`）で、16 バイト長の ENQ 電文を受信
- PySerial + termios を用いて `VMIN=1` / `VTIME=1` の設定で 1 バイトずつ読み取り
- バッファから有効な ENQ 電文を抽出・解析

### 2. エレベーター状態の更新

- データ番号に応じて、**現在階**・**行先階**・**荷重**を状態管理クラスに反映
- 通信ログ（最大 10 件）も併せて更新し、映像上に表示できる形式で保持

### 3. 映像の生成

- Pillow（PIL）を用いて画像を動的に描画
- 背景画像上に現在状態をテキストとして合成し、レイアウトやフォントも調整可能

### 4. RTSP による映像配信

- GStreamer を用いて画像を H.264 エンコードし、RTSP ストリームとして配信
- `x264enc` + `rtph264pay` による圧縮で、低ビットレート環境でも視認可能な映像を維持

この仕組みにより、ENQ 通信で得られたデータをリアルタイムで可視化し、
**現場監視・トラブル解析・遠隔支援などの用途に応用可能**な基盤を構築できます。

---

## まとめ

本記事では、Raspberry Pi 上で ENQ 信号を受信し、リアルタイム映像として RTSP 配信する
**エレベーター状態可視化システム**の構築手順を紹介しました。

本システムの特徴は以下の通りです：

- **ENQ 受信に特化した安定したアーキテクチャ**
- **状態情報（階数・荷重など）を映像として直感的に表示**
- **RTSP 配信により遠隔地からのモニタリングにも対応**

本記事で紹介したプログラムは、これまでの送信・受信モジュールとあわせて
以下の GitHub リポジトリで公開しています：

[GitHub - elevator-enq-simulator](https://github.com/isec-promotion/elevator-enq-simulator)

※ご質問やフィードバックがありましたら、GitHub の Issue または[問い合わせフォーム](/contact)経由でお気軽にお寄せください。
