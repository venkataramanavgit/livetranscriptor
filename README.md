# LiveTranscriptor (Windows) – Loopback Audio → Meeting Notes

This app records your PC speaker output (loopback capture) and converts speech to text using **Vosk**.

It writes a timestamped transcript file like: `Meeting_Notes_YYYYMMDD_HHMMSS.txt` and opens it when you stop.

---

## Features

- Captures **system audio** (what you hear from speakers/headphones) using `pyaudiowpatch`
- Offline speech-to-text using **Vosk**
- Saves transcript with timestamps
- Stops with `Ctrl + C` and auto-opens the text file

---

## Requirements

- Windows 10/11
- Python 3.9+ recommended
- Working audio output device
- Vosk English model (repo contains: `assets/vosk-model-small-en-us-0.15/`)

---

## Run from Source (Dev)

### 1) Create and activate a virtual environment

```bat
python -m venv myenv
myenv\Scripts\activate
```

### 2) Install dependencies

```bat
pip install --upgrade pip
pip install numpy vosk pyaudiowpatch
```

### 3) Run

```bat
python main.py
```

Stop with `Ctrl + C` to open the generated transcript file.

---

# Build a Windows .EXE (Bundle) – Step by Step

## Option A (Recommended): EXE + model folder next to it

This avoids packing the huge model into the exe (faster build, smaller exe).

### 1) Install PyInstaller

```bat
pip install pyinstaller
```

### 2) Build the exe

From the project folder:

```bat
pyinstaller --noconfirm --clean --onefile --name LiveTranscriptor main.py
```

This creates:

- `dist\LiveTranscriptor.exe`
- `build\...` (temporary build files)

### 3) Prepare a “release” folder you can run/share

Folder layout:

```
release/
  LiveTranscriptor.exe
  assets/
    vosk-model-small-en-us-0.15/
```

Commands to create it:

```bat
mkdir release
copy dist\LiveTranscriptor.exe release\
xcopy assets release\assets /E /I
```

### 4) Run and enjoy

```bat
release\LiveTranscriptor.exe
```

To share with others: zip the `release/` folder and send it. They can run the exe without installing Python.

---

## Option B: Bundle the model inside the exe (not recommended)

Not recommended because Vosk model is large; build time + exe size becomes huge, and GitHub may reject pushes.

If you still want it, you must:
- modify code to load the model from PyInstaller’s temp folder, and
- use `--add-data` in the build command.

---

## Notes / Troubleshooting

- If you get “Could not find loopback device”, change Windows default output device in Sound settings and try again.
- First run can take time because the Vosk model loads.
- Stop with `Ctrl + C` to close and open the transcript automatically.

---

## GitHub (Important)

Do NOT commit/push these:

- `myenv/` (virtual environment)
- `build/`, `dist/` (PyInstaller outputs)
- `assets/vosk-model*/` (very large model folder; GitHub may reject)

This repo’s `.gitignore` is configured to ignore them.
