import QtQuick
import QtQuick.Controls.Basic
import ".."

// 字符集自由勾选：内部持有状态，至少保留一类的规则在这里强制
Row {
    id: root
    property var initialKeys: ["digits", "letters", "symbols"]
    property var selectedKeys: initialKeys
    signal selectionChanged

    spacing: 7

    Repeater {
        model: controller.charsets

        Chip {
            required property var modelData
            text: modelData.label
            checkable: true
            checked: root.selectedKeys.indexOf(modelData.key) >= 0
            // 只剩最后一个时禁用，字符池永不为空
            enabled: !checked || root.selectedKeys.length > 1
            onToggled: {
                var keys = root.selectedKeys.slice()
                var at = keys.indexOf(modelData.key)
                if (at >= 0) {
                    if (keys.length > 1) keys.splice(at, 1)
                } else {
                    keys.push(modelData.key)
                }
                root.selectedKeys = keys
                root.selectionChanged()
            }
        }
    }
}
