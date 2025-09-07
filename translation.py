# translation.py
import bpy

translation_dict = {
    "ja_JP": {
        # Panels
        ("*", "Spline"): "スプライン",
        ("*", "Adjust with Curve (Modal)"): "カーブで調整（モーダル）",
        ("*", "Cannot run while UV sync selection is on."): "UV選択同期がオンのため実行できません。",
        ("*", "Control Points"): "制御点数",
        ("*", "Initializing UV Loop Equalize…"): "UVループ均等化を初期化しています…",
        ("*", "Auto Equalize"): "自動判定して等間隔",
        ("*", "Open Loop"): "開ループ",
        ("*", "Closed Loop"): "閉ループ",
        ("*", "Iterations"): "繰り返し",
        ("*", "Closed loops only"): "閉ループのみ",
        ("*", "Straighten and Equalize"): "直線化して等間隔",
        ("*", "Auto Match 3D Ratio"): "自動判定して3D比率",
        ("*", "Straighten and Match 3D Ratio"): "直線化して3D比率",

        # Preferences
        ("*", "Curve"): "カーブ",
        ("*", "Curve Color"): "カーブの色",
        ("*", "Curve Thickness"): "カーブの太さ",
        ("*", "Insert Pick Threshold (px)"): "制御点を追加する際のクリックしきい値 (px)",
        ("*", "Control Points"): "制御点",
        ("*", "Normal"): "通常",
        ("*", "Selected"): "選択",
        ("*", "Active"): "アクティブ",
        ("*", "Control Point Size"): "制御点の大きさ",
        ("*", "Point Pick Threshold (px)"): "制御点選択しきい値 (px)",

        # Operators / messages
        ("Operator", "UV Edge Equalize"): "UVエッジを等間隔に配置",
        ("Operator", "Auto Equalize"): "自動判定して等間隔",
        ("Operator", "Straighten and Equalize"): "直線化して等間隔",
        ("Operator", "No editable mesh objects in edit mode."): "編集モードにあるメッシュオブジェクトがありません。",
        ("Operator", "Cannot run while UV sync selection is on. Please disable sync in the UV editor header."): "UV選択同期がONのため実行できません。UVエディタのヘッダーで同期をOFFにしてください。",
        ("*", "No valid edge loops found."): "処理可能なエッジループが見つかりませんでした。",
        ("*", "Loop Type / Options"): "ループ種別 / オプション",
        ("*", "Options"): "オプション",
        ("*", "Weld tolerance"): "溶接しきい値",
        ("*", "Adjust with Curve (Modal)"): "カーブで調整（モーダル）",
        ("*", "[UV Spline] Curves: {count_curves} Points(each): {points} (H: toggle display, Ctrl+Wheel: current shape ±, Shift+Wheel: original shape ±)"): "[UVスプライン] カーブ: {count_curves} 制御点(各): {points} (H: 表示切替, Ctrl+ホイール: 現在形状±, Shift+ホイール: 原形状±)",
        ("Operator", "Cannot run while UV sync selection is on. Please disable sync in the UV editor header."): "UV選択同期がONのため実行できません。UVエディタのヘッダーで同期をOFFにしてください。",
        ("Operator", "Please run from the UV/Image Editor while editing a mesh."): "メッシュを編集モードにした状態でUVエディタから実行してください。",
        ("Operator", "Active object must be a mesh in Edit Mode."): "アクティブオブジェクトは編集モード中のメッシュである必要があります。",
        ("Operator", "No WINDOW region found in Image Editor."): "Image Editor に WINDOW リージョンが見つかりません。",
        ("*", "Edge loops: Open {count_open} / Closed {count_closed} Total iters {total_iters} (avg {avg_iter:.2f}) Moved verts {moved_vis_total}"): "エッジループ: 開 {count_open} / 閉 {count_closed} 繰り返し 合計 {total_iters} 回（平均 {avg_iter:.2f} 回/ループ） 移動頂点数 {moved_vis_total}",
        ("*", "Straighten Equalize: Open {count_open} / Closed (skipped) {count_closed} Moved verts {moved_vis_total}"): "直線均等: 開 {count_open} / 閉（無処理）{count_closed} 移動頂点数 {moved_vis_total}",
    }
}


def register():
    # register under explicit addon id to avoid mismatches when installed under different module paths
    bpy.app.translations.register("uv_loop_tools", translation_dict)


def unregister():
    bpy.app.translations.unregister("uv_loop_tools")
