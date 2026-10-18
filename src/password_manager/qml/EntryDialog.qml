import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "components"

// 新增/编辑资产：类型卡片（图标+名称横排）+ 表单 + 标签输入
Popup {
    id: root
    anchors.centerIn: parent
    modal: true
    closePolicy: Popup.CloseOnEscape
    padding: 26
    width: 480
    leftPadding: 28
    rightPadding: 28
    topPadding: 26
    bottomPadding: 26

    property string kind: "server"
    property int entryId: 0
    property var tags: []
    property var suggestions: []

    function openFor(entry) {
        if (entry) {
            kind = entry.kind
            entryId = entry.id
            nameField.text = entry.name
            addressField.text = entry.address
            tags = (entry.tags || []).slice()
        } else {
            kind = "server"
            entryId = 0
            nameField.text = ""
            addressField.text = ""
            tags = []
        }
        applyKind()
        open()
        nameField.forceActiveFocus()
    }

    function applyKind() {
        suggestions = kind === "server"
            ? ["MySQL", "Redis", "Nginx", "Docker", "数据库", "生产环境"]
            : ["云平台", "开发", "工作", "个人", "AI", "邮箱"]
        nameLabel.text = kind === "server" ? "显示名称（可选）" : "应用名称"
        nameField.placeholderText = kind === "server" ? "如：生产数据库服务器" : "如：阿里云、OpenAI、GitHub"
        addressLabel.text = kind === "server" ? "服务器 IP" : "网站地址（可选）"
        addressField.placeholderText = kind === "server" ? "如：192.168.1.101 或 192.168.1.101:2222" : "如：https://console.aliyun.com"
        saveButton.text = kind === "server" ? "保存服务器" : "保存应用"
    }

    enter: Transition {
        ParallelAnimation {
            NumberAnimation { property: "opacity"; from: 0; to: 1; duration: 220; easing.type: Easing.OutCubic }
            NumberAnimation { property: "scale"; from: 0.94; to: 1; duration: 300; easing.type: Easing.OutBack }
        }
    }
    exit: Transition {
        NumberAnimation { property: "opacity"; from: 1; to: 0; duration: 180; easing.type: Easing.OutCubic }
    }

    background: DialogSurface {}

    contentItem: ColumnLayout {
        id: box
        spacing: 14

            Text {
                text: root.entryId > 0 ? "编辑资产" : "新增资产"
                color: Theme.text
                font { family: Theme.displayFamily; pixelSize: 20; bold: true }
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 10
                Repeater {
                    model: [{ key: "server", label: "服务器", glyph: "server" }, { key: "application", label: "应用", glyph: "globe" }]
                    Rectangle {
                        required property var modelData
                        readonly property bool active: root.kind === modelData.key
                        Layout.fillWidth: true
                        implicitHeight: 46
                        radius: 14
                        color: active ? Theme.accentDeep : Theme.bgDeep
                        border.width: active ? 2 : 1
                        border.color: active ? Theme.accent : Theme.borderSoft
                        Behavior on color { ColorAnimation { duration: Theme.durFast } }

                        RowLayout {
                            anchors.fill: parent
                            anchors.margins: 14
                            spacing: 10
                            Icon { name: modelData.glyph; tint: active ? Theme.accent : Theme.textMuted; pixel: 18 }
                            Text { text: modelData.label; color: active ? Theme.text : Theme.textMuted; font { pixelSize: 14; bold: true } }
                            Item { Layout.fillWidth: true }
                        }
                        MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: { root.kind = modelData.key; root.applyKind() } }
                    }
                }
            }

            ColumnLayout {
                spacing: 9
                Layout.fillWidth: true
                Text { id: nameLabel; color: Theme.textMuted; font { pixelSize: 12; bold: true } }
                TextField {
                    id: nameField
                    Layout.fillWidth: true
                    color: Theme.text
                    font.pixelSize: 13
                    selectByMouse: true
                    background: Rectangle {
                        radius: 10; color: Theme.bgDeep; border.width: 1
                        border.color: nameField.activeFocus ? Theme.accent : Theme.borderSoft
                    }
                }
                Text { id: addressLabel; color: Theme.textMuted; font { pixelSize: 12; bold: true } }
                TextField {
                    id: addressField
                    Layout.fillWidth: true
                    color: Theme.text
                    font.pixelSize: 13
                    selectByMouse: true
                    background: Rectangle {
                        radius: 10; color: Theme.bgDeep; border.width: 1
                        border.color: addressField.activeFocus ? Theme.accent : Theme.borderSoft
                    }
                    onAccepted: saveButton.clicked()
                }
                Text { text: "标签（可选）"; color: Theme.textMuted; font { pixelSize: 12; bold: true } }

                // 标签胶囊 + 输入
                Rectangle {
                    Layout.fillWidth: true
                    implicitHeight: Math.max(40, tagFlow.implicitHeight + 10)
                    radius: 10
                    color: Theme.bgDeep
                    border.width: 1
                    border.color: tagInput.activeFocus ? Theme.accent : Theme.borderSoft

                    Flow {
                        id: tagFlow
                        anchors { fill: parent; margins: 5; leftMargin: 10; rightMargin: 10 }
                        spacing: 5

                        Repeater {
                            model: root.tags
                            Rectangle {
                                required property string modelData
                                radius: 12
                                implicitHeight: 26
                                implicitWidth: pillRow.implicitWidth + 16
                                color: Theme.accentDim
                                border.width: 1
                                border.color: Theme.accentBorder
                                RowLayout {
                                    id: pillRow
                                    anchors.centerIn: parent
                                    spacing: 5
                                    Text { text: modelData; color: Theme.accent; font { pixelSize: 12; bold: true } }
                                    Icon { name: "close"; tint: Theme.accent; pixel: 9
                                        MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor
                                            onClicked: { var t = root.tags.slice(); t.splice(t.indexOf(modelData), 1); root.tags = t } } }
                                }
                                MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor
                                    onClicked: { var t = root.tags.slice(); t.splice(t.indexOf(modelData), 1); root.tags = t } }
                            }
                        }
                        TextField {
                            id: tagInput
                            placeholderText: "输入后回车添加"
                            color: Theme.text
                            font.pixelSize: 12
                            implicitWidth: 140
                            background: null
                            selectByMouse: true
                            onAccepted: {
                                var parts = text.split(/[,，]/)
                                var t = root.tags.slice()
                                for (var i = 0; i < parts.length; i++) {
                                    var tag = parts[i].trim()
                                    if (tag && t.indexOf(tag) < 0 && t.length < 8) t.push(tag)
                                }
                                root.tags = t
                                text = ""
                            }
                        }
                    }
                }

                // 快捷标签
                Flow {
                    spacing: 6
                    Repeater {
                        model: root.suggestions
                        Chip {
                            required property string modelData
                            text: modelData
                            checkable: true
                            checked: root.tags.indexOf(modelData) >= 0
                            onToggled: {
                                var t = root.tags.slice()
                                var at = t.indexOf(modelData)
                                if (at >= 0) t.splice(at, 1)
                                else if (t.length < 8) t.push(modelData)
                                root.tags = t
                            }
                        }
                    }
                }
            }

            Text {
                visible: errorText.text !== ""
                id: errorText
                color: Theme.danger
                font.pixelSize: 12
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
                text: ""
            }

            RowLayout {
                Layout.fillWidth: true
                Item { Layout.fillWidth: true }
                AppButton { text: "取消"; onClicked: root.close() }
                AppButton {
                    id: saveButton
                    primary: true
                    onClicked: {
                        var result = controller.saveEntry(root.kind, nameField.text, addressField.text, root.tags, root.entryId)
                        if (result.ok) {
                            root.close()
                            controller.selectEntry(result.entryId)
                            toast.show(root.entryId > 0 ? "资产已更新" : "资产已创建")
                        } else {
                            errorText.text = result.error
                        }
                    }
                }
            }
    }
}
