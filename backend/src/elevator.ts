import { SerialPort } from "serialport";

// 型定義
export interface ElevatorStatus {
  currentFloor: string | null;
  targetFloor: string | null;
  doorStatus: "open" | "closed" | "opening" | "closing" | "unknown";
  isMoving: boolean;
  loadWeight: number | null;
  connectionStatus: "connected" | "disconnected" | "error";
  lastCommunication: string | null;
}

export interface CommunicationLog {
  timestamp: string;
  direction: "send" | "receive" | "system";
  data: string;
  result: "success" | "error" | "timeout";
  message?: string;
}

export interface ElevatorConfig {
  serialPort: string;
  baudRate: number;
  dataBits: number;
  parity: "none" | "even" | "odd";
  stopBits: number;
  timeout: number;
  retryCount: number;
}

export interface CommandResult {
  success: boolean;
  data?: any;
  error?: string;
}

// エレベーターコマンド定義
export enum ElevatorCommands {
  CURRENT_FLOOR = 0x0001,
  TARGET_FLOOR = 0x0002,
  LOAD_WEIGHT = 0x0003,
  FLOOR_SETTING = 0x0010,
  DOOR_CONTROL = 0x0011,
}

export enum DoorControl {
  STOP = 0x0000,
  OPEN = 0x0001,
  CLOSE = 0x0002,
}

export class ElevatorController {
  private serialPort: SerialPort | null = null;
  private config: ElevatorConfig;
  private status: ElevatorStatus;
  private logs: CommunicationLog[] = [];
  private isInitialized = false;
  private reconnectTimer: NodeJS.Timeout | null = null;

  constructor() {
    this.config = {
      serialPort: "COM1", // デフォルト値、実際の環境に応じて変更
      baudRate: 9600,
      dataBits: 8,
      parity: "even",
      stopBits: 1,
      timeout: 3000,
      retryCount: 8,
    };

    this.status = {
      currentFloor: null,
      targetFloor: null,
      doorStatus: "unknown",
      isMoving: false,
      loadWeight: null,
      connectionStatus: "disconnected",
      lastCommunication: null,
    };
  }

  async initialize(): Promise<void> {
    try {
      console.log("🔧 Initializing Elevator Controller...");

      // シリアルポートの利用可能性をチェック
      const ports = await SerialPort.list();
      console.log(
        "📡 Available serial ports:",
        ports.map((p) => p.path)
      );

      // 設定されたポートが利用可能かチェック
      const targetPort = ports.find((p) => p.path === this.config.serialPort);
      if (!targetPort) {
        console.warn(
          `⚠️  Configured port ${this.config.serialPort} not found. Using simulation mode.`
        );
        this.status.connectionStatus = "disconnected";
        this.isInitialized = true;
        return;
      }

      await this.connectSerial();
      this.isInitialized = true;
      console.log("✅ Elevator Controller initialized successfully");
    } catch (error) {
      console.error("❌ Failed to initialize Elevator Controller:", error);
      this.status.connectionStatus = "error";
      this.isInitialized = true; // シミュレーションモードで続行
    }
  }

  private async connectSerial(): Promise<void> {
    try {
      if (this.serialPort?.isOpen) {
        await this.serialPort.close();
      }

      this.serialPort = new SerialPort({
        path: this.config.serialPort,
        baudRate: this.config.baudRate,
        dataBits: this.config.dataBits,
        parity: this.config.parity,
        stopBits: this.config.stopBits,
      });

      this.serialPort.on("open", () => {
        console.log(`✅ Serial port ${this.config.serialPort} opened`);
        this.status.connectionStatus = "connected";
        this.addLog("system", "Serial port opened", "success");
      });

      this.serialPort.on("data", (data) => {
        this.handleReceivedData(data);
      });

      this.serialPort.on("error", (error) => {
        console.error("❌ Serial port error:", error);
        this.status.connectionStatus = "error";
        this.addLog("system", `Serial error: ${error.message}`, "error");
        this.scheduleReconnect();
      });

      this.serialPort.on("close", () => {
        console.log("📡 Serial port closed");
        this.status.connectionStatus = "disconnected";
        this.addLog("system", "Serial port closed", "success");
      });
    } catch (error) {
      console.error("❌ Failed to connect serial port:", error);
      this.status.connectionStatus = "error";
      throw error;
    }
  }

  private scheduleReconnect(): void {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
    }

    this.reconnectTimer = setTimeout(async () => {
      console.log("🔄 Attempting to reconnect...");
      try {
        await this.connectSerial();
      } catch (error) {
        console.error("❌ Reconnection failed:", error);
        this.scheduleReconnect(); // 再試行
      }
    }, 5000);
  }

  private calculateChecksum(data: Buffer): number {
    const total = data.reduce((sum, byte) => sum + byte, 0);
    const lowerByte = total & 0xff;
    const upperByte = (total >> 8) & 0xff;
    return (lowerByte + upperByte) & 0xff;
  }

  private createWriteCommand(
    targetStation: number,
    command: number,
    data: number
  ): Buffer {
    const message = Buffer.alloc(16);
    let offset = 0;

    // ENQ
    message[offset++] = 0x05;

    // 局番号 (4桁ASCII)
    const stationStr = targetStation.toString().padStart(4, "0");
    message.write(stationStr, offset, "ascii");
    offset += 4;

    // コマンド (W)
    message[offset++] = 0x57; // 'W'

    // データ番号 (4桁ASCII)
    const commandStr = command.toString().padStart(4, "0");
    message.write(commandStr, offset, "ascii");
    offset += 4;

    // データ (4桁HEX ASCII)
    const dataStr = data.toString(16).toUpperCase().padStart(4, "0");
    message.write(dataStr, offset, "ascii");
    offset += 4;

    // チェックサム計算 (ENQ以外)
    const checksumData = message.subarray(1, offset);
    const checksum = this.calculateChecksum(checksumData);
    const checksumStr = checksum.toString(16).toUpperCase().padStart(2, "0");
    message.write(checksumStr, offset, "ascii");
    offset += 2;

    return message.subarray(0, offset);
  }

  private createResponse(targetStation: number, isAck: boolean = true): Buffer {
    const response = Buffer.alloc(6);
    let offset = 0;

    // ACK/NAK
    response[offset++] = isAck ? 0x06 : 0x15;

    // 局番号 (4桁ASCII)
    const stationStr = targetStation.toString().padStart(4, "0");
    response.write(stationStr, offset, "ascii");
    offset += 4;

    return response.subarray(0, offset);
  }

  private async sendCommand(
    targetStation: number,
    command: ElevatorCommands,
    data: number
  ): Promise<CommandResult> {
    if (!this.serialPort?.isOpen) {
      // シミュレーションモード
      console.log(
        `🎭 Simulation: Sending command ${command.toString(
          16
        )} with data ${data.toString(16)} to station ${targetStation}`
      );
      this.addLog(
        "send",
        `Simulation: ${command.toString(16)}:${data.toString(16)}`,
        "success"
      );
      return { success: true, data: { simulation: true } };
    }

    try {
      const message = this.createWriteCommand(targetStation, command, data);

      return new Promise((resolve) => {
        const timeout = setTimeout(() => {
          this.addLog("send", message.toString("hex"), "timeout");
          resolve({ success: false, error: "Timeout" });
        }, this.config.timeout);

        this.serialPort!.write(message, (error) => {
          if (error) {
            clearTimeout(timeout);
            this.addLog(
              "send",
              message.toString("hex"),
              "error",
              error.message
            );
            resolve({ success: false, error: error.message });
            return;
          }

          this.addLog("send", message.toString("hex"), "success");

          // 応答待ち
          const responseHandler = (data: Buffer) => {
            clearTimeout(timeout);
            this.serialPort!.removeListener("data", responseHandler);

            if (data.length >= 1) {
              if (data[0] === 0x06) {
                // ACK
                this.addLog(
                  "receive",
                  data.toString("hex"),
                  "success",
                  "ACK received"
                );
                resolve({ success: true, data: { response: "ACK" } });
              } else if (data[0] === 0x15) {
                // NAK
                this.addLog(
                  "receive",
                  data.toString("hex"),
                  "error",
                  "NAK received"
                );
                resolve({ success: false, error: "NAK received" });
              } else {
                this.addLog(
                  "receive",
                  data.toString("hex"),
                  "error",
                  "Unknown response"
                );
                resolve({ success: false, error: "Unknown response" });
              }
            } else {
              this.addLog(
                "receive",
                data.toString("hex"),
                "error",
                "Invalid response length"
              );
              resolve({ success: false, error: "Invalid response length" });
            }
          };

          this.serialPort!.on("data", responseHandler);
        });
      });
    } catch (error) {
      const errorMessage =
        error instanceof Error ? error.message : "Unknown error";
      this.addLog("send", "", "error", errorMessage);
      return { success: false, error: errorMessage };
    }
  }

  private handleReceivedData(data: Buffer): void {
    try {
      if (data.length < 10 || data[0] !== 0x05) {
        return; // 無効なデータ
      }

      // データ解析
      const stationStr = data.subarray(1, 5).toString("ascii");
      const command = String.fromCharCode(data[5]);
      const dataNumStr = data.subarray(6, 10).toString("ascii");
      const dataValueStr = data.subarray(10, 14).toString("ascii");

      const station = parseInt(stationStr);
      const dataNum = parseInt(dataNumStr);
      const dataValue = parseInt(dataValueStr, 16);

      console.log(
        `📨 Received: Station=${station}, Command=${command}, DataNum=${dataNum}, Data=${dataValue.toString(
          16
        )}`
      );

      // データ保存
      this.updateStatusFromReceived(dataNum, dataValue);

      // 正常応答送信
      const response = this.createResponse(1, true); // 自動運転装置として応答
      if (this.serialPort?.isOpen) {
        this.serialPort.write(response);
      }

      this.addLog("receive", data.toString("hex"), "success");
      this.status.lastCommunication = new Date().toISOString();
    } catch (error) {
      console.error("❌ Error processing received data:", error);
      this.addLog(
        "receive",
        data.toString("hex"),
        "error",
        error instanceof Error ? error.message : "Unknown error"
      );
    }
  }

  private updateStatusFromReceived(dataNum: number, dataValue: number): void {
    switch (dataNum) {
      case ElevatorCommands.CURRENT_FLOOR:
        this.status.currentFloor = this.decodeFloor(dataValue);
        break;
      case ElevatorCommands.TARGET_FLOOR:
        this.status.targetFloor = this.decodeFloor(dataValue);
        break;
      case ElevatorCommands.LOAD_WEIGHT:
        this.status.loadWeight = dataValue;
        break;
    }
  }

  private decodeFloor(floorData: number): string {
    if (floorData === 0xffff) {
      return "B1F";
    } else {
      return `${floorData}F`;
    }
  }

  private encodeFloor(floorStr: string): number {
    if (floorStr.toUpperCase() === "B1F") {
      return 0xffff;
    } else {
      const floorNum = parseInt(floorStr.replace(/F$/i, ""));
      return isNaN(floorNum) ? 1 : floorNum;
    }
  }

  private addLog(
    direction: "send" | "receive" | "system",
    data: string,
    result: "success" | "error" | "timeout",
    message?: string
  ): void {
    const log: CommunicationLog = {
      timestamp: new Date().toISOString(),
      direction,
      data,
      result,
      message,
    };

    this.logs.push(log);

    // ログの最大数を制限 (最新1000件)
    if (this.logs.length > 1000) {
      this.logs = this.logs.slice(-1000);
    }
  }

  // パブリックメソッド
  async setFloor(floor: string): Promise<CommandResult> {
    const floorData = this.encodeFloor(floor);
    const result = await this.sendCommand(
      0x0002,
      ElevatorCommands.FLOOR_SETTING,
      floorData
    );

    if (result.success) {
      this.status.targetFloor = floor;
      this.status.isMoving = true;

      // シミュレーション: 3秒後に移動完了
      setTimeout(() => {
        this.status.currentFloor = floor;
        this.status.isMoving = false;
      }, 3000);
    }

    return result;
  }

  async controlDoor(action: "open" | "close" | "stop"): Promise<CommandResult> {
    let doorCmd: DoorControl;
    let newStatus: ElevatorStatus["doorStatus"];

    switch (action) {
      case "open":
        doorCmd = DoorControl.OPEN;
        newStatus = "opening";
        break;
      case "close":
        doorCmd = DoorControl.CLOSE;
        newStatus = "closing";
        break;
      case "stop":
        doorCmd = DoorControl.STOP;
        newStatus = "unknown";
        break;
    }

    const result = await this.sendCommand(
      0x0002,
      ElevatorCommands.DOOR_CONTROL,
      doorCmd
    );

    if (result.success) {
      this.status.doorStatus = newStatus;

      // シミュレーション: 2秒後に動作完了
      if (action !== "stop") {
        setTimeout(() => {
          this.status.doorStatus = action === "open" ? "open" : "closed";
        }, 2000);
      }
    }

    return result;
  }

  getStatus(): ElevatorStatus {
    return { ...this.status };
  }

  getLogs(): CommunicationLog[] {
    return [...this.logs];
  }

  async updateConfig(
    newConfig: Partial<ElevatorConfig>
  ): Promise<CommandResult> {
    try {
      this.config = { ...this.config, ...newConfig };

      // シリアルポート設定が変更された場合は再接続
      if (newConfig.serialPort && this.serialPort?.isOpen) {
        await this.disconnect();
        await this.connectSerial();
      }

      return { success: true, data: this.config };
    } catch (error) {
      return {
        success: false,
        error: error instanceof Error ? error.message : "Unknown error",
      };
    }
  }

  async disconnect(): Promise<void> {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }

    if (this.serialPort?.isOpen) {
      await new Promise<void>((resolve) => {
        this.serialPort!.close((error) => {
          if (error) {
            console.error("❌ Error closing serial port:", error);
          }
          resolve();
        });
      });
    }

    this.status.connectionStatus = "disconnected";
    console.log("✅ Elevator Controller disconnected");
  }
}
