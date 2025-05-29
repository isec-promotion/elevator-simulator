import {
  ElevatorController,
  ElevatorStatus,
  CommunicationLog,
  ELEVATOR_TIMING,
} from "./elevator.js";

// 自動運転モードのタイムアウト設定（ミリ秒）
export const AUTO_MODE_TIMING = {
  MOVEMENT_TIMEOUT: 15000, // 階移動完了待機時間（15秒）
  DOOR_OPERATION_TIMEOUT: 10000, // ドア開閉完了待機時間（10秒）
  OPERATION_INTERVAL: 15000, // 運転間隔（15秒）
  DOOR_OPEN_TIME: 5000, // ドア開放時間（5秒）
  // 高速モード用
  // MOVEMENT_TIMEOUT: 5000, // 階移動完了待機時間（5秒）
  // DOOR_OPERATION_TIMEOUT: 3000, // ドア開閉完了待機時間（3秒）
  // OPERATION_INTERVAL: 5000, // 運転間隔（5秒）
  // DOOR_OPEN_TIME: 3000, // ドア開放時間（3秒）
} as const;

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
      operationInterval: AUTO_MODE_TIMING.OPERATION_INTERVAL, // 運転間隔
      doorOpenTime: AUTO_MODE_TIMING.DOOR_OPEN_TIME, // ドア開放時間
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

    // 強制的に初期位置を1Fに設定
    console.log("🏢 初期位置を1Fに設定しています...");
    await this.initializeElevatorPosition();

    // 自動運転ループを開始
    this.startOperationLoop();
  }

  /**
   * エレベーターの初期位置を1Fに設定
   */
  private async initializeElevatorPosition(): Promise<void> {
    try {
      // 荷重を0に設定
      await this.elevatorController.setWeight(0);
      console.log("✅ 荷重を0kgに設定しました");

      // 現在の状態を取得
      const currentStatus = this.elevatorController.getStatus();
      console.log(
        `📊 現在の状態: 階=${currentStatus.currentFloor}, ドア=${currentStatus.doorStatus}`
      );

      // シミュレーションモードの場合は直接状態を設定
      if (this.elevatorController.isSimulationMode()) {
        // シミュレーションモードでは内部状態を直接更新
        console.log("🎭 シミュレーションモード: 1Fに強制設定");

        // エレベーターコントローラーの内部状態を更新するため、
        // 一度setFloorを呼び出して1Fに設定
        const result = await this.elevatorController.setFloor("1F");
        if (result.success) {
          // 移動完了まで待機
          await this.waitForMovementComplete("1F");
          console.log("✅ 初期位置を1Fに設定完了");
        } else {
          console.warn("⚠️ 初期位置設定に失敗しましたが、続行します");
        }
      } else {
        // 実機モードの場合は実際に1Fに移動
        console.log("🔧 実機モード: 1Fに移動中...");

        // ドアが開いている場合は閉める
        if (
          currentStatus.doorStatus === "open" ||
          currentStatus.doorStatus === "opening"
        ) {
          console.log("🚪 ドアを閉めています...");
          await this.elevatorController.controlDoor("close");
          await this.waitForDoorClose();
        }

        // 1Fに移動
        const result = await this.elevatorController.setFloor("1F");
        if (result.success) {
          await this.waitForMovementComplete("1F");
          console.log("✅ 初期位置を1Fに設定完了");
        } else {
          console.warn("⚠️ 初期位置設定に失敗しましたが、続行します");
        }
      }

      // 乗客数をリセット
      this.currentPassengers = 0;

      this.addAutoLog("システム", "初期位置設定完了", {
        entering: 0,
        exiting: 0,
        totalWeight: 0,
      });
    } catch (error) {
      console.error("❌ 初期位置設定エラー:", error);
      this.addAutoLog("エラー", `初期位置設定エラー: ${error}`, {
        entering: 0,
        exiting: 0,
        totalWeight: 0,
      });
    }
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
    console.log(`📊 現在のドア状態: ${status.doorStatus}`);

    // 目標階に移動
    if (status.currentFloor !== targetFloor) {
      console.log(`🚀 ${targetFloor}に移動中...`);

      // 扉の状態を確認し、必要に応じて閉める
      await this.ensureDoorClosed();

      // 階移動
      const moveResult = await this.elevatorController.setFloor(targetFloor);
      if (moveResult.success) {
        // 移動完了まで待機
        await this.waitForMovementComplete(targetFloor);
      } else {
        console.error("❌ 階移動に失敗:", moveResult.error);
        this.addAutoLog("エラー", `階移動失敗: ${moveResult.error}`, {
          entering: 0,
          exiting: 0,
          totalWeight: 0,
        });
        return;
      }
    }

    // 到着後の処理
    await this.handleFloorArrival(targetFloor);
  }

  /**
   * ドアが確実に閉まっていることを確認
   */
  private async ensureDoorClosed(): Promise<void> {
    const status = this.elevatorController.getStatus();

    if (status.doorStatus === "closed") {
      console.log("✅ ドアは既に閉まっています");
      return;
    }

    if (status.doorStatus === "open" || status.doorStatus === "opening") {
      console.log("🚪 ドアを閉めています...");
      await this.elevatorController.controlDoor("close");
      await this.waitForDoorClose();
    } else if (status.doorStatus === "closing") {
      console.log("🚪 ドアが閉まるまで待機中...");
      await this.waitForDoorClose();
    } else {
      console.warn(
        `⚠️ 不明なドア状態: ${status.doorStatus} - 強制的に閉扉コマンドを送信`
      );
      await this.elevatorController.controlDoor("close");
      await this.waitForDoorClose();
    }

    // 最終確認
    const finalStatus = this.elevatorController.getStatus();
    if (finalStatus.doorStatus !== "closed") {
      console.error(
        `❌ ドアが閉まりませんでした。現在状態: ${finalStatus.doorStatus}`
      );
      this.addAutoLog("エラー", `ドア閉鎖失敗: ${finalStatus.doorStatus}`, {
        entering: 0,
        exiting: 0,
        totalWeight: 0,
      });
    } else {
      console.log("✅ ドア閉鎖確認完了");
    }
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
      let timeoutCount = 0;
      const maxTimeout = AUTO_MODE_TIMING.MOVEMENT_TIMEOUT;

      const checkInterval = setInterval(() => {
        const status = this.elevatorController.getStatus();
        timeoutCount += 100;

        if (status.currentFloor === targetFloor && !status.isMoving) {
          console.log(`✅ 移動完了: ${targetFloor} (${timeoutCount}ms)`);
          clearInterval(checkInterval);
          resolve();
        } else if (timeoutCount >= maxTimeout) {
          console.warn(
            `⚠️ 移動タイムアウト: ${targetFloor} (${timeoutCount}ms)`
          );
          clearInterval(checkInterval);
          resolve();
        }
      }, 100);
    });
  }

  /**
   * ドア開放完了まで待機
   */
  private async waitForDoorOpen(): Promise<void> {
    return new Promise((resolve) => {
      let timeoutCount = 0;
      const maxTimeout = AUTO_MODE_TIMING.DOOR_OPERATION_TIMEOUT;

      const checkInterval = setInterval(() => {
        const status = this.elevatorController.getStatus();
        timeoutCount += 100;

        if (status.doorStatus === "open") {
          console.log(`✅ ドア開放完了 (${timeoutCount}ms)`);
          clearInterval(checkInterval);
          resolve();
        } else if (timeoutCount >= maxTimeout) {
          console.warn(
            `⚠️ ドア開放タイムアウト (${timeoutCount}ms) - 現在状態: ${status.doorStatus}`
          );
          clearInterval(checkInterval);
          resolve();
        }
      }, 100);
    });
  }

  /**
   * ドア閉鎖完了まで待機
   */
  private async waitForDoorClose(): Promise<void> {
    return new Promise((resolve) => {
      let timeoutCount = 0;
      const maxTimeout = AUTO_MODE_TIMING.DOOR_OPERATION_TIMEOUT;

      const checkInterval = setInterval(() => {
        const status = this.elevatorController.getStatus();
        timeoutCount += 100;

        if (status.doorStatus === "closed") {
          console.log(`✅ ドア閉鎖完了 (${timeoutCount}ms)`);
          clearInterval(checkInterval);
          resolve();
        } else if (timeoutCount >= maxTimeout) {
          console.warn(
            `⚠️ ドア閉鎖タイムアウト (${timeoutCount}ms) - 現在状態: ${status.doorStatus}`
          );
          clearInterval(checkInterval);
          resolve();
        }
      }, 100);
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
