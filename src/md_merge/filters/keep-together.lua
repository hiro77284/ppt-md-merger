-- keep-together.lua
-- Div .keep-together を「ページ内で分割されないブロック」に lower する。
--   Typst: #semkeeptogether[...]（分割しない block）
--   HTML : <div class="keep-together">（class 保持。semantic.css の break-inside:avoid が効く）
--   その他の形式: class を保持して素通り
function Div(el)
  if not el.classes:includes("keep-together") then
    return nil
  end
  if FORMAT == "typst" then
    -- #semkeeptogether（templates/semantic_macros.typ）= 分割しない block
    local out = { pandoc.RawBlock("typst", "#semkeeptogether[") }
    for _, b in ipairs(el.content) do out[#out + 1] = b end
    out[#out + 1] = pandoc.RawBlock("typst", "]")
    return out
  end
  return el  -- HTML 他: class を保持（CSS break-inside:avoid が効く）
end
