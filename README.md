# TransferLoop

**Version 0.2.3**

**Keep your local project in the loop with browser-based AI.**

TransferLoop is a privacy-focused, local-first desktop tool for linking projects on your machine with browser-based AI chats allowing you to  use an agent-like workflow while keeping your system and files your own.

It is designed to work with ChatGPT, Claude, Gemini, or really any AI that can read and return zip files.

TransferLoop keeps the AI interation "manual" by making the local side of the workflow fast, repeatable, and usually only a few clicks.
- This provides the power of AI-assisted project development without the paid token use and limits of tools like Codex or Cursor.
- Because the workflow does not automatically transfer data to or from the browser-based AI, it remains TOS compliant (make sure to read the TOS of your specific AI service to verify)

## Why Use This Tool?

- **Keep your project local.** The AI only receives the files you export. It does not get direct filesystem or shell access.
- **Save time.** I found that using this tool dramatically reduced hallucinations and sped up development time.
- **Choose what gets sent.** File selection and `.aiignore` control which project files can be included in an export.
- **Use the browser AI you already prefer.** TransferLoop is not tied to one provider or API and does not require an AI API key.
- **Send less on later rounds.** After the first export, **Export Changed** can send only files that changed locally. This way you don't need to export the entire project context again for your local changes.
- **Start new chats with durable project context.** `.aimemory` keeps concise project direction, decisions, constraints, open work, notes, and recent accepted changes without storing a chat transcript.
- **Navigate large projects faster.** `PROJECT_MAP.json` indexes folders and files with short responsibility descriptions and documented important symbols; the Project Visualizer makes the same map browsable and editable in the app.
- **Review AI changes before applying them.** Returned files are staged so you can inspect diffs, conflicts, additions, deletions, and AI-reported verification evidence before merging.

## How it works

1. Open a local project in TransferLoop.
2. Review `.aiignore` and choose the project files the AI should receive.
3. When starting a new AI conversation, use **Initialize AI Session — Export All**. TransferLoop creates:
   - the project ZIP
   - a separate `*_AI_INSTRUCTIONS.md` file
4. Click the **Select** action to highlight both files in Explorer or your Linux file manager (when the desktop supports multi-file reveal)
5. Upload both files to your browser-based AI.
5. Work with the AI normally until you want it to make project changes.
6. Download the returned ZIP into the watched response folder, or use **Import ZIP**. The copy button beside **Import ZIP** copies the configured response-folder path to the clipboard.
    - The folder the tool watches for incoming zip files can be set using Edit > Preferences
7. TransferLoop detects the ZIP, validates its manifest/session/path safety, stages the response, and shows the file changes plus any structured AI-reported verification results. Pending responses are remembered across app restarts while the original ZIP still exists.
8. Review the changes and accept, reject, or leave files pending. For retained text baselines, TransferLoop performs a three-way comparison between the original export, the current project, and the incoming AI version. Non-overlapping sequential edits are merged automatically; only overlapping regions are marked **Merge conflict** and skipped by **Accept Safe Changes**. If you intentionally want the incoming whole-file version instead, the conflict dialog offers **Overwrite with AI Version**.
9. Apply the accepted changes. TransferLoop creates a backup and applies the response transactionally; a mid-apply failure automatically rolls project files back.
10. If you make local changes afterward, use **Export Changed** or **Export Selected** to send only the files the AI needs instead of exporting the whole project again.

## Installation

Requirements:

- Python 3.10 or newer
- an internet connection the first time dependencies are installed
- a graphical desktop session supported by Qt/PySide6

### Windows

For normal use, install TransferLoop as a desktop application:

1. Download or clone the project.
2. Make sure Python 3.10 or newer is installed.
3. Double-click `setup.bat`.
4. Launch **TransferLoop** from the Start Menu.

`setup.bat` builds a windowed `TransferLoop.exe`, installs it under `%LOCALAPPDATA%\TransferLoop\App`, creates a Start Menu shortcut, and registers a per-user uninstaller. Mutable settings, project state, backups, logs, and Project Map layout preferences live separately under `%LOCALAPPDATA%\TransferLoop\Data`, so reinstalling the application does not replace user data. The first packaged-app run also recovers the older flat TransferLoop profile even when the installer has already created the new `Data` folder.

`run.bat` remains the source/debug launcher for development. It starts the Python version directly and may show a console window.

### Linux

1. Download or clone the project.
2. Make sure Python 3.10 or newer and Python's `venv` module are installed.
3. Run `./run.sh` from a terminal. If the executable bit was not preserved when the source was downloaded, run `bash run.sh` instead.

On Debian/Ubuntu, the Python prerequisite can typically be installed with:

```bash
sudo apt install python3 python3-venv
```

Both launchers handle the same local setup:

- check that a supported Python version is installed
- create `.venv` inside the TransferLoop project folder
- install the packages in `requirements.txt` the first time they run
- reinstall dependencies if `requirements.txt` changes
- start TransferLoop with the project-local virtual environment

On Linux, TransferLoop stores mutable application data under `$XDG_DATA_HOME/TransferLoop/Data` when `XDG_DATA_HOME` is set, otherwise under `~/.local/share/TransferLoop/Data`. The **Select in File Manager** action uses the freedesktop FileManager1 interface when the desktop provides it and otherwise opens the containing folder.

If PySide6 reports that the Qt `xcb` platform plugin cannot be initialized on a minimal Debian/Ubuntu desktop, install the missing desktop libraries for your distribution. A common starting point is `libxcb-cursor0` and `libxkbcommon-x11-0`.

The `.venv` folder is local to the project and is excluded from TransferLoop exports by `.aiignore`.

## Privacy and control

TransferLoop does not connect a browser AI directly to your machine.

| TransferLoop does | TransferLoop does not |
| --- | --- |
| Open projects you choose | Give the AI unrestricted filesystem access |
| Export selected files | Upload files to AI websites automatically |
| Apply `.aiignore` rules | Submit prompts automatically |
| Track project sync state locally | Scrape browser conversations |
| Stage returned files before merge | Download AI responses automatically |
| Show text diffs and conflict warnings | Silently overwrite local changes |
| Back up files before applying changes | Require an AI API key |
| Let you accept or reject files | Assume every AI response should be applied |

## .aimemory

`.aimemory` is a small project file used to give a new AI conversation useful information from earlier work.

It can include:

- what the project does and its technical snapshot
- current direction
- architecture and important decisions
- constraints and conventions
- open work
- durable project notes
- a short recent history of AI changes that were accepted

TransferLoop handles it as follows:

- full/new-session exports include `.aimemory`
- source files remain the source of truth
- if `.aimemory` disagrees with the project files, the project files win
- TransferLoop protects the accepted-change history from being replaced by an older AI-generated copy
- detailed audit history remains in TransferLoop's internal history store instead of growing `.aimemory` indefinitely; repeated compaction notices are normalized to one concise notice
- AI responses can optionally propose durable `memory_updates`; generated instructions ask for them only when durable project knowledge meaningfully changes, and the review screen keeps them separate and unchecked until the user chooses to retain them

## Project Map and PROJECT_MAP.json

TransferLoop creates and structurally maintains `PROJECT_MAP.json` for each project. The map indexes AI-visible directories and files, preserves AI/user-authored descriptions and important-symbol notes, and derives supported Python import/test relationships automatically.

Open **Project Map** beside the Project files heading to use the embedded map workspace. It provides:

- **Architecture** view with a project-root containment frame, sibling top-level packages, short package descriptions, total file counts, and aggregated relationships
- **Directory** view showing every visible file in the package with a short responsibility description
- **File** view with focused Incoming → Selected file → Outgoing relationships and descriptions on each file card
- browser-style **Back / Forward** navigation plus clickable breadcrumbs (Alt+Left / Alt+Right are supported)
- wheel zoom, primary-button canvas panning, **Fit**, and **100%** controls
- draggable package/file cards whose positions and canvas view are saved outside `PROJECT_MAP.json`, plus **Auto Arrange** and **Reset Layout** controls
- support/config files shown by default with a toggle to hide them, searchable nodes, editable descriptions, symbols, and authored relationships
- an **Open in Editor** action for mapped files

TransferLoop-generated map refreshes are idempotent and do not create a false local-change warning when the map was clean before the refresh. Genuine authored edits to `PROJECT_MAP.json` still participate in the normal Export Changed workflow.

Full/new-session exports always include `PROJECT_MAP.json`. Generated AI instructions tell the AI to read the map after `.aimemory`, use its descriptions and relationships to narrow the initial source search, and update authored map knowledge when implementation changes responsibilities, important symbols, or architectural relationships.

## .aiignore

`.aiignore` controls which project files and folders can be exported.

Before generating an upload, you can right-click an item in the project tree and choose **Add file to .aiignore** or **Add folder to .aiignore**. Folder entries are added with a trailing `/`, which excludes that folder and everything inside it from future exports.

Example:

```text
.venv/
__pycache__/
*.log
build/
runtime/
.env
```

## Project picker

The start screen keeps recent projects searchable by project name or path. A recent project whose folder is temporarily unavailable is retained and marked **Unavailable** instead of being silently removed, which is useful for disconnected drives, network locations, or temporarily unavailable synchronized folders.

## Built-in editor

Double-click a text or code file in the project tree to open it in the built-in editor.

Saved edits are written to the local project and appear in **Export Changed**.

TransferLoop also watches the open project for changes made in external editors and IDEs. Saved file changes update the local-change count automatically, and added, removed, renamed, or newly ignored files refresh the project tree without requiring the project to be reopened. Paths excluded by `.aiignore` are skipped by the watcher.

Shortcuts:

| Shortcut | Action |
| --- | --- |
| `Ctrl+S` | Save current file |
| `Ctrl+Shift+S` | Save all open files |
| `Ctrl+Z` / `Ctrl+Y` | Undo / redo in the editor |
| `Ctrl+F` / `Ctrl+H` | Find / replace |
| `Ctrl+G` | Go to line |
| `Ctrl+P` | Quick Open |
| `Ctrl+W` | Close current tab |
| `Ctrl+Tab` / `Ctrl+Shift+Tab` | Switch tabs |
| `Ctrl+/` | Toggle line comment where supported |
| `Ctrl+E` | Toggle Markdown read / edit mode |
| `Ctrl+Shift+B` | Show or hide the sync sidebar |
| `Ctrl+Alt+Z` | Undo Last Apply |

Open editor tabs refresh after accepted AI changes or an undo.



## AI response ZIP format

The generated AI instructions tell the AI how to return changes.

A response ZIP contains:

- files that were added or modified
- `.ai-response.json`
- deleted files listed in the manifest rather than included as empty placeholders

Example:

```text
response.zip
├── .ai-response.json
├── src/
│   └── gui.py
└── helpers/
    └── progress.py
```

Example `.ai-response.json`:

```json
{
  "format_version": 1,
  "session_id": "TL-ABC123",
  "export_id": "TL-ABC123-E0007",
  "summary": "Added persistent output-directory behavior.",
  "files": [
    {
      "path": "src/gui.py",
      "action": "modified",
      "summary": "Restores and saves the output directory.",
      "details": [
        "Loads the saved path when the window opens.",
        "Stores the new path when the user changes it."
      ]
    }
  ],
  "verification": {
    "status": "partial",
    "checks": [
      {
        "name": "Automated test suite",
        "result": "passed",
        "details": "104 tests passed"
      }
    ],
    "unverified": [
      "Packaged application was not manually launched"
    ]
  }
}
```

Generated AI instructions ask the AI to run relevant tests, add regression coverage when meaningful, and report any gaps instead of implying unperformed checks passed. The optional `verification` object is shown in the Review screen as **AI-reported verification**; TransferLoop does not claim to have independently run those checks.

Generated instructions also use **proportional effort**: at the start of an implementation turn, the AI is told to quickly classify the request as small/local, normal, or cross-cutting/high-risk before broad investigation. It should start with the smallest reasonable scope, keep localized edits narrow with targeted verification, and escalate only when inspection reveals wider dependencies or risk. Shared, architectural, security, persistence, data-integrity, or packaging changes should trigger broader impact analysis and regression testing. This keeps simple UI/text tweaks from paying the same investigation cost as feature work.

TransferLoop checks the ZIP contents against the local project instead of relying only on the manifest. It rejects unsafe manifest paths, wrong-session responses, duplicate/case-colliding manifest paths, and unsupported manifest versions. Recent exports retain an immutable hash baseline plus deduplicated text snapshots. When `export_id` is present, text changes are compared three ways: original export baseline, current local file, and incoming AI file. This allows multiple responses from the same export to preserve previously accepted AI edits or other non-overlapping local edits without forcing a re-export. Only edits that touch the same baseline region are blocked as merge conflicts, and the review UI identifies the conflicting region. Binary files, large text files, and older baselines that do not have a retained text snapshot continue to use conservative whole-file protection. Line-ending-only text differences are treated as materially unchanged for stale-context detection. Accepted AI file states are tracked separately from ordinary export synchronization so the review UI can distinguish prior accepted AI changes from newer local/exported context.

Incoming response ZIPs are fingerprinted by their SHA-256 content rather than filename/timestamp. Renaming, copying, or touching the same response therefore does not make TransferLoop treat it as a new response. Automatic response-folder scanning is also paused while the Review screen owns a response, preventing a second copy from being queued during acceptance.

A missing file in a response ZIP is not treated as deleted. Deletions must be listed with `"action": "deleted"`. Changed exports also tell the AI when a previously synchronized local file was deleted, even though that deleted file cannot be present in the ZIP.






## Project status

- **Responsive dynamic labels:** long export filenames, instruction filenames, export paths, and recent-project paths elide cleanly with full-text tooltips instead of crowding adjacent UI.

TransferLoop is under active development.

## Contributing

Bug reports, feature requests, and pull requests are welcome.

For sync or merge bugs, include the steps that led to the problem when possible.
