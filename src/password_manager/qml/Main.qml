import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Dialogs
import QtQuick.Layouts
import "components"

ApplicationWindow {
    id: root
    width: 1280
    height: 800
    minimumWidth: 980
    minimumHeight: 640
    title: "Keeper"
    color: Theme.bg
    visible: true

    property bool quitting: false

    onVisibleChanged: controller.setUiVisible(visible)

    onClosing: function (close) {
        if (controller.trayAvailable && !root.quitting) {
            close.accepted = false
            root.hide()
            controller.markHiddenToTray()
        }
    }

    function confirmQuit() {
        root.quitting = true
        controller.prepareQuit()
        Qt.quit()
    }

    // ── 背景：底色 + 双径向光晕（局部化椭圆，带真实衰减） ──
    Rectangle {
        anchors.fill: parent
        color: Theme.bg
    }
    Image {
        // 右上青色光晕：demo radial-gradient(700px 300px at 85% -5%)
        source: "image://glow/teal"
        sourceSize: Qt.size(700, 360)
        width: 700; height: 360
        smooth: true
        anchors { right: parent.right; rightMargin: -120; top: parent.top; topMargin: -160 }
    }
    Image {
        // 左下蓝色光晕
        source: "image://glow/blue"
        sourceSize: Qt.size(700, 400)
        width: 700; height: 400
        smooth: true
        anchors { left: parent.left; leftMargin: -120; bottom: parent.bottom; bottomMargin: -180 }
    }

    // ── 侧边栏（不透明，盖住左侧光晕） ──
    Sidebar {
        id: sidebar
        anchors { left: parent.left; top: parent.top; bottom: parent.bottom }
        width: 300
        onAddRequested: entryDialog.openFor(null)
        onExportRequested: exportDialog.open()
        onRekeyRequested: rekeyDialog.open()
    }

    // ── 页面栈（透明背景，首页 / 详情；锁定时整体被覆盖层盖住） ──
    StackLayout {
        id: pages
        anchors { left: sidebar.right; top: parent.top; right: parent.right; bottom: parent.bottom }
        visible: controller.vaultState === "unlocked"
        currentIndex: controller.selectedEntry.id !== undefined ? 1 : 0

        HomeView {}
        DetailView {
            onEditEntryRequested: entryDialog.openFor(controller.selectedEntry)
            onDeleteEntryRequested: confirmDialog.ask(
                "删除资产",
                `删除「${controller.selectedEntry.name}」及其全部项目？此操作无法撤销。`,
                function () { controller.deleteEntry(controller.selectedEntry.id); toast.show("资产已删除") })
            onAddCredentialRequested: credentialDialog.openFor(controller.selectedEntry, null, false)
            onAddLoginRequested: credentialDialog.openFor(controller.selectedEntry, null, true)
            onEditCredentialRequested: (credential) => credentialDialog.openFor(controller.selectedEntry, credential, false)
            onDeleteCredentialRequested: (credential) => confirmDialog.ask(
                "删除项目",
                `删除「${credential.label}」？此操作无法撤销。`,
                function () { controller.deleteCredential(credential.id, controller.selectedEntry.id); toast.show("项目已删除") })
        }
    }

    // ── 锁定覆盖层：盖住整个窗口（含侧边栏），淡入淡出 ──
    Item {
        id: lockOverlay
        anchors.fill: parent
        visible: lockShade.opacity > 0.01

        Rectangle {
            id: lockShade
            anchors.fill: parent
            color: Theme.bg
            opacity: controller.vaultState === "unlocked" ? 0 : 1
            Behavior on opacity { NumberAnimation { duration: 300; easing.type: Easing.OutCubic } }
        }
        LockedView {
            anchors.fill: parent
            onUnlockRequested: unlockDialog.open()
        }
    }

    // ── 对话框 ──
    UnlockDialog { id: unlockDialog; objectName: "unlockDialog" }
    EntryDialog { id: entryDialog }
    CredentialDialog { id: credentialDialog }
    RekeyDialog { id: rekeyDialog }
    ConfirmDialog { id: confirmDialog }

    FileDialog {
        id: exportDialog
        title: "导出凭据到 Excel"
        nameFilters: ["Excel 工作簿 (*.xlsx)"]
        fileMode: FileDialog.SaveFile
        onAccepted: {
            var result = controller.exportVault(selectedFile.toString().replace("file:///", ""))
            toast.show(result.ok ? `已导出 ${result.count} 个项目` : result.error)
        }
    }

    // ── Toast ──
    Rectangle {
        id: toast
        property string message: ""
        function show(text) {
            message = text
            toastText.text = text
            toastTimer.restart()
            opacity = 1
        }
        anchors { horizontalCenter: parent.horizontalCenter; bottom: parent.bottom; bottomMargin: 24 }
        radius: 10
        color: "#16242CF5"
        border.width: 1
        border.color: Theme.borderStrong
        implicitWidth: Math.min(toastRow.implicitWidth + 36, root.width - 80)
        implicitHeight: 40
        opacity: 0
        z: 100
        Behavior on opacity { NumberAnimation { duration: 200; easing.type: Easing.OutCubic } }

        RowLayout {
            id: toastRow
            anchors.centerIn: parent
            spacing: 8
            Icon { name: "check"; tint: Theme.accent; pixel: 15 }
            Text {
                id: toastText
                Layout.maximumWidth: root.width - 160
                text: toast.message
                color: Theme.text
                font { family: Theme.bodyFamily; pixelSize: 13 }
                elide: Text.ElideRight
            }
        }
        Timer {
            id: toastTimer
            interval: 2600
            onTriggered: toast.opacity = 0
        }
    }

    Connections {
        target: controller
        function onToastRequested(text) { toast.show(text) }
        function onShowWindowRequested() { root.show(); root.raise(); root.requestActivate() }
    }

    Component.onCompleted: {
        if (controller.vaultState === "fresh") {
            unlockDialog.open()
        }
    }
}
