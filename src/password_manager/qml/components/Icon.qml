import QtQuick
import QtQuick.Layouts
import ".."

Image {
    id: root
    property string name: ""
    property color tint: Theme.textMuted
    property int pixel: 18

    width: pixel
    height: pixel
    // Image 的 implicitSize 由 sourceSize（pixel * 2）推导，布局（RowLayout /
    // ColumnLayout）会优先使用 implicitSize 而忽略显式 width/height，导致图标
    // 以 2 倍尺寸参与排版。这里把布局首选尺寸固定为 pixel，sourceSize 只负责
    // 光栅化分辨率。
    Layout.preferredWidth: pixel
    Layout.preferredHeight: pixel

    // 2 倍渲染 + bilinear 缩小：覆盖 200% DPI，不开 mipmap（mipmap 会过柔）
    sourceSize: Qt.size(pixel * 2, pixel * 2)
    fillMode: Image.PreserveAspectFit
    smooth: true

    source: name !== "" ? `image://icons/${name}#${tint.toString().replace(/#/g, "")}` : ""
}
