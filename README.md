# VFX Review Player

**Professional VFX Review, Playback & Media Delivery Platform**

A high-performance, studio-grade media review and delivery platform engineered for Visual Effects, Feature Film, and Episodic production pipelines. Built with Python, PyQt6, VisPy (OpenGL), OpenColorIO (OCIO v2), and OpenImageIO.

![VFX Review Player](logo.png)

---

## 1. Overview & Capability Map

VFX Review Player combines playback, image-sequence inspection, color management, multi-shot review, slate and burn-in rendering, and deterministic media delivery into a single unified application:

```text
                         VFX REVIEW PLAYER
                                │
        ┌───────────────────────┼───────────────────────┐
        │                       │                       │
        ▼                       ▼                       ▼
   MEDIA ENGINE           REVIEW ENGINE          DELIVERY ENGINE
        │                       │                       │
  EXR / DPX / TIFF       A/B / Wipe / Splits      Configurable Slates
  ProRes / DNxHR         Multi-Shot Playlist     Burn-in Overlays
  H.264 / H.265 (HEVC)   3-Way Color Wheels      Client & Dailies Presets
  Timecode Engine        False Color & Scopes    ProRes / DNxHR / MP4 / MOV
  Smart Caching          Kitsu Sync & Versioning Annotation Exports
```

### Authoritative Architecture
The viewer and export pipeline are driven by the exact same frame, timebase, and color pipeline:

```text
Source File / Sequence
    ↓
Authoritative Timeline (Frame Number ↔ PTS ↔ SMPTE Timecode ↔ Drop-Frame)
    ↓
RAM / GPU Multi-Tier Cache
    ↓
OpenColorIO / ACES Color Pipeline + ASC CDL (Slope, Offset, Power, Saturation)
    ↓
VisPy GPU Accelerated Canvas (Zero-copy OpenGL display)
    ↓
Delivery Engine (Slate frames + Dynamic Burn-in metadata)
    ↓
Deterministic Multi-Format Exporter (FFmpeg & PyAV)
```

---

## 2. Key Features

### 🎬 VFX-Oriented Playback & Sequence Engine
- **High-Dynamic Range EXR & Image Sequences**: Native OpenImageIO and OpenCV-backed playback for multi-part `.exr`, `.sxr`, `.dpx`, `.cin`, `.tif`, `.tiff`, `.png`, `.jpg`, `.tga`, and `.webp`.
- **Professional Video Codecs**: Hardware-accelerated decoding of Apple ProRes (422 / 422 HQ / 4444 / 4444 XQ), Avid DNxHR, H.264, and H.265 (HEVC) containers (`.mov`, `.mp4`, `.mkv`, `.mxf`).
- **Deterministic Frame & Timebase Engine**: Exact frame indexing, SMPTE timecode calculation (drop-frame and non-drop-frame), fractional/non-integer framerate safety (23.976, 24.0, 29.97, 59.94 fps), and zero-drift A/V sync.
- **Sequence Validation**: Automated missing-frame gap detection, corrupt frame reporting, and timeline gap indicators.
- **Gapless Playlist Playback**: Direct timeline-style cuts between playlist shots with asynchronous background prefetching (`QThreadPool`), eliminating shot-boundary buffering freezes.

### 🎨 Color Management & Grading Tools
- **ACES & OpenColorIO (OCIO v2)**: Complete input colorspace, view transform, and display pipeline supporting ACEScg, ACEScc, Rec.709, sRGB, DCI-P3, and custom studio config files.
- **Interactive 3-Way ASC CDL Wheels**: High-precision Lift (Offset), Gamma (Power), and Gain (Slope) chromatic color wheels with metallic pucks, fine-control (`Shift+Drag`), double-click reset, master exposure/contrast/saturation sliders, and ASC CDL XML import/export.
- **10-Zone False Color Heatmap**: Real-time exposure scale and clipping analysis (crushed blacks, 18% middle gray, skin tones, near-clip, and clipped highlights).
- **Video Scopes**: Live Waveform, RGB Parade, Vectorscope, and Histogram dialogs.
- **Channel & Alpha Inspection**: Instant toggling between RGB, Red, Green, Blue, Alpha, and Alpha Overlays (Checkerboard, Black, White).

### 🔍 Review, Comparison & Production Tracking
- **Multi-Viewport Tile Grid**: 1-up, 2-up (side-by-side), 4-up (2x2), and 6-up (2x3) grid modes with independent drag-and-drop media assignment per tile.
- **Comparison Modes**: Real-time Wipe with draggable wipe line, Side-by-Side split, Difference QC mode, and Version comparison.
- **Version Detection & Navigation**: Automatic version family scanning (`v001`, `v002`, `v003`) with keyboard switching (`Alt+Up`, `Alt+Down`, `Alt+Home`) and 1-click comparison against previous iterations.
- **Kitsu Production Tracking Integration**:
  - Direct connection to Zou/Kitsu servers with secure credential caching.
  - Review playlist browsing with high-speed thumbnail caching.
  - One-click navigation to current shot in Kitsu web dashboard (`Ctrl+K`).
  - Publish review comments, status updates, and annotated viewport frames (`Ctrl+Alt+P`).
  - Shot versions and department task comparison dialog (`Ctrl+Alt+V`).
  - Automated or manual local cache management and cleanup.
- **Persistent Annotations & Review Sidecars**: Vector pen, shapes, text, arrows, color picker, multi-frame undo/redo, auto-saving to `.review.json` sidecars, and batch export of annotated frames (`Ctrl+Shift+E`).

### 📦 Delivery, Slates & Burn-ins
- **Production Slate Builder**: Automated slate frame generation with metadata (Show, Sequence, Shot, Version, Artist, Date, Colorspace, Resolution, FPS, Status, and Studio Logo).
- **Configurable Burn-Ins**: Real-time burn-in overlays including Timecode, Frame Number, Shot Name, Version, Colorspace, Artist, and Custom Text with customizable position, font size, and background opacity.
- **Multi-Format Media Delivery**: Single-pass and batch export to MP4 and MOV using H.264, H.265/HEVC, ProRes, or DNxHR presets.

---

## 3. Keyboard Shortcuts & Navigation

| Category | Shortcut | Action |
|---|---|---|
| **Playback** | `Space` | Play / Pause |
| | `Left` / `Right` | Step 1 Frame Backward / Forward |
| | `Shift+Left` / `Shift+Right` | Step 10 Frames Backward / Forward |
| | `Home` / `End` | Go to First / Last Frame |
| | `I` / `O` | Set In Point / Set Out Point |
| | `L` | Toggle Loop Mode |
| **Playlist / Folder** | `Page Up` / `Page Down` | Previous / Next Clip in Folder or Playlist |
| | `Ctrl+L` | Toggle Left Playlist / Shot Browser Drawer |
| **View & Layout** | `F` | Fit Image to Window |
| | `F11` | Toggle Borderless Fullscreen |
| | `1` / `2` | Minimal Cinema Mode / Normal UI Mode |
| | `S` | Toggle Side-by-Side Comparison |
| | `W` | Toggle Wipe Comparison Mode |
| **Color & Scopes** | `Ctrl+G` | Toggle 3-Way ASC CDL Grading Wheels Panel |
| | `Ctrl+Alt+F` | Toggle 10-Zone False Color Heatmap |
| | `Ctrl+Shift+S` | Open Live Video Scopes (Waveform / Parade / Vectorscope) |
| | `R` / `G` / `B` / `A` | Solo Red, Green, Blue, or Alpha Channel |
| **Annotations & Notes** | `N` or `Shift+A` | Toggle Annotation Drawing Mode |
| | `Ctrl+Z` / `Ctrl+Shift+Z` | Undo / Redo Annotation Stroke |
| | `Ctrl+Shift+E` | Batch Export All Annotated Frames |
| **Studio & Kitsu** | `Ctrl+K` | Open Current Shot in Kitsu Web Browser |
| | `Ctrl+Alt+P` | Publish Review Note & Annotated Frame to Kitsu |
| | `Ctrl+Alt+V` | Open Shot Versions & Task Compare Dialog |
| | `Alt+Up` / `Alt+Down` | Switch to Next / Previous Local Detected Version |
| | `Alt+Home` | Switch to Latest Local Version |

---

## 4. Installation & Requirements

### System Requirements
- **Operating System**: Windows 10 / 11 (64-bit)
- **Python**: 3.10 or 3.11
- **Graphics Hardware**: Dedicated GPU with OpenGL 3.3+ support (NVIDIA, AMD, or Intel Arc)
- **External Binaries**: FFmpeg / FFprobe (bundled automatically or discovered on system `PATH`)

### Running from Source
1. **Clone the repository:**
   ```bash
   git clone https://github.com/azhagurajpandians/vfx-player.git
   cd vfx-player
   ```

2. **Create and activate a Python virtual environment:**
   ```powershell
   python -m venv venv
   .\venv\Scripts\activate
   ```

3. **Install Dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Launch Application:**
   ```bash
   python main.py
   ```

---

## 5. Building & Packaging

### Standalone Executable (cx_Freeze)
To compile a standalone zero-dependency distribution:
```powershell
.\build_cxfreeze.bat
```
The compiled application will be generated in `build/exe.win-amd64-3.11/`.

### Windows Installer (Inno Setup)
To build the lightweight installer with Shell context menu ("Open with VFX Review Player") and file associations:
```powershell
.\build_installer_v1.1.0.bat
```
The final installer binary will be saved in `dist_installer/VFX_Review_Player_Setup_v1.1.0.exe`.

---

## 6. Automated Testing

VFX Review Player includes a comprehensive automated test suite covering color pipelines, ASC CDL wheels, media timeline, Kitsu synchronization, and export workflows:

```powershell
python -m unittest discover -s tests
```

---

## 7. License

Distributed under the [MIT License](LICENSE).
