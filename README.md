# Knack VFX Player

A high-performance, professional media player designed for Visual Effects workflows. Built with Python, PyQt6, VisPy, and OpenColorIO.

![VFX Player](logo.png)

## Features

- **High-Dynamic Range Playback**: Native support for **EXR sequence** playback with proper linear handling.
- **ProRes & DNxHR Support**: Fallback to FFmpeg for professional video codecs that standard OpenCV builds miss on Windows.
- **ACES Color Management**: Full OpenColorIO (OCIO v2) integration for accurate color pipelines (ACEScg, Rec.709, sRGB, etc.).
- **GPU Acceleration**: Zero-copy video upload and GPU-based color transformations (Exposure/Gamma) for smooth real-time performance.
- **Smart Caching**: Multi-threaded, predictive frame prefetching with customizable cache limits (RAM based).
- **Comparison Tools**: Side-by-Side and Wipe comparison modes.
- **Modern UI**: Clean, dark-themed interface with top-bar OCIO controls and intuitive navigation.

## Requirements

- **OS**: Windows 10/11 (Primary support)
- **Python**: 3.10+
- **GPU**: OpenGL 3.3+ compatible graphics card

## Installation (Source)

1. **Clone the repository:**
   ```bash
   git clone https://github.com/azhagurajpandians/vfx-player.git
   cd vfx-player
   ```

2. **Install Dependencies:**
   It is recommended to use a virtual environment (conda or venv).
   ```bash
   pip install -r requirements.txt
   ```
   *Note: You may need to install `OpenImageIO` and `PyOpenColorIO` binaries manually or via conda if pip packages are unavailable for your platform.*

3. **Run the Player:**
   ```bash
   python main.py
   ```

## Comparison & Navigation
- **Space**: Play/Pause
- **Left/Right Arrow**: Previous/Next Frame
- **Page Up/Down**: Previous/Next File in folder
- **S**: Toggle Side-by-Side View
- **W**: Toggle Wipe View
- **F**: Fit to Window
- **F11**: Fullscreen
- **N** or **Shift+A**: Toggle Annotation Mode (works in Fullscreen)
- **Ctrl+Z / Ctrl+Shift+Z**: Undo / Redo Annotations
- **Ctrl+Shift+E**: Export All Annotated Frames (batch export images)

## Building from Source

To create a standalone EXE distribution:

1. Ensure `cx_Freeze` is installed:
   ```bash
   pip install cx_Freeze
   ```

2. Run the build script:
   ```bash
   .\build_cxfreeze.bat
   ```

3. The output executable will be in `build/exe.win-amd64-3.10/`.

## License

[MIT License](LICENSE)
