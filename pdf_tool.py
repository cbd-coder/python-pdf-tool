"""PDF便利ツール - Windows / Python / PyMuPDF.

対象: 権限のあるPDFのみ。元ファイルは上書きしません。
文言置換はVer.4相当の簡易レイアウト処理です。
"""
from __future__ import annotations

from pathlib import Path
import re
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
import pymupdf

APP_TITLE = "PDF便利ツール Ver.5"
PDF_TYPES = [("PDFファイル", "*.pdf")]


def assert_new_path(output: str, inputs: list[str]):
    dest = Path(output).resolve()
    if any(dest == Path(x).resolve() for x in inputs):
        raise ValueError("元ファイルと同じ場所・名前には保存できません。別名を指定してください。")


def open_pdf(path: str, parent=None):
    """Return open, authenticated document. Caller closes it."""
    doc = pymupdf.open(path)
    try:
        if doc.needs_pass:
            pwd = simpledialog.askstring("パスワードの確認", f"{Path(path).name}\n閲覧パスワードを入力してください。", show="*", parent=parent)
            if pwd is None:
                raise InterruptedError("操作をキャンセルしました。")
            if not doc.authenticate(pwd):
                raise ValueError(f"パスワードが正しくありません：{Path(path).name}")
        return doc
    except Exception:
        doc.close()
        raise


def has_open_password(path: str) -> bool:
    # is_encrypted becomes False after successful authenticate(), so inspect anew.
    with pymupdf.open(path) as probe:
        return bool(probe.needs_pass)


def replace_pdf_text(doc, before: str, after: str) -> int:
    """Best effort ASCII text substitution + shift later spans on same row."""
    if not before or not after:
        raise ValueError("変更前・変更後の文字を入力してください。")
    if not before.isascii() or not after.isascii():
        raise ValueError("現バージョンの文言置換は英数字・ASCII記号のみ対応しています。")
    total = 0
    for page in doc:
        spans = []
        for block in page.get_text("dict", sort=False)["blocks"]:
            for line in block.get("lines", []):
                direction = line.get("dir", (1, 0))
                if abs(direction[0] - 1) > .001 or abs(direction[1]) > .001:
                    continue
                spans.extend(span for span in line.get("spans", []) if span["text"].strip())
        spans.sort(key=lambda s: (float(s["origin"][1]), float(s["origin"][0])))
        rows = []
        for span in spans:
            baseline = float(span["origin"][1]); size = float(span["size"])
            row = next((r for r in rows if abs(r["baseline"] - baseline) <= min(1.5, size * .12)
                        and abs(r["size"] - size) <= max(1.5, size * .2)), None)
            if row is None:
                row = {"baseline": baseline, "size": size, "spans": []}
                rows.append(row)
            row["spans"].append(span)
        changes = []
        for row in rows:
            ordered = sorted(row["spans"], key=lambda s: float(s["origin"][0]))
            if not any(before in s["text"] for s in ordered):
                continue
            if any(not s["text"].isascii() for s in ordered):
                raise ValueError(f"{page.number+1}ページ目：対象行に日本語等が含まれます。")
            first = next(i for i, s in enumerate(ordered) if before in s["text"])
            targets = ordered[first:]
            shift = 0.0; output_spans = []; hits = 0
            for span in targets:
                original = span["text"]
                updated = original.replace(before, after)
                hits += original.count(before)
                font = "hebo" if "bold" in span["font"].lower() else "helv"
                size = float(span["size"])
                x, y = (float(v) for v in span["origin"])
                output_spans.append((x + shift, y, updated, size, font))
                shift += (pymupdf.get_text_length(updated, fontname=font, fontsize=size)
                          - pymupdf.get_text_length(original, fontname=font, fontsize=size))
            end = max(x + pymupdf.get_text_length(s, fontname=f, fontsize=z)
                      for x, _, s, z, f in output_spans)
            if end > page.rect.x1 - 3:
                raise ValueError(f"{page.number+1}ページ目：右側へ移動するとページの外にはみ出します。")
            changes.append(([pymupdf.Rect(s["bbox"]) for s in targets], output_spans, hits))
        for rects, _, _ in changes:
            for rect in rects:
                page.add_redact_annot(rect, fill=(1, 1, 1), cross_out=False)
        if changes:
            page.apply_redactions(images=0, graphics=0, text=0)
        for _, output_spans, hits in changes:
            for x, y, s, size, font in output_spans:
                page.insert_text((x, y), s, fontsize=size, fontname=font, color=(0, 0, 0), overlay=True)
            total += hits
    if total == 0:
        raise ValueError("指定した文字が見つかりませんでした。文字列が別の領域に分かれている可能性があります。")
    return total


def save_doc(doc, path, *, encrypt_keep=True):
    doc.save(path, garbage=4, deflate=True,
             encryption=pymupdf.PDF_ENCRYPT_KEEP if encrypt_keep else pymupdf.PDF_ENCRYPT_NONE)


def parse_ranges(spec: str, num_pages: int) -> list[list[int]]:
    """'1-3, 5, 7-9' -> [[0,1,2],[4],[6,7,8]]."""
    chunks = [s.strip() for s in spec.split(",")]
    if not chunks or any(not c for c in chunks):
        raise ValueError("ページ範囲を例のように入力してください：1-3, 4-6, 7")
    groups = []
    for s in chunks:
        match = re.fullmatch(r"(\d+)\s*(?:-\s*(\d+))?", s)
        if not match:
            raise ValueError(f"ページ範囲が不正です：{s}")
        first = int(match[1]); last = int(match[2] or match[1])
        if not 1 <= first <= last <= num_pages:
            raise ValueError(f"ページが範囲外です：{s}（1～{num_pages}）")
        groups.append(list(range(first - 1, last)))
    return groups


class PDFTool(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("790x630")
        self.minsize(710, 590)
        # Do not use Tcl option_add with a font name containing spaces: it can be parsed as invalid font size.
        self._sources: list[str] = []
        self._page_source: str = ""
        self._page_order: list[int] = []
        self.make_ui()

    def make_ui(self):
        top = ttk.Frame(self, padding=(16, 12))
        top.pack(fill="x")
        ttk.Label(top, text=APP_TITLE, font=("Yu Gothic UI", 15, "bold")).pack(anchor="w")
        ttk.Label(top, text="元のPDFは変更しません。編集後のPDFは別名で保存します。",
                  foreground="#555555").pack(anchor="w", pady=(4, 0))
        tabs = ttk.Notebook(self)
        tabs.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        for title, maker in [
            ("文言置換", self.tab_replace), ("結合", self.tab_merge),
            ("分割", self.tab_split), ("ページ順変更", self.tab_reorder),
            ("パスワード設定", self.tab_lock), ("パスワード解除", self.tab_unlock),
        ]:
            pane = ttk.Frame(tabs, padding=18)
            tabs.add(pane, text=title)
            maker(pane)

    def row_file(self, parent, title="対象PDF"):
        ttk.Label(parent, text=title).pack(anchor="w", pady=(8, 3))
        row = ttk.Frame(parent); row.pack(fill="x", pady=(0, 12))
        value = tk.StringVar()
        ttk.Entry(row, textvariable=value).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="参照", command=lambda: self.browse(value)).pack(side="left", padx=(7, 0))
        return value

    def browse(self, var):
        path = filedialog.askopenfilename(parent=self, filetypes=PDF_TYPES)
        if path: var.set(path)

    def choose_save(self, src, suffix):
        return filedialog.asksaveasfilename(parent=self, defaultextension=".pdf", filetypes=PDF_TYPES,
             initialdir=str(Path(src).parent), initialfile=f"{Path(src).stem}_{suffix}.pdf")

    def line_entry(self, parent, title, mask=None):
        ttk.Label(parent, text=title).pack(anchor="w", pady=(5, 3))
        var = tk.StringVar()
        ttk.Entry(parent, textvariable=var, show=mask or "").pack(fill="x", pady=(0, 9))
        return var

    def note(self, parent, content):
        ttk.Label(parent, text=content, foreground="#555555", wraplength=700,
                  justify="left").pack(anchor="w", pady=(9, 8))

    def execute(self, func):
        try:
            text = func()
            if text: messagebox.showinfo("完了", text, parent=self)
        except InterruptedError:
            pass
        except Exception as exc:
            messagebox.showerror("処理できませんでした", str(exc), parent=self)

    def tab_replace(self, pane):
        src = self.row_file(pane)
        before = self.line_entry(pane, "変更前の文字（英数字）")
        after = self.line_entry(pane, "変更後の文字（英数字）")
        self.note(pane, "文字サイズを維持し、同じ行の右側の文字を移動します。単純な横書き英文PDF向け。\n"
                  "フォントや背景が変わることがあります。保存後に必ず目視確認してください。")
        def go():
            if not Path(src.get()).is_file(): raise ValueError("PDFを選択してください。")
            if not before.get() or not after.get(): raise ValueError("変更前・変更後の文字を入力してください。")
            out = self.choose_save(src.get(), "edited")
            if not out: return
            assert_new_path(out, [src.get()])
            with open_pdf(src.get(), self) as doc:
                hits = replace_pdf_text(doc, before.get(), after.get())
                save_doc(doc, out)
            return f"{hits}か所を変更しました。\n{out}\n\n文字の重なり・レイアウトを確認してください。"
        ttk.Button(pane, text="置き換えて別名保存", command=lambda: self.execute(go)).pack(fill="x", pady=15)

    def tab_merge(self, pane):
        self.note(pane, "複数のPDFを並び順に結合します。リスト内の上下移動が可能です。")
        lst = tk.Listbox(pane, height=13, selectmode=tk.EXTENDED)
        lst.pack(fill="both", expand=True)
        row = ttk.Frame(pane); row.pack(fill="x", pady=9)
        def refresh():
            lst.delete(0, tk.END)
            for path in self._sources: lst.insert(tk.END, Path(path).name)
        def add():
            files = filedialog.askopenfilenames(parent=self, filetypes=PDF_TYPES)
            for p in files:
                if p not in self._sources: self._sources.append(p)
            refresh()
        def remove():
            for i in reversed(lst.curselection()): del self._sources[i]
            refresh()
        def move(delta):
            selected = lst.curselection()
            if len(selected) != 1: return
            i = selected[0]; j = i + delta
            if j < 0 or j >= len(self._sources): return
            self._sources[i], self._sources[j] = self._sources[j], self._sources[i]
            refresh(); lst.selection_set(j); lst.see(j)
        for label, cmd in [("PDFを追加", add), ("選択を削除", remove), ("↑ 上へ", lambda: move(-1)), ("↓ 下へ", lambda: move(1))]:
            ttk.Button(row, text=label, command=cmd).pack(side="left", padx=(0, 8))
        def go():
            if len(self._sources) < 2: raise ValueError("PDFを2つ以上追加してください。")
            out = self.choose_save(self._sources[0], "merged")
            if not out: return
            assert_new_path(out, self._sources)
            result = pymupdf.open(); had_protected = False
            try:
                for path in self._sources:
                    with open_pdf(path, self) as src:
                        had_protected |= has_open_password(path)
                        result.insert_pdf(src)
                if had_protected and not messagebox.askyesno("保護PDFの結合", "パスワード付きPDFが含まれています。\n結合後のPDFはパスワードなしで保存されます。\n続行しますか？", parent=self):
                    return
                save_doc(result, out, encrypt_keep=False)
                pages = len(result)
            finally:
                result.close()
            return f"{len(self._sources)}ファイル（計{pages}ページ）を結合しました。\n{out}"
        ttk.Button(pane, text="この順番で結合して保存", command=lambda: self.execute(go)).pack(fill="x", pady=8)

    def tab_split(self, pane):
        src = self.row_file(pane)
        self.note(pane, "ページごと：1ページずつ別のPDFへ\n"
                  "範囲指定：例 1-3, 4-6, 7 → 3つのPDFを作成します。")
        mode = tk.StringVar(value="ranges")
        ttk.Radiobutton(pane, text="ページ範囲ごとに分割", variable=mode, value="ranges").pack(anchor="w", pady=3)
        ranges = self.line_entry(pane, "範囲（例：1-3, 4-6, 7）")
        ttk.Radiobutton(pane, text="1ページずつ分割", variable=mode, value="every").pack(anchor="w", pady=3)
        def go():
            if not Path(src.get()).is_file(): raise ValueError("PDFを選択してください。")
            folder = filedialog.askdirectory(parent=self, title="分割PDFの保存フォルダ")
            if not folder: return
            with open_pdf(src.get(), self) as doc:
                groups = ([[i] for i in range(len(doc))] if mode.get() == "every"
                          else parse_ranges(ranges.get(), len(doc)))
                if has_open_password(src.get()) and not messagebox.askyesno("保護PDFの分割", "分割後のPDFはパスワードなしで保存されます。\n続行しますか？", parent=self):
                    return
                names = [Path(folder) / f"{Path(src.get()).stem}_part_{i:03d}.pdf"
                         for i in range(1, len(groups) + 1)]
                existing = [p for p in names if p.exists()]
                if existing:
                    raise ValueError(f"保存先に同名ファイルが存在します：{existing[0].name}\n別のフォルダを選んでください。")
                for name, indices in zip(names, groups):
                    with pymupdf.open() as part:
                        for i in indices: part.insert_pdf(doc, from_page=i, to_page=i)
                        save_doc(part, str(name), encrypt_keep=False)
            return f"{len(groups)}個のPDFを作成しました。\n保存先：{folder}"
        ttk.Button(pane, text="分割して保存", command=lambda: self.execute(go)).pack(fill="x", pady=15)

    def tab_reorder(self, pane):
        self.note(pane, "PDF内のページ順を上下ボタンで変更します。元のPDFは残します。")
        row = ttk.Frame(pane); row.pack(fill="x", pady=5)
        self.page_label = ttk.Label(row, text="PDFが選択されていません", wraplength=530)
        self.page_label.pack(side="left", fill="x", expand=True)
        def select():
            path = filedialog.askopenfilename(parent=self, filetypes=PDF_TYPES)
            if not path: return
            try:
                with open_pdf(path, self) as doc:
                    count = len(doc)
                self._page_source = path
                self._page_order = list(range(count))
                self.page_label.configure(text=Path(path).name)
                refresh()
            except InterruptedError: pass
            except Exception as exc: messagebox.showerror("確認", str(exc), parent=self)
        ttk.Button(row, text="PDFを選択", command=select).pack(side="right")
        lst = tk.Listbox(pane, height=13, exportselection=False)
        lst.pack(fill="both", expand=True, pady=7)
        def refresh():
            selection = lst.curselection()
            lst.delete(0, tk.END)
            for index in self._page_order:
                lst.insert(tk.END, f"元の {index+1} ページ目")
            if selection and selection[0] < lst.size(): lst.selection_set(selection[0])
        def move(delta):
            sel = lst.curselection()
            if not sel: return
            i = sel[0]; j = i + delta
            if not 0 <= j < len(self._page_order): return
            self._page_order[i], self._page_order[j] = self._page_order[j], self._page_order[i]
            refresh(); lst.selection_clear(0, tk.END); lst.selection_set(j); lst.see(j)
        actions = ttk.Frame(pane); actions.pack(fill="x", pady=5)
        ttk.Button(actions, text="↑ 1つ上へ", command=lambda: move(-1)).pack(side="left", padx=(0, 9))
        ttk.Button(actions, text="↓ 1つ下へ", command=lambda: move(1)).pack(side="left")
        def go():
            if not self._page_source: raise ValueError("PDFを選択してください。")
            dest = self.choose_save(self._page_source, "reordered")
            if not dest: return
            assert_new_path(dest, [self._page_source])
            with open_pdf(self._page_source, self) as doc:
                if len(doc) != len(self._page_order):
                    raise ValueError("元のPDFのページ数が変わりました。再選択してください。")
                doc.select(self._page_order)
                save_doc(doc, dest)
            return f"ページ順を変更しました。\n{dest}"
        ttk.Button(pane, text="この順番で別名保存", command=lambda: self.execute(go)).pack(fill="x", pady=10)

    def tab_lock(self, pane):
        src = self.row_file(pane)
        passwd = self.line_entry(pane, "開くときのパスワード（必須）", "*")
        confirm = self.line_entry(pane, "開くときのパスワード（確認）", "*")
        owner = self.line_entry(pane, "管理者用パスワード（任意。未入力なら上と同じ）", "*")
        self.note(pane, "AES-256で暗号化します。パスワードを忘れると開けなくなることがあります。\n"
                  "閲覧用と管理者用を別に設定することを推奨します。")
        def go():
            if not Path(src.get()).is_file(): raise ValueError("PDFを選択してください。")
            if not passwd.get(): raise ValueError("パスワードを入力してください。")
            if passwd.get() != confirm.get(): raise ValueError("確認用パスワードが一致しません。")
            out = self.choose_save(src.get(), "protected")
            if not out: return
            assert_new_path(out, [src.get()])
            with open_pdf(src.get(), self) as doc:
                doc.save(out, garbage=4, deflate=True, encryption=pymupdf.PDF_ENCRYPT_AES_256,
                         user_pw=passwd.get(), owner_pw=owner.get() or passwd.get())
            return f"PDFにパスワードを設定しました。\n{out}"
        ttk.Button(pane, text="パスワードを設定して保存", command=lambda: self.execute(go)).pack(fill="x", pady=15)

    def tab_unlock(self, pane):
        src = self.row_file(pane)
        self.note(pane, "正しいパスワードを知っている・解除する権限があるPDFのみ使用してください。\n"
                  "解除後のPDFは誰でも開ける状態になります。元のファイルは残します。")
        def go():
            if not Path(src.get()).is_file(): raise ValueError("PDFを選択してください。")
            with open_pdf(src.get(), self) as doc:
                if not has_open_password(src.get()):
                    raise ValueError("このPDFには開くときのパスワードが設定されていません。")
                out = self.choose_save(src.get(), "unlocked")
                if not out: return
                assert_new_path(out, [src.get()])
                if not messagebox.askyesno("パスワード保護の解除", "パスワードなしのPDFを書き出します。\n続行しますか？", parent=self):
                    return
                save_doc(doc, out, encrypt_keep=False)
            return f"パスワード保護を解除したコピーを保存しました。\n{out}"
        ttk.Button(pane, text="パスワードを解除して別名保存", command=lambda: self.execute(go)).pack(fill="x", pady=15)


if __name__ == "__main__":
    PDFTool().mainloop()
