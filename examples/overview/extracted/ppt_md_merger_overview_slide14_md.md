{{#id:section:ppt_md_merger_overview:slide14}}
## インストール方法

### 1. Clone repository

```bash
git clone https://github.com/USERNAME/ppt-md-merger.git
cd ppt-md-merger
```

### 2. Create virtual environment

python仮想環境の構築
```powershell
python -m venv .venv
```

### 3. Activate virtual environment

仮想環境の有効化

```powershell
.venv\Scripts\Activate.ps1
```

仮想環境からの退出

```powershell
.venv\Scripts\deactivate.bat
```

### 4. Install package

```powershell
pip install -e .
```