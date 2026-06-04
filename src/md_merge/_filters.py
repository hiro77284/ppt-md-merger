from __future__ import annotations

from pathlib import Path


def replace_slide_placeholders(text: str, pptx_path: Path, slide_title: str, slide_idx: int) -> str:
    """Replace <__TITLE__>, <__FILENAME__>, <__BASEFILENAME__>, <__SLIDENUM__> in *text*."""
    text = text.replace("<__TITLE__>", slide_title)
    text = text.replace("<__FILENAME__>", pptx_path.name)
    text = text.replace("<__BASEFILENAME__>", pptx_path.stem)
    text = text.replace("<__SLIDENUM__>", str(slide_idx))
    return text


def escape_backslash_smart(text: str) -> str:
    lines = text.splitlines()
    processed_lines = []
    
    # 状態を管理するフラグ（あらゆるコードブロックを対象にする）
    in_code_block = False
    
    for line in lines:
        # --- 1. コードブロックの開始・終了の判定 ---
        # 行頭が ``` で始まっている場合（```{=latex} も ``` もすべてキャッチ）
        if line.strip().startswith("```"):
            # スイッチを反転させる（FalseならTrueに、TrueならFalseに）
            in_code_block = not in_code_block
            processed_lines.append(line)
            continue
            
        # --- 2. 保護エリア（何らかのコードブロック内）の処理 ---
        if in_code_block:
            # コードブロックの中（無名、latex問わず）は一切触らず、そのままスルー
            processed_lines.append(line)
        else:
            # --- 3. 通常エリアの処理（インラインコードを保護しつつ \ や & を置換） ---
            parts = line.split("`")
            for i in range(len(parts)):
                if i % 2 == 0:
                    # インラインコードの「外側」だけ、特殊文字を安全に置換
                    parts[i] = parts[i].replace("\\", "\\\\")
                    parts[i] = parts[i].replace("&", "\\&")
            
            processed_line = "`".join(parts)
            processed_lines.append(processed_line)
            
    return "\n".join(processed_lines)
