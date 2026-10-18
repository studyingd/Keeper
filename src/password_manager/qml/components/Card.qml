import QtQuick
import ".."

// 卡片：纯表面 + 描边，hover 仅变亮边框和轻微放大，无阴影/光晕
Rectangle {
    id: root
    default property alias content: body.data
    property bool accentLeft: false
    property bool hoverable: true
    property color cardColor: Theme.surface
    readonly property bool hovered: mouse.containsMouse

    radius: Theme.radiusLg
    color: cardColor
    border.width: 1
    border.color: mouse.containsMouse && hoverable ? Theme.border : Theme.borderSoft
    Behavior on border.color { ColorAnimation { duration: Theme.durFast } }

    scale: mouse.containsMouse && hoverable ? 1.01 : 1.0
    Behavior on scale { NumberAnimation { duration: Theme.durFast; easing.type: Easing.OutCubic } }

    MouseArea {
        id: mouse
        anchors.fill: parent
        hoverEnabled: root.hoverable
        propagateComposedEvents: true
    }

    // 左侧强调条（系统登录卡）
    Rectangle {
        visible: root.accentLeft
        width: 3
        radius: 1.5
        color: Theme.accent
        anchors { left: parent.left; top: parent.top; bottom: parent.bottom; margins: 0 }
    }

    Item { id: body; anchors.fill: parent }
}
