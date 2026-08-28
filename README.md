# TransferLoop

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
- **Start new chats with project history.** `.aimemory` gives a new conversation the project overview and a record of accepted changes.
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
6. Download the returned ZIP into the watched response folder, or use **Import ZIP**.
    - The folder the tool watches for incoming zip files can be set using Edit > Preferences
7. TransferLoop detects the ZIP, stages the response, and shows the file changes.
8. Review the changes and accept or reject the files you want.
9. Apply the accepted changes. TransferLoop creates a backup before writing to the project.
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

- what the project does
- project structure or technical notes
- project-specific context
- a limited history of AI changes that were accepted

TransferLoop handles it as follows:

- full/new-session exports include `.aimemory`
- source files remain the source of truth
- if `.aimemory` disagrees with the project files, the project files win
- TransferLoop protects the accepted-change history from being replaced by an older AI-generated copy

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

TransferLoop checks the ZIP contents against the local project instead of relying only on the manifest.

A missing file in a response ZIP is not treated as deleted. Deletions must be listed with `"action": "deleted"`.






## Contributing

Bug reports, feature requests, and pull requests are welcome.

For sync or merge bugs, include the steps that led to the problem when possible.
