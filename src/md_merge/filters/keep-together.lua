-- keep-together.lua
-- Div .keep-together を「ページ内で分割されないブロック」に lower する。
--   LaTeX: \begin{minipage}{\linewidth} ... \end{minipage}
--          minipage は分割不可のボックス。現ページに収まらなければブロックごと次ページへ
--          送られる＝途中改ページを防ぐ。（旧実装の \Needspace は先頭に空きを確保するだけで
--          内部の分割は防げなかった。）
--   HTML : <div class="keep-together">（class 保持。semantic.css の break-inside:avoid が効く）
--   その他の形式: class を保持して素通り
--
-- 注意:
--   - 内容が 1 ページに収まらない場合は minipage が溢れる（1 ページを超えるブロックは
--     そもそも 1 ページにまとめられない）。
--   - minipage 内では float（\begin{figure} 等）は使えない。画像を含めるなら非 float
--     画像にすること（このツールの既定の画像出力は非 float の \includegraphics）。
function Div(el)
  if not el.classes:includes("keep-together") then
    return nil
  end
  if FORMAT:match("latex") then
    table.insert(el.content, 1, pandoc.RawBlock("latex", "\\par\\noindent\\begin{minipage}{\\linewidth}"))
    table.insert(el.content, pandoc.RawBlock("latex", "\\end{minipage}\\par"))
    return el
  elseif FORMAT == "typst" then
    -- #semkeeptogether（templates/semantic_macros.typ）= 分割しない block
    local out = { pandoc.RawBlock("typst", "#semkeeptogether[") }
    for _, b in ipairs(el.content) do out[#out + 1] = b end
    out[#out + 1] = pandoc.RawBlock("typst", "]")
    return out
  end
  return el  -- HTML 他: class を保持（CSS break-inside:avoid が効く）
end
