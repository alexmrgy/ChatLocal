"""Génère assets/icons/*.svg (style trait, couleur remplacée à l'exécution)."""
from pathlib import Path

STROKE = '<g fill="none" stroke="currentColor" stroke-width="{w}" stroke-linecap="round" stroke-linejoin="round">{b}</g>'
FILL = '<g fill="currentColor" stroke="currentColor" stroke-width="2.6" stroke-linejoin="round">{b}</g>'

S = {
    "images": '<rect x="3" y="8" width="13" height="13" rx="3.5"/><path d="M8 8V7a3.5 3.5 0 0 1 3.5-3.5H17A3.5 3.5 0 0 1 20.5 7v5.5A3.5 3.5 0 0 1 17 16h-1"/><circle cx="7.5" cy="13" r="1"/><path d="m3.5 19 4-3.5 4 3.5"/>',
    "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5.2l3 1.8"/>',
    "library": '<rect x="3" y="4" width="4.5" height="16" rx="2.4"/><rect x="9.5" y="4" width="4.5" height="16" rx="2.4"/><path d="m16 6.2 3.8-1.1 2.6 13.8-3.8 1.1z"/>',
    "atcircle": '<circle cx="12" cy="12" r="3.6"/><path d="M15.6 8.5v4.4a2.6 2.6 0 0 0 5.2 0V12a8.8 8.8 0 1 0-3.4 7"/>',
    "tempchat": '<circle cx="12" cy="12" r="8" stroke-dasharray="3.2 3.2"/><path d="M12 8.5v7M8.5 12h7"/>',
    "panel": '<rect x="3" y="5" width="18" height="14" rx="6"/><path d="M15 5v4.5"/>',
    "sidebar": '<rect x="3" y="4" width="18" height="16" rx="6"/><path d="M9.5 4v16"/>',
    "download": '<path d="M12 4v11m0 0-4.2-4.2M12 15l4.2-4.2M5 20h14"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "arrow_down": '<path d="M12 5v14m-6.5-6.5L12 19l6.5-6.5"/>',
    "arrow_up": '<path d="M12 19V5m-6.5 6.5L12 5l6.5 6.5"/>',
    "image_plus": '<rect x="3" y="3" width="18" height="18" rx="6"/><circle cx="9" cy="9" r="1.6"/><path d="m21 15-5-5L6 20.5"/>',
    "pencil": '<path d="M16.5 3.5a2.8 2.8 0 0 1 4 4L8 20l-5 1.2L4.2 16z"/><path d="m14.5 5.5 4 4"/>',
    "globe": '<circle cx="12" cy="12" r="9.5"/><path d="M2.5 12h19M12 2.5c2.6 2.6 4 6 4 9.5s-1.4 6.9-4 9.5c-2.6-2.6-4-6-4-9.5s1.4-6.9 4-9.5z"/>',
    "copy": '<rect x="9" y="9" width="12" height="12" rx="4"/><path d="M5.5 15H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v.5"/>',
    "check": '<path d="M20 6.5 9.5 17 4 11.5"/>',
    "chevron_down": '<path d="m6 9.5 6 6 6-6"/>',
    "arrow_left": '<path d="M19 12H5m6-6-6 6 6 6"/>',
    "arrow_right": '<path d="M5 12h14m-6-6 6 6-6 6"/>',
    "new_chat": '<path d="M12 4H7a3 3 0 0 0-3 3v10a3 3 0 0 0 3 3h10a3 3 0 0 0 3-3v-5"/><path d="M17.5 3.5a2.1 2.1 0 0 1 3 3L12 15l-4 1 1-4z"/>',
    "chat": '<path d="M12 3.8a8.2 8.2 0 0 0-7.1 12.3L3.8 20.2l4.2-1.1A8.2 8.2 0 1 0 12 3.8z"/>',
    "key": '<circle cx="8" cy="15.5" r="4.2"/><path d="m11.2 12.3 8.8-8.8m-3.2 3.2 3 3m-6.2 0 2.2 2.2"/>',
    "trash": '<path d="M4 7h16M10 11v6M14 11v6M6 7l1 11.5A2 2 0 0 0 9 20.5h6a2 2 0 0 0 2-2L18 7M9 7V4.5h6V7"/>',
    "code": '<path d="m8 8.5-3.8 3.5L8 15.5M16 8.5l3.8 3.5-3.8 3.5M13.4 5.5l-2.8 13"/>',
    "brain": '<path d="M12 5a3 3 0 1 0-5.997.125 4 4 0 0 0-2.526 5.77 4 4 0 0 0 .556 6.588A4 4 0 1 0 12 18Z"/><path d="M12 5a3 3 0 1 1 5.997.125 4 4 0 0 1 2.526 5.77 4 4 0 0 1-.556 6.588A4 4 0 1 1 12 18Z"/><path d="M15 13a4.5 4.5 0 0 1-3-4 4.5 4.5 0 0 1-3 4"/><path d="M17.6 6.5a3 3 0 0 0 .4-1.4M6 5.1a3 3 0 0 0 .4 1.4M3.5 10.9a4 4 0 0 1 .6-.4M19.9 10.5a4 4 0 0 1 .6.4M6 18a4 4 0 0 1-2-.5M20 17.5a4 4 0 0 1-2 .5"/>',
    "archive": '<rect x="3" y="4" width="18" height="5" rx="1.8"/><path d="M5 9v9a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V9M10 13h4"/>',
    "pin": '<path d="M12 16.5V22M8.5 3h7l-1 6 3 3.2v2H6.5v-2L9.5 9z"/>',
    "lock": '<rect x="5" y="11" width="14" height="10" rx="2.8"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/>',
    "unlock": '<rect x="5" y="11" width="14" height="10" rx="2.8"/><path d="M8 11V8a4 4 0 0 1 7.6-1.7"/>',
    "folder_move": '<path d="M3 17V7a2 2 0 0 1 2-2h4l2 2.5h8a2 2 0 0 1 2 2V17a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><path d="M11 13h5m-2-2.2 2.2 2.2-2.2 2.2"/>',
    "chevron_right": '<path d="m9.5 6 6 6-6 6"/>',
    "chevron_left": '<path d="m14.5 6-6 6 6 6"/>',
    "export": '<path d="M12 15V4m0 0L8 8m4-4 4 4"/><path d="M4 14v4a2.5 2.5 0 0 0 2.5 2.5h11A2.5 2.5 0 0 0 20 18v-4"/>',
    "list": '<path d="M9.5 6H20M9.5 12H20M9.5 18H20M4.5 6h.01M4.5 12h.01M4.5 18h.01"/>',
    "palette": '<path d="M12 3a9 9 0 1 0 0 18c1.2 0 2-.8 2-1.8 0-.5-.2-.9-.5-1.2-.3-.3-.5-.7-.5-1.2 0-1 .8-1.8 1.8-1.8H17a4 4 0 0 0 4-4c0-4.4-4-8-9-8z"/><path d="M7.5 11.5h.01M10 7.5h.01M14.5 7.5h.01"/>',
    "panel_open": '<path d="M4 12h11m-4.5-4.5L15 12l-4.5 4.5M20 5v14"/>',
    "terminal": '<rect x="2.5" y="4" width="19" height="16" rx="3.6"/><path d="m6.5 9.5 3 2.5-3 2.5M12.5 15h5"/>',
    "search": '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.6-3.6"/>',
    "folder": '<path d="M3 7a2 2 0 0 1 2-2h4l2 2.5h8a2 2 0 0 1 2 2V17a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    "folder_open": '<path d="M3 17V7a2 2 0 0 1 2-2h4l2 2.5h6a2 2 0 0 1 2 2V10"/><path d="M3.5 19 6 11h15.5l-2.2 7a2 2 0 0 1-1.9 1.4z"/>',
    "speaker": '<path d="M11 5 6.5 9H3v6h3.5L11 19z"/><path d="M15.5 9.2a4 4 0 0 1 0 5.6M18.5 6.5a8 8 0 0 1 0 11"/>',
    "share": '<path d="M12 15V4m0 0L8 8m4-4 4 4"/><path d="M5 12v6a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-6"/>',
    "win_min": '<path d="M5 12h14" stroke-width="1.4"/>',
    "win_max": '<rect x="5.5" y="5.5" width="13" height="13" rx="3.2" stroke-width="1.4"/>',
    "win_restore": '<rect x="5.5" y="8.5" width="10" height="10" rx="3.2" stroke-width="1.4"/><path d="M8.5 8.5v-1a2 2 0 0 1 2-2h6a2 2 0 0 1 2 2v6a2 2 0 0 1-2 2h-1" stroke-width="1.4"/>',
    "win_close": '<path d="M6 6l12 12M18 6 6 18" stroke-width="1.4"/>',
}
F = {
    "home": '<path d="M3.5 10.8 12 3.5l8.5 7.3V19a1.5 1.5 0 0 1-1.5 1.5h-4v-5.5h-6v5.5H5A1.5 1.5 0 0 1 3.5 19z"/>',
    "dots": '<circle cx="5" cy="12" r="1.7"/><circle cx="12" cy="12" r="1.7"/><circle cx="19" cy="12" r="1.7"/>',
    "sparkle": '<path d="M12 2.5 14.2 9.8 21.5 12l-7.3 2.2L12 21.5l-2.2-7.3L2.5 12l7.3-2.2z"/>',
    "play": '<path d="M8 5.2v13.6a1 1 0 0 0 1.5.86l11-6.8a1 1 0 0 0 0-1.72l-11-6.8A1 1 0 0 0 8 5.2z"/>',
    "stop": '<rect x="7" y="7" width="10" height="10" rx="3.4"/>',
}

out = Path(__file__).resolve().parent.parent / "assets" / "icons"
out.mkdir(parents=True, exist_ok=True)
for name, body in S.items():
    w = 2.0
    svg = STROKE.format(w=w, b=body)
    (out / f"{name}.svg").write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24">{svg}</svg>', encoding="utf-8")
for name, body in F.items():
    svg = FILL.format(b=body)
    (out / f"{name}.svg").write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24">{svg}</svg>', encoding="utf-8")
print(len(S) + len(F), "icônes")

