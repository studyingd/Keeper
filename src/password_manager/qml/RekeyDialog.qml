import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "components"

// 修改主密码：验证旧密码后整库重新加密
Popup {
    id: root
    anchors.centerIn: parent
    modal: true
    closePolicy: Popup.CloseOnEscape
    padding: 0
    width: 430
    leftPadding: 28
    rightPadding: 28
    topPadding: 26
    bottomPadding: 26

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
        spacing: 13

        Text {
            text: "修改主密码"
            color: Theme.text
            font { family: Theme.displayFamily; pixelSize: 20; bold: true }
        }
        Text {
            text: "会用新主密码重新加密整个保险库，内容保持不变。主密码无法恢复，请确认新密码已妥善保存。"
            color: Theme.textMuted
            font { family: Theme.bodyFamily; pixelSize: 12 }
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }

        Text { text: "当前主密码"; color: Theme.textMuted; font { family: Theme.bodyFamily; pixelSize: 12; bold: true } }
        TextField {
            id: currentField
            Layout.fillWidth: true
            echoMode: TextInput.Password
            color: Theme.text
            font { family: Theme.bodyFamily; pixelSize: 13 }
            selectByMouse: true
            background: Rectangle {
                radius: 10; color: Theme.bgDeep; border.width: 1
                border.color: currentField.activeFocus ? Theme.accent : Theme.borderSoft
            }
        }
        Text { text: "新主密码"; color: Theme.textMuted; font { family: Theme.bodyFamily; pixelSize: 12; bold: true } }
        TextField {
            id: newField
            Layout.fillWidth: true
            echoMode: TextInput.Password
            color: Theme.text
            font { family: Theme.bodyFamily; pixelSize: 13 }
            selectByMouse: true
            background: Rectangle {
                radius: 10; color: Theme.bgDeep; border.width: 1
                border.color: newField.activeFocus ? Theme.accent : Theme.borderSoft
            }
        }
        Text { text: "确认新密码"; color: Theme.textMuted; font { family: Theme.bodyFamily; pixelSize: 12; bold: true } }
        TextField {
            id: confirmField
            Layout.fillWidth: true
            echoMode: TextInput.Password
            color: Theme.text
            font { family: Theme.bodyFamily; pixelSize: 13 }
            selectByMouse: true
            background: Rectangle {
                radius: 10; color: Theme.bgDeep; border.width: 1
                border.color: confirmField.activeFocus ? Theme.accent : Theme.borderSoft
            }
            onAccepted: saveButton.clicked()
        }

        Text {
            id: errorText
            visible: text !== ""
            color: Theme.danger
            font { family: Theme.bodyFamily; pixelSize: 12 }
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
            text: ""
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.topMargin: 4
            Item { Layout.fillWidth: true }
            AppButton { text: "取消"; onClicked: root.close() }
            AppButton {
                id: saveButton
                primary: true
                text: "重新加密保险库"
                onClicked: {
                    var result = controller.rekeyVault(currentField.text, newField.text, confirmField.text)
                    if (result.ok) {
                        root.close()
                        toast.show("主密码已更换，保险库已用新密码重新加密")
                    } else {
                        errorText.text = result.error
                    }
                }
            }
        }
    }

    onAboutToShow: {
        currentField.text = ""
        newField.text = ""
        confirmField.text = ""
        errorText.text = ""
    }
}
