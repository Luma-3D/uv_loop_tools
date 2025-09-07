import bpy


def _is_japanese_language():
    """Return True if Blender language/locale appears to be Japanese.

    Heuristics: check preferences.view.language and bpy.app.translations.locale if available.
    """
    try:
        lang = getattr(bpy.context.preferences.view, 'language', '')
        if isinstance(lang, str) and ('ja' in lang.lower() or 'japan' in lang.lower()):
            return True
    except Exception:
        pass
    try:
        locale = getattr(bpy.app.translations, 'locale', '')
        if isinstance(locale, str) and locale.lower().startswith('ja'):
            return True
    except Exception:
        pass
    return False


def tr(en: str, ja: str = None) -> str:
    """Return localized string: English by default, Japanese if Blender is set to Japanese and a Japanese string is provided.

    This is a tiny helper intended for addons that want English labels by default and Japanese
    when the user's Blender locale is Japanese. It intentionally avoids gettext to keep things
    simple—if later you prefer full i18n, switch to bpy.app.translations or gettext.
    """
    if ja is None:
        return en
    try:
        return ja if _is_japanese_language() else en
    except Exception:
        return en


__all__ = ("tr", "_is_japanese_language")
