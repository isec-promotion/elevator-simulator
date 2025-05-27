import { SerialPort } from "serialport";

// 型定義
export interface ElevatorStatus {
  currentFloor: string | null;
  targetFloor: string | null;
  doorStatus: "open" | "closed" | "opening" | "closing" | "unknown";
  isMoving: boolean;
  loadWeight: number | null;
  connectionStatus: "connected" | "disconnected" | "error" | "simulation";
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
  dataBits: 5 | 6 | 7 | 8;
  parity: "none" | "even" | "odd";
  stopBits: 1 | 1.5 | 2;
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
  OPEN = 0x0001, // bit0: 開扉開始
  CLOSE = 0x0002, // bit1: 閉扉開始
}

export class ElevatorController {
  private serialPort: SerialPort | null = null;
  private config: ElevatorConfig;
  private status: ElevatorStatus;
  private logs: CommunicationLog[] = [];
  private isInitialized = false;
  private reconnectTimer: NodeJS.Timeout | null = null;
  private simulationMode: boolean = false;
  private simulationTimer: NodeJS.Timeout | null = null;

  constructor(simulationMode: boolean = false) {
    this.simulationMode = simulationMode;
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
      connectionStatus: simulationMode ? "simulation" : "disconnected",
      lastCommunication: null,
    };

    if (simulationMode) {
      console.log("🎭 Elevator Controller initialized in simulation mode");
      this.startSimulation();
    }
  }

  private startSimulation(): void {
    // 疑似モードでの初期状態設定
    this.status.currentFloor = "1F";
    this.status.doorStatus = "closed";
    this.status.loadWeight = 0;
    this.status.connectionStatus = "connected"; // RS422接続中として表示
    this.status.lastCommunication = new Date().toISOString();

    this.addLog(
      "system",
      "Simulation mode started",
      "success",
      "疑似モード: RS422接続中"
    );
  }

  async initialize(): Promise<void> {
    try {
      console.log("🔧 Initializing Elevator Controller...");

      if (this.simulationMode) {
        console.log(
          "🎭 Running in simulation mode - skipping serial port initialization"
        );
        this.isInitialized = true;
        return;
      }

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
        this.simulationMode = true;
        this.status.connectionStatus = "simulation";
        this.startSimulation();
        this.isInitialized = true;
        return;
      }

      await this.connectSerial();
      this.isInitialized = true;
      console.log("✅ Elevator Controller initialized successfully");
    } catch (error) {
      console.error("❌ Failed to initialize Elevator Controller:", error);
      console.log("🎭 Falling back to simulation mode");
      this.simulationMode = true;
      this.status.connectionStatus = "simulation";
      this.startSimulation();
      this.isInitialized = true;
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

  private formatSerialData(message: Buffer): string {
    if (message.length < 10) {
      return "Invalid message";
    }

    const enq = message[0].toString(16).padStart(2, "0").toUpperCase();
    const station = message.subarray(1, 5).toString("ascii");
    const command = String.fromCharCode(message[5]);
    const dataNum = message.subarray(6, 10).toString("ascii");
    const data = message.subarray(10, 14).toString("ascii");
    const checksum = message.subarray(14, 16).toString("ascii");

    // データ番号の意味を解釈
    let dataDescription = "";
    const dataNumInt = parseInt(dataNum);
    switch (dataNumInt) {
      case 0x0010:
        const floorValue = parseInt(data, 16);
        const floorName = floorValue === 0xffff ? "B1F" : `${floorValue}F`;
        dataDescription = `階数設定: ${floorName}`;
        break;
      case 0x0011:
        const doorValue = parseInt(data, 16);
        let doorAction = "";
        if (doorValue === 0x0001) doorAction = "開扉";
        else if (doorValue === 0x0002) doorAction = "閉扉";
        else if (doorValue === 0x0000) doorAction = "停止";
        else doorAction = "不明";
        dataDescription = `扉制御: ${doorAction}`;
        break;
      case 0x0003:
        const weightValue = parseInt(data, 16);
        dataDescription = `荷重設定: ${weightValue}kg`;
        break;
      default:
        dataDescription = `データ番号: ${dataNum}`;
    }

    return `ENQ(${enq}) 局番号:${station} CMD:${command} ${dataDescription} データ:${data} チェックサム:${checksum}`;
  }

  private async sendCommand(
    targetStation: number,
    command: ElevatorCommands,
    data: number
  ): Promise<CommandResult> {
    // 実際の送信データを作成（シミュレーションモードでも表示用）
    const message = this.createWriteCommand(targetStation, command, data);
    const hexData = message.toString("hex").toUpperCase();
    const readableData = this.formatSerialData(message);

    if (this.simulationMode || !this.serialPort?.isOpen) {
      // シミュレーションモード
      console.log(
        `🎭 Simulation: Sending command ${command.toString(
          16
        )} with data ${data.toString(16)} to station ${targetStation}`
      );
      console.log(`📡 Serial Data: ${hexData}`);
      console.log(`📋 Readable: ${readableData}`);

      this.addLog("send", hexData, "success", `${readableData} (疑似モード)`);

      // 疑似的な応答遅延
      await new Promise((resolve) => setTimeout(resolve, 100));

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
    // 安全チェック: 扉が閉まっていない場合は移動を拒否
    if (this.status.doorStatus !== "closed") {
      let errorMessage = "";
      if (
        this.status.doorStatus === "open" ||
        this.status.doorStatus === "opening"
      ) {
        errorMessage =
          "扉が開いています。扉を閉めてから階数を選択してください。";
      } else if (this.status.doorStatus === "closing") {
        errorMessage = "扉が閉まるまでお待ちください。";
      } else {
        errorMessage =
          "扉の状態が不明です。扉を閉めてから階数を選択してください。";
      }

      this.addLog(
        "system",
        `Floor setting rejected: ${floor}`,
        "error",
        `安全エラー: ${errorMessage}`
      );
      return {
        success: false,
        error: errorMessage,
      };
    }

    const floorData = this.encodeFloor(floor);
    const result = await this.sendCommand(
      0x0001,
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
        this.addLog(
          "system",
          `Floor changed to ${floor}`,
          "success",
          `疑似モード: ${floor}に移動完了`
        );
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
      0x0001,
      ElevatorCommands.DOOR_CONTROL,
      doorCmd
    );

    if (result.success) {
      this.status.doorStatus = newStatus;

      // シミュレーション: 2秒後に動作完了
      if (action !== "stop") {
        setTimeout(() => {
          this.status.doorStatus = action === "open" ? "open" : "closed";
          this.addLog(
            "system",
            `Door ${action} completed`,
            "success",
            `疑似モード: ドア${action === "open" ? "開" : "閉"}完了`
          );
        }, 2000);
      }
    }

    return result;
  }

  async setWeight(weight: number): Promise<CommandResult> {
    // 荷重の範囲チェック (0-1000kg)
    if (weight < 0 || weight > 1000) {
      this.addLog(
        "system",
        `Weight setting rejected: ${weight}kg`,
        "error",
        "荷重エラー: 0-1000kgの範囲で入力してください。"
      );
      return {
        success: false,
        error: "荷重は0-1000kgの範囲で入力してください。",
      };
    }

    // 注意: 荷重は通常エレベータから自動運転装置への送信データです
    // シミュレーション目的でのみ使用
    const result = await this.sendCommand(
      0x0001,
      ElevatorCommands.LOAD_WEIGHT,
      weight
    );

    if (result.success) {
      this.status.loadWeight = weight;
      this.status.lastCommunication = new Date().toISOString();
      this.addLog(
        "system",
        `Weight set to ${weight}kg`,
        "success",
        `疑似モード: 荷重を${weight}kgに設定`
      );
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
      if (
        newConfig.serialPort &&
        this.serialPort?.isOpen &&
        !this.simulationMode
      ) {
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

    if (this.simulationTimer) {
      clearInterval(this.simulationTimer);
      this.simulationTimer = null;
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

    this.status.connectionStatus = this.simulationMode
      ? "simulation"
      : "disconnected";
    console.log("✅ Elevator Controller disconnected");
  }

  // 疑似モード制御メソッド
  isSimulationMode(): boolean {
    return this.simulationMode;
  }

  enableSimulationMode(): void {
    if (!this.simulationMode) {
      this.simulationMode = true;
      this.status.connectionStatus = "simulation";
      this.startSimulation();
      console.log("🎭 Simulation mode enabled");
    }
  }

  disableSimulationMode(): void {
    if (this.simulationMode) {
      this.simulationMode = false;
      if (this.simulationTimer) {
        clearInterval(this.simulationTimer);
        this.simulationTimer = null;
      }
      this.status.connectionStatus = "disconnected";
      console.log("🔌 Simulation mode disabled");
    }
  }
}
