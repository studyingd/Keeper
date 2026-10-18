import QtQuick
import QtQuick.Controls.Basic
import ".."

// 胶囊按钮：筛选 chips / 字符集勾选共用
AbstractButton {
    id: root
    property bool emphasized: false
    property string glyph: ""

    implicitHeight: 30
    implicitWidth: content.implicitWidth + 28
    hoverEnabled: true
    leftPadding: 13
    rightPadding: 13

    background: Rectangle {
        radius: height / 2
        color: root.checked ? Theme.accentDim : Theme.bgDeep
        border.width: 1
        border.color: root.checked ? Theme.accentBorder : (root.hovered ? Theme.borderStrong : Theme.borderSoft)
        Behavior on border.color { ColorAnimation { duration: Theme.durFast } }
    }
    contentItem: Row {
        id: content
        spacing: 7
        Icon {
            name: root.glyph !== "" && root.checked ? "check" : root.glyph
            tint: root.checked ? Theme.accent : Theme.textMuted
            pixel: 13
            anchors.verticalCenter: parent.verticalCenter
            visible: root.glyph !== ""
        }
        Text {
            anchors.verticalCenter: parent.verticalCenter
            text: root.text
            color: root.checked ? Theme.accent : (root.hovered ? Theme.text : Theme.textMuted)
            font.pixelSize: 12
            font.bold: true
            Behavior on color { ColorAnimation { duration: Theme.durFast } }
        }
    }
}
