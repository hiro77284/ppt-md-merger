-- center.lua
-- Div .center を中央寄せブロックに lower する。
--   LaTeX: \begin{center} ... \end{center}（組込み環境。ヘッダ定義不要）
--   HTML : <div class="center" style="text-align:center">（CSS 未読込でも効くよう inline style）
--   その他の形式: 素通り
function Div(el)
  if not el.classes:includes("center") then
    return nil
  end
  if FORMAT:match("latex") then
    table.insert(el.content, 1, pandoc.RawBlock("latex", "\\begin{center}"))
    table.insert(el.content, pandoc.RawBlock("latex", "\\end{center}"))
    return el
  elseif FORMAT:match("html") then
    el.attributes["style"] = "text-align:center"
    return el
  elseif FORMAT == "typst" then
    -- #semcenter（templates/semantic_macros.typ）。Div を外して中身を直接包む
    -- （Div のままだと Typst writer が余分な #block[ ] で包む）。
    local out = { pandoc.RawBlock("typst", "#semcenter[") }
    for _, b in ipairs(el.content) do out[#out + 1] = b end
    out[#out + 1] = pandoc.RawBlock("typst", "]")
    return out
  end
  return nil
end
