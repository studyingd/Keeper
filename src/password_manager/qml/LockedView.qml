import QtQuick
import QtQuick.Layouts
import "components"

// 锁定页：锁定≠空库，数据仍在本地加密文件里（盖住整个窗口的覆盖层内容）
ColumnLayout {
    id: root
    spacing: 0

    signal unlockRequested()

    // 弹簧入场（demo 的 lockIn：opacity 0→1 + scale 0.94→1 OutBack）
    property bool appeared: false
    opacity: appeared ? 1 : 0
    scale: appeared ? 1 : 0.94
    Behavior on opacity { NumberAnimation { duration: 260; easing.type: Easing.OutCubic } }
    Behavior on scale { NumberAnimation { duration: 360; easing.type: Easing.OutBack } }

    function playAppear(show: bool) {
        appeared = false
        if (show) appearDelay.restart()
    }
    Timer {
        id: appearDelay
        interval: 60
        onTriggered: root.appeared = true
    }
    Connections {
        target: controller
        function onVaultStateChanged() {
            root.playAppear(controller.vaultState !== "unlocked")
        }
    }
    Component.onCompleted: playAppear(controller.vaultState !== "unlocked")

    Item { Layout.fillHeight: true }

    // 图标瓷砖（渐变 + 描边，无光晕）
    Rectangle {
        id: mark
        Layout.alignment: Qt.AlignHCenter
        width: 64; height: 64
        radius: 19
        gradient: Gradient {
            GradientStop { position: 0; color: Theme.accentDeep }
            GradientStop { position: 1; color: Theme.surface }
        }
        border.width: 1
        border.color: Theme.accentBorder
        Icon {
            anchors.centerIn: parent
            name: "lock"
            tint: Theme.accent
            pixel: 28
        }
    }

    Text {
        Layout.alignment: Qt.AlignHCenter
        Layout.topMargin: 18
        text: "保险库已锁定"
        color: Theme.text
        font { family: Theme.displayFamily; pixelSize: 28; bold: true }
    }

    AppButton {
        Layout.alignment: Qt.AlignHCenter
        Layout.topMargin: 24
        primary: true
        glyph: "lock"
        text: "解锁保险库"
        implicitHeight: 42
        leftPadding: 26
        rightPadding: 26
        onClicked: root.unlockRequested()
    }

    Text {
        Layout.alignment: Qt.AlignHCenter
        Layout.topMargin: 16
        text: controller.trayAvailable
            ? `关闭窗口时 Keeper 会驻留系统托盘，${controller.autoLockMinutes} 分钟无操作自动锁定`
            : `${controller.autoLockMinutes} 分钟无操作自动锁定`
        color: Theme.textFaint
        font { family: Theme.bodyFamily; pixelSize: 11 }
    }

    Item { Layout.fillHeight: true }

    // 回车即解锁
    Shortcut {
        sequence: "Return"
        enabled: root.appeared
        context: Qt.WindowShortcut
        onActivated: root.unlockRequested()
    }
}
