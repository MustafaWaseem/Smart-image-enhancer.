"""Smart Image Enhancer - Flet 0.28.x app (Android / Desktop).

Features: Sharpen (Kernel / Unsharp Mask), Grayscale, Auto Contrast,
before/after comparison, live stats, save result to device.
"""
import base64
import os
import time

import cv2
import flet as ft
import numpy as np

BRAND = "#800000"
BRAND_DARK = "#4A0000"
# 1x1 transparent PNG: Flet's Image crashes if it has neither src nor src_base64
BLANK = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA"
    "60e6kgAAAABJRU5ErkJggg=="
)


# ---------- Image processing ----------
def compute_sharpness(img: np.ndarray) -> float:
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def apply_grayscale(img: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)


def apply_kernel_sharpen(img: np.ndarray, strength: float) -> np.ndarray:
    kernel = np.array(
        [
            [0, -strength, 0],
            [-strength, 1 + 4 * strength, -strength],
            [0, -strength, 0],
        ],
        dtype=np.float32,
    )
    return cv2.filter2D(img, -1, kernel)


def apply_unsharp_mask(img: np.ndarray, amount: float, sigma: float) -> np.ndarray:
    blurred = cv2.GaussianBlur(img, (0, 0), sigma)
    return cv2.addWeighted(img, 1.0 + amount, blurred, -amount, 0)


def apply_auto_contrast(img: np.ndarray, clip: float) -> np.ndarray:
    """CLAHE on the lightness channel - improves contrast without colour shifts."""
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    l_ch, a_ch, b_ch = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=float(clip), tileGridSize=(8, 8))
    merged = cv2.merge((clahe.apply(l_ch), a_ch, b_ch))
    return cv2.cvtColor(merged, cv2.COLOR_LAB2BGR)


def encode_image(img: np.ndarray, ext: str):
    ok, buf = cv2.imencode(ext, img)
    if not ok:
        raise ValueError("Image encode fail")
    return base64.b64encode(buf).decode("utf-8"), len(buf) / 1024.0


def save_image(img: np.ndarray, filename: str) -> str:
    """Save to a public folder if possible, else app storage. Returns final path."""
    candidates = [
        "/storage/emulated/0/Pictures/SmartImageEnhancer",
        "/storage/emulated/0/Download",
        os.path.expanduser("~/Pictures"),
        os.path.expanduser("~/Downloads"),
        os.getenv("FLET_APP_STORAGE_DATA", ""),
        os.getcwd(),
    ]
    for folder in candidates:
        if not folder:
            continue
        try:
            os.makedirs(folder, exist_ok=True)
            path = os.path.join(folder, filename)
            if cv2.imwrite(path, img):
                return path
        except Exception:
            continue
    raise IOError("Koi writable folder nahi mila")


# ---------- UI ----------
def main(page: ft.Page):
    page.title = "Smart Image Enhancer"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.theme = ft.Theme(color_scheme_seed=BRAND, use_material3=True)
    page.padding = 0
    page.spacing = 0
    page.bgcolor = "#F5F3F2"
    page.horizontal_alignment = ft.CrossAxisAlignment.STRETCH  # full-width header fix

    state = {
        "orig": None, "proc": None, "ext": ".png",
        "orig_kb": 0.0, "orig_score": 0.0, "view": "split",
    }

    # ----- Header (full width, respects the status bar / notch) -----
    header = ft.Container(
        gradient=ft.LinearGradient(
            begin=ft.alignment.top_left,
            end=ft.alignment.bottom_right,
            colors=[BRAND, BRAND_DARK],
        ),
        border_radius=ft.border_radius.only(bottom_left=28, bottom_right=28),
        padding=ft.padding.only(left=20, right=20, bottom=22),
        content=ft.SafeArea(
            bottom=False,
            content=ft.Row(
                [
                    ft.Container(
                        content=ft.Icon(ft.Icons.AUTO_FIX_HIGH, color=BRAND, size=26),
                        bgcolor=ft.Colors.WHITE, width=48, height=48, border_radius=14,
                        alignment=ft.alignment.center,
                    ),
                    ft.Column(
                        [
                            ft.Text("Smart Image Enhancer", size=21,
                                    weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE),
                            ft.Text("Sharpen  •  Grayscale  •  Compare", size=12,
                                    color=ft.Colors.WHITE70),
                        ],
                        spacing=2, expand=True,
                    ),
                ],
                spacing=14,
            ),
        ),
    )

    # ----- Status line -----
    status_icon = ft.Icon(ft.Icons.INFO_OUTLINE, size=18, color=ft.Colors.GREY_700)
    status_text = ft.Text(
        "JPG/PNG image upload karein, settings badlein, compare karein aur save karein.",
        size=13, color=ft.Colors.GREY_800, expand=True,
    )
    status_box = ft.Container(
        content=ft.Row([status_icon, status_text], spacing=10,
                       vertical_alignment=ft.CrossAxisAlignment.START),
        padding=12, bgcolor=ft.Colors.WHITE, border_radius=14,
    )

    def set_status(msg: str, kind: str = "info"):
        icon, color = {
            "info": (ft.Icons.INFO_OUTLINE, ft.Colors.GREY_700),
            "ok": (ft.Icons.CHECK_CIRCLE_OUTLINE, ft.Colors.GREEN_700),
            "err": (ft.Icons.ERROR_OUTLINE, ft.Colors.RED_700),
        }[kind]
        status_icon.name, status_icon.color = icon, color
        status_text.value, status_text.color = msg, color

    # ----- Stat cards -----
    card_res = ft.Text("-", weight=ft.FontWeight.BOLD, size=14)
    card_size = ft.Text("-", weight=ft.FontWeight.BOLD, size=14)
    card_score = ft.Text("-", weight=ft.FontWeight.BOLD, size=14)

    def stat_card(icon, title, value_ctl):
        return ft.Container(
            expand=True, padding=ft.padding.symmetric(vertical=12, horizontal=6),
            bgcolor=ft.Colors.WHITE, border_radius=14,
            content=ft.Column(
                [ft.Icon(icon, size=18, color=BRAND),
                 ft.Text(title, size=11, color=ft.Colors.GREY_600), value_ctl],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=3,
            ),
        )

    info_row = ft.Row(
        [stat_card(ft.Icons.ASPECT_RATIO, "Resolution", card_res),
         stat_card(ft.Icons.STORAGE, "Size", card_size),
         stat_card(ft.Icons.BLUR_ON, "Sharpness", card_score)],
        spacing=8,
    )

    # ----- Image views -----
    def make_img(height):
        return ft.Image(src_base64=BLANK, fit=ft.ImageFit.CONTAIN, height=height,
                        border_radius=10, gapless_playback=True)

    img_split_o, img_split_p = make_img(200), make_img(200)
    img_full_o, img_full_p = make_img(340), make_img(340)

    def labelled(title, img):
        return ft.Column(
            [ft.Text(title, size=12, weight=ft.FontWeight.BOLD, color=BRAND), img],
            expand=True, horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=6,
        )

    view_split = ft.Row([labelled("Original", img_split_o), labelled("Processed", img_split_p)],
                        spacing=8, vertical_alignment=ft.CrossAxisAlignment.START)
    view_orig = ft.Column([img_full_o], horizontal_alignment=ft.CrossAxisAlignment.CENTER, visible=False)
    view_proc = ft.Column([img_full_p], horizontal_alignment=ft.CrossAxisAlignment.CENTER, visible=False)

    def on_view_change(e):
        sel = list(e.control.selected)[0]
        state["view"] = sel
        view_split.visible = sel == "split"
        view_orig.visible = sel == "orig"
        view_proc.visible = sel == "proc"
        page.update()

    view_switch = ft.SegmentedButton(
        selected={"split"}, allow_multiple_selection=False, on_change=on_view_change,
        segments=[
            ft.Segment(value="split", label=ft.Text("Compare")),
            ft.Segment(value="orig", label=ft.Text("Original")),
            ft.Segment(value="proc", label=ft.Text("Processed")),
        ],
    )

    placeholder = ft.Container(
        padding=30, alignment=ft.alignment.center,
        content=ft.Column(
            [ft.Icon(ft.Icons.IMAGE_OUTLINED, size=56, color=ft.Colors.GREY_400),
             ft.Text("Abhi koi image select nahi ki", color=ft.Colors.GREY_600, size=13)],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=8,
        ),
    )
    preview_content = ft.Column([view_switch, view_split, view_orig, view_proc],
                                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                                spacing=12, visible=False)
    preview_card = ft.Container(
        padding=14, bgcolor=ft.Colors.WHITE, border_radius=18,
        content=ft.Column([placeholder, preview_content]),
    )

    busy = ft.ProgressBar(visible=False, color=BRAND, bar_height=3)

    # ----- Controls -----
    def val_text(v):
        return ft.Text(f"{v:.1f}", size=12, weight=ft.FontWeight.BOLD, color=BRAND)

    strength_val, amount_val, sigma_val, clip_val = val_text(1.0), val_text(1.2), val_text(1.5), val_text(2.0)

    def slider(minv, maxv, value, divs, label_ctl):
        def live(e):
            label_ctl.value = f"{e.control.value:.1f}"
            label_ctl.update()
        return ft.Slider(min=minv, max=maxv, value=value, divisions=divs,
                         active_color=BRAND, on_change=live,
                         on_change_end=lambda e: process())

    strength_slider = slider(0.1, 3.0, 1.0, 29, strength_val)
    amount_slider = slider(0.1, 3.0, 1.2, 29, amount_val)
    sigma_slider = slider(0.5, 5.0, 1.5, 45, sigma_val)
    clip_slider = slider(1.0, 6.0, 2.0, 50, clip_val)

    def slider_row(title, val_ctl, sld):
        return ft.Column(
            [ft.Row([ft.Text(title, size=12, color=ft.Colors.GREY_800), val_ctl],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN), sld],
            spacing=0,
        )

    op_switch = ft.SegmentedButton(
        selected={"sharpen"}, allow_multiple_selection=False,
        on_change=lambda e: process(),
        segments=[
            ft.Segment(value="sharpen", label=ft.Text("Sharpen"), icon=ft.Icon(ft.Icons.DEBLUR)),
            ft.Segment(value="gray", label=ft.Text("Gray"), icon=ft.Icon(ft.Icons.FILTER_B_AND_W)),
            ft.Segment(value="contrast", label=ft.Text("Contrast"), icon=ft.Icon(ft.Icons.CONTRAST)),
        ],
    )
    method_dropdown = ft.Dropdown(
        label="Sharpening Method", value="Kernel", border_radius=12,
        options=[ft.dropdown.Option("Kernel", "Kernel Filter"),
                 ft.dropdown.Option("Unsharp", "Unsharp Mask")],
        on_change=lambda e: process(),
    )

    kernel_box = ft.Column([slider_row("Strength", strength_val, strength_slider)])
    unsharp_box = ft.Column(
        [slider_row("Amount", amount_val, amount_slider),
         slider_row("Sigma", sigma_val, sigma_slider)],
        visible=False,
    )
    sharpen_box = ft.Column([method_dropdown, kernel_box, unsharp_box], spacing=10)
    contrast_box = ft.Column([slider_row("Clip limit", clip_val, clip_slider)], visible=False)

    settings_card = ft.Container(
        padding=16, bgcolor=ft.Colors.WHITE, border_radius=18,
        content=ft.Column(
            [ft.Text("Settings", size=16, weight=ft.FontWeight.BOLD),
             op_switch, sharpen_box, contrast_box],
            spacing=12,
        ),
    )

    # ----- Processing -----
    def process():
        orig = state["orig"]
        if orig is None:
            return
        op = list(op_switch.selected)[0]
        sharpen_box.visible = op == "sharpen"
        contrast_box.visible = op == "contrast"
        kernel_box.visible = method_dropdown.value == "Kernel"
        unsharp_box.visible = method_dropdown.value == "Unsharp"
        busy.visible = True
        page.update()
        try:
            if op == "gray":
                proc = apply_grayscale(orig)
            elif op == "contrast":
                proc = apply_auto_contrast(orig, clip_slider.value)
            elif method_dropdown.value == "Kernel":
                proc = apply_kernel_sharpen(orig, float(strength_slider.value))
            else:
                proc = apply_unsharp_mask(orig, float(amount_slider.value), float(sigma_slider.value))

            state["proc"] = proc
            b64, kb = encode_image(proc, state["ext"])
            img_split_p.src_base64 = b64
            img_full_p.src_base64 = b64
            card_size.value = f"{kb:.0f} KB"
            score = compute_sharpness(proc)
            diff = score - state["orig_score"]
            card_score.value = f"{score:.0f} ({'+' if diff >= 0 else ''}{diff:.0f})"
            btn_save.disabled = False
        except Exception as ex:
            set_status(f"Processing error: {ex}", "err")
        busy.visible = False
        page.update()

    method_dropdown.on_change = lambda e: process()

    # ----- File picking / saving -----
    def on_file_picked(e: ft.FilePickerResultEvent):
        if not e.files:
            return
        f = e.files[0]
        path = f.path
        if not path:
            set_status("File path nahi mila. Dobara try karein.", "err")
            page.update()
            return
        ext = os.path.splitext(path)[1].lower()
        if ext not in (".jpg", ".jpeg", ".png"):
            set_status("Sirf JPG, JPEG ya PNG upload karein!", "err")
            page.update()
            return
        img = cv2.imread(path)
        if img is None:
            set_status("File kharab hai ya read nahi ho saki.", "err")
            page.update()
            return

        h, w = img.shape[:2]
        if w > 1080:
            img = cv2.resize(img, (1080, int(h * 1080 / w)), interpolation=cv2.INTER_AREA)
            h, w = img.shape[:2]

        state["orig"] = img
        state["ext"] = ".jpg" if ext in (".jpg", ".jpeg") else ".png"
        state["orig_kb"] = os.path.getsize(path) / 1024.0
        state["orig_score"] = compute_sharpness(img)

        b64, _ = encode_image(img, state["ext"])
        img_split_o.src_base64 = b64
        img_full_o.src_base64 = b64
        card_res.value = f"{w}x{h}"
        placeholder.visible = False
        preview_content.visible = True
        set_status(f"Loaded: {f.name}", "ok")
        process()

    def on_save_click(e):
        if state["proc"] is None:
            return
        try:
            name = f"enhanced_{int(time.time())}{state['ext']}"
            path = save_image(state["proc"], name)
            msg, color = f"Saved: {path}", ft.Colors.GREEN_700
        except Exception as ex:
            msg, color = f"Save fail: {ex}", ft.Colors.RED_700
        page.open(ft.SnackBar(ft.Text(msg), bgcolor=color, duration=5000))

    picker = ft.FilePicker(on_result=on_file_picked)
    page.overlay.append(picker)

    btn_upload = ft.FilledButton(
        "Upload Image", icon=ft.Icons.UPLOAD_FILE, expand=True, height=48,
        style=ft.ButtonStyle(bgcolor=BRAND, color=ft.Colors.WHITE,
                             shape=ft.RoundedRectangleBorder(radius=14)),
        on_click=lambda _: picker.pick_files(
            allow_multiple=False, file_type=ft.FilePickerFileType.IMAGE),
    )
    btn_save = ft.OutlinedButton(
        "Save Result", icon=ft.Icons.DOWNLOAD, expand=True, height=48, disabled=True,
        style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=14)),
        on_click=on_save_click,
    )

    page.add(
        ft.Column(
            [
                header,
                ft.Container(
                    padding=ft.padding.all(16),
                    content=ft.Column(
                        [status_box,
                         ft.Row([btn_upload, btn_save], spacing=10),
                         busy, info_row, preview_card, settings_card,
                         ft.Container(height=16)],
                        spacing=14,
                    ),
                ),
            ],
            expand=True, scroll=ft.ScrollMode.AUTO, spacing=0,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        )
    )


if __name__ == "__main__":
    ft.app(target=main)
