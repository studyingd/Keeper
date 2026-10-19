import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "components"

// 详情页：头部瓷砖/chips/标签 + 凭据卡列表
Flickable {
    id: root
    contentWidth: width
    contentHeight: column.implicitHeight + 56
    clip: true
    boundsBehavior: Flickable.StopAtBounds
    ScrollBar.vertical: ScrollBar {
        policy: ScrollBar.AsNeeded
        implicitWidth: 8
        contentItem: Rectangle {
            radius: 4
            color: parent.hovered ? Theme.borderStrong : Theme.border
        }
    }

    property var entry: controller.selectedEntry

    signal editEntryRequested()
    signal deleteEntryRequested()
    signal addCredentialRequested()
    signal addLoginRequested()
    signal editCredentialRequested(var credential)
    signal deleteCredentialRequested(var credential)
    signal goHomeRequested()

    ColumnLayout {
        id: column
        x: 34; y: 24
        width: root.width - 68
        spacing: 14

        // ── 头部 ──
        RowLayout {
            Layout.fillWidth: true
            spacing: 14

            Rectangle {
                width: 50; height: 50; radius: 15
                gradient: Gradient {
                    GradientStop { position: 0; color: Theme.accentDeep }
                    GradientStop { position: 1; color: Theme.surface }
                }
                border.width: 1
                border.color: Theme.accentBorder
                Icon { anchors.centerIn: parent; name: root.entry.kind === "server" ? "server" : "globe"; tint: Theme.accent; pixel: 24 }
            }

            ColumnLayout {
                spacing: 4
                Layout.fillWidth: true
                Text { text: root.entry.eyebrow || ""; color: Theme.accent; font { pixelSize: 11; bold: true; letterSpacing: 1.4 } }
                Text {
                    text: root.entry.name || ""
                    color: Theme.text
                    font { family: Theme.displayFamily; pixelSize: 27; bold: true }
                    elide: Text.ElideRight
                    Layout.fillWidth: true
                }
                RowLayout {
                    spacing: 7
                    Repeater {
                        model: {
                            var chips = []
                            if (root.entry.address) chips.push({ text: root.entry.address, mono: true, tag: false, clickable: root.entry.kind === "application" })
                            chips.push({ text: `${root.entry.credentialCount} 个项目`, mono: false, tag: false })
                            var tags = root.entry.tags || []
                            for (var i = 0; i < Math.min(tags.length, 4); i++)
                                chips.push({ text: tags[i], mono: false, tag: true })
                            return chips
                        }
                        Rectangle {
                            id: chip
                            required property var modelData
                            readonly property bool clickable: modelData.clickable === true
                            radius: 12
                            implicitHeight: 22
                            implicitWidth: chipText.implicitWidth + 22
                            color: modelData.tag ? Theme.accentDim : (clickable && chipHover.containsMouse ? Theme.accentDim : Theme.surface)
                            border.width: 1
                            border.color: modelData.tag ? Theme.accentBorder : (clickable && chipHover.containsMouse ? Theme.accentBorder : Theme.borderSoft)
                            Text {
                                id: chipText
                                anchors.centerIn: parent
                                text: modelData.tag ? `#${modelData.text}` : modelData.text
                                color: modelData.tag ? Theme.accent : (chip.clickable ? Theme.accent : Theme.textMuted)
                                font { family: modelData.mono ? Theme.monoFamily : Theme.bodyFamily; pixelSize: modelData.mono ? 11 : 12 }
                            }
                            // 应用的网站地址 chip 可点击直达；服务器保存的是 IP，不进浏览器，保持静态展示
                            MouseArea {
                                id: chipHover
                                enabled: chip.clickable
                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onClicked: controller.openAddress(root.entry.address)
                            }
                            ToolTip.visible: chipHover.containsMouse && chip.clickable
                            ToolTip.text: "点击在浏览器中打开"
                        }
                    }
                    Item { Layout.fillWidth: true }
                }
            }

            RowLayout {
                spacing: 8
                RoundButton {
                    implicitWidth: 32; implicitHeight: 32
                    hoverEnabled: true
                    background: Rectangle { radius: 8; color: Theme.surface2; border.width: 1; border.color: Theme.border }
                    contentItem: Icon { anchors.centerIn: parent; name: "pencil"; tint: Theme.textMuted; pixel: 14 }
                    onClicked: root.editEntryRequested()
                    ToolTip.visible: hovered; ToolTip.text: "编辑资产"
                }
                RoundButton {
                    implicitWidth: 32; implicitHeight: 32
                    hoverEnabled: true
                    background: Rectangle { radius: 8; color: parent.hovered ? Theme.dangerDim : Theme.surface2; border.width: 1; border.color: Theme.border }
                    contentItem: Icon { anchors.centerIn: parent; name: "trash"; tint: Theme.danger; pixel: 14 }
                    onClicked: root.deleteEntryRequested()
                    ToolTip.visible: hovered; ToolTip.text: "删除资产"
                }
                AppButton {
                    visible: root.entry.kind === "server"
                    text: "+ 系统登录"
                    onClicked: root.addLoginRequested()
                }
                AppButton {
                    primary: true
                    text: "+ 新增项目"
                    onClicked: root.addCredentialRequested()
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            height: 1
            color: Theme.borderSoft
        }

        // ── 凭据卡 ──
        Repeater {
            model: controller.credentials

            Card {
                id: card
                required property var modelData
                required property int index
                Layout.fillWidth: true
                implicitHeight: cardBox.implicitHeight + 30

                ColumnLayout {
                    id: cardBox
                    anchors.fill: parent
                    anchors { leftMargin: 20; rightMargin: 20; topMargin: 15; bottomMargin: 15 }
                    spacing: 8

                    RowLayout {
                        spacing: 9
                        Layout.fillWidth: true
                        Rectangle {
                            width: 30; height: 30; radius: 9
                            color: card.modelData.isLogin ? Theme.accentDeep : Theme.surface2
                            border.width: 1
                            border.color: card.modelData.isLogin ? Theme.accentBorder : Theme.borderSoft
                            Icon { anchors.centerIn: parent; name: card.modelData.icon; tint: card.modelData.isLogin ? Theme.accent : Theme.textMuted; pixel: 15 }
                        }
                        Text {
                            text: card.modelData.label
                            color: Theme.text
                            font { family: Theme.displayFamily; pixelSize: 15; bold: true }
                        }
                        Rectangle {
                            visible: card.modelData.badge !== ""
                            radius: 7
                            implicitHeight: 18
                            implicitWidth: badgeText.implicitWidth + 16
                            color: Theme.accentDim
                            border.width: 1
                            border.color: Theme.accentBorder
                            Text { id: badgeText; anchors.centerIn: parent; text: card.modelData.badge; color: Theme.accent; font { pixelSize: 10; bold: true } }
                        }
                        Item { Layout.fillWidth: true }

                        // hover 才出现的低频操作
                        Row {
                            spacing: 2
                            opacity: card.hovered ? 1 : 0
                            Behavior on opacity { NumberAnimation { duration: Theme.durFast } }
                            RoundButton {
                                implicitWidth: 28; implicitHeight: 28
                                hoverEnabled: true
                                background: Rectangle { radius: 7; color: parent.hovered ? Theme.surface2 : "transparent" }
                                contentItem: Icon { anchors.centerIn: parent; name: "chevron-up"; tint: Theme.textFaint; pixel: 14 }
                                enabled: index > 0
                                opacity: enabled ? 1 : 0.3
                                onClicked: controller.moveCredential(card.modelData.id, "up")
                            }
                            RoundButton {
                                implicitWidth: 28; implicitHeight: 28
                                hoverEnabled: true
                                background: Rectangle { radius: 7; color: parent.hovered ? Theme.surface2 : "transparent" }
                                contentItem: Icon { anchors.centerIn: parent; name: "chevron-down"; tint: Theme.textFaint; pixel: 14 }
                                enabled: index < controller.credentials.length - 1
                                opacity: enabled ? 1 : 0.3
                                onClicked: controller.moveCredential(card.modelData.id, "down")
                            }
                            RoundButton {
                                implicitWidth: 28; implicitHeight: 28
                                hoverEnabled: true
                                background: Rectangle { radius: 7; color: parent.hovered ? Theme.surface2 : "transparent" }
                                contentItem: Icon { anchors.centerIn: parent; name: "pencil"; tint: Theme.textFaint; pixel: 14 }
                                onClicked: root.editCredentialRequested(card.modelData)
                            }
                            RoundButton {
                                implicitWidth: 28; implicitHeight: 28
                                hoverEnabled: true
                                background: Rectangle { radius: 7; color: parent.hovered ? Theme.dangerDim : "transparent" }
                                contentItem: Icon { anchors.centerIn: parent; name: "trash"; tint: Theme.danger; pixel: 14 }
                                onClicked: root.deleteCredentialRequested(card.modelData)
                            }
                        }
                    }

                    RowLayout {
                        spacing: 9
                        Layout.leftMargin: 39
                        Text {
                            text: card.modelData.username
                            color: Theme.textMuted
                            font { family: Theme.monoFamily; pixelSize: 12; bold: true }
                        }
                        Text { visible: card.modelData.extra !== ""; text: "·"; color: Theme.textFaint }
                        Text {
                            visible: card.modelData.extra !== ""
                            Layout.fillWidth: true
                            text: card.modelData.extra
                            color: Theme.textFaint
                            font { family: Theme.monoFamily; pixelSize: 12 }
                            elide: Text.ElideRight
                        }
                        Text { visible: card.modelData.hasPassword; text: "·"; color: Theme.textFaint }
                        Text {
                            visible: card.modelData.hasPassword
                            text: card.revealed ? card.modelData.password : card.modelData.masked
                            color: card.revealed ? Theme.text : Theme.textFaint
                            font { family: Theme.monoFamily; pixelSize: 12; letterSpacing: card.revealed ? 0 : 1.5 }
                            MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: card.revealed = !card.revealed }
                        }
                        Icon {
                            visible: card.modelData.hasPassword
                            name: card.revealed ? "eye-off" : "eye"
                            tint: Theme.textFaint
                            pixel: 13
                            MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: card.revealed = !card.revealed }
                        }
                    }

                    RowLayout {
                        spacing: 8
                        Layout.leftMargin: 39
                        AppButton {
                            glyph: "copy"
                            text: "复制用户名"
                            onClicked: controller.copyCredentialSecret(card.modelData.id, "username")
                        }
                        AppButton {
                            glyph: "copy"
                            text: "复制密码"
                            onClicked: controller.copyCredentialSecret(card.modelData.id, "password")
                        }
                        AppButton {
                            visible: card.modelData.showConnect
                            primary: true
                            glyph: "terminal"
                            text: card.modelData.connectLabel
                            onClicked: controller.connectLogin(card.modelData.id)
                        }
                        AppButton {
                            visible: card.modelData.url !== ""
                            primary: true
                            glyph: "external"
                            text: "访问网站"
                            onClicked: controller.openAddress(card.modelData.url)
                        }
                        Item { Layout.fillWidth: true }
                    }
                }

                property bool revealed: false
            }
        }

        // 空状态
        Card {
            visible: controller.credentials.length === 0
            Layout.fillWidth: true
            implicitHeight: emptyText.implicitHeight + 44
            Text {
                id: emptyText
                anchors.centerIn: parent
                text: root.entry.kind === "server" ? "还没有项目。点右上角「+ 新增项目」添加第一条凭据。" : "还没有项目。点右上角「+ 新增项目」添加第一条凭据。"
                color: Theme.textMuted
                font.pixelSize: 13
            }
        }

        Item { Layout.fillHeight: true }
    }
}
