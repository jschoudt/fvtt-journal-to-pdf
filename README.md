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

## ✨ Features (v1.0)

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

---

## 🖥 Screenshots

<img width="1102" height="732" alt="image" src="https://github.com/user-attachments/assets/6f344cee-b1ac-4b66-b03c-9441afdcd870" />


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

### Export a Single Journal

1. Open the Journal Directory.
2. Open the Journal.
3. Select <img width="189" height="128" alt="image" src="https://github.com/user-attachments/assets/6316004a-7b5f-44c4-b6f2-f0d4dd59ab42" />
In the upper right corner of the journal window.
4. A `.zip` file will be created and automatically downloaded to your downloads folder.

### Export a Folder of Journals

1. CLick the button in the top of the journals tab. <img width="355" height="89" alt="image" src="https://github.com/user-attachments/assets/b8a28a51-8ee5-438d-a0c3-d3339ba56f16" />

2. Select **Export Folder for PDF App**. <img width="400" height="144" alt="image" src="https://github.com/user-attachments/assets/a0ef9d89-5b54-4612-b566-5fa5cd827467" />

3. Click Export.  Download will start automatically and the downloaded ZIP will be in your downloads folder.
4. The module generates a structured ZIP containing:

   * `manifest.json`
   * `/journals/` directory with journal data

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
pyinstaller --onefile --windowed app_with_dividers.py
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

### v1.1 (Planned)

* Optional parchment backgrounds
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


