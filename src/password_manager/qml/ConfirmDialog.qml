import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "components"

// 确认对话框：危险操作（删除）前必须显式确认
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

    property string titleText: ""
    property string messageText: ""
    property var onConfirmed: null

    function ask(title, message, callback) {
        titleText = title
        messageText = message
        onConfirmed = callback
        open()
    }

    enter: Transition {
        ParallelAnimation {
            NumberAnimation { property: "opacity"; from: 0; to: 1; duration: 220; easing.type: Easing.OutCubic }
            NumberAnimation { property: "scale"; from: 0.95; to: 1; duration: 260; easing.type: Easing.OutBack }
        }
    }
    exit: Transition {
        NumberAnimation { property: "opacity"; from: 1; to: 0; duration: 180; easing.type: Easing.OutCubic }
    }

    background: DialogSurface {}

    contentItem: ColumnLayout {
        spacing: 12

        Text {
            text: root.titleText
            color: Theme.text
            font { family: Theme.displayFamily; pixelSize: 20; bold: true }
        }
        Text {
            Layout.fillWidth: true
            text: root.messageText
            color: Theme.textMuted
            font { family: Theme.bodyFamily; pixelSize: 13 }
            wrapMode: Text.WordWrap
        }
        RowLayout {
            Layout.fillWidth: true
            Item { Layout.fillWidth: true }
            AppButton { text: "取消"; onClicked: root.close() }
            AppButton {
                primary: true
                text: "删除"
                onClicked: {
                    root.close()
                    if (root.onConfirmed) root.onConfirmed()
                }
            }
        }
    }
}
