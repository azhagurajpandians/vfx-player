# VFX Player — Professional Product & Engineering Audit

**Product classification:** Professional VFX Review, Playback & Media Delivery Platform  
**Audit scope:** Playback, image/video handling, color management, review tools, export, slate/burn-ins, architecture, reliability, packaging, and studio readiness  
**Assessment:** Engineering/product audit based on the current repository implementation

---

## 1. Executive Summary

The application should **not** be evaluated as only a media review player.

It is better understood as a:

> **Professional VFX Review, Playback & Media Delivery Platform**

The current implementation already contains a strong set of capabilities for a VFX-oriented workflow:

- EXR/image-sequence playback
- Video playback
- ProRes / DNxHR workflows
- MP4 / MOV delivery
- H.264 / H.265 (HEVC) encoding support
- ACES / OpenColorIO color management
- GPU-accelerated display
- Smart frame caching and prefetching
- A/B and wipe comparison
- Annotations
- Metadata
- Export pipeline
- Slate frames
- Burn-in information
- Windows packaging/workflow

This makes the product considerably more ambitious than a conventional player.

The main challenge is no longer simply **adding features**. The next stage is making the existing functionality **deterministic, frame-accurate, production-safe, configurable, testable, and studio-ready**.

### Overall assessment

**Current position:** Advanced VFX workstation tool / emerging professional review and delivery application.

**Potential position:** A unified application for:

```text
VFX MEDIA
    ↓
IMPORT / PLAYBACK
    ↓
COLOR MANAGEMENT
    ↓
REVIEW / COMPARE / ANNOTATE
    ↓
SLATE + BURN-IN
    ↓
EXPORT / DELIVERY
    ↓
MP4 / MOV / H.264 / H.265 / ProRes / DNxHR
```

The highest-priority engineering work is around **frame/timebase correctness, deterministic color processing, export/viewer consistency, professional review workflow, media validation, and production reliability**.

---

# 2. Product Capability Map

The application should be evaluated across five major areas.

```text
                         VFX PLAYER
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
        ▼                     ▼                     ▼
      MEDIA                 REVIEW               DELIVERY
      ENGINE                ENGINE                ENGINE
        │                     │                     │
    EXR / Video          A/B / Wipe             Slate
    Sequences            Annotations             Burn-ins
    ProRes               Metadata                Encode
    DNxHR                Compare                 MP4
    H.264/H.265          Notes                   MOV
                                                 H.264
                                                 H.265
                                                 ProRes
                                                 DNxHR
```

Underneath all three should be a common frame pipeline:

```text
Decode
  ↓
Frame / Timebase
  ↓
Cache
  ↓
Color Management
  ↓
Viewer Processing
  ↓
Burn-in / Slate (when exporting)
  ↓
Encoder
```

The key architectural principle is:

> **The viewer and exporter must be driven by the same authoritative frame and color pipeline.**

---

# 3. Existing Strengths

## 3.1 VFX-Oriented Media Support

The project is clearly designed around real VFX media rather than consumer video playback.

Strengths include:

- OpenImageIO-oriented image handling
- EXR sequence workflows
- FFmpeg-backed video handling
- ProRes / DNxHR support
- H.264 / H.265 delivery
- MP4 / MOV output
- GPU display
- OCIO/ACES processing
- Metadata access
- Review-oriented comparison tools

This is a strong foundation.

---

## 3.2 Export Is a Major Product Feature

Export should be considered one of the application's core differentiators, not an auxiliary feature.

The product can function as:

```text
EXR SEQUENCE
      ↓
COLOR / VIEW TRANSFORM
      ↓
SLATE
      ↓
BURN-IN
      ↓
ENCODE
      ↓
MP4 / MOV
```

This makes it useful for:

- Internal dailies
- Client review
- Supervisor review
- Editorial handoff
- Production previews
- Versioned shot delivery
- Quick VFX media conversion

The audit should therefore focus on **making export more deterministic and configurable**, rather than treating export as a missing capability.

---

# 4. Critical Priority — Frame-Accurate Playback

This remains the most important technical area.

The relationship between:

```text
Frame Index
    ↕
FPS
    ↕
Timestamp
    ↕
Decoder PTS
    ↕
Displayed Frame
```

must be authoritative.

Potential problems arise when a player assumes:

```text
time = frame / fps
```

for every media type.

That becomes unsafe for:

- Variable frame rate media
- Non-integer frame rates
- B-frames
- Edit lists
- Stream offsets
- Different time bases
- Container timestamps
- Audio/video synchronization

### Recommendation

Create a dedicated `Timeline/Timebase` service.

It should own:

- Frame number
- Presentation timestamp
- Decode timestamp
- FPS
- Time base
- Start frame
- Duration
- Drop-frame/non-drop-frame behavior
- Timecode conversion

No UI component should independently calculate frame/time relationships.

---

# 5. SMPTE Timecode

Professional review and delivery need first-class timecode.

Support:

- HH:MM:SS:FF
- Non-drop-frame
- Drop-frame
- Start timecode
- Source timecode
- Burn-in timecode
- Timecode overlays
- Timecode-based seeking

Example:

```text
01:02:14:18
```

Timecode should be tied to the same authoritative timeline service used by playback and export.

---

# 6. Professional Timeline

The current timeline should evolve into a production review timeline.

Recommended features:

- Zoom
- Pan
- Frame ruler
- Timecode ruler
- Current-frame indicator
- Start/end range
- In/Out points
- Loop range
- Markers
- Bookmarks
- Missing-frame indicators
- Cache status
- Playback position
- Audio waveform
- Shot boundaries where applicable

Example:

```text
TC     01:00:00       01:00:10       01:00:20
       │              │              │
───────┼──────────────┼──────────────┼────────────
       ▲
       Current Frame

[ IN ]==============================[ OUT ]
              LOOP RANGE
```

---

# 7. Professional Transport Controls

Recommended controls:

- Play
- Pause
- Stop
- Next frame
- Previous frame
- Next key frame where applicable
- Reverse playback
- Fast forward
- Multiple playback speeds
- Shuttle
- Jog
- Loop
- In/Out playback

Common speeds:

```text
-8x -4x -2x -1x
 1x
 2x  4x  8x
```

---

# 8. Scrubbing

Scrubbing should be treated as a specialized high-performance operation.

Requirements:

- Exact-frame seeking
- Low-latency cache lookup
- Predictive decode
- Proxy/thumbnail mode when appropriate
- Decoder seek optimization
- No accidental frame skipping during precision operations

For EXR sequences, frame lookup should be deterministic.

For compressed video, keyframe-aware seeking and forward decode should be used intelligently.

---

# 9. Cache Architecture

The current caching strategy is a good foundation.

A professional version should evolve into:

```text
               CACHE MANAGER
                    │
       ┌────────────┼────────────┐
       ▼            ▼            ▼
    GPU CACHE    RAM CACHE    DISK CACHE
       │            │            │
   Hot frames   Active frames  Persistent
```

Cache keys should account for:

- Source media
- Frame
- Resolution
- Color configuration
- Viewer transform
- Processing state
- Proxy/full-resolution state

This prevents invalid reuse after color or display changes.

---

# 10. Deterministic Color Management

Color management is one of the most important professional areas.

The system should have one authoritative pipeline:

```text
SOURCE
  ↓
INPUT COLORSPACE
  ↓
OCIO / ACES
  ↓
VIEW TRANSFORM
  ↓
VIEWER
```

Export should use the same pipeline:

```text
SOURCE
  ↓
INPUT COLORSPACE
  ↓
OCIO / ACES
  ↓
VIEW TRANSFORM
  ↓
BURN-IN / SLATE
  ↓
ENCODE
```

The viewer and export result should never disagree because they used different color-processing implementations.

---

# 11. OCIO Configuration Management

The application should not depend on a single hard-coded OCIO configuration.

Support:

- Bundled configuration
- Environment configuration
- Show configuration
- Studio configuration
- User configuration
- Config version display

A professional UI should expose:

```text
OCIO Config:
[ Studio ACES 2.0 ▼ ]

Input:
[ ACEScg ▼ ]

View:
[ sRGB / Rec.709 ▼ ]

Look:
[ None ▼ ]
```

---

# 12. Automatic Colorspace Detection

Recommended detection hierarchy:

1. Explicit user override
2. Project/show configuration
3. Metadata
4. Filename/path conventions
5. EXR metadata
6. Safe fallback

The UI should always show the detected result and allow override.

---

# 13. Alpha Support

Professional VFX review needs clear alpha handling.

Support:

- RGB
- RGBA
- Alpha-only
- Straight alpha
- Premultiplied alpha
- Unpremultiply/re-premultiply
- Checkerboard
- Black/white background
- Alpha overlay

Example:

```text
RGBA
 ├─ RGB
 └─ Alpha

Alpha Display:
[ RGB ] [ Alpha ] [ RGBA ]
```

---

# 14. Pixel Inspector

A professional VFX viewer should provide pixel inspection.

Display:

- X/Y
- RGB
- RGBA
- Scene-linear values
- Display-referred values
- Normalized values
- Channel value
- EXR channel name

Potential feature:

```text
Pixel
X: 1042
Y: 612

R: 0.8234
G: 0.7142
B: 0.6127
A: 1.0000

Colorspace: ACEScg
```

---

# 15. Scopes

Recommended scopes:

- Histogram
- Waveform
- RGB Parade
- Vectorscope
- False Color

These are particularly useful for checking:

- Exposure
- Clipping
- Color balance
- Transform errors
- Legal range
- HDR output

---

# 16. EXR Channels / Layers

Professional EXR support should expose channels and layers.

Example:

```text
Channels

beauty
 ├─ R
 ├─ G
 ├─ B
 └─ A

diffuse
 ├─ R
 ├─ G
 └─ B

specular
 ├─ R
 ├─ G
 └─ B

crypto_object
 ├─ R
 ├─ G
 └─ B
 └─ A
```

Useful actions:

- Solo layer
- RGB
- Alpha
- Channel selection
- Channel search
- Layer comparison

---

# 17. Multi-Part / Tiled / Deep EXR

The application should either support or clearly diagnose:

- Multipart EXR
- Tiled EXR
- Deep EXR
- Mipmapped EXR
- Large-resolution images

If a feature is unsupported, the application should explain why instead of silently failing.

---

# 18. Data Window / Display Window / Overscan

These are critical for VFX.

Support:

- Display window
- Data window
- Overscan
- Cropping
- Fit-to-display
- Fit-to-data
- Pixel aspect ratio

The viewer should make it clear which region is being displayed.

---

# 19. Image Sequence Detection

Sequence detection should support production naming patterns.

Examples:

```text
shot_010_v001.1001.exr
shot_010_v001.1002.exr
shot_010_v001.1003.exr
```

Validation should identify:

- Missing frames
- Duplicate frames
- Corrupt frames
- Resolution changes
- Color-space changes
- Channel changes
- Frame-range gaps

Example:

```text
1001 ─ 1002 ─ 1003 ─ [MISSING] ─ 1005
```

---

# 20. Version Management

VFX workflows are fundamentally version-driven.

Recognize:

```text
shot010_v001
shot010_v002
shot010_v003
shot010_v004
```

Provide:

- Version detection
- Version list
- Latest version
- A/B version compare
- Version switching
- Version history
- Missing version detection

---

# 21. A/B Comparison

Existing A/B and wipe functionality is a strong feature.

It should be expanded with:

- A/B
- Side-by-side
- Wipe
- Vertical split
- Horizontal split
- Flicker
- Difference
- Absolute difference
- Onion skin

Example:

```text
A                  B
───────────────│───────────────
 Version 12     │ Version 13
                │
                │
```

---

# 22. Difference / QC Mode

A dedicated QC comparison mode would be extremely valuable.

Modes:

```text
Difference
Absolute Difference
Flicker
Overlay
A/B
Wipe
```

Useful for detecting:

- Matte changes
- Tracking errors
- Edge changes
- Render differences
- Frame mismatches
- Color differences

---

# 23. Playlist / Flipbook

The application should support a review playlist.

Example:

```text
REVIEW SESSION

001  shot010_v012
002  shot020_v008
003  shot030_v004
004  shot040_v019
```

Features:

- Drag/drop ordering
- Per-item duration
- Loop
- Auto advance
- Shot labels
- Version labels
- Notes
- Status

---

# 24. Contact Sheet

A VFX-oriented contact sheet is a high-value productivity feature.

Generate thumbnails for:

- Shots
- Versions
- Frames
- Review sessions

Display:

```text
┌────────┐ ┌────────┐ ┌────────┐
│010 v12 │ │020 v08 │ │030 v04 │
├────────┤ ├────────┤ ├────────┤
│040 v19 │ │050 v02 │ │060 v11 │
└────────┘ └────────┘ └────────┘
```

---

# 25. Persistent Annotations

Annotations should survive application/project restarts.

Each annotation should store:

```text
Shot
Version
Frame
Timecode
Position
Type
Comment
Author
Priority
Status
Timestamp
```

Annotation types:

- Draw
- Arrow
- Circle
- Rectangle
- Freehand
- Text
- Point
- Measurement

---

# 26. Review Notes

Review notes should become structured data.

Example:

```text
Frame: 1042
TC: 01:00:01:18

NOTE:
"Edge matte is too soft."

Status:
[ Open ]

Priority:
[ High ]
```

Potential states:

```text
Open
In Progress
Fixed
Approved
Rejected
```

---

# 27. Review Export

Review data should be exportable.

Recommended formats:

- PDF
- HTML
- JSON
- CSV

A review report could contain:

```text
SHOT 010
VERSION 023

Frame 1042
TIME 01:00:01:18
Issue: Matte edge too soft
Priority: High
Status: Open

Frame 1088
TIME 01:00:03:16
Issue: Tracking slip
Priority: Medium
Status: Fixed
```

---

# 28. Slate System

Slate generation should be treated as a first-class delivery feature.

A configurable slate builder should support:

- Show
- Sequence
- Shot
- Version
- Artist
- Department
- Date
- Frame range
- FPS
- Resolution
- Colorspace
- Notes
- Custom fields
- Studio branding
- Logo

Example:

```text
┌──────────────────────────────────────┐
│              SHOW NAME               │
│                                      │
│              SHOT 010                │
│              VERSION 023             │
│                                      │
│ Artist: Artist Name                  │
│ Frame Range: 1001 - 1100             │
│ FPS: 24                              │
│ Resolution: 2048 x 1152              │
│ Colorspace: ACEScg                   │
│                                      │
└──────────────────────────────────────┘
```

---

# 29. Burn-In System

Burn-ins should be configurable rather than hard-coded.

Possible fields:

- Shot
- Version
- Frame
- Timecode
- Filename
- Resolution
- FPS
- Colorspace
- Artist
- Date
- Project
- Custom text

Controls:

- Font
- Size
- Position
- Alignment
- Opacities
- Background
- Safe area
- Margin

---

# 30. Burn-In Presets

Recommended presets:

### Client Review

```text
Shot
Version
Timecode
Frame
```

### Internal VFX Review

```text
Shot
Version
Frame
Artist
Colorspace
```

### Dailies

```text
Shot
Version
Timecode
Frame
Filename
```

### Custom

User-defined template.

Presets should be saveable and reusable.

---

# 31. Export Pipeline

The export pipeline is already an important product capability.

The next architectural goal should be:

```text
             EXPORT JOB
                 │
        ┌────────┼────────┐
        ▼        ▼        ▼
      Source   Slate   Burn-in
        │        │        │
        └────────┼────────┘
                 ▼
          Color Pipeline
                 ▼
              Encode
                 ▼
           Output File
```

Every export should be reproducible from a stored configuration.

---

# 32. Viewer-to-Export Consistency

This is a critical professional requirement.

If the viewer shows:

```text
ACEScg → Rec.709
Exposure +1
Gamma 0.9
```

the exported movie should use the same effective processing when the user chooses that mode.

Avoid separate implementations of:

- OCIO conversion
- Exposure
- Gamma
- Frame selection
- Aspect handling

Centralize them.

---

# 33. Professional Export Formats

Recommended export matrix:

| Format | Codec | Purpose |
|---|---|---|
| MP4 | H.264 | General review |
| MP4 | H.265/HEVC | High-quality compact review |
| MOV | H.264 | Review |
| MOV | H.265/HEVC | Compact high-quality review |
| MOV | ProRes | Production review |
| MOV | DNxHR | Editorial / production |
| Image sequence | EXR/PNG/etc. | High-quality interchange |

Presets should expose:

- Resolution
- FPS
- Codec
- Bitrate
- CRF/quality
- Pixel format
- Audio
- Color range
- Color transform
- Slate
- Burn-ins

---

# 34. High-Bit-Depth Video

Avoid unnecessarily reducing high-quality media to 8-bit too early.

Professional pipeline should support appropriate:

- 8-bit
- 10-bit
- 12-bit where codec/container allows
- RGB/YUV formats
- Alpha where supported

The internal representation should remain high precision until the final conversion required by the encoder.

---

# 35. HDR

HDR requires more than selecting an OCIO view.

A professional HDR workflow needs:

- HDR transfer functions
- Display capability awareness
- 10-bit output
- Correct pixel format
- Metadata where required
- OS/GPU/display handling
- HDR export presets

---

# 36. Legal / Full Range

Provide explicit handling for:

- Full range
- Limited/legal range
- RGB range
- YUV range

The user should be able to identify the active range rather than relying on hidden assumptions.

---

# 37. Audio

For video review, professional audio support should include:

- Audio playback
- Waveform
- Audio meters
- Channel selection
- Mute
- Solo
- Gain
- Offset
- Sync controls

---

# 38. A/V Synchronization

Audio and video should share the authoritative timeline.

The system should diagnose:

- Audio offset
- Missing audio
- Drift
- Unsupported sample rates
- Stream duration mismatch

---

# 39. Framing / Viewer Controls

Recommended viewer controls:

- Fit
- 100%
- 200%
- 400%
- Zoom
- Pan
- Center
- Pixel-perfect
- Aspect correction
- Safe area

---

# 40. Guides / Masks

Useful professional overlays:

- Action safe
- Title safe
- Center
- Rule of thirds
- Crosshair
- Aspect-ratio guides
- Custom masks
- Letterbox
- Crop guides

---

# 41. Project / Session Persistence

A professional application should have a project/session format.

For example:

```text
VFX Review Project
├── Media
├── Versions
├── Playlist
├── Timeline
├── Annotations
├── Notes
├── Color Settings
├── Viewer Settings
├── Slate Settings
├── Burn-in Settings
└── Export Presets
```

Suggested extension:

```text
.vfxreview
```

or

```text
.vfxplayer
```

---

# 42. File / Sequence Browser

A production-oriented browser should understand:

- Sequences
- Shots
- Versions
- Frame ranges
- File patterns
- Missing frames

Example:

```text
SHOW
└── SEQ010
    ├── SH010_v012
    ├── SH010_v013
    ├── SH020_v008
    └── SH030_v004
```

---

# 43. Studio Integration

Future integrations could include:

- Nuke
- Houdini
- Maya
- DaVinci Resolve
- ShotGrid / Autodesk Flow Production Tracking
- ftrack
- Kitsu

Potential actions:

```text
Open Shot
Open Latest Version
Send Review
Create Review Movie
Publish
Reveal Source
```

---

# 44. Keyboard Customization

A professional application needs configurable shortcuts.

Example:

```text
Space       Play/Pause
←           Previous Frame
→           Next Frame
I           Set In
O           Set Out
L           Loop
A           A/B
W           Wipe
D           Difference
B           Bookmark
N           Annotation
```

Users should be able to customize these.

---

# 45. Command Palette

A command palette can dramatically improve discoverability.

Example:

```text
> Export Review Movie
> Load Latest Version
> Toggle Alpha
> Show Waveform
> Set In Point
> Set Out Point
> Add Bookmark
> Compare With Previous
> Open Slate Editor
> Open Burn-in Editor
```

---

# 46. Diagnostics Panel

Production software should explain what is happening.

Display:

```text
MEDIA
Resolution: 2048x1152
FPS: 24
Frames: 1001-1100
Codec: ProRes 4444
Pixel Format: 10-bit

COLOR
OCIO: Studio Config
Input: ACEScg
View: Rec.709

PERFORMANCE
GPU: ...
Cache: 78%
FPS: 24
Dropped: 0
Decode: ...
```

---

# 47. Performance HUD

Useful indicators:

- Current FPS
- Target FPS
- Decode time
- Render time
- GPU time
- Cache hit rate
- Cache memory
- Dropped frames
- Audio latency

---

# 48. Dropped Frame Accounting

Do not merely display an FPS number.

Track:

```text
Target: 24 fps
Actual: 23.98 fps
Dropped: 3
Late: 7
Cache Hits: 96%
```

This gives supervisors and artists confidence in playback accuracy.

---

# 49. Benchmark Mode

Add a repeatable benchmark.

Example:

```text
Media: 4K EXR
Frames: 1001-1100
OCIO: ACEScg → Rec709
GPU: ...
Cache: ...
Average FPS: 31.4
Min FPS: 22.1
Dropped: 2
```

This is valuable for debugging and hardware certification.

---

# 50. Error Handling

Avoid broad exception swallowing.

Every failure should identify:

- Operation
- File
- Frame
- Error
- Suggested action

Example:

```text
Unable to decode frame 1042.

File:
shot010_v023.1042.exr

Reason:
Unsupported EXR channel format.

Action:
Open Diagnostics
```

---

# 51. Logging

Use structured logging.

Recommended levels:

```text
DEBUG
INFO
WARNING
ERROR
CRITICAL
```

Log context should include:

- Media
- Frame
- Operation
- Thread
- GPU
- Decoder
- Export job

---

# 52. Crash Diagnostics

A professional build should collect:

- Application version
- OS
- GPU
- Driver
- Python/runtime
- FFmpeg version
- OCIO version/config
- Last operation
- Recent errors

Avoid hiding failures behind global exception handlers.

---

# 53. Dependency Management

The project should have one authoritative dependency strategy.

Avoid configuration drift between:

- requirements.txt
- environment.yml
- packaging configuration
- CI environment

Pin or constrain important binary dependencies where reproducibility matters.

---

# 54. Packaging / Release

Production releases should provide:

- Version number
- Build number
- Installer
- Portable option if useful
- FFmpeg packaging strategy
- OCIO config packaging
- GPU capability check
- Upgrade path
- Release notes

---

# 55. CI/CD

Recommended automated checks:

```text
Lint
 ↓
Unit Tests
 ↓
Media Tests
 ↓
Color Tests
 ↓
Export Tests
 ↓
Package Build
 ↓
Installer Validation
```

---

# 56. Automated Media Regression Tests

Build a controlled test media library.

Test:

- EXR
- Multipart EXR
- Different resolutions
- Alpha
- Video
- H.264
- H.265
- ProRes
- DNxHR
- Missing frames
- Corrupt frames
- Non-integer FPS
- Different timecodes

---

# 57. Golden-Image Color Tests

Color management needs image-based regression tests.

Example:

```text
Input EXR
   ↓
OCIO Transform
   ↓
Rendered Image
   ↓
Compare against Golden Image
```

This catches accidental changes to:

- OCIO
- Exposure
- Gamma
- LUTs
- Renderer
- Pixel conversions

---

# 58. GPU Fallback

A production application should have multiple rendering paths.

```text
Preferred GPU Renderer
        ↓
Fallback Renderer
        ↓
CPU / Compatibility Mode
```

The user should receive a clear diagnostic if acceleration is unavailable.

---

# 59. Renderer Abstraction

Avoid tying the whole application to one rendering implementation.

A renderer interface could support:

```text
Renderer
 ├── GPU Renderer
 ├── Compatibility Renderer
 └── CPU Renderer
```

This improves portability and testing.

---

# 60. Code Organization

The main application window has become large.

The long-term architecture should separate:

```text
UI
│
├── Main Window
├── Viewer
├── Timeline
├── Export UI
└── Review UI

Services
│
├── Media Service
├── Timeline Service
├── Cache Service
├── Color Service
├── Annotation Service
├── Export Service
├── Slate Service
└── Burn-in Service

Models
│
├── Project
├── Shot
├── Version
├── Media
├── Review
└── Export Job
```

This will make the application much easier to maintain.

---

# 61. Recommended Professional Architecture

```text
                        VFX PLAYER
                             │
        ┌────────────────────┼────────────────────┐
        │                    │                    │
        ▼                    ▼                    ▼
     PROJECT              MEDIA                REVIEW
     MANAGER              ENGINE                ENGINE
        │                    │                    │
        │              ┌─────┼─────┐         ┌───┼────┐
        │              │     │     │         │   │    │
        │             EXR   VIDEO AUDIO      A/B Notes QC
        │                    │
        └────────────────────┼────────────────────┘
                             ▼
                      TIMELINE ENGINE
                             │
                      CACHE MANAGER
                             │
                     COLOR PIPELINE
                             │
                       GPU RENDERER
                             │
                    ┌────────┴────────┐
                    ▼                 ▼
                  VIEWER            EXPORT
                                      │
                              ┌───────┼────────┐
                              ▼       ▼        ▼
                            SLATE  BURN-IN   ENCODE
                                              │
                                ┌─────────────┼────────────┐
                                ▼             ▼            ▼
                               MP4           MOV        IMAGE SEQ
                                │
                         H.264 / H.265
                         ProRes / DNxHR
```

---

# 62. Priority Roadmap

## P0 — Production-Critical

These should be addressed first.

### P0.1 Frame / Timebase Engine
- Frame-accurate playback
- PTS handling
- Timecode
- Non-integer FPS
- VFR safety
- Seek correctness

### P0.2 Viewer/Export Pipeline Unification
- One authoritative frame pipeline
- One color pipeline
- Consistent exposure/gamma
- Consistent frame selection

### P0.3 Export Reliability
- H.264
- H.265/HEVC
- ProRes
- DNxHR
- MP4
- MOV
- High-bit-depth paths

### P0.4 Slate/Burn-in System
- Slate editor
- Burn-in editor
- Presets
- Timecode
- Frame
- Shot/version
- Custom metadata

### P0.5 Media Validation
- Missing frames
- Corrupt frames
- Inconsistent sequences
- Codec errors
- Clear diagnostics

---

# 63. P1 — Professional Review Workflow

- Professional timeline
- Jog/shuttle
- Reverse playback
- In/Out
- Loop
- Bookmarks
- Playlist
- Contact sheet
- Version management
- Difference mode
- Flicker
- Persistent annotations
- Structured notes
- Review report export
- Pixel inspector
- Scopes
- Alpha tools
- EXR channel/layer tools
- Audio waveform/meters

---

# 64. P2 — Studio Platform

- Studio OCIO profiles
- Automatic colorspace detection
- Project/session format
- Shot browser
- DCC integrations
- Production tracking integrations
- Configurable keyboard profiles
- Command palette
- Plugin/API system
- Remote review
- Enterprise deployment
- Centralized presets/configuration

---

# 65. Recommended UI Structure

The product should feel like a VFX workstation application rather than a generic media player.

```text
┌───────────────────────────────────────────────────────────────┐
│ PROJECT  MEDIA  REVIEW  COMPARE  EXPORT  VIEW  SETTINGS      │
├───────────────┬───────────────────────────────┬───────────────┤
│               │                               │               │
│ MEDIA / SHOT  │                               │ INSPECTOR     │
│ BROWSER       │          VIEWER               │               │
│               │                               │ Metadata      │
│ Shot 010      │                               │ Channels      │
│  v023         │                               │ Color         │
│  v022         │                               │ Annotations   │
│               │                               │ Export        │
│ Shot 020      │                               │               │
│               │                               │               │
├───────────────┴───────────────────────────────┴───────────────┤
│ Timeline / Timecode / Markers / Cache / Audio                │
├───────────────────────────────────────────────────────────────┤
│ ◀  ◀◀  ▶  ▶▶   IN   OUT   LOOP     FRAME   TC   FPS          │
└───────────────────────────────────────────────────────────────┘
```

Export should have its own focused workspace:

```text
┌─────────────────────────────────────────────────────┐
│ EXPORT REVIEW MOVIE                                 │
├─────────────────────────────────────────────────────┤
│ Source:      shot010_v023                           │
│ Frame Range: 1001 - 1100                            │
│ FPS:         24                                     │
│                                                     │
│ Format:      MOV ▼                                  │
│ Codec:       H.265 ▼                                │
│ Resolution:  2048x1152 ▼                            │
│ Quality:     High                                   │
│                                                     │
│ ☑ Add Slate                                         │
│ ☑ Add Burn-in                                       │
│ ☑ Timecode                                          │
│ ☑ Frame Number                                      │
│                                                     │
│ Slate:       Client Review ▼                        │
│ Burn-in:     Client Review ▼                        │
│                                                     │
│ [ Preview ]                       [ EXPORT ]         │
└─────────────────────────────────────────────────────┘
```

---

# 66. Product Differentiators

The application has the potential to differentiate itself by combining functions that are often split between several tools.

### Typical workflow

```text
VFX Player
   ↓
Screenshot
   ↓
Separate Slate Tool
   ↓
Separate Burn-in Tool
   ↓
FFmpeg command
   ↓
Review Movie
```

### Target workflow

```text
VFX Player
   ↓
Review
   ↓
Compare
   ↓
Annotate
   ↓
Select Version
   ↓
Slate
   ↓
Burn-in
   ↓
Export
   ↓
MP4 / MOV
```

That is a much stronger product proposition.

---

# 67. What Should NOT Be Treated as Missing

The following are already meaningful product capabilities and should be represented as **existing strengths** in future audits:

- MP4 export
- MOV export
- H.264
- H.265 / HEVC
- ProRes workflows
- DNxHR workflows
- Slate frames
- Burn-in frames/information
- EXR playback
- Video playback
- OCIO/ACES
- GPU display
- Smart caching
- A/B comparison
- Wipe comparison
- Annotations
- Metadata

The engineering goal is to make these capabilities **more configurable, reliable, reproducible, and integrated**.

---

# 68. Final Assessment

The project is significantly more than a media player.

Its strongest product direction is:

> **A VFX review, playback, comparison, annotation, slate, burn-in, and media-delivery application built around high-quality image sequences and professional video formats.**

The application already has many of the ingredients required for this.

The next stage should focus on **professionalization rather than feature accumulation**.

The three highest-value improvements are:

### 1. Trust the frame

Make frame, timestamp, timecode, seeking, playback, and export mathematically deterministic.

### 2. Trust the image

Make the color pipeline authoritative, consistent, high precision, and identical between viewer and export.

### 3. Trust the delivery

Make slate, burn-in, encoding, metadata, presets, and output validation deterministic and repeatable.

Once these are solid, the remaining features—scopes, version browser, contact sheets, review notes, integrations, and studio automation—can build on a reliable foundation.

---

# 69. Target End State

```text
                 PROFESSIONAL VFX PLATFORM
                           │
       ┌───────────────────┼───────────────────┐
       │                   │                   │
       ▼                   ▼                   ▼
     REVIEW             PLAYBACK             DELIVERY
       │                   │                   │
     Compare             Frame               Slate
     Annotate            Accurate             Burn-in
     Notes               Timecode             Encode
     Versions            Color                Presets
     QC                  Audio                MP4/MOV
     Scopes              Cache                H.264/H.265
     Channels            GPU                  ProRes/DNxHR
       │                   │                   │
       └───────────────────┼───────────────────┘
                           ▼
                  PROJECT / SESSION
                           │
                           ▼
                   STUDIO WORKFLOW
```

**Recommended product name/category:**

> **VFX Review & Media Delivery Platform**

rather than simply **VFX Player**.

**Target maturity:**

```text
Current Foundation        ███████████████░░░░░
Professional Product      ████████████████████
Studio Platform           █████████████████████
```

The project is on a credible path toward a professional VFX production tool. The key now is to harden the underlying media/timebase/color/export architecture and then build the studio workflow layer on top of it.
