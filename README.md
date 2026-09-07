# TransferLoop

**Version 0.1.10**

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
- **Review AI changes before applying them.** Returned files are staged so you can inspect diffs, conflicts, additions, and deletions before merging.

## How it works

1. Open a local project in TransferLoop.
2. Review `.aiignore` and choose the project files the AI should receive.
3. When starting a new AI conversation, use **Initialize AI Session — Export All**. TransferLoop creates:
   - the project ZIP
   - a separate `*_AI_INSTRUCTIONS.md` file
4. Click "select in explorer" to highlight both files in explorer
5. Upload both files to your browser-based AI.
5. Work with the AI normally until you want it to make project changes.
6. Download the returned ZIP into the watched response folder, or use **Import ZIP**. The copy button beside **Import ZIP** copies the configured response-folder path to the clipboard.
    - The folder the tool watches for incoming zip files can be set using Edit > Preferences
7. TransferLoop detects the ZIP, validates its manifest/session/path safety, stages the response, and shows the file changes. Pending responses are remembered across app restarts while the original ZIP still exists.
8. Review the changes and accept, reject, or leave files pending. **Accept Safe Changes** skips conflicted files by default. When conflicts are reported, the warning offers **Ignore Warning and Overwrite** if you intentionally want the AI versions to replace those local files; overwritten files are treated as synchronized after the accepted response is applied.
9. Apply the accepted changes. TransferLoop creates a backup and applies the response transactionally; a mid-apply failure automatically rolls project files back.
10. If you make local changes afterward, use **Export Changed** or **Export Selected** to send only the files the AI needs instead of exporting the whole project again.

## Installation

### Windows source release


Requirements:

- Python 3.10 or newer
- an internet connection the first time dependencies are installed

To run TransferLoop:

1. Download or clone the project.
2. Make sure Python 3.10 or newer is installed.
3. Double-click `run.bat`.

`run.bat` handles the local setup:

- checks that Python is installed
- creates `.venv` inside the TransferLoop project folder
- installs the packages in `requirements.txt` the first time it runs
- reinstalls dependencies if `requirements.txt` changes
- starts TransferLoop with the project-local virtual environment

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
- detailed audit history remains in TransferLoop's internal history store instead of growing `.aimemory` indefinitely
- AI responses can optionally propose durable `memory_updates`; the review screen keeps these separate and unchecked until the user chooses to retain them

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
  ]
}
```

TransferLoop checks the ZIP contents against the local project instead of relying only on the manifest. It rejects unsafe manifest paths, wrong-session responses, duplicate/case-colliding manifest paths, and unsupported manifest versions. When `export_id` is present, conflicts are checked against the exact retained baseline for that export. Conflict warnings are conservative by default, but the review dialog provides an explicit **Ignore Warning and Overwrite** action for intentional replacements; accepted overwritten paths become the new synchronized local state after apply.

Incoming response ZIPs are fingerprinted by their SHA-256 content rather than filename/timestamp. Renaming, copying, or touching the same response therefore does not make TransferLoop treat it as a new response. Automatic response-folder scanning is also paused while the Review screen owns a response, preventing a second copy from being queued during acceptance.

A missing file in a response ZIP is not treated as deleted. Deletions must be listed with `"action": "deleted"`. Changed exports also tell the AI when a previously synchronized local file was deleted, even though that deleted file cannot be present in the ZIP.






## Project status

- **Responsive dynamic labels:** long export filenames, instruction filenames, export paths, and recent-project paths elide cleanly with full-text tooltips instead of crowding adjacent UI.

TransferLoop is under active development.

## Contributing

Bug reports, feature requests, and pull requests are welcome.

For sync or merge bugs, include the steps that led to the problem when possible.
