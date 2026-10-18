pragma Singleton
import QtQuick

// Exact OKLCH→sRGB conversions shared with ui/theme.py (scripts/oklch_convert.py).
QtObject {
    readonly property color bgDeep: "#050B10"
    readonly property color bg: "#081116"
    readonly property color surface: "#0E191F"
    readonly property color surface2: "#142027"
    readonly property color border: "#223039"
    readonly property color borderSoft: "#1A262D"
    readonly property color borderStrong: "#334550"
    readonly property color sidebarTop: "#0F1B22"
    readonly property color sidebarBottom: "#0A141A"
    readonly property color btnHover: "#1B2831"
    readonly property color rowHover: "#18262E"
    readonly property color rowSelected: "#082E38"

    readonly property color text: "#E6ECF0"
    readonly property color textMuted: "#8D9BA3"
    readonly property color textFaint: "#6B767E"

    readonly property color accent: "#51D2C4"
    readonly property color accentStrong: "#73E3D5"
    readonly property color accentDeep: "#003038"
    readonly property color accentInk: "#00191D"
    readonly property color accentDim: "#51D2C41D"   // 14% alpha
    readonly property color accentBorder: "#51D2C473" // 45% alpha

    readonly property color ok: "#59D38C"
    readonly property color warning: "#E7B643"
    readonly property color danger: "#FF645F"
    readonly property color dangerDim: "#FF645F1F"

    readonly property color shadow: "#000408"
    readonly property color primaryTop: "#7EE7D9"
    readonly property color primaryBottom: "#4BCFC4"

    readonly property string bodyFamily: "Inter, \"Noto Sans SC\", \"Segoe UI\", \"Microsoft YaHei\""
    readonly property string displayFamily: "\"Space Grotesk\", Inter, \"Noto Sans SC\", \"Segoe UI\""
    readonly property string monoFamily: "\"JetBrains Mono\", \"Cascadia Mono\", Consolas"

    readonly property int radiusSm: 8
    readonly property int radiusMd: 12
    readonly property int radiusLg: 16
    readonly property int radiusXl: 20

    readonly property int durFast: 150
    readonly property int durBase: 250
    readonly property int durSlow: 400

    readonly property var levelColors: ["#FF645F", "#E7B643", "#51D2C4", "#59D38C"]
}
