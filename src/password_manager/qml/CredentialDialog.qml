import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "components"

// 新增/编辑项目（含系统登录模式）：内嵌与首页一致的生成器
// 所有字段统一结构：label(12px muted) → field(40px, radius10, bgDeep, border)
Popup {
    id: root
    anchors.centerIn: parent
    modal: true
    closePolicy: Popup.CloseOnEscape
    padding: 0
    width: 480
    leftPadding: 28
    rightPadding: 28
    topPadding: 26
    bottomPadding: 26

    property bool loginMode: false
    property int credentialId: 0
    property int entryId: 0
    property bool isRdp: false
    property int lengthValue: 12

    readonly property string mode: toggles.selectedKeys.join("+")
    readonly property int strengthLevel: passwordField.text !== "" ? controller.strengthFor(mode, lengthValue) : 0

    function openFor(entry, credential, login) {
        entryId = entry.id
        loginMode = login || (credential && credential.isLogin)
        if (credential) {
            credentialId = credential.id
            nameField.text = credential.label
            userField.text = credential.username
            passwordField.text = credential.password
            extraField.text = credential.extra
            isRdp = credential.kind === "rdp"
        } else {
            credentialId = 0
            nameField.text = ""
            userField.text = loginMode ? "root" : ""
            passwordField.text = ""
            extraField.text = ""
            isRdp = false
        }
        open()
        ;(loginMode ? userField : nameField).forceActiveFocus()
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
        spacing: 10

        // ── 标题 ──
        Text {
            text: root.loginMode ? (root.credentialId > 0 ? "编辑系统登录" : "新增系统登录")
                 : (root.credentialId > 0 ? "编辑项目" : "新增项目")
            color: Theme.text
            font { family: Theme.displayFamily; pixelSize: 20; bold: true }
            Layout.bottomMargin: 6
        }

        // ── 登录平台（仅登录模式） ──
        ColumnLayout {
            visible: root.loginMode
            Layout.fillWidth: true
            spacing: 6

            Text { text: "登录平台"; color: Theme.textMuted; font { family: Theme.bodyFamily; pixelSize: 12; bold: true } }
            RowLayout {
                Layout.fillWidth: true
                spacing: 14
                ButtonGroup { id: platform; buttons: [sshRadio, rdpRadio] }
                RadioButton {
                    id: sshRadio
                    text: "Linux（SSH）"
                    checked: !root.isRdp
                    onToggled: {
                        if (userField.text === "" || userField.text === "administrator") userField.text = "root"
                        root.isRdp = false
                    }
                }
                RadioButton {
                    id: rdpRadio
                    text: "Windows（RDP）"
                    checked: root.isRdp
                    onToggled: {
                        if (userField.text === "" || userField.text === "root") userField.text = "administrator"
                        root.isRdp = true
                    }
                }
                Item { Layout.fillWidth: true }
            }
        }

        // ── 项目名称（仅非登录模式） ──
        ColumnLayout {
            visible: !root.loginMode
            Layout.fillWidth: true
            spacing: 6

            Text { text: "项目名称"; color: Theme.textMuted; font { family: Theme.bodyFamily; pixelSize: 12; bold: true } }
            TextField {
                id: nameField
                Layout.fillWidth: true
                implicitHeight: 40
                placeholderText: "如：MySQL、网站后台"
                color: Theme.text
                font { family: Theme.bodyFamily; pixelSize: 13 }
                selectByMouse: true
                leftPadding: 12
                background: Rectangle {
                    radius: 10; color: Theme.bgDeep; border.width: 1
                    border.color: nameField.activeFocus ? Theme.accent : Theme.borderSoft
                }
            }
        }

        // ── 用户名 ──
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 6

            Text {
                text: root.loginMode ? "登录账号" : "用户名（可选）"
                color: Theme.textMuted; font { family: Theme.bodyFamily; pixelSize: 12; bold: true }
            }
            TextField {
                id: userField
                Layout.fillWidth: true
                implicitHeight: 40
                placeholderText: "如：root / db_admin"
                color: Theme.text
                font { family: Theme.bodyFamily; pixelSize: 13 }
                selectByMouse: true
                leftPadding: 12
                background: Rectangle {
                    radius: 10; color: Theme.bgDeep; border.width: 1
                    border.color: userField.activeFocus ? Theme.accent : Theme.borderSoft
                }
            }
        }

        // ── 密码 ──
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 6

            // 标签行：左标签 + 右侧生成按钮
            RowLayout {
                Layout.fillWidth: true
                Text { text: "密码（可选）"; color: Theme.textMuted; font { family: Theme.bodyFamily; pixelSize: 12; bold: true } }
                Item { Layout.fillWidth: true }
                AppButton {
                    primary: true
                    text: "生成"
                    implicitHeight: 26
                    font { family: Theme.bodyFamily; pixelSize: 12 }
                    onClicked: {
                        var keys = toggles.selectedKeys.join("+")
                        passwordField.text = controller.generate(keys, root.lengthValue)
                        passwordField.revealed = true
                    }
                }
            }
            // 密码输入框：与其他字段完全一致的结构，眼睛图标叠加在右侧
            TextField {
                id: passwordField
                Layout.fillWidth: true
                implicitHeight: 40
                echoMode: passwordField.revealed ? TextInput.Normal : TextInput.Password
                property bool revealed: false
                color: Theme.text
                font { family: Theme.monoFamily; pixelSize: 13 }
                selectByMouse: true
                leftPadding: 12
                rightPadding: 42
                background: Rectangle {
                    radius: 10; color: Theme.bgDeep; border.width: 1
                    border.color: passwordField.activeFocus ? Theme.accent : Theme.borderSoft
                }
                onAccepted: saveButton.clicked()

                // 眼睛图标叠加在输入框右端（与边框内嵌）
                Icon {
                    anchors {
                        right: parent.right; rightMargin: 12
                        verticalCenter: parent.verticalCenter
                    }
                    name: passwordField.revealed ? "eye-off" : "eye"
                    tint: passwordField.activeFocus ? Theme.accent : Theme.textFaint
                    pixel: 15
                    Behavior on tint { ColorAnimation { duration: Theme.durFast } }
                    MouseArea {
                        anchors.fill: parent
                        anchors.margins: -6
                        cursorShape: Qt.PointingHandCursor
                        onClicked: passwordField.revealed = !passwordField.revealed
                    }
                }
            }
        }

        // ── 生成器（字符集 + 长度） ──
        RowLayout {
            Layout.fillWidth: true
            Layout.topMargin: 2
            spacing: 12
            CharSetToggles {
                id: toggles
            }
            Item { Layout.fillWidth: true }
            Text { text: "长度"; color: Theme.textMuted; font { family: Theme.bodyFamily; pixelSize: 12 } }
            Slider {
                from: 1; to: 128
                value: root.lengthValue
                implicitWidth: 110
                onMoved: root.lengthValue = value
                background: Rectangle {
                    y: parent.height / 2 - 2
                    width: parent.availableWidth
                    height: 4
                    radius: 2
                    color: Theme.surface2
                    Rectangle {
                        width: parent.width * parent.position
                        height: parent.height
                        radius: 2
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
        }

        // ── 强度条 ──
        RowLayout {
            Layout.fillWidth: true
            spacing: 10
            StrengthMeter { Layout.fillWidth: true; level: root.strengthLevel }
            Text {
                text: root.strengthLevel > 0 ? controller.strengthLabels[root.strengthLevel - 1] : "—"
                color: Theme.textMuted; font { family: Theme.bodyFamily; pixelSize: 12 }
                Layout.preferredWidth: 36
                horizontalAlignment: Text.AlignRight
            }
        }

        // ── 说明（仅非登录模式） ──
        ColumnLayout {
            visible: !root.loginMode
            Layout.fillWidth: true
            spacing: 6

            Text { text: "说明 / 网站地址（可选）"; color: Theme.textMuted; font { family: Theme.bodyFamily; pixelSize: 12; bold: true } }
            TextField {
                id: extraField
                Layout.fillWidth: true
                implicitHeight: 40
                placeholderText: "如：https://admin.example.com"
                color: Theme.text
                font { family: Theme.bodyFamily; pixelSize: 13 }
                selectByMouse: true
                leftPadding: 12
                background: Rectangle {
                    radius: 10; color: Theme.bgDeep; border.width: 1
                    border.color: extraField.activeFocus ? Theme.accent : Theme.borderSoft
                }
            }
        }

        // ── 错误 ──
        Text {
            id: errorText
            visible: text !== ""
            color: Theme.danger
            font { family: Theme.bodyFamily; pixelSize: 12 }
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
            text: ""
        }

        // ── 按钮（右对齐） ──
        RowLayout {
            Layout.fillWidth: true
            Layout.topMargin: 4
            Item { Layout.fillWidth: true }
            AppButton { text: "取消"; onClicked: root.close() }
            AppButton {
                id: saveButton
                primary: true
                text: "保存项目"
                onClicked: {
                    var kind = root.loginMode ? (root.isRdp ? "rdp" : "ssh") : "custom"
                    var label = root.loginMode ? "系统登录账号" : nameField.text
                    var extra = root.loginMode ? "" : extraField.text
                    var result = controller.saveCredential(root.entryId, kind, label, userField.text, passwordField.text, extra, root.credentialId)
                    if (result.ok) {
                        root.close()
                        toast.show("项目已保存")
                    } else {
                        errorText.text = result.error
                    }
                }
            }
        }
    }
}
