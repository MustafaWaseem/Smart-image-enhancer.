# Smart Image Enhancer

Flet + OpenCV app: image **Sharpen** (Kernel / Unsharp Mask), **Grayscale**, **Auto Contrast**,
side-by-side comparison, live sharpness score, and save result.

## Run on PC
```bash
pip install -r requirements.txt
flet run src/main.py
```

## Build APK
Automatic: push to `main`, then GitHub -> **Actions -> Build Android APK -> Artifacts**.

Manual:
```bash
pip install "flet[all]==0.28.3"
flet build apk
```
APK output: `build/apk/`

Saved images go to `Pictures/SmartImageEnhancer` (or `Download`) on the phone.
