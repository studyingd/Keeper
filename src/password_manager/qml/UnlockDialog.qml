import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "components"

// 解锁/创建对话框：节流倒计时由 QML 自己驱动
Popup {
    id: root
    anchors.centerIn: parent
    modal: true
    closePolicy: Popup.NoAutoClose
    padding: 0
    width: 480
    leftPadding: 28
    rightPadding: 28
    topPadding: 28
    bottomPadding: 28

    property bool isFresh: controller.vaultState === "fresh"
    property int throttleMs: 0
    property string errorText: ""

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
        spacing: 12

        // 品牌行：渐变小瓷砖 + KEEPER
        RowLayout {
            spacing: 10
            Layout.bottomMargin: 4
            Rectangle {
                width: 34; height: 34; radius: 10
                gradient: Gradient {
                    GradientStop { position: 0; color: Theme.accentStrong }
                    GradientStop { position: 1; color: Theme.accent }
                }
                Icon { anchors.centerIn: parent; name: "shield-check"; tint: Theme.accentInk; pixel: 19 }
            }
            Text { text: "KEEPER"; color: Theme.accent; font { pixelSize: 11; bold: true; letterSpacing: 1.4 } }
            Item { Layout.fillWidth: true }
        }
        Text {
            text: root.isFresh ? "创建保险库" : "欢迎回来"
            color: Theme.text
            font { family: Theme.displayFamily; pixelSize: 27; bold: true }
        }
        Text {
            text: root.isFresh ? "设置一个只用于解锁此本地保险库的主密码。" : "输入主密码以解锁本地加密保险库。"
            color: Theme.textMuted
            font { family: Theme.bodyFamily; pixelSize: 13 }
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }

        // 带锁图标的密码框
        Item {
            Layout.fillWidth: true
            Layout.topMargin: 8
            implicitHeight: 44

            readonly property bool focused: password.activeFocus
            Rectangle {
                anchors.fill: parent
                radius: 10
                color: Theme.bgDeep
                border.width: 1
                border.color: password.activeFocus ? Theme.accent : (root.throttleMs === 0 ? Theme.borderSoft : Theme.borderSoft)
                Behavior on border.color { ColorAnimation { duration: Theme.durFast } }
            }
            Icon {
                x: 14
                anchors.verticalCenter: parent.verticalCenter
                name: "lock"
                tint: password.activeFocus ? Theme.accent : Theme.textFaint
                pixel: 15
                Behavior on tint { ColorAnimation { duration: Theme.durFast } }
            }
            TextField {
                id: password
                anchors { fill: parent; leftMargin: 40; rightMargin: 12 }
                echoMode: TextInput.Password
                placeholderText: "主密码"
                color: Theme.text
                font { family: Theme.bodyFamily; pixelSize: 13 }
                selectByMouse: true
                enabled: root.throttleMs === 0
                background: null
                verticalAlignment: TextInput.AlignVCenter
                onAccepted: submit.clicked()
            }
        }
        Item {
            Layout.fillWidth: true
            implicitHeight: 44
            visible: root.isFresh

            Rectangle {
                anchors.fill: parent
                radius: 10
                color: Theme.bgDeep
                border.width: 1
                border.color: confirm.activeFocus ? Theme.accent : Theme.borderSoft
                Behavior on border.color { ColorAnimation { duration: Theme.durFast } }
            }
            Icon {
                x: 14
                anchors.verticalCenter: parent.verticalCenter
                name: "shield-check"
                tint: confirm.activeFocus ? Theme.accent : Theme.textFaint
                pixel: 15
            }
            TextField {
                id: confirm
                anchors { fill: parent; leftMargin: 40; rightMargin: 12 }
                echoMode: TextInput.Password
                placeholderText: "确认密码"
                color: Theme.text
                font { family: Theme.bodyFamily; pixelSize: 13 }
                selectByMouse: true
                enabled: root.throttleMs === 0
                background: null
                verticalAlignment: TextInput.AlignVCenter
                onAccepted: submit.clicked()
            }
        }

        // 错误行（带图标）
        RowLayout {
            visible: root.errorText !== ""
            spacing: 8
            Layout.fillWidth: true
            Icon { name: "close"; tint: Theme.danger; pixel: 13 }
            Text {
                Layout.fillWidth: true
                text: root.errorText
                color: Theme.danger
                font { family: Theme.bodyFamily; pixelSize: 12 }
                wrapMode: Text.WordWrap
            }
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.topMargin: 6
            spacing: 9
            AppButton {
                text: "退出 Keeper"
                onClicked: Qt.quit()
            }
            Item { Layout.fillWidth: true }
            AppButton {
                id: submit
                primary: true
                text: root.isFresh ? "创建加密保险库" : "解锁保险库"
                enabled: root.throttleMs === 0
                implicitHeight: 40
                leftPadding: 22
                rightPadding: 22
                onClicked: {
                    var result = root.isFresh
                        ? controller.createVault(password.text, confirm.text)
                        : controller.attemptUnlock(password.text)
                    if (result.ok) {
                        root.close()
                        password.text = ""
                        confirm.text = ""
                        root.errorText = ""
                    } else if (result.error === "throttled") {
                        root.throttleMs = result.throttleMs
                        root.errorText = ""
                    } else {
                        root.errorText = result.error
                    }
                }
            }
        }
    }

    Timer {
        id: throttleTimer
        interval: 100
        running: root.throttleMs > 0
        repeat: true
        onTriggered: {
            root.throttleMs -= interval
            if (root.throttleMs <= 0) {
                root.throttleMs = 0
                root.errorText = ""
                password.forceActiveFocus()
            } else {
                root.errorText = `解锁失败，请 ${Math.ceil(root.throttleMs / 1000)} 秒后重试。`
            }
        }
    }

    onAboutToShow: {
        password.text = ""
        confirm.text = ""
        errorText = ""
        password.forceActiveFocus()
    }
}
