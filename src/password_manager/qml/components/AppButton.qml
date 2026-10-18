import QtQuick
import QtQuick.Controls.Basic
import ".."

// 主按钮（渐变）/ 普通按钮 / 危险按钮 — hover 变色 + 按下缩放
Button {
    id: root
    property bool primary: false
    property bool ghost: false
    property string glyph: ""

    implicitHeight: 36
    hoverEnabled: true
    font { family: Theme.bodyFamily; pixelSize: 13 }

    background: Rectangle {
        radius: 10
        color: root.primary ? "transparent"
             : root.ghost ? (root.hovered ? Theme.surface2 : "transparent")
             : (root.pressed ? Theme.bgDeep : root.hovered ? Theme.btnHover : Theme.surface2)
        border.width: root.primary || root.ghost ? 0 : 1
        border.color: root.pressed ? Theme.accent : (root.hovered || root.primary ? Theme.borderStrong : Theme.border)
        Behavior on color { ColorAnimation { duration: Theme.durFast } }
        Behavior on border.color { ColorAnimation { duration: Theme.durFast } }

        // 主按钮渐变底（按下变暗）
        Rectangle {
            visible: root.primary
            anchors.fill: parent
            radius: parent.radius
            gradient: Gradient {
                GradientStop { position: 0; color: root.pressed ? "#5BC4B7" : root.hovered ? "#87F7E9" : Theme.primaryTop }
                GradientStop { position: 1; color: root.pressed ? "#3AB5A8" : root.hovered ? "#62E2D5" : Theme.primaryBottom }
            }
        }
    }

    contentItem: Row {
        spacing: 7
        leftPadding: 0
        Icon {
            name: root.glyph
            tint: root.primary ? Theme.accentInk : Theme.text
            pixel: 14
            visible: root.glyph !== ""
            anchors.verticalCenter: parent.verticalCenter
        }
        Text {
            anchors.verticalCenter: parent.verticalCenter
            text: root.text
            color: root.primary ? Theme.accentInk : Theme.text
            font { family: Theme.bodyFamily; pixelSize: 13; bold: true }
        }
    }

    // 按下时轻微缩小，松开弹回
    scale: root.pressed ? 0.97 : 1.0
    Behavior on scale { NumberAnimation { duration: 100; easing.type: Easing.OutCubic } }

    opacity: enabled ? 1.0 : 0.45
}
