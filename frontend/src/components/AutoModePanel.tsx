import React, { useState, useEffect } from "react";
import "./AutoModePanel.css";

// 自動運転モード設定の型定義
export interface AutoModeConfig {
  enabled: boolean;
  minPassengers: number;
  maxPassengers: number;
  passengerWeight: number;
  floorRange: {
    min: string;
    max: string;
  };
  operationInterval: number;
  doorOpenTime: number;
}

// 乗客情報の型定義
export interface PassengerInfo {
  entering: number;
  exiting: number;
  totalWeight: number;
}

// 自動運転ログの型定義
export interface AutoModeLog {
  timestamp: string;
  floor: string;
  action: string;
  passengers: PassengerInfo;
  message: string;
}

// 自動運転状態の型定義
export interface AutoModeStatus {
  isRunning: boolean;
  currentPassengers: number;
  nextTargetFloor: string;
  config: AutoModeConfig;
}

interface AutoModePanelProps {
  autoModeStatus: AutoModeStatus | null;
  autoModeLogs: AutoModeLog[];
  onStartAutoMode: () => void;
  onStopAutoMode: () => void;
  onUpdateConfig: (config: Partial<AutoModeConfig>) => void;
  isAutoModeEnabled: boolean;
}

const AutoModePanel: React.FC<AutoModePanelProps> = ({
  autoModeStatus,
  autoModeLogs,
  onStartAutoMode,
  onStopAutoMode,
  onUpdateConfig,
  isAutoModeEnabled,
}) => {
  const [showConfig, setShowConfig] = useState(false);
  const [configForm, setConfigForm] = useState<Partial<AutoModeConfig>>({});

  // 自動運転モードが有効かどうかを判定
  const isRunning = autoModeStatus?.isRunning || false;

  // 設定フォームの初期化
  useEffect(() => {
    if (autoModeStatus?.config) {
      setConfigForm(autoModeStatus.config);
    }
  }, [autoModeStatus?.config]);

  const handleConfigChange = (key: string, value: any) => {
    setConfigForm((prev) => ({
      ...prev,
      [key]: value,
    }));
  };

  const handleConfigSubmit = () => {
    onUpdateConfig(configForm);
    setShowConfig(false);
  };

  const formatTime = (timestamp: string) => {
    return new Date(timestamp).toLocaleTimeString("ja-JP");
  };

  const getStatusColor = () => {
    if (!isAutoModeEnabled) return "#9E9E9E";
    return isRunning ? "#4CAF50" : "#FF9800";
  };

  const getStatusText = () => {
    if (!isAutoModeEnabled) return "自動運転モード無効";
    return isRunning ? "自動運転中" : "停止中";
  };

  return (
    <div className="auto-mode-panel">
      <div className="panel-header">
        <h3>🤖 自動運転モード</h3>
        <div className="auto-mode-status">
          <span
            className="status-indicator"
            style={{ backgroundColor: getStatusColor() }}
          />
          <span>{getStatusText()}</span>
        </div>
      </div>

      {isAutoModeEnabled && (
        <>
          <div className="auto-mode-controls">
            <button
              className={`control-button ${isRunning ? "stop" : "start"}`}
              onClick={isRunning ? onStopAutoMode : onStartAutoMode}
              disabled={!autoModeStatus}
            >
              {isRunning ? "🛑 停止" : "🚀 開始"}
            </button>

            <button
              className="config-button"
              onClick={() => setShowConfig(!showConfig)}
              disabled={isRunning}
            >
              ⚙️ 設定
            </button>
          </div>

          {autoModeStatus && (
            <div className="auto-mode-info">
              <div className="info-row">
                <span className="label">現在の乗客数:</span>
                <span className="value">
                  {autoModeStatus.currentPassengers}人
                </span>
              </div>
              <div className="info-row">
                <span className="label">次の目標階:</span>
                <span className="value">{autoModeStatus.nextTargetFloor}</span>
              </div>
              <div className="info-row">
                <span className="label">運転間隔:</span>
                <span className="value">
                  {autoModeStatus.config.operationInterval / 1000}秒
                </span>
              </div>
              <div className="info-row">
                <span className="label">最大乗客数:</span>
                <span className="value">
                  {autoModeStatus.config.maxPassengers}人
                </span>
              </div>
            </div>
          )}

          {showConfig && autoModeStatus && (
            <div className="config-panel">
              <h4>自動運転設定</h4>

              <div className="config-group">
                <label>運転間隔 (秒):</label>
                <input
                  type="number"
                  min="5"
                  max="60"
                  value={(configForm.operationInterval || 10000) / 1000}
                  onChange={(e) =>
                    handleConfigChange(
                      "operationInterval",
                      parseInt(e.target.value) * 1000
                    )
                  }
                />
              </div>

              <div className="config-group">
                <label>ドア開放時間 (秒):</label>
                <input
                  type="number"
                  min="2"
                  max="10"
                  value={(configForm.doorOpenTime || 5000) / 1000}
                  onChange={(e) =>
                    handleConfigChange(
                      "doorOpenTime",
                      parseInt(e.target.value) * 1000
                    )
                  }
                />
              </div>

              <div className="config-group">
                <label>最大乗客数 (人):</label>
                <input
                  type="number"
                  min="1"
                  max="20"
                  value={configForm.maxPassengers || 10}
                  onChange={(e) =>
                    handleConfigChange(
                      "maxPassengers",
                      parseInt(e.target.value)
                    )
                  }
                />
              </div>

              <div className="config-group">
                <label>1人あたりの重量 (kg):</label>
                <input
                  type="number"
                  min="40"
                  max="100"
                  value={configForm.passengerWeight || 60}
                  onChange={(e) =>
                    handleConfigChange(
                      "passengerWeight",
                      parseInt(e.target.value)
                    )
                  }
                />
              </div>

              <div className="config-buttons">
                <button className="apply-button" onClick={handleConfigSubmit}>
                  適用
                </button>
                <button
                  className="cancel-button"
                  onClick={() => setShowConfig(false)}
                >
                  キャンセル
                </button>
              </div>
            </div>
          )}

          <div className="auto-mode-logs">
            <h4>自動運転ログ</h4>
            <div className="logs-container">
              {autoModeLogs.length === 0 ? (
                <div className="no-logs">ログがありません</div>
              ) : (
                autoModeLogs
                  .slice(-10)
                  .reverse()
                  .map((log, index) => (
                    <div key={index} className="log-entry">
                      <div className="log-time">
                        {formatTime(log.timestamp)}
                      </div>
                      <div className="log-content">
                        <div className="log-floor">{log.floor}</div>
                        <div className="log-action">{log.action}</div>
                        <div className="log-passengers">
                          乗車: {log.passengers.entering}人, 降車:{" "}
                          {log.passengers.exiting}人
                        </div>
                      </div>
                    </div>
                  ))
              )}
            </div>
          </div>
        </>
      )}

      {!isAutoModeEnabled && (
        <div className="auto-mode-disabled">
          <p>
            自動運転モードを使用するには、
            <br />
            <code>npm run dev:auto</code> でサーバーを起動してください。
          </p>
        </div>
      )}
    </div>
  );
};

export default AutoModePanel;
