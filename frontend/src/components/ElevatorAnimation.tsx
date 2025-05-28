import React from "react";
import { ElevatorStatus } from "../App";
import "./ElevatorAnimation.css";

interface ElevatorAnimationProps {
  status: ElevatorStatus;
}

const ElevatorAnimation: React.FC<ElevatorAnimationProps> = ({ status }) => {
  const floors = ["B1F", "1F", "2F", "3F", "4F", "5F"];

  // 現在階から位置を計算（下から上へ）
  const getCurrentFloorPosition = () => {
    const currentFloor = status.currentFloor || "1F";
    const floorIndex = floors.indexOf(currentFloor);
    if (floorIndex === -1) return 1; // デフォルトは1F（インデックス1）
    return floorIndex; // そのまま使用（B1F=0, 1F=1, 2F=2...）
  };

  const getTargetFloorPosition = () => {
    if (!status.targetFloor) return getCurrentFloorPosition();
    const floorIndex = floors.indexOf(status.targetFloor);
    if (floorIndex === -1) return getCurrentFloorPosition();
    return floorIndex; // そのまま使用（B1F=0, 1F=1, 2F=2...）
  };

  const currentPosition = getCurrentFloorPosition();
  const targetPosition = getTargetFloorPosition();

  // かごの位置を計算（0-85%、5階でもシャフト内に収まるように）
  const cagePosition = status.isMoving
    ? (targetPosition / (floors.length - 1)) * 85
    : (currentPosition / (floors.length - 1)) * 85;

  // 扉の状態に応じたクラス
  const getDoorClass = () => {
    switch (status.doorStatus) {
      case "open":
        return "door-open";
      case "opening":
        return "door-opening";
      case "closing":
        return "door-closing";
      case "closed":
        return "door-closed";
      default:
        return "door-unknown";
    }
  };

  return (
    <div className="elevator-animation">
      <div className="animation-header">
        <h2>🏢 エレベーター動作状況</h2>
      </div>

      <div className="elevator-shaft">
        {/* 階数表示 */}
        <div className="floor-indicators">
          {floors
            .slice()
            .reverse()
            .map((floor, index) => (
              <div
                key={floor}
                className={`floor-indicator ${
                  status.currentFloor === floor ? "current" : ""
                } ${status.targetFloor === floor ? "target" : ""}`}
                style={{ top: `${index * 60}px` }}
              >
                {floor}
              </div>
            ))}
        </div>

        {/* エレベーターシャフト */}
        <div className="shaft-container">
          <div className="shaft-background">
            {/* 階層線 */}
            {floors.map((_, index) => (
              <div
                key={index}
                className="floor-line"
                style={{ bottom: `${(index / (floors.length - 1)) * 85}%` }}
              />
            ))}
          </div>

          {/* エレベーターかご */}
          <div
            className={`elevator-cage ${
              status.isMoving ? "moving" : "stopped"
            }`}
            style={{
              bottom: `${cagePosition}%`,
              transition: status.isMoving ? "bottom 3s ease-in-out" : "none",
            }}
          >
            {/* かご本体 */}
            <div className="cage-body">
              {/* 扉 */}
              <div className={`cage-doors ${getDoorClass()}`}>
                <div className="door-left"></div>
                <div className="door-right"></div>
              </div>

              {/* 荷重表示 */}
              <div className="weight-indicator">
                {status.loadWeight !== null ? `${status.loadWeight}kg` : "--"}
              </div>
            </div>

            {/* 移動方向インジケーター */}
            {status.isMoving && (
              <div className="direction-indicator">
                {currentPosition < targetPosition ? "↑" : "↓"}
              </div>
            )}
          </div>
        </div>

        {/* 状態表示 */}
        <div className="status-overlay">
          <div className="current-floor-display">
            現在階: {status.currentFloor || "--"}
          </div>
          {status.targetFloor && (
            <div className="target-floor-display">
              行先階: {status.targetFloor}
            </div>
          )}
          <div
            className={`movement-status ${
              status.isMoving ? "moving" : "stopped"
            }`}
          >
            {status.isMoving ? "移動中" : "停止中"}
          </div>
        </div>
      </div>
    </div>
  );
};

export default ElevatorAnimation;
