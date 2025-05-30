# SEC-3000H エレベーターシミュレーター

SEC-3000H エレベーター制御システムのシミュレーターです。RS422 通信プロトコルを使用してエレベーターとの通信をシミュレートし、Web ベースの UI で操作・監視が可能です。

## 🏗️ システム構成

```
elevator-simulator/
├── backend/                 # Node.js + TypeScript バックエンド
│   ├── src/
│   │   ├── index.ts        # メインサーバー
│   │   ├── elevator.ts     # エレベーター制御クラス
│   │   └── websocket.ts    # WebSocket通信ハンドラー
│   ├── package.json
│   └── tsconfig.json
├── frontend/               # React + TypeScript フロントエンド
│   ├── src/
│   │   ├── components/     # Reactコンポーネント
│   │   ├── App.tsx        # メインアプリケーション
│   │   └── main.tsx       # エントリーポイント
│   ├── package.json
│   ├── vite.config.ts
│   └── tsconfig.json
└── README.md
```

## 🚀 機能

### エレベーター制御

- **階数選択**: B1F〜10F の階数選択
- **扉制御**: 開扉・閉扉・停止操作
- **状態監視**: 現在階、行先階、扉状態、移動状態、荷重の監視

### 🤖 自動運転モード（NEW!）

- **完全自動運転**: 手動操作なしでエレベーターが自動運転
- **乗客シミュレーション**: 各階で 0〜10 人がランダムに出入り
- **荷重計算**: 1 人 60kg として自動計算（設定変更可能）
- **運転間隔設定**: 運転間隔やドア開放時間の調整
- **自動運転ログ**: 乗客の出入り履歴を詳細記録

### 通信機能

- **RS422 シミュレーション**: SEC-3000H 通信プロトコルの実装
- **リアルタイム通信**: WebSocket によるリアルタイム状態更新
- **通信ログ**: 送受信データの詳細ログ表示（16 進数＋人間可読形式）

### UI 機能

- **レスポンシブデザイン**: PC・タブレット・スマートフォン対応
- **リアルタイム更新**: 状態変化の即座な反映
- **視覚的フィードバック**: アニメーション・色分けによる状態表示
- **自動運転パネル**: 自動運転の制御・監視・設定

## 🛠️ 技術スタック

### バックエンド

- **Node.js** - JavaScript 実行環境
- **TypeScript** - 型安全な JavaScript
- **Hono** - Web フレームワーク
- **ws** - WebSocket 通信
- **serialport** - シリアル通信（RS422）

### フロントエンド

- **React** - UI ライブラリ
- **TypeScript** - 型安全な JavaScript
- **Vite** - 高速ビルドツール
- **CSS3** - スタイリング（グラデーション・アニメーション）

## 📋 セットアップ

### 前提条件

- Node.js 18.0.0 以上
- npm または yarn

### インストール

1. **プロジェクトのクローン**

```bash
git clone <repository-url>
cd elevator-simulator
```

2. **バックエンドのセットアップ**

```bash
cd backend
npm install
```

3. **フロントエンドのセットアップ**

```bash
cd ../frontend
npm install
```

### 開発環境での実行

1. **バックエンドサーバーの起動**

```bash
cd backend
npm run dev
```

サーバーは http://localhost:3000 で起動します。

2. **フロントエンドの起動**

```bash
cd frontend
npm run dev
```

フロントエンドは http://localhost:5173 で起動します。

### 本番環境でのビルド

1. **バックエンドのビルド**

```bash
cd backend
npm run build
npm start
```

2. **フロントエンドのビルド**

```bash
cd frontend
npm run build
npm run preview
```

## 🔧 設定

### シリアルポート設定

`backend/src/elevator.ts` でシリアルポートの設定を変更できます：

```typescript
/**
 * シリアルポートの設定
 * 実際の環境に応じて変更してください
 */
const SERIAL_PORT = "COM1"; // Windowsの場合
// const SERIAL_PORT = "/dev/ttyUSB0"; // Linuxの場合

this.config = {
  serialPort: SERIAL_PORT, // シリアルポートの設定
  baudRate: 9600,
  dataBits: 8,
  parity: "even",
  stopBits: 1,
  timeout: 3000,
  retryCount: 8,
};
```

#### エレベーター速度設定

`backend/src/elevator.ts` でエレベーター速度を変更できます：

```typescript
// エレベーター動作時間設定（ミリ秒）
export const ELEVATOR_TIMING = {
  FLOOR_MOVEMENT_TIME: 3000, // エレベーター移動時間（3秒）
  DOOR_OPERATION_TIME: 2000, // 扉開閉時間（2秒）
  COMMAND_RESPONSE_DELAY: 100, // コマンド応答遅延（0.1秒）
  // 高速モード用
  // FLOOR_MOVEMENT_TIME: 500, // 0.5秒
  // DOOR_OPERATION_TIME: 300, // 0.3秒
  // COMMAND_RESPONSE_DELAY: 10, // 0.01秒
} as const;
```

### WebSocket 設定

デフォルトでは以下のポートを使用します：

- バックエンド: 3000 番ポート
- WebSocket: 3000 番ポート（HTTP 同一ポート）
- フロントエンド: 5173 番ポート

## 📡 通信プロトコル

### SEC-3000H 通信仕様

- **通信方式**: RS422
- **ボーレート**: 9600bps
- **データビット**: 8bit
- **パリティ**: Even
- **ストップビット**: 1bit

### コマンド形式

```
ENQ + 局番号(4桁) + コマンド(1文字) + データ番号(4桁) + データ(4桁HEX) + チェックサム(2桁HEX)
```

### 主要コマンド

- `0x0001`: 現在階取得
- `0x0002`: 行先階取得
- `0x0003`: 荷重取得
- `0x0010`: 階数設定
- `0x0011`: 扉制御

## 🎮 使用方法

### 通常モード

1. **システム起動**: バックエンドとフロントエンドを起動
2. **接続確認**: WebSocket 接続状態を確認
3. **階数選択**: 操作パネルで行先階を選択
4. **扉操作**: 開扉・閉扉ボタンで扉を制御
5. **状態監視**: リアルタイムで状態変化を監視
6. **ログ確認**: 通信ログで詳細な通信内容を確認

### 🤖 自動運転モード

#### 起動方法

```bash
# 自動運転モードでシステムを起動
npm run dev:auto
```

または個別に起動：

```bash
# バックエンド（自動運転モード）
cd backend
npm run dev:auto

# フロントエンド（自動運転モード）
cd frontend
npm run dev:auto
```

#### 使用手順

1. **自動運転モード起動**: `npm run dev:auto` でシステムを起動
2. **自動運転開始**: UI の自動運転パネルで「🚀 開始」ボタンをクリック
3. **自動運転監視**: エレベーターが自動で各階を巡回
4. **乗客出入り確認**: 各階で乗客がランダムに出入りする様子を監視
5. **設定変更**: 運転間隔や最大乗客数などを調整可能
6. **ログ確認**: 自動運転ログで乗客の出入り履歴を確認

#### 自動運転の特徴

- **完全自動**: 手動操作は無効化され、エレベーターが自動運転
- **乗客シミュレーション**: 各階停止時に 0〜10 人がランダムに出入り
- **荷重自動計算**: 1 人 60kg として荷重を自動計算・更新
- **循環運転**: B1F〜10F を順次巡回
- **リアルタイム表示**: 乗客数、荷重、運転状況をリアルタイム表示

#### Raspberry Pi での受信

```bash
# Raspberry Pi で自動運転モード用受信スクリプトを実行
cd raspberryPi
python3 auto_mode_receiver.py
```

このスクリプトは以下の機能を提供：

- RS422 通信の受信・解析
- 16 進数データと人間可読形式の両方でログ出力
- 自動運転時の乗客出入りシミュレーション
- 通信ログの詳細記録

## 🔍 トラブルシューティング

### 接続エラー

- シリアルポートの設定を確認
- ポート番号の重複をチェック
- デバイスドライバーの確認

#### RS422 USB コンバーターの設定

以下のように 5 線接続する。

- T/R+ ⇔ RXD+
- T/R- ⇔ RXD-
- RXD+ ⇔ T/R+
- RXD- ⇔ T/R-
- GND ⇔ GND

### WebSocket 接続エラー

- ファイアウォール設定の確認
- ポート番号の競合をチェック
- ブラウザのコンソールでエラー確認

### シミュレーションモード

実際のハードウェアが接続されていない場合、自動的にシミュレーションモードで動作します。

## 📝 ライセンス

MIT License

## 🤝 貢献

プルリクエストやイシューの報告を歓迎します。

## 📞 サポート

技術的な質問やサポートが必要な場合は、イシューを作成してください。

---

**開発者**: アイゼック株式会社
**バージョン**: 1.0.0  
**最終更新**: 2025 年 5 月 27 日
