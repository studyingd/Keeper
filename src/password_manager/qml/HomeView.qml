import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "components"

// 首页仪表盘：统计 + 生成器 + 最近访问 + 安全状态
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

    property var generated: ""
    property var selectedSets: ["digits", "letters", "symbols"]
    property int lengthValue: 12

    readonly property string mode: selectedSets.join("+")

    ColumnLayout {
        id: column
        x: 34; y: 28
        width: root.width - 68
        spacing: 18

        RowLayout {
            Layout.fillWidth: true
            spacing: 16
            ColumnLayout {
                spacing: 5
                Text { text: "保险库总览"; color: Theme.accent; font { pixelSize: 11; bold: true; letterSpacing: 1.4 } }
                Text {
                    text: "一切安全，一切就绪"
                    color: Theme.text
                    font { family: Theme.displayFamily; pixelSize: 27; bold: true }
                }
                Text {
                    text: `${controller.serversCount} 台服务器 · ${controller.applicationsCount} 个应用 · ${controller.credentialsCount} 条凭据，整库 SQLCipher 加密`
                    color: Theme.textMuted
                    font.pixelSize: 13
                }
            }
            Item { Layout.fillWidth: true }
        }

        // 统计卡片
        RowLayout {
            Layout.fillWidth: true
            spacing: 12
            Repeater {
                model: [
                    { value: controller.serversCount, caption: "服务器", glyph: "server" },
                    { value: controller.applicationsCount, caption: "应用", glyph: "globe" },
                    { value: controller.credentialsCount, caption: "凭据总数", glyph: "lock" },
                    { value: controller.autoLockMinutes, caption: "分钟", glyph: "clock" },
                ]
                Card {
                    required property var modelData
                    Layout.fillWidth: true
                    implicitHeight: 92
                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 16
                        spacing: 3
                        Text {
                            text: modelData.value
                            color: Theme.text
                            font { family: Theme.displayFamily; pixelSize: 30; bold: true }
                        }
                        RowLayout {
                            spacing: 6
                            Icon { name: modelData.glyph; tint: Theme.textFaint; pixel: 13 }
                            Text { text: modelData.caption; color: Theme.textMuted; font.pixelSize: 12 }
                            Item { Layout.fillWidth: true }
                        }
                    }
                }
            }
        }

        // 两栏（宽屏）或上下堆叠（窄屏）
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 12

            // 生成器
            Card {
                Layout.fillWidth: true
                Layout.minimumWidth: 340
                implicitHeight: generatorBox.implicitHeight + 36
                ColumnLayout {
                    id: generatorBox
                    anchors.fill: parent
                    anchors.margins: 22
                    spacing: 12

                    Text { text: "随机密码生成器"; color: Theme.text; font { family: Theme.displayFamily; pixelSize: 15; bold: true } }

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 8
                        Rectangle {
                            Layout.fillWidth: true
                            radius: 10
                            color: Theme.bgDeep
                            border.width: 1
                            border.color: Theme.borderSoft
                            implicitHeight: 44
                            Text {
                                anchors.fill: parent
                                anchors.leftMargin: 14
                                verticalAlignment: Text.AlignVCenter
                                text: root.generated === "" ? "生成的密码会显示在这里" : root.generated
                                color: root.generated === "" ? Theme.textFaint : Theme.text
                                font { family: Theme.monoFamily; pixelSize: 16; bold: true }
                                elide: Text.ElideRight
                            }
                        }
                        RoundButton {
                            implicitWidth: 34; implicitHeight: 34
                            hoverEnabled: true
                            enabled: root.generated !== ""
                            background: Rectangle { radius: 8; color: parent.hovered ? Theme.surface2 : "transparent" }
                            contentItem: Icon { anchors.centerIn: parent; name: "copy"; tint: Theme.textMuted; pixel: 16 }
                            onClicked: controller.copyGeneratedPassword(root.generated)
                            ToolTip.visible: hovered
                            ToolTip.text: "复制（30 秒后自动清除）"
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 10
                        StrengthMeter {
                            Layout.fillWidth: true
                            level: root.strengthLevel
                        }
                        Text {
                            text: root.strengthLevel > 0 ? controller.strengthLabels[root.strengthLevel - 1] : "—"
                            color: Theme.textMuted
                            font.pixelSize: 12
                            Layout.preferredWidth: 36
                            horizontalAlignment: Text.AlignRight
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 14
                        CharSetToggles {
                            id: generatorToggles
                            onSelectionChanged: root.regenerate()
                        }
                        Item { Layout.fillWidth: true }
                        Text { text: "长度"; color: Theme.textMuted; font.pixelSize: 12 }
                        Slider {
                            id: lengthSlider
                            from: 1; to: 128
                            value: root.lengthValue
                            implicitWidth: 140
                            onMoved: { root.lengthValue = value; root.regenerate() }
                            background: Rectangle {
                                y: parent.height / 2 - 2; width: parent.availableWidth; height: 4; radius: 2
                                color: Theme.surface2
                                Rectangle {
                                    width: parent.width * parent.position; height: parent.height; radius: 2
                                    color: Theme.accent
                                }
                            }
                            handle: Rectangle {
                                x: parent.leftPadding + parent.availableWidth * parent.position - width / 2
                                y: parent.height / 2 - height / 2
                                width: 14; height: 14; radius: 7
                                color: Theme.text
                            }
                        }
                        Text { text: root.lengthValue; color: Theme.text; font { family: Theme.monoFamily; pixelSize: 13 } }
                        AppButton {
                            primary: true
                            text: "生成密码"
                            onClicked: root.regenerate()
                        }
                    }
                }
            }

            // 右列：最近访问（宽屏在右侧，窄屏在下方）
            Card {
                Layout.fillWidth: true
                Layout.minimumWidth: 280
                Layout.preferredHeight: recentBox.implicitHeight + 30
                Layout.maximumHeight: 320
                    ColumnLayout {
                        id: recentBox
                        anchors.fill: parent
                        anchors.margins: 18
                        spacing: 8
                        Text { text: "最近访问"; color: Theme.text; font { family: Theme.displayFamily; pixelSize: 15; bold: true } }
                        Repeater {
                            model: controller.recentUses
                            ColumnLayout {
                                required property var modelData
                                spacing: 1
                                Layout.fillWidth: true
                                Text { Layout.fillWidth: true; text: modelData.title; color: Theme.text; font { pixelSize: 13; bold: true } elide: Text.ElideRight }
                                Text { Layout.fillWidth: true; text: modelData.sub; color: Theme.textFaint; font.pixelSize: 11; elide: Text.ElideRight }
                            }
                        }
                        Text {
                            visible: controller.recentUses.length === 0
                            text: "复制密码或发起连接后，这里会记录最近的操作。"
                            color: Theme.textFaint
                            font.pixelSize: 12
                            wrapMode: Text.WordWrap
                            Layout.fillWidth: true
                        }
                    }
                }
            }
    }

    readonly property int strengthLevel: generated !== "" ? controller.strengthFor(mode, lengthValue) : 0

    // regenerate 直接读组件的 selectedKeys，不走 mode 绑定
    // （信号触发时绑定可能还没重新求值，导致读到旧值）
    function regenerate() {
        var keys = generatorToggles.selectedKeys.join("+")
        generated = controller.generate(keys, lengthValue)
    }

    Component.onCompleted: regenerate()
}
