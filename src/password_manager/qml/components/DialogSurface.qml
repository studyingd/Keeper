import QtQuick
import ".."

// 对话框表面：卡面 + 顶部高光线（两端内缩一个圆角半径，避免伸出圆弧外）
Rectangle {
    id: surface
    radius: Theme.radiusXl
    color: Theme.surface
    border.width: 1
    border.color: Theme.border

    Rectangle {
        anchors {
            top: parent.top
            horizontalCenter: parent.horizontalCenter
        }
        width: parent.width - 2 * parent.radius
        height: 1
        color: Qt.rgba(255, 255, 255, 0.10)
    }
}
