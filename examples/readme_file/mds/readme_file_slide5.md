<!-- md_merge_rawtitle: 環境構築 -->
{{#id:section:readme_file:slide5}}
## 環境構築

Pyrhon 環境の構築に慣れている方はご自分の仕様で構築してください。

### Python環境の構築

Python Install Manager をインストール
```powershell
winget install 9NQ7512CXL7T
```

Python をインストール　（3.15.2をインストールする例を示しますがバージョンは適宜変更してください）
```powershell
py install 3.15.2
```

インストールできたことを確認する。Python 3.15 が 表示されればOK
```powershell
py list
Tag           Name           Managed By  Version  Alias
3.15[-64]  *  Python 3.15.2  PythonCore  3.15.2   python3[-64].exe, python3.15[-64].exe
```

### Pandoc

```powershell
winget install --id JohnMacFarlane.Pandoc -e
```

### Typst

Typst をインストールする
```powershell
winget install --id Typst.Typst -e
```

### ppt-md-merger

ppt-md-merger インストール用の親ディレクトリを作って GitHub から ppt-md-merge の最新バージョンを入手
```powershell
mkdir c:\tools
cd c:\tools
git clone --depth 1 --single-branch -b main https://github.com/hiro77284/ppt-md-merger.git
```

ppt-md-merger ディレクトリにPython仮想環境を作り、有効化する
```powershell
cd ppt-md-merger
py -V:3.15 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

プロンプトが
```powershell
(.venv) PS C:\tools\ppt-md-merger>
```
のように変わればPython仮想環境が有効になっています。

ppt-md-merger をインストールする
```powershell
cd C:\tools\ppt-md-merger>
python -m pip install -e .
```

-e で editable install すると、githubから最新版をDLするとすぐに反映されます。

### サンプル文書のコンパイル


サンプル文書をコンパイルしてみる
```powershell
cd examples/pdf1_minimum/
pptmdmerge ppt_to_pdf src/pdf1_minimum_pdf_recipe.yaml --keep-work
```
動作ログが表示されたのち、最後に完了メッセージが流れれば成功です。所要時間は環境により異なります。

```powershell
========================================
  ppt_to_pdf 完了
  所要時間: 7.7秒
========================================
```

成果物は

PDFファイル： build/pdf1_minimum_target.pdf

です。　その他に、

```powershell
pptmdmerge ppt_to_puremd src/pdf1_minimum_pdf_recipe.yaml --keep-work
```
で、

MDファイル： build/pdf1_minimum_target_puremd.md

を生成します。PDFではなくMDで配付したい場合はこれをbuild/images ディレクトリとともに配付します。

```powershell
pptmdmerge ppt_to_githubmd src/pdf1_minimum_pdf_recipe.yaml --keep-work
```
で、

GitHub 仕様のMDファイル： build/pdf1_minimum_target_github.md

を生成します。