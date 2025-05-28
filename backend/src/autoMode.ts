import {
  ElevatorController,
  ElevatorStatus,
  CommunicationLog,
  ELEVATOR_TIMING,
} from "./elevator.js";

/**
 * 自動運転モード設定
 */
export interface AutoModeConfig {
  enabled: boolean;
  minPassengers: number;
  maxPassengers: number;
  passengerWeight: number; // 1人あたりの重量（kg）
  floorRange: {
    min: string;
    max: string;
  };
  operationInterval: number; // 運転間隔（ミリ秒）
  doorOpenTime: number; // ドア開放時間（ミリ秒）
}

/**
 * 乗客情報
 */
export interface PassengerInfo {
  entering: number; // 乗車人数
  exiting: number; // 降車人数
  totalWeight: number; // 総重量
}

/**
 * 自動運転ログ
 */
export interface AutoModeLog {
  timestamp: string;
  floor: string;
  action: string;
  passengers: PassengerInfo;
  message: string;
}

/**
 * 自動運転モードコントローラー
 */
export class AutoModeController {
  private elevatorController: ElevatorController;
  private config: AutoModeConfig;
  private isRunning: boolean = false;
  private operationTimer: NodeJS.Timeout | null = null;
  private autoLogs: AutoModeLog[] = [];
  private currentPassengers: number = 0;
  private targetFloors: string[] = [];
  private currentTargetIndex: number = 0;

  constructor(elevatorController: ElevatorController) {
    this.elevatorController = elevatorController;
    this.config = {
      enabled: false,
      minPassengers: 0,
      maxPassengers: 10,
      passengerWeight: 60, // 1人60kg
      floorRange: {
        min: "B1F",
        max: "5F",
      },
      operationInterval: 10000, // 10秒間隔
      doorOpenTime: 5000, // 5秒間ドア開放
    };

    // 運転対象階を初期化
    this.initializeTargetFloors();
  }

  /**
   * 運転対象階を初期化
   */
  private initializeTargetFloors(): void {
    this.targetFloors = [];

    // B1Fから5Fまでの階を追加
    this.targetFloors.push("B1F");
    for (let i = 1; i <= 5; i++) {
      this.targetFloors.push(`${i}F`);
    }

    console.log("🏢 自動運転対象階:", this.targetFloors);
  }

  /**
   * 自動運転モードを開始
   */
  async start(): Promise<void> {
    if (this.isRunning) {
      console.log("⚠️ 自動運転モードは既に実行中です");
      return;
    }

    console.log("🚀 自動運転モードを開始します");
    this.isRunning = true;
    this.config.enabled = true;

    this.addAutoLog("システム", "自動運転モード開始", {
      entering: 0,
      exiting: 0,
      totalWeight: 0,
    });

    // 初期位置を1Fに設定
    const status = this.elevatorController.getStatus();
    if (!status.currentFloor) {
      await this.elevatorController.setWeight(0);
      // 初期位置設定は手動で行う（実際のエレベーターでは現在位置を取得）
    }

    // 自動運転ループを開始
    this.startOperationLoop();
  }

  /**
   * 自動運転モードを停止
   */
  async stop(): Promise<void> {
    if (!this.isRunning) {
      console.log("⚠️ 自動運転モードは実行されていません");
      return;
    }

    console.log("🛑 自動運転モードを停止します");
    this.isRunning = false;
    this.config.enabled = false;

    if (this.operationTimer) {
      clearTimeout(this.operationTimer);
      this.operationTimer = null;
    }

    this.addAutoLog("システム", "自動運転モード停止", {
      entering: 0,
      exiting: 0,
      totalWeight: 0,
    });
  }

  /**
   * 自動運転ループを開始
   */
  private startOperationLoop(): void {
    if (!this.isRunning) return;

    this.operationTimer = setTimeout(async () => {
      try {
        await this.executeOperation();
      } catch (error) {
        console.error("❌ 自動運転エラー:", error);
        this.addAutoLog("エラー", `運転エラー: ${error}`, {
          entering: 0,
          exiting: 0,
          totalWeight: 0,
        });
      }

      // 次の運転サイクルをスケジュール
      if (this.isRunning) {
        this.startOperationLoop();
      }
    }, this.config.operationInterval);
  }

  /**
   * 自動運転操作を実行
   */
  private async executeOperation(): Promise<void> {
    const status = this.elevatorController.getStatus();

    // 次の目標階を決定
    const targetFloor = this.getNextTargetFloor();

    console.log(`🎯 次の目標階: ${targetFloor} (現在: ${status.currentFloor})`);

    // 目標階に移動
    if (status.currentFloor !== targetFloor) {
      console.log(`🚀 ${targetFloor}に移動中...`);

      // 扉が開いている場合は閉める
      if (status.doorStatus === "open" || status.doorStatus === "opening") {
        console.log("🚪 扉を閉めています...");
        await this.elevatorController.controlDoor("close");
        await this.waitForDoorClose();
      }

      // 階移動
      const moveResult = await this.elevatorController.setFloor(targetFloor);
      if (moveResult.success) {
        // 移動完了まで待機
        await this.waitForMovementComplete(targetFloor);
      } else {
        console.error("❌ 階移動に失敗:", moveResult.error);
        return;
      }
    }

    // 到着後の処理
    await this.handleFloorArrival(targetFloor);
  }

  /**
   * 次の目標階を取得
   */
  private getNextTargetFloor(): string {
    const targetFloor = this.targetFloors[this.currentTargetIndex];
    this.currentTargetIndex =
      (this.currentTargetIndex + 1) % this.targetFloors.length;
    return targetFloor;
  }

  /**
   * 階到着時の処理
   */
  private async handleFloorArrival(floor: string): Promise<void> {
    console.log(`🏢 ${floor}に到着しました`);

    // ドアを開く
    console.log("🚪 ドアを開いています...");
    await this.elevatorController.controlDoor("open");
    await this.waitForDoorOpen();

    // 乗客の出入りをシミュレート
    const passengerChange = this.simulatePassengerChange(floor);

    // 荷重を更新
    this.currentPassengers +=
      passengerChange.entering - passengerChange.exiting;
    this.currentPassengers = Math.max(
      0,
      Math.min(this.currentPassengers, this.config.maxPassengers)
    );

    const newWeight = this.currentPassengers * this.config.passengerWeight;
    await this.elevatorController.setWeight(newWeight);

    // ログ記録
    this.addAutoLog(floor, "乗客出入り", passengerChange);

    console.log(
      `👥 現在の乗客数: ${this.currentPassengers}人 (${newWeight}kg)`
    );
    console.log(
      `📊 乗車: ${passengerChange.entering}人, 降車: ${passengerChange.exiting}人`
    );

    // ドア開放時間待機
    await new Promise((resolve) =>
      setTimeout(resolve, this.config.doorOpenTime)
    );

    // ドアを閉める
    console.log("🚪 ドアを閉めています...");
    await this.elevatorController.controlDoor("close");
    await this.waitForDoorClose();
  }

  /**
   * 乗客の出入りをシミュレート
   */
  private simulatePassengerChange(floor: string): PassengerInfo {
    // 現在の乗客数に基づいて降車人数を決定
    const maxExiting = this.currentPassengers;
    const exiting = Math.floor(Math.random() * (maxExiting + 1));

    // 残り容量に基づいて乗車人数を決定
    const remainingCapacity =
      this.config.maxPassengers - (this.currentPassengers - exiting);
    const maxEntering = Math.min(remainingCapacity, this.config.maxPassengers);
    const entering = Math.floor(Math.random() * (maxEntering + 1));

    const totalWeight =
      (this.currentPassengers - exiting + entering) *
      this.config.passengerWeight;

    return {
      entering,
      exiting,
      totalWeight,
    };
  }

  /**
   * 移動完了まで待機
   */
  private async waitForMovementComplete(targetFloor: string): Promise<void> {
    return new Promise((resolve) => {
      const checkInterval = setInterval(() => {
        const status = this.elevatorController.getStatus();
        if (status.currentFloor === targetFloor && !status.isMoving) {
          clearInterval(checkInterval);
          resolve();
        }
      }, 100);

      // タイムアウト設定
      setTimeout(() => {
        clearInterval(checkInterval);
        resolve();
      }, ELEVATOR_TIMING.FLOOR_MOVEMENT_TIME + 1000);
    });
  }

  /**
   * ドア開放完了まで待機
   */
  private async waitForDoorOpen(): Promise<void> {
    return new Promise((resolve) => {
      const checkInterval = setInterval(() => {
        const status = this.elevatorController.getStatus();
        if (status.doorStatus === "open") {
          clearInterval(checkInterval);
          resolve();
        }
      }, 100);

      // タイムアウト設定
      setTimeout(() => {
        clearInterval(checkInterval);
        resolve();
      }, ELEVATOR_TIMING.DOOR_OPERATION_TIME + 1000);
    });
  }

  /**
   * ドア閉鎖完了まで待機
   */
  private async waitForDoorClose(): Promise<void> {
    return new Promise((resolve) => {
      const checkInterval = setInterval(() => {
        const status = this.elevatorController.getStatus();
        if (status.doorStatus === "closed") {
          clearInterval(checkInterval);
          resolve();
        }
      }, 100);

      // タイムアウト設定
      setTimeout(() => {
        clearInterval(checkInterval);
        resolve();
      }, ELEVATOR_TIMING.DOOR_OPERATION_TIME + 1000);
    });
  }

  /**
   * 自動運転ログを追加
   */
  private addAutoLog(
    floor: string,
    action: string,
    passengers: PassengerInfo
  ): void {
    const log: AutoModeLog = {
      timestamp: new Date().toISOString(),
      floor,
      action,
      passengers,
      message: `${floor}: ${action} - 乗車:${passengers.entering}人, 降車:${passengers.exiting}人, 総重量:${passengers.totalWeight}kg`,
    };

    this.autoLogs.push(log);

    // ログの最大数を制限 (最新500件)
    if (this.autoLogs.length > 500) {
      this.autoLogs = this.autoLogs.slice(-500);
    }

    console.log(`📝 自動運転ログ: ${log.message}`);
  }

  /**
   * 設定を更新
   */
  updateConfig(newConfig: Partial<AutoModeConfig>): void {
    this.config = { ...this.config, ...newConfig };
    console.log("⚙️ 自動運転設定を更新しました:", this.config);
  }

  /**
   * 現在の設定を取得
   */
  getConfig(): AutoModeConfig {
    return { ...this.config };
  }

  /**
   * 自動運転ログを取得
   */
  getAutoLogs(): AutoModeLog[] {
    return [...this.autoLogs];
  }

  /**
   * 現在の状態を取得
   */
  getStatus(): {
    isRunning: boolean;
    currentPassengers: number;
    nextTargetFloor: string;
    config: AutoModeConfig;
  } {
    return {
      isRunning: this.isRunning,
      currentPassengers: this.currentPassengers,
      nextTargetFloor: this.targetFloors[this.currentTargetIndex],
      config: this.config,
    };
  }

  /**
   * 自動運転モードが有効かどうか
   */
  isEnabled(): boolean {
    return this.config.enabled && this.isRunning;
  }
}
