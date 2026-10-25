-- filters/semantic-break.lua
-- 見出し内の強制改行マーカー {{br}} を出力形式ごとに lower する（インライン）。
--   LaTeX: \hdbreak （semantic_macros.tex 定義のロバストマクロ。既定=空白、
--          見出しの組版時のみ \titleformat 側で \\ に上書きされ改行になる。
--          目次・柱・PDF しおりでは空白になり moving 引数エラーを起こさない）
--   HTML : <br>
--   Typst: #linebreak()（目次・柱・しおりでは semantic_macros.typ の show ルールで消える）
--   その他: pandoc の LineBreak（素の改行）
--
-- {{br}} は Str の内部に埋め込まれる（例 "Part{{br}}Second"）ので、Str を分割して
-- 置換する。段落本文でも動くが、本文での \hdbreak は既定の空白になる（改行になるのは
-- \def\hdbreak{\\} を効かせている見出しのみ）。用途は主に章・節タイトルの改行位置指定。

local MARK = "{{br}}"

local function break_inline()
  if FORMAT:match("latex") then
    return pandoc.RawInline("latex", "\\hdbreak ")
  elseif FORMAT:match("html") or FORMAT:match("revealjs") then
    return pandoc.RawInline("html", "<br>")
  elseif FORMAT == "typst" then
    -- pandoc.LineBreak は Typst では「\ ＋改行」になり、見出し（= …）がその改行で終わって
    -- 後半が本文に落ちる。関数呼び出しにすれば見出しの 1 行に収まる。目次・柱・しおりでは
    -- semantic_macros.typ の show ルールで消す。末尾の ; は直後の文字を式の続きと
    -- 解釈させないため（Typst は ; を埋め込み式の終端として消費する）。
    return pandoc.RawInline("typst", "#linebreak();")
  end
  return pandoc.LineBreak()
end

function Str(el)
  if not el.text:find(MARK, 1, true) then
    return nil
  end
  local out = {}
  local rest = el.text
  while true do
    local s, e = rest:find(MARK, 1, true)
    if not s then
      if rest ~= "" then out[#out + 1] = pandoc.Str(rest) end
      break
    end
    local head = rest:sub(1, s - 1)
    if head ~= "" then out[#out + 1] = pandoc.Str(head) end
    out[#out + 1] = break_inline()
    rest = rest:sub(e + 1)
  end
  return out
end
