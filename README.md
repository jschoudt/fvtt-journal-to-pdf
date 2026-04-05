# FVTT Journal → PDF

Export **Foundry Virtual Tabletop (FVTT)** journals to beautifully formatted, print-ready PDF documents.

This desktop companion application converts Foundry journal exports (ZIP files) into structured PDFs with:

* Hierarchical **Table of Contents** with dotted leaders
* Clickable internal navigation
* Automatic **Back-to-TOC** links on every page
* Embedded images (PNG, WebP, SVG)
* Preserved tables and formatting
* Actor / Scene / Macro references converted into readable placeholders
* Support for both **single journal** and **folder exports**

Designed for Game Masters, publishers, and content creators who want professional-quality documents from Foundry content.

---

## ✨ Features (v1.5)

* 📚 Multi-journal selection UI
* 📑 Automatic hierarchical Table of Contents
* 🔗 Clickable navigation throughout the document
* 🖼 Image extraction from Foundry Assets folder
* 🧾 Table preservation from journal HTML
* 🧭 Internal bookmarks for PDF readers
* 🔁 Back-to-TOC links (top & bottom of pages)
* 📦 Supports:

  * Single journal export (`journal.json`)
  * Folder export (`manifest.json` + journals/)
* 🧩 Foundry entity links converted into readable text placeholders
* 🖨 Print-friendly layout
* 🎨 Optional full-page PDF backgrounds (built-in or custom image)

---

## 🖥 Screenshots
1. Open your *.zip that was created with the required, companion FoundryVTT module (https://github.com/Gacky2k/journal-resolver-exporter).
2. Select a builtin background image or browse to add your own!
3. Optionally specify mode:  Fill, Fit, Stretch or Tile.
4. Set Opacity (0-100) 100=full opacity and 0=full transparancy.
5. Optionally apply to only first page.
6. Click "Generate PDF..." once you're happy with your settings!

   
<img width="1102" height="732" alt="image" src="https://github.com/user-attachments/assets/a6ce8a35-526e-4e21-ab39-cc0b3ae150c3" />

<img width="728" height="944" alt="image" src="https://github.com/user-attachments/assets/5a0f092d-30ee-413a-8a18-2457443ff472" />

---

## 📦 Installation

### Option 1 — Run from Source (Recommended for Developers)

Requirements:

* Python **3.10+**
* Windows / macOS / Linux

Install dependencies:

```bash
pip install -r requirements.txt
```

Run:

```bash
python app_with_dividers.py
```

---

### Option 2 — Prebuilt Executable

If you downloaded a compiled release:

1. Run the `.exe`
2. Click **Open Journals (ZIP)**
3. Select your Foundry export ZIP
4. Choose content
5. Generate PDF

---

## 📂 How to Export from Foundry

### Single Journal Export

1. Right-click journal entry
2. Export
3. Save ZIP
4. Open ZIP in this tool

### Folder Export

1. Right-click journal folder
2. Export
3. Save ZIP
4. Open ZIP in this tool

Both formats are fully supported.

---

## 🖼 SVG Image Support (Important)

SVG rendering requires **Cairo**.

Install:

### Windows

Install GTK runtime:

https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer

Then install Python dependency:

```bash
pip install cairosvg
```

---

## 🧱 Project Structure

```
app_with_dividers.py                 # Desktop UI
fvtt_parser_with_images_and_zip.py   # Foundry ZIP parser
pdf_builder_with_images.py           # PDF renderer
```

---

## 🛠 Building an Executable

Example using PyInstaller:

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --add-data "backgrounds;backgrounds" app_with_dividers.py
```

---

## 📜 License

Licensed under the **Apache License 2.0**.

See `LICENSE` file for details.

---

## 🙏 Acknowledgements

This project relies on:

* ReportLab — PDF generation
* Pillow — Image processing
* CairoSVG — SVG rendering
* Foundry Virtual Tabletop — Content platform

Foundry Virtual Tabletop is © Foundry Gaming LLC.

This project is not affiliated with or endorsed by Foundry Gaming LLC.

---

## 🚀 Roadmap

### v1.6 (Ideas)

* More bundled background packs
* Visual themes
* Header / footer customization
* Improved typography
* Cover page generator

---

## 🤝 Contributing

Contributions, bug reports, and feature requests are welcome.

Please open an issue or pull request.

---

## ⭐ Support the Project

If you find this tool useful:

* Star the repository
* Share with the Foundry community
* Report bugs or ideas

---

## 🧙 Author

Created by a Foundry GM, for Foundry GMs.

---

## Disclaimer

This tool converts exported content provided by users.
Users are responsible for respecting intellectual property rights of the content they export.

---
