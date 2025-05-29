#!/usr/bin/env node
/**
 * SEC-3000H Elevator Auto Pilot CLI
 * シリアル通信専用エレベーター自動操縦プログラム
 */

import { SerialPort } from "serialport";

// 設定
const SERIAL_PORT = "COM27"; // Windowsの場合
// const SERIAL_PORT = "/dev/ttyUSB0"; // Linuxの場合

const SERIAL_CONFIG = {
  baudRate: 9600,
  dataBits: 8 as const,
  parity: "even" as const,
  stopBits: 1 as const,
};

// SEC-3000H データ番号定義
enum DataNumbers {
  CURRENT_FLOOR = 0x0001, // 現在階数
  TARGET_FLOOR = 0x0002, // 行先階
  LOAD_WEIGHT = 0x0003, // 荷重
  FLOOR_SETTING = 0x0010, // 階数設定
  DOOR_CONTROL = 0x0011, // 扉制御
}

// 扉制御コマンド
enum DoorCommands {
  STOP = 0x0000, // 停止
  OPEN = 0x0001, // 開扉
  CLOSE = 0x0002, // 閉扉
}

// エレベーター状態
interface ElevatorState {
  currentFloor: string;
  targetFloor: string | null;
  loadWeight: number;
  isMoving: boolean;
  doorStatus: "open" | "closed" | "opening" | "closing" | "unknown";
}

// 自動運転シーケンス
const AUTO_SEQUENCE = ["B1F", "1F", "2F", "3F", "4F", "5F"];

class ElevatorAutoPilot {
  private serialPort: SerialPort | null = null;
  private state: ElevatorState;
  private sequenceIndex = 0;
  private isRunning = false;
  private statusBroadcastTimer: NodeJS.Timeout | null = null;
  private operationTimer: NodeJS.Timeout | null = null;

  constructor() {
    this.state = {
      currentFloor: "1F",
      targetFloor: null,
      loadWeight: 0,
      isMoving: false,
      doorStatus: "unknown",
    };
  }

  /**
   * 初期化
   */
  async initialize(): Promise<void> {
    console.log("🚀 SEC-3000H Elevator Auto Pilot CLI 起動中...");
    console.log("📡 シリアルポート設定:", SERIAL_PORT, SERIAL_CONFIG);
    console.log("🎭 疑似モード: 自動運転内部完結型");

    try {
      await this.connectSerial();
      console.log("✅ 初期化完了");
    } catch (error) {
      console.warn("⚠️ シリアルポート接続失敗、疑似モードで継続:", error);
      this.serialPort = null;
      console.log("✅ 疑似モード初期化完了");
    }
  }

  /**
   * シリアルポート接続
   */
  private async connectSerial(): Promise<void> {
    return new Promise((resolve, reject) => {
      this.serialPort = new SerialPort({
        path: SERIAL_PORT,
        ...SERIAL_CONFIG,
      });

      this.serialPort.on("open", () => {
        console.log(`✅ シリアルポート ${SERIAL_PORT} 接続成功`);
        resolve();
      });

      this.serialPort.on("data", (data) => {
        this.handleReceivedData(data);
      });

      this.serialPort.on("error", (error) => {
        console.error("❌ シリアルポートエラー:", error);
        reject(error);
      });

      this.serialPort.on("close", () => {
        console.log("📡 シリアルポート切断");
      });
    });
  }

  /**
   * 受信データ処理
   */
  private handleReceivedData(data: Buffer): void {
    try {
      if (data.length < 16 || data[0] !== 0x05) {
        return; // 無効なデータ
      }

      // メッセージ解析
      const station = data.subarray(1, 5).toString("ascii");
      const command = String.fromCharCode(data[5]);
      const dataNumStr = data.subarray(6, 10).toString("ascii");
      const dataValueStr = data.subarray(10, 14).toString("ascii");
      const checksum = data.subarray(14, 16).toString("ascii");

      const dataNum = parseInt(dataNumStr, 16);
      const dataValue = parseInt(dataValueStr, 16);

      const timestamp = new Date().toLocaleString("ja-JP", {
        timeZone: "Asia/Tokyo",
      });

      // データ内容を解釈
      let description = "";
      switch (dataNum) {
        case DataNumbers.CURRENT_FLOOR:
          const currentFloor = dataValue === 0xffff ? "B1F" : `${dataValue}F`;
          this.state.currentFloor = currentFloor;
          description = `現在階数: ${currentFloor}`;
          break;
        case DataNumbers.TARGET_FLOOR:
          const targetFloor = dataValue === 0xffff ? "B1F" : `${dataValue}F`;
          this.state.targetFloor = targetFloor;
          description = `行先階: ${targetFloor}`;
          break;
        case DataNumbers.LOAD_WEIGHT:
          this.state.loadWeight = dataValue;
          description = `荷重: ${dataValue}kg`;
          break;
        default:
          description = `データ番号: ${dataNum.toString(16).padStart(4, "0")}`;
      }

      console.log(
        `[${timestamp}] 📨 受信: 局番号:${station} CMD:${command} ${description} データ:${dataValueStr} チェックサム:${checksum}`
      );

      // ACK応答送信
      this.sendAckResponse(station);
    } catch (error) {
      console.error("❌ 受信データ処理エラー:", error);
    }
  }

  /**
   * ACK応答送信
   */
  private sendAckResponse(station: string): void {
    if (!this.serialPort?.isOpen) return;

    const response = Buffer.alloc(5);
    response[0] = 0x06; // ACK
    response.write(station, 1, "ascii");

    this.serialPort.write(response, (error) => {
      if (error) {
        console.error("❌ ACK送信エラー:", error);
      } else {
        const timestamp = new Date().toLocaleString("ja-JP", {
          timeZone: "Asia/Tokyo",
        });
        console.log(
          `[${timestamp}] 📤 送信: ACK(06) 局番号:${station} | HEX: ${response
            .toString("hex")
            .toUpperCase()}`
        );
      }
    });
  }

  /**
   * チェックサム計算
   */
  private calculateChecksum(data: Buffer): string {
    const total = data.reduce((sum, byte) => sum + byte, 0);
    const lowerByte = total & 0xff;
    const upperByte = (total >> 8) & 0xff;
    const checksum = (lowerByte + upperByte) & 0xff;
    return checksum.toString(16).toUpperCase().padStart(2, "0");
  }

  /**
   * コマンド送信（疑似モード対応）
   */
  private async sendCommand(
    targetStation: string,
    dataNum: number,
    dataValue: number
  ): Promise<boolean> {
    // メッセージ作成
    const message = Buffer.alloc(16);
    let offset = 0;

    // ENQ
    message[offset++] = 0x05;

    // 局番号 (4桁ASCII)
    message.write(targetStation, offset, "ascii");
    offset += 4;

    // コマンド (W)
    message[offset++] = 0x57; // 'W'

    // データ番号 (4桁ASCII)
    const dataNumStr = dataNum.toString(16).toUpperCase().padStart(4, "0");
    message.write(dataNumStr, offset, "ascii");
    offset += 4;

    // データ (4桁HEX ASCII)
    const dataValueStr = dataValue.toString(16).toUpperCase().padStart(4, "0");
    message.write(dataValueStr, offset, "ascii");
    offset += 4;

    // チェックサム計算 (ENQ以外)
    const checksumData = message.subarray(1, offset);
    const checksum = this.calculateChecksum(checksumData);
    message.write(checksum, offset, "ascii");

    const timestamp = new Date().toLocaleString("ja-JP", {
      timeZone: "Asia/Tokyo",
    });

    // データ内容を解釈
    let description = "";
    switch (dataNum) {
      case DataNumbers.FLOOR_SETTING:
        const floor = dataValue === 0xffff ? "B1F" : `${dataValue}F`;
        description = `階数設定: ${floor}`;
        break;
      case DataNumbers.DOOR_CONTROL:
        if (dataValue === DoorCommands.OPEN) description = "扉制御: 開扉";
        else if (dataValue === DoorCommands.CLOSE) description = "扉制御: 閉扉";
        else description = "扉制御: 停止";
        break;
      default:
        description = `データ番号: ${dataNumStr}`;
    }

    if (this.serialPort?.isOpen) {
      // 実際のシリアル通信
      return new Promise((resolve) => {
        const timeout = setTimeout(() => {
          console.error("❌ コマンド送信タイムアウト");
          resolve(false);
        }, 3000);

        this.serialPort!.write(message, (error) => {
          if (error) {
            clearTimeout(timeout);
            console.error("❌ コマンド送信エラー:", error);
            resolve(false);
            return;
          }

          console.log(
            `[${timestamp}] 📤 送信: ENQ(05) 局番号:${targetStation} CMD:W ${description} データ:${dataValueStr} チェックサム:${checksum}`
          );

          // ACK待ち
          const responseHandler = (data: Buffer) => {
            clearTimeout(timeout);
            this.serialPort!.removeListener("data", responseHandler);

            if (data.length >= 1 && data[0] === 0x06) {
              console.log(`[${timestamp}] ✅ ACK受信`);
              resolve(true);
            } else {
              console.error("❌ 無効な応答:", data.toString("hex"));
              resolve(false);
            }
          };

          this.serialPort!.on("data", responseHandler);
        });
      });
    } else {
      // 疑似モード（内部完結）
      console.log(
        `[${timestamp}] 📤 疑似送信: ENQ(05) 局番号:${targetStation} CMD:W ${description} データ:${dataValueStr} チェックサム:${checksum}`
      );

      // 疑似的な処理遅延
      await this.sleep(100);

      console.log(`[${timestamp}] ✅ 疑似ACK受信`);
      return true;
    }
  }

  /**
   * 階数設定
   */
  private async setFloor(floor: string): Promise<boolean> {
    const floorValue =
      floor === "B1F" ? 0xffff : parseInt(floor.replace("F", ""));
    return this.sendCommand("0001", DataNumbers.FLOOR_SETTING, floorValue);
  }

  /**
   * 扉制御
   */
  private async controlDoor(
    action: "open" | "close" | "stop"
  ): Promise<boolean> {
    let command: DoorCommands;
    switch (action) {
      case "open":
        command = DoorCommands.OPEN;
        break;
      case "close":
        command = DoorCommands.CLOSE;
        break;
      case "stop":
        command = DoorCommands.STOP;
        break;
    }
    return this.sendCommand("0001", DataNumbers.DOOR_CONTROL, command);
  }

  /**
   * 自動運転開始
   */
  async startAutoPilot(): Promise<void> {
    if (this.isRunning) {
      console.log("⚠️ 自動運転は既に実行中です");
      return;
    }

    console.log("🚀 自動運転開始");
    console.log("🏢 運転シーケンス:", AUTO_SEQUENCE.join(" → "));
    this.isRunning = true;

    // 初期位置を1Fに設定
    console.log("🏢 初期位置を1Fに設定中...");
    await this.setFloor("1F");
    await this.sleep(2000);

    // 自動運転ループ開始
    this.executeAutoPilotLoop();
  }

  /**
   * 自動運転ループ
   */
  private async executeAutoPilotLoop(): Promise<void> {
    if (!this.isRunning) return;

    try {
      const targetFloor = AUTO_SEQUENCE[this.sequenceIndex];

      console.log(
        `\n🎯 次の目標階: ${targetFloor} (現在: ${this.state.currentFloor})`
      );

      // 1. 扉を閉める
      console.log("🚪 扉を閉めています...");
      await this.controlDoor("close");
      await this.sleep(3000);

      // 2. 目標階に移動
      console.log(`🚀 ${targetFloor}に移動中...`);
      this.state.isMoving = true;
      await this.setFloor(targetFloor);
      await this.sleep(5000); // 移動時間

      // 3. 到着
      console.log(`✅ ${targetFloor}に到着`);
      this.state.currentFloor = targetFloor;
      this.state.isMoving = false;

      // 4. 扉を開ける
      console.log("🚪 扉を開いています...");
      await this.controlDoor("open");
      await this.sleep(3000);

      // 5. 乗客の出入り時間
      console.log("👥 乗客の出入り中...");
      await this.sleep(5000);

      // 次の階へ
      this.sequenceIndex = (this.sequenceIndex + 1) % AUTO_SEQUENCE.length;

      // 次のサイクルをスケジュール
      this.operationTimer = setTimeout(() => {
        this.executeAutoPilotLoop();
      }, 2000);
    } catch (error) {
      console.error("❌ 自動運転エラー:", error);
      // エラー時は少し待ってから再試行
      this.operationTimer = setTimeout(() => {
        this.executeAutoPilotLoop();
      }, 5000);
    }
  }

  /**
   * 自動運転停止
   */
  stopAutoPilot(): void {
    console.log("🛑 自動運転停止");
    this.isRunning = false;

    if (this.operationTimer) {
      clearTimeout(this.operationTimer);
      this.operationTimer = null;
    }
  }

  /**
   * 状態表示
   */
  private displayStatus(): void {
    const timestamp = new Date().toLocaleString("ja-JP", {
      timeZone: "Asia/Tokyo",
    });

    console.log(`\n[${timestamp}] 📊 エレベーター状態`);
    console.log(`現在階: ${this.state.currentFloor}`);
    console.log(`行先階: ${this.state.targetFloor || "-"}`);
    console.log(`荷重: ${this.state.loadWeight}kg`);
    console.log(`移動中: ${this.state.isMoving ? "はい" : "いいえ"}`);
    console.log(`扉状態: ${this.state.doorStatus}`);
  }

  /**
   * 定期状態表示開始
   */
  startStatusDisplay(): void {
    this.statusBroadcastTimer = setInterval(() => {
      this.displayStatus();
    }, 30000); // 30秒間隔
  }

  /**
   * 終了処理
   */
  async shutdown(): Promise<void> {
    console.log("🛑 システム終了中...");

    this.stopAutoPilot();

    if (this.statusBroadcastTimer) {
      clearInterval(this.statusBroadcastTimer);
    }

    if (this.serialPort?.isOpen) {
      await new Promise<void>((resolve) => {
        this.serialPort!.close(() => {
          console.log("📡 シリアルポート切断完了");
          resolve();
        });
      });
    }

    console.log("✅ システム終了完了");
  }

  /**
   * スリープ
   */
  private sleep(ms: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }
}

// メイン処理
async function main() {
  const autoPilot = new ElevatorAutoPilot();

  // シグナルハンドラー設定
  process.on("SIGINT", async () => {
    console.log("\n🛑 Ctrl+C が押されました");
    await autoPilot.shutdown();
    process.exit(0);
  });

  process.on("SIGTERM", async () => {
    console.log("\n🛑 SIGTERM を受信しました");
    await autoPilot.shutdown();
    process.exit(0);
  });

  try {
    // 初期化
    await autoPilot.initialize();

    // 定期状態表示開始
    autoPilot.startStatusDisplay();

    // 自動運転開始
    await autoPilot.startAutoPilot();

    console.log("\n✅ システム稼働中 (Ctrl+C で終了)");
  } catch (error) {
    console.error("❌ システムエラー:", error);
    await autoPilot.shutdown();
    process.exit(1);
  }
}

// プログラム開始
main().catch((error) => {
  console.error("❌ 予期しないエラー:", error);
  process.exit(1);
});
