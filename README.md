# 📚 Study Manager

**Study Manager** is a cross-platform productivity tool (macOS & Windows) designed to help students and professionals manage their study environments. It allows you to "capture" your current workspace—including browser tabs, open documents, and applications—and save them into specific sessions that can be restored with a single click.

---

## 🚀 Main Features

- **Workspace Snapshot**: Detects open documents (Word, Excel, PowerPoint, PDF/Preview) and browser tabs (Chrome, Safari/Edge).
- **Session Management**: Save, preview, and switch between different study sessions (e.g., "Mathematics", "Deep Work", "Project X").
- **Smart Grouping**: Elements are automatically grouped by application for a cleaner interface.
- **Chrome Profile Support**: Assign specific Chrome profiles to individual URLs. When restoring a session, links will open in the correct profile.
- **Delta Sync**: Real-time background scanning that updates the list without flickering or interrupting your work.
- **One-Click Cleanup**: Close all selected study-related apps instantly.

---

## ⚠️ MANDATORY: Permissions & Setup

Before using the app, you **must** grant specific system permissions, otherwise, the application won't be able to "see" your open windows or browser tabs.

### 🍎 For macOS Users
Since the app uses AppleScript to communicate with other programs, macOS security will block it by default.
1. **Accessibility**: Go to `System Settings > Privacy & Security > Accessibility`. Add and enable **Study Manager**.
2. **Automation**: The first time you run the app, you will see pop-ups asking for permission to control "Google Chrome", "Preview", etc. **Click "OK" on all of them.**
3. **Screen Recording (Optional but recommended)**: In some macOS versions, "Screen Recording" permission is required for the app to detect window titles, even if no actual recording takes place.

### 🪟 For Windows Users
The Windows version uses **UI Automation** to read browser URLs.
1. **Run as Administrator**: For best results in detecting URLs from Chrome or Edge, run the application as an Administrator.
2. **Antivirus**: Some antivirus software may flag the "UI Automation" activity as suspicious. You may need to add the app to your antivirus exclusion list.

---

## 📂 Data Storage
The application stores your sessions and preferences in a hidden folder in your User directory:
- **macOS**: `~/.study_manager/`
- **Windows**: `%LOCALAPPDATA%\StudyManager\`

---

## 🖱️ Pro Tips
- **Right-Click**: Right-click on any element in the list to set "Always Select/Deselect" defaults for that specific app.
- **Chrome Profiles**: Right-click on a Chrome tab to assign it to a specific profile. This is saved permanently for that URL.
- **Asterisk (*)**: An asterisk next to the session name indicates that your current workspace has changed and the session needs to be saved.

---
