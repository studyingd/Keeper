import QtQuick
import ".."

Image {
    id: root
    property string name: ""
    property color tint: Theme.textMuted
    property int pixel: 18

    width: pixel
    height: pixel

    // 2 倍渲染 + bilinear 缩小：覆盖 200% DPI，不开 mipmap（mipmap 会过柔）
    sourceSize: Qt.size(pixel * 2, pixel * 2)
    fillMode: Image.PreserveAspectFit
    smooth: true

    source: name !== "" ? `image://icons/${name}#${tint.toString().replace(/#/g, "")}` : ""
}
