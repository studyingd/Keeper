import QtQuick
import ".."

// 四段强度条：level 0-4，分段过渡动画
Row {
    id: root
    property int level: 0
    spacing: 4

    Repeater {
        model: 4
        Rectangle {
            required property int index
            width: (root.width - 3 * root.spacing) / 4
            height: 5
            radius: height / 2
            color: root.level > 0 && index < root.level ? Theme.levelColors[root.level - 1] : Theme.surface2
            Behavior on color { ColorAnimation { duration: 500; easing.type: Easing.OutCubic } }
            scale: root.level > 0 && index < root.level ? 1.0 : 1.0
        }
    }
}
