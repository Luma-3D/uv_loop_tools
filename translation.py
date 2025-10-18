# translation.py
import bpy

translation_dict = {
    "ja_JP": {
        # Panels
        ("*", "Spline"): "スプライン",
        ("*", "Adjust with Curve (Modal)"): "カーブで調整（モーダル）",
        ("*", "Only available in Edit Mode."): "編集モードで実行可能です。",
        ("*", "Cannot run while UV sync selection is on."): "UV選択同期がオンのため実行できません。",
        ("*", "Control Points"): "制御点数",
        ("*", "UV Loop Equalize"): "形状を維持して等間隔",
        ("*", "Initializing UV Loop Equalize…"): "UVループ均等化を初期化しています…",
        ("*", "Auto Equalize"): "自動判定して等間隔",
        ("*", "Open Loop"): "開ループ",
        ("*", "Closed Loop"): "閉ループ",
        ("*", "Iterations"): "繰り返し",
        ("*", "Closed loops only"): "閉ループのみ",
        ("*", "Straighten Equalize"): "直線化して等間隔",
        ("*", "Straighten and Equalize"): "直線化(等間隔)",
        ("*", "Match 3D Ratio"): "形状を維持して3D比率",
        ("*", "Auto Match 3D Ratio"): "自動判定して3D比率",
        ("*", "Straighten Match 3D Ratio (Open only)"): "直線化して3D比率(開ループのみ)",
        ("*", "Straighten and Match 3D Ratio"): "直線化(3D比率)",

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
        ("*", "[UV Spline] Curves: {count_curves}  Points(avg): {points}"): "[UVスプライン] カーブ: {count_curves} 制御点(平均): {points}",
        ("*", "Esc/RMB: Exit | G/LMB(Drag): Move | H: Hide spline | Shift+LMB: Multiple selection"): "Esc/RMB: 確定 | G/LMB(ドラッグ): 移動 | H: スプライン表示切り替え | Shift+LMB: 複数選択",
        ("*", "Ctrl/Shift+Wheel: Change control points | Ctrl+LMB: Add or delete | Del: Delete | R: Reset deform"): "Ctrl/Shift+Wheel: 制御点数の変更 | Ctrl+LMB: 制御点の追加/削除 | Del: 制御点の削除 | R: 変形のリセット",
        ("*", "(while moving)"): "(移動中)",
        ("*", "RMB: Move cancel | X/Y: axis lock"): "RMB: 移動キャンセル | X/Y: 移動軸固定",
        ("Operator", "Cannot run while UV sync selection is on. Please disable sync in the UV editor header."): "UV選択同期がONのため実行できません。UVエディタのヘッダーで同期をOFFにしてください。",
        ("Operator", "Please run from the UV/Image Editor while editing a mesh."): "メッシュを編集モードにした状態でUVエディタから実行してください。",
        ("Operator", "Active object must be a mesh in Edit Mode."): "アクティブオブジェクトは編集モード中のメッシュである必要があります。",
        ("Operator", "No WINDOW region found in Image Editor."): "Image Editor に WINDOW リージョンが見つかりません。",
        ("*", "Equalize: Open {count_open} / Closed {count_closed} Moved {moved_vis_total}"): "自動等間隔: 開 {count_open} / 閉 {count_closed} 移動頂点数 {moved_vis_total}",
        ("*", "Edge loops: Open {count_open} / Closed {count_closed} Total iters {total_iters} (avg {avg_iter:.2f}) Moved verts {moved_vis_total}"): "エッジループ: 開 {count_open} / 閉 {count_closed} 繰り返し 合計 {total_iters} 回（平均 {avg_iter:.2f} 回/ループ） 移動頂点数 {moved_vis_total}",
        ("*", "Straighten open loops: Open {count_open} Moved {moved_vis_total}"): "直線等間隔: 開 {count_open} 移動頂点数 {moved_vis_total}",
        ("*", "3D Ratio (preserve shape): Open {count_open} / Closed {count_closed} Moved verts {moved_vis_total}"): "形状を維持して3D比率: 開 {count_open} / 閉 {count_closed} 移動頂点数 {moved_vis_total}",
        ("*", "3D Ratio Straighten: Open {count_open} Moved verts {moved_vis_total}"): "直線化3D比: 開 {count_open} 移動頂点数 {moved_vis_total}",
        ("*", " Skipped {skipped}"): " スキップ {skipped}",
    }
}


def register():
    # register under explicit addon id to avoid mismatches when installed under different module paths
    bpy.app.translations.register("uv_loop_tools", translation_dict)


def unregister():
    bpy.app.translations.unregister("uv_loop_tools")
