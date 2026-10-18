import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "components"

// 三段式侧边栏：品牌+锁定 / 资产区（搜索+筛选+新增+列表） / 保险库状态+工具
Rectangle {
    id: root
    implicitWidth: 300

    gradient: Gradient {
        orientation: Gradient.Vertical
        GradientStop { position: 0; color: Theme.sidebarTop }
        GradientStop { position: 1; color: Theme.sidebarBottom }
    }

    // 点击品牌图标+文字返回总览（不覆盖右侧锁定按钮）
    MouseArea {
        anchors { left: parent.left; top: parent.top }
        width: 160
        height: 48
        cursorShape: Qt.PointingHandCursor
        onClicked: controller.clearSelection()
        ToolTip.visible: containsMouse
        ToolTip.text: "返回总览"
        ToolTip.delay: 500
        z: 10
    }

    // 右侧分割线
    Rectangle {
        anchors { right: parent.right; top: parent.top; bottom: parent.bottom }
        width: 1
        color: Theme.borderSoft
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 16
        spacing: 8

        // ── 第一段：品牌 + 锁定 ──
        RowLayout {
            Layout.fillWidth: true
            spacing: 10

            Rectangle {
                width: 32; height: 32; radius: 9
                gradient: Gradient {
                    GradientStop { position: 0; color: Theme.accentStrong }
                    GradientStop { position: 1; color: Theme.accent }
                }
                Icon { anchors.centerIn: parent; name: "shield-check"; tint: Theme.accentInk; pixel: 17 }
            }
            ColumnLayout {
                spacing: 0
                Layout.fillWidth: true
                Text {
                    text: "Keeper"
                    color: Theme.text
                    font { family: Theme.displayFamily; pixelSize: 15; bold: true }
                }
                Text {
                    text: "本地加密保险库"
                    color: Theme.textFaint
                    font { family: Theme.bodyFamily; pixelSize: 10 }
                }
            }
            Item { Layout.fillWidth: true }
            Button {
                implicitWidth: 30; implicitHeight: 30
                hoverEnabled: true
                flat: true
                background: Rectangle {
                    radius: 8
                    color: parent.hovered ? Theme.surface2 : "transparent"
                    border.width: 1
                    border.color: parent.hovered ? Theme.borderStrong : "transparent"
                }
                contentItem: Icon { anchors.centerIn: parent; name: "lock"; tint: Theme.textMuted; pixel: 14 }
                onClicked: controller.lock()
                ToolTip.visible: hovered; ToolTip.text: "锁定保险库"; ToolTip.delay: 400
            }
        }

        Rectangle { Layout.fillWidth: true; height: 1; color: Theme.borderSoft }

        // ── 搜索 ──
        Rectangle {
            Layout.fillWidth: true
            implicitHeight: 36
            radius: 10
            color: Theme.bgDeep
            border.width: 1
            border.color: searchField.activeFocus ? Theme.accent : Theme.borderSoft
            Behavior on border.color { ColorAnimation { duration: Theme.durFast } }

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 12
                anchors.rightMargin: 10
                spacing: 8

                Icon {
                    name: "search"
                    tint: searchField.activeFocus ? Theme.accent : Theme.textFaint
                    pixel: 14
                }
                TextField {
                    id: searchField
                    Layout.fillWidth: true
                    placeholderText: "搜索名称、IP 或标签…"
                    placeholderTextColor: Theme.textFaint
                    color: Theme.text
                    font { family: Theme.bodyFamily; pixelSize: 13 }
                    selectByMouse: true
                    background: null
                    verticalAlignment: TextInput.AlignVCenter
                    leftPadding: 0; rightPadding: 0; topPadding: 0; bottomPadding: 0
                    onTextChanged: controller.Search = text
                    Connections {
                        target: controller
                        function onVaultStateChanged() {
                            if (controller.vaultState !== "unlocked") searchField.text = ""
                        }
                    }
                }
            }
        }

        // ── 筛选 + 新增（一行放下） ──
        RowLayout {
            Layout.fillWidth: true
            spacing: 6

            Chip {
                text: "全部"
                checkable: true
                checked: controller.FilterKind === "all"
                onToggled: controller.FilterKind = "all"
            }
            Chip {
                text: "服务器"
                checkable: true
                checked: controller.FilterKind === "server"
                onToggled: controller.FilterKind = "server"
            }
            Chip {
                text: "应用"
                checkable: true
                checked: controller.FilterKind === "application"
                onToggled: controller.FilterKind = "application"
            }
        }

        AppButton {
            Layout.fillWidth: true
            primary: true
            glyph: "plus"
            text: "新增资产"
            implicitHeight: 36
            onClicked: root.addRequested()
        }

        // ── 资产列表（无滚动条，滚轮滚动） ──
        ListView {
            id: list
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.topMargin: 4
            clip: true
            spacing: 1
            boundsBehavior: Flickable.StopAtBounds
            // 滚动条只在滚动时短暂显示，不遮挡内容
            ScrollBar.vertical: ScrollBar {
                policy: ScrollBar.AsNeeded
                implicitWidth: 4
                interactive: false
                contentItem: Rectangle {
                    radius: 2
                    color: Theme.border
                }
            }
            model: controller.entriesModel

            section.property: "section"
            section.delegate: Item {
                width: list.width
                height: 26

                Text {
                    anchors {
                        left: parent.left; leftMargin: 10
                        verticalCenter: parent.verticalCenter
                    }
                    text: section
                    color: Theme.textFaint
                    font { family: Theme.bodyFamily; pixelSize: 10; bold: true; letterSpacing: 1.2 }
                }
            }

            delegate: Rectangle {
                id: row
                required property int eid
                required property string kind
                required property string name
                required property string subtitle
                required property int count
                required property string section

                // 行宽留 4px 给滚动条，不越界
                width: list.width - 4
                x: 0
                height: 52
                radius: 10
                color: selected ? Theme.rowSelected : (hover.hovered ? Theme.rowHover : "transparent")
                Behavior on color { ColorAnimation { duration: Theme.durFast } }

                readonly property bool selected: controller.selectedEntry.id === eid

                Rectangle {
                    visible: row.selected
                    width: 3; radius: 1.5
                    color: Theme.accent
                    anchors { left: parent.left; top: parent.top; bottom: parent.bottom; topMargin: 8; bottomMargin: 8; leftMargin: 0 }
                }

                MouseArea {
                    id: hover
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: controller.selectEntry(row.eid)
                }

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 10
                    anchors.rightMargin: 6
                    spacing: 9

                    Rectangle {
                        width: 28; height: 28; radius: 8
                        color: Theme.surface2
                        border.width: 1
                        border.color: row.selected ? Theme.accentBorder : Theme.borderSoft
                        Icon { anchors.centerIn: parent; name: row.kind === "server" ? "server" : "globe"; tint: row.selected ? Theme.accent : Theme.textMuted; pixel: 14 }
                    }
                    ColumnLayout {
                        spacing: 0
                        Layout.fillWidth: true
                        Text {
                            Layout.fillWidth: true
                            text: row.name
                            color: Theme.text
                            font { family: Theme.bodyFamily; pixelSize: 13; bold: true }
                            elide: Text.ElideRight
                        }
                        Text {
                            Layout.fillWidth: true
                            visible: row.subtitle !== ""
                            text: row.subtitle
                            color: Theme.textFaint
                            font { family: Theme.monoFamily; pixelSize: 10 }
                            elide: Text.ElideRight
                        }
                    }
                    // 计数（选中时隐藏，左侧已有强调条）
                    Text {
                        visible: !row.selected && row.count > 0
                        text: row.count
                        color: Theme.textFaint
                        font { family: Theme.monoFamily; pixelSize: 10 }
                    }
                }
            }

            // 空列表
            Text {
                visible: list.count === 0 && controller.vaultState === "unlocked"
                anchors.centerIn: parent
                text: controller.Search !== "" ? "没有匹配的资产" : "还没有资产\n点上方「新增资产」创建"
                color: Theme.textFaint
                font { family: Theme.bodyFamily; pixelSize: 12 }
                horizontalAlignment: Text.AlignHCenter
                lineHeight: 1.5
            }
        }

        Rectangle { Layout.fillWidth: true; height: 1; color: Theme.borderSoft }

        // ── 第三段：状态 + 工具 ──
        RowLayout {
            Layout.fillWidth: true
            spacing: 8

            Rectangle {
                width: 5; height: 5; radius: 2.5
                color: Theme.ok
                SequentialAnimation on opacity {
                    loops: Animation.Infinite
                    NumberAnimation { to: 0.4; duration: 1400; easing.type: Easing.InOutSine }
                    NumberAnimation { to: 1.0; duration: 1400; easing.type: Easing.InOutSine }
                }
            }
            Text {
                Layout.fillWidth: true
                text: `已解锁 · ${controller.autoLockMinutes} 分钟后自动锁定`
                color: Theme.textFaint
                font { family: Theme.bodyFamily; pixelSize: 10 }
                elide: Text.ElideRight
            }
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: 6

            AppButton {
                Layout.fillWidth: true
                glyph: "download"
                text: "导出"
                implicitHeight: 30
                font { family: Theme.bodyFamily; pixelSize: 12 }
                onClicked: root.exportRequested()
                ToolTip.visible: hovered; ToolTip.text: "导出全部项目到 Excel（含明文密码）"; ToolTip.delay: 400
            }
            AppButton {
                Layout.fillWidth: true
                glyph: "key"
                text: "主密码"
                implicitHeight: 30
                font { family: Theme.bodyFamily; pixelSize: 12 }
                onClicked: root.rekeyRequested()
                ToolTip.visible: hovered; ToolTip.text: "用新主密码重新加密整个保险库"; ToolTip.delay: 400
            }
        }
    }

    signal addRequested()
    signal exportRequested()
    signal rekeyRequested()
}
