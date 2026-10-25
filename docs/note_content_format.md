NOTE_CONTENT :=
    FORMAT_VERSION_LINE
    (NEWLINE | EOF)
    CONTENT_BLOCK*

CONTENT_BLOCK :=
    BLOCK_SEPARATOR_LINE
    NEWLINE
    CONTENT_TYPE_LINE
    NEWLINE
    CONTENT_BODY


FORMAT_VERSION_LINE :=
    "NOTE_CONTENT_FORMAT:" SP VERSION

VERSION =
    DIGIT+ , "." , DIGIT+ ;
    
BLOCK_SEPARATOR_LINE :=
    "===BLOCK===" , LINE_COMMENT?

CONTENT_TYPE_LINE :=
    "{{BLOCK:" MAINTYPE (":" SUBTYPE)? "}}" , LINE_COMMENT?

LINE_COMMENT :=
    (SP | TAB)* , ( "#" , 行末までの任意の文字 )?

MAINTYPE :=
      "MD"
    | "HTML"
    | "EXPORT"
    | "PLAIN"
    | "IMAGE"
    | "YAML" ;

SUBTYPE :=
      "LONG"
    | "SHORT";

CONTENT_BODY :=
    次の BLOCK_SEPARATOR_LINE または EOF の直前までの1行以上

MD_BLOCK :=
    CONTENT_BLOCK where CONTENT_TYPE_LINE.MAINTYPE = "MD"

MD_LONGBLOCK :=
    CONTENT_BLOCK where CONTENT_TYPE_LINE.MAINTYPE = "MD" and CONTENT_TYPE_LINE.SUBTYPE = "LONG"

PLAIN_BLOCK :=
    CONTENT_BLOCK where CONTENT_TYPE_LINE.MAINTYPE = "PLAIN"

MD_BODY :=
    MD_BLOCK.CONTENT_BODY

IMAGE_BLOCK :=
    CONTENT_BLOCK where CONTENT_TYPE_LINE.MAINTYPE = "IMAGE"

IMAGE_BODY :=
    IMAGE_BLOCK.CONTENT_BODY

YAML_BLOCK :=
    CONTENT_BLOCK where CONTENT_TYPE_LINE.MAINTYPE = "YAML"

YAML_BODY :=
    YAML_BLOCK.CONTENT_BODY


補足ルール:
- CONTENT_BODY は1行以上でなければならない。
- CONTENT_BODY は次の BLOCK_SEPARATOR_LINE または EOF によって終了する。
- CONTENT_BODY 内では、行全体が "===BLOCK===" である行を使用できない。
- BLOCK_SEPARATOR_LINE と CONTENT_TYPE_LINE は、行末に `#` コメントを書ける（`#` 以降は行末まで無視する）。`#` の前の空白は任意。
- 行コメントは**この 2 種類の行にのみ**適用する。CONTENT_BODY には適用しない（Markdown の見出し `#` を壊さないため）。YAML_BODY 内のコメントは YAML の文法として処理される。
- FORMAT_VERSION_LINE は前方一致で判定するため、こちらも行末にコメントを書ける。
- "{{BLOCK:MD}}" は "{{BLOCK:MD:LONG}}" と同じ意味とする。
- YAML_BODY は key: value 行の羅列ではなく、1 個の YAML ドキュメントとして解析される（`pptyamlexport` が処理する）。
- YAML_BODY はレシピ YAML と同じ規則（`_include` / `_constants` / `__CONSTANT__`）で読み込まれる。相対パスは元 PPTX と同じディレクトリが基準（詳細は [pptx.md](spec/pptx.md#ノート-yaml-での-_include)）。


<!-- NOTE_CONTENTのサンプル -->
NOTE_CONTENT_FORMAT: 1.0

===BLOCK===
{{BLOCK:MD:LONG}}

# 見出し

本文です。

===BLOCK===   # 区切り行・タイプ行は行末にコメントを書ける
{{BLOCK:PLAIN}}  # ここも可
プレーンテキストです。

===BLOCK===
{{BLOCK:YAML}}
id: sample
title: "サンプル図"
baseframe: exportrange
slots:
  - id: slot1
    x: auto
    y: auto
    width: auto
    height: auto
