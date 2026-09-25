# VFX Review Player — Release Notes

## Version 1.1.3 (Current Release)

**Release Date:** September 2026  
**License:** GNU General Public License v3 (GPLv3)  
**Binary Installer:** `VFX_Review_Player_Setup_v1.1.3.exe`  

VFX Review Player v1.1.3 is a major release advancing the platform into a studio-grade review, color grading, multi-shot dailies comparison, and media delivery ecosystem.

---

### Highlights & Key Additions

#### 1. Multi-Shot Synchronized Grid Review (6-Up / 2x3 Tile Mode)
- **Synchronized Sequence Comparison**: Review up to 6 shots simultaneously in a synchronized 2x3 viewport grid with single-master transport control.
- **Shot-to-Shot Continuity**: Compare color, lighting, framing, and pacing across multiple shots in sequence.
- **Slot Assignment**: Drag and drop media or right-click any shot from the Playlist to assign directly to Grid Slots 1 through 6.
- **Unified Scrubbing & Caching**: Multi-threaded frame caching ensures smooth playback across all active grid viewports.

#### 2. Interactive 3-Way ASC CDL Color Grading Wheels
- **Studio-Standard Color Balance**: Added interactive chromatic color wheels for **Offset (Lift)** and **Power (Gamma)** alongside numeric sliders for **Slope (Gain)** and **Saturation**.
- **Real-Time GPU Acceleration**: Custom GLSL shader executes color transformations at zero display latency directly on the GPU canvas.
- **Fine Control & Reset**: Hold `Shift` while dragging color pucks for high-precision adjustments; double-click any wheel to reset to neutral.
- **Industry Interchange**: One-click **Export CDL** and **Import CDL** (`.cdl` / `.cc` XML format) for seamless handoff to Nuke, DaVinci Resolve, or Baselight.

#### 3. Production Tracking & Kitsu / Zou Integration
- **Direct Studio Synchronization**: Native connection to Kitsu/Zou servers with secure credential handling.
- **Supervisor Review Submissions**: Publish review comments, status changes (e.g., *Approved*, *Retake*, *WIP*), and annotated frame snapshots directly to Kitsu (`Ctrl+Alt+P`).
- **Official Zou Preview Workflow**: Automated multi-step preview generation, asset attachment, and comment linking via Zou REST API.
- **Instant Web Navigation**: Jump directly to the active shot in the Kitsu web interface with `Ctrl+K`.
- **Shot Versions & Task Comparison**: Inspect department task revisions, comments, and historical versions (`Ctrl+Alt+V`).

#### 4. Gapless Playlist & Shot Browser
- **Background Prefetching**: Multithreaded `QThreadPool` pre-buffers adjacent playlist shots, eliminating black frames and stutter at cut boundaries.
- **Automated Version Family Detection**: Scans directory structures for version tokens (`v001`, `v002`, `v003`) with keyboard switching (`Alt+Up`, `Alt+Down`) and 1-click comparison.
- **Context Menu Actions**: Quick-play, slot assignment, version comparison, path copying, and playlist management.

#### 5. OpenColorIO (OCIO v2) & Professional Video Pipelines
- **Color Accuracy**: Full input colorspace, view transform, and display pipeline supporting ACEScg, ACEScc, Rec.709, sRGB, and DCI-P3.
- **Native Video Decoding**: Hardware-accelerated decoding of Apple ProRes (422, 422 HQ, 4444, 4444 XQ), Avid DNxHR, H.264, and HEVC.
- **Deep EXR Support**: Multi-channel and multi-part EXR inspection via OpenImageIO.

#### 6. Professional Packaging & Legal Compliance
- **Clean GNU GPLv3 License**: Cleaned license documentation featuring dedicated application header and official terms and conditions.
- **Windows Installer**: Self-contained per-user installer (`dist_installer/VFX_Review_Player_Setup_v1.1.3.exe`) with Explorer context menu ("Open with VFX Review Player") and file associations (`.exr`, `.dpx`, `.cin`, `.mov`, `.mp4`).

---

### Previous Releases

#### Version 1.1.0
- Added GPU color grading and GPUScaledTexture2D HDR EXR rendering.
- Integrated PyAV native video decoder pipeline and zero-drift A/V sync.
- Added 10-zone false color heatmap and video scopes dialog (Waveform, RGB Parade, Vectorscope, Histogram).
- Introduced DJV-style memory cache settings with gigabyte-based capacity management.

#### Version 1.0.0
- Initial production release with core EXR/DPX sequence playback, timeline engine, annotations, and slate/burn-in delivery export.
